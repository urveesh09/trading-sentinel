"""[O26d 2026-10-26] No real network from the test suite.

The suite runs on the developer's machine, whose .env holds the real bot tokens. On Oct 26 a test that calls
every scheduled job polled the real partner bot during market hours (Production's own poll got Telegram's 409
three times, and backed off 10 minutes each time). O26c refused name lookups only; a connection to a numeric
address went straight past it (independent review R5).

Refused here, before any packet leaves:
  * a name lookup of a non-local host (``socket.getaddrinfo``);
  * ``connect`` / ``connect_ex`` / ``sendto`` of a socket to a non-local address, numeric or named (a name given to
    ``connect`` is looked up in C, past ``getaddrinfo``);
  * asyncio's ``sock_connect`` (the Windows proactor loop connects with ConnectEx, never ``socket.connect``).
Local is: loopback and unspecified addresses, ``localhost``, ``testserver`` and the reserved ``.test``,
``.invalid`` and ``.localhost`` names. A Unix socket is not an IP address and is allowed.

Scope: ``tests/conftest.py`` installs this in the test process and puts this folder first on ``PYTHONPATH``, so a
Python child process that inherits the environment installs it too, as its ``sitecustomize``. A child given its
own ``PYTHONPATH``, and any non-Python program, is not covered. ``SENTINEL_TEST_NETWORK=1`` turns the guard off:
the explicit opt-in for an integration run that is meant to reach a real service.
"""
import ipaddress
import os
import socket

LOCAL_NAMES = frozenset({"", "localhost", "testserver"})
LOCAL_SUFFIXES = (".test", ".invalid", ".localhost")
OPT_IN = "SENTINEL_TEST_NETWORK"


class NetworkRefused(OSError):
    """A test tried to reach a non-local host."""


def is_local(host) -> bool:
    name = host.decode() if isinstance(host, bytes) else str(host if host is not None else "")
    if name in LOCAL_NAMES or name.endswith(LOCAL_SUFFIXES):
        return True
    try:
        address = ipaddress.ip_address(name.split("%", 1)[0])
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified


def check(address, what: str) -> None:
    """Refuse ``address`` (a socket address) unless it is local; a non-IP address (a Unix path) passes."""
    if isinstance(address, tuple) and address and not is_local(address[0]):
        raise NetworkRefused(f"tests may not reach the network ({what} to {address[0]!r} refused by tests/netguard)")


def install() -> bool:
    """Install the guard once per process; False when it is already in or opted out."""
    if os.environ.get(OPT_IN) == "1" or getattr(socket, "_sentinel_netguard", False):
        return False
    real_getaddrinfo = socket.getaddrinfo

    def getaddrinfo(host, *args, **kwargs):
        if not is_local(host):
            raise NetworkRefused(f"tests may not reach the network (lookup of {host!r} refused by tests/netguard)")
        return real_getaddrinfo(host, *args, **kwargs)

    socket.getaddrinfo = getaddrinfo
    for method in ("connect", "connect_ex"):
        real = getattr(socket.socket, method)

        def guarded(self, address, _real=real, _what=method):
            check(address, _what)
            return _real(self, address)

        setattr(socket.socket, method, guarded)
    real_sendto = socket.socket.sendto

    def sendto(self, data, *args):
        check(args[-1] if args else None, "sendto")
        return real_sendto(self, data, *args)

    socket.socket.sendto = sendto
    from asyncio import proactor_events, selector_events
    for loop_class in (selector_events.BaseSelectorEventLoop, proactor_events.BaseProactorEventLoop):
        real_sock_connect = loop_class.sock_connect

        async def sock_connect(self, sock, address, _real=real_sock_connect):
            check(address, "sock_connect")
            return await _real(self, sock, address)

        loop_class.sock_connect = sock_connect
    socket._sentinel_netguard = True
    return True


install()
