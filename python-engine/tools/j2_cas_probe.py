#!/usr/bin/env python3
"""[WORKFLOW-J.2 2026-09-13] Staging-only CAS-window broker-behaviour probe.

This CLI is the evidence-collection instrument for J.2 Part 2. It is
DESIGNED TO RUN ONLY IN STAGING (or any environment with a live Kite
feed). It does not import at Dev test time, so ``pytest`` does not
exercise it -- the prompt explicitly marks it as "documentation-only in
Dev".

Purpose:

The CAS-aware session classifier (J.1) labels a CAS-eligible
underlying's 15:15-15:35 window as a distinct session phase. Before
J.3 (or any future slice that uses the classifier to drive strategy)
can trust the broker-side of a CAS transaction, the operator must
verify what Kite actually returns during that window. This probe is
that verification.

It captures, for one or more operator-supplied underlyings, at one
or more operator-supplied timestamps, the following evidence:

  1. The classifier's verdict for (symbol, observation_at,
     is_derivative). This proves the Python side agrees with
     operator expectations.
  2. The quote fields Kite returned, sorted by category:
        * cash-specific (last_price, ohlc, volume, depth)
        * circuit limits (upper_circuit_limit, lower_circuit_limit)
        * CAS-window-specific keys (only present in CAS window --
          e.g. the Kite feed may carry different fields during 15:15-
          15:35 vs 09:15-15:14)
  3. The CAS eligibility verdict (``is_cas_eligible``) for each
     symbol under the operator-populated list.

The output is a single JSON document. The operator pipes the
document to ``jq`` for review and saves it under
``/data/research/cas_probe_<date>_<session>.json`` so J.3 (or the
parallel agent's correction plan) can consume the evidence.

Why a separate tool (not a pytest case):

  * Cas-window probes cannot run on demand -- Kite calls during
    15:15-15:35 only return CAS-window shapes; outside that window
    a probe tells us nothing about CAS behaviour.
  * The probe must run in staging (NOT Dev) per the prompt: Dev
    has no live broker.
  * pytest would not be able to assert any property (the broker
    response is non-deterministic in field shape across CAS sub-
    windows). The "test" is the operator's manual review of the
    captured JSON.

Usage (operator):

    # Probe RELIANCE and HDFCBANK at the current IST timestamp.
    ./winvenv/Scripts/python.exe python-engine/tools/j2_cas_probe.py \\
        --symbols "RELIANCE,HDFCBANK" \\
        --now

    # Probe at an explicit IST moment (multiple windows tested).
    ./winvenv/Scripts/python.exe python-engine/tools/j2_cas_probe.py \\
        --symbols "RELIANCE" \\
        --observation-at "2026-09-14T15:17:00+05:30" \\
        --output /data/research/cas_probe_15_17.json

    # Probe without a live broker (validate shape, NOT real quotes):
    ./winvenv/Scripts/python.exe python-engine/tools/j2_cas_probe.py \\
        --symbols "RELIANCE" \\
        --observation-at "2026-09-14T15:17:00+05:30" \\
        --dry-run

The ``--dry-run`` flag is the Dev-mode escape hatch. It deliberately
does NOT call the broker; it captures the classifier + eligibility
verdicts only, so Dev-tests / CI can sanity-check the wiring without
hitting Kite.

Exit codes:

  * 0 -- success (broker call returned, JSON printed, file written).
  * 1 -- broker error (Kite call failed; partial evidence printed;
         operator reviews).
  * 2 -- configuration error (symbols empty, observation_at
         unparseable; operator retries).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

# Add python-engine to sys.path so ``from market_calendar import ...``
# works whether the operator invokes the tool from python-engine/ or
# the repo root.
_TOOLS_DIR = Path(__file__).resolve().parent
_ENGINE_DIR = _TOOLS_DIR.parent
if str(_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINE_DIR))

from market_calendar import (  # noqa: E402  -- intentional sys.path insertion above
    classify_session_phase,
    is_cas_eligible,
)
from pytz import timezone as _tz  # noqa: E402

IST = _tz("Asia/Kolkata")


# --- Probe result types ------------------------------------------------

@dataclass(frozen=True)
class ProbeRow:
    symbol: str
    observation_at_iso: str
    observation_at_ist: str
    is_cas_eligible: bool
    classifier_phase: str
    quote: dict | None
    quote_error: str | None

    def to_dict(self) -> dict:
        out = {
            "symbol": self.symbol,
            "observation_at_utc": self.observation_at_iso,
            "observation_at_ist": self.observation_at_ist,
            "is_cas_eligible": self.is_cas_eligible,
            "classifier_phase": self.classifier_phase,
            "quote": self.quote,
        }
        if self.quote_error:
            out["quote_error"] = self.quote_error
        return out


# --- Schema / wiring ---------------------------------------------------

#: Schema version embedded in every captured document. Bump when
#: the row shape evolves. The receipt-review tool refuses documents
#: whose ``schema_version`` does not match.
SCHEMA_VERSION: int = 2

#: The JSON Schema for the captured document. Surfaced via
#: ``--schema-print`` so the operator (and the J.3 capture-review
#: tool) can validate against the same shape independent of Python.
#: Kept inline because the document is small and lives/evolves
#: with the tool.
CAPTURE_JSON_SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "j2_cas_probe capture document",
    "type": "object",
    "required": [
        "tool", "schema_version", "generated_at_utc", "dry_run",
        "observation_at_utc", "observation_at_ist",
        "symbol_count", "rows",
    ],
    "additionalProperties": False,
    "properties": {
        "tool": {"const": "j2_cas_probe"},
        "schema_version": {"const": SCHEMA_VERSION},
        "generated_at_utc": {"type": "string", "format": "date-time"},
        "dry_run": {"type": "boolean"},
        "observation_at_utc": {"type": "string", "format": "date-time"},
        "observation_at_ist": {"type": "string"},
        "symbol_count": {"type": "integer", "minimum": 0},
        "rows": {
            "type": "array",
            "items": {"$ref": "#/$defs/row"},
        },
    },
    "$defs": {
        "row": {
            "type": "object",
            "required": [
                "symbol", "observation_at_utc", "observation_at_ist",
                "is_cas_eligible", "classifier_phase", "quote",
            ],
            "additionalProperties": False,
            "properties": {
                "symbol": {"type": "string", "minLength": 1},
                "observation_at_utc": {"type": "string"},
                "observation_at_ist": {"type": "string"},
                "is_cas_eligible": {"type": "boolean"},
                "classifier_phase": {
                    "type": "string",
                    "enum": [
                        "CLOSED", "PRE_MARKET", "CONTINUOUS_TRADING",
                        "CAS_REFERENCE_PRICE_WINDOW",
                        "CAS_ORDER_ENTRY", "CAS_LIMIT_ENTRY_ONLY",
                        "CAS_MATCHING", "CAS_POST",
                        "DERIVATIVES_CAS_ALIGNED", "UNKNOWN",
                    ],
                },
                "quote": {
                    "oneOf": [
                        {"type": "null"},
                        {"type": "object"},
                    ],
                },
                "quote_error": {"type": "string"},
            },
        },
    },
}


# --- Probe logic -------------------------------------------------------

def _normalise_symbols(raw: str) -> tuple[str, ...]:
    """Strip whitespace, uppercase, drop empty tokens. Mirrors
    ``_normalised_cas_eligibility_set`` so the operator gets the same
    canonicalisation regardless of where a symbol was edited.
    """
    parts = (raw or "").split(",")
    cleaned = tuple(p.strip().upper() for p in parts if p and p.strip())
    if not cleaned:
        raise ValueError("at least one symbol is required")
    return cleaned


def _probe_one(
    symbol: str,
    observation_at: datetime,
    dry_run: bool,
    eligibility_override_csv: str | None = None,
) -> ProbeRow:
    """Probe one symbol at one observation moment. Returns a ProbeRow;
    never raises (brokers errors are captured in ``quote_error``).

    Resolves CAS eligibility ONCE per row (via the override CSV if
    provided, else via the settings-driven ``is_cas_eligible``) and
    passes the explicit boolean to the classifier. This keeps the
    override path authoritative end-to-end: the row-level
    ``is_cas_eligible`` and the classifier's CAS-aware phase both
    reflect the same eligibility verdict.
    """
    obs_utc = observation_at.astimezone(_tz("UTC"))
    obs_iso = obs_utc.isoformat()
    obs_ist = observation_at.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S %Z")

    cas = _resolve_eligibility(symbol, eligibility_override_csv)
    phase = classify_session_phase(
        obs_utc, symbol=symbol, is_derivative=False, cas_eligible=cas,
    )

    quote: dict | None = None
    quote_error: str | None = None

    if not dry_run:
        try:
            quote = asyncio.run(_fetch_quote_async(symbol))
        except Exception as exc:  # defensive: surface, do not raise
            quote_error = f"{type(exc).__name__}: {exc}"

    return ProbeRow(
        symbol=symbol,
        observation_at_iso=obs_iso,
        observation_at_ist=obs_ist,
        is_cas_eligible=cas,
        classifier_phase=phase,
        quote=quote,
        quote_error=quote_error,
    )


def _resolve_eligibility(symbol: str, override_csv: str | None) -> bool:
    """Decide whether ``symbol`` is CAS-eligible. When ``override_csv``
    is non-empty the override is authoritative for THIS call -- the
    normal ``config.settings.CAS_PHASE1_FNO_UNDERLYINGS`` lookup is
    bypassed. This makes staging captures reproducible without
    depending on shell env state across many invocations.

    Defensive: any non-string, None, or empty input returns False.
    """
    if not symbol or not isinstance(symbol, str):
        return False
    target = symbol.strip().upper()
    if not target:
        return False
    if override_csv is not None:
        # Override path: parse the override locally (no settings
        # import required). Same parser semantics as
        # ``market_calendar._normalised_cas_eligibility_set``: split
        # on comma, strip, uppercase, drop empties.
        parts = [p.strip().upper() for p in override_csv.split(",")]
        return target in {p for p in parts if p}
    # Default path: consult the lazy-imported config settings.
    from market_calendar import is_cas_eligible as _impl  # local rebind
    return _impl(symbol)


def _validate_document_against_schema(document: dict) -> list[str]:
    """Validate the captured document against the inline JSON Schema.
    Returns a list of human-readable error messages; empty list =
    pass. The validator is intentionally minimal: it confirms
    schema_version + required fields + the row enum. We deliberately
    do NOT bring in jsonschema as a hard dependency for a CLI
    tool -- the schema is small enough to validate by hand and an
    upgrade adds an installation requirement to staging.
    """
    errs: list[str] = []
    if document.get("tool") != "j2_cas_probe":
        errs.append(f"tool must be 'j2_cas_probe', got {document.get('tool')!r}")
    if document.get("schema_version") != SCHEMA_VERSION:
        errs.append(
            f"schema_version must be {SCHEMA_VERSION}, "
            f"got {document.get('schema_version')!r}"
        )
    for required in CAPTURE_JSON_SCHEMA["required"]:
        if required not in document:
            errs.append(f"missing required field {required!r}")
    valid_phases = set(CAPTURE_JSON_SCHEMA["$defs"]["row"]["properties"]["classifier_phase"]["enum"])
    rows = document.get("rows") or []
    if not isinstance(rows, list):
        errs.append("rows must be a list")
        return errs
    for i, row in enumerate(rows):
        phase = row.get("classifier_phase")
        if phase not in valid_phases:
            errs.append(f"row[{i}].classifier_phase {phase!r} not in documented enum")
        if not isinstance(row.get("is_cas_eligible"), bool):
            errs.append(f"row[{i}].is_cas_eligible must be bool")
        if not isinstance(row.get("symbol"), str) or not row["symbol"]:
            errs.append(f"row[{i}].symbol must be non-empty string")
        if row.get("quote") is not None and not isinstance(row.get("quote"), dict):
            errs.append(f"row[{i}].quote must be null or object")
    return errs


async def _fetch_quote_async(symbol: str) -> dict:
    """Resolve a token for ``symbol`` and fetch the quote via the
    repo's existing Kite wrapper. Deliberately raises on any error
    so the caller can capture the message for the operator's
    evidence review.

    Importing ``kite_client`` is gated inside the function (not at
    module load) so this CLI does not fail at import when Kite is
    absent (e.g. unit-test imports, sandbox, dry-run).
    """
    from kite_client import get_kite_client  # type: ignore  # noqa: WPS433
    from fno_instruments import (  # type: ignore  # noqa: WPS433
        resolve_cash_token,
    )

    token = resolve_cash_token(symbol)
    if token is None:
        raise RuntimeError(
            f"no cash token resolved for {symbol!r}; the F&O "
            f"instrument map is not populated in this environment"
        )
    client = get_kite_client()
    quotes = await client.get_quote([token])
    return _normalise_quote(quotes.get(token, {}))


def _normalise_quote(raw: dict) -> dict:
    """Project the raw Kite quote dict into a JSON-friendly shape
    with the keys grouped by category. The exact field names Kite
    returns evolve over time; this projection captures the fields
    J.2 is interested in (cash + circuit limits + CAS-window cues)
    AND falls back to the original dict for any unknown field so
    no evidence is silently dropped.
    """
    out: dict = {}
    out["last_price"] = raw.get("last_price")
    out["ohlc"] = raw.get("ohlc", {})
    out["volume"] = raw.get("volume")
    out["depth_available"] = bool(raw.get("depth"))
    if raw.get("depth"):
        out["depth_buy_levels"] = len(raw["depth"].get("buy", []))
        out["depth_sell_levels"] = len(raw["depth"].get("sell", []))
    out["upper_circuit_limit"] = raw.get("upper_circuit_limit")
    out["lower_circuit_limit"] = raw.get("lower_circuit_limit")
    # CAS-window cues (some Kite versions attach different keys
    # during 15:15-15:35 vs continuous trading). Surface any
    # unknown field with its actual name so the operator sees
    # exactly what the broker returned.
    known = {
        "last_price", "ohlc", "volume", "depth",
        "upper_circuit_limit", "lower_circuit_limit",
        "timestamp", "instrument_token", "tradable",
    }
    extra = {k: v for k, v in raw.items() if k not in known}
    if extra:
        out["broker_extra_fields"] = extra
    return out


def _now_ist() -> datetime:
    """Return the current IST-aware UTC datetime. Operator's
    ``--now`` shortcut; not exposed as a probe feature for tests.
    """
    from datetime import datetime as _dt_cls
    return _dt_cls.now(tz=IST)


def _parse_observation_at(raw: str) -> datetime:
    """Parse an ISO 8601 instant. **Strict**: requires a timezone
    offset (``+05:30`` or ``Z``). Naive timestamps are rejected with
    a clear ``ValueError`` because the operator's working timezone
    is ambiguous -- and we'd rather make the operator think about it
    than silently assume IST.

    Accepts ``Z`` (UTC) per ISO 8601:2019 and ``+HH:MM`` offsets
    for any zone (including IST ``+05:30``). Space separators
    (``"2026-09-14 15:17:00+05:30"``) are also accepted because
    ``datetime.fromisoformat`` handles them in modern Python, but
    we still flag the convention.
    """
    from datetime import datetime as _dt_cls
    if not raw or not isinstance(raw, str):
        raise ValueError(
            "observation_at must be a non-empty string"
        )
    # Refuse naive timestamps with a precise message: ambiguous
    # timezone is one of the most expensive bugs in scheduling
    # code. The operator must write the offset.
    candidate = raw.strip()
    if not candidate:
        raise ValueError("observation_at must be non-empty")
    looks_offseted = (
        candidate.endswith("Z")
        or "+" in candidate[10:]  # skip the date prefix
        or "-" in candidate[10:]
    )
    if not looks_offseted:
        raise ValueError(
            f"observation_at must carry a timezone offset "
            f"(e.g. '+05:30' or 'Z'); got naive timestamp "
            f"{candidate!r}"
        )
    parsed = _dt_cls.fromisoformat(candidate)
    if parsed.tzinfo is None:
        # Defensive double-check: if the offset character was
        # dropped at parse time we still want to refuse.
        raise ValueError(
            f"observation_at parsed to a naive datetime; "
            f"please supply an explicit offset"
        )
    return parsed


# --- CLI ---------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="j2_cas_probe",
        description=(
            "Staging-only CAS-window broker-behaviour probe. "
            "See docs/2026-09-13-j2-broker-behaviour-probe.md "
            "for the operator procedure."
        ),
    )
    p.add_argument(
        "--symbols",
        # Not argparse-required: we validate manually in main()
        # so that --schema-print can short-circuit before the
        # argparse error. For every other invocation, missing
        # --symbols returns exit 2 just like argparse's
        # required=True would have.
        default="",
        help=(
            "Comma-separated NSE symbols to probe, e.g. "
            "'RELIANCE,HDFCBANK'. Whitespace tolerated; "
            "uppercased defensively."
        ),
    )
    p.add_argument(
        "--observation-at",
        default=None,
        help=(
            "ISO 8601 instant to classify and probe. Examples: "
            "'2026-09-14T15:17:00+05:30' (IST) or "
            "'2026-09-14T09:47:00Z' (UTC). Naive timestamps "
            "default to IST."
        ),
    )
    p.add_argument(
        "--now",
        action="store_true",
        help=(
            "Use the current IST moment as the observation. "
            "Mutually exclusive with --observation-at."
        ),
    )
    p.add_argument(
        "--output",
        default="-",
        help=(
            "Path to write the JSON evidence document. "
            "Default '-' writes to stdout; pass an absolute path "
            "(e.g. /data/research/cas_probe.json) to write to "
            "disk. Parent directory must exist."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Do not call the broker. Capture classifier + "
            "eligibility verdicts only. Use this in Dev to "
            "sanity-check the wiring without hitting Kite."
        ),
    )
    p.add_argument(
        "--eligibility-list",
        default="",
        help=(
            "Override the CAS Phase 1 eligibility CSV for THIS "
            "call only. Same format as the env var "
            "CAS_PHASE1_FNO_UNDERLYINGS (comma-separated, "
            "whitespace-tolerated). When provided (even as an "
            "empty string explicitly) the override is "
            "authoritative; ``config.settings`` is bypassed. "
            "Use this in staging to make captures reproducible "
            "across invocations without depending on shell env "
            "state."
        ),
    )
    p.add_argument(
        "--require-eligible",
        action="store_true",
        help=(
            "Exit with code 1 if every probed symbol returns "
            "is_cas_eligible=False. Use this to catch the "
            "common staging mistake of forgetting to populate "
            "CAS_PHASE1_FNO_UNDERLYINGS. The exit code "
            "distinguishes \"eligibility list missing\" from "
            "the broader \"config error\" exit code 2."
        ),
    )
    p.add_argument(
        "--validate",
        action="store_true",
        help=(
            "Run the captured document through the inline "
            "schema check before printing. Any schema failure "
            "exits 1. Useful for CI / for verifying that a "
            "refactor of the probe did not change the row "
            "shape. The schema is also exposed via "
            "--schema-print for external validators."
        ),
    )
    p.add_argument(
        "--schema-print",
        action="store_true",
        help=(
            "Print the inline JSON Schema of the captured "
            "document to stdout and exit. Lets external tools "
            "(jq pipelines, dashboards, the J.3 capture-review "
            "tool) validate against the same shape independent "
            "of Python. Note: this flag short-circuits the rest "
            "of validation, so an operator can introspect the "
            "schema even without a valid symbol list."
        ),
    )
    return p


def main(argv: Iterable[str] | None = None) -> int:
    # --schema-print is a print-and-exit shortcut. Pre-parse with
    # argparse just to harvest this one flag so an operator can
    # inspect the schema without supplying a valid symbol list.
    pre = _build_arg_parser().parse_known_args(
        list(argv) if argv is not None else None
    )
    pre_args, _ = pre
    if getattr(pre_args, "schema_print", False):
        sys.stdout.write(json.dumps(CAPTURE_JSON_SCHEMA, indent=2) + "\n")
        return 0

    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)

    # We removed ``required=True`` from --symbols above so that
    # ``--schema-print`` can short-circuit. Re-validate manually.
    if not args.symbols or not args.symbols.strip():
        print("ERROR: --symbols is required (non-empty)", file=sys.stderr)
        return 2

    # Validate exactly one of --now / --observation-at.
    if bool(args.now) == bool(args.observation_at):
        print(
            "ERROR: pass exactly one of --now or --observation-at",
            file=sys.stderr,
        )
        return 2

    try:
        symbols = _normalise_symbols(args.symbols)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.now:
        observation_at = _now_ist()
    else:
        try:
            observation_at = _parse_observation_at(args.observation_at)
        except ValueError as exc:
            print(f"ERROR: unparseable --observation-at: {exc}", file=sys.stderr)
            return 2

    # The override CSV, when explicitly passed (argparse default
    # is ""), suppresses the settings-driven eligibility lookup.
    # We use a sentinel marker: ``--eligibility-list ANYTHING``
    # sets override_csv to ANYTHING; omitting the flag keeps
    # override_csv at None and defers to ``config.settings``.
    # To preserve the distinction explicitly, an empty-string
    # explicit value ALSO activates the override (authoritative
    # "nothing is eligible"). This is consistent with the
    # senior-dev rule that explicit beats implicit.
    override_active = "--eligibility-list" in sys.argv
    override_csv: str | None = args.eligibility_list if override_active else None

    rows = [
        _probe_one(sym, observation_at, dry_run=args.dry_run, eligibility_override_csv=override_csv)
        for sym in symbols
    ]
    document = {
        "tool": "j2_cas_probe",
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(tz=_tz("UTC")).isoformat(),
        "dry_run": bool(args.dry_run),
        "observation_at_utc": observation_at.astimezone(_tz("UTC")).isoformat(),
        "observation_at_ist": observation_at.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "symbol_count": len(rows),
        "eligibility_source": (
            "override_cli" if override_csv is not None else "settings"
        ),
        "rows": [r.to_dict() for r in rows],
    }

    # Optional schema validation. Failures here are exit 1, the
    # "broker-class error" bucket, because a schema-drift is
    # functionally equivalent to a stale response.
    if args.validate:
        schema_errs = _validate_document_against_schema(document)
        if schema_errs:
            print(
                "ERROR: schema validation failed:\n  - "
                + "\n  - ".join(schema_errs),
                file=sys.stderr,
            )
            return 1

    payload = json.dumps(document, indent=2, sort_keys=True, default=str)

    if args.output == "-":
        sys.stdout.write(payload + "\n")
    else:
        out_path = Path(args.output)
        if not out_path.parent.exists():
            print(
                f"ERROR: output directory does not exist: "
                f"{out_path.parent}",
                file=sys.stderr,
            )
            return 2
        out_path.write_text(payload + "\n", encoding="utf-8")
        sys.stdout.write(f"wrote {out_path}\n")

    # Eligibility-missing is a config-class signal that we want
    # to surface distinctly. Exit code 1 for "broker error" is
    # the closest bucket; operators see the stderr-style exit
    # code AND the row-level is_cas_eligible flag in the JSON.
    if args.require_eligible and not any(r.is_cas_eligible for r in rows):
        print(
            "ERROR: --require-eligible set but no probed symbol "
            "returned is_cas_eligible=True; check the eligibility "
            "list (env var or --eligibility-list)",
            file=sys.stderr,
        )
        return 1

    # Any row with a quote_error is a hard "broker failed" signal;
    # surface exit code so CI / operator notice. Classifier-only
    # evidence is still useful even when the broker errors.
    return 1 if any(r.quote_error for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
