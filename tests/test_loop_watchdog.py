"""A blocked event loop leaves a stack trace, and an unattended process exits (issue #10).

Each case runs in its own process: the watchdog is per process, and an exit is its whole point."""
import os
import subprocess
import sys
import textwrap

import pytest

from misaka.utils import loop_watchdog

SCRIPT = textwrap.dedent('''
    import asyncio, re, sys, time
    from misaka.utils import loop_watchdog

    def spin_forever():
        while True:
            pass

    def backtrack_forever():
        re.match(r"(a+)+$", "a" * 40 + "!")

    async def body(kind):
        await asyncio.sleep(0.2)
        if kind == "python":
            spin_forever()
        elif kind == "regex":
            backtrack_forever()
        elif kind == "blocked":
            time.sleep(2.5)
        else:
            await asyncio.sleep(3)

    kind, exit_on_stall, configured = sys.argv[1], sys.argv[2] == "1", sys.argv[3] == "1"
    if configured:
        loop_watchdog.configure("card-t_test", exit_on_stall=exit_on_stall)
    asyncio.run(loop_watchdog.watched(body(kind)))
''')


def _run(tmp_path, kind, *, exit_on_stall=True, configured=True):
    env = {**os.environ, "MISAKA_HOME": str(tmp_path), "MISAKA_LOOP_STALL_SECONDS": "1"}
    done = subprocess.run([sys.executable, "-c", SCRIPT, kind, "1" if exit_on_stall else "0", "1" if configured else "0"],
                          env=env, capture_output=True, text=True, timeout=30, check=False)
    logs = list((tmp_path / "logs" / "stalls").glob("card-t_test-*.log")) if (tmp_path / "logs").exists() else []
    return done.returncode, (logs[0].read_text(encoding="utf-8") if logs else ""), logs


@pytest.mark.parametrize("kind, frame", [("python", "spin_forever"), ("regex", "backtrack_forever")])
def test_an_unattended_process_writes_where_it_is_stuck_and_exits(tmp_path, kind, frame, monkeypatch):
    code, log, logs = _run(tmp_path, kind)
    assert code == 1 and "Timeout (" in log and frame in log
    monkeypatch.setenv("MISAKA_HOME", str(tmp_path))
    pid = int(logs[0].stem.rsplit("-", 1)[1])
    assert f"in {frame}" in loop_watchdog.report("card-t_test", pid)
    assert f"in {frame}" in loop_watchdog.report("card-t_test"), "found without the pid too"


def test_an_attended_process_writes_the_stack_and_goes_on(tmp_path):
    code, log, _logs = _run(tmp_path, "blocked", exit_on_stall=False)
    assert code == 0 and "Timeout (" in log


def test_a_healthy_loop_writes_no_stack(tmp_path):
    code, log, _logs = _run(tmp_path, "healthy")
    assert code == 0 and "Timeout (" not in log


def test_an_unconfigured_process_is_not_watched(tmp_path):
    code, _log, logs = _run(tmp_path, "blocked", configured=False)
    assert code == 0 and logs == []

