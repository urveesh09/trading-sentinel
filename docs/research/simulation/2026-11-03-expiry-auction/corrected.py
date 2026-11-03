"""Post-score diagnostic (NOT a pre-registered pass): the frozen test read S0, "the frozen index value", at 15:20.
The Breeze history shows an indicative auction index from 15:20 on some days, while Kite's index stays frozen.
This recomputes every measure with S0 read at 15:15, the last continuous value (the plan's stated intent), and
profiles the remaining move R(t) from 15:20 to 15:29. Writes corrected.json. The verdict in results.json stands.
"""
from __future__ import annotations
import json, statistics as st
from pathlib import Path
import auction as A

HERE = Path(__file__).resolve().parent
TIMES = ["15:16", "15:18", "15:19", "15:20", "15:21", "15:22", "15:23", "15:24", "15:25", "15:26", "15:27", "15:28", "15:29"]


def main():
    prod = A.production_days(); ex = A.export_days(); days = {}
    for (u, d), snaps in prod.items():
        s15 = A.at(snaps, A.secs("15:15:30")); after = [s for s in snaps if s["t"] >= A.secs("15:31:00")]
        s0 = A.at(snaps, A.secs("15:20:00"))["spot"]
        if s0 is None or not after or after[0]["spot"] is None:
            days[(u, d)] = dict(unavailable="no recorded index"); continue
        ys = {}
        for g in TIMES:
            s = A.at(snaps, A.secs(g + ":00"))
            ys[g] = A.prod_synthetic(s, s0) if s and A.secs(g + ":00") - s["t"] <= A.FRESH_PROD else None
        days[(u, d)] = dict(source="production", s0=s0, settle=after[0]["spot"], y=ys)
    for (u, d), rec in ex.items():
        idx, fut, daily = A.index_minutes(u, d)
        f = idx.get(A.secs("15:35:00")) or idx.get(A.secs("15:39:00"))
        if A.secs("15:15:00") not in idx or f is None:
            days[(u, d)] = dict(unavailable="index minutes missing"); continue
        ys = {}
        for g in TIMES:
            t = A.secs(g + ":00"); legs = []
            for o in ("CE", "PE"):
                done = [e for e in rec["bars"][o] if t - A.FRESH_EXPORT <= e <= t]
                legs.append(rec["bars"][o][max(done)] if done else None)
            ys[g] = rec["strike"] + legs[0] - legs[1] if None not in legs else None
        days[(u, d)] = dict(source="export", s0=idx[A.secs("15:15:00")], settle=f, s0_at_1520=idx.get(A.secs("15:20:00")),
                            indicative_at_1520=idx.get(A.secs("15:20:00")) != idx[A.secs("15:15:00")], y=ys)
    rows = {}
    for k, r in days.items():
        if "unavailable" in r or k in A.SEEN:
            continue
        r["move"] = round(r["settle"] - r["s0"], 2); r["at"] = {}
        for g, y in r["y"].items():
            if y is None:
                continue
            dd = y - r["s0"]; sign = 1 if dd > 0 else -1 if dd < 0 else 0
            r["at"][g] = dict(d=round(dd, 2), r=round((r["settle"] - y) * sign, 2), signal=abs(dd) >= A.THETA * r["s0"])
        rows[f"{k[0]} {k[1]}"] = r
    profile = {}
    for g in TIMES:
        sig = [(n, r["at"][g]) for n, r in rows.items() if g in r["at"] and r["at"][g]["signal"]]
        if not sig:
            continue
        rr = [x["r"] for _, x in sig]
        agree = [(x["d"] > 0) == (rows[n]["move"] > 0) for n, x in sig if rows[n]["move"]]
        profile[g] = dict(signalled=len(sig), agree=round(sum(agree) / len(agree), 3), r_mean=round(st.mean(rr), 2),
                          r_median=round(st.median(rr), 2), r_positive=round(sum(x > 0 for x in rr) / len(rr), 3),
                          r_mean_pct=round(st.mean(x / rows[n]["s0"] * 100 for (n, _), x in zip(sig, rr)), 4))
    out = dict(note=__doc__, days=rows, profile=profile,
               unavailable=sorted(f"{k[0]} {k[1]}" for k, r in days.items() if "unavailable" in r),
               indicative_at_1520=sorted(n for n, r in rows.items() if r.get("indicative_at_1520")))
    (HERE / "corrected.json").write_text(json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8")
    for g, p in profile.items():
        print(g, p)
    print("unavailable", out["unavailable"]); print("indicative index at 15:20 in the history", out["indicative_at_1520"])
    for n, r in rows.items():
        a = r["at"].get("15:22", {})
        print(n, r["source"][:4], "S0", r["s0"], "F", r["settle"], "M", r["move"], "D22", a.get("d"), "R22", a.get("r"))


if __name__ == "__main__":
    main()
