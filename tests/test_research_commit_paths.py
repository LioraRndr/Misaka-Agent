"""The node and run commits carry each card's output folder. Until 2026-09-24 the commit
listed the project-flat ``cards/<id>`` attachment folder only, so under the by-node layout
(``nodes/<node>/cards/<id>``) a whole run's Sister work stayed outside git: 531 files after
five hours, none tracked. The folder's derived bundle (``SOURCES.md``, hard-linked
``sources/``) is rebuilt at every settle and documented as never committed, so it is excluded
by pathspec rather than by an ignore file an older project may not have."""
import subprocess
from contextlib import closing
from pathlib import Path

import pytest

from misaka.core.platform import cards, tasks
from misaka.core.research import runs


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def project(tmp_path):
    _git(tmp_path, "init", "-q")
    with closing(tasks.connect(str(tmp_path / "board.db"))) as con:
        run = runs.create(con, workspace=str(tmp_path), question="Fixture question")
        yield con, run


def test_node_commit_carries_card_output_files_but_never_the_bundle(project):
    con, run = project
    workspace = Path(run["workspace"])
    root = runs.nodes(con, run["id"])[0]
    tid = cards.create(con, run["workspace"], "fixture output", "fixture body", "fixture")
    runs.link_task(con, run["id"], tid, kind="research", node=root, local_id="source")
    out = Path(tasks.get(con, tid)["output_dir"])
    assert out.relative_to(workspace).parts[:1] == ("nodes",)
    (out / "notes.md").write_text("finding\n")
    (out / "tools").mkdir()
    (out / "tools" / "fetch.py").write_text("print()\n")
    (out / "SOURCES.md").write_text("derived\n")
    (out / "sources").mkdir()
    (out / "sources" / "a.md").write_text("link\n")
    (out / "tools" / "__pycache__").mkdir()
    (out / "tools" / "__pycache__" / "fetch.cpython-313.pyc").write_bytes(b"\x00")
    (out / "stray.pyc").write_bytes(b"\x00")
    (out / ".DS_Store").write_bytes(b"\x00")
    (out / "tools" / ".DS_Store").write_bytes(b"\x00")

    runs._commit(con, run, "fixture commit")

    tracked = set(_git(workspace, "ls-files").split())
    rel = out.relative_to(workspace).as_posix()
    assert {f"{rel}/notes.md", f"{rel}/tools/fetch.py", f"cards/{tid}.md"} <= tracked
    assert not [path for path in tracked if path.startswith(f"{rel}/sources/") or path.endswith("SOURCES.md")]
    assert not [path for path in tracked if "__pycache__" in path or path.endswith((".pyc", ".DS_Store"))]
    assert _git(workspace, "log", "--format=%s").split("\n")[0] == "fixture commit"


def test_a_deleted_output_file_is_committed_as_a_deletion(project):
    con, run = project
    workspace = Path(run["workspace"])
    root = runs.nodes(con, run["id"])[0]
    tid = cards.create(con, run["workspace"], "fixture output", "fixture body", "fixture")
    runs.link_task(con, run["id"], tid, kind="research", node=root, local_id="source")
    out = Path(tasks.get(con, tid)["output_dir"])
    (out / "draft.md").write_text("first\n")
    runs._commit(con, run, "first")
    (out / "draft.md").unlink()
    runs._commit(con, run, "second")
    assert "draft.md" not in _git(workspace, "ls-files")
    assert _git(workspace, "log", "--format=%s").split() == ["second", "first"]


def test_an_output_folder_outside_the_project_is_ignored(project):
    con, run = project
    root = runs.nodes(con, run["id"])[0]
    row = {"id": "t_x", "output_dir": "/somewhere/else"}
    assert runs._output_pathspec(run["workspace"], type("Row", (), {
        "__getitem__": lambda self, key: row[key], "keys": lambda self: row.keys()})()) == []
    assert root["parent_id"] is None
