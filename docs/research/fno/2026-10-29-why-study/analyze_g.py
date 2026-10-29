"""O29g analysis -> results.json (per lot first: the real-money test trades one lot)."""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab_g  # noqa: E402

Y = lab_g.Y
RAW = lab_g.LOCAL / "results-raw.json"


def per_lot(trades, window, days):
    inside = set(Y.O27F.sessions_in(window, days))
    daily = {d: 0.0 for d in inside}
    n = 0
    for t in trades:
        if t.get("net_pnl") is None or t["entry_time"][:10] not in inside:
            continue
        daily[t["entry_time"][:10]] += float(t["net_pnl"]) / max(1, int(t.get("lots_at_exit") or 1))
        n += 1
    months, weeks = defaultdict(float), defaultdict(float)
    for d, v in daily.items():
        months[d[:7]] += v
        weeks[date.fromisoformat(d).isocalendar()[:2]] += v
    run = peak = dd = 0.0
    for d in sorted(daily):
        run += daily[d]
        peak = max(peak, run)
        dd = max(dd, peak - run)
    best = max([0.0, *daily.values()])
    return {"trades": n, "net": round(sum(daily.values())), "without_best_day": round(sum(daily.values()) - best),
            "worst_day": round(min([0.0, *daily.values()])), "dd": round(dd),
            "green_months": sum(v > 0 for v in months.values()), "red_months": sum(v < 0 for v in months.values()),
            "green_weeks": sum(v > 0 for v in weeks.values()), "red_weeks": sum(v < 0 for v in weeks.values()),
            "monthly": {k: round(v) for k, v in sorted(months.items())}}


def one_lot_weeks(trades, days, start=15000.0, floor=7000.0, lot=65):
    sys.path.insert(0, str(Y.ROOT / "python-engine"))
    from fno_costs import calc_fno_costs
    weeks = defaultdict(list)
    for d in days:
        weeks[date.fromisoformat(d).isocalendar()[:2]].append(d)
    closed = sorted((t for t in trades if t.get("net_pnl") is not None), key=lambda t: t["entry_time"])
    ends = []
    for wk in weeks.values():
        cash, held_until, per_day = start, "", defaultdict(int)
        for t in closed:
            d = t["entry_time"][:10]
            if d not in wk or t["entry_time"] < held_until or per_day[d] >= 3 or cash < floor:
                continue
            if t["entry_premium"] * lot + calc_fno_costs(t["entry_premium"], t["entry_premium"], lot) > cash:
                continue
            cash += float(t["net_pnl"]) / max(1, int(t.get("lots_at_exit") or 1))
            held_until, per_day[d] = t["exit_time"], per_day[d] + 1
        ends.append(cash)
    return {"weeks": len(ends), "up": sum(e > start for e in ends), "down": sum(e < start for e in ends),
            "worst_end": round(min(ends)), "mean_end": round(statistics.fmean(ends))}


def main() -> None:
    raw = json.loads(RAW.read_text())
    days = json.loads((Y.HERE / "freeze.json").read_text())["bindings"]["year_sessions"]
    trades = {name: raw["trades"][key] for name, key in raw["books"].items()}
    windows = {"FULL": lab_g.FULL, "H1": lab_g.H1, "H2": lab_g.H2}
    m = {name: {w: per_lot(t, span, days) for w, span in windows.items()} for name, t in trades.items()}

    selection = {}
    for c in Y.NAMED:
        rows = {g: m[f"{c}|{g}"] for g in lab_g.GATES}
        pick_h1 = max(lab_g.GATES, key=lambda g: (rows[g]["H1"]["without_best_day"], -lab_g.GATES.index(g)))
        pick_h2 = max(lab_g.GATES, key=lambda g: (rows[g]["H2"]["without_best_day"], -lab_g.GATES.index(g)))
        selection[c] = {"H1_pick": pick_h1, "its_H2": rows[pick_h1]["H2"]["net"], "always_H2": rows["ALWAYS"]["H2"]["net"],
                        "H2_pick": pick_h2, "its_H1": rows[pick_h2]["H1"]["net"], "always_H1": rows["ALWAYS"]["H1"]["net"]}
        selection[c]["beats_always_both_ways"] = (selection[c]["its_H2"] > selection[c]["always_H2"]
                                                  and selection[c]["its_H1"] > selection[c]["always_H1"])

    null_effect = {}
    for g in ("adx_abs20:HIGH", "trend_regime:HIGH"):
        diffs = [m[f"NULL{i:02d}|{g}"]["FULL"]["net"] - m[f"NULL{i:02d}|ALWAYS"]["FULL"]["net"] for i in range(20)]
        null_effect[g] = {"median_change": round(statistics.median(diffs)), "improved": sum(x > 0 for x in diffs),
                          "gated_median_net": round(statistics.median(m[f"NULL{i:02d}|{g}"]["FULL"]["net"] for i in range(20))),
                          "always_median_net": round(statistics.median(m[f"NULL{i:02d}|ALWAYS"]["FULL"]["net"] for i in range(20)))}

    ranked = sorted((n for n in m if not n.startswith("NULL")),
                    key=lambda n: (min(m[n]["H1"]["net"], m[n]["H2"]["net"]), m[n]["FULL"]["net"]), reverse=True)
    top = ranked[:12]
    weeks = {n: one_lot_weeks(trades[n], days) for n in top + ["UNION_DRIVE_LIVE", "TPB|ALWAYS"]}
    out = {"schema": "o29g_results_v1", "freeze_sha256": Y.grid._sha(HERE / "freeze.json"), "metrics_per_lot": m,
           "selection_two_fold": selection, "null_gate_effect": null_effect,
           "ranked_by_worse_half": ranked, "one_lot_weeks": weeks, "status": lab_g.RULE["status"]}
    Y.write_new(HERE / "results.json", out)
    print("two-fold gate selection (per lot):")
    for c, s in selection.items():
        print(f"  {c:8} H1 pick {s['H1_pick']:20} -> H2 {s['its_H2']:>7} vs ALWAYS {s['always_H2']:>7} | "
              f"H2 pick {s['H2_pick']:20} -> H1 {s['its_H1']:>7} vs ALWAYS {s['always_H1']:>7} | both {s['beats_always_both_ways']}")
    print("gates on random-entry books:", null_effect)
    print(f"{'book':40} {'FULL':>7} {'H1':>7} {'H2':>7} {'t':>4} {'worst':>6} {'dd':>6} {'g/r mo':>6} {'g/r wk':>6}")
    for n in ranked[:25] + ["UNION_DRIVE_LIVE"]:
        f = m[n]["FULL"]
        print(f"{n:40} {f['net']:7} {m[n]['H1']['net']:7} {m[n]['H2']['net']:7} {f['trades']:4} {f['worst_day']:6} "
              f"{f['dd']:6} {f['green_months']:2}/{f['red_months']:<2}  {f['green_weeks']:2}/{f['red_weeks']:<2}")
    print("one-lot weeks from Rs 15,000:", json.dumps(weeks))
    for n in ranked[:6]:
        print(n, m[n]["FULL"]["monthly"])


if __name__ == "__main__":
    main()
