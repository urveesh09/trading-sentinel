"""N08 diagnosis, step 2: where N07's rupees come from and go, per year. Seen data only. Writes diagnosis.json and prints the tables."""
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
YEARS = ("2024", "2025", "2026")
rows = [t for y in YEARS for t in json.loads((HERE / "_local" / f"context-{y}.json").read_text())]


def group(key, subset=None):
    out = defaultdict(lambda: {y: 0.0 for y in YEARS} | {"n": 0, "wins": 0, "total": 0.0, "per_lot": 0.0})
    for t in subset if subset is not None else rows:
        g = out[key(t)]
        g[t["year"]] += t["net"]
        g["n"] += 1
        g["wins"] += t["net"] > 0
        g["total"] += t["net"]
        g["per_lot"] += t["net"] / max(1, t["lots"])
    return out


def show(title, key, subset=None):
    print(f"\n{title}")
    print(f"  {'':24}{'n':>4}{'win%':>6}{'2024':>9}{'2025':>9}{'2026':>9}{'total':>9}{'/lot':>9}")
    table = group(key, subset)
    for k, g in sorted(table.items(), key=lambda kv: str(kv[0])):
        print(f"  {str(k):24}{g['n']:>4}{100 * g['wins'] / g['n']:>6.0f}{g['2024']:>9.0f}{g['2025']:>9.0f}{g['2026']:>9.0f}{g['total']:>9.0f}{g['per_lot']:>9.0f}")
    return {str(k): {a: round(b, 2) for a, b in g.items()} for k, g in table.items()}


def band(v):
    return None if v is None else "<15" if v < 15 else "15-20" if v < 20 else "20-25" if v < 25 else "25-30" if v < 30 else "30-35" if v < 35 else "35+"


def hour(t):
    return t["time"][:2]


def r_band(v):
    return "<0.5R" if v < 0.5 else "0.5-1R" if v < 1 else "1-1.5R" if v < 1.5 else "1.5-2R" if v < 2 else "2-3R" if v < 3 else "3R+"


out = {}
out["origin_expert"] = show("By source and strategy", lambda t: f"{t['origin']}/{t['expert']}")
out["origin_lots"] = show("By source and lots", lambda t: f"{t['origin']}/{t['lots']}lot")
out["direction"] = show("By side", lambda t: f"{t['origin']}/{t['direction']}")
out["hour"] = show("By entry hour", hour)
low = [t for t in rows if t["origin"] == "TPB_LOW"]
main = [t for t in rows if t["origin"] == "MAIN"]
out["low_adx"] = show("Low-day TPB by ADX band", lambda t: band(t["adx"]), low)
out["low_di"] = show("Low-day TPB by yesterday's DI (True: +DI above -DI)", lambda t: t["di_up"], low)
out["low_rising"] = show("Low-day TPB by ADX rising", lambda t: t["adx_rising"], low)
out["low_hour"] = show("Low-day TPB by hour", hour, low)
out["main_adx"] = show("Main book by ADX band", lambda t: band(t["adx"]), main)
out["main_di"] = show("Main by DI and side", lambda t: f"{t['direction']}/di_up={t['di_up']}", main)
out["gap"] = show("By big gap", lambda t: t["gap_big"])
out["gap_side"] = show("By gap against or with trade", lambda t: "with" if (t["gap_dir"] == "UP") == (t["direction"] == "LONG") else "against")
out["event"] = show("By scheduled event (the O31e calendar)", lambda t: t["event"])
out["dte"] = show("By days to weekly expiry", lambda t: t["dte2"])
out["weekday"] = show("By weekday", lambda t: t["weekday"])
out["exit"] = show("By exit", lambda t: t["exit"])
out["exit_expert"] = show("By strategy and exit", lambda t: f"{t['expert']}/{t['exit']}")
print("\nBest premium gain reached while held (R = 25% of premium), by final result")
out["mfe_losers"] = show("Losers by best gain reached", lambda t: r_band(t["mfe_r"]), [t for t in rows if t["net"] <= 0])
out["mfe_winners"] = show("Winners by best gain reached", lambda t: r_band(t["mfe_r"]), [t for t in rows if t["net"] > 0])
for expert in ("TPB", "EFF", "OR20", "SHIPPED"):
    sub = [t for t in rows if t["expert"] == expert]
    print(f"\n{expert}: give-back from the best gain to the exit, in R, for trades that reached 1R")
    reached = [t for t in sub if t["mfe_r"] >= 1]
    for t_band in ("<0.5R", "0.5-1R", "1-1.5R", "1.5-2R", "2-3R", "3R+"):
        s = [t for t in reached if r_band(t["mfe_r"]) == t_band]
        if s:
            print(f"  best {t_band:8} n={len(s):3} avg exit {sum(t['exit_r'] for t in s) / len(s):6.2f}R  exit below entry {sum(t['exit_r'] <= 0 for t in s):3}  net {sum(t['net'] for t in s):9.0f}")
late = [t for t in rows if t["exit"] in ("underlying_stop", "premium_backstop", "time_stop") and t["after_last_r"] is not None]
print(f"\nStops: {len(late)} trades; where the option stood at 15:10 versus the exit, in R")
print("  recovered above entry by 15:10:", sum(t["after_last_r"] > 0 for t in late), "of", len(late))
out["stopped_recovered"] = {"n": len(late), "recovered": sum(t["after_last_r"] > 0 for t in late)}
(HERE / "diagnosis.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
