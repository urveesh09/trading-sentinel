"""N08 diagnosis, step 4: is the morning low-day edge about the clock, about being first, or about something else? Event days too."""
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
YEARS = ("2024", "2025", "2026")
rows = [t for y in YEARS for t in json.loads((HERE / "_local" / f"context-{y}.json").read_text())]
sides = {}
for y in YEARS:
    sides.update(json.loads((HERE / "_local" / f"sides-{y}.json").read_text()))
by_day = defaultdict(list)
for t in sorted(rows, key=lambda t: (t["day"], t["time"])):
    by_day[t["day"]].append(t)
for day, ts in by_day.items():
    for n, t in enumerate(ts, 1):
        t["nth"] = n
        t["held_before"] = n > 1
        t.update({k: v for k, v in sides.get(day, {}).items() if k in ("adx_value", "adx_band", "adx_rising", "di_cross", "don20", "nr7", "inside", "cpr_narrow", "event", "gap_big", "gap_dir", "dte", "dte_band")})
print("side names:", sorted(sides[rows[0]["day"]]))


def show(title, key, subset=None, out={}):
    table = defaultdict(lambda: {y: 0.0 for y in YEARS} | {"n": 0, "wins": 0, "total": 0.0, "r": 0.0})
    for t in subset if subset is not None else rows:
        g = table[key(t)]
        g[t["year"]] += t["net"]
        g["n"] += 1
        g["wins"] += t["net"] > 0
        g["total"] += t["net"]
        g["r"] += t["exit_r"]
    print(f"\n{title}")
    print(f"  {'':24}{'n':>4}{'win%':>6}{'2024':>9}{'2025':>9}{'2026':>9}{'total':>9}{'avg':>8}{'avgR':>7}")
    for k, g in sorted(table.items(), key=lambda kv: str(kv[0])):
        print(f"  {str(k):24}{g['n']:>4}{100 * g['wins'] / g['n']:>6.0f}{g['2024']:>9.0f}{g['2025']:>9.0f}{g['2026']:>9.0f}{g['total']:>9.0f}{g['total'] / g['n']:>8.0f}{g['r'] / g['n']:>7.2f}")


low = [t for t in rows if t["origin"] == "TPB_LOW"]
main = [t for t in rows if t["origin"] == "MAIN"]
half = lambda t: t["time"][:2] + (":00" if t["time"][3:] < "30" else ":30")
show("Low-day TPB by half hour", half, low)
show("Low-day TPB: nth trade of the day", lambda t: t["nth"], low)
show("Low-day TPB: first of day, by hour", lambda t: (t["nth"] == 1, t["time"][:2]), low)
show("Low-day TPB by ADX band", lambda t: t.get("adx_band"), low)
show("Low-day TPB morning by ADX band", lambda t: (t["time"] < "12:00", t.get("adx_band")), low)
show("Low-day TPB by ADX rising", lambda t: t.get("adx_rising"), low)
show("Low-day TPB by gap direction", lambda t: t.get("gap_dir"), low)
show("Low-day TPB by big gap", lambda t: t.get("gap_big"), low)
show("Low-day TPB by DTE", lambda t: t.get("dte", t.get("dte_band")), low)
show("Low-day TPB morning by DI", lambda t: (t["time"] < "12:00", t["di_up"]), low)
show("Low-day TPB by stretch band", lambda t: None if t["stretch"] is None else ("<0" if t["stretch"] < 0 else "0-.25" if t["stretch"] < .25 else ".25-.5"), low)
show("Main TPB by hour", lambda t: t["time"][:2], [t for t in main if t["expert"] == "TPB"])
show("Lots vs R", lambda t: (t["origin"], t["lots"]))
show("Event days, all", lambda t: t.get("event"))
show("Event days by source", lambda t: (t["origin"], t.get("event")))
show("Main by DTE", lambda t: t.get("dte", t.get("dte_band")), main)
show("Main by gap", lambda t: t.get("gap_big"), main)
print("\nEvery event-day trade:")
for t in rows:
    if t.get("event") == "HIGH":
        print(f"  {t['day']} {t['time']} {t['expert']:8}{t['direction']:6}{t['lots']} lot {t['exit']:18}{t['net']:>8.0f}")
print("\nDays with the largest losses:")
days = defaultdict(float)
for t in rows:
    days[t["day"]] += t["net"]
for d, v in sorted(days.items(), key=lambda kv: kv[1])[:10]:
    print(f"  {d} {v:>8.0f} ", [(t["time"], t["expert"], t["lots"], t["exit"][:9], round(t["net"])) for t in by_day[d]])
