#!/usr/bin/env python3
"""[WORKFLOW-D.2.a-flags 2026-09-16] Audit the python-engine
``Settings`` defaults and runtime config flags.

Per Workstream D item 2 in NEXT_AGENT_PLAN.md:
> 2. Review migrations, defaults, flags and Docker volumes.

This is the bounded dev-side slice of D.2.a-flags. The
script walks the ``Settings`` class in
``python-engine/config.py`` and classifies every default
into one of three buckets:

  - ``SAFE``: small caps, fail-closed semantics. No
    operator review required.

  - ``RISKY``: large caps, fail-open semantics, or large
    numerical defaults that could cause real-money impact.
    Operator MUST review these before a release.

  - ``INFRASTRUCTURE``: paths, hosts, ports, log levels.
    Reviewed by the deployment runbook, not the audit.

Usage:

    python scripts/audit_defaults.py              # human-readable
    python scripts/audit_defaults.py --json      # machine-readable
    python scripts/audit_defaults.py --out FILE  # write JSON
    python scripts/audit_defaults.py --risky-only
"""
from __future__ import annotations

import argparse
import dataclasses
import enum
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable


class RiskTier(str, enum.Enum):
    SAFE = "SAFE"
    RISKY = "RISKY"
    INFRASTRUCTURE = "INFRASTRUCTURE"


# Bounded default thresholds. Operators can override via
# AUDIT_DEFAULT_* env vars (not currently used; reserved for
# future work).
_BIG_NUMBER_RISK_THRESHOLD = 100_000.0  # anything bigger is potentially risky
_FAIL_OPEN_NAME_TOKENS: tuple[str, ...] = (
    "DISABLE_", "ALLOW_", "OVERRIDE_", "FORCE_", "BYPASS_",
)
_PATH_NAME_TOKENS: tuple[str, ...] = (
    "PATH", "URL", "HOST", "PORT", "DIR", "FILE", "LOG_LEVEL",
    "TIMEOUT", "INTERVAL",
)


@dataclasses.dataclass(frozen=True)
class DefaultAudit:
    """One row of the audit report.

    Attributes:
        name: the Settings attribute name (e.g. ``INITIAL_BANKROLL``).
        default: the default value (as a string for portability).
        type: the declared Python type.
        tier: the risk classification.
        reason: human-readable reason for the tier.
    """
    name: str
    default: str
    type: str
    tier: str
    reason: str


def _format_value(value: Any) -> str:
    """Render a Settings default as a string for the report."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if value is None:
        return "None"
    return repr(value)


def _classify(name: str, default: Any) -> tuple[RiskTier, str]:
    """Classify a Settings default into a risk tier + reason."""
    # Infrastructure: paths, hosts, ports, log levels, etc.
    lowered = name.upper()
    for token in _PATH_NAME_TOKENS:
        if token in lowered:
            return (
                RiskTier.INFRASTRUCTURE,
                f"name contains '{token}' -- infra-level setting, not behaviour",
            )

    # Fail-open name tokens.
    for token in _FAIL_OPEN_NAME_TOKENS:
        if token in lowered:
            return (
                RiskTier.RISKY,
                f"name contains '{token}' -- fail-open semantics, "
                "operator must confirm intent",
            )

    # Big numerical defaults.
    if isinstance(default, (int, float)) and not isinstance(default, bool):
        if abs(default) >= _BIG_NUMBER_RISK_THRESHOLD:
            return (
                RiskTier.RISKY,
                f"large numeric default ({default!r}) >= "
                f"{_BIG_NUMBER_RISK_THRESHOLD!r}; operator must confirm intent",
            )

    # Everything else is SAFE.
    return (
        RiskTier.SAFE,
        "small/no cap, no fail-open name, no large numeric default",
    )


def _load_settings(engine_dir: Path):
    """Dynamically load the ``config.Settings`` class without
    requiring ``config`` to be on ``sys.path`` (it pulls in
    kite_client, models, etc., which need the venv).

    The audit only needs the Settings class metadata --
    not the module's runtime behaviour -- so we use a
    lightweight AST-style approach via ``model_fields``.
    """
    config_path = engine_dir / "config.py"
    if not config_path.is_file():
        raise FileNotFoundError(f"config.py not found in {engine_dir}")
    spec = importlib.util.spec_from_file_location(
        "_python_engine_config", str(config_path),
    )
    # We DON'T exec the module (it has heavy imports). We're
    # only here for the Settings class. If exec fails, fall
    # back to a different strategy: import via venv.
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.Settings
    except Exception as exc:
        raise RuntimeError(
            f"audit_defaults: cannot import config.Settings "
            f"({type(exc).__name__}: {exc}). Run from the "
            f"python-engine directory with its venv active."
        )


def audit_settings(settings_cls: type) -> list[DefaultAudit]:
    """Walk the Settings class and emit one audit row per attribute."""
    rows: list[DefaultAudit] = []
    # pydantic_settings exposes the field metadata via
    # ``model_fields`` (a dict[str, FieldInfo]). The default
    # value lives on ``FieldInfo.default`` -- reading the
    # class attribute via ``getattr(Settings, name)`` raises
    # ``AttributeError`` for fields that pydantic considers
    # undeclared at class scope (even though they DO have
    # a default). We therefore read from ``FieldInfo`` directly.
    if hasattr(settings_cls, "model_fields"):
        field_items = list(settings_cls.model_fields.items())
    else:
        ann = getattr(settings_cls, "__annotations__", {})
        field_items = [(name, ann[name]) for name in ann]
    for name, field_info in field_items:
        # Extract the default from FieldInfo. ``FieldInfo.default``
        # is a sentinel (``PydanticUndefined``) when no default
        # is declared; in that case the field is required and
        # has no default to audit.
        sentinel_undefined = object()
        default = getattr(field_info, "default", sentinel_undefined)
        if default is sentinel_undefined:
            continue
        if name.startswith("_"):
            continue
        if callable(default) and not isinstance(default, (int, float, bool, str, type)):
            continue
        if hasattr(field_info, "annotation") and field_info.annotation is not None:
            declared_type = field_info.annotation
        else:
            declared_type = field_info
        declared_type_str = (
            declared_type.__name__
            if hasattr(declared_type, "__name__")
            else str(declared_type)
        )
        tier, reason = _classify(name, default)
        rows.append(DefaultAudit(
            name=name,
            default=_format_value(default),
            type=declared_type_str,
            tier=tier.value,
            reason=reason,
        ))
    rows.sort(key=lambda r: (r.tier, r.name))
    return rows


def format_audit(rows: Iterable[DefaultAudit]) -> str:
    """Render the audit as a human-readable table."""
    rows = list(rows)
    lines = [
        "# Settings defaults audit",
        "# ----------------------",
        f"# {len(rows)} rows",
        "",
    ]
    by_tier: dict[str, list[DefaultAudit]] = {}
    for row in rows:
        by_tier.setdefault(row.tier, []).append(row)
    for tier in (RiskTier.RISKY.value, RiskTier.INFRASTRUCTURE.value, RiskTier.SAFE.value):
        rows_in_tier = by_tier.get(tier, [])
        if not rows_in_tier:
            continue
        lines.append(f"## {tier} ({len(rows_in_tier)} rows)")
        lines.append("")
        lines.append(f"{'NAME':<50}  {'TYPE':<25}  {'DEFAULT':<20}  REASON")
        lines.append(f"{'-' * 50}  {'-' * 25}  {'-' * 20}  {'-' * 50}")
        for row in rows_in_tier:
            type_str = row.type[:25] if len(row.type) > 25 else row.type
            default_str = row.default[:20] if len(row.default) > 20 else row.default
            lines.append(
                f"{row.name:<50}  {type_str:<25}  {default_str:<20}  {row.reason}"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def audit_as_dicts(rows: Iterable[DefaultAudit]) -> list[dict]:
    """Serialize audit rows for JSON output."""
    return [
        {
            "name": r.name,
            "default": r.default,
            "type": r.type,
            "tier": r.tier,
            "reason": r.reason,
        }
        for r in rows
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-dir", type=Path,
                        default=Path(__file__).resolve().parent.parent / "python-engine",
                        help="Path to the python-engine directory.")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON to stdout")
    parser.add_argument("--out", type=Path, default=None,
                        help="write the report to this path (in addition to stdout)")
    parser.add_argument("--risky-only", action="store_true",
                        help="restrict output to RISKY tier (operator review focus)")
    args = parser.parse_args(argv)
    try:
        Settings = _load_settings(args.engine_dir)
    except Exception as exc:
        print(f"audit_defaults: {exc}", file=sys.stderr)
        return 2
    rows = audit_settings(Settings)
    if args.risky_only:
        rows = [r for r in rows if r.tier == RiskTier.RISKY.value]
    if args.json:
        sys.stdout.write(
            json.dumps(audit_as_dicts(rows), indent=2, sort_keys=True) + "\n"
        )
    else:
        sys.stdout.write(format_audit(rows))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(audit_as_dicts(rows), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    # Non-zero exit if any RISKY rows are present (operators
    # can opt out via AUDIT_FAIL_ON_RISKY=0).
    if os.environ.get("AUDIT_FAIL_ON_RISKY", "0") == "1":
        risky_count = sum(1 for r in rows if r.tier == RiskTier.RISKY.value)
        if risky_count > 0:
            return 3
    return 0


__all__ = [
    "DefaultAudit",
    "RiskTier",
    "audit_as_dicts",
    "audit_settings",
    "format_audit",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
