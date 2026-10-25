"""[O25c 2026-10-25] The Kite tunnel for the Oracle VM: CONNECT to api.kite.trade:443 only, with a password."""
from __future__ import annotations

import asyncio
import base64
import importlib.util
import os
import subprocess
import threading
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("kite_tunnel", Path(__file__).parents[1] / "kite_tunnel.py")
kt = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(kt)

USER, PASSWORD = "kite", "0123456789abcdef0123456789abcdef"
KITE = "api.kite.trade:443"


def _auth(user=USER, password=PASSWORD):
    return "Proxy-Authorization: Basic " + base64.b64encode(f"{user}:{password}".encode()).decode() + "\r\n"


class Upstream:
    """Stands in for Kite: answers 'pong:<what it got>' and counts who reached it."""

    def __init__(self, wait_for_eof=False):
        self.connections, self.wait_for_eof, self.server = 0, wait_for_eof, None

    async def handle(self, reader, writer):
        self.connections += 1
        data = await reader.read() if self.wait_for_eof else await reader.read(100)
        writer.write(b"pong:" + data)
        await writer.drain()
        writer.close()

    async def start(self):
        self.server = await asyncio.start_server(self.handle, "127.0.0.1", 0)
        return self.server.sockets[0].getsockname()[1]


async def _stop(*servers):
    for server in servers:
        server.close()
        try:
            await asyncio.wait_for(server.wait_closed(), 2)
        except asyncio.TimeoutError:
            pass


async def _start(tunnel):
    server = await asyncio.start_server(tunnel.handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


async def _closed_without_answer(reader):
    """The tunnel hung up without a word (Windows reports the unread request as a reset)."""
    try:
        return await asyncio.wait_for(reader.read(), 3) == b""
    except ConnectionResetError:
        return True


async def _ask(port, head):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(head.encode())
    await writer.drain()
    answer = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
    return reader, writer, answer


@pytest.mark.asyncio
async def test_only_connect_to_kite_with_the_password_reaches_kite():
    upstream = Upstream()
    up_port = await upstream.start()
    server, port = await _start(kt.Tunnel(USER, PASSWORD, upstream=("127.0.0.1", up_port), auth_fail_delay=0))
    refused = {
        "GET http://api.kite.trade/ HTTP/1.1\r\nHost: api.kite.trade\r\n" + _auth() + "\r\n": b"405",
        f"CONNECT {KITE} HTTP/1.1\r\n\r\n": b"407",
        f"CONNECT {KITE} HTTP/1.1\r\n" + _auth(password="x" * 32) + "\r\n": b"407",
        "CONNECT example.com:443 HTTP/1.1\r\n\r\n": b"407",            # a stranger learns nothing of the policy
        "CONNECT example.com:443 HTTP/1.1\r\n" + _auth() + "\r\n": b"403",
        "CONNECT api.kite.trade:80 HTTP/1.1\r\n" + _auth() + "\r\n": b"403",
        "CONNECT api.kite.trade.evil.test:443 HTTP/1.1\r\n" + _auth() + "\r\n": b"403",
    }
    for head, code in refused.items():
        _, writer, answer = await _ask(port, head)
        assert answer.split(b" ")[1] == code, head
        writer.close()
    assert upstream.connections == 0                                     # nothing refused ever reached "Kite"
    _, writer, answer = await _ask(port, f"CONNECT {KITE} HTTP/1.1\r\nHost: {KITE}\r\n" + _auth() + "\r\n")
    assert answer.startswith(b"HTTP/1.1 200")
    assert b"Proxy-Authenticate" not in answer
    reader = _
    writer.write(b"ping")
    await writer.drain()
    assert await asyncio.wait_for(reader.read(), 5) == b"pong:ping"
    assert upstream.connections == 1
    writer.close()
    await _stop(server, upstream.server)


@pytest.mark.asyncio
async def test_a_wrong_password_is_told_how_to_authenticate():
    server, port = await _start(kt.Tunnel(USER, PASSWORD, upstream=("127.0.0.1", 9), auth_fail_delay=0))
    _, writer, answer = await _ask(port, f"CONNECT {KITE} HTTP/1.1\r\n\r\n")
    assert b"407 Proxy Authentication Required" in answer and b'Proxy-Authenticate: Basic realm="kite-tunnel"' in answer
    writer.close()
    await _stop(server)


@pytest.mark.asyncio
async def test_a_client_outside_the_allow_list_gets_no_answer():
    class ExternalClient(kt.Tunnel):
        def _allowed(self, client):
            return super()._allowed("198.51.100.7")  # external peer, delivered through the local test socket

    server, port = await _start(ExternalClient(USER, PASSWORD, allow=["10.0.0.0/8"], upstream=("127.0.0.1", 9)))
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write((f"CONNECT {KITE} HTTP/1.1\r\n" + _auth() + "\r\n").encode())
    assert await _closed_without_answer(reader)
    writer.close()
    await _stop(server)
    allowed = kt.Tunnel(USER, PASSWORD, allow=["127.0.0.1/32"])
    assert allowed._allowed("127.0.0.1") and allowed._allowed("::ffff:127.0.0.1") and not allowed._allowed("10.1.1.1")


@pytest.mark.asyncio
async def test_a_half_closed_request_still_gets_its_whole_answer():
    upstream = Upstream(wait_for_eof=True)
    up_port = await upstream.start()
    server, port = await _start(kt.Tunnel(USER, PASSWORD, upstream=("127.0.0.1", up_port)))
    reader, writer, _ = await _ask(port, f"CONNECT {KITE} HTTP/1.1\r\n" + _auth() + "\r\n")
    writer.write(b"request")
    writer.write_eof()
    assert await asyncio.wait_for(reader.read(), 5) == b"pong:request"
    writer.close()
    await _stop(server, upstream.server)


@pytest.mark.asyncio
async def test_silence_closes_the_tunnel_and_a_silent_client_is_dropped():
    async def quiet(reader, writer):
        await reader.read()                      # says nothing until the tunnel hangs up on it
        writer.close()

    quiet_server = await asyncio.start_server(quiet, "127.0.0.1", 0)
    up_port = quiet_server.sockets[0].getsockname()[1]
    server, port = await _start(kt.Tunnel(USER, PASSWORD, upstream=("127.0.0.1", up_port), idle_timeout=0.3,
                                          head_timeout=0.3))
    reader, writer, answer = await _ask(port, f"CONNECT {KITE} HTTP/1.1\r\n" + _auth() + "\r\n")
    assert answer.startswith(b"HTTP/1.1 200")
    assert await asyncio.wait_for(reader.read(), 3) == b""              # closed after 0.3 s of nothing
    writer.close()
    reader, writer = await asyncio.open_connection("127.0.0.1", port)    # connects, never speaks
    assert await _closed_without_answer(reader)
    writer.close()
    await _stop(server, quiet_server)


@pytest.mark.asyncio
async def test_kite_unreachable_is_a_502_and_the_service_keeps_serving():
    probe = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    dead_port = probe.sockets[0].getsockname()[1]
    probe.close()
    await probe.wait_closed()
    tunnel = kt.Tunnel(USER, PASSWORD, upstream=("127.0.0.1", dead_port), upstream_timeout=2)
    server, port = await _start(tunnel)
    for _attempt in range(2):
        _, writer, answer = await _ask(port, f"CONNECT {KITE} HTTP/1.1\r\n" + _auth() + "\r\n")
        assert answer.split(b" ")[1] == b"502"
        writer.close()
    assert tunnel.active == 0
    await _stop(server)


@pytest.mark.parametrize("allow", [(), ("203.0.113.7/32",)])
def test_the_self_test_passes_against_a_real_tunnel_and_fails_on_a_wrong_password(allow):
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    holder = {}

    async def run():
        upstream = Upstream()
        up_port = await upstream.start()
        server, port = await _start(kt.Tunnel(USER, PASSWORD, allow=allow,
                                            upstream=("127.0.0.1", up_port), auth_fail_delay=0))
        holder["port"], holder["server"], holder["upstream"] = port, server, upstream.server
        ready.set()

    thread = threading.Thread(target=lambda: (loop.run_until_complete(run()), loop.run_forever()), daemon=True)
    thread.start()
    assert ready.wait(5)

    async def shutdown():
        await _stop(holder["server"], holder["upstream"])
        # This loop belongs only to this test. Server.close stops accepting,
        # but existing CONNECT handlers must also be joined before it closes.
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    try:
        good = kt.self_test(holder["port"], USER, PASSWORD, through_to_kite=False)
        assert [passed for _, passed, _ in good] == [True, True, True], good
        bad = kt.self_test(holder["port"], USER, "y" * 32, through_to_kite=False)
        assert [passed for _, passed, _ in bad] == [True, False, False], bad
    finally:
        asyncio.run_coroutine_threadsafe(shutdown(), loop).result(5)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(5)
        loop.close()


class Recorder:
    """subprocess.run as the VM would answer it: Oracle's INPUT chain ends in a REJECT at line 5."""

    LISTING = ("Chain INPUT (policy ACCEPT)\nnum  target     prot opt source               destination\n"
               "1    ACCEPT     all  --  0.0.0.0/0            0.0.0.0/0            state RELATED,ESTABLISHED\n"
               "2    ACCEPT     icmp --  0.0.0.0/0            0.0.0.0/0\n"
               "3    ACCEPT     all  --  0.0.0.0/0            0.0.0.0/0\n"
               "4    ACCEPT     tcp  --  0.0.0.0/0            0.0.0.0/0            state NEW tcp dpt:22\n"
               "5    REJECT     all  --  0.0.0.0/0            0.0.0.0/0            reject-with icmp-host-prohibited\n")

    def __init__(self, accepted=False):
        self.calls, self.accepted = [], accepted

    def __call__(self, cmd, check=True):
        self.calls.append(cmd)
        if cmd[:2] == ["iptables", "-C"]:
            return subprocess.CompletedProcess(cmd, 0 if self.accepted else 1, "")
        if cmd[:2] == ["iptables", "-L"]:
            return subprocess.CompletedProcess(cmd, 0, self.LISTING)
        if cmd[:2] == ["iptables", "-I"]:
            self.accepted = True
        if cmd[:2] == ["iptables", "-D"]:
            self.accepted = False
        return subprocess.CompletedProcess(cmd, 0, "")


def test_the_vm_firewall_accepts_the_port_before_oracles_reject_and_keeps_it_for_reboots():
    which = {"iptables": "/usr/sbin/iptables", "netfilter-persistent": "/usr/sbin/netfilter-persistent"}.get
    run = Recorder()
    note = kt.open_firewall(31528, run=run, which=which)
    assert ["iptables", "-I", "INPUT", "5", "-p", "tcp", "--dport", "31528", "-j", "ACCEPT"] in run.calls
    assert ["netfilter-persistent", "save"] in run.calls and "rule 5" in note
    again = Recorder(accepted=True)
    assert "already accepts" in kt.open_firewall(31528, run=again, which=which)
    assert not [c for c in again.calls if c[:2] == ["iptables", "-I"]]          # never a duplicate rule
    kt.close_firewall(31528, run=run, which=which)
    assert ["iptables", "-D", "INPUT", "-p", "tcp", "--dport", "31528", "-j", "ACCEPT"] in run.calls


def test_install_keeps_its_password_writes_a_hardened_service_and_prints_both_env_lines(tmp_path, capsys):
    paths = dict(install_dir=str(tmp_path / "opt"), env_file=str(tmp_path / "kite-tunnel.env"),
                 unit_file=str(tmp_path / "kite-tunnel.service"))
    seen = []

    def passing(port, user, password):
        seen.append((port, user, password))
        return [("a check", True, "ok")]

    run = Recorder()
    common = dict(run=run, require_root=False, test=passing, wait=lambda port: True, **paths)
    assert kt.install(31528, "161.118.160.180", None, **common) == 0
    first = kt.read_env_file(paths["env_file"])
    assert len(first["KITE_TUNNEL_PASSWORD"]) == 48 and first["KITE_TUNNEL_PORT"] == "31528"
    if os.name != "nt":
        assert os.stat(paths["env_file"]).st_mode & 0o777 == 0o600
    unit = Path(paths["unit_file"]).read_text()
    assert "DynamicUser=yes" in unit and "ProtectSystem=strict" in unit and "kite_tunnel.py serve" in unit
    assert (Path(paths["install_dir"]) / "kite_tunnel.py").exists()
    assert ["systemctl", "restart", "kite-tunnel"] in run.calls
    out = capsys.readouterr().out
    url = f"http://kite:{first['KITE_TUNNEL_PASSWORD']}@161.118.160.180:31528"
    assert f"KITE_PROXY_URL={url}" in out and f"KITE_ORDER_PROXY_URL={url}" in out
    assert "ingress rule, TCP port 31528" in out
    assert kt.install(31528, "161.118.160.180", None, **common) == 0             # again: the same password
    assert kt.read_env_file(paths["env_file"])["KITE_TUNNEL_PASSWORD"] == first["KITE_TUNNEL_PASSWORD"]
    assert seen[0][2] == first["KITE_TUNNEL_PASSWORD"]

    def failing(port, user, password):
        return [("TLS to api.kite.trade", False, "refused")]

    capsys.readouterr()
    assert kt.install(31528, "161.118.160.180", None, **dict(common, test=failing)) == 1
    out = capsys.readouterr().out
    assert "do not switch the .env files yet" in out and "KITE_PROXY_URL=" not in out


def test_a_short_password_is_refused():
    with pytest.raises(ValueError):
        kt.Tunnel(USER, "short")
