"""Post-freeze reporting only. The acceptance thresholds are in committed PLAN.md."""
from __future__ import annotations
import json
import math
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
LOCAL = HERE / "_local"
YEARS = ("2023", "2024", "2025", "2026")


def load(phase, year, name):
    key = json.loads((LOCAL / f"keys-{phase}-{year}.json").read_text())[name]
    return json.loads((LOCAL / "evals" / f"{key}.json").read_text())


def summarize(rows, capital=250000.):
    equity = peak = capital
    drawdown = 0.
    daily = defaultdict(float)
    wins, losses = [], []
    for t in sorted(rows, key=lambda r: r["exit_time"]):
        n = float(t["net_pnl"])
        equity += n
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)
        daily[t["exit_time"][:10]] += n
        (wins if n > 0 else losses).append(n)
    nets = sorted(wins + losses, reverse=True)
    return {"net": equity - capital, "end": equity, "trades": len(rows), "wins": len(wins),
            "closed_drawdown_pct": drawdown * 100, "worst_trade": min(nets, default=0.),
            "worst_day": min(daily.values(), default=0.), "best_trade": max(nets, default=0.),
            "without_best": sum(nets[1:]), "without_best5": sum(nets[5:]),
            "profit_factor": sum(wins) / -sum(losses) if sum(losses) < 0 else None,
            "daily": dict(daily), "last_exit": rows[-1]["exit_time"] if rows else None}


def whole(fresh):
    return {"net": sum(s["net"] for s in fresh.values()),
            "worst_day": min(s["worst_day"] for s in fresh.values()),
            "worst_trade": min(s["worst_trade"] for s in fresh.values()),
            "worst_annual_closed_drawdown_pct": max(s["closed_drawdown_pct"] for s in fresh.values()),
            "trades": sum(s["trades"] for s in fresh.values())}


def paired_weeks(candidate, baseline):
    weeks = []
    for y in YEARS:
        day = date(int(y), 1, 1)
        end = date(int(y), 10, 28) if y == "2026" else date(int(y), 12, 31)
        while day <= end:
            iso = tuple(day.isocalendar()[:2])
            if iso not in weeks:
                weeks.append(iso)
            day += timedelta(days=1)
    out = []
    for rows in (candidate, baseline):
        net = defaultdict(float)
        for t in rows:
            iso = tuple(date.fromisoformat(t["exit_time"][:10]).isocalendar()[:2])
            net[iso] += t["net_pnl"]
        out.append(np.array([net[w] for w in weeks]))
    delta = out[0] - out[1]
    rng = np.random.default_rng(110901)
    sampled = []
    for _ in range(4096):
        ix = np.concatenate([(np.arange(4) + i) % len(delta) for i in rng.integers(0, len(delta), math.ceil(len(delta) / 4))])[:len(delta)]
        sampled.append(float(delta[ix].sum()))
    se = float(delta.std(ddof=1) / math.sqrt(len(delta)))
    return {"weeks": len(weeks), "mean_weekly_delta": float(delta.mean()), "total_delta": float(delta.sum()),
            "paired_t": float(delta.mean() / se) if se else None,
            "four_week_block_bootstrap_95pct_total_delta": list(np.percentile(sampled, [2.5, 97.5])),
            "draws": 4096, "seed": 110901, "qualification": "descriptive only, all data previously studied"}


def opportunity(candidate, baseline):
    def key(t):
        return (t["entry_time"], t["tradingsymbol"], t["bar_ts"], t["initial_stop_underlying"], t["initial_target_underlying"])
    a, b = {key(t): t for t in candidate}, {key(t): t for t in baseline}
    assert len(a) == len(candidate) and len(b) == len(baseline)
    shared, added, missed = a.keys() & b.keys(), a.keys() - b.keys(), b.keys() - a.keys()
    result = {"matched": len(shared), "matched_delta": sum(a[k]["net_pnl"] - b[k]["net_pnl"] for k in shared),
              "resized": sum(a[k]["initial_quantity"] != b[k]["initial_quantity"] for k in shared),
              "added_winners": sum(a[k]["net_pnl"] > 0 for k in added),
              "added_winners_net": sum(a[k]["net_pnl"] for k in added if a[k]["net_pnl"] > 0),
              "added_losers": sum(a[k]["net_pnl"] <= 0 for k in added),
              "added_losers_net": sum(a[k]["net_pnl"] for k in added if a[k]["net_pnl"] <= 0),
              "missed_winners": sum(b[k]["net_pnl"] > 0 for k in missed),
              "missed_winners_net": sum(b[k]["net_pnl"] for k in missed if b[k]["net_pnl"] > 0),
              "avoided_losers": sum(b[k]["net_pnl"] <= 0 for k in missed),
              "avoided_losers_net": sum(b[k]["net_pnl"] for k in missed if b[k]["net_pnl"] <= 0)}
    delta = (result["matched_delta"] + result["added_winners_net"] + result["added_losers_net"]
             - result["missed_winners_net"] - result["avoided_losers_net"])
    assert abs(delta - sum(t["net_pnl"] for t in candidate) + sum(t["net_pnl"] for t in baseline)) < .001
    result["total_delta"] = delta
    return result


def main():
    fresh = {name: {} for name in ("N08", "S_VOL", "VOL_CLOCK", "CUSHION")}
    costs, carry, rows = {}, {}, {}
    for name in fresh:
        phase = "primary" if name in ("VOL_CLOCK", "CUSHION") else "controls"
        rows[name] = {y: load(phase, y, name)["trades"] for y in YEARS}
        fresh[name] = {y: summarize(rows[name][y]) for y in YEARS}
        cr = [t for y in YEARS for t in load("carry", y, name)["trades"]]
        carry[name] = {"summary": summarize(cr), "by_year": {y: summarize(load("carry", y, name)["trades"])["net"] for y in YEARS}}
    for name in ("N08", "VOL_CLOCK", "CUSHION"):
        costs[name] = {c: {y: summarize(load("costs", y, name + "|" + c)["trades"]) for y in YEARS} for c in ("none", "double")}
    base = whole(fresh["N08"])
    verdict, stats, changes = {}, {}, {}
    for name in ("VOL_CLOCK", "CUSHION"):
        got = whole(fresh[name])
        common = {"continuous_end_not_worse": carry[name]["summary"]["end"] >= carry["N08"]["summary"]["end"],
                  "double_extra_cost_aggregate_positive": whole(costs[name]["double"])["net"] > 0,
                  "annual_drawdown_not_worse": got["worst_annual_closed_drawdown_pct"] <= base["worst_annual_closed_drawdown_pct"] + 1e-8}
        risk = {**common, "retain_90pct_profit": got["net"] >= .9 * base["net"],
                "worst_day_20pct_smaller": got["worst_day"] >= .8 * base["worst_day"],
                "previously_positive_years_positive": all(fresh[name][y]["net"] > 0 for y in ("2024", "2025", "2026"))}
        profit = {**common, "net_above_n08": got["net"] > base["net"],
                  "worst_day_not_worse": got["worst_day"] >= base["worst_day"],
                  "2023_not_worse": fresh[name]["2023"]["net"] >= fresh["N08"]["2023"]["net"]}
        verdict[name] = {"risk_checks": risk, "risk_route_pass": all(risk.values()),
                         "profit_checks": profit, "profit_route_pass": all(profit.values()),
                         "meaning": "seen-data screen only; no qualification/deployment"}
        stats[name] = paired_weeks([t for y in YEARS for t in rows[name][y]], [t for y in YEARS for t in rows["N08"][y]])
        changes[name] = {y: opportunity(rows[name][y], rows["N08"][y]) for y in YEARS}
    result = {"schema": "n091_results_v1", "all_data_seen": True, "fresh": fresh,
              "aggregates": {n: whole(v) for n, v in fresh.items()}, "costs": costs, "continuous": carry,
              "verdicts": verdict, "weekly_uncertainty": stats, "opportunity_cost": changes}
    (HERE / "results.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("aggregates", "verdicts", "weekly_uncertainty")}, indent=2))


if __name__ == "__main__":
    main()
