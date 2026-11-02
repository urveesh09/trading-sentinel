"""What exactly changes between N07 and the candidate, trade by trade, on 2024-26. Is the gain broad or a handful of trades? Reads saved replays only."""
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
A = HERE.parent / "2026-11-01-fno-failure-anatomy"
YEARS = ("2024", "2025", "2026")


def stored(key):
    return json.loads((HERE / "_local" / "evals" / f"{key}.json").read_text(encoding="utf-8"))["trades"]


refs = {y: {**json.loads((A / "_local" / f"keys-reference-{y}.json").read_text()), **json.loads((A / "_local" / f"keys-candidate-{y}.json").read_text())} for y in YEARS}
keys = {y: json.loads((HERE / "_local" / f"keys-screen4-{y}.json").read_text()) for y in YEARS}
out = {"years": {}}
biggest = []
for y in YEARS:
    a = {(t["entry_time"], t["tradingsymbol"]): t for t in stored(refs[y]["NORMAL|PREMIUM_STALL"])}
    b = {(t["entry_time"], t["tradingsymbol"]): t for t in stored(keys[y]["WELC"])}
    groups = defaultdict(lambda: {"n": 0, "delta": 0.0})
    for k, t in b.items():
        old = a.get(k)
        if old is None:
            g = "new trade"
            d = t["net_pnl"]
        else:
            d = t["net_pnl"] - old["net_pnl"]
            same_exit = old["exit_time"] == t["exit_time"]
            lots = t["entry_qty"] != old["entry_qty"]
            g = ("lots " + ("up" if t["entry_qty"] > old["entry_qty"] else "down") if lots else "same lots") + (", same exit" if same_exit else ", later exit" if t["exit_time"] > old["exit_time"] else ", earlier exit")
        groups[g]["n"] += 1
        groups[g]["delta"] += d
        biggest.append((d, y, t["entry_time"][:16], t["entry_expert"], t["direction"], t["entry_qty"] // 65, old["entry_qty"] // 65 if old else 0, t["exit_reason"], round(t["net_pnl"]), round(old["net_pnl"]) if old else None))
    for k, t in a.items():
        if k not in b:
            groups["dropped"]["n"] += 1
            groups["dropped"]["delta"] -= t["net_pnl"]
            biggest.append((-t["net_pnl"], y, t["entry_time"][:16], t["entry_expert"], t["direction"], 0, t["entry_qty"] // 65, "dropped", 0, round(t["net_pnl"])))
    out["years"][y] = {g: {"n": v["n"], "delta": round(v["delta"])} for g, v in groups.items()}
    print(y, json.dumps(out["years"][y]))
biggest.sort(key=lambda r: r[0])
print("\nLargest harms:")
for r in biggest[:10]:
    print("  ", r)
print("Largest gains:")
for r in biggest[-14:][::-1]:
    print("  ", r)
total = sum(r[0] for r in biggest)
top5 = sum(r[0] for r in sorted(biggest, key=lambda r: -r[0])[:5])
print(f"\nTotal change {total:.0f}; the five largest gains {top5:.0f}; without them {total - top5:.0f}")
daily = defaultdict(list)
for y in YEARS:
    for t in stored(keys[y]["WELC"]):
        daily[t["entry_time"][:10]].append(t)
print("Worst days of the candidate:")
for d, ts in sorted(daily.items(), key=lambda kv: sum(t["net_pnl"] for t in kv[1]))[:6]:
    print("  ", d, round(sum(t["net_pnl"] for t in ts)), [(t["entry_time"][11:16], t["entry_expert"], t["entry_qty"] // 65, t["exit_reason"][:9], round(t["net_pnl"])) for t in ts])
worst = sorted((t for y in YEARS for t in stored(keys[y]["WELC"])), key=lambda t: t["net_pnl"])[:5]
print("Worst trades:", [(t["entry_time"][:16], t["entry_expert"], t["entry_qty"] // 65, t["exit_reason"][:9], round(t["net_pnl"])) for t in worst])
months = defaultdict(float)
for y in YEARS:
    for t in stored(keys[y]["WELC"]):
        months[t["exit_time"][:7]] += t["net_pnl"]
vals = list(months.values())
print(f"Months up/down: {sum(v > 0 for v in vals)}/{sum(v < 0 for v in vals)}; worst month {min(vals):.0f}")
