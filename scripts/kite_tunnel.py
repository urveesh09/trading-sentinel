#!/usr/bin/env python3
"""[O25c 2026-10-25] The Kite tunnel, for the free Oracle VM whose IP Kite has registered.

Why. The relay on this VM (port 31527) forwards plain HTTP. Every request's
Authorization header (the API key and the day's access token) crosses the
internet readable, and anyone who finds the port can use it. This program is
the encrypted replacement. It serves exactly one thing: an HTTP CONNECT tunnel
to api.kite.trade:443, for clients that send its password. The home machine
speaks TLS to Kite inside the tunnel, so:

  - the token is encrypted from the home machine all the way to Kite;
  - orders still leave from this VM's IP, the static IP Kite checks;
  - no other host, port or method is served: it is not an open proxy.

The tunnel password travels in the CONNECT request, outside TLS. Someone who
captured it could reach api.kite.trade from this IP, but without a Kite access
token (now always inside TLS) Kite gives them nothing.

Python 3.8+ standard library only: nothing to buy and nothing to install.

  sudo python3 kite_tunnel.py install [--port 31528] [--public-ip 161.118.160.180] [--allow CIDR[,CIDR]]
      Once. Installs the service and opens this VM's own firewall for the port,
      then runs a self-test through the tunnel to Kite. Prints the two .env lines.
      Re-running keeps the password.
  sudo python3 kite_tunnel.py status       is it running, and what else listens (the old relay)
  sudo python3 kite_tunnel.py print-env    the two .env lines again
  sudo python3 kite_tunnel.py uninstall
       python3 kite_tunnel.py serve        what the service runs (settings from /etc/kite-tunnel.env)

Oracle's own firewall (the subnet's security list) is outside the VM. Add an
ingress rule for the port in the Oracle console (docs/runbooks/fno-live-test.md).
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hmac
import ipaddress
import os
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple

TARGET_HOST = "api.kite.trade"
TARGET_PORT = 443
DEFAULT_PORT = 31528
DEFAULT_PUBLIC_IP = "161.118.160.180"
OLD_RELAY_PORT = 31527
USER = "kite"
HEAD_LIMIT = 8192           # bytes of request head accepted
HEAD_TIMEOUT = 10.0         # seconds a client has to send its CONNECT head
UPSTREAM_TIMEOUT = 10.0     # seconds to reach Kite
IDLE_TIMEOUT = 300.0        # a tunnel with no bytes either way for this long is closed
MAX_CONNECTIONS = 128       # tunnels plus handshakes in progress
AUTH_FAIL_DELAY = 1.0       # a wrong password waits this long for its 407

INSTALL_DIR = "/opt/kite-tunnel"
ENV_FILE = "/etc/kite-tunnel.env"
UNIT_FILE = "/etc/systemd/system/kite-tunnel.service"
SERVICE = "kite-tunnel"

UNIT = """[Unit]
Description=Kite tunnel (HTTP CONNECT to api.kite.trade:443 only)
After=network-online.target
Wants=network-online.target

[Service]
EnvironmentFile={env_file}
Environment=PYTHONUNBUFFERED=1
ExecStart={python} {install_dir}/kite_tunnel.py serve
DynamicUser=yes
Restart=always
RestartSec=3
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
ProtectKernelLogs=yes
ProtectClock=yes
ProtectHostname=yes
PrivateUsers=yes
CapabilityBoundingSet=
RestrictNamespaces=yes
RestrictRealtime=yes
RestrictSUIDSGID=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes
SystemCallArchitectures=native
SystemCallFilter=@system-service
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
UMask=0077
LimitNOFILE=4096

[Install]
WantedBy=multi-user.target
"""


def _log(message: str) -> None:
    print(time.strftime("%Y-%m-%dT%H:%M:%S") + " " + message, flush=True)


class Tunnel:
    """CONNECT to api.kite.trade:443 only, for clients that send the password."""

    def __init__(self, user: str, password: str, allow: Sequence[str] = (),
                 upstream: Tuple[str, int] = (TARGET_HOST, TARGET_PORT), *,
                 idle_timeout: float = IDLE_TIMEOUT, head_timeout: float = HEAD_TIMEOUT,
                 upstream_timeout: float = UPSTREAM_TIMEOUT, auth_fail_delay: float = AUTH_FAIL_DELAY,
                 max_connections: int = MAX_CONNECTIONS) -> None:
        if len(password) < 16:
            raise ValueError("the tunnel password must be at least 16 characters")
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self._expected = f"Basic {token}".encode()
        self.allow = [ipaddress.ip_network(a.strip(), strict=False) for a in allow if a.strip()]
        self.upstream = upstream
        self.idle_timeout, self.head_timeout = idle_timeout, head_timeout
        self.upstream_timeout, self.auth_fail_delay = upstream_timeout, auth_fail_delay
        self.max_connections = max_connections
        self.active = 0

    def _allowed(self, client: str) -> bool:
        if not self.allow:
            return True
        try:
            address = ipaddress.ip_address(client)
        except ValueError:
            return False
        if address.version == 6 and address.ipv4_mapped:
            address = address.ipv4_mapped
        return any(address in network for network in self.allow)

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        client = str(peer[0]) if peer else "?"
        started = time.monotonic()
        outcome, up, down = "closed", 0, 0
        kite_writer = None
        self.active += 1
        try:
            if self.active > self.max_connections:
                outcome = "busy"
                await self._answer(writer, 503, "Service Unavailable")
                return
            if not self._allowed(client):
                outcome = "client_not_allowed"
                return
            try:
                head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), self.head_timeout)
            except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError,
                    ConnectionError):
                outcome = "no_request"
                return
            if len(head) > HEAD_LIMIT:
                outcome = "request_too_large"
                await self._answer(writer, 431, "Request Header Fields Too Large")
                return
            lines = head.decode("latin-1").split("\r\n")
            request = lines[0].split(" ")
            headers: Dict[str, str] = {}
            for line in lines[1:]:
                name, sep, value = line.partition(":")
                if sep:
                    headers[name.strip().lower()] = value.strip()
            if len(request) != 3 or request[0] != "CONNECT" or not request[2].startswith("HTTP/1."):
                outcome = "not_connect"
                await self._answer(writer, 405, "Method Not Allowed")
                return
            # The password first: nothing about what the tunnel serves is told to a stranger.
            if not hmac.compare_digest(headers.get("proxy-authorization", "").encode("latin-1"), self._expected):
                outcome = "wrong_password"
                await asyncio.sleep(self.auth_fail_delay)
                await self._answer(writer, 407, "Proxy Authentication Required",
                                   'Proxy-Authenticate: Basic realm="kite-tunnel"\r\n')
                return
            host, _, port = request[1].rpartition(":")
            if host.lower() != TARGET_HOST or port != str(TARGET_PORT):
                outcome = "target_refused"
                await self._answer(writer, 403, "Forbidden")
                return
            try:
                kite_reader, kite_writer = await asyncio.wait_for(
                    asyncio.open_connection(*self.upstream), self.upstream_timeout)
            except (OSError, asyncio.TimeoutError):
                outcome = "kite_unreachable"
                await self._answer(writer, 502, "Bad Gateway")
                return
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            await writer.drain()
            outcome = "tunnel"
            up, down = await self._pipe(reader, writer, kite_reader, kite_writer)
        except Exception as exc:     # one connection's failure never stops the service
            outcome = f"error:{type(exc).__name__}"
        finally:
            self.active -= 1
            for stream in (writer, kite_writer):
                if stream is not None:
                    try:
                        stream.close()
                        await stream.wait_closed()
                    except Exception:
                        pass
            _log(f"client={client} outcome={outcome} up={up} down={down} "
                 f"secs={time.monotonic() - started:.1f}")

    @staticmethod
    async def _answer(writer: asyncio.StreamWriter, code: int, reason: str, extra: str = "") -> None:
        try:
            writer.write(f"HTTP/1.1 {code} {reason}\r\n{extra}Content-Length: 0\r\n"
                         "Connection: close\r\n\r\n".encode())
            await writer.drain()
        except (ConnectionError, OSError):
            pass

    async def _pipe(self, client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter,
                    kite_reader: asyncio.StreamReader, kite_writer: asyncio.StreamWriter) -> Tuple[int, int]:
        """Bytes both ways until either side closes or both are quiet for idle_timeout."""
        loop = asyncio.get_running_loop()
        last = [loop.time()]
        moved = [0, 0]
        tick = min(30.0, self.idle_timeout)

        async def pump(source: asyncio.StreamReader, sink: asyncio.StreamWriter, index: int) -> str:
            while True:
                try:
                    data = await asyncio.wait_for(source.read(65536), tick)
                except asyncio.TimeoutError:
                    if loop.time() - last[0] >= self.idle_timeout:
                        return "idle"
                    continue
                if not data:
                    try:
                        if sink.can_write_eof():
                            sink.write_eof()
                    except (ConnectionError, OSError):
                        pass
                    return "eof"
                last[0] = loop.time()
                moved[index] += len(data)
                sink.write(data)
                await sink.drain()

        tasks = [asyncio.ensure_future(pump(client_reader, kite_writer, 0)),
                 asyncio.ensure_future(pump(kite_reader, client_writer, 1))]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            first = next(iter(done))
            if pending and not first.cancelled() and first.exception() is None and first.result() == "eof":
                # A half-close: the other direction may still be delivering (it ends on idle by itself).
                await asyncio.wait(pending)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        return moved[0], moved[1]


async def serve(tunnel: Tunnel, bind: str, port: int) -> None:
    server = await asyncio.start_server(tunnel.handle, bind, port, reuse_address=True)
    clients = ", clients " + ",".join(str(n) for n in tunnel.allow) if tunnel.allow else ""
    _log(f"kite tunnel listening on {bind}:{port}: CONNECT {TARGET_HOST}:{TARGET_PORT} only{clients}")
    async with server:
        await server.serve_forever()


# --- settings -----------------------------------------------------------------------------------------

def read_env_file(path: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    try:
        with open(path) as handle:
            for line in handle:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip()
    except (FileNotFoundError, PermissionError):
        pass        # the service's own user cannot read it: systemd has passed the values in already
    return values


def write_env_file(path: str, values: Dict[str, str]) -> None:
    previous = os.umask(0o077)
    try:
        with open(path, "w") as handle:
            handle.write("# The Kite tunnel (scripts/kite_tunnel.py). Root-only: it holds the tunnel password.\n")
            for key, value in values.items():
                handle.write(f"{key}={value}\n")
    finally:
        os.umask(previous)
    os.chmod(path, 0o600)


def env_lines(values: Dict[str, str], public_ip: str) -> List[str]:
    url = (f"http://{values.get('KITE_TUNNEL_USER', USER)}:{values['KITE_TUNNEL_PASSWORD']}"
           f"@{public_ip}:{values.get('KITE_TUNNEL_PORT', DEFAULT_PORT)}")
    return ["# node-gateway/.env (all of the gateway's Kite calls):",
            f"KITE_PROXY_URL={url}",
            "# the root .env, beside docker-compose.yml (the engine's orders):",
            f"KITE_ORDER_PROXY_URL={url}"]


# --- self-test ----------------------------------------------------------------------------------------

def _read_head(sock: socket.socket) -> bytes:
    data = b""
    while b"\r\n\r\n" not in data and len(data) < HEAD_LIMIT:
        chunk = sock.recv(1)
        if not chunk:
            break
        data += chunk
    return data


def _status_of(head: bytes) -> int:
    try:
        return int(head.split(b" ", 2)[1])
    except (IndexError, ValueError):
        return 0


def self_test(port: int, user: str, password: str, host: str = "127.0.0.1", *, through_to_kite: bool = True,
              timeout: float = 15.0) -> List[Tuple[str, bool, str]]:
    """(check, passed, detail) for: no password refused, another host refused, Kite reached over TLS."""
    def ask(target: str, credentials: Optional[str]) -> Tuple[socket.socket, int]:
        sock = socket.create_connection((host, port), timeout=timeout)
        head = f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n"
        if credentials:
            head += "Proxy-Authorization: Basic " + base64.b64encode(credentials.encode()).decode() + "\r\n"
        sock.sendall((head + "\r\n").encode())
        return sock, _status_of(_read_head(sock))

    results: List[Tuple[str, bool, str]] = []
    kite = f"{TARGET_HOST}:{TARGET_PORT}"
    try:
        sock, status = ask(kite, None)
        sock.close()
        results.append(("a client without the password is refused", status == 407, f"HTTP {status}"))
        sock, status = ask("example.com:443", f"{user}:{password}")
        sock.close()
        results.append(("any host but api.kite.trade:443 is refused", status == 403, f"HTTP {status}"))
        sock, status = ask(kite, f"{user}:{password}")
        if status != 200:
            sock.close()
            results.append(("the tunnel reaches Kite", False, f"HTTP {status}"))
        elif not through_to_kite:
            sock.close()
            results.append(("the tunnel opens to Kite", True, "HTTP 200"))
        else:
            context = ssl.create_default_context()
            with context.wrap_socket(sock, server_hostname=TARGET_HOST) as tls:
                tls.sendall(b"GET / HTTP/1.1\r\nHost: api.kite.trade\r\nUser-Agent: kite-tunnel-self-test\r\n"
                            b"Connection: close\r\n\r\n")
                answer = _read_head(tls).split(b"\r\n", 1)[0].decode("latin-1", "replace")
            results.append(("TLS to api.kite.trade through the tunnel (certificate verified)",
                            answer.startswith("HTTP/"), f"Kite answered {answer!r}"))
    except (OSError, ssl.SSLError) as exc:
        results.append(("the tunnel answers on its port", False, f"{type(exc).__name__}: {exc}"))
    return results


# --- install / status / uninstall (run on the VM with sudo) --------------------------------------------

Runner = Callable[..., subprocess.CompletedProcess]


def _run(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def open_firewall(port: int, run: Runner = _run, which: Callable[[str], Optional[str]] = shutil.which) -> str:
    """This VM's own firewall. Oracle's Ubuntu images end INPUT with a REJECT: insert ACCEPT before it."""
    notes = []
    if which("iptables"):
        rule = ["INPUT", "-p", "tcp", "--dport", str(port), "-j", "ACCEPT"]
        if run(["iptables", "-C", *rule], check=False).returncode == 0:
            notes.append(f"iptables already accepts {port}")
        else:
            listing = run(["iptables", "-L", "INPUT", "--line-numbers", "-n"], check=False).stdout or ""
            position = next((line.split()[0] for line in listing.splitlines()
                             if line.split()[:1] and line.split()[0].isdigit()
                             and len(line.split()) > 1 and line.split()[1] in ("REJECT", "DROP")), "1")
            run(["iptables", "-I", "INPUT", position, "-p", "tcp", "--dport", str(port), "-j", "ACCEPT"])
            notes.append(f"iptables accepts {port} (rule {position})")
            if which("netfilter-persistent"):
                run(["netfilter-persistent", "save"])
                notes.append("saved for reboots")
            else:
                notes.append("NOT saved for reboots (no netfilter-persistent): sudo apt install iptables-persistent")
    if which("ufw") and "Status: active" in (run(["ufw", "status"], check=False).stdout or ""):
        run(["ufw", "allow", f"{port}/tcp"])
        notes.append(f"ufw allows {port}")
    return "; ".join(notes) or "no firewall on this VM restricts the port"


def close_firewall(port: int, run: Runner = _run, which: Callable[[str], Optional[str]] = shutil.which) -> None:
    if which("iptables"):
        rule = ["INPUT", "-p", "tcp", "--dport", str(port), "-j", "ACCEPT"]
        for _ in range(10):         # every copy of the rule, a bounded number of times
            if run(["iptables", "-C", *rule], check=False).returncode != 0:
                break
            run(["iptables", "-D", *rule])
        if which("netfilter-persistent"):
            run(["netfilter-persistent", "save"])
    if which("ufw") and "Status: active" in (run(["ufw", "status"], check=False).stdout or ""):
        run(["ufw", "delete", "allow", f"{port}/tcp"], check=False)


def _wait_listening(port: int, seconds: float = 15.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1.0).close()
            return True
        except OSError:
            time.sleep(0.5)
    return False


def install(port: int, public_ip: str, allow: str, *, run: Runner = _run, install_dir: str = INSTALL_DIR,
            env_file: str = ENV_FILE, unit_file: str = UNIT_FILE, require_root: bool = True,
            test: Callable[..., List[Tuple[str, bool, str]]] = self_test,
            wait: Callable[[int], bool] = _wait_listening) -> int:
    if require_root and os.geteuid() != 0:
        print("Run it with sudo: sudo python3 kite_tunnel.py install")
        return 2
    if not shutil.which("systemctl") and require_root:
        print("This VM has no systemd; run `python3 kite_tunnel.py serve` under your own supervisor.")
        return 2
    os.makedirs(install_dir, exist_ok=True)
    os.chmod(install_dir, 0o755)
    target = os.path.join(install_dir, "kite_tunnel.py")
    if os.path.abspath(__file__) != os.path.abspath(target):
        shutil.copyfile(os.path.abspath(__file__), target)
    os.chmod(target, 0o644)
    values = read_env_file(env_file)
    kept = bool(values.get("KITE_TUNNEL_PASSWORD"))
    values = {
        "KITE_TUNNEL_USER": values.get("KITE_TUNNEL_USER") or USER,
        "KITE_TUNNEL_PASSWORD": values.get("KITE_TUNNEL_PASSWORD") or secrets.token_hex(24),
        "KITE_TUNNEL_PORT": str(port),
        "KITE_TUNNEL_BIND": values.get("KITE_TUNNEL_BIND") or "0.0.0.0",
        "KITE_TUNNEL_ALLOW": allow if allow is not None else values.get("KITE_TUNNEL_ALLOW", ""),
    }
    write_env_file(env_file, values)
    with open(unit_file, "w") as handle:
        handle.write(UNIT.format(env_file=env_file, python=shutil.which("python3") or "/usr/bin/python3",
                                 install_dir=install_dir))
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", SERVICE])
    run(["systemctl", "restart", SERVICE])
    print(f"Service {SERVICE}: installed and started (password {'kept' if kept else 'new'}).")
    print("Firewall on this VM: " + open_firewall(port, run=run))
    if not wait(port):
        print(f"FAIL: nothing listens on {port}. See: sudo journalctl -u {SERVICE} -n 30 --no-pager")
        return 1
    results = test(port, values["KITE_TUNNEL_USER"], values["KITE_TUNNEL_PASSWORD"])
    for check, passed, detail in results:
        print(f"  {'PASS' if passed else 'FAIL'}  {check}: {detail}")
    if not all(passed for _, passed, _ in results):
        print("The self-test failed: do not switch the .env files yet.")
        return 1
    print()
    print("Self-test passed. Put these lines in the two .env files on the home PC.")
    print("Keep the password out of chats and screenshots:")
    for line in env_lines(values, public_ip):
        print("  " + line)
    print()
    print(f"Last step outside this VM: in the Oracle console add an ingress rule, TCP port {port}, "
          "to the VM subnet's security list (docs/runbooks/fno-live-test.md).")
    return 0


def status(run: Runner = _run, env_file: str = ENV_FILE) -> int:
    values = read_env_file(env_file)
    port = values.get("KITE_TUNNEL_PORT", str(DEFAULT_PORT))
    state = (run(["systemctl", "is-active", SERVICE], check=False).stdout or "").strip() or "unknown"
    print(f"Service {SERVICE}: {state}; port {port}")
    listening = run(["ss", "-ltnp"], check=False).stdout or ""
    for wanted, label in ((port, "the tunnel"), (str(OLD_RELAY_PORT), "the old plain-HTTP relay")):
        rows = [line for line in listening.splitlines() if f":{wanted} " in line]
        print(f"Port {wanted} ({label}): " + (rows[0].split()[-1] if rows else "nothing listening"))
    print((run(["journalctl", "-u", SERVICE, "-n", "10", "--no-pager"], check=False).stdout or "").rstrip())
    return 0 if state == "active" else 1


def uninstall(run: Runner = _run, install_dir: str = INSTALL_DIR, env_file: str = ENV_FILE,
              unit_file: str = UNIT_FILE) -> int:
    values = read_env_file(env_file)
    port = int(values.get("KITE_TUNNEL_PORT", DEFAULT_PORT))
    run(["systemctl", "disable", "--now", SERVICE], check=False)
    for path in (unit_file, env_file, os.path.join(install_dir, "kite_tunnel.py")):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
    run(["systemctl", "daemon-reload"], check=False)
    close_firewall(port, run=run)
    print(f"Removed. Also remove the Oracle security-list rule for TCP {port}.")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="The Kite tunnel (CONNECT to api.kite.trade:443 only).")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="run the tunnel (the service does this)")
    inst = sub.add_parser("install", help="install the service, open the VM firewall, self-test (sudo)")
    inst.add_argument("--port", type=int, default=DEFAULT_PORT)
    inst.add_argument("--public-ip", default=DEFAULT_PUBLIC_IP, help="this VM's public IP, for the .env lines")
    inst.add_argument("--allow", default=None, help="optional: only these client IPs/CIDRs, comma-separated")
    sub.add_parser("status", help="service state, listeners, recent log")
    env_cmd = sub.add_parser("print-env", help="print the two .env lines again (sudo)")
    env_cmd.add_argument("--public-ip", default=DEFAULT_PUBLIC_IP)
    sub.add_parser("uninstall", help="remove the service and its firewall rule (sudo)")
    args = parser.parse_args(argv)
    if args.command == "serve":
        values = dict(read_env_file(ENV_FILE), **{k: v for k, v in os.environ.items() if k.startswith("KITE_TUNNEL_")})
        if not values.get("KITE_TUNNEL_PASSWORD"):
            print("KITE_TUNNEL_PASSWORD is not set (run install first).", file=sys.stderr)
            return 2
        tunnel = Tunnel(values.get("KITE_TUNNEL_USER", USER), values["KITE_TUNNEL_PASSWORD"],
                        (values.get("KITE_TUNNEL_ALLOW") or "").split(","))
        asyncio.run(serve(tunnel, values.get("KITE_TUNNEL_BIND", "0.0.0.0"),
                          int(values.get("KITE_TUNNEL_PORT", DEFAULT_PORT))))
        return 0
    if args.command == "install":
        return install(args.port, args.public_ip, args.allow)
    if args.command == "status":
        return status()
    if args.command == "print-env":
        values = read_env_file(ENV_FILE)
        if not values.get("KITE_TUNNEL_PASSWORD"):
            print("Not installed (or run it with sudo).")
            return 2
        print("\n".join(env_lines(values, args.public_ip)))
        return 0
    return uninstall()


if __name__ == "__main__":
    raise SystemExit(main())
