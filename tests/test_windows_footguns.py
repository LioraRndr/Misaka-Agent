"""Hermes's Windows footgun checker (scripts/check-windows-footguns.py) passes over the tree.

It runs on every platform: a POSIX-only call, a text-mode open without an encoding or an
unguarded signal handler breaks the Windows build whether or not anyone runs it there."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_tree_has_no_windows_footguns():
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "check-windows-footguns.py"), "--all"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=300, check=False)
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-2000:]
