"""Frozen O30p scoring: report every candidate including failed offspring."""
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab_p as N
sys.path.insert(0, str(N.C.ROOT / "docs/research/fno/2026-10-30-case-study"))
import analyze_c as A
import analyze_g as AG


def score(metrics, unknown, null):
    halves = [f"{y}_{h}" for y in A.YEARS for h in ("H1", "H2")]
    verdict = {}
    for n, m in metrics.items():
        if not n.startswith("P|"):
            continue
        verdict[n] = (all(m[y]["net"] > metrics["REF|" + n.split("|")[1]][y]["net"]
                         and m[y]["trades"] >= 40 and m[y]["stress200"] > 0
                         and m[y]["without_best_day"] > 0 and m[y]["net"] > null[y]
                         and m[y]["dd"] <= 1.25 * metrics["REF|" + n.split("|")[1]][y]["dd"]
                         and unknown[y][n] == 0 for y in A.YEARS)
                      and sum(m[h]["net"] >= metrics["REF|" + n.split("|")[1]][h]["net"] for h in halves) >= 3)
    selection = {}
    for parent in ('TPB','BEST'):
        candidates = sorted(n for n in verdict if n.startswith('P|'+parent+'|'))
        for train,test in (('2025','2026'),('2026','2025')):
            pick=min(candidates,key=lambda n:(-min(metrics[n][f'{train}_{h}']['stress200'] for h in ('H1','H2')),n))
            selection[parent+'_'+train]={'pick':pick,'test_year':test,'test_net':metrics[pick][test]['net'],
                'beats_best':metrics[pick][test]['net']>metrics['REF|'+parent][test]['net']}

    return {"candidates_pass": verdict, "selection": selection,
            "selection_pass_both_ways": all(s["beats_best"] for s in selection.values())}


def main():
    sha = N.Y.grid._sha(HERE / "freeze.json")
    days, trades, unknown = A.sessions(), {}, {}
    for y in A.YEARS:
        raw = json.loads((N.LOCAL / f"results-raw-{y}.json").read_text())
        assert raw["freeze_sha256"] == sha and raw["year"] == y
        trades[y] = {n: raw["trades"][k] for n, k in raw["books"].items()}
        unknown[y] = {n: sum(t.get("net_pnl") is None for t in ts) for n, ts in trades[y].items()}
    metrics = {}
    for n in trades["2025"]:
        spans = {y: (y, N.C.WINDOWS[y]) for y in A.YEARS}
        spans.update({f"{y}_{h}": (y, span) for y in A.YEARS
                      for h, span in zip(("H1", "H2"), N.C.HALVES[y])})
        m = {key: AG.per_lot(trades[y][n], span, days[y]) for key, (y, span) in spans.items()}
        m["both"] = AG.per_lot(trades["2025"][n] + trades["2026"][n], A.BOTH, days["2025"] + days["2026"])
        for row in m.values():
            row.update(stress200=row["net"] - 200 * row["trades"], stress300=row["net"] - 300 * row["trades"])
        m["cash12500_week_proxy"] = AG.one_lot_weeks(
            trades["2025"][n] + trades["2026"][n], days["2025"] + days["2026"], start=12500.)
        metrics[n] = m
    assert (metrics["REF|LIVE"]["2025"]["net"], metrics["REF|LIVE"]["2026"]["net"]) == (271, 80912), "baseline parity failed"
    null = {y: statistics.median(metrics[f"NULL{i:02d}"][y]["net"] for i in range(20)) for y in A.YEARS}
    out = {"schema": "o30p_results_v1", "freeze_sha256": sha, "rule": N.RULE,
           "verdict": score(metrics, unknown, null), "null_median": null,
           "unresolved": unknown, "metrics_per_lot": metrics,
           "limitations": ["2025 and 2026 have already been seen; cross-year selection is diagnostic",
                           "minute close/spread model, not live executable quotes; fixed 65-unit current lot",
                           "stress holds trades fixed; does not replay cash/entry changes from worse prices",
                           "cash12500_week_proxy filters multi-lot parent trades, not exact one-lot portfolio replay",
                           "2024 and forward sessions untouched; no Production changes"]}
    N.Y.write_new(HERE / "results.json", out)
    print(json.dumps(out["verdict"], indent=2))
    for n in sorted(metrics):
        if n.startswith("NULL"):
            continue
        print(n, json.dumps({y: {k: metrics[n][y][k] for k in ("net", "trades", "dd", "stress200")}
                             for y in ("2025", "2026")}))


if __name__ == "__main__":
    main()
