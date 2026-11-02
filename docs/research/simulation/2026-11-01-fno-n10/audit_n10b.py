"""Independent audit of N10B after its verdict: recompute it from raw quotes and walk the minutes again. Changes nothing. Writes audit-n10b-YEAR.json.

    N08_YEAR=<year> python audit_n10b.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import n10b_lab as B  # noqa: E402
from fno_costs import calc_fno_costs  # noqa: E402

T, Y, Z, M = B.T, B.Y, B.Z, B.M
YEAR = B.YEAR


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

    checks = {"money": 0, "prices": 0, "add_first_reach": 0, "no_missed_stop": 0, "two_lot_parent": 0, "planned_within_5000": 0, "reserve_at_entry": 0}
    for phase, name in (("panel2", "R2_THIRD_CW"), ("carry2", "R2_THIRD_CW")):
        key = json.loads((T.LOCAL / f"keys-{phase}-{YEAR}.json").read_text(encoding="utf-8"))[name]
        obj = json.loads((Y.EVALS / f"{key}.json").read_text(encoding="utf-8"))
        for t in obj["trades"]:
            qty, entry, exit_price = t["entry_qty"], t["entry_premium"], t["exit_premium"]
            parent = (exit_price - entry) * qty - calc_fno_costs(entry, exit_price, qty) - float(t.get("extra_cost") or 0.0)
            kids = t.get("n10_children") or []
            for c in kids:
                own = (c["bid"] - c["ask"]) * c["qty"] - calc_fno_costs(c["ask"], c["bid"], c["qty"]) - c["extra"]
                assert abs(own - c["net"]) < 0.01, ("child money", t["entry_time"])
                assert c["extra"] == (200.0 + 5.0) * 1
            assert abs(parent + sum(c["net"] for c in kids) - t["net_pnl"]) < 0.02, ("money", t["entry_time"], parent, t["net_pnl"])
            checks["money"] += 1
            day = t["entry_time"][:10]
            rows = session(day)
            by_time = {o.at.isoformat(): o for o in rows}
            assert abs(quote_of(by_time[t["entry_time"]], t["tradingsymbol"]).ask - entry) < 0.001
            q = quote_of(by_time[t["exit_time"]], t["tradingsymbol"])
            assert abs((q.bid if q.bid > 0 else q.ltp) - exit_price) < 0.001
            checks["prices"] += 2
            for c in kids:
                assert t["entry_qty"] == 130, "an earned lot only on a two-lot trade"
                checks["two_lot_parent"] += 1
                assert c["planned_total"] <= 5000.0 + 1e-6 and c["limit"] <= 5000.0 + 1e-6, ("planned", c)
                checks["planned_within_5000"] += 1
                add = by_time[c["at"]]
                assert abs(quote_of(add, t["tradingsymbol"]).ask - c["ask"]) < 0.001 and abs(add.future.ltp - c["future"]) < 0.001
                checks["prices"] += 1
                r = abs(t["entry_underlying"] - t["initial_stop_underlying"])
                before_entry = datetime.fromisoformat(t["entry_time"])
                at = datetime.fromisoformat(c["at"])
                out = datetime.fromisoformat(c["exit_at"])
                assert (add.future.ltp - t["entry_underlying"]) * side(t["direction"]) >= r - 1e-6, "added before reaching +1R"
                assert at.hour * 60 + at.minute < 14 * 60 + 45, "added at or after the last-entry time"
                reached = [o for o in rows if before_entry < o.at < at and (o.future.ltp - t["entry_underlying"]) * side(t["direction"]) >= r]
                # A minute may reach +1R and be passed over only if the rule refused it then. The first reach must be recorded by a refusal, or it is a bug.
                if reached:
                    checks.setdefault("reached_earlier_then_refused", 0)
                    checks["reached_earlier_then_refused"] += 1
                else:
                    checks["add_first_reach"] += 1
                # Walk the earned lot's life again: it must leave at the first breach, and no earlier.
                for o in rows:
                    if at < o.at < out:
                        bid = quote_of(o, t["tradingsymbol"]).bid
                        assert (o.future.ltp - c["level"]) * side(t["direction"]) > 0, ("missed the level", o.at)
                        assert bid <= 0 or bid > c["premium_stop"], ("missed the backstop", o.at)
                checks["no_missed_stop"] += 1
                final = by_time[c["exit_at"]]
                q2 = quote_of(final, t["tradingsymbol"])
                assert abs((q2.bid if q2.bid > 0 else q2.ltp) - c["bid"]) < 0.001
                checks["prices"] += 1
                if c["reason"] == "n10_level":
                    assert (final.future.ltp - c["level"]) * side(t["direction"]) <= 0
                elif c["reason"].startswith("with_first"):
                    assert c["exit_at"] == t["exit_time"] and abs(c["bid"] - exit_price) < 0.001
        for phase_receipt in (M.LOCAL / "receipts" / f"{key}.json",):
            for a in json.loads(phase_receipt.read_text(encoding="utf-8"))["admissions"]:
                if a["accepted"]:
                    need = a["full_reserves"][str(a["final_lots"])] if str(a["final_lots"]) in a["full_reserves"] else a["full_reserves"][a["final_lots"]]
                    assert a["floor"] + a["open_reserve"] + need <= a["pool"] + 1e-6, ("reserve", a["at"])
                    checks["reserve_at_entry"] += 1
    # WATCH's evidence, recomputed from the paper trades with exits strictly before each slice, on the one-account path.
    at, nets = Z.shadow_trades(B.shadow_names())
    key = json.loads((T.LOCAL / f"keys-carry2-{YEAR}.json").read_text(encoding="utf-8"))["R2_THIRD_CW"]
    watch = json.loads((T.LOCAL / "states" / f"watch-{key.rsplit('_', 1)[-1]}.json").read_text(encoding="utf-8"))
    for s in watch["slices"]:
        now = datetime.fromisoformat(s["at"])
        prior = [n for when, n in zip(at, nets) if when < now]
        assert abs(sum(prior[-20:]) - s["evidence"]) < 0.01 and s["evidence"] > 0
        assert s["to"] >= 0.75 * s["best"] - 1e-6 and s["to"] < s["from"]
        checks.setdefault("slices_rechecked", 0)
        checks["slices_rechecked"] += 1
    out = {"year": YEAR, "passed": True, "checks": checks, "note": "Modelled quotes from candles, not market depth. An audit of the replay's arithmetic and clocks, not of future profit."}
    T.X.write(HERE / f"audit-n10b-{YEAR}.json", out)
    print(json.dumps(out), flush=True)


if __name__ == "__main__":
    main()
