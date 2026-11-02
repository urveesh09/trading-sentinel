"""O31c analysis -> results-c.json. Frozen with lab_o2.py before any of its replays; never changed after seeing a result."""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
FNO = ROOT / "docs/research/fno"
sys.path[:0] = [str(HERE), str(ROOT / "python-engine"), str(FNO / "2026-10-30-risk-spectrum")]
import analyze_o as AO  # noqa: E402
import analyze_r as A  # noqa: E402

YEARS = AO.YEARS
PER_TRADE = 200.0
ADX_LEVELS = (20, 25, 27, 30, 32, 35)
SKIPS = ("none", "25", "35", "50", "65", "75")


def one_lot(t: dict) -> float:
    return float(t["net_pnl"]) / max(1, int(t.get("lots_at_exit") or 1))


def per_lot(by_year: dict, sessions: dict) -> dict:
    """After Rs 200 a trade: each year's net, trades, the whole run's fall, and the worse year."""
    years, daily = {}, {}
    for y in YEARS:
        rows = [t for t in by_year[y] if t.get("net_pnl") is not None]
        years[y] = {"net": round(sum(one_lot(t) - PER_TRADE for t in rows)), "gross": round(sum(one_lot(t) for t in rows)), "trades": len(rows)}
        for t in rows:
            d = t["entry_time"][:10]
            daily[d] = daily.get(d, 0.0) + one_lot(t) - PER_TRADE
    every = [d for y in YEARS for d in sessions[y]]
    return {"years": years, "total": sum(years[y]["net"] for y in YEARS), "worst_year": min(years[y]["net"] for y in YEARS),
            "fall": fall(daily, every)}


def fall(daily: dict, sessions: list) -> int:
    run = peak = out = 0.0
    for d in sorted(sessions):
        run += daily.get(d, 0.0)
        peak = max(peak, run)
        out = max(out, peak - run)
    return round(out)


def rule_plateau(surface: dict) -> dict:
    none = surface["A25|Snone"]["total"]
    return {"no_rule": none, "limits": {s: surface[f"A25|S{s}"]["total"] for s in ("25", "35", "50", "65", "75")},
            "on_plateau": all(surface[f"A25|S{s}"]["total"] > none for s in ("35", "50", "65"))}


def adx_plateau(exact: dict, surface: dict) -> dict:
    money = {a: exact[a]["years"] for a in ("A28", "A30", "A32")}
    positive = all(v > 0 for row in money.values() for v in row.values())
    base_fall = surface["A25|S50"]["fall"]
    falls = {a: surface[f"{a}|S50"]["fall"] for a in ("A27", "A30", "A32")}
    return {"exact_money": money, "all_positive_every_year": positive, "surface_falls": falls, "surface_fall_at_25": base_fall,
            "lower_fall_on_surface": all(v < base_fall for v in falls.values()),
            "on_plateau": positive and all(v < base_fall for v in falls.values())}


def final_call(rule_ok: bool, adx_ok: bool) -> str:
    return {(True, True): "four strategies + rule + ADX 30, today's limits", (True, False): "four strategies + rule + ADX 25, today's limits",
            (False, True): "four strategies + ADX 30, today's limits; the rule on paper only", (False, False): "the book as live today; both on paper only"}[(rule_ok, adx_ok)]


def main() -> None:
    frozen = json.loads((HERE / "freeze-c.json").read_text(encoding="utf-8"))
    keys = {y: json.loads((HERE / f"_local/keys-c-{y}.json").read_text(encoding="utf-8")) for y in YEARS}
    keys_b = {y: json.loads((HERE / f"_local/keys-{y}.json").read_text(encoding="utf-8")) for y in YEARS}
    sessions = {y: [d for d in json.loads((AO.DATA[y] / "manifest.json").read_text(encoding="utf-8"))["sessions"] if d <= AO.LAST[y]] for y in YEARS}

    def load(key: str) -> dict:
        return json.loads((HERE / f"_local/evals/{key}.json").read_text(encoding="utf-8"))

    def trades(name: str, source=keys) -> dict:
        return {y: load(source[y][name])["trades"] for y in YEARS}

    problems = {}
    for name, book in frozen["books"].items():
        cap = int(book["cfg"].get("FNO_MAX_TRADES_PER_DAY", 3))
        for y in YEARS:
            d = load(keys[y][name])
            bad = A.check_book(d["trades"], {"cfg": book["cfg"]}, A.CAPITAL, book.get("cost"), cap)
            bad.pop("unresolved", None)
            if bad:
                problems[f"{name}|{y}"] = bad
            memo = {k: v for k, v in d["notes"].items() if "conflict" in k or k == "named_memo_miss"}
            if memo:
                problems[f"{name}|{y}|notes"] = memo

    surface = {f"A{a}|S{s}": per_lot(trades(f"SURFACE|A{a}|S{s}"), sessions) for a in ADX_LEVELS for s in SKIPS}
    exact = {}
    for a in ("A27", "A28", "A32", "A35", "S35", "S65"):
        by = trades(f"EXACT|{a}")
        exact[a] = {"years": {y: A.path(by[y])["net"] for y in YEARS}, "falls": {y: A.path(by[y])["fall_pct"] for y in YEARS},
                    "trades": {y: A.path(by[y])["trades"] for y in YEARS}, "worst_day": min(A.path(by[y])["worst_day"] for y in YEARS)}
    by = trades("ADX|30", keys_b)
    exact["A30"] = {"years": {y: A.path(by[y])["net"] for y in YEARS}, "falls": {y: A.path(by[y])["fall_pct"] for y in YEARS},
                    "trades": {y: A.path(by[y])["trades"] for y in YEARS}, "worst_day": min(A.path(by[y])["worst_day"] for y in YEARS)}
    by = trades("BASE", keys_b)
    exact["A25"] = {"years": {y: A.path(by[y])["net"] for y in YEARS}, "falls": {y: A.path(by[y])["fall_pct"] for y in YEARS},
                    "trades": {y: A.path(by[y])["trades"] for y in YEARS}, "worst_day": min(A.path(by[y])["worst_day"] for y in YEARS)}
    by = trades("EXACT|A30|AS")
    as_replayed = {y: A.pub(A.path(by[y])) for y in YEARS}
    carried = {}
    for n, first in (("BASE30", load(keys_b["2024"]["ADX|30"])), ("BASE30|AS", load(keys["2024"]["EXACT|A30|AS"]))):
        t = list(first["trades"])
        for y in ("2025", "2026"):
            t += load(keys[y][f"{n}|carry"])["trades"]
        carried[n] = A.pub(A.path(t))

    def random_stats(a: int) -> dict:
        rows = [per_lot(trades(f"RANDOM|{i:02d}|A{a}"), sessions) for i in range(20)]
        return {"median_total": statistics.median(r["total"] for r in rows), "best_total": max(r["total"] for r in rows),
                "positive_total": sum(r["total"] > 0 for r in rows), "positive_every_year": sum(r["worst_year"] > 0 for r in rows),
                "median_by_year": {y: statistics.median(r["years"][y]["net"] for r in rows) for y in YEARS},
                "median_fall": statistics.median(r["fall"] for r in rows)}

    rand = {a: random_stats(a) for a in (25, 30)}
    gain_real = surface["A30|S50"]["total"] - surface["A25|S50"]["total"]
    gain_random = rand[30]["median_total"] - rand[25]["median_total"]
    r_plateau, a_plateau = rule_plateau(surface), adx_plateau(exact, surface)
    out = {"schema": "o31c_results_v1", "rule": frozen["rule"], "correctness": {"replays": sum(len(k) for k in keys.values()), "problems": problems},
           "surface_per_lot_after_200": surface, "exact_rupees_with_cost": exact, "a30_as_replayed": as_replayed, "carried": carried,
           "random": {"A25": rand[25], "A30": rand[30], "gain_real": gain_real, "gain_random": gain_random,
                      "market_effect": gain_random >= gain_real},
           "rule_plateau": r_plateau, "adx_plateau": a_plateau, "final": final_call(r_plateau["on_plateau"], a_plateau["on_plateau"]),
           "qualification": "NOT_ASSESSED", "can_place_orders": False}
    tmp = HERE / "results-c.json.part"
    tmp.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8", newline="\n")
    tmp.replace(HERE / "results-c.json")
    print(json.dumps({k: out[k] for k in ("rule_plateau", "adx_plateau", "final")}, indent=1))
    print("random", json.dumps(out["random"], indent=0))
    print("problems", str(problems)[:800])


if __name__ == "__main__":
    main()
