"""SN07 - the REAL N11 book with its big-money rules switched off, replayed by the shipped engine (research only).

N11 refuses some of its own signals for reasons that protect a Rs 2.5 lakh pool: the open-premium cap, the daily /
weekly / monthly kill switches and the 15% drawdown halt, the stand-aside after a losing paper record, three trades
a day, two open positions. A Rs 15,000 one-lot wallet with the owner's day limit and refills needs none of them.
This script builds N11 variants with those rules off (settings per book through the chain's ``cfg`` hook) and
replays them with N11's own lab chain. Everything is written under this study's _local.

    N08_YEAR=<2023|2024|2025|2026> <venv python> sn07_lab.py --jobs 4
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
N11 = HERE.parents[1] / "simulation" / "2026-11-02-fno-n11"
sys.path.insert(0, str(N11))

import n11_lab as L  # noqa: E402

LOCAL = HERE / "_local"
for _mod in (L, L.U, L.B, L.T, L.M, L.X):
    _mod.LOCAL = LOCAL
L.Y.EVALS = LOCAL / "evals"
L.Y.EVALS.mkdir(parents=True, exist_ok=True)
(LOCAL / "decisions").mkdir(parents=True, exist_ok=True)

BRAKES_OFF = {"FNO_ADAPTIVE_RISK_ENABLED": False, "FNO_DAILY_KILL_PCT": 9.0, "FNO_WEEKLY_KILL_PCT": 9.0,
              "FNO_MONTHLY_KILL_PCT": 9.0, "FNO_MAX_DRAWDOWN_PCT": 0.999, "FNO_MAX_CONSECUTIVE_LOSSES": 1_000_000,
              "FNO_TWO_STRIKE_LOSSES": 1_000_000, "FNO_MAX_OPEN_PREMIUM_PCT": 10.0}


def books() -> dict:
    out = {"N11": L.n11_book()}
    s1 = L.n11_book("SN07|S1", stand=None, stand_ratio=None)
    s1["cfg"] = {**s1.get("cfg", {}), **BRAKES_OFF}
    out["S1"] = s1
    s2 = copy.deepcopy(s1)
    s2["label"] = "N11|SN07|S2"
    s2["cfg"] = {**s2["cfg"], "FNO_MAX_TRADES_PER_DAY": 6}
    out["S2"] = s2
    s3 = copy.deepcopy(s2)
    s3["label"] = "N11|SN07|S3"
    s3["cfg"] = {**s3["cfg"], "FNO_MAX_CONCURRENT": 3}
    out["S3"] = s3
    return out


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--jobs", type=int, default=4)
    a = cli.parse_args()
    bk = books()
    L.Z.N.run_books(bk, a.jobs)
    keys = {n: L.Y.task_key(b, "year", L.B.C.WINDOW) for n, b in bk.items()}
    (LOCAL / f"keys-{L.YEAR}.json").write_text(json.dumps(keys, indent=1), encoding="utf-8")
    print("DONE", L.YEAR, keys, flush=True)
