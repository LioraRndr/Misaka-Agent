"""An exclusive lock on an open lock file, released when the file is closed.

POSIX: ``flock``. Windows: a one-byte ``msvcrt.locking`` range at offset 0, Hermes's pattern
(``hermes_cli/kanban_db_connect.py`` ``_try_lock_nb``). ``msvcrt``'s blocking mode gives up
after ten one-second tries, while a holder here can keep the lock for a whole turn, so Windows
waits by polling the non-blocking attempt instead.
"""
from __future__ import annotations

import os
import time

POLL_SECONDS = 0.05


def lock_fd(fd: int, *, blocking: bool = True) -> bool:
    """Take the lock on ``fd``; False only when ``blocking`` is off and another holder has it."""
    if os.name == "nt":
        import msvcrt

        while True:
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                if not blocking:
                    return False
                time.sleep(POLL_SECONDS)
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
    except BlockingIOError:
        return False
    return True
