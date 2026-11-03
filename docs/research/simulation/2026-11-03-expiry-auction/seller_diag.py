"""Post-score neighbourhood of the one passing seller arm (T 14:00, 4-step wings, stop at 2x credit). IN-SAMPLE,
never a pass: entry time 13:00-14:30 (and 13:00-14:45 without the stop), wings 3-5 steps, stop 0.75-1.5x, and on the nine Production days the
exit before the auction (15:14) against after it (15:31). Writes seller-diagnostics.json.
"""
from __future__ import annotations
import json
from pathlib import Path
import seller as S

HERE = Path(__file__).resolve().parent


def chains(a, T):
    out = {}
    for y in (2024, 2025):
        for sc in ("ordinary", "adverse", "catastrophe"):
            s = S.summarize([S.chain_day(t, a, sc) for t in T[y]])
            out[f"{y}|{sc}"] = {k: s.get(k) for k in ("net", "without_best", "worst", "wins", "traded")}
    return out


def prod(a, before_auction=False):
    p = S.A.production_days(); rows = []
    for (u, d), snaps in sorted(p.items()):
        settle = next((s["spot"] for s in snaps if s["t"] >= S.A.secs("15:31:00") and s["spot"]), None)
        if not settle:
            continue
        if before_auction:          # same rule, but every leg is closed on the 15:14 snapshot's book
            cut = [s for s in snaps if s["t"] < S.A.secs("15:14:00")]
            tail = next(s for s in snaps if s["t"] >= S.A.secs("15:14:00"))
            snaps = cut + [dict(tail, t=S.A.secs("15:31:00"))]
        rows.append(S.prod_day(u, d, snaps, a, settle))
    s = S.summarize(rows)
    return dict(summary={k: s.get(k) for k in ("net", "without_best", "worst", "wins", "traded")}, days={r["day"]: r.get("net") for r in rows})


def main():
    T = S.LAB.tapes(); base = dict(T=840, steps=4, stop=1.)
    out = dict(note=__doc__, time={}, wings={}, stop={}, production={})
    for T_ in (780, 795, 810, 825, 840, 855, 870):
        out["time"][f"{T_ // 60}:{T_ % 60:02d}"] = chains(dict(base, T=T_), T)
    for w in (3, 4, 5):
        out["wings"][str(w)] = chains(dict(base, steps=w), T)
    for s in (.75, 1., 1.25, 1.5, None):
        out["stop"][str(s)] = chains(dict(base, stop=s), T)
    out["time_hold_ordinary"] = {}
    for T_ in (780, 795, 810, 825, 840, 855, 870, 885):
        a = dict(T=T_, steps=4, stop=None); row = {}
        for y in (2024, 2025):
            s = S.summarize([S.chain_day(t, a, "ordinary") for t in T[y]]); row[str(y)] = [s["net"], s["without_best"], s["wins"]]
        out["time_hold_ordinary"][f"{T_ // 60}:{T_ % 60:02d}"] = row
    for label, a, before in (("after_auction", base, False), ("before_auction", base, True),
                             ("after_auction_hold", dict(base, stop=None), False), ("before_auction_hold", dict(base, stop=None), True)):
        out["production"][label] = prod(a, before)
    (HERE / "seller-diagnostics.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    for grp in ("time", "wings", "stop"):
        for k, v in out[grp].items():
            print(grp, k, {x: (y["net"], y["without_best"], y["worst"]) for x, y in v.items()})
    for k, v in out["production"].items():
        print("production", k, v["summary"], v["days"])


if __name__ == "__main__":
    main()
