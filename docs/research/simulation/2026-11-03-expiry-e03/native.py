"""E02 R3 and E03 on Production's own recorded NIFTY expiries (October 6 - November 3, 2026).

Neither rule was fitted on these sessions. The ten-second packets become minute bars the way
the E02 paper shadow builds them (at least four fresh index/future samples a minute, else no
bar). An option's minute bar is the open/high/low/close of its quoted mid; its volume field is
five times the smaller side of its five-level depth, so the lab's 20% participation equals the
visible depth. Fills then follow the lab exactly (next bar's open plus the half spread).
Recording starts at 12:59, so the ten-bar readings first exist about 13:10, as in the shadow.
"""
from __future__ import annotations
import json, re, sqlite3, sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import e03_lab as X
D, E = X.D, X.E

EXPORT = X.HERE.parent / "2026-11-02-expiry-e01/_local/export/expiry.sqlite"
EXTRA = X.HERE / "_local/native-extra.sqlite"      # read-only copy of later Production days


def tape(conn, day):
    rows = conn.execute("SELECT ts, spot, fut, quotes FROM expiry_paper_ticks WHERE day=? AND underlying='NIFTY' ORDER BY ts", (day,)).fetchall()
    base = datetime.fromisoformat(day + "T09:15:00")
    spots, futs = defaultdict(list), defaultdict(list)
    legs = defaultdict(lambda: defaultdict(list))
    depth = {}
    for ts, spot, fut, quotes in rows:
        stamp = datetime.fromisoformat(ts).replace(tzinfo=None)
        k = int((stamp - base).total_seconds() // 60)
        if not 0 <= k < 375:
            continue
        if spot and fut:
            spots[k].append(float(spot)); futs[k].append(float(fut))
        for sym, q in json.loads(quotes).get("legs", {}).items():
            if isinstance(q, list):      # October 6 logged the top level only: bid, qty, ask, qty, ltp, ts
                b, a = ([[q[0], q[1]]] if q[0] else []), ([[q[2], q[3]]] if q[2] else [])
            else:
                b, a = q.get("b") or [], q.get("a") or []
            if not b or not a:
                continue
            legs[sym][k].append((float(b[0][0]) + float(a[0][0])) / 2)
            depth[(sym, k)] = min(sum(int(x[1]) for x in b), sum(int(x[1]) for x in a))
    x = np.full((375, 4), np.nan); f = x.copy()
    for k in spots:
        if len(spots[k]) >= 4:
            s, u = spots[k], futs[k]
            x[k] = [s[0], max(s), min(s), s[-1]]; f[k] = [u[0], max(u), min(u), u[-1]]
    names = sorted(legs)
    parsed = []
    for n in names:
        m = re.search(r"(\d{5})(CE|PE)$", n)
        parsed.append((float(m.group(1)), 1 if m.group(2) == "CE" else -1))
    q = np.full((375, len(names), 5), np.nan)
    for j, n in enumerate(names):
        for k, mids in legs[n].items():
            if np.isfinite(x[k, 3]):
                q[k, j] = [mids[0], max(mids), min(mids), mids[-1], 5 * depth[(n, k)]]
    now = [datetime.fromisoformat(day + "T09:15:00").replace(tzinfo=E.EP.IST) + timedelta(minutes=i + 1) for i in range(375)]
    return D.Tape(day, x, f, q, np.array([p[0] for p in parsed]), np.array([p[1] for p in parsed]),
                  [f"NIFTY-{day}-{p[0]:g}-{'CE' if p[1] == 1 else 'PE'}" for p in parsed], now, np.arange(556, 931), 0)


def tapes():
    out = []
    for path in (EXPORT, EXTRA):
        if not path.exists():
            continue
        c = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        days = [r[0] for r in c.execute("SELECT DISTINCT day FROM expiry_paper_ticks WHERE underlying='NIFTY' ORDER BY day")]
        out += [tape(c, d) for d in days if d not in {t.day for t in out}]
        c.close()
    return out


if __name__ == "__main__":
    E03 = dict(max_lots=3, split=True, runner_floor=1.0, runner_keep=0.5, hero_target=9.0)
    ts = tapes()
    print("sessions", [t.day for t in ts], "index bars from 13:00", [int(np.isfinite(t.close[225:]).sum()) for t in ts])
    res = {}
    for name, extra in (("E02_R3", {}), ("E03", E03)):
        for sc in ("ordinary", "adverse"):
            r = X.run_year(ts, X.Hero(**{**X.R3, **extra}), sc, details=True)
            res[f"{name}_{sc}"] = dict(summary=X.brief(r["summary"]), days=[dict(day=d["day"], net=d["net"], trades=d["trades"],
                                       positions=[dict(symbol=p["symbol"], entry=p["entry"], lots=p["lots"], peak=p["peak"], net=p["net"],
                                                       exits=[(e.get("reason"), e["price"]) for e in p["events"][1:]]) for p in d["positions"]])
                                       for d in r["days"]])
            print(name, sc, X.brief(r["summary"]))
            for d in res[f"{name}_{sc}"]["days"]:
                print("   ", d["day"], d["net"], [(p["symbol"][-8:], p["entry"], p["lots"], p["peak"], p["net"], p["exits"]) for p in d["positions"]])
    D.dump(X.HERE / "native-results.json", res)
