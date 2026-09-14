"""Regenerate the Node isExecutionAllowed golden vector file.

Run from the python-engine directory:

    python tests/fixtures/regenerate_execution_allowed_golden.py

This regenerates a JSON snapshot of the Python
``market_calendar.execution_allowed`` helper over a fixed
date sweep. The Node ``isExecutionAllowed`` mirror under
``tests/unit/isExecutionAllowed.test.js`` must produce
identical output for every vector.

Two sweeps:
  1) Broad minute-granularity sweep -- catches every phase
     boundary at 15-minute granularity.
  2) Second-granularity pass -- hits the sub-windows
     CAS_LIMIT_ENTRY_ONLY (15:29:30 - 15:30 IST) and
     CAS_POST (15:40 - 16:00 IST) the broad sweep misses.

The dual-write contract is the same as the session-phase
golden: the regenerator writes to BOTH the python-engine
source-of-truth location and the Node test consumer
location, keeping the Node consumer in lockstep with the
Python source-of-truth.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from market_calendar import execution_allowed
from pytz import timezone


def _sweep_broad(ist, utc, vectors):
    """Minute-granularity sweep across weekday trading hours.
    Catches most phase boundaries.
    """
    for day in (7, 9, 10, 11, 13, 15, 17, 18, 21):
        # Sep 14 is Ganesh Chaturthi (holiday) -- avoid it.
        for hour in range(24):
            for minute in (0, 15, 30, 45):
                ist_dt = ist.localize(datetime(2026, 9, day, hour, minute))
                utc_dt = ist_dt.astimezone(utc)
                # Cash
                vectors.append({
                    "ist_utc": utc_dt.isoformat(),
                    "deriv": False,
                    "expected": execution_allowed(utc_dt),
                })
                # Cash + cas_eligible (RELIANCE-style)
                vectors.append({
                    "ist_utc": utc_dt.isoformat(),
                    "symbol": "RELIANCE",
                    "deriv": False,
                    "cas": True,
                    "expected": execution_allowed(
                        utc_dt, symbol="RELIANCE", cas_eligible=True
                    ),
                })
                # Derivative
                vectors.append({
                    "ist_utc": utc_dt.isoformat(),
                    "symbol": "FUTIDX",
                    "deriv": True,
                    "expected": execution_allowed(
                        utc_dt, symbol="FUTIDX", is_derivative=True
                    ),
                })
                # Derivative + allow_pre_market (to test the
                # pre-market override branch)
                vectors.append({
                    "ist_utc": utc_dt.isoformat(),
                    "symbol": "FUTIDX",
                    "deriv": True,
                    "allow_pre_market": True,
                    "expected": execution_allowed(
                        utc_dt, symbol="FUTIDX",
                        is_derivative=True, allow_pre_market=True,
                    ),
                })


def _sweep_second_granularity(ist, utc, vectors):
    """Second-level boundary pass. Hits sub-windows the
    broad sweep misses.

    Window boundaries per the live classifier:
      CAS_REFERENCE_PRICE_WINDOW  15:15 - 15:20
      CAS_ORDER_ENTRY             15:20 - 15:25
      CAS_LIMIT_ENTRY_ONLY        15:25 - 15:30
      CAS_MATCHING                15:30 - 15:35
      CAS_POST (cash)             15:35 - 16:00
      DERIVATIVES_CAS_ALIGNED     15:30 - 15:40
      PRE_MARKET                  09:00 - 09:15
      CONTINUOUS_TRADING          09:15 - 15:30 (cash) / 15:30 (deriv)
    """
    base_day = 10  # non-holiday Thursday
    boundary_instant_specs = [
        # CAS sub-window in-window instants
        (15, 16, 0),    # CAS_REFERENCE_PRICE_WINDOW
        (15, 19, 59),
        (15, 20, 0),    # CAS_ORDER_ENTRY (boundary)
        (15, 22, 0),
        (15, 24, 59),
        (15, 25, 0),    # CAS_LIMIT_ENTRY_ONLY (boundary)
        (15, 27, 0),
        (15, 29, 59),
        (15, 30, 0),    # CAS_MATCHING (cash) / DERIVATIVES_CAS_ALIGNED (deriv)
        (15, 32, 0),
        (15, 34, 59),
        (15, 35, 0),    # CAS_POST (cash) / DERIVATIVES_CAS_ALIGNED (deriv)
        (15, 39, 59),
        (15, 40, 0),    # DERIVATIVES_CAS_ALIGNED boundary / derivatives CLOSED after
        (15, 50, 0),
        (15, 59, 59),
        # PRE_MARKET window
        (9, 0, 0),
        (9, 14, 59),
        # Continuous trading open / close
        (9, 15, 0),
        (15, 14, 59),
        (15, 30, 0),
        (16, 0, 0),
        (16, 30, 0),
    ]
    for hh, mm, ss in boundary_instant_specs:
        ist_dt = ist.localize(datetime(2026, 9, base_day, hh, mm, ss))
        utc_dt = ist_dt.astimezone(utc)
        vectors.append({
            "ist_utc": utc_dt.isoformat(),
            "deriv": False,
            "expected": execution_allowed(utc_dt),
        })
        vectors.append({
            "ist_utc": utc_dt.isoformat(),
            "symbol": "RELIANCE",
            "deriv": False,
            "cas": True,
            "expected": execution_allowed(
                utc_dt, symbol="RELIANCE", cas_eligible=True
            ),
        })
        vectors.append({
            "ist_utc": utc_dt.isoformat(),
            "symbol": "FUTIDX",
            "deriv": True,
            "expected": execution_allowed(
                utc_dt, symbol="FUTIDX", is_derivative=True
            ),
        })


def main() -> int:
    ist = timezone("Asia/Kolkata")
    utc = timezone("UTC")
    vectors = []
    _sweep_broad(ist, utc, vectors)
    _sweep_second_granularity(ist, utc, vectors)
    payload = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(tz=utc).isoformat(),
        "python_helper": "market_calendar.execution_allowed",
        "vector_count": len(vectors),
        "vectors": vectors,
    }
    here = Path(__file__).resolve().parents[0] / "execution_allowed_golden.json"
    here.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    node_target = (
        Path(__file__).resolve().parents[3]
        / "node-gateway" / "server" / "tests" / "fixtures"
        / "execution_allowed_golden.json"
    )
    node_target.parent.mkdir(parents=True, exist_ok=True)
    node_target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    sys.stdout.write(
        f"wrote {len(vectors)} vectors to:\n  {here}\n  {node_target}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
