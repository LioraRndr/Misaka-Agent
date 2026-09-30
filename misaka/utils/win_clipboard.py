"""Text onto the Windows clipboard, through the Win32 API.

A port of herdr's ``platform/windows.rs`` ``write_clipboard``: the console window opens the
clipboard, and the text goes in as CF_UNICODETEXT in movable global memory. It stands in for
the native clipboard pi's clipboard code reaches first (its addon writes through the same API
on Windows); the ``clip`` command it falls back to reads its input in the OEM code page.
Windows-only, imported only there.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.GetConsoleWindow.restype = wintypes.HWND
_user32.OpenClipboard.argtypes = [wintypes.HWND]
_user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
_user32.SetClipboardData.restype = wintypes.HANDLE
_kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
_kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalLock.restype = ctypes.c_void_p
_kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]


def _failed(what):
    return ctypes.WinError(ctypes.get_last_error(), f"{what} failed")


def copy(text: str) -> None:
    """Replace the clipboard's content with ``text``; OSError when the clipboard refuses."""
    if "\0" in text:
        raise ValueError("clipboard text cannot hold a NUL")
    data = (text + "\0").encode("utf-16-le")
    owner = _kernel32.GetConsoleWindow()
    if not owner or not _user32.OpenClipboard(owner):
        raise _failed("OpenClipboard")
    try:
        if not _user32.EmptyClipboard():
            raise _failed("EmptyClipboard")
        memory = _kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not memory:
            raise _failed("GlobalAlloc")
        locked = _kernel32.GlobalLock(memory)
        if not locked:
            _kernel32.GlobalFree(memory)
            raise _failed("GlobalLock")
        ctypes.memmove(locked, data, len(data))
        _kernel32.GlobalUnlock(memory)
        if not _user32.SetClipboardData(CF_UNICODETEXT, memory):
            _kernel32.GlobalFree(memory)
            raise _failed("SetClipboardData")
    finally:
        _user32.CloseClipboard()
