"""Independent audit of N11T after its frozen run: money and prices from raw quotes, and each raised trade against the rule's conditions, by their own code. Changes nothing. Writes audit-YEAR.json.

    N08_YEAR=<year> python audit_n11t.py
"""
from __future__ import annotations

import bisect
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
N11 = HERE.parent / "2026-11-02-fno-n11"
sys.path[:0] = [str(HERE), str(N11)]
import stress as ST  # noqa: E402  (first: N09.1 has a stress.py too)
import n11t_lab as Q  # noqa: E402
from fno_costs import calc_fno_costs  # noqa: E402

L, Y, Z = Q.L, Q.Y, Q.Z
YEAR = Q.YEAR
LOCAL = Q.LOCAL
LIMIT = 7500.0


def main() -> None:
    Z.B.L._init()
    data = Y.dataset("year")
    packets: dict = {}

    def session(day):
        if day not in packets:
            packets[day] = sorted(data.observations(day)[0], key=lambda o: o.at)
        return packets[day]

    def quote_of(obs, symbol):
        rows = [q for q in obs.options.values() if q.contract.tradingsymbol == symbol]
        assert len(rows) == 1, symbol
        return rows[0]

    vols = ST.vol_table()
    paper = []
    for y in ST.YEARS:
        key = json.loads((Z.LOCAL / f"keys-diag-{y}.json").read_text(encoding="utf-8"))["DIAG"]
        paper += [(datetime.fromisoformat(t["exit_time"]), float(t["net_pnl"])) for t in json.loads((Z.LOCAL / f"evals-{y}" / f"{key}.json").read_text(encoding="utf-8"))["trades"]]
    paper.sort(key=lambda e: e[0])
    at, nets = [e[0] for e in paper], [e[1] for e in paper]

    def evidence(now_iso):
        prior = nets[:bisect.bisect_left(at, datetime.fromisoformat(now_iso))]
        return len(prior) >= 20 and sum(prior[-20:]) > 0

    def vol_up(day):
        atr, usual = vols.get(day, (None, None))
        return bool(atr is not None and usual is not None and atr >= usual)

    k = json.loads((LOCAL / f"keys-panel-{YEAR}.json").read_text(encoding="utf-8"))
    mine = json.loads((Y.EVALS / f"{k['N11T']}.json").read_text(encoding="utf-8"))["trades"]
    base = {(t["entry_time"], t["tradingsymbol"]): t for t in json.loads((Y.EVALS / f"{k['N11']}.json").read_text(encoding="utf-8"))["trades"]}
    checks: dict = defaultdict(int)
    planned_over = []
    closed = defaultdict(list)
    for t in sorted(mine, key=lambda r: r["entry_time"]):
        qty, entry, exit_price = t["entry_qty"], t["entry_premium"], t["exit_premium"]
        lots = qty // 65
        assert lots in (1, 2), ("lot cap", t["entry_time"])
        extra = (200.0 + 5.0 * lots) * lots
        parent = (exit_price - entry) * qty - calc_fno_costs(entry, exit_price, qty) - extra
        kids = t.get("n10_children") or []
        assert abs(parent + sum(c["net"] for c in kids) - t["net_pnl"]) < 0.02, ("money", t["entry_time"])
        checks["money"] += 1
        by_time = {o.at.isoformat(): o for o in session(t["entry_time"][:10])}
        assert abs(quote_of(by_time[t["entry_time"]], t["tradingsymbol"]).ask - entry) < 0.001
        q = quote_of(by_time[t["exit_time"]], t["tradingsymbol"])
        assert abs((q.bid if q.bid > 0 else q.ltp) - exit_price) < 0.001
        checks["prices"] += 2
        day = t["entry_time"][:10]
        realised = sum(n for when, n in closed[day] if when <= t["entry_time"])
        same = base.get((t["entry_time"], t["tradingsymbol"]))
        if same is not None and t["entry_qty"] > same["entry_qty"]:
            assert vol_up(day), ("raised on a below-usual day", t["entry_time"])
            assert evidence(t["entry_time"]), ("raised on a losing record", t["entry_time"])
            assert realised >= 0, ("raised after a realised loss", t["entry_time"])
            assert lots == 2
            checks["raised_trades_conditions_hold"] += 1
            info = t.get("n11_entry") or {}
            stop = info.get("premium_stop") if info.get("raised_from") else round(0.75 * entry, 2)
            planned = (entry - stop) * qty + calc_fno_costs(entry, stop, qty) + extra
            if planned > LIMIT + 1e-6:
                planned_over.append({"at": t["entry_time"], "ask": entry, "stop": stop, "planned": round(planned, 2)})
            assert planned <= LIMIT + 1500.0, ("planned far past the limit", t["entry_time"], planned)
        closed[t["exit_time"][:10]].append((t["exit_time"], float(t["net_pnl"])))
    out = {"year": YEAR, "passed": True, "checks": dict(checks), "plan_wording_planned_loss_over_7500": planned_over,
           "note": "planned_over lists raised trades whose planned loss passes Rs 7,500 once fees and stress are counted: the frozen code's gap from PLAN.md's wording, handled by n11t_strict.py. Modelled quotes, not market depth."}
    (HERE / f"audit-{YEAR}.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out)[:900], flush=True)


if __name__ == "__main__":
    main()
