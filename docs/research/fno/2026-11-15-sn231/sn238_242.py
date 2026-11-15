"""SN238-SN242 (PLAN.md), each written to its own results-snNNN.json.
SN238 SENSEX WK-H as a second instrument: its daily marks (Oct 2024 - Apr 2026) added to Gold v6; months positive in the
       account window and in the overlap months; band 0.6 and 0.8.
SN239 cost-aware weeks: skip a WK-H week when the entry straddle is below p% of the index (p 0.6 / 0.7 / 0.8); five samples
       and the account; a 500-draw random-skip null on the account's months positive (same skips per sample).
SN240 leg mix: WK-H units 1 / 2 / 3 (and the band-0.8 version) with Gold v5 unchanged.
SN241 month protection: once the account's month-to-date reaches X (Rs 20k / 40k / 60k), no new WK-H week starts that
       month (open weeks run on). Profit protection only; nothing reacts to a loss.
SN242 idle capital: the wallet (Rs 30k + Rs 5 lakh) as pledged liquid-fund collateral at an assumed 5% a year, credited
       monthly; shown separately."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ev  # noqa: E402
import led  # noqa: E402
import wk4  # noqa: E402

wk = led.wk
dumps = lambda x: json.dumps(x, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))   # noqa: E731
jd = lambda x: json.dumps(x, default=lambda o: o.item() if hasattr(o, "item") else str(o))   # noqa: E731  (post-run print fix)


def once(sn):
    p = HERE / f"results-sn{sn}.json"
    if p.exists():
        raise SystemExit(f"SN{sn} is run once")
    return p


def wkh(n, hp):
    return wk4.book4(led.sample(n), "STRADDLE", "M", "settle", hp)


def sn238():
    p = once(238)
    res = {}
    days = led.sessions()
    for lab, hp in (("band 0.6", {}), ("band 0.8", {"band": 0.8})):
        nifty = wkh("DEV", hp) + wkh("TEST", hp)
        sx = wkh("SENSEX", hp)
        base = ev.account([ev.leg_days(nifty)])
        plus = ev.account([ev.leg_days(nifty), ev.leg_days(sx)])
        ov = [m for m in sorted({d[:7] for d in days}) if "2024-10" <= m <= "2026-04"]
        g = led.gold()
        mn = led.months({d: g.get(d, 0.0) + ev.leg_days(nifty).get(d, 0.0) for d in days}, days)
        sxd = ev.leg_days(sx)
        mp = led.months({d: g.get(d, 0.0) + ev.leg_days(nifty).get(d, 0.0) + sxd.get(d, 0.0) for d in days}, days)
        res[lab] = {"without": base, "with SENSEX WK-H": plus, "overlap_months": len(ov),
                    "overlap_positive_without": sum(mn[m] > 0 for m in ov), "overlap_positive_with": sum(mp[m] > 0 for m in ov),
                    "overlap_worst_without": round(min(mn[m] for m in ov)), "overlap_worst_with": round(min(mp[m] for m in ov))}
        print("SN238", lab, jd({k: (v if not isinstance(v, dict) else {x: v[x] for x in ("net", "months_positive", "worst_month")}) for k, v in res[lab].items()}), flush=True)
    p.write_text(dumps(res), encoding="utf-8")


def prem(t, s):
    S = wk.idx_px(s.data, t["entry"])
    return t["Q"] / S * 100 if S else None


def sn239():
    p = once(239)
    res = {}
    days = led.sessions()
    g = led.gold()
    for lab, hp in (("band 0.6", {}), ("band 0.8", {"band": 0.8})):
        tr = {n: wkh(n, hp) for n in led.WK_SAMPLES}
        base_st = ev.wk_stats(tr)
        res[lab] = {"no skip": {"wk": base_st, "account": ev.account([ev.leg_days(tr["DEV"] + tr["TEST"])])}}
        for thr in (0.6, 0.7, 0.8):
            kept = {n: [t for t in tr[n] if (prem(t, led.sample(n)) or 0) >= thr] for n in led.WK_SAMPLES}
            st = ev.wk_stats(kept)
            ac = ev.account([ev.leg_days(kept["DEV"] + kept["TEST"])])
            rng = np.random.default_rng(239)
            full = tr["DEV"] + tr["TEST"]
            nk = len(kept["DEV"]) + len(kept["TEST"])
            null = []
            for _ in range(500):
                idx = rng.choice(len(full), size=nk, replace=False)
                leg = ev.leg_days([full[i] for i in idx])
                null.append(sum(v > 0 for v in led.months({d: g.get(d, 0.0) + leg.get(d, 0.0) for d in days}, days).values()))
            res[lab][f"skip below {thr}%"] = {"wk": st, "account": ac, "skipped_account_weeks": len(full) - nk,
                                              "null_months_positive_p95": float(np.percentile(null, 95)), "q4_vs_unskipped": ev.q4(st, base_st)}
            print("SN239", ev.line(f"{lab} skip < {thr}%", st, ac), "skipped", len(full) - nk, "null p95", res[lab][f"skip below {thr}%"]["null_months_positive_p95"], flush=True)
    p.write_text(dumps(res), encoding="utf-8")


def scaled(leg, k):
    return {d: x * k for d, x in leg.items()}


def sn240():
    p = once(240)
    res = {}
    for lab, hp in (("band 0.6", {}), ("band 0.8", {"band": 0.8})):
        leg = ev.leg_days(wkh("DEV", hp) + wkh("TEST", hp))
        for u in (1, 2, 3):
            ac = ev.account([scaled(leg, u)])
            res[f"{lab}, {u} unit{'s' if u > 1 else ''} (Rs {5 * u} lakh)"] = ac
            print("SN240", lab, u, jd({x: ac[x] for x in ("net", "months_positive", "worst_month", "second_worst_month")}), flush=True)
    p.write_text(dumps(res), encoding="utf-8")


def sn241():
    p = once(241)
    res = {}
    days = led.sessions()
    g = led.gold()
    for lab, hp in (("band 0.6", {}), ("band 0.8", {"band": 0.8})):
        trades = sorted(wkh("DEV", hp) + wkh("TEST", hp), key=lambda t: t["entry"])
        for X in (20000, 40000, 60000):
            kept, skipped = [], 0
            for t in trades:
                m = t["entry"][:7]
                # month-to-date of the account up to the entry day's 15:15 (Gold's full day + the legs' marks so far)
                leg = ev.leg_days(kept)
                mtd = sum(g.get(d, 0.0) + leg.get(d, 0.0) for d in days if d[:7] == m and d <= t["entry"])
                if mtd >= X:
                    skipped += 1
                    continue
                kept.append(t)
            ac = ev.account([ev.leg_days(kept)])
            res[f"{lab}, pause new weeks after +{X:,}"] = {"account": ac, "weeks_skipped": skipped}
            print("SN241", lab, X, "skipped", skipped, jd({x: ac[x] for x in ("net", "months_positive", "worst_month")}), flush=True)
    p.write_text(dumps(res), encoding="utf-8")


def sn242():
    p = once(242)
    days = led.sessions()
    res = {}
    for lab, hp in (("band 0.6", {}), ("band 0.8", {"band": 0.8})):
        leg = ev.leg_days(wkh("DEV", hp) + wkh("TEST", hp))
        g = led.gold()
        months = sorted({d[:7] for d in days})
        tot = {d: g.get(d, 0.0) + leg.get(d, 0.0) for d in days}
        first = {}
        for d in days:
            first.setdefault(d[:7], d)
        y = {first[m]: 530000 * 0.05 / 12 for m in months}
        withy = {d: tot[d] + y.get(d, 0.0) for d in days}
        res[lab] = {"without": led.account_stats(tot, days), "with 5% on Rs 5.3 lakh": led.account_stats(withy, days), "monthly_credit": round(530000 * 0.05 / 12)}
        print("SN242", lab, jd({k: {x: v[x] for x in ("net", "months_positive", "worst_month")} for k, v in res[lab].items() if isinstance(v, dict)}), flush=True)
    p.write_text(dumps(res), encoding="utf-8")


if __name__ == "__main__":
    for f in (sn238, sn239, sn240, sn241, sn242):
        f()
