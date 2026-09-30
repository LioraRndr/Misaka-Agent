"""A pane's pseudo terminal on Windows: ConPTY, driven through ctypes.

A port of the ConPTY backend herdr vendors (``vendor/portable-pty/src/win``: ``psuedocon.rs``,
``conpty.rs``, ``procthreadattr.rs``, ``WinChild``): two anonymous pipes, a pseudo console
created with the same flags, and the program started into it through a STARTUPINFOEX attribute
list with its standard handles explicitly invalid (so a daemon whose own stdio goes to a log
file does not hand that file to the pane). The system ConPTY is used; herdr's optional
app-local ``conpty.dll`` bundle is not shipped.

The input pipe is handed to the caller as a non-blocking file descriptor (``input_fd``), so
the daemon writes a pane's input exactly as it writes a POSIX pty master: a write takes what
fits and a full pipe says so. Output and exit take a thread each, since no event loop can wait
on either: a pseudo console keeps its output pipe open after the program exits, so the waiter
closes the console once the program is gone, and the reader drains what is left and then sees
the end of the pipe, which is where POSIX sees EOF on the pty. Windows-only, imported only there.
"""
from __future__ import annotations

import _winapi
import ctypes
import msvcrt
import os
import shutil
import subprocess
import threading
from ctypes import wintypes

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)

PSUEDOCONSOLE_INHERIT_CURSOR = 0x1          # psuedocon.rs spells it so
PSEUDOCONSOLE_RESIZE_QUIRK = 0x2
PSEUDOCONSOLE_WIN32_INPUT_MODE = 0x4
PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE = 0x00020016
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
CREATE_UNICODE_ENVIRONMENT = 0x00000400
STARTF_USESTDHANDLES = 0x00000100
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
STILL_ACTIVE = 259
READ_SIZE = 65536


class _Coord(ctypes.Structure):
    _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]


class _StartupInfo(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR),
                ("lpTitle", wintypes.LPWSTR), ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD), ("dwXCountChars", wintypes.DWORD),
                ("dwYCountChars", wintypes.DWORD), ("dwFillAttribute", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.c_void_p), ("hStdInput", wintypes.HANDLE),
                ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE)]


class _StartupInfoEx(ctypes.Structure):
    _fields_ = [("StartupInfo", _StartupInfo), ("lpAttributeList", ctypes.c_void_p)]


class _ProcessInformation(ctypes.Structure):
    _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]


_k32.CreatePseudoConsole.argtypes = [_Coord, wintypes.HANDLE, wintypes.HANDLE, wintypes.DWORD,
                                     ctypes.POINTER(wintypes.HANDLE)]
_k32.CreatePseudoConsole.restype = ctypes.c_long
_k32.ResizePseudoConsole.argtypes = [wintypes.HANDLE, _Coord]
_k32.ResizePseudoConsole.restype = ctypes.c_long
_k32.ClosePseudoConsole.argtypes = [wintypes.HANDLE]
_k32.ClosePseudoConsole.restype = None
_k32.InitializeProcThreadAttributeList.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                                   ctypes.POINTER(ctypes.c_size_t)]
_k32.UpdateProcThreadAttribute.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_size_t, ctypes.c_void_p,
                                           ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
_k32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
_k32.DeleteProcThreadAttributeList.restype = None
_k32.CreateProcessW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
                                wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
                                ctypes.POINTER(_StartupInfoEx), ctypes.POINTER(_ProcessInformation)]


def _check(result, what):
    if result != 0:
        raise OSError(f"{what} failed: HRESULT {result & 0xFFFFFFFF:#010x}")


def _environment_block(env):
    """KEY=VALUE, NUL-separated and double-terminated, sorted the way Windows keeps its own
    (cmdbuilder.rs environment_block; keys holding '=' past the first character are skipped)."""
    entries = [f"{key}={value}" for key, value in sorted(env.items(), key=lambda item: item[0].upper())
               if key and "=" not in key[1:] and "\0" not in key + value]
    return ctypes.create_unicode_buffer("\0".join(entries) + "\0\0")


class Process:
    """The program in a pseudo console, answering the part of ``subprocess.Popen`` the daemon
    uses: ``pid``, ``poll``, ``wait``, ``returncode``."""

    def __init__(self, handle, pid):
        self._handle, self.pid, self.returncode = handle, pid, None

    def __del__(self):
        _winapi.CloseHandle(self._handle)

    def poll(self):
        if self.returncode is None and _winapi.WaitForSingleObject(self._handle, 0) == _winapi.WAIT_OBJECT_0:
            self.returncode = _winapi.GetExitCodeProcess(self._handle)
        return self.returncode

    def wait(self, timeout=None):
        milliseconds = _winapi.INFINITE if timeout is None else int(timeout * 1000)
        if _winapi.WaitForSingleObject(self._handle, milliseconds) != _winapi.WAIT_OBJECT_0:
            raise subprocess.TimeoutExpired(self.pid, timeout)
        return self.poll()

    def kill(self):
        """TerminateProcess, as portable-pty's WinChild kill; the rest of the console's programs
        end with the console (``PseudoConsole.hang_up``)."""
        if self.poll() is None:
            _winapi.TerminateProcess(self._handle, 1)


class PseudoConsole:
    """One pane's ConPTY: the program, its console, its input as ``input_fd`` (non-blocking,
    closed by whoever holds it) and the two threads that stand in for a pollable output.
    ``attach`` names the callback that receives output on the event loop (``b""`` once, at the
    end); ``hang_up`` closes the console, which ends every program attached to it the way
    SIGHUP ends a POSIX session."""

    def __init__(self, argv, cwd, env, rows, cols):
        input_read, self._input = _winapi.CreatePipe(None, 0)
        self._output, output_write = _winapi.CreatePipe(None, 0)
        console = wintypes.HANDLE()
        try:
            _check(_k32.CreatePseudoConsole(
                _Coord(cols, rows), input_read, output_write,
                PSUEDOCONSOLE_INHERIT_CURSOR | PSEUDOCONSOLE_RESIZE_QUIRK | PSEUDOCONSOLE_WIN32_INPUT_MODE,
                ctypes.byref(console)), "CreatePseudoConsole")
        except BaseException:
            for handle in (self._input, self._output):
                _winapi.CloseHandle(handle)
            raise
        finally:
            # The console holds its own duplicates of the far ends (psuedocon.rs drops them here).
            _winapi.CloseHandle(input_read)
            _winapi.CloseHandle(output_write)
        self._console = console.value
        self._lock = threading.Lock()
        self._closed = False
        self._loop = self._on_output = None
        try:
            self.proc = self._spawn(argv, cwd, env)
        except BaseException:
            self.hang_up()                       # no thread owns the pipes yet
            _winapi.CloseHandle(self._input)
            _winapi.CloseHandle(self._output)
            raise
        self.proc.console = self
        self.input_fd = msvcrt.open_osfhandle(self._input, os.O_WRONLY)
        os.set_blocking(self.input_fd, False)    # PIPE_NOWAIT: a write takes what fits

    def _spawn(self, argv, cwd, env):
        size = ctypes.c_size_t()
        _k32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
        attributes = ctypes.create_string_buffer(size.value)
        if not _k32.InitializeProcThreadAttributeList(attributes, 1, 0, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not _k32.UpdateProcThreadAttribute(attributes, 0, PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE,
                                                  self._console, ctypes.sizeof(wintypes.HANDLE), None, None):
                raise ctypes.WinError(ctypes.get_last_error())
            startup = _StartupInfoEx()
            startup.StartupInfo.cb = ctypes.sizeof(_StartupInfoEx)
            startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES
            startup.StartupInfo.hStdInput = startup.StartupInfo.hStdOutput = INVALID_HANDLE_VALUE
            startup.StartupInfo.hStdError = INVALID_HANDLE_VALUE
            startup.lpAttributeList = ctypes.cast(attributes, ctypes.c_void_p)
            info = _ProcessInformation()
            # cmdbuilder.rs search_path: the program as PATH and PATHEXT resolve it, so a
            # `.cmd` shim (npm's) starts as well as an `.exe`.
            program = shutil.which(argv[0], path=env.get("PATH")) or argv[0]
            command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
            if not _k32.CreateProcessW(program, command_line, None, None, False,
                                       EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT,
                                       _environment_block(env), os.fspath(cwd), ctypes.byref(startup),
                                       ctypes.byref(info)):
                error = ctypes.get_last_error()
                raise ctypes.WinError(error, f"{ctypes.FormatError(error)}: {argv[0]!r} in {cwd!r}")
        finally:
            _k32.DeleteProcThreadAttributeList(attributes)
        _winapi.CloseHandle(info.hThread)
        return Process(info.hProcess, info.dwProcessId)

    @property
    def pid(self):
        return self.proc.pid

    def attach(self, loop, on_output):
        """Start delivering output to ``on_output`` on ``loop``; call once."""
        self._loop, self._on_output = loop, on_output
        for target, name in ((self._read, "conpty-read"), (self._wait, "conpty-wait")):
            threading.Thread(target=target, name=name, daemon=True).start()

    def detach(self):
        """Stop delivering output; the reader keeps draining it, so the program never blocks
        on a full pipe while it is being asked to leave."""
        self._on_output = None

    def _deliver(self, chunk):
        callback = self._on_output
        if callback is None:
            return
        try:
            self._loop.call_soon_threadsafe(callback, chunk)
        except RuntimeError:                     # the loop is closed: nobody is listening
            self._on_output = None

    def _read(self):
        # The output pipe is closed by the thread that reads it: closing a handle under a
        # blocked synchronous read does not reliably release it.
        while True:
            try:
                chunk, _ = _winapi.ReadFile(self._output, READ_SIZE)
            except OSError:                      # ERROR_BROKEN_PIPE: the console is closed
                break
            if chunk:
                self._deliver(chunk)
        _winapi.CloseHandle(self._output)
        self._deliver(b"")

    def _wait(self):
        _winapi.WaitForSingleObject(self.proc._handle, _winapi.INFINITE)
        self.hang_up()

    def resize(self, rows, cols):
        with self._lock:
            if not self._closed:
                _check(_k32.ResizePseudoConsole(self._console, _Coord(cols, rows)), "ResizePseudoConsole")

    def hang_up(self):
        """Close the console: its programs get CTRL_CLOSE_EVENT and end, and the output pipe
        ends after what is left in it. May block while the console flushes, so the daemon
        calls it off its event loop."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        _k32.ClosePseudoConsole(self._console)

    def close(self):
        """Close the console if it is still open; the reader then releases the output pipe.
        ``input_fd`` is the caller's to close."""
        self.hang_up()
