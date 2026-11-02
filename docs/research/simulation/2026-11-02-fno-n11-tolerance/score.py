"""N11T's verdict, by PLAN.md's checks, and the honest checks, from saved replays only. Writes results.json. Nothing here changes a book or a threshold."""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
N11 = HERE.parent / "2026-11-02-fno-n11"
sys.path[:0] = [str(HERE), str(N11), str(next(p for p in HERE.parents if (p / "python-engine").is_dir()) / "python-engine")]
import screen_view as V  # noqa: E402
import stress as ST  # noqa: E402

V.LOCAL = HERE / "_local"
LOCAL = V.LOCAL
YEARS = V.YEARS
BASE = {"sum": 255365, "fall": 6.89, "double": 199622, "without_top5": 125490, "years": {"2023": -11537, "2024": 93256, "2025": 53095, "2026": 120551}}
N11_ACCOUNT = {"195": 519193, "198": 518827, "199": 518566, "200": 518305, "201": 518044, "202": 517783, "205": 517000, "180": 515071, "220": 512864, "400": 445026}
BAR_DAY, BAR_TRADE = -6127, -7500


def rows_of(phase, name):
    return {y: V.load(LOCAL, phase, y, name)["trades"] for y in YEARS}


def summary(rows):
    per = {y: V.stats(rows[y]) for y in YEARS}
    nets = sorted((float(t["net_pnl"]) for y in YEARS for t in rows[y]), reverse=True)
    return {"years": {y: round(per[y]["net"]) for y in YEARS}, "sum": round(sum(per[y]["net"] for y in YEARS)), "worst_day": round(min(per[y]["worst_day"] for y in YEARS)), "worst_trade": round(min(per[y]["worst_trade"] for y in YEARS)),
            "fall": round(max(per[y]["fall"] for y in YEARS), 2), "without_top5": round(sum(nets[5:])), "trades": sum(per[y]["n"] for y in YEARS), "two_lot_entries": sum(1 for y in YEARS for t in rows[y] if t["entry_qty"] >= 130)}


def account(tag):
    eq = pk = 250000.0
    fall, low = 0.0, eq
    for y in YEARS:
        for t in sorted(V.load(LOCAL, "carry", y, tag)["trades"], key=lambda r: r["exit_time"]):
            eq += float(t["net_pnl"])
            pk = max(pk, eq)
            low = min(low, eq)
            fall = max(fall, (pk - eq) / pk)
    return {"end": round(eq), "fall": round(fall * 100, 2), "lowest": round(low)}


def key(t):
    return (t["entry_time"], t["tradingsymbol"])


def second_lot_value(t):
    """What the second lot itself earned, from the raised trade: half its first-lot-sized money, fees and stress as the replay charged the difference."""
    return float(t["net_pnl"])


def raised(rows, base):
    out = {y: [] for y in YEARS}
    for y in YEARS:
        a = {key(t): t for t in base[y]}
        for t in rows[y]:
            b = a.get(key(t))
            if b is not None and t["entry_qty"] > b["entry_qty"]:
                out[y].append((t, b, float(t["net_pnl"]) - float(b["net_pnl"])))
    return out


def placebo(base, picked: int, actual: float) -> dict:
    """The same number of second lots given at random among N11's one-lot trades on above-usual days, valued as a second lot held to the same exit."""
    from fno_costs import calc_fno_costs
    pool = []
    for y in YEARS:
        for t in base[y]:
            if t["entry_qty"] == 65 and (t.get("n11_entry") or {}).get("vol_up"):
                e, x = t["entry_premium"], t["exit_premium"]
                pool.append((x - e) * 65 - (calc_fno_costs(e, x, 130) - calc_fno_costs(e, x, 65)) - (420.0 - 205.0))
    rng = random.Random(13)
    draws = sorted(sum(rng.sample(pool, picked)) for _ in range(20000))
    return {"eligible": len(pool), "picked": picked, "actual": round(actual), "median": round(draws[10000]), "p95": round(draws[19000]), "share_at_or_above_actual": sum(d >= actual for d in draws) / 20000}


def main() -> None:
    me_rows, base = rows_of("panel", "N11T"), rows_of("panel", "N11")
    me = summary(me_rows)
    assert summary(base)["sum"] == BASE["sum"], "the N11 reference must come back"
    double = summary(rows_of("panel", "DOUBLE"))
    neighbours = {n: summary(rows_of("panel", n)) for n in ("K1.5", "K2.0", "L6250", "L7000")}
    controls = {n: summary(rows_of("panel", n)) for n in ("NO_READING", "REVERSED")}
    accounts = {t: account(t) for t in N11_ACCOUNT}
    near = [accounts[t]["end"] for t in ("195", "198", "199", "200", "201", "202", "205")]
    audit = {y: json.loads((HERE / f"audit-{y}.json").read_text(encoding="utf-8")) for y in YEARS}
    checks = {
        "1_sum_above_n11": me["sum"] > BASE["sum"],
        "2_worst_day_no_larger_than_6_127": me["worst_day"] >= BAR_DAY,
        "3_fall_no_larger_than_n11": me["fall"] <= BASE["fall"],
        "4_worst_trade_no_larger_than_7_500": me["worst_trade"] >= BAR_TRADE,
        "5_every_year_at_or_above_n11_within_500": all(me["years"][y] >= BASE["years"][y] - 500 for y in YEARS),
        "6_double_cost_above_n11": double["sum"] > BASE["double"],
        "7_without_top_five_above_n11": me["without_top5"] > BASE["without_top5"],
        "8_plateau": all(s["sum"] > BASE["sum"] and s["worst_day"] >= BAR_DAY for s in neighbours.values()),
        "9_account_every_cost": all(accounts[t]["end"] >= N11_ACCOUNT[t] for t in N11_ACCOUNT) and (max(near) - min(near)) / min(near) <= 0.05 and all(accounts[t]["lowest"] >= 212500 for t in accounts),
        "10_audit": all(a["passed"] for a in audit.values()),
    }
    up = raised(me_rows, base)
    gains = sorted((g for y in YEARS for _t, _b, g in up[y]), reverse=True)
    by_year = {y: round(sum(g for _t, _b, g in up[y])) for y in YEARS}
    knock = {y: me["years"][y] - BASE["years"][y] - by_year[y] for y in YEARS}
    hidden = {y: {"sum_on_the_other_three": sum(v for k, v in by_year.items() if k != y), "would_be_chosen": sum(v for k, v in by_year.items() if k != y) > 0, "on_the_hidden_year": by_year[y]} for y in YEARS}
    result = {"schema": "n11t_results_v1", "all_data_seen": True, "n11t": me, "n11": BASE, "double": double, "neighbours": neighbours, "controls": controls, "accounts": accounts, "n11_account": N11_ACCOUNT,
              "near_cost_spread_pct": round((max(near) - min(near)) / min(near) * 100, 2), "checks_a_and_b": checks, "meets_the_bar_on_seen_years": all(checks.values()),
              "second_lots": {"count": len(gains), "wins": sum(g > 0 for g in gains), "own_by_year": by_year, "own_total": round(sum(gains)), "knock_on_by_year": {y: round(v) for y, v in knock.items()}, "top_three": round(sum(gains[:3])), "worst": round(min(gains, default=0.0)), "list": [(t["entry_time"][:16], t["member"], t["direction"][0], t["entry_premium"], t["exit_reason"][:13], round(b["net_pnl"]), round(t["net_pnl"])) for y in YEARS for t, b, _g in up[y]]},
              "placebo": placebo(base, len(gains), sum(gains)), "hidden_year": hidden, "audit": {y: audit[y]["checks"] for y in YEARS}}
    if (LOCAL / "keys-strict-2024.json").exists():
        result["plan_wording"] = {"STRICT": summary(rows_of("strict", "STRICT")), "STRICT_DOUBLE": summary(rows_of("strict", "STRICT|DOUBLE"))}
    (HERE / "results.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("n11t", "checks_a_and_b", "meets_the_bar_on_seen_years", "placebo", "hidden_year", "near_cost_spread_pct", "plan_wording") if k in result}, indent=1))
    print("second lots", {k: v for k, v in result["second_lots"].items() if k != "list"})
    print("accounts", {t: accounts[t]["end"] for t in accounts}, "lowest", min(accounts[t]["lowest"] for t in accounts), "fall", accounts["200"]["fall"])
    print("double", double["sum"], double["worst_day"], "controls", {k: (v["sum"], v["fall"]) for k, v in controls.items()})


if __name__ == "__main__":
    main()
