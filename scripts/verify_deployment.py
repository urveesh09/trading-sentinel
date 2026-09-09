#!/usr/bin/env python3
"""Verify that every application container carries one expected release SHA.

Run this *after* a normal Compose rebuild/recreate.  It never deploys,
restarts, removes, or changes a container.  A receipt is written only when
all identity checks and the optional HTTP smoke check pass.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, Iterable

APPLICATION_SERVICES = ("node-gateway", "python-engine", "agent")
SHA_RE = re.compile(r"^[0-9a-f]{7,64}$")


class VerificationError(RuntimeError):
    """The runtime does not prove that the requested release is deployed."""


def _environment(raw: Iterable[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in raw:
        key, separator, value = str(item).partition("=")
        if separator:
            result[key] = value
    return result


def verify_containers(expected_sha: str, containers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Validate inspect payloads without invoking Docker (unit-testable core)."""
    expected = expected_sha.strip().lower()
    if not SHA_RE.fullmatch(expected):
        raise VerificationError("expected SHA must be a 7-64 character lowercase hexadecimal revision")

    errors: list[str] = []
    services: dict[str, dict[str, str]] = {}
    for service in APPLICATION_SERVICES:
        inspect = containers.get(service)
        if not inspect:
            errors.append(f"{service}: container is absent")
            continue
        env = _environment(inspect.get("Config", {}).get("Env", []))
        actual = env.get("SENTINEL_RELEASE_SHA", "")
        declared_service = env.get("SENTINEL_SERVICE_NAME", "")
        build_utc = env.get("SENTINEL_BUILD_UTC", "")
        if actual != expected:
            errors.append(f"{service}: release SHA {actual or '<missing>'} != expected {expected}")
        if declared_service != service:
            errors.append(f"{service}: service identity {declared_service or '<missing>'} is invalid")
        if not build_utc or build_utc == "unknown":
            errors.append(f"{service}: build UTC is missing")
        services[service] = {
            "container_id": str(inspect.get("Id", ""))[:12],
            "image_id": str(inspect.get("Image", "")),
            "started_at": str(inspect.get("State", {}).get("StartedAt", "")),
            "release_sha": actual,
            "build_utc": build_utc,
        }
    if errors:
        raise VerificationError("; ".join(errors))
    return {"expected_sha": expected, "services": services}


def verify_health(expected_sha: str, payload: dict[str, Any]) -> None:
    """Reject a reachable gateway that reports a different gateway/engine build."""
    gateway = payload.get("release") or {}
    engine = payload.get("python_engine_release") or {}
    errors = []
    if gateway.get("revision") != expected_sha or not gateway.get("declared"):
        errors.append("gateway health release identity does not match expected SHA")
    if engine.get("revision") != expected_sha or not engine.get("declared"):
        errors.append("python-engine health release identity does not match expected SHA")
    if errors:
        raise VerificationError("; ".join(errors))


def _command(command: list[str]) -> str:
    return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()


def _inspect_compose_service(service: str) -> dict[str, Any]:
    ids = [line for line in _command(["docker", "compose", "ps", "-q", service]).splitlines() if line]
    if len(ids) != 1:
        raise VerificationError(f"{service}: expected exactly one Compose container, found {len(ids)}")
    result = json.loads(_command(["docker", "inspect", ids[0]]))
    return result[0]


def _get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=8) as response:  # nosec B310: explicit operator URL
        if response.status != 200:
            raise VerificationError(f"health smoke returned HTTP {response.status}")
        decoded = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, dict):
        raise VerificationError("health smoke did not return a JSON object")
    return decoded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-sha", required=True, help="target Git revision (7-64 lowercase hex characters)")
    parser.add_argument("--health-url", default="http://127.0.0.1/api/health")
    parser.add_argument("--skip-health", action="store_true", help="verify Docker identities only")
    parser.add_argument("--receipt", type=Path, help="write JSON receipt after every check passes")
    args = parser.parse_args()

    try:
        receipt = verify_containers(args.expected_sha, {
            service: _inspect_compose_service(service) for service in APPLICATION_SERVICES
        })
        if not args.skip_health:
            verify_health(receipt["expected_sha"], _get_json(args.health_url))
        receipt["verified_at"] = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        receipt["health_checked"] = not args.skip_health
        if args.receipt:
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    except (VerificationError, subprocess.CalledProcessError, OSError, json.JSONDecodeError) as exc:
        print(f"deployment verification FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
