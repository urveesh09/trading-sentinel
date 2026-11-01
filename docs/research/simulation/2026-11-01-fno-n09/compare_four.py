"""The plain four strategies against N08, on N08's own terms: fresh Rs 2.5 lakh a year, today's brakes, extra cost in the money path.

EX|MAIN goes through the same run as the control: it must return its stored +16,371 / +5,710 / +30,540 and -37,810, or nothing here counts.
All four years are already seen, so this chooses nothing and freezes nothing. Windows workers re-import this file.

    N08_YEAR=<year> python compare_four.py run --jobs 3
    python compare_four.py score
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

STUDY = Path(r"C:\Users\Urveesh\Desktop\trading-sentinel\docs\research\simulation\2026-11-01-fno-n08")
sys.path.insert(0, str(STUDY))
OUT = Path(__file__).resolve().parent
YEARS = ("2023", "2024", "2025", "2026")


def books(N) -> dict:
    exam = json.loads((N.FNO_STUDIES / "2026-10-31-weak-spots/freeze-2023.json").read_text(encoding="utf-8"))["books"]
    main = copy.deepcopy(exam["EX|MAIN"])

    def four(label: str, gate: str) -> dict:
        b = copy.deepcopy(main)
        b["members"] = [{**m, "gate": gate} for m in b["members"]]
        b.pop("skip")
        b["o31"] = label
        return b

    return {"EX|MAIN": main, "FOUR|PLAIN": four("CMP|FOUR|PLAIN", "ALWAYS"), "FOUR|ADX25": four("CMP|FOUR|ADX25", "adx_abs25:HIGH"),
            "N07": N.references()["NORMAL|PREMIUM_STALL"], "N08": N.n08_book()}


def run(jobs: int) -> None:
    import n08_lab as N
    b = books(N)
    N.run_books(b, jobs)
    keys = {n: N.Y.task_key(v, "year", N.C.WINDOW) for n, v in b.items()}
    (OUT / f"compare-keys-{N.B.YEAR}.json").write_text(json.dumps({"keys": keys, "evals": str(N.Y.EVALS)}, indent=1), encoding="utf-8")
    print("DONE", N.B.YEAR, keys, flush=True)


def stats(trades: list) -> dict:
    ordered = sorted(trades, key=lambda t: t["exit_time"])
    equity = peak = 250000.0
    fall = 0.0
    days = defaultdict(float)
    for t in ordered:
        equity += t["net_pnl"]
        peak = max(peak, equity)
        fall = max(fall, (peak - equity) / peak)
        days[t["exit_time"][:10]] += t["net_pnl"]
    return {"net": round(sum(t["net_pnl"] for t in ordered)), "fall_pct": round(fall * 100, 2), "trades": len(ordered), "wins": sum(t["net_pnl"] > 0 for t in ordered),
            "worst_trade": round(min((t["net_pnl"] for t in ordered), default=0)), "worst_day": round(min(days.values(), default=0)), "last": ordered[-1]["exit_time"][:10] if ordered else None}


def score() -> None:
    out = {}
    for y in YEARS:
        saved = json.loads((OUT / f"compare-keys-{y}.json").read_text(encoding="utf-8"))
        for name, key in saved["keys"].items():
            trades = json.loads((Path(saved["evals"]) / f"{key}.json").read_text(encoding="utf-8"))["trades"]
            out.setdefault(name, {})[y] = stats(trades)
    for name, row in out.items():
        print(name, "total", sum(row[y]["net"] for y in YEARS))
        for y in YEARS:
            print("  ", y, row[y])
    control = [out["EX|MAIN"][y]["net"] for y in YEARS]
    print("control EX|MAIN", control, "expected [-37810, 16371, 5710, 30540]")
    print("control N08", [out["N08"][y]["net"] for y in YEARS], "expected [-37581, 76294, 58647, 104924]", [out["N08"][y]["fall_pct"] for y in YEARS], "expected falls 15.08 2.16 4.70 2.69")
    print("control N07", [out["N07"][y]["net"] for y in YEARS], "expected [-37719, 57982, 52023, 77135]")
    (OUT / "compare-four.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", nargs="?", choices=("run", "score"))
    cli.add_argument("--jobs", type=int, default=3)
    a = cli.parse_args()
    if a.action == "run":
        run(a.jobs)
    elif a.action == "score":
        score()
else:
    # Pool workers import this file under another name: the stack's patches must be in place in them too.
    if os.environ.get("N08_YEAR"):
        import n08_lab  # noqa: F401
