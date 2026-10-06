"""Settings worker against a throwaway MISAKA_HOME. Never touches the real home."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from misaka.ui.gui.services import Settings
from misaka.ui.gui.settings_worker import MARK


class SettingsWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.home = root / "home"
        self.workspace = root / "workspace"
        self.home.mkdir()
        self.workspace.mkdir()
        real = Path.home() / ".misaka"
        self.real_settings = real / "settings.json"
        self.real_sisters = real / "profiles" / "sisters"
        self.settings_stamp = self._stamp(self.real_settings)
        self.sister_names = self._names(self.real_sisters)

    def _stamp(self, path: Path):
        try:
            return path.stat().st_mtime_ns
        except OSError:
            return None

    def _names(self, path: Path):
        if not path.is_dir():
            return None
        return sorted(p.name for p in path.iterdir())

    def tearDown(self):
        self.assertEqual(self._stamp(self.real_settings), self.settings_stamp)
        self.assertEqual(self._names(self.real_sisters), self.sister_names)

    def call(self, op, params=None):
        env = {**os.environ, "MISAKA_HOME": str(self.home), "PYTHONUTF8": "1",
               "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1", "NO_COLOR": "1", "TERM": "dumb"}
        request = json.dumps({"op": op, "params": params or {}, "workspace": str(self.workspace)}, ensure_ascii=False)
        done = subprocess.run(
            [sys.executable, "-u", "-X", "utf8", "-m", "misaka.ui.gui.settings_worker"],
            input=request + "\n", capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=self.workspace, env=env, timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for line in reversed(done.stdout.splitlines()):
            if line.startswith(MARK):
                return json.loads(line[len(MARK):])
        tail = "\n".join((done.stderr or "").splitlines()[-8:])
        self.fail(f"worker 没有返回标记行（exit {done.returncode}）：{tail}")

    def test_overview_and_models_read_the_throwaway_home(self):
        overview = self.call("overview")
        self.assertTrue(overview["ok"], overview)
        data = overview["data"]
        self.assertIn("version", data)
        self.assertTrue(data["python_ok"])
        self.assertIsInstance(data["tools"], list)
        self.assertTrue(data["plan_approval"])
        self.assertTrue(str(data["paths"]["roles"]).startswith(str(self.home)))
        models = self.call("models_overview")
        self.assertTrue(models["ok"], models)
        self.assertGreater(len(models["data"]["providers"]), 0)
        self.assertEqual(models["data"]["targets"][0]["label"], "全局默认")

    def test_create_sister_and_plan_approval_roundtrip(self):
        empty = self.call("sisters")
        self.assertTrue(empty["ok"], empty)
        self.assertEqual(empty["data"]["sisters"], [])
        created = self.call("create_sister", {"id": "10032", "specialty": "查找证据"})
        self.assertTrue(created["ok"], created)
        self.assertIn("10032", created["data"]["message"])
        listed = self.call("sisters")
        self.assertEqual([item["id"] for item in listed["data"]["sisters"]], ["10032"])
        self.assertIn("查找证据", listed["data"]["sisters"][0]["description"])
        turned_off = self.call("set_research", {"plan_approval": False})
        self.assertTrue(turned_off["ok"], turned_off)
        self.assertFalse(self.call("overview")["data"]["plan_approval"])
        self.call("set_research", {"plan_approval": True})
        self.assertTrue(self.call("overview")["data"]["plan_approval"])
        saved = json.loads((self.home / "settings.json").read_text(encoding="utf-8"))
        self.assertTrue(saved["research"]["plan_approval"])

    def test_unknown_op_and_service_call(self):
        failed = self.call("not_an_op")
        self.assertFalse(failed["ok"])
        self.assertIn("未知设置操作", failed["error"])
        with mock.patch.dict(os.environ, {"MISAKA_HOME": str(self.home), "PYTHONDONTWRITEBYTECODE": "1"}):
            data = Settings().call("sisters", {}, str(self.workspace))
            with self.assertRaisesRegex(ValueError, "未知设置操作"):
                Settings().call("not_an_op", {}, str(self.workspace))
        self.assertEqual(data["sisters"], [])

    def test_web_overview_is_readable(self):
        web = self.call("web_overview")
        self.assertTrue(web["ok"], web)
        self.assertIn("search", web["data"]["resolved"])
        self.assertIn("extract", web["data"]["resolved"])
        self.assertIsInstance(web["data"]["providers"], list)


if __name__ == "__main__":
    unittest.main()
