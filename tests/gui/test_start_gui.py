"""Launcher workspace selection stays independent of any one machine."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "scripts" / "start-gui.py"
SPEC = importlib.util.spec_from_file_location("start_gui_under_test", SOURCE)
start_gui = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(start_gui)


class WorkspaceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.saved_runtime = start_gui.RUNTIME
        self.saved_remembered = start_gui.REMEMBERED
        self.saved_pick = start_gui.pick_folder
        start_gui.RUNTIME = self.root / "runtime"
        start_gui.REMEMBERED = start_gui.RUNTIME / "workspace.txt"
        start_gui.pick_folder = lambda: (_ for _ in ()).throw(AssertionError("不应弹出文件夹选择"))
        self.addCleanup(self.restore)

    def restore(self):
        start_gui.RUNTIME = self.saved_runtime
        start_gui.REMEMBERED = self.saved_remembered
        start_gui.pick_folder = self.saved_pick

    def test_explicit_folder_is_remembered(self):
        project = self.root / "project"
        project.mkdir()
        resolved = start_gui.resolve_workspace(str(project))
        self.assertEqual(resolved, project.resolve())
        self.assertEqual(start_gui.remembered_workspace().resolve(), project.resolve())

    def test_next_launch_reuses_the_remembered_folder(self):
        project = self.root / "project"
        project.mkdir()
        start_gui.remember_workspace(project)
        self.assertEqual(start_gui.resolve_workspace(None), project.resolve())

    def test_missing_folder_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "文件夹"):
            start_gui.resolve_workspace(str(self.root / "missing"))

    def test_without_a_saved_folder_it_does_not_invent_one(self):
        start_gui.pick_folder = lambda: None
        with self.assertRaisesRegex(RuntimeError, "gui.cmd --workspace"):
            start_gui.resolve_workspace(None)


if __name__ == "__main__":
    unittest.main()
