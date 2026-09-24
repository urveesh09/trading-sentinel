#!/usr/bin/env python3
"""Verify the rendered Compose log-retention contract.

This is deliberately a deployment-configuration check rather than an estimate
of production retention.  It asks Compose to render the effective service
definition, then checks the only settings Docker applies to the engine's JSON
log files.  It neither connects to a running container nor emits environment
values from the rendered configuration.

Usage:

    python scripts/verify_compose_logging.py
    python scripts/verify_compose_logging.py --compose-file docker-compose.yml
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


SERVICE_NAME = "python-engine"
REQUIRED_DRIVER = "json-file"
MINIMUM_CAPACITY_MIB = 200
_SIZE_RE = re.compile(r"^(?P<number>[1-9][0-9]*)(?P<unit>[kmg])$", re.IGNORECASE)
_MIB_BY_UNIT = {"k": 1 / 1024, "m": 1, "g": 1024}


class ComposeLoggingError(ValueError):
    """The rendered Compose service cannot satisfy the retention contract."""


def _size_to_mib(value: object, *, field: str) -> float:
    """Parse Docker's positive K/M/G json-file size notation strictly."""
    if not isinstance(value, str):
        raise ComposeLoggingError(f"{field} must be a string in K/M/G notation")
    match = _SIZE_RE.fullmatch(value.strip())
    if not match:
        raise ComposeLoggingError(
            f"{field} must be a positive whole K/M/G size, got {value!r}"
        )
    return int(match.group("number")) * _MIB_BY_UNIT[match.group("unit").lower()]


def assess_rendered_compose(
    payload: object,
    *,
    minimum_capacity_mib: int = MINIMUM_CAPACITY_MIB,
) -> dict[str, object]:
    """Validate rendered ``python-engine`` JSON logging without leaking env."""
    if not isinstance(payload, dict):
        raise ComposeLoggingError("Compose config must be a JSON object")
    services = payload.get("services")
    if not isinstance(services, dict):
        raise ComposeLoggingError("Compose config has no services object")
    service = services.get(SERVICE_NAME)
    if not isinstance(service, dict):
        raise ComposeLoggingError(f"Compose config has no {SERVICE_NAME!r} service")
    logging = service.get("logging")
    if not isinstance(logging, dict):
        raise ComposeLoggingError(f"{SERVICE_NAME} has no rendered logging section")
    if logging.get("driver") != REQUIRED_DRIVER:
        raise ComposeLoggingError(
            f"{SERVICE_NAME} logging driver must be {REQUIRED_DRIVER!r}"
        )
    options = logging.get("options")
    if not isinstance(options, dict):
        raise ComposeLoggingError(f"{SERVICE_NAME} json-file logging has no options")
    max_size_mib = _size_to_mib(options.get("max-size"), field="max-size")
    max_file = options.get("max-file")
    if not isinstance(max_file, (str, int)) or isinstance(max_file, bool):
        raise ComposeLoggingError("max-file must be a positive integer")
    try:
        max_file_int = int(max_file)
    except ValueError as exc:
        raise ComposeLoggingError("max-file must be a positive integer") from exc
    if str(max_file_int) != str(max_file).strip() or max_file_int <= 0:
        raise ComposeLoggingError("max-file must be a positive integer")
    capacity_mib = max_size_mib * max_file_int
    if capacity_mib < minimum_capacity_mib:
        raise ComposeLoggingError(
            f"{SERVICE_NAME} log capacity is {capacity_mib:g} MiB; expected at least "
            f"{minimum_capacity_mib} MiB"
        )
    return {
        "service": SERVICE_NAME,
        "driver": REQUIRED_DRIVER,
        "max_size": options["max-size"],
        "max_file": max_file_int,
        "capacity_mib": capacity_mib,
    }


def render_compose(compose_file: Path) -> dict[str, Any]:
    """Return ``docker compose config --format json`` without printing it."""
    command = ["docker", "compose", "-f", str(compose_file), "config", "--format", "json"]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise ComposeLoggingError(f"cannot run docker compose: {exc}") from exc
    if completed.returncode:
        detail = completed.stderr.strip() or "no diagnostic output"
        raise ComposeLoggingError(f"docker compose config failed: {detail}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ComposeLoggingError("docker compose config did not emit JSON") from exc
    if not isinstance(payload, dict):
        raise ComposeLoggingError("docker compose config did not emit an object")
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-file", type=Path, default=root / "docker-compose.yml")
    parser.add_argument("--minimum-capacity-mib", type=int, default=MINIMUM_CAPACITY_MIB)
    args = parser.parse_args(argv)
    if args.minimum_capacity_mib <= 0:
        parser.error("--minimum-capacity-mib must be positive")
    try:
        result = assess_rendered_compose(
            render_compose(args.compose_file),
            minimum_capacity_mib=args.minimum_capacity_mib,
        )
    except ComposeLoggingError as exc:
        print(f"compose logging verification failed: {exc}", file=sys.stderr)
        return 2
    print(
        f"{result['service']}: driver={result['driver']} max-size={result['max_size']} "
        f"max-file={result['max_file']} capacity={result['capacity_mib']:g}MiB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
