"""O29b analysis: reads _local/results-raw.json (study.py run) and writes results.json. Explanation tables read the
whole session (hindsight) and are labelled so; the verdicts read only the walk-forward picks' test sessions."""
from __future__ import annotations

import importlib.util
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("o29b_study", HERE / "study.py")
study = importlib.util.module_from_spec(spec)
sys.modules["o29b_study"] = study
spec.loader.exec_module(study)
router = study.router


def _sum(rows: list[dict]) -> dict:
    by_day = {}
    for r in rows:
        by_day.update(r["by_day"])
    net = round(sum(r["net"] for r in rows), 2)
    return {"net": net, "trades": sum(r["trades"] for r in rows), "worst_day": min([0.0, *by_day.values()]),
            "green": sum(v > 0 for v in by_day.values()), "red": sum(v < 0 for v in by_day.values()),
            "per_fold": [r["net"] for r in rows]}


def main() -> None:
    raw = json.loads((study.LOCAL / "results-raw.json").read_text(encoding="utf-8"))
    trades, configs, days = raw["trades"], raw["configs"], raw["sessions"]
    d = study.digest
    out: dict = {"sessions": len(days), "window": [days[0], days[-1]]}

    # 1. Oct 28: what each strategy did (the union book and each strategy alone).
    today = {}
    for name, cfg in [("UNION", study.UNION), ("UNION_DRIVE", study.UNION_DRIVE),
                      *((c, study.single(c)) for c in study.BASE)]:
        today[name] = [{k: t.get(k) for k in ("component", "direction", "tradingsymbol", "entry_time", "entry_premium",
                                              "exit_time", "exit_premium", "exit_reason", "net_pnl")}
                       for t in trades[d(cfg)] if t["bar_ts"][:10] == study.TODAY]
    out["oct28_trades"] = today

    # 2. Hindsight: each session's shape against each strategy's result (explanation only).
    bars = study.futures_bars()
    states = study.bar_states(bars)
    shape = router.hindsight({t: f[["open", "high", "low", "close"]] for t, f in bars.items()})
    per_day = {}
    for day in days:
        last = list(states.get(day, {}).values())[-1] if states.get(day) else None
        row = {"trend_day": (shape.get(day) or {}).get("trend_day"), "body": (shape.get(day) or {}).get("body"),
               "er_close": last and round(last["er"], 3), "failed": last and last["failed"],
               "vwap_crosses": last and last["vx"], "drive": last and last["drive"]}
        for name, cfg in [("UNION", study.UNION), *((c, study.single(c)) for c in study.BASE)]:
            row[name] = raw["full"][d(cfg)]["by_day"].get(day, 0.0)
        per_day[day] = row
    out["per_day"] = per_day
    groups = {}
    for label, test in (("trend day", lambda r: r["trend_day"] is True),
                        ("not a trend day", lambda r: r["trend_day"] is False),
                        ("failed OR break by the close", lambda r: r["failed"] is True),
                        ("no failed OR break", lambda r: r["failed"] is False)):
        rows = [r for r in per_day.values() if test(r)]
        groups[label] = {"sessions": len(rows), **{n: round(sum(r[n] for r in rows), 2)
                                                   for n in ("UNION", *study.BASE)}}
    out["by_day_type"] = groups

    # 3. Each fixed filter on each strategy over all 31 sessions (in sample: every filter is one of eight).
    out["filters_in_sample"] = {c: {g: {k: raw["full"][d(study.single(c, g))][k]
                                        for k in ("trades", "net", "net_ex_best", "worst_day", "max_dd")}
                                    | {"oct28": raw["today"][d(study.single(c, g))]["net"]}
                                    for g in study.GATES} for c in study.BASE}

    # 4. Walk-forward: picks and their test sessions only.
    folds = [f for f in raw["folds"] if f.get("test_metrics")]
    oos = {k: _sum([f["test_metrics"][k] for f in folds]) for k in folds[0]["test_metrics"]}
    base = {k: _sum([f["baselines"][k] for f in folds]) for k in folds[0]["baselines"]}
    out["walk_forward"] = {"folds": [{"name": f["name"], "test": f["test"],
                                      "picks": {k: configs[v] for k, v in f["picks"].items()},
                                      "test_net": {k: m["net"] for k, m in f["test_metrics"].items()},
                                      "baseline_net": {k: m["net"] for k, m in f["baselines"].items()}}
                                     for f in folds],
                           "out_of_sample": oos, "baselines": base}
    verdict = {}
    for c in study.BASE:
        g, u = oos[f"G:{c}"], base[f"ungated:{c}"]
        verdict[f"G:{c}"] = g["net"] > u["net"] and g["worst_day"] >= u["worst_day"]
    f_folds = oos["F"]["per_fold"][:3]
    verdict["F"] = oos["F"]["net"] > 0 and sum(v > 0 for v in f_folds) >= 2 and oos["F"]["net"] > oos["NULL"]["net"]
    verdict["S"] = (oos["S"]["net"] > base["SHIPPED"]["net"] and oos["S"]["net"] > base["UNION"]["net"]
                    and oos["S"]["worst_day"] >= study.EXTREME_DAY)
    out["verdicts"] = verdict

    # 5. The FINAL fold's picks (forward-test candidates) with their full-period and Oct 28 figures.
    final = next(f for f in raw["folds"] if f["name"] == "FINAL")
    out["final_picks"] = {k: {"config": configs[v], "full": raw["full"][v], "oct28": raw["today"][v]["net"]}
                          for k, v in final["picks"].items()}

    # 6. Oct 28 for everything: how many of each kind made money that day, and the best of each.
    kinds = {"fades": [d(study.single(g)) for g in study.fade_genomes()],
             "nulls": [d(study.single(g)) for g in study.null_genomes()]}
    out["oct28_counts"] = {}
    for kind, keys in kinds.items():
        nets = [raw["today"][k]["net"] for k in keys]
        traded = [n for n in nets if n]
        out["oct28_counts"][kind] = {"configs": len(nets), "traded": len(traded), "made_money": sum(n > 0 for n in nets),
                                     "median_of_traded": round(statistics.median(traded), 2) if traded else None}
    fade_full = sorted(kinds["fades"], key=lambda k: raw["full"][k]["net"], reverse=True)
    out["fades_by_full_net"] = [{"config": configs[k]["comps"][0][2], "full": {x: raw["full"][k][x] for x in
                                 ("trades", "net", "net_ex_best", "worst_day", "max_dd", "green", "red")},
                                 "oct28": raw["today"][k]["net"]} for k in fade_full[:10]]
    out["fades_positive_full"] = sum(raw["full"][k]["net"] > 0 for k in kinds["fades"])
    out["nulls_positive_full"] = sum(raw["full"][k]["net"] > 0 for k in kinds["nulls"])
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8", newline="\n")
    print(json.dumps({"verdicts": verdict, "oos": {k: v["net"] for k, v in oos.items()},
                      "baselines": {k: v["net"] for k, v in base.items()}}, indent=1))


if __name__ == "__main__":
    main()
