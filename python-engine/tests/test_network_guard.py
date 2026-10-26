"""[O26d, independent review R5] The suite cannot reach the network: names, numeric IPv4/IPv6, pre-resolved
clients, asyncio and Python child processes are refused before a packet leaves; local servers still work.
The refused addresses are documentation ranges (203.0.113.0/24, 2001:db8::/32) and a reserved name."""
import asyncio
import os
import socket
import subprocess
import sys

import httpx
import pytest

from tests.conftest import netguard

REFUSED = "refused by tests/netguard"


def test_the_guard_is_in_this_process():
    assert getattr(socket, "_sentinel_netguard", False) is True
    assert os.environ["PYTHONPATH"].split(os.pathsep)[0].endswith("netguard")


def test_a_name_lookup_of_an_outside_host_is_refused():
    with pytest.raises(netguard.NetworkRefused, match="lookup"):
        socket.getaddrinfo("sentinel-guard-check.example", 443)
    assert socket.getaddrinfo("localhost", 80)                         # local names still resolve


@pytest.mark.parametrize("family,address", [
    (socket.AF_INET, ("203.0.113.1", 443)),
    (socket.AF_INET6, ("2001:db8::1", 443, 0, 0)),
    (socket.AF_INET, ("sentinel-guard-check.example", 443)),          # a name given to connect skips getaddrinfo
])
def test_a_direct_connection_to_an_outside_address_is_refused(family, address):
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        with pytest.raises(netguard.NetworkRefused, match="connect"):
            sock.connect(address)
        with pytest.raises(netguard.NetworkRefused, match="connect_ex"):
            sock.connect_ex(address)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        with pytest.raises(netguard.NetworkRefused, match="sendto"):
            udp.sendto(b"x", ("203.0.113.1", 53))


def test_a_client_given_a_numeric_address_is_refused():
    with pytest.raises((netguard.NetworkRefused, httpx.ConnectError)) as caught:
        httpx.get("http://203.0.113.1:9/", timeout=1)
    assert REFUSED in str(caught.value) or REFUSED in str(caught.value.__cause__ or caught.value.__context__)


@pytest.mark.asyncio
async def test_asyncio_connections_are_refused_too():
    with pytest.raises(netguard.NetworkRefused):
        await asyncio.open_connection("203.0.113.1", 443)
    with pytest.raises(OSError):
        await asyncio.open_connection("sentinel-guard-check.example", 443)


@pytest.mark.asyncio
async def test_a_local_server_still_works():
    async def echo(reader, writer):
        writer.write(await reader.read(5))
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(echo, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(b"hello")
    await writer.drain()
    assert await reader.read(5) == b"hello"
    writer.close()
    server.close()
    await server.wait_closed()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        with socket.create_connection(listener.getsockname(), timeout=2):
            pass


def test_a_python_child_process_has_the_guard():
    child = subprocess.run(
        [sys.executable, "-c", "import socket; print(getattr(socket, '_sentinel_netguard', False)); "
                               "socket.socket().connect(('203.0.113.1', 443))"],
        capture_output=True, text=True, timeout=60)
    assert child.stdout.strip() == "True"
    assert child.returncode != 0 and REFUSED in child.stderr


def test_the_explicit_opt_in_turns_it_off_for_an_integration_run():
    env = dict(os.environ, **{netguard.OPT_IN: "1"})
    child = subprocess.run([sys.executable, "-c", "import socket; print(getattr(socket, '_sentinel_netguard', False))"],
                           capture_output=True, text=True, timeout=60, env=env)
    assert child.stdout.strip() == "False"


def test_every_test_gets_fake_tokens():
    from config import settings
    assert settings.TELEGRAM_BOT_TOKEN.startswith("test-") and settings.PARTNER_TELEGRAM_BOT_TOKEN.startswith("test-")
