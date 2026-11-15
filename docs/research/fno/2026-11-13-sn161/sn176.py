"""SN176 - the wage day player (PLAN.md). Development sessions. Gold v5 first (unchanged v5 rules); on Gold's empty
days SN95-L / SN126-L (the forward watches), then any P3 rule that passed development (p4.passing_companions; the ML
studies failed development and are excluded), first that trades; companions keep their own Rs 15k (SN171's straddle
Rs 30k) sizing and their wage lock / day limit. Wallets Rs 15k, Rs 30k growing (production) and Rs 50k growing.
Wage = 10% of the starting wallet. In-sample description (the TEST column is SN181's)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import p3  # noqa: E402
import p4  # noqa: E402
import pw  # noqa: E402

C = pw.C


def watches(dset):
    adm = pw.pa.admission()
    s95 = {S.day: pw.pb.net(pw.pa.path(S, pw.pa.I10)) for S in pw.pb.signal_days(adm, True) if S.day in dset}
    r126 = json.loads((C.FNO / "2026-11-13-sn121" / "results-sn126.json").read_text(encoding="utf-8"))
    s126 = {d: v for d, v in r126["heldout_day_nets"].items() if v and d in dset}
    out = {d: v for d, v in s95.items() if v}
    for d, v in s126.items():
        out.setdefault(d, v)
    return out


if __name__ == "__main__":
    out_path = HERE / "results-sn176.json"
    if out_path.exists():
        raise SystemExit("SN176 is scored once")
    ss = pw.dev_sessions()
    days = [S.day for S in ss]
    comps = p4.passing_companions()
    rho = p3.rho_table(p3.HAR(ss), ss, lambda d: True)
    w = watches(set(days))
    res = {"companions_passing_development": list(comps)}
    for key in ("Rs 15k", "Rs 30k growing (production)", "Rs 50k growing"):
        wallet = p4.WALLETS[key][1]
        g = p4.gold(key)
        gw = dict(g)
        for d, v in w.items():
            gw.setdefault(d, v)
        full = p4.day_player(gw, ss, comps, rho, wallet)
        res[key] = {name: pw.wage_stats(dn, days, wallet) for name, dn in
                    (("Gold v5", g), ("+ forward watches", gw), ("+ passing companions", full))}
        for name, s in res[key].items():
            print(f"SN176 {key:28s} {name:22s} trade days {s['trade_days']:4d} wage days {s['wage_days']:4d} "
                  f"({s['wage_share']:.1%}) wage days/month {s['month']['wage_days_mean']:4.1f} net {s['net']:>10,} "
                  f"month median {s['month']['median']:>8,} worst {s['month']['worst']:>9,}", flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
