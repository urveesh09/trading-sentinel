"""SN306 (archive part): where the one-minute delay loss happens (PLAN.md, frozen at 94c772cd). SN290's cases (sealed
minute archive, NIFTY front-weekly ATM CE / PE / straddle, one lot, bought at 09:20 / 10:00 / 11:00 / 13:00 / 14:00, sold
15 or 60 minutes later, real ask walk in and real bid walk out, Zerodha charges): the round trip with the entry alone one
minute late, the exit alone one minute late, and both (SN290's shift), each minus the on-time round trip. Signed mean,
absolute mean, 5th / 95th percentiles; cases with a missing quote at any of the four clocks are dropped (counted)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn286"))
sys.path.insert(0, str(FNO / "2026-11-13-sn101"))
sys.path.insert(0, str(FNO / "2026-11-16-sn251"))
import gl  # noqa: E402
import qa  # noqa: E402
import sn290  # noqa: E402

SHIFTS = {"ontime": (0, 0), "entry_late": (1, 0), "exit_late": (0, 1), "both_late": (1, 1)}


if __name__ == "__main__":
    out = HERE / "results-sn306.json"
    if out.exists():
        raise SystemExit("SN306 is run once")
    rows, dropped = [], 0
    days = sorted(x.stem.replace("quotes-", "") for x in qa.LOCAL.glob("quotes-*.pkl"))
    for day in days:
        try:
            q = qa.load(day)
        except Exception:
            continue
        e = sn290.front(q, day)
        fk = sorted(k for k in q["fut"] if k[0] == "NIFTY")
        if e is None or not fk:
            continue
        fut = q["fut"][fk[0]]
        lot = q["lot"]["NIFTY"]
        for cn, i in sn290.CLOCKS.items():
            fm = sn290.mid(fut, i)
            if fm is None:
                continue
            K = int(round(fm / 50.0) * 50)
            for name, legs in (("CE", [(K, "CE")]), ("PE", [(K, "PE")]), ("straddle", [(K, "CE"), (K, "PE")])):
                recs = [q["opt"].get(("NIFTY", e, k, o)) for k, o in legs]
                if any(r is None for r in recs):
                    continue
                for h in sn290.HOLDS:
                    vals = {}
                    for tag, (da, db) in SHIFTS.items():
                        a, b = i + da, i + h + db
                        rb = [sn290.real_px(r, a, "buy", lot) for r in recs]
                        rs = [sn290.real_px(r, b, "sell", lot) for r in recs]
                        if any(x is None for x in rb + rs):
                            vals = None
                            break
                        vals[tag] = sum((s - bb) * lot - gl.wk.charges(bb, s, lot, "NFO") for bb, s in zip(rb, rs))
                    if vals is None:
                        dropped += 1
                        continue
                    rows.append({"day": day, "clock": cn, "kind": name, "hold": h,
                                 **{k: vals[k] - vals["ontime"] for k in ("entry_late", "exit_late", "both_late")}})
    res = {"cases": len(rows), "dropped_missing_quote": dropped, "days": len({r["day"] for r in rows}), "by": {}}
    for kind in ("CE", "PE", "straddle"):
        for h in sn290.HOLDS:
            rs = [r for r in rows if r["kind"] == kind and r["hold"] == h]
            if not rs:
                continue
            res["by"][f"{kind} hold {h}"] = {"n": len(rs), **{
                k: {"mean": round(float(np.mean([r[k] for r in rs]))), "abs_mean": round(float(np.mean([abs(r[k]) for r in rs]))),
                    "p5": round(float(np.percentile([r[k] for r in rs], 5))), "p95": round(float(np.percentile([r[k] for r in rs], 95)))}
                for k in ("entry_late", "exit_late", "both_late")}}
            print("SN306", kind, h, json.dumps(res["by"][f"{kind} hold {h}"]), flush=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
