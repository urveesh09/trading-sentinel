"""An independent check of the restart accounts, from raw trade files only: no replay code. Each claim the report makes about them is asserted here."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE / "_local"
YEARS = ("2023", "2024", "2025", "2026")


def trades(table: dict, name: str) -> list:
    rows = []
    for y in YEARS:
        rows += json.loads((LOCAL / "evals-carry" / f"{table[y][name]}.json").read_text(encoding="utf-8"))["trades"]
    return sorted((t for t in rows if t.get("net_pnl") is not None), key=lambda t: t["exit_time"])


def shadow_at(moment: str) -> list:
    rows = []
    for y in YEARS:
        key = json.loads((LOCAL / f"keys-diag-{y}.json").read_text(encoding="utf-8"))["DIAG"]
        rows += json.loads((LOCAL / f"evals-{y}" / f"{key}.json").read_text(encoding="utf-8"))["trades"]
    done = sorted((t for t in rows if t.get("net_pnl") is not None), key=lambda t: t["exit_time"])
    return [t["net_pnl"] for t in done if t["exit_time"] < moment]


def main() -> None:
    n08 = {y: json.loads((LOCAL / f"keys-carry-{y}.json").read_text(encoding="utf-8")) for y in YEARS}
    vol = {y: json.loads((LOCAL / f"keys-supp-carry-{y}.json").read_text(encoding="utf-8")) for y in YEARS}
    report = {}
    for label, table, name in (("N08", n08, "N08"), ("N08|ANNUAL", n08, "N08|ANNUAL"), ("N08|SHADOW", n08, "N08|SHADOW"), ("S_VOL|SHADOW", vol, "S_VOL|SHADOW")):
        rows = trades(table, name)
        equity = peak = 250000.0
        fall, floor, gap, last_exit, rearms = 0.0, 212500.0, None, None, []
        for t in rows:
            entry = datetime.fromisoformat(t["entry_time"])
            if equity < floor:
                # A new entry while below the floor can only be a restart: the floor moves to 85% of the equity at that moment.
                rearms.append({"entry": t["entry_time"], "equity": round(equity, 2), "days_stopped": (entry - last_exit).days})
                floor = equity * 0.85
            equity += t["net_pnl"]
            peak = max(peak, equity)
            fall = max(fall, (peak - equity) / peak)
            last_exit = datetime.fromisoformat(t["exit_time"])
        report[label] = {"trades": len(rows), "end": round(equity), "fall_pct": round(fall * 100, 2), "restarts": rearms, "last_exit": rows[-1]["exit_time"][:10]}
        print(label, report[label], flush=True)
    assert report["N08"]["end"] == 212419 and report["N08"]["last_exit"] == "2023-10-03" and not report["N08"]["restarts"]
    assert report["N08|SHADOW"]["end"] == 436635 and len(report["N08|SHADOW"]["restarts"]) == 1
    assert report["N08|ANNUAL"]["end"] == 441234 and report["N08|ANNUAL"]["restarts"][0]["entry"][:4] == "2024"
    assert report["S_VOL|SHADOW"]["end"] == 410542
    restart = report["N08|SHADOW"]["restarts"][0]["entry"]
    paper = shadow_at(restart)
    assert sum(paper[-20:]) > 0, "the last 20 paper trades before the first real entry must have made money"
    print("paper, last 20 before the first entry after the stop:", round(sum(paper[-20:])), "at", restart, flush=True)
    (HERE / "audit-account.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("AUDIT OK", flush=True)


if __name__ == "__main__":
    main()
