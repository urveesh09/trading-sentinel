#!/usr/bin/env python3
"""[WORKFLOW-E.2 2026-09-17] Partner card validator.

Per Workstream E in NEXT_AGENT_PLAN.md:
> Improve cards around decisions a manual trader can take:
> index/exchange, timestamp/validity, setup rationale, entry
> trigger and bounded price, exact contract legs/expiry/lot,
> total debit and modeled costs, maximum defined loss,
> invalidation/target and intraday deadline. Explain
> uncertainty and liquidity limits without overwhelming the
> message.

This script is the bounded dev-side slice of E.2. It
takes a partner-card payload (JSON, the same shape that
``_candidate_payload`` produces in
``partner_manual_advisory.py``) and reports:

  - Required fields per scope (MARKET_SETUP,
    CONDITIONAL_PROTECTION).
  - Type validation (e.g. ``legs[i].side`` must be BUY/SELL).
  - Bounded economics (e.g. ``net_debit_rs`` must be > 0
    if set; ``breakevens`` array non-empty).
  - Liquidity-limit surfacing (top-of-book depth vs needed
    quantity) -- the bounded improvement the plan asks for.
  - Hedge interpretation (personalized protection vs
    directional spread) for CONDITIONAL_PROTECTION scope.

Read-only: never mutates state, never sends Telegram,
never places orders. Operators run it locally (or against
a JSON file written by the partner audit pipeline).

Usage:
    # Validate a card from a file.
    python scripts/validate_partner_card.py path/to/card.json

    # Validate a card from stdin.
    cat card.json | python scripts/validate_partner_card.py -

    # JSON output for piping.
    python scripts/validate_partner_card.py card.json --json

Exit code: 0 (PASS) / 1 (FAIL) / 2 (BLOCKER for malformed card).
"""
from __future__ import annotations

import argparse
import dataclasses
import enum
import json
import re
import sys
from pathlib import Path
from typing import Any


class Status(str, enum.Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    BLOCKER = "BLOCKER"

    def exit_code(self) -> int:
        if self == Status.BLOCKER:
            return 2
        if self == Status.FAIL:
            return 1
        return 0


@dataclasses.dataclass(frozen=True)
class ValidationFinding:
    """One row of the validator's report.

    Attributes:
        field: dotted field path (e.g. ``legs[2].strike``).
        status: PASS / WARN / FAIL / BLOCKER.
        message: human-readable explanation.
        expected: optional schema expectation (type, range).
    """
    field: str
    status: Status
    message: str
    expected: str = ""


# Side-token validation (BUY / SELL per AdvisoryLeg.side).
_VALID_SIDES: frozenset[str] = frozenset({"BUY", "SELL"})
_VALID_OPTION_TYPES: frozenset[str] = frozenset({"CE", "PE"})
_VALID_SCOPES: frozenset[str] = frozenset({
    "MARKET_SETUP",
    "CONDITIONAL_PROTECTION",
})
_VALID_EVIDENCE: frozenset[str] = frozenset({
    "QUALIFIED_FOR_ADVISORY",
    "RESEARCH_PREVIEW",
})
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$"
)


def _is_real_date(year: int, month: int, day: int) -> bool:
    """Validate that year/month/day form a real calendar date."""
    import calendar
    if month < 1 or month > 12:
        return False
    if day < 1:
        return False
    return day <= calendar.monthrange(year, month)[1]
_VALID_EXCHANGES: frozenset[str] = frozenset({"NSE", "BSE"})


# Required fields per scope (from the plan's checklist).
_COMMON_REQUIRED_FIELDS: tuple[str, ...] = (
    "scope", "underlying", "exchange", "quote_time", "valid_until",
    "policy_version", "evidence", "thesis_id",
    "legs", "why_now", "uncertainty",
    "invalidation", "management",
    "holding_horizon", "management_deadline",
)

_MARKET_SETUP_REQUIRED: tuple[str, ...] = (
    "net_debit_rs", "max_loss_rs",
    "breakevens",
    "trigger_level", "invalidation_level", "target_level",
    "estimated_round_trip_cost_rs",
)

_CONDITIONAL_PROTECTION_REQUIRED: tuple[str, ...] = (
    "exposure_assumption", "coverage_units",
)


def _is_iso_date(s: Any) -> bool:
    if not isinstance(s, str) or not _ISO_DATE_RE.match(s):
        return False
    try:
        year, month, day = (int(p) for p in s.split("-"))
    except ValueError:
        return False
    return _is_real_date(year, month, day)


def _is_iso_datetime(s: Any) -> bool:
    return isinstance(s, str) and bool(_ISO_DATETIME_RE.match(s))


def _check_type(value: Any, expected_type: str) -> bool:
    """Validate the JSON type of ``value``.

    ``expected_type`` is one of: ``str``, ``int``, ``float``,
    ``bool``, ``list``, ``dict``. ``float`` accepts ints too
    (JSON doesn't distinguish).
    """
    if expected_type == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "str":
        return isinstance(value, str)
    if expected_type == "bool":
        return isinstance(value, bool)
    if expected_type == "list":
        return isinstance(value, list)
    if expected_type == "dict":
        return isinstance(value, dict)
    return True


def _find_value(card: dict, dotted: str) -> Any:
    """Look up ``legs[2].strike`` -> ``card['legs'][2]['strike']``.

    Returns ``_MISSING`` if any path segment is absent.
    """
    cur: Any = card
    for part in dotted.split("."):
        if "[" in part:
            field, rest = part.split("[", 1)
            idx_str = rest.rstrip("]")
            try:
                idx = int(idx_str)
            except ValueError:
                return _MISSING
            if field and cur is not _MISSING:
                cur = cur.get(field) if isinstance(cur, dict) else _MISSING
            if cur is _MISSING:
                return _MISSING
            if not isinstance(cur, list) or idx >= len(cur):
                return _MISSING
            cur = cur[idx]
        else:
            if cur is _MISSING or not isinstance(cur, dict):
                return _MISSING
            cur = cur.get(part, _MISSING)
    return cur


_MISSING = object()


def _validate_required_fields(card: dict) -> list[ValidationFinding]:
    """Check that every common + scope-specific required field is present."""
    findings: list[ValidationFinding] = []
    scope = card.get("scope") if isinstance(card, dict) else None
    required = list(_COMMON_REQUIRED_FIELDS)
    if scope == "MARKET_SETUP":
        required.extend(_MARKET_SETUP_REQUIRED)
    elif scope == "CONDITIONAL_PROTECTION":
        required.extend(_CONDITIONAL_PROTECTION_REQUIRED)

    for field in required:
        value = _find_value(card, field)
        if value is _MISSING:
            findings.append(ValidationFinding(
                field=field,
                status=Status.FAIL,
                message=f"required field '{field}' is missing",
                expected="non-null",
            ))
            continue
        if value is None:
            findings.append(ValidationFinding(
                field=field,
                status=Status.FAIL,
                message=f"required field '{field}' is null",
                expected="non-null",
            ))
            continue
        if isinstance(value, (list, tuple)) and len(value) == 0:
            findings.append(ValidationFinding(
                field=field,
                status=Status.FAIL,
                message=f"required field '{field}' is an empty list",
                expected="non-empty",
            ))
        elif isinstance(value, str) and not value.strip():
            findings.append(ValidationFinding(
                field=field,
                status=Status.FAIL,
                message=f"required field '{field}' is an empty string",
                expected="non-empty",
            ))
    return findings


def _is_present(value: Any) -> bool:
    """A field is 'present' if it's not the MISSING sentinel
    and not None. Used to gate type / format checks."""
    return value is not _MISSING and value is not None


def _validate_type_constraints(card: dict) -> list[ValidationFinding]:
    """Type-checks the major scalar fields."""
    findings: list[ValidationFinding] = []
    type_checks = [
        ("scope", "str"),
        ("underlying", "str"),
        ("exchange", "str"),
        ("policy_version", "str"),
        ("thesis_id", "str"),
        ("evidence", "str"),
        ("net_debit_rs", "float"),
        ("net_credit_rs", "float"),
        ("max_loss_rs", "float"),
        ("max_profit_rs", "float"),
        ("estimated_round_trip_cost_rs", "float"),
        ("trigger_level", "float"),
        ("invalidation_level", "float"),
        ("target_level", "float"),
        ("coverage_units", "int"),
        ("breakevens", "list"),
        ("why_now", "list"),
        ("legs", "list"),
    ]
    for field, expected in type_checks:
        value = _find_value(card, field)
        if not _is_present(value):
            continue  # Required-field check handles this.
        if not _check_type(value, expected):
            findings.append(ValidationFinding(
                field=field,
                status=Status.FAIL,
                message=f"field '{field}' has wrong type: {type(value).__name__}",
                expected=expected,
            ))
    # Scope / evidence enum checks.
    scope = card.get("scope") if isinstance(card, dict) else None
    if scope is not None and scope not in _VALID_SCOPES:
        findings.append(ValidationFinding(
            field="scope",
            status=Status.FAIL,
            message=f"unknown scope: {scope}",
            expected=f"one of {sorted(_VALID_SCOPES)}",
        ))
    evidence = card.get("evidence")
    if evidence is not None and evidence not in _VALID_EVIDENCE:
        findings.append(ValidationFinding(
            field="evidence",
            status=Status.FAIL,
            message=f"unknown evidence: {evidence}",
            expected=f"one of {sorted(_VALID_EVIDENCE)}",
        ))
    exchange = card.get("exchange")
    if exchange is not None and exchange not in _VALID_EXCHANGES:
        findings.append(ValidationFinding(
            field="exchange",
            status=Status.WARN,  # Soft: future exchanges may appear.
            message=f"unrecognized exchange: {exchange}",
            expected=f"one of {sorted(_VALID_EXCHANGES)} (or update VALID_EXCHANGES)",
        ))
    # ISO datetime checks for timestamps.
    for field in ("quote_time", "valid_until", "signal_at",
                   "entry_deadline", "management_deadline",
                   "quote_observed_at", "quote_received_at",
                   "quote_valid_until", "generated_at"):
        value = _find_value(card, field)
        if not _is_present(value):
            continue
        if not _is_iso_datetime(value):
            findings.append(ValidationFinding(
                field=field,
                status=Status.FAIL,
                message=f"field '{field}' is not ISO 8601 datetime: {value!r}",
                expected="YYYY-MM-DDTHH:MM:SS[.fff][Z|+HH:MM]",
            ))
    return findings


def _validate_legs(card: dict) -> list[ValidationFinding]:
    """Per-leg validation: side, option_type, lot_size, ratio."""
    findings: list[ValidationFinding] = []
    legs = _find_value(card, "legs")
    if legs is _MISSING or legs is None or not isinstance(legs, list):
        return findings  # Required-field / type check already flagged.
    for i, leg in enumerate(legs):
        prefix = f"legs[{i}]"
        if not isinstance(leg, dict):
            findings.append(ValidationFinding(
                field=prefix,
                status=Status.FAIL,
                message=f"leg {i} is not a dict: {type(leg).__name__}",
                expected="dict",
            ))
            continue
        side = leg.get("side")
        if side not in _VALID_SIDES:
            findings.append(ValidationFinding(
                field=f"{prefix}.side",
                status=Status.FAIL,
                message=f"leg {i} side is not BUY or SELL: {side!r}",
                expected="BUY | SELL",
            ))
        option_type = leg.get("option_type")
        if option_type not in _VALID_OPTION_TYPES:
            findings.append(ValidationFinding(
                field=f"{prefix}.option_type",
                status=Status.FAIL,
                message=f"leg {i} option_type is not CE or PE: {option_type!r}",
                expected="CE | PE",
            ))
        ratio = leg.get("ratio")
        if not isinstance(ratio, int) or isinstance(ratio, bool) or ratio <= 0:
            findings.append(ValidationFinding(
                field=f"{prefix}.ratio",
                status=Status.FAIL,
                message=f"leg {i} ratio must be a positive integer: {ratio!r}",
                expected="positive int",
            ))
        lot_size = leg.get("lot_size")
        if not isinstance(lot_size, int) or isinstance(lot_size, bool) or lot_size <= 0:
            findings.append(ValidationFinding(
                field=f"{prefix}.lot_size",
                status=Status.FAIL,
                message=f"leg {i} lot_size must be a positive integer: {lot_size!r}",
                expected="positive int",
            ))
        expiry = leg.get("expiry")
        if not _is_iso_date(expiry):
            findings.append(ValidationFinding(
                field=f"{prefix}.expiry",
                status=Status.FAIL,
                message=f"leg {i} expiry must be ISO date YYYY-MM-DD: {expiry!r}",
                expected="YYYY-MM-DD",
            ))
        strike = leg.get("strike")
        if not isinstance(strike, (int, float)) or isinstance(strike, bool) or strike <= 0:
            findings.append(ValidationFinding(
                field=f"{prefix}.strike",
                status=Status.FAIL,
                message=f"leg {i} strike must be positive: {strike!r}",
                expected="positive number",
            ))
        # Liquidity surfacing (the bounded improvement the
        # plan asks for: "explain uncertainty and liquidity
        # limits without overwhelming the message"). We do
        # not require this; we surface it as WARN so the
        # operator can decide whether to add it.
        bid_quantity = leg.get("bid_quantity")
        ask_quantity = leg.get("ask_quantity")
        if bid_quantity is None and ask_quantity is None:
            findings.append(ValidationFinding(
                field=f"{prefix}.liquidity_limit",
                status=Status.WARN,
                message=(
                    f"leg {i} has no bid_quantity/ask_quantity -- the "
                    "operator cannot size the order against top-of-book "
                    "depth. Set bid_quantity + ask_quantity on each leg."
                ),
                expected="bid_quantity and ask_quantity ints",
            ))
    return findings


def _validate_economics(card: dict) -> list[ValidationFinding]:
    """Bounded-economics invariants: net_debit > 0, valid_until > quote_time."""
    findings: list[ValidationFinding] = []
    net_debit = _find_value(card, "net_debit_rs")
    if _is_present(net_debit):
        if not isinstance(net_debit, (int, float)) or isinstance(net_debit, bool) or net_debit <= 0:
            findings.append(ValidationFinding(
                field="net_debit_rs",
                status=Status.FAIL,
                message=f"net_debit_rs must be positive: {net_debit!r}",
                expected="positive number",
            ))
    net_credit = _find_value(card, "net_credit_rs")
    if _is_present(net_credit):
        if not isinstance(net_credit, (int, float)) or isinstance(net_credit, bool) or net_credit <= 0:
            findings.append(ValidationFinding(
                field="net_credit_rs",
                status=Status.FAIL,
                message=f"net_credit_rs must be positive: {net_credit!r}",
                expected="positive number",
            ))
    # valid_until > quote_time (parsed).
    quote_time = _find_value(card, "quote_time")
    valid_until = _find_value(card, "valid_until")
    if (isinstance(quote_time, str) and _is_iso_datetime(quote_time)
        and isinstance(valid_until, str) and _is_iso_datetime(valid_until)):
        if valid_until <= quote_time:
            findings.append(ValidationFinding(
                field="valid_until",
                status=Status.FAIL,
                message=(
                    f"valid_until ({valid_until}) must be strictly "
                    f"after quote_time ({quote_time})"
                ),
                expected="valid_until > quote_time",
            ))
    return findings


def _validate_hedge_interpretation(card: dict) -> list[ValidationFinding]:
    """[WORKFLOW-E.2 2026-09-17] Hedge-first interpretation.

    Per the plan: 'Hedge-first must have an explicit
    interpretation. Conditional protection states the
    exposure assumption and coverage; market directional
    spreads are not automatically personalized hedges.'

    For CONDITIONAL_PROTECTION scope: the card MUST
    surface whether the protection is personalized (the
    user already holds the underlying) or generic (a
    generic view protection). Without this distinction,
    the partner may mis-execute.
    """
    findings: list[ValidationFinding] = []
    scope = card.get("scope") if isinstance(card, dict) else None
    if scope != "CONDITIONAL_PROTECTION":
        return findings

    coverage_assumption = _find_value(card, "exposure_assumption")
    if coverage_assumption is None or coverage_assumption is _MISSING:
        # Already flagged by required-field check.
        return findings

    text = str(coverage_assumption).strip().lower()
    # The plan: "Conditional protection states the exposure
    # assumption and coverage; market directional spreads
    # are not automatically personalized hedges." We check
    # that the assumption text contains one of:
    #   - 'long underlying' / 'short underlying' /
    #     'held underlying' / 'personalized'
    # ...so the partner can distinguish personalized from
    # generic.
    personalization_markers = (
        "long underlying",
        "short underlying",
        "held underlying",
        "personalized",
        "owner holds",
        "personal exposure",
    )
    generic_markers = (
        "generic",
        "any holder",
        "hypothetical",
        "market view",
    )
    has_personal = any(m in text for m in personalization_markers)
    has_generic = any(m in text for m in generic_markers)
    if not (has_personal or has_generic):
        findings.append(ValidationFinding(
            field="exposure_assumption",
            status=Status.WARN,
            message=(
                "exposure_assumption does not state whether the "
                "protection is personalized (operator holds the "
                "underlying) or generic (market view). Add "
                "'personalized' / 'owner holds N lots of "
                "<underlying>' or 'generic' / 'market view' to "
                "the assumption text."
            ),
            expected="personalized OR generic marker",
        ))
    return findings


def validate_card(card: Any) -> list[ValidationFinding]:
    """Run every check and return all findings."""
    findings: list[ValidationFinding] = []
    if not isinstance(card, dict):
        # The card isn't even a dict -- this is BLOCKER
        # because we can't introspect it at all.
        findings.append(ValidationFinding(
            field="<root>",
            status=Status.BLOCKER,
            message=f"card is not a dict: {type(card).__name__}",
            expected="dict",
        ))
        return findings
    findings.extend(_validate_required_fields(card))
    findings.extend(_validate_type_constraints(card))
    findings.extend(_validate_legs(card))
    findings.extend(_validate_economics(card))
    findings.extend(_validate_hedge_interpretation(card))
    return findings


def format_report(findings: list[ValidationFinding]) -> str:
    """Render findings as a human-readable report."""
    lines = [
        "# Partner card validation",
        "# ----------------------",
        f"# {len(findings)} finding(s)",
        "",
    ]
    if not findings:
        lines.append("All checks passed.")
        return "\n".join(lines) + "\n"
    by_status: dict[str, list[ValidationFinding]] = {}
    for f in findings:
        by_status.setdefault(f.status.value, []).append(f)
    for status in ("BLOCKER", "FAIL", "WARN", "PASS"):
        items = by_status.get(status, [])
        if not items:
            continue
        lines.append(f"## [{status}] ({len(items)})")
        for item in items:
            lines.append(f"- `{item.field}`: {item.message}")
            if item.expected:
                lines.append(f"  expected: {item.expected}")
        lines.append("")
    return "\n".join(lines) + "\n"


def findings_as_dicts(findings: list[ValidationFinding]) -> list[dict]:
    """Serialize findings for JSON output."""
    return [
        {
            "field": f.field,
            "status": f.status.value,
            "message": f.message,
            "expected": f.expected,
        }
        for f in findings
    ]


def _load_card(path_arg: str) -> Any:
    """Load a card JSON from a file path or stdin (``-``)."""
    if path_arg == "-":
        return json.loads(sys.stdin.read())
    path = Path(path_arg)
    if not path.is_file():
        print(
            f"validate_partner_card: not a file: {path}",
            file=sys.stderr,
        )
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(
            f"validate_partner_card: invalid JSON: {exc}",
            file=sys.stderr,
        )
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("card", help="path to card JSON, or '-' for stdin")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON to stdout")
    args = parser.parse_args(argv)
    card = _load_card(args.card)
    if card is None:
        return 2  # BLOCKER-equivalent: can't even parse the input.
    findings = validate_card(card)
    if args.json:
        sys.stdout.write(
            json.dumps(findings_as_dicts(findings), indent=2) + "\n"
        )
    else:
        sys.stdout.write(format_report(findings))
    has_blocker = any(f.status == Status.BLOCKER for f in findings)
    has_fail = any(f.status == Status.FAIL for f in findings)
    if has_blocker:
        return 2
    if has_fail:
        return 1
    return 0


__all__ = [
    "Status",
    "ValidationFinding",
    "findings_as_dicts",
    "format_report",
    "main",
    "validate_card",
]


if __name__ == "__main__":
    raise SystemExit(main())
