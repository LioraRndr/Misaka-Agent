"""A card whose accepted files changed after submission is not a tampered run, it is a Sister
who kept working: after `misaka_card_complete` she answers the Last Order's DMs and edits her
deliverables, settle itself rebuilds her SOURCES.md, and a node-level ledger is written by every
card that shares it. Until 2026-09-24 the first such file failed the whole run with "Accepted
artifact changed before Research registration", and `/research resume` re-hit it forever (18
changed paths across 6 cards on run r_5b1357a9c6). Now the card's own changed files send the card
back to its Sister to declare again, derived and shared files are skipped, and a halt leaves the
reopening to resume."""
import hashlib
from contextlib import closing
from pathlib import Path

import pytest

from misaka.core.network import dispatch
from misaka.core.platform import cards, repo, tasks
from misaka.core.research import runs, workflow


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(repo, "enabled", lambda *a: False)
    monkeypatch.setattr(workflow, "_bundle", lambda *a, **k: None)
    with closing(tasks.connect(str(tmp_path / "board.db"))) as con:
        run = runs.create(con, workspace=str(tmp_path), question="Fixture question")
        yield con, run, runs.nodes(con, run["id"])[0]


def _accept(con, run, root, local_id, files):
    """A card accepted with ``files`` ({relative-to-output-dir or workspace path: text}) declared."""
    tid = cards.create(con, run["workspace"], f"card {local_id}", "fixture body", "fixture")
    runs.link_task(con, run["id"], tid, kind="research", node=root, local_id=local_id)
    task = tasks.get(con, tid)
    rels = []
    for name, text in files.items():
        path = Path(run["workspace"], name) if name.startswith("nodes/") else Path(task["output_dir"], name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        rels.append(str(path.relative_to(run["workspace"])))
    con.execute("UPDATE tasks SET status='running',claim_lock='fixture',claim_expires=? WHERE id=?", (10**12, tid))
    assert dispatch.accept_state(con, tasks.get(con, tid), {"summary": "fixture", "artifacts": rels},
                                 generation=task["generation"], claim_lock="fixture")
    return tid, {rel: Path(run["workspace"], rel) for rel in rels}


def test_a_changed_deliverable_sends_the_card_back_while_the_others_settle(state):
    con, run, root = state
    intact, _ = _accept(con, run, root, "intact", {"a.md": "kept\n"})
    drifted, paths = _accept(con, run, root, "drifted", {"b.md": "first\n", "c.md": "same\n"})
    next(p for p in paths if p.endswith("b.md"))
    Path(run["workspace"], next(p for p in paths if p.endswith("b.md"))).write_text("revised after completion\n", encoding="utf-8")

    workflow.settle_done_tasks(con, run_id=run["id"])

    assert [row["kind"] for row in runs.artifacts(con, run["id"], task_id=intact)] == ["task_output"]
    assert tasks.latest_payload(con, intact, "research_v2_settled", generation=1)
    row = tasks.get(con, drifted)
    assert row["status"] in {"ready", "todo"} and int(row["generation"]) == 2
    assert runs.artifacts(con, run["id"], task_id=drifted) == []
    drift = tasks.latest_payload(con, drifted, "research_artifact_drift", generation=1)
    assert drift and "b.md" in drift and "c.md" not in drift
    assert tasks.latest_payload(con, drifted, "research_resumed", generation=2)
    assert workflow._cards_reopened(con, run, root) == [drifted]


def test_derived_bundle_and_shared_node_files_are_never_drift(state):
    con, run, root = state
    tid, paths = _accept(con, run, root, "shared", {
        "notes.md": "own\n", "SOURCES.md": "bundle\n", "sources/x.md": "link\n",
        f"nodes/{run['id']}/coordination_ledger.md": "ledger v1\n"})
    for rel, path in paths.items():
        if rel.endswith(("SOURCES.md", "x.md", "coordination_ledger.md")):
            path.write_text("rewritten by settle, a link, or another card\n", encoding="utf-8")

    workflow.settle_done_tasks(con, run_id=run["id"])

    registered = runs.artifacts(con, run["id"], task_id=tid)
    assert [Path(row["path"]).name for row in registered] == ["notes.md"]
    assert tasks.get(con, tid)["status"] == "done"
    assert tasks.latest_payload(con, tid, "artifact_derived_skipped", generation=1)
    assert tasks.latest_payload(con, tid, "artifact_outside_card", generation=1)


def test_a_halt_records_the_drift_and_resume_reopens_the_card(state):
    con, run, root = state
    tid, paths = _accept(con, run, root, "halted", {"d.md": "first\n"})
    next(iter(paths.values())).write_text("changed\n", encoding="utf-8")

    workflow.settle_done_tasks(con, run_id=run["id"], reopen_drift=False)
    assert tasks.get(con, tid)["status"] == "done"
    assert tasks.latest_payload(con, tid, "research_artifact_drift", generation=1)

    runs.set_state(con, run["id"], status="stopped")
    runs.resume(con, run["id"])
    row = tasks.get(con, tid)
    assert row["status"] in {"ready", "todo"} and int(row["generation"]) == 2


def test_a_newer_declaration_is_settled_again_and_not_treated_as_drift(state):
    con, run, root = state
    tid, paths = _accept(con, run, root, "redeclared", {"f.md": "first\n"})
    workflow.settle_done_tasks(con, run_id=run["id"])
    first = runs.artifacts(con, run["id"], task_id=tid)[0]["sha256"]

    path = next(iter(paths.values()))
    path.write_text("revised, then declared again by the Sister's own session\n", encoding="utf-8")
    rel = str(path.relative_to(run["workspace"]))
    prepared = dispatch.prepare_submission(tasks.get(con, tid), {"summary": "fixture", "artifacts": [rel]})
    tasks.add_event(con, tid, "submitted", prepared.payload, generation=1)

    workflow.settle_done_tasks(con, run_id=run["id"])
    registered = runs.artifacts(con, run["id"], task_id=tid)
    assert len(registered) == 1 and registered[0]["sha256"] != first
    assert registered[0]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert int(tasks.get(con, tid)["generation"]) == 1
    assert tasks.latest_payload(con, tid, "research_artifact_drift", generation=1) is None


def test_resume_ignores_a_drift_older_than_the_latest_declaration(state):
    con, run, root = state
    tid, paths = _accept(con, run, root, "stale-drift", {"g.md": "first\n"})
    path = next(iter(paths.values()))
    path.write_text("changed\n", encoding="utf-8")
    workflow.settle_done_tasks(con, run_id=run["id"], reopen_drift=False)
    assert tasks.latest_payload(con, tid, "research_artifact_drift", generation=1)
    rel = str(path.relative_to(run["workspace"]))
    prepared = dispatch.prepare_submission(tasks.get(con, tid), {"summary": "fixture", "artifacts": [rel]})
    tasks.add_event(con, tid, "submitted", prepared.payload, generation=1)

    runs.set_state(con, run["id"], status="stopped")
    runs.resume(con, run["id"])
    assert tasks.get(con, tid)["status"] == "done" and int(tasks.get(con, tid)["generation"]) == 1


def test_a_missing_deliverable_is_drift_too(state):
    con, run, root = state
    tid, paths = _accept(con, run, root, "gone", {"e.md": "first\n"})
    next(iter(paths.values())).unlink()
    workflow.settle_done_tasks(con, run_id=run["id"])
    assert int(tasks.get(con, tid)["generation"]) == 2
    assert hashlib.sha256(b"first\n").hexdigest() not in {row["sha256"] for row in runs.artifacts(con, run["id"])}
