"""Regenerate the Node sessionPhase golden vector file.

Run from the repo root:

    python tests/fixtures/regenerate_session_phase_golden.py

This is an audit-grade reproducibility surface -- the golden file
is a JSON snapshot of the Python classifier's output over a fixed
date sweep, so any change to the Python classifier is visible by
diffing the golden.

The Node ``sessionPhase`` mirror under ``tests/unit/sessionPhase.test.js``
must produce identical output for every vector. A divergence is a
category-1 invariant failure: J.6 is broken.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from market_calendar import (
    NSE_HOLIDAYS_ISO,
    classify_session_phase,
)
from pytz import timezone


def _sweep_broad(ist, utc, vectors):
    """Wide minute-granularity sweep. Catches most phase
    boundaries (9:14/9:15, 9:15/9:16, 15:14/15:15, etc.).
    """
    for day in range(7, 22, 2):  # mid-September spread
        for hour in range(24):
            for minute in (0, 15, 30, 45):
                ist_dt = ist.localize(datetime(2026, 9, day, hour, minute))
                utc_dt = ist_dt.astimezone(utc)
                # Default -- no symbol, no derivative flag.
                vectors.append({
                    "ist_utc": utc_dt.isoformat(),
                    "symbol": None,
                    "deriv": False,
                    "expected": classify_session_phase(utc_dt),
                })
                # CAS-eligible cash.
                vectors.append({
                    "ist_utc": utc_dt.isoformat(),
                    "symbol": "RELIANCE",
                    "deriv": False,
                    "cas": True,
                    "expected": classify_session_phase(
                        utc_dt, symbol="RELIANCE", cas_eligible=True
                    ),
                })
                # Derivative.
                vectors.append({
                    "ist_utc": utc_dt.isoformat(),
                    "symbol": "FUTIDX",
                    "deriv": True,
                    "expected": classify_session_phase(
                        utc_dt, symbol="FUTIDX", is_derivative=True
                    ),
                })


def _sweep_second_granularity(ist, utc, vectors):
    """Focused second-level boundary pass. CAS_LIMIT_ENTRY_ONLY
    only fires at 15:29:30 - 15:30 IST; CAS_POST only fires for
    derivatives at 15:40 - 16:00 IST. Both are second-granularity
    windows the 15-minute sweep misses. This pass exercises
    every known sub-window with at least one vector inside it.
    """
    # Pin a non-holiday trading day: 2026-09-10 (Thursday).
    # Sep 14 is Ganesh Chaturthi (holiday), so we avoid it.
    base_day = 10
    # Define the (hour, minute, second) boundary points that
    # the broad sweep cannot reach.
    boundary_instant_specs = [
        # CAS_LIMIT_ENTRY_ONLY window: 15:29:30 - 15:29:59
        (15, 29, 31),
        (15, 29, 45),
        (15, 29, 59),
        # CAS_ORDER_ENTRY window: 15:20 - 15:29:30 (the broad
        # 15-minute sweep only hits 15:15 and 15:30, missing the
        # entire CAS_ORDER_ENTRY window).
        (15, 20, 0),
        (15, 20, 1),
        (15, 25, 0),
        (15, 29, 0),
        # CAS_MATCHING window: 15:30 - 15:40 (already covered
        # at minute granularity, but we add an in-window
        # second for tightness)
        (15, 30, 0),
        (15, 30, 1),
        # CAS_POST window for derivatives: 15:40 - 16:00
        (15, 40, 0),
        (15, 40, 1),
        (15, 50, 0),
        (15, 59, 59),
        # PRE_MARKET: 9:00 - 9:14
        (9, 0, 0),
        (9, 14, 59),
        # Continuous open: 9:15
        (9, 15, 0),
        # Derivatives close: 15:40
        (15, 40, 0),
    ]
    for hh, mm, ss in boundary_instant_specs:
        ist_dt = ist.localize(
            datetime(2026, 9, base_day, hh, mm, ss)
        )
        utc_dt = ist_dt.astimezone(utc)
        # Default
        vectors.append({
            "ist_utc": utc_dt.isoformat(),
            "symbol": None,
            "deriv": False,
            "expected": classify_session_phase(utc_dt),
        })
        # CAS-eligible cash
        vectors.append({
            "ist_utc": utc_dt.isoformat(),
            "symbol": "RELIANCE",
            "deriv": False,
            "cas": True,
            "expected": classify_session_phase(
                utc_dt, symbol="RELIANCE", cas_eligible=True
            ),
        })
        # Derivative
        vectors.append({
            "ist_utc": utc_dt.isoformat(),
            "symbol": "FUTIDX",
            "deriv": True,
            "expected": classify_session_phase(
                utc_dt, symbol="FUTIDX", is_derivative=True
            ),
        })


def main() -> int:
    ist = timezone("Asia/Kolkata")
    utc = timezone("UTC")
    vectors = []
    # Sweep mid-September 2026 across every weekday, every
    # 15-minute boundary, and three option combinations. This
    # is the canonical sweep size: covers boundary edges
    # (9:14 vs 9:15, 15:14 vs 15:15, 15:29 vs 15:30, etc.)
    # exhaustively. The second-granularity pass adds the
    # sub-minute sub-windows (CAS_LIMIT_ENTRY_ONLY,
    # CAS_POST) the broad sweep cannot reach.
    _sweep_broad(ist, utc, vectors)
    _sweep_second_granularity(ist, utc, vectors)
    payload = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(tz=utc).isoformat(),
        "python_classifier": "market_calendar.classify_session_phase",
        "vector_count": len(vectors),
        "vectors": vectors,
    }
    # The regenerate script writes the golden to BOTH the
    # source-of-truth location (python-engine/tests/fixtures) and
    # the Node test consumer location (node-gateway/.../tests/
    # fixtures). Keeping both in lockstep ensures the Node
    # sessionPhase.test.js assertion stays accurate whenever
    # someone regenerates.
    here = Path(__file__).resolve().parents[0] / "session_phase_golden.json"
    here.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    node_target = (
        Path(__file__).resolve().parents[3]
        / "node-gateway" / "server" / "tests" / "fixtures"
        / "session_phase_golden.json"
    )
    if node_target.parent.is_dir() or node_target.parent.exists():
        node_target.parent.mkdir(parents=True, exist_ok=True)
        node_target.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        sys.stdout.write(
            f"wrote {len(vectors)} vectors to:\n"
            f"  {here}\n"
            f"  {node_target}\n"
        )
    else:
        sys.stdout.write(
            f"wrote {len(vectors)} vectors to:\n  {here}\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
