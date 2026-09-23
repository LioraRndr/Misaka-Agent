"""Completion does not end a Sister's session. A note from Last Order that crosses the
completion, or another Sister's DM, starts more turns in it, and the deliverables those turns
change stayed declared under the old digests; the run's settle then saw bytes that did not match
the declaration (2026-09-24: 18 changed paths on 6 cards, a whole run failed). The declaration
now follows the work: at the end of any further clean turn the runtime rebuilds the submission
from the output folder and records it as a newer ``submitted`` row, without a model turn."""
import hashlib
import json
import os
import time

import pytest

from misaka.core.network import todo
from misaka.core.platform import tasks

BODY = ("## research question\nWhy?\n\n## deliverable\nreport.md\n"
        "Write it under the deliverable location the card names.\n\n## boundaries\nnone\n")


class _Moments:
    def send_message(self, message, options):
        return None


class _Agent:
    async def waitForIdle(self):
        return None


class _Session:
    def __init__(self, session_file):
        self.moments = _Moments()
        self.agent = _Agent()
        self.sessionManager = type("SM", (), {"sessionFile": session_file})()


@pytest.fixture
def card(tmp_path, monkeypatch, request):
    from misaka.core.network import worker
    from misaka.core.platform import cards
    con = tasks.connect(str(tmp_path / "board.db"))
    request.addfinalizer(con.close)
    out = tmp_path / "nodes" / "cards" / "t1"
    out.mkdir(parents=True)
    tid = cards.create(con, str(tmp_path), "T1 report", BODY, "10032")
    session_file = str(tmp_path / "sister.jsonl")
    con.execute("UPDATE tasks SET status='running', claim_lock='lock1', claim_expires=?, output_dir=?, "
                "worker_pid=?, session_file=? WHERE id=?",
                (int(time.time()) + 1800, str(out), os.getpid(), session_file, tid))
    worker.record_output_baseline(con, tasks.get(con, tid))
    monkeypatch.setenv("MISAKA_USAGE_TASK_ID", tid)
    monkeypatch.setenv("MISAKA_USAGE_CLAIM_LOCK", "lock1")
    monkeypatch.setenv("MISAKA_USAGE_GENERATION", "1")
    monkeypatch.delenv("MISAKA_SISTER_OWNER_CLAIM_LOCK", raising=False)
    part = todo.TodoPart(tid, "10032")
    part._con = con
    part.attach(_Session(session_file))
    return con, tid, out, part


def _turn(reason, text):
    return {"type": "agent_end", "messages": [
        {"role": "assistant", "stopReason": reason, "content": [{"type": "text", "text": text}]}]}


async def _end_turn(part, text="done for now", reason="stop"):
    await part.agent_end(_turn(reason, text))
    await part.agent_settled()


def _submissions(con, tid):
    return [json.loads(r["payload"]) for r in con.execute(
        "SELECT payload FROM events WHERE task_id=? AND kind='submitted' ORDER BY id", (tid,))]


async def _complete(con, tid, out, part):
    (out / "report.md").write_text("first version\n")
    part._completion = (1, "delivered")
    await _end_turn(part, "delivered")
    assert tasks.get(con, tid)["status"] == "done"
    assert len(_submissions(con, tid)) == 1


async def test_a_later_turn_that_changed_the_deliverable_declares_it_again(card):
    con, tid, out, part = card
    await _complete(con, tid, out, part)
    (out / "report.md").write_text("revised after Last Order's note\n")
    (out / "extra.csv").write_text("a,b\n")

    await _end_turn(part, "revised as asked")

    rows = _submissions(con, tid)
    assert len(rows) == 2 and rows[-1]["summary"] == rows[0]["summary"]
    rel = str((out / "report.md").relative_to(out.parents[2]))
    assert rows[-1]["artifact_digests"][rel] == hashlib.sha256(b"revised after Last Order's note\n").hexdigest()
    assert any(path.endswith("extra.csv") for path in rows[-1]["artifacts"])
    row = tasks.get(con, tid)
    assert row["status"] == "done" and int(row["generation"]) == 1
    assert tasks.latest_payload(con, tid, "redeclared", generation=1)


async def test_a_turn_that_changed_nothing_declares_nothing(card):
    con, tid, out, part = card
    await _complete(con, tid, out, part)
    await _end_turn(part, "just a reply to Last Order")
    assert len(_submissions(con, tid)) == 1
    assert tasks.latest_payload(con, tid, "redeclared", generation=1) is None


async def test_an_aborted_turn_and_another_session_do_not_declare(card):
    con, tid, out, part = card
    await _complete(con, tid, out, part)
    (out / "report.md").write_text("changed\n")
    await _end_turn(part, "", reason="aborted")
    assert len(_submissions(con, tid)) == 1
    part.session.sessionManager.sessionFile = str(out.parents[2] / "someone-else.jsonl")
    await _end_turn(part, "a reader pane's turn")
    assert len(_submissions(con, tid)) == 1
