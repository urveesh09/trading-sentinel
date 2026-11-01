"""Score the one-time 2023 opening by the rules fixed in freeze.json, and put all four years side by side. Writes results.json."""
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from analyze_screen import A, closed_dd, paired_t, stored

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())
WEAK = ROOT / "docs/research/fno/2026-10-31-weak-spots"
YEARS = ("2023", "2024", "2025", "2026")
DEV = ("2024", "2025", "2026")
keys23 = json.loads((HERE / "_local" / "keys-exam-2023.json").read_text())
refs = {y: {**json.loads((A / "_local" / f"keys-reference-{y}.json").read_text()), **json.loads((A / "_local" / f"keys-candidate-{y}.json").read_text())} for y in DEV}
dev_keys = {y: {"N03": refs[y]["NORMAL|BASE"], "N04": refs[y]["NORMAL|STALL30"], "N05": refs[y]["NORMAL|STRUCT30"], "N07": refs[y]["NORMAL|PREMIUM_STALL"]} for y in DEV}
for y in DEV:
    s1 = json.loads((HERE / "_local" / f"keys-screen-{y}.json").read_text())
    s2 = json.loads((HERE / "_local" / f"keys-screen2-{y}.json").read_text())
    s3 = json.loads((HERE / "_local" / f"keys-screen3-{y}.json").read_text())
    s4 = json.loads((HERE / "_local" / f"keys-screen4-{y}.json").read_text())
    dev_keys[y].update({"N08": s4["WELC"], "PART|WIDE_TRAIL": s1["TRAIL_EFF_OR20|2.0"], "PART|EARLY_TWO": s2["LOW_TWO_BEFORE|12:00"], "PART|LATE_STOP": s2["LOW_LAST|14:00"],
                        "PART|CAP2": s3["COMBO|C"], "PART|NO_LOW_TPB": s2["NO_LOW_TPB"], "ONE|N07": s4["ONE|N07"], "ONE|WL": s4["ONE|WL"]})


def stats(trades: list) -> dict:
    wins = [t["net_pnl"] for t in trades if t["net_pnl"] > 0]
    losses = [t["net_pnl"] for t in trades if t["net_pnl"] <= 0]
    days = defaultdict(float)
    for t in trades:
        days[t["entry_time"][:10]] += t["net_pnl"]
    return {"net": round(sum(wins) + sum(losses)), "fall_pct": round(closed_dd(trades), 2), "trades": len(trades), "wins": len(wins), "avg_win": round(sum(wins) / max(1, len(wins))),
            "avg_loss": round(sum(losses) / max(1, len(losses))), "worst_trade": round(min(losses, default=0)), "worst_day": round(min(days.values(), default=0)), "best_day": round(max(days.values(), default=0))}


names = ("N03", "N04", "N05", "N07", "N08", "PART|WIDE_TRAIL", "PART|EARLY_TWO", "PART|LATE_STOP", "PART|CAP2", "PART|NO_LOW_TPB", "ONE|N07", "ONE|WL")
trades = {n: {"2023": stored(keys23[n]), **{y: stored(dev_keys[y][n]) for y in DEV}} for n in names}
table = {n: {y: stats(trades[n][y]) for y in YEARS} for n in names}
print(f"{'book':18}{'2023':>9}{'fall%':>7}{'n':>4}{'win':>4}{'avgW':>7}{'avgL':>7}{'wrstT':>7}{'wrstD':>8} |{'2024':>8}{'2025':>8}{'2026':>9}{'4 years':>9}{'3 years':>9}")
for n in names:
    t = table[n]
    s = t["2023"]
    print(f"{n:18}{s['net']:>9}{s['fall_pct']:>7}{s['trades']:>4}{s['wins']:>4}{s['avg_win']:>7}{s['avg_loss']:>7}{s['worst_trade']:>7}{s['worst_day']:>8} |{t['2024']['net']:>8}{t['2025']['net']:>8}{t['2026']['net']:>9}{sum(t[y]['net'] for y in YEARS):>9}{sum(t[y]['net'] for y in DEV):>9}")

n08, n07 = table["N08"], table["N07"]
passes_2023 = {"net_above_zero": n08["2023"]["net"] > 0, "net_at_or_above_n07": n08["2023"]["net"] >= n07["2023"]["net"], "fall_no_larger_than_n07": n08["2023"]["fall_pct"] <= n07["2023"]["fall_pct"]}
total = {n: sum(table[n][y]["net"] for y in YEARS) for n in names}
passes_four = {"positive_every_year": all(n08[y]["net"] > 0 for y in YEARS), **{f"total_above_{r}": total["N08"] > total[r] for r in ("N03", "N04", "N05", "N07")}}
print("\nN08 on 2023:", passes_2023)
print("N08 on four years:", passes_four)
all08 = [t for y in YEARS for t in trades["N08"][y]]
all07 = [t for y in YEARS for t in trades["N07"][y]]
print("Paired weekly t, N08 against N07: 2023 alone", round(paired_t(trades["N08"]["2023"], trades["N07"]["2023"]), 2), "; four years", round(paired_t(all08, all07), 2))

exam = {}
weak = json.loads((WEAK / "results.json").read_text())
three = {"EX|MAIN": 52621}
for name in ("EX|MAIN", "EX|D|only_puts_from_25", "EX|D|puts_from_25", "EX|D|tpb_puts_closed", "EX|C|puts_only", "EX|C|no_eff"):
    ts = stored(keys23["EXAM|" + name])
    short = name.split("|", 1)[1]
    change = weak["changes"].get(short.replace("|", "|")) if short in weak["changes"] else None
    exam[name] = {**stats(ts), "three_year_net": change["total"] if change else three.get(name)}
main = exam["EX|MAIN"]
exam_verdict = {"main_holds": main["net"] > 0 and main["fall_pct"] <= 15}
for name, s in exam.items():
    if name != "EX|MAIN":
        exam_verdict[name + " holds"] = s["net"] > main["net"] and s["fall_pct"] <= 15
holding = [n for n in ("EX|D|only_puts_from_25", "EX|D|tpb_puts_closed") if exam_verdict[n + " holds"]]
exam_verdict["recommended_by_the_rule"] = max(holding, key=lambda n: exam[n]["three_year_net"] or 0) if holding else "the main book stays"
print("\nO31e exam on 2023:")
for name, s in exam.items():
    print(f"  {name:28}{s['net']:>9} fall {s['fall_pct']:>5}% trades {s['trades']:>3} wins {s['wins']:>3} worst day {s['worst_day']:>7}  three-year {s['three_year_net']}")
print(" ", exam_verdict)

# What 2023 did to each piece
print("\nN07 and N08 on 2023 by source and strategy:")
for book in ("N07", "N08"):
    groups = defaultdict(lambda: [0, 0, 0.0])
    for t in trades[book]["2023"]:
        g = groups[(t.get("origin"), t.get("entry_expert"), t["direction"])]
        g[0] += 1
        g[1] += t["net_pnl"] > 0
        g[2] += t["net_pnl"]
    print(" ", book, {str(k): (v[0], v[1], round(v[2])) for k, v in sorted(groups.items(), key=lambda kv: str(kv[0]))})
months = defaultdict(float)
for t in trades["N08"]["2023"]:
    months[t["exit_time"][:7]] += t["net_pnl"]
print("N08 by month of 2023:", {k: round(v) for k, v in sorted(months.items())})
months = defaultdict(float)
for t in trades["N07"]["2023"]:
    months[t["exit_time"][:7]] += t["net_pnl"]
print("N07 by month of 2023:", {k: round(v) for k, v in sorted(months.items())})
early = [t for t in trades["N08"]["2023"] if t.get("origin") == "TPB_LOW" and t["entry_time"][11:16] < "12:00"]
print("N08 morning low-day trades on 2023:", len(early), "wins", sum(t["net_pnl"] > 0 for t in early), "net", round(sum(t["net_pnl"] for t in early)))
funnel = json.loads((HERE / "_local" / "evals" / f"{keys23['N08']}.json").read_text())
print("N08 2023 halted days:", funnel.get("drawdown_halt_days"), " notes:", {k: v for k, v in funnel["notes"].items() if "regime" not in k and "grid" not in k})
(HERE / "results.json").write_text(json.dumps({"schema": "n08_results_v1", "table": table, "four_year_total": total, "n08_passes_2023": passes_2023, "n08_passes_four_years": passes_four,
                                                "o31e_exam": exam, "o31e_verdict": exam_verdict, "qualified": False, "can_place_orders": False}, indent=1), encoding="utf-8")
