"""SN388: where N11's stand-aside helped or hurt in 2022 (PLAN.md section 1, frozen at c6e99cee; details fixed here
before any SN388 number). Reads SN366's exam evals only (no replay).

A "fire" = a NO_STAND entry (entry time + contract) that N11 did not take. For each fire, what the rule knew at the
entry: the last 20 one-lot paper nets (N08's DIAG trades of Sep - Dec 2021 and 2022, exits strictly before the entry,
the exam's own stream), their sum, and the volatility reading (yesterday's ATR% vs 0.9 x its 250-session median, N09's
algorithm on the 2022 point's daily file). Reported: the fires' total and mean net (NO_STAND's trade), by month, by
entry expert and side; the longest run of consecutive fired sessions; how many fires came while the paper record was
within Rs 2,000 of zero (a knife edge); and the N11 / NO_STAND / N10 one try / retry nets beside them (the exam).
The Rs 30,000 Gold comparison is SN392's.
"""
from __future__ import annotations

import bisect
import collections
import json
import statistics
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SN366 = HERE.parent / "2026-11-16-sn366"
OUT = HERE / "results-sn388.json"


def vol_table(path):
    rows = {r[0]: r for r in json.loads(Path(path).read_text(encoding="utf-8"))["rows"]}
    days = sorted(rows)
    out, atr, readings, prev = {}, None, [], None
    for i, day in enumerate(days):
        if readings:
            good = readings[:-1][-250:]
            out[day] = (readings[-1], statistics.median(good) if len(good) >= 120 else None)
        _d, _o, high, low, close = rows[day]
        tr = high - low if prev is None else max(high - low, abs(high - prev), abs(low - prev))
        atr = tr if atr is None else atr + (tr - atr) / 14
        if i >= 14:
            readings.append(atr / close * 100)
        prev = close
    return out


def main():
    if OUT.exists():
        raise SystemExit("SN388 is run once")
    keys = json.loads((SN366 / "_local" / "keys-exam-2022.json").read_text(encoding="utf-8"))
    load = lambda n: json.loads((SN366 / "_local" / "exam-evals-2022" / f"{keys[n]}.json").read_text(encoding="utf-8"))["trades"]  # noqa: E731
    n11, nost = load("panel|N11"), load("panel|NO_STAND")
    paper = []
    for y in ("2021", "2022"):
        k = json.loads((SN366 / "_local" / "n09" / f"keys-diag-{y}.json").read_text(encoding="utf-8"))["DIAG"]
        paper += json.loads((SN366 / "_local" / "n09" / f"evals-{y}" / f"{k}.json").read_text(encoding="utf-8"))["trades"]
    paper.sort(key=lambda t: t["exit_time"])
    at = [datetime.fromisoformat(t["exit_time"]) for t in paper]
    nets = [float(t["net_pnl"]) for t in paper]
    vt = vol_table(SN366 / "_local" / "daily-2022.json")
    taken = {(t["entry_time"], t["tradingsymbol"]) for t in n11}
    fires = []
    for t in nost:
        if (t["entry_time"], t["tradingsymbol"]) in taken:
            continue
        now = datetime.fromisoformat(t["entry_time"])
        prior = nets[:bisect.bisect_left(at, now)]
        last20 = prior[-20:]
        a, u = vt.get(t["entry_time"][:10], (None, None))
        fires.append({"day": t["entry_time"][:10], "entry": t["entry_time"][11:16], "expert": t.get("entry_expert"), "side": "CE" if "CE" in t["tradingsymbol"] else "PE",
                      "net": round(float(t["net_pnl"]), 2), "paper_last20_sum": round(sum(last20), 1), "paper_count": len(prior),
                      "atr_pct": None if a is None else round(a, 3), "usual_x0.9": None if u is None else round(0.9 * u, 3)})
    fd = sorted({f["day"] for f in fires})
    sess = sorted({t["entry_time"][:10] for t in nost})
    run = best = 0
    for d in sess:
        run = run + 1 if d in fd else 0
        best = max(best, run)
    ex = json.loads((SN366 / "results-sn366-exam-2022.json").read_text(encoding="utf-8"))["stats"]
    res = {"fires": len(fires), "fired_sessions": len(fd), "fires_net_total": round(sum(f["net"] for f in fires)),
           "fires_net_mean": round(sum(f["net"] for f in fires) / max(1, len(fires)), 1), "fires_won": sum(f["net"] > 0 for f in fires),
           "by_month": {m: round(sum(f["net"] for f in fires if f["day"][:7] == m)) for m in sorted({f["day"][:7] for f in fires})},
           "by_expert": {e: {"n": sum(1 for f in fires if f["expert"] == e), "net": round(sum(f["net"] for f in fires if f["expert"] == e))} for e in sorted({str(f["expert"]) for f in fires})},
           "by_side": {s: round(sum(f["net"] for f in fires if f["side"] == s)) for s in ("CE", "PE")},
           "longest_run_of_fired_sessions": best, "knife_edge_fires_(|last20|<2000)": sum(abs(f["paper_last20_sum"]) < 2000 for f in fires),
           "exam_nets": {k: ex[k]["net"] for k in ("panel|N11", "panel|NO_STAND", "STRICT", "ctrl|N10", "CUSHION")},
           "rows": fires}
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    main()
