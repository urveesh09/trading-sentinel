"""Independent audit of N11 after its frozen run: recompute it from raw quotes and walk the minutes again. Changes nothing. Writes audit-YEAR.json.

    N08_YEAR=<year> python audit_n11.py

It reuses the replay only to read quotes. The volatility reading, the paper evidence and the risk charge are recomputed here by their own code, not read back from the book.
"""
from __future__ import annotations

import bisect
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import stress as ST  # noqa: E402  (first: N09.1 has a stress.py too, and n11_lab puts its folder ahead of this one)
import n11_lab as L  # noqa: E402
from fno_costs import calc_fno_costs  # noqa: E402

Y, Z, T = L.Y, L.Z, L.T
YEAR = L.YEAR
LOCAL = L.LOCAL
RATIO, NEED, LIMIT, STOP_PCT = 0.9, 20, 5000.0, 0.25


def side(direction: str) -> int:
    return 1 if direction == "LONG" else -1


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

    def vol(day, ratio):
        atr, usual = vols.get(day, (None, None))
        return bool(atr is not None and usual is not None and atr >= usual * ratio)

    # the paper stream, rebuilt here from the saved one-lot trades of all four years
    paper = []
    diag = {}
    for y in ST.YEARS:
        key = json.loads((Z.LOCAL / f"keys-diag-{y}.json").read_text(encoding="utf-8"))["DIAG"]
        rows = json.loads((Z.LOCAL / f"evals-{y}" / f"{key}.json").read_text(encoding="utf-8"))["trades"]
        diag[y] = rows
        paper += [(datetime.fromisoformat(t["exit_time"]), float(t["net_pnl"])) for t in rows]
    paper.sort(key=lambda e: e[0])
    at = [e[0] for e in paper]
    nets = [e[1] for e in paper]

    def standing(now_iso):
        now = datetime.fromisoformat(now_iso)
        prior = nets[:bisect.bisect_left(at, now)]
        return (not vol(now_iso[:10], RATIO)) and len(prior) >= NEED and sum(prior[-NEED:]) <= 0

    checks = defaultdict(int)
    for phase, name in (("panel", "N11"), ("carry", "200")):
        key = json.loads((LOCAL / f"keys-{phase}-{YEAR}.json").read_text(encoding="utf-8"))[name]
        obj = json.loads((Y.EVALS / f"{key}.json").read_text(encoding="utf-8"))
        assert obj["book"]["n091"]["mode"] == "VOL_CLOCK" and "watch" not in obj["book"]["n10"], "no reserve, no WATCH"
        closed_today = defaultdict(list)
        for t in sorted(obj["trades"], key=lambda r: r["entry_time"]):
            qty, entry, exit_price = t["entry_qty"], t["entry_premium"], t["exit_premium"]
            lots = qty // 65
            assert lots in (1, 2), ("lot cap", t["entry_time"])
            # money, including every earned lot
            extra = (200.0 + 5.0 * lots) * lots
            parent = (exit_price - entry) * qty - calc_fno_costs(entry, exit_price, qty) - extra
            kids = t.get("n10_children") or []
            assert len(kids) <= 1 and lots + len(kids) <= 3
            for c in kids:
                own = (c["bid"] - c["ask"]) * c["qty"] - calc_fno_costs(c["ask"], c["bid"], c["qty"]) - c["extra"]
                assert abs(own - c["net"]) < 0.01 and c["extra"] == 205.0, ("child money", t["entry_time"])
            assert abs(parent + sum(c["net"] for c in kids) - t["net_pnl"]) < 0.02, ("money", t["entry_time"], parent, t["net_pnl"])
            checks["money"] += 1
            # prices against the raw quotes
            day = t["entry_time"][:10]
            by_time = {o.at.isoformat(): o for o in session(day)}
            assert abs(quote_of(by_time[t["entry_time"]], t["tradingsymbol"]).ask - entry) < 0.001
            q = quote_of(by_time[t["exit_time"]], t["tradingsymbol"])
            assert abs((q.bid if q.bid > 0 else q.ltp) - exit_price) < 0.001
            checks["prices"] += 2
            # the stand-aside: no real entry while both readings are against
            assert not standing(t["entry_time"]), ("entered while standing aside", t["entry_time"])
            checks["no_entry_while_standing_aside"] += 1
            # size by volatility, the morning rule, one lot after a loss
            minute = int(t["entry_time"][11:13]) * 60 + int(t["entry_time"][14:16])
            if not vol(day, 1.0):
                assert lots == 1, ("two lots on a below-usual day", t["entry_time"])
                checks["one_lot_on_low_volatility"] += 1
            if t["member"] == 4 and minute >= 720:
                assert lots == 1, ("late low-day two lots", t["entry_time"])
                checks["morning_rule"] += 1
            earlier = [n for when, n in closed_today[day] if when <= t["entry_time"]]
            if sum(earlier) < 0:
                assert lots == 1, ("two lots after a realised loss today", t["entry_time"], earlier)
                checks["one_lot_after_a_loss"] += 1
            closed_today[t["exit_time"][:10]].append((t["exit_time"], t["net_pnl"]))
            # the earned lot: a two-lot trade, at or beyond +1R, before 14:45, within the charge, and its life walked again
            r = abs(t["entry_underlying"] - t["initial_stop_underlying"])
            for c in kids:
                assert lots == 2, "an earned lot only on a two-lot trade"
                checks["two_lot_parent"] += 1
                add = by_time[c["at"]]
                q2 = quote_of(add, t["tradingsymbol"])
                assert abs(q2.ask - c["ask"]) < 0.001 and abs(add.future.ltp - c["future"]) < 0.001
                checks["prices"] += 1
                now = datetime.fromisoformat(c["at"])
                assert (add.future.ltp - t["entry_underlying"]) * side(t["direction"]) >= r - 1e-6, "added before +1R"
                assert now.hour * 60 + now.minute < 14 * 60 + 45, "added at or after the last-entry time"
                child_stop = c["ask"] * (1 - STOP_PCT)
                child_loss = (c["ask"] - child_stop) * c["qty"] + calc_fno_costs(c["ask"], child_stop, c["qty"]) + 205.0
                assert abs(child_loss - c["risk"]) < 0.5, ("child charge is the whole backstop", c["risk"], child_loss)
                assert c["planned_total"] <= LIMIT + 1e-6 and c["limit"] <= LIMIT + 1e-6, ("planned", c)
                checks["planned_within_5000"] += 1
                assert abs(c["premium_stop"] - round(c["ask"] * (1 - STOP_PCT), 2)) < 0.011
                out = datetime.fromisoformat(c["exit_at"])
                for o in session(day):
                    if now < o.at < out:
                        bid = quote_of(o, t["tradingsymbol"]).bid
                        assert (o.future.ltp - c["level"]) * side(t["direction"]) > 0, ("missed the level", o.at)
                        assert bid <= 0 or bid > c["premium_stop"], ("missed the backstop", o.at)
                checks["no_missed_stop"] += 1
                q3 = quote_of(by_time[c["exit_at"]], t["tradingsymbol"])
                assert abs((q3.bid if q3.bid > 0 else q3.ltp) - c["bid"]) < 0.001
                checks["prices"] += 1
                if c["reason"].startswith("with_first"):
                    assert c["exit_at"] == t["exit_time"] and abs(c["bid"] - exit_price) < 0.001
    # check 12: the earned lot never changes how the held lots live, on any trade in both books
    k = json.loads((LOCAL / f"keys-panel-{YEAR}.json").read_text(encoding="utf-8"))
    n11 = {(t["entry_time"], t["tradingsymbol"]): t for t in json.loads((Y.EVALS / f"{k['N11']}.json").read_text(encoding="utf-8"))["trades"]}
    bare = {(t["entry_time"], t["tradingsymbol"]): t for t in json.loads((Y.EVALS / f"{k['NO_ADD']}.json").read_text(encoding="utf-8"))["trades"]}
    for kk in n11.keys() & bare.keys():
        a, b = n11[kk], bare[kk]
        assert (a["exit_time"], a["exit_premium"], a["exit_reason"]) == (b["exit_time"], b["exit_premium"], b["exit_reason"]), ("held lots changed", kk)
        if a["entry_qty"] == b["entry_qty"]:
            checks["held_lots_identical"] += 1
    # the stand-aside fired where it says: a paper signal in the state must not be a real trade
    real = {(t["entry_time"], t["tradingsymbol"]) for t in n11.values()}
    for t in diag[YEAR]:
        if standing(t["entry_time"]):
            assert (t["entry_time"], t["tradingsymbol"]) not in real, ("a paper trade in the state became real", t["entry_time"])
            checks["paper_trades_in_the_state_not_taken"] += 1
    out = {"year": YEAR, "passed": True, "checks": dict(checks), "note": "Modelled quotes from candles, not market depth. An audit of the replay's arithmetic and clocks, not of future profit."}
    (HERE / f"audit-{YEAR}.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out), flush=True)


if __name__ == "__main__":
    main()
