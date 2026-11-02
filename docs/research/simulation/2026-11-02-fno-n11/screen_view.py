"""Print any phase's books against the five earlier strategies, from saved replays only. A development view: it decides nothing."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
LOCAL = HERE / "_local"
YEARS = ("2023", "2024", "2025", "2026")
CAP = 250000.0
ECONOMIC = ("entry_time", "tradingsymbol", "entry_premium", "exit_time", "exit_premium", "exit_reason", "net_pnl", "entry_qty")


def stats(trades):
    eq = pk = CAP
    fall = 0.0
    days = defaultdict(float)
    for t in sorted(trades, key=lambda r: r["exit_time"]):
        n = float(t["net_pnl"])
        eq += n
        pk = max(pk, eq)
        fall = max(fall, (pk - eq) / pk)
        days[t["exit_time"][:10]] += n
    nets = [float(t["net_pnl"]) for t in trades]
    return dict(net=eq - CAP, fall=fall * 100, worst_day=min(days.values(), default=0.0), worst_trade=min(nets, default=0.0), n=len(trades))


def load(folder, phase, year, name):
    key = json.loads((folder / f"keys-{phase}-{year}.json").read_text())[name]
    return json.loads((folder / "evals" / f"{key}.json").read_text())


def line(name, rows):
    per = {y: stats(rows[y]) for y in YEARS}
    allnets = sorted((float(t["net_pnl"]) for y in YEARS for t in rows[y]), reverse=True)
    two = sum(1 for y in YEARS for t in rows[y] if int(t.get("entry_qty", 65)) >= 130)
    raised = sum(1 for y in YEARS for t in rows[y] if (t.get("n11_entry") or {}).get("raised_from"))
    kids = sum(len(t.get("n10_children") or []) for y in YEARS for t in rows[y])
    return (f"{name:<22}" + "".join(f"{per[y]['net']:>9,.0f}" for y in YEARS) + f"{sum(per[y]['net'] for y in YEARS):>10,.0f}" + f"{min(per[y]['worst_day'] for y in YEARS):>8,.0f}"
            + f"{max(per[y]['fall'] for y in YEARS):>7.2f}" + f"{min(per[y]['worst_trade'] for y in YEARS):>8,.0f}" + f"{sum(allnets[5:]):>9,.0f}" + f"{sum(per[y]['n'] for y in YEARS):>5}{two:>5}{raised:>5}{kids:>4}")


def refs():
    N09 = SIM / "2026-11-01-fno-n09" / "_local"
    N091 = SIM / "2026-11-01-fno-n091" / "_local"
    N10 = SIM / "2026-11-01-fno-n10" / "_local"
    out = {"N08": {}, "N09.1": {}, "N10 retry": {}}
    for y in YEARS:
        k = json.loads((N09 / f"keys-diag-{y}.json").read_text())["N08"]
        out["N08"][y] = json.loads((N09 / f"evals-{y}" / f"{k}.json").read_text())["trades"]
        k = json.loads((N091 / f"keys-primary-{y}.json").read_text())["CUSHION"]
        out["N09.1"][y] = json.loads((N091 / "evals" / f"{k}.json").read_text())["trades"]
        k = json.loads((N10 / f"keys-panel2-{y}.json").read_text())["R2_THIRD_CW"]
        out["N10 retry"][y] = json.loads((N10 / "evals" / f"{k}.json").read_text())["trades"]
    return out


def main(phase):
    print(f"{'book':<22}" + "".join(f"{y:>9}" for y in YEARS) + f"{'SUM':>10}{'wDay':>8}{'fall':>7}{'wTrade':>8}{'noTop5':>9}{'n':>5}{'2lot':>5}{'rais':>5}{'kid':>4}")
    r = refs()
    for name, rows in r.items():
        print(line(name, rows))
    names = list(json.loads((LOCAL / f"keys-{phase}-{YEARS[0]}.json").read_text()))
    for name in names:
        rows = {y: load(LOCAL, phase, y, name)["trades"] for y in YEARS}
        print(line(name, rows))
    if "NOOP" in names:
        same = {y: [{k: t.get(k) for k in ECONOMIC} for t in load(LOCAL, phase, y, "NOOP")["trades"]] == [{k: t.get(k) for k in ECONOMIC} for t in r["N10 retry"][y]] for y in YEARS}
        print("NOOP equals saved N10 retry, trade for trade:", same)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "screen")
