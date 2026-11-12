"""SN08 - N11 with its QUALITY refusals relaxed, replayed by the shipped engine through N11's lab chain (research only).

N11 turns most of its signals away with three quality rules (2025 funnel, per bar): stretched entries (310), the
low-ADX-day direction rule (puts only, 325) and the low-day 14:00 cutoff (97). SN08 relaxes them:
  SN08_PATCH unset      LATE (no 14:00 cutoff), WITH_TREND (low-day calls in a daily uptrend), LATE+WITH_TREND
  SN08_PATCH=both       BOTH (low-day trades on either side), BOTH+LATE
  SN08_PATCH=nostretch  NOSTRETCH (no stretched-entry skip), NOSTRETCH+LATE
  SN08_PATCH=all        ALL (both sides, no stretch skip, no cutoff)
Patches are made at module level (Windows workers re-import this script) and every patched book has its own label,
so its replay key differs from the unpatched book's.

    N08_YEAR=<year> [SN08_PATCH=...] <venv python> sn08_lab.py --jobs 4
"""
from __future__ import annotations

import argparse
import copy
import json
import os
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

PATCH = os.environ.get("SN08_PATCH", "")
_rules = sys.modules["n08_rules"]
_n08 = sys.modules["n08_lab"]
if PATCH in ("both", "all"):
    _rules.low_day_direction_allowed = lambda mode, direction, di_up: True
if PATCH in ("nostretch", "all"):
    _n08.X.S.stretch_at = lambda frame, now, direction: None


def book(label: str, **n08) -> dict:
    b = L.n11_book()
    b = copy.deepcopy(b)
    b["label"] = f"N11|SN08|{label}"
    for k, v in n08.items():
        if v is None:
            b["n08"].pop(k, None) if k != "low_last_minute" else b["n08"].__setitem__(k, None)
        else:
            b["n08"][k] = v
    return b


def books() -> dict:
    if PATCH == "":
        return {"LATE": book("LATE", low_last_minute=None), "WITH_TREND": book("WITH_TREND", low_direction="WITH_TREND"),
                "LATE+WITH_TREND": book("LATE+WITH_TREND", low_last_minute=None, low_direction="WITH_TREND")}
    if PATCH == "both":
        return {"BOTH": book("BOTH"), "BOTH+LATE": book("BOTH+LATE", low_last_minute=None)}
    if PATCH == "nostretch":
        return {"NOSTRETCH": book("NOSTRETCH"), "NOSTRETCH+LATE": book("NOSTRETCH+LATE", low_last_minute=None)}
    if PATCH == "all":
        return {"ALL": book("ALL", low_last_minute=None)}
    raise SystemExit(f"unknown SN08_PATCH {PATCH}")


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--jobs", type=int, default=4)
    a = cli.parse_args()
    bk = books()
    L.Z.N.run_books(bk, a.jobs)
    keys = {n: L.Y.task_key(b, "year", L.B.C.WINDOW) for n, b in bk.items()}
    path = LOCAL / f"keys-{L.YEAR}.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    path.write_text(json.dumps({**old, **keys}, indent=1), encoding="utf-8")
    print("DONE", L.YEAR, PATCH or "-", list(keys), flush=True)
