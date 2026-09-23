"""``misaka_research_view(view="workspace")`` renders the whole project index; on a mature
project that is megabytes (2026-09-24: 1.85 MB, 25k lines) and one call put a Sister at
1.19M tokens, past every window in play. The view is cut at a fixed size like find/grep, and the
cut tells the model how to narrow instead of re-reading; a small index passes untouched."""
from contextlib import closing
from types import SimpleNamespace

import pytest

from misaka import workspace as workspace_index
from misaka.core.platform import tasks
from misaka.core.research import runs, tools


@pytest.fixture
def view(tmp_path, monkeypatch):
    db = tmp_path / "board.db"
    with closing(tasks.connect(str(db))) as con:
        run = runs.create(con, workspace=str(tmp_path), question="Fixture question")
    defs = []
    tools.register(SimpleNamespace(registerTool=defs.append))
    monkeypatch.setattr(tools, "CFG", {"db": str(db)})
    monkeypatch.setattr(workspace_index, "outline", lambda *a, **k: {"fixture": True})
    execute = defs[0].execute

    async def call(**params):
        result = await execute("call", params, None, None, SimpleNamespace(cwd=str(tmp_path)))
        return result["content"][0]["text"], result["details"]

    return SimpleNamespace(call=call, run=run)


async def test_a_huge_index_is_cut_at_the_cap_with_a_narrowing_note(view, monkeypatch):
    monkeypatch.setattr(workspace_index, "render",
                        lambda tree: "\n".join(f"line {i} " + "x" * 80 for i in range(30000)))
    text, details = await view.call(view="workspace", run_id=view.run["id"])
    assert details["truncated"] is True and details["total_lines"] == 30000
    assert len(text.encode("utf-8")) < tools.WORKSPACE_VIEW_MAX_BYTES + 2048
    assert "line 0 " in text and "line 29999 " not in text
    assert "limit reached" in text and "doc_find" in text and "find / grep" in text


async def test_a_small_index_passes_through_untouched(view, monkeypatch):
    monkeypatch.setattr(workspace_index, "render", lambda tree: "PROJECT.md\n  cards/t_1.md\n")
    text, details = await view.call(view="workspace", run_id=view.run["id"])
    assert details == {"truncated": False, "total_lines": 2}
    assert "PROJECT.md\n  cards/t_1.md" in text and "limit reached" not in text
