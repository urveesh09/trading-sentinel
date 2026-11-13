"""Phase C helpers (SN116-SN120): imports phase A (pa, sn110's day-logging player) and phase B (pb); edits nothing."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn111"))
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn101"))
import pb  # noqa: E402
import pa  # noqa: E402
import sn110  # noqa: E402

C, M, L = pa.C, pa.M, pa.C.L


def gold_days(v, w):
    """(panel row, [(day, net), ...]) for one wallet tuple, through SN110's day-logging player (v5 parity proven)."""
    return sn110.run_wallet(v, w)


def series_stats(day_nets):
    x = np.array([n for _d, n in day_nets], dtype=float)
    if not len(x):
        return {"max_drawdown": 0, "worst_day": 0}
    cum = np.cumsum(x)
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:] - cum).max())
    return {"max_drawdown": round(dd), "worst_day": round(float(x.min()))}


def merge(*day_lists):
    out = {}
    for dl in day_lists:
        for d, n in dl:
            out[d] = out.get(d, 0.0) + n
    return sorted(out.items())


def by_year(day_nets):
    return [round(sum(n for d, n in day_nets if d[:4] == y)) for y in C.YEARS]
