"""SN405: one wallet by information time (PLAN.md section 1, frozen at 00693405; details fixed here before any SN405
number). Not a verdict: no challenger has passed its own paper gate.

(a) Gold-only coverage, DEPLOYED Gold v5 from Rs 30k, 2022 - 2026 path, Rs 205 / 400 (sn403's wiring, Gold untouched):
    market sessions, sessions with a Gold trade, empty sessions, net per market session, share of sessions >= Rs 750,
    share of sessions > 0, the longest stretch (sessions) from an equity high to the next new high, and the net an
    empty session would need to average for Rs 500 / Rs 750 per market session.
(b) Development illustration of the shared wallet (Dec 8, 2025 - Oct 28, 2026, the HONEST fw9 rows: CHEAP auction
    sessions, 2-ITM then 1-ITM at the 09:15 close, 60 minutes, Rs 3,000 stop): Gold keeps priority. If Gold enters before
    the opener's exit and the wallet minus the opener's debit cannot pay Gold's entry debit (ask0 x 65 x lots0 + charges),
    the opener is closed at Gold's entry minute at the model bid (pre-emption). The 20% shared day stop is counted, not
    re-simulated: days where the opener's loss plus Gold's loss would pass 20% of the wallet are listed. Reported: opener
    trades, conflicts (Gold entry before 10:16), pre-emptions, incremental net, per market session, positive opener days.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import op  # noqa: E402
import sn403 as T  # noqa: E402

P, B, D, L, C, G, Q = T.P, T.B, T.D, T.L, T.C, T.G, T.Q
gl = op.gl
OUT = HERE / "results-sn405.json"
YEARS = ("2022", "2023", "2024", "2025", "2026")


def gold(stress):
    B.stream = P.stream
    D.DATASETS["2022"] = P.SN366L / "dataset-nifty-2022"
    D.load_year = G.load_2022
    for mod in (B, L, C):
        mod.YEARS = YEARS
    C._YEARS = None
    L.VOLT.clear()
    C.panel = lambda r: {w: {} for w in r}
    old = C.V5["books"]
    C.V5["books"] = ("N11", "R0.85")
    try:
        _row, days, log = Q.run(stress)
    finally:
        C.V5["books"] = old
    return days, log


def coverage(days, log):
    traded = collections.Counter(x["day"] for x in log)
    nets = [n for _d, _w, n, _t, _l in days]
    n = len(days)
    tot = float(sum(nets))
    empty = sum(1 for d, *_ in days if traded.get(d, 0) == 0)
    eq, hi, run, longest = 0.0, 0.0, 0, 0
    for x in nets:
        eq += x
        if eq > hi:
            hi, run = eq, 0
        else:
            run += 1
            longest = max(longest, run)
    out = {"market_sessions": n, "gold_sessions": n - empty, "empty_sessions": empty, "net": round(tot), "net_per_market_session": round(tot / n, 1),
           "share_sessions_ge_750": round(float(np.mean([x >= 750 for x in nets])), 3), "share_sessions_positive": round(float(np.mean([x > 0 for x in nets])), 3),
           "longest_sessions_to_new_high": longest}
    for target in (500, 750):
        need = target * n - tot
        out[f"needed_per_empty_session_for_{target}"] = round(need / empty, 1) if empty else None
    return out


def main():
    if OUT.exists():
        raise SystemExit("SN405 is run once")
    Q.install()
    res = {}
    gold_days = {}
    for st in (205.0, 400.0):
        days, log = gold(st)
        res[f"coverage @{int(st)}"] = coverage(days, log)
        gold_days[st] = (days, log)
        print(int(st), json.dumps(res[f"coverage @{int(st)}"]), flush=True)
    smp, _d, au = op.setup()
    jm = op.jumps(smp, "HONEST")
    lab = op.labels(jm, True)
    for st in (205.0, 400.0):
        days, log = gold_days[st]
        wallet = {d: w for d, w, *_ in days}
        gnet = {d: n for d, _w, n, *_ in days}
        by_day = collections.defaultdict(list)
        for x in log:
            by_day[x["day"]].append(x)
        rows = []
        for d, a in sorted(au.items()):
            if a["g"] == 0 or lab.get(d) != "CHEAP" or d not in wallet:
                continue
            s = smp.s[d]
            side = "CE" if a["g"] > 0 else "PE"
            pos, _dep, state, jf = op.leg(smp, s, side, 1, "HONEST", st)
            if pos is None:
                rows.append({"day": d, "state": state, "net": 0.0})
                continue
            debit = op.entry_cost(pos.fills[0])
            g_first = min(by_day.get(d, []), key=lambda x: x["i"], default=None)
            conflict = g_first is not None and g_first["i"] < jf + 60
            pre = False
            if conflict:
                gdeb = g_first["ask0"] * op.LOT * (g_first["lots0"] or 1) if g_first.get("ask0") else 0.0
                pre = wallet[d] - debit < gdeb
            if pre:
                v = pos.value(s, g_first["i"])
                walked = gl.walk(pos, s, jf, g_first["i"], room=op.STOP)
                net = walked[0] if walked[2] == "stop" else (v if v is not None else walked[0])
            else:
                net = gl.walk(pos, s, jf, jf + 60, room=op.STOP)[0]
            net = net or 0.0
            rows.append({"day": d, "state": "FILLED", "net": round(net, 2), "conflict": conflict, "preempted": pre,
                         "day_stop_breach": (min(0.0, net) + min(0.0, gnet.get(d, 0.0))) <= -0.2 * wallet[d]})
        window = [d for d, *_ in days if op.sn353b.LO <= d < op.sn353b.HI]
        res[f"shared wallet @{int(st)} (development illustration)"] = {
            "window_market_sessions": len(window), "cheap_sessions": len(rows), "opener_fills": sum(r["state"] == "FILLED" for r in rows),
            "conflicts_gold_before_exit": sum(bool(r.get("conflict")) for r in rows), "preemptions": sum(bool(r.get("preempted")) for r in rows),
            "day_stop_breaches": sum(bool(r.get("day_stop_breach")) for r in rows), "incremental_net": round(sum(r["net"] for r in rows)),
            "incremental_per_market_session": round(sum(r["net"] for r in rows) / max(1, len(window)), 1),
            "positive_opener_days": sum(r["net"] > 0 for r in rows), "opener_days_ge_750": sum(r["net"] >= 750 for r in rows),
            "gold_net_same_window": round(sum(n for d, _w, n, *_ in days if d in set(window))), "rows": rows}
        print(int(st), json.dumps({k: v for k, v in res[f"shared wallet @{int(st)} (development illustration)"].items() if k != "rows"}), flush=True)
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
