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
) -> ProbeRow:
    """Probe one symbol at one observation moment. Returns a ProbeRow;
    never raises (brokers errors are captured in ``quote_error``).
    """
    obs_utc = observation_at.astimezone(_tz("UTC"))
    obs_iso = obs_utc.isoformat()
    obs_ist = observation_at.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S %Z")

    cas = is_cas_eligible(symbol)
    phase = classify_session_phase(
        obs_utc, symbol=symbol, is_derivative=False,
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
    """Parse an ISO 8601 instant. Tolerates the operator's preference
    for either ``+05:30`` (IST) or ``Z`` (UTC).
    """
    from datetime import datetime as _dt_cls
    parsed = _dt_cls.fromisoformat(raw)
    if parsed.tzinfo is None:
        # Naive timestamps are interpreted as IST (the operator's
        # working timezone) per the runbook.
        parsed = IST.localize(parsed)
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
        required=True,
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
    return p


def main(argv: Iterable[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)

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

    rows = [
        _probe_one(sym, observation_at, dry_run=args.dry_run)
        for sym in symbols
    ]
    document = {
        "tool": "j2_cas_probe",
        "schema_version": 1,
        "generated_at_utc": datetime.now(tz=_tz("UTC")).isoformat(),
        "dry_run": bool(args.dry_run),
        "observation_at_utc": observation_at.astimezone(_tz("UTC")).isoformat(),
        "observation_at_ist": observation_at.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "symbol_count": len(rows),
        "rows": [r.to_dict() for r in rows],
    }
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

    # Any row with a quote_error is a hard "broker failed" signal;
    # surface exit code so CI / operator notice. Classifier-only
    # evidence is still useful even when the broker errors.
    return 1 if any(r.quote_error for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
