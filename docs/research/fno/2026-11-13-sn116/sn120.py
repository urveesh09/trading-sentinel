"""SN120 - the scoreboard (PLAN.md): every SN91-SN119 candidate in one table, read from the committed result files
(nothing is rescored). Basis: HO = leave-one-year-out held out; IS = in-sample description; REAL = real quotes."""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
F = HERE.parent


def j(folder, name):
    return json.loads((F / folder / name).read_text(encoding="utf-8"))


if __name__ == "__main__":
    rows = []
    add = lambda sn, what, basis, result, verdict: rows.append({"SN": sn, "candidate": what, "basis": basis, "result": result, "verdict": verdict})  # noqa: E731
    r91 = j("2026-11-13-sn91", "results.json")
    add("91", "Rupees of wallet per lot 10k / 12.5k / 15k / 20k (Rs 30k growing, stop 3)", "IS",
        " / ".join(str(r91[f"Rs {x} per lot | grow from 30k, stop after 3"]["net"]) for x in (10000, 12500, 15000, 20000)), "15k stays")
    for sn, fname, key in (("93", "results-sn93.json", "drift calls"), ("94", "results-sn94.json", "failed breakout")):
        r = j("2026-11-13-sn92", fname)
        add(sn, key, "HO", r["verdict"]["held_out_sum"], "PASS" if r["verdict"]["PASS"] else "NOT PROVEN")
    r95 = j("2026-11-13-sn92", "results-sn95.json")["sides"]
    add("95", "10:00 cheap straddle (Gold-free, Rs 100/leg)", "HO", r95["gold-free | buy"]["verdict"]["held_out_sum"], "NOT PROVEN (forward watch SN95-L)")
    add("95", "rich iron fly (Gold-free)", "HO", r95["gold-free | sell"]["verdict"]["held_out_sum"], "NOT PROVEN")
    r96 = j("2026-11-13-sn92", "results-sn96.json")
    add("96", "NIFTY 50 components: next-30-minute forecast gain", "test months", f"{r96['info']['y30']['mse_gain_pct']}%", "no information")
    r97 = j("2026-11-13-sn92", "results-sn97.json")
    add("97", "drift / failed-break + futures volume", "HO", f"{r97['SN93 drift']['verdict']['held_out_sum']} / {r97['SN94 failed break']['verdict']['held_out_sum']}", "NOT PROVEN")
    r98 = j("2026-11-13-sn92", "results-sn98.json")
    add("98", "expiry mornings priced", "chronological", r98["stress"]["house 100/leg"]["pick_score"]["net"], "NOT PROVEN")
    r99 = j("2026-11-13-sn92", "results-sn99.json")
    add("99", "Gold sizing variants (C / G3 held out vs v5)", "HO", f"{r99['pass_detail']['C 30k sized']['sum']} vs {r99['pass_detail']['C 30k sized']['v5_sum']}; "
        f"{r99['pass_detail']['G3 (Gold)']['sum']} vs {r99['pass_detail']['G3 (Gold)']['v5_sum']}", "NOT PROVEN (reverses under stress / delay)")
    r100 = j("2026-11-13-sn92", "results-sn100.json")
    add("100", "Gold + SN93 / + SN94 (Rs 30k growing, stop 3)", "HO picks", f"{r100['verdict']['Gold + SN93']['30k grow stop 3']} / {r100['verdict']['Gold + SN94']['30k grow stop 3']}", "worse")
    r101 = j("2026-11-13-sn101", "results-sn101.json")
    add("101", "SN95's signal vs matched random days (p)", "permutation", r101["permutation_gold_free"]["p_value"], "information YES")
    r102 = j("2026-11-13-sn101", "results-sn102.json")["verdict"]["all days"]
    add("102", "remaining-value straddle model", "HO", f"{r102['total']} (w/o best 5 {r102['without_best_5']})", "NOT PROVEN")
    r103 = j("2026-11-13-sn101", "results-sn103.json")["summary"]
    add("103", "next- vs nearest-expiry straddle per Rs 1,000 premium", "REAL", r103["net per Rs 1,000 premium (205) near / next"], "description")
    r104 = j("2026-11-13-sn101", "results-sn104.json")["gold-free (SN95-L)"]["verdict"]
    add("104", "straddle giveback exit vs hold", "fixed rule", f"{r104['GB_total']} vs {r104['hold_total']}", "NOT PROVEN")
    r105 = j("2026-11-13-sn101", "results-sn105.json")
    add("105", "bank cancellation continuation (bp, 30 min)", "test months", round(r105["y30"]["continuation_in_cancel_state_mean_bp"], 1), "no information")
    r106 = j("2026-11-13-sn101", "results-sn106.json")
    add("106", "SN95-L on SENSEX (admitted)", "partial", r106["sensex_admitted"]["net"], "NOT PROVEN")
    r107 = j("2026-11-13-sn101", "results-sn107.json")
    add("107", "RBI-day implied volatility change by 10:30", "17 events", r107["iv_change"]["rbi_mean_n"][0], "description")
    r108 = j("2026-11-13-sn101", "results-sn108.json")
    add("108", "order-book absorption", "test month", "no gain", "no information" if not r108["INFORMATION_PASS"] else "information")
    r110 = j("2026-11-13-sn101", "results-sn110.json")["verdict"]["SN95-L strict"]
    add("110", "Gold + straddle in one wallet (+% at 30k fixed / growing)", "IS", f"{r110['increment_pct_30k_fixed']}% / {r110['increment_pct_30k_grow3']}%", "fails v6 bar")
    r113 = j("2026-11-13-sn111", "results-sn113.json")
    add("113", "Gold skip on low R_today", "HO", "v5 picked every year", "NOT PROVEN")
    r114 = j("2026-11-13-sn111", "results-sn114.json")["tables"]
    add("114", "strangle 1 step vs ATM straddle", "fixed set", f"{r114['strangle 1 step']['total']} vs {r114['ATM straddle']['total']}", "ATM stays")
    r115 = j("2026-11-13-sn111", "results-sn115.json")
    add("115", "measured signal-to-fill cost per lot (median / mean)", "REAL", f"{r115['signal_to_fill_per_lot']['median']} / {r115['signal_to_fill_per_lot']['mean']}", "Rs 205 is about right")
    for sn, fname in (("116", "results-sn116.json"), ("117", "results-sn117.json"), ("118", "results-sn118.json"), ("119", "results-sn119.json")):
        p = HERE / fname
        if not p.exists():
            continue
        r = json.loads(p.read_text(encoding="utf-8"))
        if sn == "116":
            b = r["total 45k | grow stop 3"]
            add("116", "Rs 45k growing (stop 3): Gold 45k vs Gold 30k + separate sleeve", "IS",
                f"{b['Gold 45k alone']['net']} vs {b['Gold 30k + separate 15k straddle sleeve']['net']}", "capital to Gold")
        if sn == "117":
            add("117", "Gold v5 at Rs 30k growing under measured costs (5th / 50th / 95th)", "calibrated", r["percentiles"]["30k grow stop 3"], "expectation")
        if sn == "118":
            s = r["configs"]["30k uncapped"]["summary"]
            add("118", "Rs 30k real account, no refills: median final multiple / share dead", "IS", f"{s['median_final_multiple']} / {s['share_dead']}", "survival")
        if sn == "119":
            add("119", "Gold v5 percentile vs random-entry Golds (N1 / N2, Rs 30k growing)", "null", f"{r['nulls']['N1 own days, random minute and side']['summary']['30k grow stop 3']['v5_percentile']} / "
                f"{r['nulls']['N2 random days, minute and side']['summary']['30k grow stop 3']['v5_percentile']}", r["reading"]["30k grow stop 3"])
    for x in rows:
        print(f"SN{x['SN']:>4} | {x['candidate'][:70]:70s} | {x['basis']:13s} | {str(x['result'])[:40]:40s} | {x['verdict']}")
    (HERE / "results-sn120.json").write_text(json.dumps(rows, indent=1, default=str), encoding="utf-8")
