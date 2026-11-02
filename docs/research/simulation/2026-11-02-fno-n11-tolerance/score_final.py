"""The final book's verdict, by PLAN_FINAL.md's checks, from saved replays only. Writes results-final.json. Nothing here changes a book or a threshold."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "2026-11-01-fno-n09")]
import score as S  # noqa: E402  (the first freeze's own measures, unedited)
from analyze_panel import all_weeks, cscv, weekly  # noqa: E402

V, LOCAL, YEARS = S.V, S.LOCAL, S.YEARS
BASE, N11_ACCOUNT = S.BASE, S.N11_ACCOUNT
BAR_DAY, BAR_TRADE = -6127, -6250


def rows_of(name):
    return S.rows_of("fpanel", name)


def account(tag):
    eq = pk = 250000.0
    fall, low = 0.0, eq
    for y in YEARS:
        for t in sorted(V.load(LOCAL, "fcarry", y, tag)["trades"], key=lambda r: r["exit_time"]):
            eq += float(t["net_pnl"])
            pk = max(pk, eq)
            low = min(low, eq)
            fall = max(fall, (pk - eq) / pk)
    return {"end": round(eq), "fall": round(fall * 100, 2), "lowest": round(low)}


def overfit() -> dict:
    """This study's whole family, every phase, with this book's panel added, exact duplicates removed."""
    weeks = all_weeks()
    index = {w: i for i, w in enumerate(weeks)}
    seen, names, columns = set(), [], []
    for phase in ("screen", "screen2", "screen3", "screen4", "screen5", "panel", "fpanel"):
        for name in json.loads((LOCAL / f"keys-{phase}-2024.json").read_text(encoding="utf-8")):
            if name == "DOUBLE":
                continue
            row = np.zeros(len(weeks))
            for w, v in weekly([t for y in YEARS for t in V.load(LOCAL, phase, y, name)["trades"]]).items():
                if w in index:
                    row[index[w]] += v
            key = row.round(2).tobytes()
            if key not in seen:
                seen.add(key)
                names.append(f"{phase}|{name}")
                columns.append(row)
    matrix = np.array(columns).T
    totals = matrix.sum(axis=0)
    actual = cscv(matrix, blocks=16)
    rng = np.random.default_rng(29)
    shuffled = [cscv(matrix[rng.permutation(matrix.shape[0])], blocks=16)["pbo"] for _ in range(20)]
    me = next(i for i, n in enumerate(names) if n.endswith("S6250_K1.75") or n.endswith("|FINAL") or n.endswith("|L6250"))
    return {"books": len(names), "pbo": round(actual["pbo"], 3), "median_out_of_sample_percentile": round(actual["median_out_of_sample_percentile"], 3), "weeks_shuffled_jointly": {"median": round(float(np.median(shuffled)), 3), "low": round(min(shuffled), 3), "high": round(max(shuffled), 3)},
            "rank_by_total": int((totals > totals[me]).sum()) + 1, "identified_as": names[me], "reading": "On pure noise this estimator averages 0.51 to 0.55 with a standard deviation of about 0.18. All data seen."}


def main() -> None:
    me_rows, base = rows_of("FINAL"), rows_of("N11")
    me = S.summary(me_rows)
    assert S.summary(base)["sum"] == BASE["sum"], "the N11 reference must come back"
    double = S.summary(rows_of("DOUBLE"))
    neighbours = {n: S.summary(rows_of(n)) for n in ("K1.5", "K2.0", "L5500", "L7000")}
    controls = {n: S.summary(rows_of(n)) for n in ("NO_READING", "REVERSED")}
    accounts = {t: account(t) for t in N11_ACCOUNT}
    near = [accounts[t]["end"] for t in ("195", "198", "199", "200", "201", "202", "205")]
    audit = {y: json.loads((HERE / f"audit-final-{y}.json").read_text(encoding="utf-8")) for y in YEARS}
    parity = {y: json.loads((HERE / f"parity-final-{y}.json").read_text(encoding="utf-8")) for y in YEARS}
    checks = {
        "1_sum_above_n11": me["sum"] > BASE["sum"],
        "2_worst_day_no_larger_than_6_127": me["worst_day"] >= BAR_DAY,
        "3_fall_no_larger_than_n11": me["fall"] <= BASE["fall"],
        "4_worst_trade_no_larger_than_6_250": me["worst_trade"] >= BAR_TRADE,
        "5_every_year_at_or_above_n11_within_500": all(me["years"][y] >= BASE["years"][y] - 500 for y in YEARS),
        "6_double_cost_above_n11": double["sum"] > BASE["double"],
        "7_without_top_five_above_n11": me["without_top5"] > BASE["without_top5"],
        "8_neighbours": all(s["sum"] > BASE["sum"] and s["worst_day"] >= BAR_DAY for s in neighbours.values()),
        "9_account_every_cost": all(accounts[t]["end"] >= N11_ACCOUNT[t] for t in N11_ACCOUNT) and (max(near) - min(near)) / min(near) <= 0.05 and all(accounts[t]["lowest"] >= 212500 for t in accounts),
        "10_audit": all(a["passed"] for a in audit.values()),
        "11_engine_parity": all(p["mismatch_count"] == 0 for p in parity.values()),
    }
    up = S.raised(me_rows, base)
    gains = sorted((g for y in YEARS for _t, _b, g in up[y]), reverse=True)
    by_year = {y: round(sum(g for _t, _b, g in up[y])) for y in YEARS}
    knock = {y: me["years"][y] - BASE["years"][y] - by_year[y] for y in YEARS}
    hidden = {y: {"sum_on_the_other_three": sum(v for k, v in by_year.items() if k != y), "would_be_chosen": sum(v for k, v in by_year.items() if k != y) > 0, "on_the_hidden_year": by_year[y]} for y in YEARS}
    tolerance = {when for y in YEARS for when in parity[y]["raised_at"]}
    own = [g for y in YEARS for t, _b, g in up[y] if t["entry_time"] in tolerance]
    stance = [(t["entry_time"][:16], t["entry_premium"], round(g)) for y in YEARS for t, _b, g in up[y] if t["entry_time"] not in tolerance]
    result = {"schema": "n11t_final_results_v1", "all_data_seen": True, "tolerance_second_lots": {"count": len(own), "wins": sum(g > 0 for g in own), "own_total": round(sum(own)), "top_three": round(sum(sorted(own, reverse=True)[:3]))},
              "two_lots_by_the_stance_as_a_knock_on": stance, "placebo_tolerance_only": S.placebo(base, len(own), sum(own)), "final": me, "n11": BASE, "double": double, "neighbours": neighbours, "controls": controls, "accounts": accounts, "n11_account": N11_ACCOUNT, "near_cost_spread_pct": round((max(near) - min(near)) / min(near) * 100, 2),
              "checks": checks, "meets_the_bar_on_the_seen_years": all(checks.values()),
              "second_lots": {"count": len(gains), "wins": sum(g > 0 for g in gains), "own_by_year": by_year, "own_total": round(sum(gains)), "knock_on_by_year": {y: round(v) for y, v in knock.items()}, "top_three": round(sum(gains[:3])), "worst": round(min(gains, default=0.0)),
                              "list": [(t["entry_time"][:16], t["member"], t["direction"][0], t["entry_premium"], t["exit_reason"][:13], round(b["net_pnl"]), round(t["net_pnl"])) for y in YEARS for t, b, _g in up[y]]},
              "placebo": S.placebo(base, len(gains), sum(gains)), "hidden_year": hidden, "overfit": overfit(),
              "parity": {y: {k: parity[y][k] for k in ("decisions_compared", "research_raised", "engine_raised", "by_reason", "stops_compared", "stops_tightened", "raised_but_not_entered", "mismatch_count")} for y in YEARS}, "audit": {y: audit[y]["checks"] for y in YEARS}}
    (HERE / "results-final.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("final", "checks", "meets_the_bar_on_the_seen_years", "tolerance_second_lots", "two_lots_by_the_stance_as_a_knock_on", "placebo", "placebo_tolerance_only", "hidden_year", "near_cost_spread_pct", "overfit")}, indent=1))
    print("second lots", {k: v for k, v in result["second_lots"].items() if k != "list"})
    print("list", result["second_lots"]["list"])
    print("accounts", {t: accounts[t]["end"] for t in accounts}, "lowest", min(accounts[t]["lowest"] for t in accounts), "fall", accounts["200"]["fall"])
    print("double", double["sum"], double["worst_day"], double["fall"], "controls", {k: (v["sum"], v["fall"]) for k, v in controls.items()})
    print("parity", result["parity"])


if __name__ == "__main__":
    main()
