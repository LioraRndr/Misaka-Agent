"""Fixes from the code audit attached to GitHub issue #10 (2026-10-07)."""
import asyncio

import pytest

from misaka.core.skills.wiring.skills import SkillsPart


def _write(tmp_path, kind, path):
    workspace = tmp_path / "project"
    workspace.mkdir(exist_ok=True)
    part = SkillsPart(None, str(tmp_path / "profile"), cwd=str(workspace), kind=kind)
    part._live_roots = set()
    part._refresh_roots = lambda: None
    return asyncio.run(part.tool_call({"toolName": "write", "input": {"path": path, "content": "x"}}, None))


# -- H4: a card rewriting the instructions every later session loads --------------------------------------

@pytest.mark.parametrize("path", ["PROJECT.md", "AGENTS.md", "../CLAUDE.md"])
@pytest.mark.parametrize("kind", ["card", "beast", "child"])
def test_a_sister_or_sub_agent_does_not_write_the_projects_instructions(tmp_path, kind, path):
    decision = _write(tmp_path, kind, path)
    assert decision and decision["block"] and "Tell Last Order" in decision["reason"]


@pytest.mark.parametrize("kind, path", [("foreground", "PROJECT.md"), ("card", "nodes/b_1/notes.md"),
                                        ("card", "nodes/b_1/AGENTS.md")])
def test_last_order_and_ordinary_files_are_untouched(tmp_path, kind, path):
    assert _write(tmp_path, kind, path) is None


# -- M1: MISAKA's own credentials through the file tools ----------------------------------------------------

def test_the_file_tools_do_not_read_misakas_credentials(tmp_path, monkeypatch):
    from misaka.config import home
    from misaka.core.tools.grep import create_grep_tool
    from misaka.core.web.evidence import CREDENTIALS_REFUSED, check_material_read
    monkeypatch.setenv(home.ENV_HOME, str(tmp_path / "home"))
    auth = home.path("auth")
    auth.parent.mkdir(parents=True)
    auth.write_text('{"deepseek": {"key": "sk-secret-value"}}', encoding="utf-8")
    (tmp_path / "home" / ".env").write_text("EXA_API_KEY=exa-secret-value\n", encoding="utf-8")
    (tmp_path / "home" / "notes.md").write_text("secret-value is a phrase here\n", encoding="utf-8")
    for path in (auth, tmp_path / "home" / ".env", auth.parent):
        with pytest.raises(ValueError, match="not read through file tools"):
            check_material_read(str(path))
    check_material_read(str(tmp_path / "home" / "notes.md"))
    grep = create_grep_tool(str(tmp_path))
    found = asyncio.run(grep.execute("g", {"pattern": "secret-value", "path": str(tmp_path / "home")}, None, None))
    text = found.content[0].text
    assert "notes.md" in text and "sk-secret" not in text and "exa-secret" not in text
    assert CREDENTIALS_REFUSED.startswith("MISAKA's credentials")
