"""The guard the offline tests put on the socket layer."""
import socket
import sys


def refuse_network(monkeypatch, message, attempts=None):
    """Fail on every outgoing connection, recording its arguments in ``attempts`` when given.

    Windows builds ``socket.socketpair`` from a loopback connect, and every asyncio event loop
    makes one for its self-pipe: that connection never leaves the process and passes."""
    real_connect = socket.socket.connect

    def no_network(*args, **_kwargs):
        if sys._getframe(1).f_code is socket.socketpair.__code__:
            return real_connect(*args)
        if attempts is not None:
            attempts.append(args)
        raise AssertionError(message)

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
