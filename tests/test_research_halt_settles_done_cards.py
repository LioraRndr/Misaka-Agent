"""Every halt of a research run settles the cards the Sisters finished before the partial
report is written. The cancel and interrupt paths used to skip it: a driver crash on
2026-09-23 left 39 done cards unregistered, un-ingested and unbundled for five hours, and the
partial report knew nothing of them. A settle failure must not cost the report itself."""
import asyncio

import pytest
from test_research_root_lifecycle import (
    root_run,  # noqa: F401 - the fixture is used by name
)

from misaka.core.research import runs, workflow


@pytest.mark.parametrize("outcome", ["halt", "interrupt", "cancel"])
async def test_every_halt_path_settles_once_before_the_partial_report(root_run, monkeypatch, outcome):  # noqa: F811
    con, run, _root, _owner, _events = root_run
    settled = []
    monkeypatch.setattr(workflow, "settle_done_tasks", lambda db, *, run_id: settled.append(run_id))

    async def expand(*args, **kwargs):
        if outcome == "cancel":
            raise asyncio.CancelledError
        if outcome == "interrupt":
            raise InterruptedError("The user requested a stop.")
        return "stopped"

    monkeypatch.setattr(workflow, "_expand", expand)
    if outcome == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await workflow.run(con, {}, object(), run_id=run["id"])
    else:
        assert (await workflow.run(con, {}, object(), run_id=run["id"]))["reason"] == "stopped"
    assert settled == [run["id"]]
    assert runs.get(con, run["id"])["status"] == "stopped"


async def test_a_settle_failure_does_not_cost_the_partial_report(root_run, monkeypatch, caplog):  # noqa: F811
    con, run, _root, _owner, _events = root_run

    def failing(db, *, run_id):
        raise ValueError("Accepted artifact changed before Research registration: x.md")

    monkeypatch.setattr(workflow, "settle_done_tasks", failing)

    async def expand(*args, **kwargs):
        raise InterruptedError("The user requested a stop.")

    monkeypatch.setattr(workflow, "_expand", expand)
    result = await workflow.run(con, {}, object(), run_id=run["id"])
    assert result["reason"] == "stopped" and result["final"]["artifact"]
    assert runs.get(con, run["id"])["status"] == "stopped"
    assert "settling finished cards" in caplog.text
