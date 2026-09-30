"""The local socket the panel daemon and session control listen on, on this platform: a unix
socket on POSIX, an owner-only named pipe bridged to a socketpair on Windows (herdr ipc.rs)."""
import asyncio
import os
import sys
import tempfile

import pytest

from misaka.utils import local_socket


@pytest.fixture
def sock_path():
    # A short directory: a unix socket path is capped at 104 bytes on macOS.
    directory = tempfile.mkdtemp(prefix="ls-", dir="/tmp" if os.path.isdir("/tmp") else None)
    yield os.path.join(directory, "t.sock")
    for name in os.listdir(directory):
        os.unlink(os.path.join(directory, name))
    os.rmdir(directory)


async def _echo(reader, writer):
    while line := await reader.readline():
        writer.write(b"echo " + line)
        await writer.drain()
    writer.close()


async def test_sync_and_async_clients_talk_to_one_server(sock_path):
    server = await local_socket.start_server(_echo, sock_path, limit=1 << 20)
    try:
        def exchange():
            with local_socket.connect(sock_path, timeout=5) as sock:
                sock.sendall(b"one\n" + b"x" * 200_000 + b"\n")
                received = b""
                while received.count(b"\n") < 2:
                    received += sock.recv(65536)
                return received
        received = await asyncio.to_thread(exchange)
        assert received == b"echo one\necho " + b"x" * 200_000 + b"\n"

        reader, writer = await local_socket.open_connection(sock_path, limit=1 << 20)
        writer.write(b"two\n")
        await writer.drain()
        assert await reader.readline() == b"echo two\n"
        writer.close()
        await writer.wait_closed()
        assert local_socket.identity(sock_path) == local_socket.identity(sock_path)
    finally:
        server.close()
        await server.wait_closed()


async def test_a_closed_server_leaves_a_stale_path_and_a_missing_one_is_not_found(sock_path):
    server = await local_socket.start_server(_echo, sock_path, limit=1 << 20)
    server.close()
    await server.wait_closed()
    if sys.platform == "win32":
        await asyncio.sleep(0.1)          # the accept thread lets go of the last instance
    with pytest.raises((ConnectionRefusedError, FileNotFoundError)):
        local_socket.connect(sock_path, timeout=1).close()
    if os.path.exists(sock_path):         # asyncio's unix server removes its own file from 3.13 on
        os.unlink(sock_path)
    with pytest.raises(FileNotFoundError):
        local_socket.connect(sock_path, timeout=1).close()


async def test_a_client_that_hangs_up_ends_the_servers_stream(sock_path):
    ended = asyncio.Event()

    async def wait_for_eof(reader, writer):
        assert await reader.read() == b"bye"
        ended.set()
        writer.close()

    server = await local_socket.start_server(wait_for_eof, sock_path, limit=1 << 20)
    try:
        sock = local_socket.connect(sock_path, timeout=5)
        sock.sendall(b"bye")
        sock.close()
        await asyncio.wait_for(ended.wait(), 5)
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.skipif(sys.platform != "win32", reason="POSIX binds over a path the caller unlinked first")
async def test_a_second_server_at_the_same_path_is_refused(sock_path):
    server = await local_socket.start_server(_echo, sock_path, limit=1 << 20)
    try:
        with pytest.raises(OSError, match="already listening"):
            await local_socket.start_server(_echo, sock_path, limit=1 << 20)
    finally:
        server.close()
        await server.wait_closed()
