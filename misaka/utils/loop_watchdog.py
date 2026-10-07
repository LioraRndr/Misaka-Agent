"""A blocked event loop becomes a stack trace -- and, in a process nobody is watching, an exit.

Every MISAKA process does its work on one asyncio loop. Synchronous code that never returns on it
(GitHub issue #10: the live-skill guard looping forever before a bash call) freezes everything
that process does -- heartbeats, leases, the TUI -- and nothing inside the process can notice,
because noticing needs the loop. ``faulthandler``'s watchdog is a C thread that needs neither the
loop nor the GIL: the running loop re-arms it every ``STALL_SECONDS / 4``, and if no loop re-arms
it, it writes every thread's stack to ``logs/stalls/<label>-<pid>.log`` -- and, in a process that
exits on a stall (an unattended card, node or sub-agent), ends it with status 1, which every
supervisor already treats as a crashed attempt and retries.

Nothing happens until a process entry calls :func:`configure`; library code and tests are
untouched. Whichever loop is running re-arms the one timer, so ``run_coro``'s nested loop (whose
caller's loop is waiting on it) keeps the watch going. Known limit: with two loops alive in two
threads, the live one keeps re-arming while the other is frozen.
"""
from __future__ import annotations

import asyncio
import faulthandler
import os
import re
import sys
import sysconfig
import time

STALL_SECONDS = 300.0
_settings: dict | None = None
_file = None
_depth = 0


def _seconds() -> float:
    try:
        return float(os.environ.get("MISAKA_LOOP_STALL_SECONDS") or STALL_SECONDS)   # tests and diagnosis only
    except ValueError:
        return STALL_SECONDS


def log_path(label: str, pid: int) -> str:
    from misaka.config import home
    return os.path.join(str(home.path("stall_logs")), f"{label}-{int(pid)}.log")


def configure(label: str, *, exit_on_stall: bool) -> None:
    """Watch this process's loops from now on (once per process, at its entry)."""
    global _settings
    _settings = {"label": re.sub(r"[^A-Za-z0-9_.-]", "_", label) or "process", "exit": exit_on_stall}


def _open():
    global _file
    if _file is None:
        path = log_path(_settings["label"], os.getpid())
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _file = open(path, "a", encoding="utf-8")  # noqa: SIM115 - faulthandler needs it open for the process's life
        _file.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} {_settings['label']} pid {os.getpid()} "
                    f"stall {_seconds():g} s exit {_settings['exit']} argv {sys.argv!r}\n")
        _file.flush()
    return _file


async def _rearm(seconds: float) -> None:
    while True:
        faulthandler.dump_traceback_later(seconds, repeat=not _settings["exit"], file=_open(), exit=_settings["exit"])
        await asyncio.sleep(seconds / 4)


async def watched(coro):
    """``await coro`` with this loop re-arming the watchdog; a pass-through when not configured."""
    global _depth
    if _settings is None:
        return await coro
    rearm = asyncio.ensure_future(_rearm(_seconds()))
    _depth += 1
    try:
        return await coro
    finally:
        _depth -= 1
        rearm.cancel()
        if _depth == 0:
            faulthandler.cancel_dump_traceback_later()


_FRAME = re.compile(r'File "([^"]+)", line (\d+) in (\S+)')


def report(label: str, pid: int | None = None, *, since: float | None = None) -> str | None:
    """One line for a failure reason: where the loop of ``label``'s process was stuck, and the log
    with the whole stack; None when it left no stall. ``pid`` names the process; without it (a
    pane's process may be a launcher) the newest log of ``label`` written after ``since`` is read."""
    import glob

    label = re.sub(r"[^A-Za-z0-9_.-]", "_", label)
    if pid:
        path = log_path(label, pid)
    else:
        logs = [p for p in glob.glob(log_path(label, 0)[:-len("0.log")] + "*.log")
                if since is None or os.path.getmtime(p) >= since]
        if not logs:
            return None
        path = max(logs, key=os.path.getmtime)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return None
    if "Timeout (" not in text:
        return None
    last = text[text.rindex("Timeout ("):]
    # The loop's thread is the one inside asyncio's run loop; its first frame is where it is stuck.
    for block in re.split(r"\n(?=(?:Current thread|Thread) 0x)", last):
        frames = _FRAME.findall(block)
        if frames and any("asyncio" in file and func in ("run_forever", "_run_once") for file, _line, func in frames):
            # The innermost frame is often the standard library (re, shlex); name the caller too.
            stdlib = sysconfig.get_paths()["stdlib"]
            shown = [frames[0]]
            own = next((frame for frame in frames if not os.path.realpath(frame[0]).startswith(os.path.realpath(stdlib))
                        and "asyncio" not in frame[0]), None)
            if own is not None and own != frames[0]:
                shown.append(own)
            where = " <- ".join(f"{os.path.basename(file)}:{line} in {func}" for file, line, func in shown)
            return f"the event loop was blocked for over {_seconds():g} s at {where}; full stack in {path}"
    return f"the event loop was blocked for over {_seconds():g} s; stack in {path}"
