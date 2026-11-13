"""SN77 - sell time value, defined risk, on the days SN Gold sits out (research only).

SN76: Gold has no setup on 609 of 742 sessions, mostly low-ADX days that grind up or go nowhere (N11 then buys only
puts). SN02-B: BUYING a call and a put lost on almost every setting there, i.e. option time value is overpriced
intraday on such days. SN77 takes the other side with capped risk: iron condors, bull-put and bear-call spreads,
sold at the bid and covered at the ask on the sealed 1-minute candles (bid/ask = the year datasets' model), charges
per leg (shipped model) + a stress per leg-lot. Days: chosen before the open (yesterday's ADX < 30, optionally
with low volatility). Exit at 15:00, a profit target (share of the credit kept), a stop (loss as a multiple of the
credit), or the 20% day limit. Margin proxy: the structure's maximum loss must fit the wallet (Zerodha's real hedged
margin must be checked before any real use). Leave one year out.
"""
from __future__ import annotations

import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
for p in ("2026-11-12-sn01", "2026-11-12-sn03", "2026-11-13-sn51"):
    sys.path.insert(0, str(HERE.parent / p))
import sn01_data as D  # noqa: E402
import sn01_sim as M  # noqa: E402
from sn03_run import loyo  # noqa: E402

YEARS = ("2023", "2024", "2025", "2026")
EXIT = 345        # 15:00
LOT = 65


def legs_for(kind, atm, k, w):
    if kind == "IC":
        return [(atm + k * 50, "CE", -1), (atm + (k + w) * 50, "CE", +1), (atm - k * 50, "PE", -1), (atm - (k + w) * 50, "PE", +1)]
    if kind == "BPS":
        return [(atm - k * 50, "PE", -1), (atm - (k + w) * 50, "PE", +1)]
    if kind == "BCS":
        return [(atm + k * 50, "CE", -1), (atm + (k + w) * 50, "CE", +1)]
    raise ValueError(kind)


def series(S, strike, opt):
    a = S.s["options"].get((strike, opt))
    if a is None:
        return None
    close = D._ffill(a[3].astype(float).copy())
    return close


def _ask(x):
    x = np.asarray(x, dtype=float)
    half = np.select([x < 50, x < 100, x < 150, x < 200, x < 300, x < 450], [0.05, 0.10, 0.15, 0.225, 0.30, 0.40],
                     np.maximum(0.40, np.round(0.002 * x / 0.05) * 0.05 / 2))
    return np.maximum(M._bid_vec(x) + 0.05, np.ceil((x + half) / 0.05 - 1e-9) * 0.05)


def prepare(S, kind, k, w, i):
    """The structure's P&L path from minute i (before charges): (pnl, credit, max_loss, legs) or None."""
    c = S.F["c"]
    atm = int(round(c[i] / 50) * 50)
    paths = []
    for strike, opt, side in legs_for(kind, atm, k, w):
        p = series(S, strike, opt)
        if p is None or not np.isfinite(p[i]):
            return None
        paths.append((p, side))
    open_px = [(float(M._bid_vec(np.array([p[i]]))[0]) if s < 0 else float(_ask([p[i]])[0]), s) for p, s in paths]
    credit = sum(-s * px for px, s in open_px) * LOT
    if credit <= 0:
        return None
    seg = slice(i + 1, EXIT + 1)
    closes = [(_ask(p[seg]) if s < 0 else M._bid_vec(p[seg])) for p, s in paths]
    cost = sum((cl if s < 0 else -cl) for cl, (_p, s) in zip(closes, paths)) * LOT
    return credit - cost, credit, w * 50 * LOT - credit, open_px, closes


def finish(prep, tp, sl, stress, wallet):
    pnl, credit, max_loss, open_px, closes = prep
    if max_loss > wallet:
        return None
    hit = len(pnl) - 1
    for cond in ((pnl >= tp * credit) if tp else None, (pnl <= -sl * credit) if sl else None, pnl <= -0.2 * wallet):
        if cond is not None:
            t = np.flatnonzero(cond)
            if len(t):
                hit = min(hit, int(t[0]))
    fees = 0.0
    for (px0, s), cl in zip(open_px, closes):
        px1 = float(cl[hit])
        buy, sell = (px1, px0) if s < 0 else (px0, px1)
        fees += M.charges(buy, sell, LOT)
    return float(pnl[hit]) - fees - stress * len(open_px)


def grid():
    out = []
    for kind, k, w in [("IC", 1, 1), ("IC", 2, 1), ("IC", 2, 2), ("IC", 3, 1), ("BPS", 1, 1), ("BPS", 2, 2), ("BCS", 1, 1), ("BCS", 2, 2)]:
        for entry, tp, sl, gate in itertools.product((15, 45, 75, 105), (0.0, 0.5, 0.7), (0.0, 1.0, 2.0), ("all", "adx<30", "adx<30&quiet")):
            out.append({"kind": kind, "k": k, "w": w, "entry": entry, "tp": tp, "sl": sl, "gate": gate})
    return out


def gate_ok(day, gate, adx, volt):
    if gate == "all":
        return True
    rd = adx.get(day)
    if rd is None or rd["adx"] >= 30:
        return False
    if gate == "adx<30&quiet":
        a, med = volt.get(day, (None, None))
        return a is not None and a < med
    return True


if __name__ == "__main__":
    import lab as L
    adx = json.loads((HERE.parent / "2026-11-12-sn06" / "_local" / "daily.json").read_text(encoding="utf-8"))
    volt = L.vol_table()
    stress = float(sys.argv[1]) if len(sys.argv) > 1 else 100.0
    sessions = {y: [M.Session(s) for s in D.load_year(y)["sessions"].values()] for y in YEARS}
    table = {}
    STRUCT = [("IC", 1, 1), ("IC", 2, 1), ("IC", 2, 2), ("IC", 3, 1), ("BPS", 1, 1), ("BPS", 2, 2), ("BCS", 1, 1), ("BCS", 2, 2)]
    for kind, k, w in STRUCT:
        for entry in (15, 45, 75, 105):
            preps = {y: [(S.day, prepare(S, kind, k, w, entry)) for S in sessions[y]] for y in YEARS}
            for tp, sl, gate in itertools.product((0.0, 0.5, 0.7), (0.0, 1.0, 2.0), ("all", "adx<30", "adx<30&quiet")):
                cfg = {"kind": kind, "k": k, "w": w, "entry": entry, "tp": tp, "sl": sl, "gate": gate}
                per = {}
                for y in YEARS:
                    nets = []
                    for day, pr in preps[y]:
                        x = finish(pr, tp, sl, stress, 30000.0) if (pr is not None and gate_ok(day, gate, adx, volt)) else None
                        nets.append(x if x is not None else 0.0)
                    per[y] = {"net": round(sum(nets)), "green": sum(v > 0 for v in nets), "red": sum(v < 0 for v in nets),
                              "none": sum(v == 0 for v in nets), "worst": round(min(nets)), "refilled": round(sum(-v for v in nets if v < 0))}
                table[json.dumps(cfg, sort_keys=True)] = per
    pos_all = [k for k, v in table.items() if all(v[y]["net"] > 0 for y in YEARS)]
    print("configs", len(table), "positive in every year:", len(pos_all), flush=True)
    top = sorted(table.items(), key=lambda kv: -min(kv[1][y]["net"] for y in YEARS))[:8]
    for k, v in top:
        print(k, [v[y]["net"] for y in YEARS], "won/lost", sum(v[y]["green"] for y in YEARS), sum(v[y]["red"] for y in YEARS), "worst", min(v[y]["worst"] for y in YEARS))
    Lh = loyo(table, "profit")
    print("LOYO held out", {y: (Lh[y]["net"]) for y in YEARS}, "sum", Lh["sum"]["net"], "picks", [json.loads(Lh[y]["pick"])["kind"] + json.loads(Lh[y]["pick"])["gate"] for y in YEARS])
    (HERE / f"results-{int(stress)}.json").write_text(json.dumps({"table": table, "loyo": Lh}, indent=1), encoding="utf-8")
