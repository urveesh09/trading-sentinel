"""SN161 - the wage calendar of today's system (PLAN.md). Development sessions only (TEST is SN181's).

Gold v5 day nets through SN110's player (v5 parity proven) for the Rs 15k one-lot wallet and the production Rs 30k
growing wallet (stop 3); SN95-L (10:00 straddle on causal hot, Gold-free days, strict) and SN126-L (held-out bursts) on
the same calendar; the three together as one ledger (Gold first; a straddle / burst day adds its net). Wage = 10% of
the starting wallet. Wage / red / flat days per month, monthly sums, per year."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pw  # noqa: E402
import pc  # noqa: E402

C = pw.C

if __name__ == "__main__":
    out_path = HERE / "results-sn161.json"
    if out_path.exists():
        raise SystemExit("SN161 is scored once")
    days = [S.day for S in pw.dev_sessions()]
    dset = set(days)
    adm = pw.pa.admission()
    s95 = {S.day: pw.pb.net(pw.pa.path(S, pw.pa.I10)) for S in pw.pb.signal_days(adm, True) if S.day in dset}
    s95 = {d: v for d, v in s95.items() if v}
    r126 = json.loads((C.FNO / "2026-11-13-sn121" / "results-sn126.json").read_text(encoding="utf-8"))
    s126 = {d: v for d, v in r126["heldout_day_nets"].items() if v and d in dset}
    res = {"calendar": {"from": days[0], "to": days[-1], "sessions": len(days)}}
    for name, w, wallet in (("Rs 15k one lot", ("A 15k 1 lot", 15000.0, "one", None), 15000.0),
                            ("Rs 30k growing stop 3 (production)", ("30k grow stop 3", 30000.0, "grow", 3), 30000.0)):
        _row, daylog = pc.gold_days(C.V5, w)
        gold = {d: n for d, n in daylog if n and d in dset}
        both = dict(gold)
        for src in (s95, s126):
            for d, v in src.items():
                if d not in gold:
                    both[d] = both.get(d, 0.0) + v
        res[name] = {"Gold v5": pw.wage_stats(gold, days, wallet),
                     "Gold v5 + SN95-L + SN126-L": pw.wage_stats(both, days, wallet)}
        print(f"=== SN161 {name}", flush=True)
        for k, s in res[name].items():
            print(f"   {k:28s} trade days {s['trade_days']:4d} wage days {s['wage_days']:4d} ({s['wage_share']:.1%}) red "
                  f"{s['red_days']:4d} net {s['net']:>10,} | month mean {s['month']['mean']:>8,} median {s['month']['median']:>8,} "
                  f"worst {s['month']['worst']:>9,} wage days/month {s['month']['wage_days_mean']}", flush=True)
    res["SN95-L alone (Rs 15k sleeve)"] = pw.wage_stats(s95, days, 15000.0)
    res["SN126-L alone (Rs 15k sleeve)"] = pw.wage_stats(s126, days, 15000.0)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
