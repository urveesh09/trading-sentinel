#!/usr/bin/env python3
"""[WORKFLOW-J.3 2026-09-13] Static review of j2_cas_probe captures.

A capture document is a JSON file produced by the staging-only
``tools/j2_cas_probe.py`` CLI against a real Kite session. This tool
is the deterministic half of J.3: it reads a captured JSON, runs the
six-point checklist, and exits 0 only when every check passes.

The captures themselves arrive operator-supplied (the J.3.0 + J.3.1
slice ships the scaffolding; J.3.x adds the captures). This tool is
the bridge between them.

Checks (six-point review checklist, per
docs/2026-09-13-j2-broker-behaviour-probe.md):

  1. Schema-level: the document matches CAPTURE_JSON_SCHEMA
     (delegated to the probe's validator; we re-import it so the
     review cannot drift from the probe).

  2. Eligibility: every probed symbol whose row carries
     ``is_cas_eligible=True`` is genuinely CAS-eligible per
     the configured list (the operator catches the
     "I forgot to populate CAS_PHASE1_FNO_UNDERLYINGS" mistake).

  3. Classifier phase: every CAS-eligible symbol's
     ``classifier_phase`` matches the IST window per the
     classifier constants (any mismatch is a sentinel for
     classifier drift or a typo'd observation_at).

  4. Quote present: when ``dry_run`` is False, every row's
     ``quote`` must be a non-null object. A null quote on a
     live capture means the broker call failed.

  5. Circuit limits: the quote carries ``upper_circuit_limit``
     AND ``lower_circuit_limit``, both non-zero (the +-3% CAS
     band per NSE/CMTR/72394).

  6. Broker extras: the quote carries at least one key in
     ``broker_extra_fields`` (CAS-window specific fields
     surfaced by Kite). An empty extras dict is a regression
     signal -- the broker may be stripping CAS-window keys.

Bonus checks (cross-window consistency):

  7. OHLC continuity across the pre-CAS / CAS reference window:
     ``ohlc.close`` at 15:10 IST should equal ``ohlc.close``
     at 15:17 IST for the same symbol on the same trading day
     (per NSE/CMTR/72394 -- the CAS reference price uses the
     pre-CAS trade VWAP). The review does this cross-file
     because each capture is one moment; the operator runs the
     review with ``--cross-window prior.json current.json`` to
     compare two captures.

Usage (operator):

    # Review a single capture.
    ./winvenv/Scripts/python.exe tools/j2_capture_review.py \\
        docs/j2_captures/2026-XX-XX_RELIANCE_15_17.json

    # Review with cross-window consistency check.
    ./winvenv/Scripts/python.exe tools/j2_capture_review.py \\
        docs/j2_captures/2026-XX-XX_RELIANCE_15_17.json \\
        --compare-with docs/j2_captures/2026-XX-XX_RELIANCE_15_10.json

Exit codes:

  * 0 -- every check passes; the capture is signed off.
  * 1 -- at least one check failed; the capture is rejected.
  * 2 -- the input file cannot be parsed or does not match the
         probe's schema. Operator retries with a corrected file.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

# Tools/ sits next to the probe. We import the probe's validator
# directly so the review cannot drift from the probe's contract.
_TOOLS_DIR = Path(__file__).resolve().parent
_ENGINE_DIR = _TOOLS_DIR.parent
if str(_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINE_DIR))

import j2_cas_probe as _probe  # noqa: E402


# ---- Result types ---------------------------------------------------

class Check:
    """A single checklist result. Pure data; serialisable."""

    def __init__(
        self,
        name: str,
        passed: bool,
        detail: str = "",
        evidence: dict | None = None,
    ) -> None:
        self.name = name
        self.passed = passed
        self.detail = detail
        self.evidence = evidence or {}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "evidence": self.evidence,
        }


# ---- Six-point checklist ------------------------------------------

def _check_schema(document: dict) -> Check:
    errs = _probe._validate_document_against_schema(document)
    return Check(
        name="schema",
        passed=not errs,
        detail=("" if not errs else "; ".join(errs)),
        evidence={
            "schema_version": document.get("schema_version"),
        },
    )


def _check_eligibility(document: dict, expected: set[str]) -> Check:
    """Every row where the operator-declared eligibility set says
    the symbol is eligible must match the row-level
    is_cas_eligible=True. A mismatch is hard fail.
    """
    failures: list[str] = []
    for row in document.get("rows", []):
        symbol = row.get("symbol", "")
        declared = symbol in expected
        actual = bool(row.get("is_cas_eligible"))
        if declared != actual:
            failures.append(
                f"row.symbol={symbol!r} declared={declared} "
                f"actual={actual} (mismatch)"
            )
    return Check(
        name="eligibility",
        passed=not failures,
        detail=("" if not failures else "; ".join(failures)),
        evidence={
            "expected_symbols": sorted(expected),
        },
    )


def _check_classifier_phase(document: dict) -> Check:
    """For each row, recompute the expected phase from
    (observation_at_utc, symbol, is_cas_eligible) and confirm the
    row's classifier_phase matches.
    """
    from market_calendar import (
        classify_session_phase,
        _ist_clock_minutes,
        CAS_OPEN_TIME, CAS_REFERENCE_PRICE_END,
        CAS_ORDER_ENTRY_END, CAS_LIMIT_ENTRY_ONLY_END,
        CAS_MATCHING_END, CAS_POST_CLOSE_END,
        MARKET_OPEN_TIME, MARKET_CLOSE_TIME,
        PRE_MARKET_OPEN_TIME,
        DERIVATIVES_CLOSE_TIME,
    )
    from datetime import datetime

    failures: list[str] = []
    for row in document.get("rows", []):
        try:
            obs = datetime.fromisoformat(row.get("observation_at_utc", ""))
        except ValueError as exc:
            failures.append(
                f"row.symbol={row.get('symbol')!r} "
                f"unparseable observation_at_utc: {exc}"
            )
            continue
        cas = bool(row.get("is_cas_eligible"))
        expected = classify_session_phase(
            obs, symbol=row.get("symbol"), cas_eligible=cas,
        )
        actual = row.get("classifier_phase")
        if expected != actual:
            failures.append(
                f"row.symbol={row.get('symbol')!r} expected={expected} "
                f"actual={actual} at {row.get('observation_at_utc')}"
            )
    return Check(
        name="classifier_phase",
        passed=not failures,
        detail=("" if not failures else "; ".join(failures)),
        evidence={"row_count": len(document.get("rows", []))},
    )


def _check_quote_present(document: dict) -> Check:
    """Live captures (``dry_run=False``) must carry a non-null
    quote object per row. A null quote is a hard broker-call
    failure signal. Dry-run documents legitimately have null
    quotes; we skip the check there.
    """
    if bool(document.get("dry_run")):
        return Check(
            name="quote_present",
            passed=True,
            detail="skipped: document is dry_run",
        )
    failures: list[str] = []
    for row in document.get("rows", []):
        q = row.get("quote")
        if q is None:
            failures.append(
                f"row.symbol={row.get('symbol')!r} quote is null"
                + (f" ({row.get('quote_error')})"
                   if row.get("quote_error") else "")
            )
    return Check(
        name="quote_present",
        passed=not failures,
        detail=("" if not failures else "; ".join(failures)),
    )


def _check_circuit_limits(document: dict) -> Check:
    """Per row, ``quote.upper_circuit_limit`` and
    ``quote.lower_circuit_limit`` are both present and non-zero.
    These are the +-3% CAS band per NSE/CMTR/72394. Dry-run
    documents have no quotes; the check is skipped there.
    """
    if bool(document.get("dry_run")):
        return Check(
            name="circuit_limits",
            passed=True,
            detail="skipped: document is dry_run",
        )
    failures: list[str] = []
    for row in document.get("rows", []):
        q = row.get("quote") or {}
        ucl = q.get("upper_circuit_limit")
        lcl = q.get("lower_circuit_limit")
        sym = row.get("symbol")
        if ucl in (None, 0):
            failures.append(f"row.symbol={sym!r} upper_circuit_limit missing or zero")
        if lcl in (None, 0):
            failures.append(f"row.symbol={sym!r} lower_circuit_limit missing or zero")
    return Check(
        name="circuit_limits",
        passed=not failures,
        detail=("" if not failures else "; ".join(failures)),
    )


def _check_broker_extras(document: dict) -> Check:
    """Per row, ``quote.broker_extra_fields`` is non-empty in CAS
    sub-windows. Kite typically attaches additional CAS-window
    keys during the CAS session; absence is a soft regression
    signal. Dry-run documents have no quotes; the check is
    skipped.
    """
    if bool(document.get("dry_run")):
        return Check(
            name="broker_extras",
            passed=True,
            detail="skipped: document is dry_run",
        )
    # CAS sub-windows the extras check is meaningful for.
    cas_only_phases = {
        "CAS_REFERENCE_PRICE_WINDOW", "CAS_ORDER_ENTRY",
        "CAS_LIMIT_ENTRY_ONLY", "CAS_MATCHING", "CAS_POST",
    }
    failures: list[str] = []
    for row in document.get("rows", []):
        phase = row.get("classifier_phase")
        if phase not in cas_only_phases:
            continue
        q = row.get("quote") or {}
        extras = q.get("broker_extra_fields")
        sym = row.get("symbol")
        if not isinstance(extras, dict) or not extras:
            failures.append(
                f"row.symbol={sym!r} CAS phase {phase!r} "
                f"has no broker_extra_fields (regression signal)"
            )
    if failures:
        return Check(
            name="broker_extras",
            passed=False,
            detail="; ".join(failures),
        )
    return Check(
        name="broker_extras",
        passed=True,
        detail=(
            "" if not cas_only_phases else
            "every CAS-window row carries broker_extra_fields"
        ),
    )


# ---- Cross-window continuity ---------------------------------------

def _check_ohlc_continuity(
    document_a: dict, document_b: dict,
) -> Check:
    """Cross-window check: for any symbol present in both
    documents, ``quote.ohlc.close`` must be equal (the CAS
    reference price is the pre-CAS VWAP, so the close at 15:10
    IST should match the close at 15:17 IST). Mismatch is a
    hard fail because it signals either (a) the broker calls
    were not back-to-back and a real move happened, or (b) the
    captures were tampered with.
    """
    rows_a = {r["symbol"]: r for r in document_a.get("rows", []) if "symbol" in r}
    rows_b = {r["symbol"]: r for r in document_b.get("rows", []) if "symbol" in r}
    failures: list[str] = []
    for symbol in sorted(rows_a.keys() & rows_b.keys()):
        ra = rows_a[symbol]
        rb = rows_b[symbol]
        qa = (ra.get("quote") or {}).get("ohlc") or {}
        qb = (rb.get("quote") or {}).get("ohlc") or {}
        ca = qa.get("close")
        cb = qb.get("close")
        if ca is None or cb is None:
            failures.append(
                f"symbol={symbol!r} missing ohlc.close in one of "
                f"({ra.get('observation_at_utc')}, "
                f"{rb.get('observation_at_utc')})"
            )
        elif ca != cb:
            failures.append(
                f"symbol={symbol!r} ohlc.close diverges: "
                f"{ca!r} vs {cb!r} "
                f"(at {ra.get('observation_at_utc')}, "
                f"{rb.get('observation_at_utc')})"
            )
    return Check(
        name="ohlc_continuity",
        passed=not failures,
        detail=("" if not failures else "; ".join(failures)),
        evidence={
            "document_a_symbols": sorted(rows_a.keys()),
            "document_b_symbols": sorted(rows_b.keys()),
        },
    )


# ---- CLI -----------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="j2_capture_review",
        description=(
            "Static review of j2_cas_probe captures. Runs the "
            "six-point checklist (schema, eligibility, classifier, "
            "quote, circuit, broker extras) and optionally a "
            "cross-window OHLC continuity check. Exits 0 only "
            "when every check passes."
        ),
    )
    p.add_argument(
        "capture",
        help="Path to the capture JSON document.",
    )
    p.add_argument(
        "--expected-eligibility",
        default=None,
        help=(
            "Override the eligibility set used for check 2 "
            "(eligibility). When omitted, the review reads "
            "config.settings.CAS_PHASE1_FNO_UNDERLYINGS via the "
            "lazy-imported ``is_cas_eligible``. Pass an explicit "
            "CSV (same format as the env var) to make the "
            "review deterministic across environments."
        ),
    )
    p.add_argument(
        "--compare-with",
        default=None,
        help=(
            "Path to a second capture JSON. When provided, an "
            "OHLC-continuity check is run between the two. The "
            "typical use is to compare a pre-CAS 15:10 IST "
            "capture against a 15:17 IST capture for the same "
            "symbol on the same trading day."
        ),
    )
    return p


def _expected_eligibility_from_csv(csv: str) -> set[str]:
    """The same parser the engine uses, but exposed here for
    tests. Empty CSV -> empty set (nothing eligible).
    """
    if not csv:
        return set()
    parts = [p.strip().upper() for p in csv.split(",")]
    return {p for p in parts if p}


def _expected_eligibility_from_settings() -> set[str]:
    """Read the operator-populated env var via the same lazy
    lookup that ``market_calendar.is_cas_eligible`` uses. Returns
    an empty set when config is unavailable (Dev).
    """
    try:
        from config import settings
    except Exception:
        return set()
    raw = getattr(settings, "CAS_PHASE1_FNO_UNDERLYINGS", "") or ""
    return _expected_eligibility_from_csv(raw)


def main(argv: Iterable[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    capture_path = Path(args.capture)
    if not capture_path.exists():
        print(f"ERROR: capture file not found: {capture_path}", file=sys.stderr)
        return 2

    try:
        document = json.loads(capture_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: capture is not valid JSON: {exc}", file=sys.stderr)
        return 2

    if not isinstance(document, dict):
        print("ERROR: capture root must be an object", file=sys.stderr)
        return 2

    # Resolve the expected eligibility set.
    if args.expected_eligibility is not None:
        expected = _expected_eligibility_from_csv(args.expected_eligibility)
    else:
        expected = _expected_eligibility_from_settings()

    checks: list[Check] = []
    checks.append(_check_schema(document))
    checks.append(_check_eligibility(document, expected))
    checks.append(_check_classifier_phase(document))
    checks.append(_check_quote_present(document))
    checks.append(_check_circuit_limits(document))
    checks.append(_check_broker_extras(document))

    # Cross-window continuity (bonus, opt-in).
    cross_check: Check | None = None
    if args.compare_with:
        compare_path = Path(args.compare_with)
        if not compare_path.exists():
            print(
                f"ERROR: compare-with file not found: {compare_path}",
                file=sys.stderr,
            )
            return 2
        try:
            other = json.loads(compare_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(
                f"ERROR: compare-with is not valid JSON: {exc}",
                file=sys.stderr,
            )
            return 2
        cross_check = _check_ohlc_continuity(document, other)

    document_report = {
        "tool": "j2_capture_review",
        "capture_path": str(capture_path),
        "expected_eligibility_source": (
            "cli" if args.expected_eligibility is not None else "settings"
        ),
        "check_count": len(checks) + (1 if cross_check else 0),
        "checks": [c.to_dict() for c in checks]
        + ([cross_check.to_dict()] if cross_check else []),
    }
    all_passed = all(c.passed for c in checks) and (
        cross_check is None or cross_check.passed
    )
    document_report["overall_passed"] = all_passed

    sys.stdout.write(json.dumps(document_report, indent=2, sort_keys=True) + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
