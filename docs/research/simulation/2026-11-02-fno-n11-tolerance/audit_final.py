"""Independent audit of the final book after its frozen run: money and prices from raw quotes, and each raised trade against PLAN_FINAL.md's conditions, by their own code. Changes nothing. Writes audit-final-YEAR.json.

    N08_YEAR=<year> python audit_final.py
"""
from __future__ import annotations

import bisect
import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
N11 = HERE.parent / "2026-11-02-fno-n11"
sys.path[:0] = [str(HERE), str(N11)]
import stress as ST  # noqa: E402  (first: N09.1 has a stress.py too)
import n11t_final as F  # noqa: E402
from fno_costs import calc_fno_costs  # noqa: E402

L, Y, Z = F.L, F.Y, F.Z
YEAR = F.YEAR
LOCAL = F.LOCAL
LIMIT = 6250.0


def own_stop(entry: float, limit: float) -> float:
    """PLAN_FINAL.md's backstop, written out here rather than imported: the whole trade inside the limit, rounded up to the tick, never below 25%."""
    room = limit - calc_fno_costs(entry, entry, 130) - 420.0
    tight = round(math.ceil((entry - room / 130) / 0.05 - 1e-9) * 0.05, 2)
    return max(round(0.75 * entry, 2), tight)


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

    k = json.loads((LOCAL / f"keys-fpanel-{YEAR}.json").read_text(encoding="utf-8"))
    mine = json.loads((Y.EVALS / f"{k['FINAL']}.json").read_text(encoding="utf-8"))["trades"]
    base = {(t["entry_time"], t["tradingsymbol"]): t for t in json.loads((Y.EVALS / f"{k['N11']}.json").read_text(encoding="utf-8"))["trades"]}
    checks: dict = defaultdict(int)
    raised_rows = []
    closed = defaultdict(list)
    # The tolerance's own second lots, by the parity run's record of them. Any other trade with more lots than N11's reached two by the stance's existing rule, on its normal 25% backstop:
    # earlier gains made the book "proven" sooner. Those are the tolerance's knock-on, not the tolerance, so they aren't held to its limit.
    tolerance = set(json.loads((HERE / f"parity-final-{YEAR}.json").read_text(encoding="utf-8"))["raised_at"])
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
            assert lots == 2 and same["entry_qty"] == 65, ("raised past one lot", t["entry_time"])
            checks["raised_trades_conditions_hold"] += 1
            if t["entry_time"] not in tolerance:
                checks["two_lots_by_the_stance_not_the_tolerance"] += 1
                raised_rows.append({"at": t["entry_time"], "ask": entry, "by": "stance", "planned_at_25pct": round(0.25 * entry * qty + calc_fno_costs(entry, 0.75 * entry, qty) + extra, 2), "exit": t["exit_reason"], "net": round(float(t["net_pnl"]))})
            else:
                stop = own_stop(entry, LIMIT)        # at a full-size stance. A drawdown's smaller limit can only tighten it further
                planned = (entry - stop) * qty + calc_fno_costs(entry, stop, qty) + extra
                assert planned <= LIMIT + 1e-6, ("planned past the limit", t["entry_time"], planned)
                checks["tolerance_second_lots_planned_inside_the_limit"] += 1
                # A trade that left at its backstop left at or under that level: nothing kept it open below where the rule puts it. It may have left sooner on a tighter stop.
                if str(t["exit_reason"]).startswith("premium"):
                    assert exit_price <= stop + 0.001, ("backstop exit above the rule's level", t["entry_time"], exit_price, stop)
                    checks["backstop_exits_at_or_under_the_level"] += 1
                assert float(t["net_pnl"]) >= -(LIMIT + 1500.0), ("a raised trade lost far past its plan", t["entry_time"], t["net_pnl"])
                raised_rows.append({"at": t["entry_time"], "ask": entry, "by": "tolerance", "stop": stop, "planned": round(planned, 2), "exit": t["exit_reason"], "net": round(float(t["net_pnl"]))})
        closed[t["exit_time"][:10]].append((t["exit_time"], float(t["net_pnl"])))
    assert tolerance <= {t["entry_time"] for t in mine}, "every second lot the parity run recorded must be in the frozen book"
    assert checks["tolerance_second_lots_planned_inside_the_limit"] == len(tolerance), "every second lot the parity run recorded must be audited as one"
    out = {"year": YEAR, "passed": True, "checks": dict(checks), "raised": raised_rows, "note": "Modelled quotes, not market depth. A stop can gap: planned loss isn't a promise."}
    (HERE / f"audit-final-{YEAR}.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out)[:900], flush=True)


if __name__ == "__main__":
    main()
