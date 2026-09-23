"""A plan larger than one reply is submitted in several `misaka_research_assign` calls.

2026-09-23: the root plan turn wrote a plan longer than the reply's output cap, lost it to
truncation, and then shrank the plan to fit one call -- the tool replaced the record wholesale,
so it could not be split. An append call folds onto the recorded plan instead."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from misaka.core.platform import tasks
from misaka.core.research import commands, planner, runs
from misaka.core.research.prompting import RESEARCH_LO_ORCHESTRATION

ROSTER = [{"id": "10032"}, {"id": "10043"}]


def task(local_id, **fields):
    return {"local_id": local_id, "title": local_id, "question": "q", "rationale": "r",
            "deliverable": "findings.md", "assignee": "10032", "assignee_reason": "fits", **fields}


def first_plan():
    return {"status": "ready", "plan_markdown": "design", "tasks": [task("a")],
            "red_team": {"assignee": "10043", "reason": "critic"}}


def validate(value):
    return planner.validate_plan(value, ROSTER)


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(runs, "_commit", lambda *a, **k: None)
    con = tasks.connect(str(tmp_path / "board.db"))
    run = runs.create(con, workspace=str(tmp_path), question="fixture")
    root = runs.nodes(con, run["id"])[0]
    assert runs.acquire_driver(con, run["id"], "driver")
    runs.prepare_runner(con, "research_branches", root["id"])
    try:
        yield con, runs.get(con, run["id"]), runs.node(con, root["id"])
    finally:
        con.close()


def ctx(session_file):
    return SimpleNamespace(sessionManager=SimpleNamespace(sessionFile=session_file))


def test_merge_keeps_recorded_tasks_and_replaces_by_local_id():
    recorded = validate({**first_plan(), "tasks": [task("a"), task("b", title="old b")]})
    merged = commands.merge_plan(recorded, {"status": "ready", "plan_markdown": "", "tasks": [
        task("b", title="new b"), task("c")], "red_team": None, "reframed_question": ""})
    assert [t["local_id"] for t in merged["tasks"]] == ["a", "b", "c"]
    assert merged["tasks"][1]["title"] == "new b"
    assert merged["plan_markdown"] == "design"
    assert merged["red_team"]["assignee"] == "10043"
    replaced = commands.merge_plan(recorded, {"status": "ready", "plan_markdown": "v2", "tasks": [],
                                              "red_team": {"assignee": "10032", "reason": "swap"}})
    assert (replaced["plan_markdown"], replaced["red_team"]["assignee"]) == ("v2", "10032")


async def test_append_during_the_wait_folds_onto_the_recorded_plan(state):
    con, run, root = state
    runs.set_node(con, root["id"], status="awaiting_approval")
    session_file = str(Path(run["workspace"]) / "session.jsonl")
    runs.record_action(con, run, root, "plan", validate(first_plan()), session_file=session_file, tool_call_id="c1")
    runs.record_action(con, run, root, "start", {}, session_file=session_file, tool_call_id="s1")
    assign = next(t for t in commands.review_tools(con, run, root, validate=validate, session_file=session_file)
                  if t.name == "misaka_research_assign")
    result = await assign.execute("c2", {"status": "ready", "append": True, "tasks": [task("b", dependencies=["a"])]},
                                  None, None, ctx(session_file))
    recorded = runs.action(con, run["id"], root["id"], "plan")
    assert [t["local_id"] for t in recorded["payload"]["tasks"]] == ["a", "b"]
    assert recorded["payload"]["plan_markdown"] == "design"
    assert "append" not in recorded["payload"]
    assert recorded["tool_call_id"] == "c2"
    assert runs.action(con, run["id"], root["id"], "start") is None    # a changed plan needs a fresh go-ahead
    assert "2 task(s)" in result["content"][0]["text"]


async def test_append_is_validated_as_one_plan_and_a_bad_half_changes_nothing(state):
    con, run, root = state
    runs.set_node(con, root["id"], status="awaiting_approval")
    session_file = str(Path(run["workspace"]) / "session.jsonl")
    runs.record_action(con, run, root, "plan", validate(first_plan()), session_file=session_file, tool_call_id="c1")
    assign = next(t for t in commands.review_tools(con, run, root, validate=validate, session_file=session_file)
                  if t.name == "misaka_research_assign")
    with pytest.raises(ValueError, match="unknown dependencies"):
        await assign.execute("c2", {"status": "ready", "append": True, "tasks": [task("b", dependencies=["zz"])]},
                             None, None, ctx(session_file))
    recorded = runs.action(con, run["id"], root["id"], "plan")
    assert [t["local_id"] for t in recorded["payload"]["tasks"]] == ["a"]
    assert recorded["tool_call_id"] == "c1"


async def test_phase_tool_appends_within_the_planning_turn(state):
    con, run, root = state
    session_file = str(Path(run["workspace"]) / "session.jsonl")
    tool = commands.tool(con, run, root, key="plan", name="misaka_research_assign", description="d",
                         model=commands.Plan, validate=validate, session_dir=run["workspace"],
                         session_file=session_file, merge=commands.merge_plan)
    await tool.execute("c1", first_plan(), None, None, ctx(session_file))
    await tool.execute("c2", {"status": "ready", "append": True, "tasks": [task("b")]}, None, None, ctx(session_file))
    recorded = runs.action(con, run["id"], root["id"], "plan")
    assert [t["local_id"] for t in recorded["payload"]["tasks"]] == ["a", "b"]
    assert recorded["tool_call_id"] == "c2"
    # A first call marked append, with nothing recorded yet, is an ordinary first submission.
    runs.delete_action(con, run["id"], root["id"], "plan")
    await tool.execute("c3", {**first_plan(), "append": True}, None, None, ctx(session_file))
    assert runs.action(con, run["id"], root["id"], "plan")["payload"]["tasks"][0]["local_id"] == "a"


def test_an_append_without_a_design_is_still_refused_as_a_first_plan():
    with pytest.raises(ValueError, match="plan_markdown"):
        validate({"status": "ready", "tasks": [task("a")], "red_team": {"assignee": "10043", "reason": "r"}})


def test_the_prompts_ask_for_full_granularity_and_offer_appending():
    assert "`append: true`" in planner.ROOT_CONTRACT
    assert "coverage table" in planner.ROOT_CONTRACT
    assert "never shrink" in planner.ROOT_CONTRACT
    assert "`append: true`" in planner.PLAN_WAITS
    assert "only paces dispatch" in RESEARCH_LO_ORCHESTRATION
    assert "budget limits" not in RESEARCH_LO_ORCHESTRATION
    nudge = planner.output_limit_nudge("misaka_research_assign")
    assert "`append: true`" in nudge and "do not redo it" in nudge and "compact" not in nudge
    assert "append" not in planner.output_limit_nudge("misaka_research_investigate")
