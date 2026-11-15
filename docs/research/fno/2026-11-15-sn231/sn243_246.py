"""SN243-SN246 (PLAN.md), each to its own results file.
SN243 the amendment's extra candidates: none beyond DIAGNOSIS.md (recorded).
SN244 combinations: only band 0.8 passed SN235-SN243, so the eligible combination is band 0.8 (+ SN242's idle capital,
      shown separately). Information only, not eligible: band 0.8 with each SN235 expiry variant and with the synthetic hedge.
SN245 Gold v7 by the frozen rule (Q1-Q5) over every candidate scored in SN235-SN244.
SN246 robustness of band 0.8 against WK-H (band 0.6): neighbouring bands 0.7 / 0.9; option stress Rs 200 / 300 per leg-lot
      and futures half-spread 1.5 points with Rs 200 per lot-order; months positive per year; a paired month bootstrap
      (2,000 draws) of months positive; the five WK samples side by side."""
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

wk3 = led.wk3
dumps = lambda x: json.dumps(x, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))   # noqa: E731
jd = lambda x: json.dumps(x, default=lambda o: o.item() if hasattr(o, "item") else str(o))   # noqa: E731


def once(sn):
    p = HERE / f"results-sn{sn}.json"
    if p.exists():
        raise SystemExit(f"SN{sn} is run once")
    return p


def score(hp, samples=led.WK_SAMPLES):
    tr = {n: wk4.book4(led.sample(n), "STRADDLE", "M", "settle", hp) for n in samples}
    return tr, ev.wk_stats(tr), ev.account([ev.leg_days(tr["DEV"] + tr["TEST"])])


def qualifies(ac, st, base_ac, base_st):
    return {"Q1_more_months_positive": ac["months_positive"] > base_ac["months_positive"], "Q2_net_90pct": ac["net"] >= 0.9 * base_ac["net"],
            "Q3_worst_month_no_worse": ac["worst_month"] >= base_ac["worst_month"], "Q4_wk_samples": ev.q4(st, base_st)}


if __name__ == "__main__":
    p243, p244, p245, p246 = once(243), once(244), once(245), once(246)
    p243.write_text(dumps({"extra_candidates": [], "note": "SN234's amendment added the SN235-SN237 candidates; nothing else was added."}), encoding="utf-8")
    _, base_st, base_ac = score({})
    res244 = {}
    for lab, hp in (("band 0.8 (eligible)", {"band": 0.8}), ("info: band 0.8 + checks through 15:15", {"band": 0.8, "freeze_j": 361}),
                    ("info: band 0.8 + flatten at 14:30", {"band": 0.8, "flatten_j": 315}),
                    ("info: band 0.8 + every 5 min after 14:30", {"band": 0.8, "freeze_j": 361, "late_every": 5, "late_from": 315}),
                    ("info: band 0.8 + synthetic hedge", {"band": 0.8, "instrument": "synth"})):
        _tr, st, ac = score(hp)
        res244[lab] = {"hp": hp, "wk": st, "account": ac, "rule": qualifies(ac, st, base_ac, base_st)}
        print("SN244", ev.line(lab, st, ac), jd(res244[lab]["rule"]), flush=True)
    p244.write_text(dumps(res244), encoding="utf-8")
    # SN245: every candidate from SN235-SN244's result files, by the frozen rule
    cands = {}                                       # label -> (account, Q4/Q5 passed)
    for sn, key in ((235, "variants"), (236, "cost")):
        r = json.loads((HERE / f"results-sn{sn}.json").read_text(encoding="utf-8"))[key]
        for lab, v in r.items():
            if lab != "WK-H (as frozen)":
                cands[f"SN{sn} {lab}"] = (v["account"], bool(v["q4_vs_wkh"]))
    for lab, v in json.loads((HERE / "results-sn236.json").read_text(encoding="utf-8"))["second_unit"].items():
        cands[f"SN236 {lab}"] = (v["account"], ev.q4(v["leg_alone"], base_st))
    for lab, v in json.loads((HERE / "results-sn237.json").read_text(encoding="utf-8")).items():
        cands[f"SN237 {lab}"] = (v["account"], bool(v["q4_vs_wkh"]))
    for lab, v in json.loads((HERE / "results-sn238.json").read_text(encoding="utf-8")).items():
        cands[f"SN238 {lab} + SENSEX WK-H"] = (v["with SENSEX WK-H"], False)        # the added leg exists on one sample only
    for lab, v in json.loads((HERE / "results-sn239.json").read_text(encoding="utf-8")).items():
        for k, x in v.items():
            if k != "no skip":
                cands[f"SN239 {lab} {k}"] = (x["account"], bool(x["q4_vs_unskipped"]) and x["account"]["months_positive"] > x["null_months_positive_p95"])
    b08 = json.loads((HERE / "results-sn236.json").read_text(encoding="utf-8"))["cost"]["band 0.8 every 15"]["q4_vs_wkh"]
    for lab, v in json.loads((HERE / "results-sn240.json").read_text(encoding="utf-8")).items():
        cands[f"SN240 {lab}"] = (v, bool(b08) if "band 0.8" in lab else True)
    for lab, v in json.loads((HERE / "results-sn241.json").read_text(encoding="utf-8")).items():
        cands[f"SN241 {lab}"] = (v["account"], False)                              # a threshold rule with no null computed
    for lab, v in res244.items():
        if lab.startswith("band 0.8"):
            cands[f"SN244 {lab}"] = (v["account"], bool(v["rule"]["Q4_wk_samples"]))
    table = {}
    for lab, (ac, q45) in cands.items():
        q = {"Q1": ac["months_positive"] > base_ac["months_positive"], "Q2": ac["net"] >= 0.9 * base_ac["net"],
             "Q3": ac["worst_month"] >= base_ac["worst_month"], "Q4/Q5": q45}
        table[lab] = {"months_positive": ac["months_positive"], "net": ac["net"], "worst_month": ac["worst_month"], **q, "qualifies": all(q.values())}
    qual = sorted([k for k, v in table.items() if v["qualifies"]], key=lambda k: (-table[k]["months_positive"], -table[k]["worst_month"], -table[k]["net"]))
    res245 = {"baseline_gold_v6": base_ac, "candidates": table, "qualifying": qual, "gold_v7": qual[0] if qual else None}
    for k, v in table.items():
        print(f"SN245 {k:62s} months+ {v['months_positive']} net {v['net']:>9} worst {v['worst_month']:>8} Q {v['Q1']}/{v['Q2']}/{v['Q3']}/{v['Q4/Q5']} -> {'QUALIFIES' if v['qualifies'] else '-'}", flush=True)
    print("SN245 Gold v7 =", res245["gold_v7"], flush=True)
    p245.write_text(dumps(res245), encoding="utf-8")
    # SN246 robustness
    res246 = {"neighbours": {}, "stress": {}, "years": {}, "bootstrap": {}}
    for b in (0.6, 0.7, 0.8, 0.9, 1.0):
        _tr, st, ac = score({"band": b})
        res246["neighbours"][f"band {b}"] = {"account": {x: ac[x] for x in ("net", "months_positive", "worst_month")},
                                             "wk": {n: st[n]["net"] for n in led.WK_SAMPLES}, "positive_samples": st["positive_samples"],
                                             "months_positive_total": st["months_positive_total"]}
        print("SN246 band", b, jd(res246["neighbours"][f"band {b}"]), flush=True)
    orig_bt, old_fut, old_half = wk3.base_trade, wk3.FUT_STRESS, dict(wk3.HALF)

    def bt_stress(stress):
        def f(smp, e, days, struct, k):
            key = (e, struct, k, "stress", stress)
            if key not in smp.base:
                kk = wk3.k_of(k, e, days)
                t = wk3.wk.trade(smp.mk, smp.data, e, days, kk, struct, "settle", None, stress) if kk is not None else None
                smp.base[key] = None if (t is None or t.get("net") is None) else t
            return smp.base[key]
        return f

    for lab, (opt_s, fut_s, half) in (("stress 200 / fut 200 / half 1.5", (200.0, 200.0, 1.5)), ("stress 300 / fut 200 / half 1.5", (300.0, 200.0, 1.5))):
        wk3.base_trade, wk3.FUT_STRESS = bt_stress(opt_s), fut_s
        wk3.HALF["NIFTY"] = half
        out = {}
        for b in (0.6, 0.8):
            for n in ("DEV", "TEST"):
                led.sample(n).__dict__.get("hpaths4", {}).clear()
            tr = {n: wk4.book4(led.sample(n), "STRADDLE", "M", "settle", {"band": b}) for n in ("DEV", "TEST")}
            ac = ev.account([ev.leg_days(tr["DEV"] + tr["TEST"])])
            out[f"band {b}"] = {x: ac[x] for x in ("net", "months_positive", "worst_month")}
        res246["stress"][lab] = out
        print("SN246 stress", lab, jd(out), flush=True)
    wk3.base_trade, wk3.FUT_STRESS = orig_bt, old_fut
    wk3.HALF.clear()
    wk3.HALF.update(old_half)
    for n in ("DEV", "TEST"):
        led.sample(n).__dict__.get("hpaths4", {}).clear()
    days = led.sessions()
    g = led.gold()
    tr6, tr8 = score({})[0], score({"band": 0.8})[0]
    l6, l8 = ev.leg_days(tr6["DEV"] + tr6["TEST"]), ev.leg_days(tr8["DEV"] + tr8["TEST"])
    m6 = led.months({d: g.get(d, 0.0) + l6.get(d, 0.0) for d in days}, days)
    m8 = led.months({d: g.get(d, 0.0) + l8.get(d, 0.0) for d in days}, days)
    for y in ("2023", "2024", "2025", "2026"):
        ms = [m for m in m6 if m[:4] == y]
        res246["years"][y] = {"band 0.6": int(sum(m6[m] > 0 for m in ms)), "band 0.8": int(sum(m8[m] > 0 for m in ms)), "months": len(ms),
                              "net 0.6": round(sum(m6[m] for m in ms)), "net 0.8": round(sum(m8[m] for m in ms))}
    rng = np.random.default_rng(246)
    keys = sorted(m6)
    diff = []
    for _ in range(2000):
        idx = rng.integers(0, len(keys), len(keys))
        diff.append(int(sum(m8[keys[i]] > 0 for i in idx)) - int(sum(m6[keys[i]] > 0 for i in idx)))
    res246["bootstrap"] = {"share_band08_more_months": round(float(np.mean(np.array(diff) > 0)), 3),
                           "share_equal": round(float(np.mean(np.array(diff) == 0)), 3), "mean_extra_months": round(float(np.mean(diff)), 2)}
    res246["months_that_changed"] = {m: {"band 0.6": round(m6[m]), "band 0.8": round(m8[m])} for m in keys if (m6[m] > 0) != (m8[m] > 0)}
    print("SN246 years", jd(res246["years"]), "bootstrap", jd(res246["bootstrap"]), "changed", jd(res246["months_that_changed"]), flush=True)
    p246.write_text(dumps(res246), encoding="utf-8")
