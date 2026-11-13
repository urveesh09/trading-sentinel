"""SN158 - the hot-day book (PLAN.md) and SN159 - robustness of the pieces. The book is one separate Rs 15k sleeve:
SN95-L's 10:00 straddle where it trades, else SN126-L's held-out burst trades that day, else any SN151-SN157 survivor
(held-out day nets), one source a day (earliest-starting first). Per year; against the same Rs 15k inside Gold
(Rs 45k vs Rs 30k + sleeve, growing stop 3 and fixed). SN159: for SN95-L, SN126-L, every survivor and the book, a
day-bootstrap 95% interval of the mean trade-day net."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn116"))
import ph  # noqa: E402
import pc  # noqa: E402

pa, pb = ph.pa, ph.pb


def j(name):
    p = HERE / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def survivors():
    out = {}
    for name, key in (("results-sn151.json", "gold-free"), ("results-sn152.json", "gold-free")):
        r = j(name)
        if r and r[key]["verdict"]["PASS"]:
            out[name[8:13]] = r[key]["heldout_day_nets"]
    r = j("results-sn154.json")
    if r and r["gold-free"]["sn154_verdict"]["PASS"]:
        out["sn154"] = r["gold-free"]["heldout_day_nets"]
    if r and r["gold-free"]["sn155"]["PASS"]:
        out["sn155"] = r["gold-free"]["consensus_day_nets"]
    return out


def boot(vals, n=4000, seed=159):
    v = np.array([x for x in vals if x != 0])
    if len(v) < 3:
        return None
    rng = np.random.default_rng(seed)
    m = [float(rng.choice(v, len(v)).mean()) for _ in range(n)]
    return {"trade_days": len(v), "mean": round(float(v.mean())), "ci95": [round(float(np.percentile(m, 2.5))), round(float(np.percentile(m, 97.5)))]}


if __name__ == "__main__":
    out_path = HERE / "results-sn158.json"
    if out_path.exists():
        raise SystemExit("SN158 is scored once")
    adm = pa.admission()
    sn95 = {S.day: pb.net(pa.path(S, pa.I10)) for S in pb.signal_days(adm, True)}
    sn95 = {d: v for d, v in sn95.items() if v != 0}
    r126 = json.loads((ph.C.FNO / "2026-11-13-sn121" / "results-sn126.json").read_text(encoding="utf-8"))
    sn126 = {d: v for d, v in r126["heldout_day_nets"].items() if v}
    surv = survivors()
    book = {}
    for d in sorted(set(sn95) | set(sn126) | {d for s in surv.values() for d in s}):
        if d in sn95:
            book[d] = sn95[d]
        elif d in sn126:
            book[d] = sn126[d]
        else:
            for s in surv.values():
                if s.get(d):
                    book[d] = s[d]
                    break
    tb = ph.table(book)
    res = {"survivors_used": sorted(surv), "book_by_year": {y: tb[y]["net"] for y in ph.YEARS}, "book_total": ph.tot(tb),
           "book_trade_days": len(book)}
    for mname, cap in (("fixed", 0), ("grow stop 3", 3)):
        g30, _d = pc.gold_days(pc.C.V5, (f"30k {mname}", 30000.0, "grow", cap))
        g45, _d = pc.gold_days(pc.C.V5, (f"45k {mname}", 45000.0, "grow", cap))
        res[f"Rs 45k {mname}"] = {"Gold 30k + hot-day book": round(g30["net"] + res["book_total"]), "Gold 45k": round(g45["net"])}
    res["sn159_bootstrap"] = {"SN95-L straddle": boot(sn95.values()), "SN126-L bursts": boot(sn126.values()), "hot-day book": boot(book.values()),
                              **{k: boot(v.values()) for k, v in surv.items()}}
    print("SN158", json.dumps(res), flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
