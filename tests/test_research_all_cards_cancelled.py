"""Every card of a round cancelled while they ran, then the node plans again: the round is
withdrawn and the node concludes; it was closed as a branch point, with no conclusion (0.18.10 sweep)."""
import asyncio

from test_research_plan_change import change, executing, task  # noqa: F401

from misaka.core.research import planner, runs, workflow


def test_a_round_whose_cards_were_all_cancelled_is_concluded_not_closed(executing, monkeypatch):  # noqa: F811
    con, run, root, tool, ctx = executing
    cards = workflow._round_cards(con, run, root, 1)
    con.execute("UPDATE tasks SET status='ready' WHERE id=?", (cards["a"]["id"],))
    change(tool, ctx, cancel=[{"card": "a", "reason": "x"}, {"card": "b", "reason": "x"}, {"card": "c", "reason": "x"}])
    asyncio.run(workflow._apply_plan_changes(con, run, root, 1, [0], None, (run, root)))
    con.execute("UPDATE research_branches SET status='failed' WHERE id=?", (root["id"],))
    runs.resume(con, run["id"], driver_lock="driver")
    monkeypatch.setattr(planner, "plan_needs_user", lambda *a, **k: False)
    monkeypatch.setattr(planner, "publish_project_brief", lambda *a, **k: None)
    monkeypatch.setattr(workflow, "_views", lambda *a, **k: asyncio.sleep(0))
    async def drive(*a, **k):
        return "stopped"
    monkeypatch.setattr(workflow, "_drive_tasks", drive)
    reached = []

    def synthesize(*a, **k):
        reached.append(runs.node(con, root["id"])["status"])
        raise RuntimeError("stop here: the node went on to conclude")

    monkeypatch.setattr(planner, "synthesize", synthesize)
    try:
        asyncio.run(workflow._expand(con, {}, None, None, runs.get(con, run["id"]), runs.node(con, root["id"]),
                                     context=None, tool_call_id="t", poll_seconds=0, progress=None))
    except RuntimeError:
        pass
    assert reached == ["synthesizing"]
