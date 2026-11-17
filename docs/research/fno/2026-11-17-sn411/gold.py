"""Shared Gold runner for SN418 / SN419 / SN421 - SN425 (sn403.one's wiring; Gold's files untouched). Learning only.

run(years, books, stress, wallet=GOLD_30K, stream_filter=None, leg=None, **vx) -> (days, log)
  days  ow's DAYLOG rows (day, wallet, net, gold trades, leg net); log  gw.LOG rows (Gold's full trade records)
  stream_filter(signal) -> bool keeps a signal (expert / side ablations); vx overrides Gold v5's config (C.V5)
summary(days, log) -> net, by year, months positive, worst month, worst day, refills, trades, per session
parity() asserts DEPLOYED 2023-26 at Rs 205 = Rs 8,50,882 / 883.
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-17-sn396"))
import sn403 as T  # noqa: E402

P, B, D, L, C, G, Q = T.P, T.B, T.D, T.L, T.C, T.G, T.Q
ow = P.ow
GOLD_30K = ow.GOLD_30K
DEPLOYED = ("N11", "R0.85")
NO_STAND_R = ("NO_STAND", "R0.85")
Y22, Y2326, Y2226 = ("2022",), ("2023", "2024", "2025", "2026"), ("2022", "2023", "2024", "2025", "2026")
_installed = {"done": False}
_orig_stream = P.stream


def install():
    if not _installed["done"]:
        Q.install()
        _installed["done"] = True


def run(years, books, stress, wallet=GOLD_30K, stream_filter=None, leg=None, **vx):
    install()

    def stream(year, book="N11"):
        xs = _orig_stream(year, book)
        return [x for x in xs if stream_filter(x)] if stream_filter else xs
    B.stream = stream
    D.DATASETS["2022"] = P.SN366L / "dataset-nifty-2022"
    D.load_year = G.load_2022
    for mod in (B, L, C):
        mod.YEARS = years
    C._YEARS = None
    L.VOLT.clear()
    C.panel = lambda r: {w: {} for w in r}
    old = C.V5["books"]
    C.V5["books"] = books
    T.Q.gw.LOG.clear()
    old_s = L.STRESS
    L.STRESS = stress
    try:
        v = {**C.V5, **vx}
        _row, days, _legs = ow.run_wallet(v, wallet, leg)
        log = list(T.Q.gw.LOG)
    finally:
        C.V5["books"] = old
        L.STRESS = old_s
        B.stream = _orig_stream
    return days, log, _legs


def summary(days, log):
    nets = [n for _d, _w, n, _t, _l in days]
    by_m, by_y = collections.defaultdict(float), collections.defaultdict(float)
    for d, _w, n, _t, _l in days:
        by_m[d[:7]] += n
        by_y[d[:4]] += n
    return {"net": round(sum(nets)), "by_year": {y: round(v) for y, v in sorted(by_y.items())}, "months_positive": sum(v > 0 for v in by_m.values()),
            "months": len(by_m), "worst_month": round(min(by_m.values())) if by_m else 0, "worst_day": round(min(nets)) if nets else 0,
            "refilled": round(sum(-n for n in nets if n < 0)), "trades": len(log), "sessions": len(days),
            "per_session": round(sum(nets) / max(1, len(days)), 1), "final_wallet": round(days[-1][1]) if days else None}


def parity():
    days, log, _ = run(Y2326, DEPLOYED, 205.0)
    net = summary(days, log)["net"]
    assert net in (850882, 850883), net
    return net
