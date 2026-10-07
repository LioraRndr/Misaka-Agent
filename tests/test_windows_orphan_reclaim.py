"""On Windows a Sister root's card is reclaimed once its process is gone (issue #10 plan, O1).

The root records a process-group identity on every platform, and terminate_orphaned_group refused
outright off POSIX: the card's lease was never reclaimed, and the panel's takeover kept saying its
previous process was still running."""
import subprocess
import sys

from misaka.core.platform import processes


def test_a_gone_or_reused_pid_is_absent_and_a_live_one_is_ended():
    reclaim = processes._terminate_recorded_tree        # what terminate_orphaned_group runs off POSIX
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        recorded = processes.identity(child.pid)
        assert reclaim(child.pid, "someone-else@0") is True, "a reused PID is not ours"
        assert child.poll() is None
        assert reclaim(child.pid, recorded) is True
        assert child.wait(5) is not None
        assert reclaim(child.pid, recorded) is True, "gone is absent"
    finally:
        if child.poll() is None:
            child.kill()
