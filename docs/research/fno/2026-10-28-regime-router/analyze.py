"""O28 analysis of _local/results-raw.json under the frozen RULE. Writes results.json and prints the summary.

python docs/research/fno/2026-10-28-regime-router/analyze.py
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import statistics
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("o28_router", HERE / "router.py")
router = importlib.util.module_from_spec(spec)
sys.modules["o28_router"] = router
spec.loader.exec_module(router)
metrics, sessions_in, digest = router.O27F.metrics, router.O27F.sessions_in, router.digest
SHORT = ("sessions", "trades", "unresolved", "net", "net_without_best_day", "dd", "stressed", "win_rate",
         "profit_factor", "green_days", "red_days", "green_weeks", "red_weeks", "worst_day")


def short(m: dict) -> dict:
    return {k: m[k] for k in SHORT}


def permutation(values: np.ndarray, labels: np.ndarray, rng: np.random.Generator, n: int = 20000) -> float:
    observed = values[labels].mean() - values[~labels].mean()
    hits = 0
    for _ in range(n):
        perm = rng.permutation(labels)
        hits += abs(values[perm].mean() - values[~perm].mean()) >= abs(observed) - 1e-9
    return (hits + 1) / (n + 1)


def holm(pvalues: dict) -> dict:
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    out, running, m = {}, 0.0, len(ordered)
    for i, (key, p) in enumerate(ordered):
        running = max(running, min(1.0, (m - i) * p))
        out[key] = running
    return out


def engine_regime(days: list[str]) -> dict:
    db = router.DATA / "fno-replay.sqlite"
    con = sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT bar_ts, regime FROM fno_signals WHERE regime IS NOT NULL AND regime!='' AND "
                           "substr(bar_ts,12,8)<='09:40:00' ORDER BY evaluated_at").fetchall()
    finally:
        con.close()
    out = {}
    for bar_ts, regime in rows:
        if bar_ts[:10] in days:
            out[bar_ts[:10]] = regime  # the newest regime logged by 09:40 that day
    return out


def main() -> None:
    raw = json.loads((router.LOCAL / "results-raw.json").read_text(encoding="utf-8"))
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    assert raw["freeze_sha256"] == router.grid._sha(HERE / "freeze.json")
    days, trades, table, past = raw["days"], raw["trades"], raw["table"], raw["hindsight"]
    folds = [f for f in frozen["folds"] if f["test"]]
    oos_days = [d for f in folds for d in sessions_in(f["test"], days)]
    t = lambda config: trades[digest(config)]  # noqa: E731

    def oos(config_by_fold: dict) -> dict:
        """Each fold's config sliced to its own test window, summed."""
        per, joined = {}, []
        for f in folds:
            test = sessions_in(f["test"], days)
            m = metrics(t(config_by_fold[f["name"]]), test)
            per[f["name"]] = {"sessions": len(test), "trades": m["trades"], "net": m["net"]}
            joined += [x for x in t(config_by_fold[f["name"]]) if x["entry_time"][:10] in test]
        total = metrics(joined, oos_days)
        return {"folds": per, **short(total)}

    fixed = {"UNION": router.UNION, **router.THEORY,
             **{f"{c}_ALONE": router.single(c, "ALWAYS") for c in router.COMPONENTS}}
    routers = raw["routers"]
    walk = oos({f["name"]: routers[f["name"]] for f in folds})
    baselines = {name: oos({f["name"]: cfg for f in folds}) for name, cfg in fixed.items()}
    nulls = [oos({f["name"]: cfg for f in folds})["net"] for cfg in router.null_configs()]
    null_rank = sum(n < walk["net"] for n in nulls) / len(nulls)
    union_folds = baselines["UNION"]["folds"]
    checks = {
        "oos_net_gt_union": walk["net"] > baselines["UNION"]["net"],
        "oos_net_gt_zero": walk["net"] > 0,
        "oos_net_gt_shipped": walk["net"] > baselines["SHIPPED_ALONE"]["net"],
        "ge_union_in_2_of_3_folds": sum(walk["folds"][k]["net"] >= union_folds[k]["net"] for k in walk["folds"]) >= 2,
        "ge_null_p90": walk["net"] >= float(np.percentile(nulls, 90)),
    }
    verdict = "CONDITIONS_ADD_VALUE_ON_THIS_TEST" if all(checks.values()) else "CONDITIONS_NOT_SHOWN_TO_ADD_VALUE"

    full = {name: short(metrics(t(cfg), days)) for name, cfg in fixed.items()}
    full["FINAL_ROUTER_IN_SAMPLE"] = short(metrics(t(routers["FINAL"]), days))
    gated = {c: {o: short(metrics(t(router.single(c, o)), days)) for o in router.OPTIONS if o != "NEVER"}
             for c in router.COMPONENTS}

    # ---- what conditions each strategy won under (descriptive, all 29 sessions) ----
    rng = np.random.default_rng(2026102802)
    daily = {c: metrics(t(router.single(c, "ALWAYS")), days)["daily"] for c in router.COMPONENTS}
    cond, pvals = {}, {}
    for c in router.COMPONENTS:
        cond[c] = {}
        for f in router.FEATURES:
            sides = {d: table[d]["side"][f] for d in days if table.get(d) and table[d]["side"][f]}
            hi = [daily[c][d] for d in sides if sides[d] == "HIGH"]
            lo = [daily[c][d] for d in sides if sides[d] == "LOW"]
            values = np.array([daily[c][d] for d in sides])
            labels = np.array([sides[d] == "HIGH" for d in sides])
            p = permutation(values, labels, rng) if labels.any() and (~labels).any() else 1.0
            pvals[f"{c}|{f}"] = p
            cond[c][f] = {"HIGH": {"days": len(hi), "net": round(sum(hi), 2), "trading_days": sum(v != 0 for v in hi),
                                   "mean_day": round(statistics.fmean(hi), 2) if hi else None},
                          "LOW": {"days": len(lo), "net": round(sum(lo), 2), "trading_days": sum(v != 0 for v in lo),
                                  "mean_day": round(statistics.fmean(lo), 2) if lo else None},
                          "p": round(p, 4)}
    adjusted = holm(pvals)
    for key, p in adjusted.items():
        c, f = key.split("|")
        cond[c][f]["p_holm"] = round(p, 4)
    # [post hoc, added after the verdict] does each split point the same way in both halves (A, B)?
    halves = {}
    for c in router.COMPONENTS:
        halves[c] = {}
        for f in router.FEATURES:
            row = {}
            for half, window in (("A", router.O27F.A), ("B", router.O27F.B)):
                inside = [d for d in sessions_in(window, days) if table.get(d) and table[d]["side"][f]]
                hi = [daily[c][d] for d in inside if table[d]["side"][f] == "HIGH"]
                lo = [daily[c][d] for d in inside if table[d]["side"][f] == "LOW"]
                row[half] = round((statistics.fmean(hi) if hi else 0.0) - (statistics.fmean(lo) if lo else 0.0), 2)
            row["same_sign"] = (row["A"] > 0) == (row["B"] > 0) and row["A"] != 0 and row["B"] != 0
            halves[c][f] = row

    # ---- hindsight day type (explanation only) and whether 09:45 saw it coming ----
    trend_days = [d for d in days if past.get(d, {}).get("trend_day")]
    by_type = {c: {"trend_days": round(sum(daily[c][d] for d in trend_days), 2),
                   "other_days": round(sum(daily[c][d] for d in days if d not in trend_days), 2)}
               for c in router.COMPONENTS}
    foresight = {}
    for f in router.FEATURES:
        foresight[f] = {}
        for side in ("HIGH", "LOW"):
            picked = [d for d in days if table.get(d) and table[d]["side"][f] == side]
            foresight[f][side] = {"days": len(picked), "trend_days": sum(d in trend_days for d in picked)}
    regimes = engine_regime(days)
    by_regime = {}
    for c in router.COMPONENTS:
        by_regime[c] = {}
        for d in days:
            key = regimes.get(d, "NOT_LOGGED")
            by_regime[c].setdefault(key, {"days": 0, "net": 0.0})
            by_regime[c][key]["days"] += 1
            by_regime[c][key]["net"] = round(by_regime[c][key]["net"] + daily[c][d], 2)
    names = list(router.COMPONENTS)
    corr = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            x = np.array([daily[a][d] for d in days])
            y = np.array([daily[b][d] for d in days])
            both = sum((daily[a][d] > 0) and (daily[b][d] > 0) for d in days)
            rx, ry = x.argsort().argsort(), y.argsort().argsort()
            corr[f"{a}~{b}"] = {"spearman": round(float(np.corrcoef(rx, ry)[0, 1]), 3), "both_green_days": both}
    oracle = round(sum(max(0.0, *(daily[c][d] for c in names)) for d in days), 2)
    oracle_oos = round(sum(max(0.0, *(daily[c][d] for c in names)) for d in oos_days), 2)
    per_day = {d: {"side": table[d]["side"], "values": {f: (round(table[d][f], 4) if table[d][f] is not None else None)
                                                        for f in router.FEATURES},
                   "hindsight": past.get(d), "engine_regime": regimes.get(d),
                   "net": {c: daily[c][d] for c in names}} for d in days}

    results = {
        "freeze_sha256": raw["freeze_sha256"], "parity": raw["parity"], "warm_conflicts": raw["warm_conflicts"],
        "replays": len(trades), "oos_sessions": oos_days,
        "walk_forward": {"routers": routers, "oos": walk, "checks": checks, "verdict": verdict,
                         "null": {"count": len(nulls), "median": round(float(np.median(nulls)), 2),
                                  "p90": round(float(np.percentile(nulls, 90)), 2),
                                  "share_below_router": round(null_rank, 4),
                                  "share_positive": round(sum(n > 0 for n in nulls) / len(nulls), 4),
                                  "best": round(max(nulls), 2), "worst": round(min(nulls), 2)},
                         "baselines_oos": baselines,
                         "hindsight_oracle_oos_approx": oracle_oos},
        "full_in_sample": full, "gated_in_sample": gated, "hindsight_oracle_full_approx": oracle,
        "conditions": cond, "halves_post_hoc": halves, "by_hindsight_day_type": by_type, "trend_days": trend_days, "foresight": foresight,
        "by_engine_regime": by_regime, "daily_correlation": corr, "per_day": per_day,
    }
    (HERE / "results.json").write_text(json.dumps(results, indent=1, default=str), encoding="utf-8", newline="\n")

    print("VERDICT", verdict, checks)
    print("walk-forward OOS", {k: walk[k] for k in ("trades", "net", "dd", "green_days", "red_days")}, walk["folds"])
    for name, b in baselines.items():
        print(f"  {name:18s} OOS net {b['net']:>10.2f} trades {b['trades']:>3d} folds "
              f"{[b['folds'][k]['net'] for k in b['folds']]}")
    print("null", results["walk_forward"]["null"])
    print("oracle full/oos (approx)", oracle, oracle_oos)
    for name, m in full.items():
        print(f"  FULL {name:24s} net {m['net']:>10.2f} trades {m['trades']:>3d} nwbd {m['net_without_best_day']:>9.2f} "
              f"dd {m['dd']:>8.2f} days +{m['green_days']}/-{m['red_days']} weeks +{m['green_weeks']}/-{m['red_weeks']}")
    for c in names:
        print(c, {f: (cond[c][f]["HIGH"]["net"], cond[c][f]["LOW"]["net"], cond[c][f]["p"], cond[c][f]["p_holm"])
                  for f in router.FEATURES})
    print("halves (HIGH-LOW mean day, A | B)", {c: {f: (v["A"], v["B"], v["same_sign"]) for f, v in halves[c].items()}
                                                for c in names})
    print("by day type", by_type, "trend days", len(trend_days))
    print("foresight", foresight)
    print("regime", by_regime)
    print("corr", corr)


if __name__ == "__main__":
    main()
