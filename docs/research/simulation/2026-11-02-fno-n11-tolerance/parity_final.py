"""Does the engine's live second lot decide what the final book decided? Replays a year through the research stack and, at every planned entry, asks the engine's own fno_n11.second_lot the same question on
the same plan and state, then checks the backstop on every raised trade. Research only. Writes parity-final-YEAR.json.

    N08_YEAR=<year> python parity_final.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import n11t_final as F  # noqa: E402
import fno_n11  # noqa: E402

Q, L, Y, B = F.Q, F.L, F.Y, F.B
YEAR = F.YEAR
NAMES = {0: "N11_SHIPPED", 1: "N11_OR20", 2: "N11_EFF", 3: "N11_TPB", 4: "N11_TPB_LOW"}
REPORT = {"decisions_compared": 0, "research_raised": 0, "engine_raised": 0, "by_reason": {}, "decision_mismatches": [], "limit_mismatches": [], "stops_compared": 0, "stops_tightened": 0, "stop_mismatches": [], "planned_over_limit": [], "raised_but_not_entered": 0, "raised_at": []}
_second = Q.second_lot


def second_lot(engine, cfg, n11, sig, snap, regime, now, state):
    """Research decides, by its own path. The engine then answers from N11's one-lot plan, with its own readings of the same facts."""
    flag = n11.get("true_risk")
    n11["true_risk"] = False
    try:
        first = Q._planner(sig, snap, regime, now, state)
    finally:
        n11["true_risk"] = flag
    before = engine.notes["n11t_second_lots"]
    out = _second(engine, cfg, n11, sig, snap, regime, now, state)
    raised = engine.notes["n11t_second_lots"] > before
    minute = now.hour * 60 + now.minute
    ceiling = fno_n11.lot_ceiling(NAMES[engine._fired], minute, L.vol_up(now), L.realised_today(engine._n10_book, now)) if engine._fired is not None else 1
    mine = fno_n11.second_lot(first, state, stop_points=abs(float(snap.forward) - float(sig.stop_underlying)), ceiling=ceiling, is_vol_up=L.vol_up(now), is_paper_positive=fno_n11.paper_positive(L.paper_before(now)))
    REPORT["decisions_compared"] += 1
    REPORT["research_raised"] += raised
    REPORT["engine_raised"] += mine is not None
    if mine is not None:
        REPORT["by_reason"][mine.reason] = REPORT["by_reason"].get(mine.reason, 0) + 1
    if raised != (mine is not None) or (raised and out.lots != mine.plan.lots):
        REPORT["decision_mismatches"].append({"at": now.isoformat(), "research": out.lots if out.accepted else None, "first": first.lots if first.accepted else None, "engine": mine.plan.lots if mine else None, "ask": first.quote.ask if first.quote else None, "delta": first.delta, "m": state.risk_multiplier, "ceiling": ceiling})
    if raised and mine is not None and abs(engine._n11t_limit - mine.limit) > 1e-9:
        REPORT["limit_mismatches"].append({"at": now.isoformat(), "research": engine._n11t_limit, "engine": mine.limit})
    engine._parity_second = mine if raised else None
    return out


Q.second_lot = second_lot
_entry = Y.BookReplay._entry


def entry(self, book, obs, frame, day, now):
    self._parity_second = None
    before = book.next_id
    _entry(self, book, obs, frame, day, now)
    mine = self._parity_second
    if mine is None:
        return
    if book.next_id == before:
        REPORT["raised_but_not_entered"] += 1
        return
    leg = book.open[before]
    REPORT["raised_at"].append(now.isoformat())
    native = round(0.75 * leg.entry_premium, 2)
    stop = fno_n11.second_lot_stop(leg.entry_premium, leg.qty, leg.lots, mine.limit, native)
    REPORT["stops_compared"] += 1
    REPORT["stops_tightened"] += stop > native
    if abs(stop - leg.premium_stop) > 1e-9:
        REPORT["stop_mismatches"].append({"at": now.isoformat(), "research": leg.premium_stop, "engine": stop, "fill": leg.entry_premium})
    planned = (leg.entry_premium - stop) * leg.qty + fno_n11.calc_fno_costs(leg.entry_premium, stop, leg.qty) + fno_n11.extra_cost(leg.lots)
    if planned > mine.limit + 1e-6:
        REPORT["planned_over_limit"].append({"at": now.isoformat(), "planned": round(planned, 2), "limit": mine.limit})


Y.BookReplay._entry = entry


def main() -> None:
    B.L._init()
    data = Y.dataset("year")
    book = F.book("FINAL")
    with Y.ROUTER.dispatch():
        engine = Y.BookReplay(data, book, Y.table("year"), "year")
        result = engine.run(*B.C.WINDOW)
    nets = round(sum(t["net_pnl"] for t in result["trades"] if t.get("net_pnl") is not None), 2)
    keys = json.loads((F.LOCAL / f"keys-fpanel-{YEAR}.json").read_text(encoding="utf-8"))
    frozen = round(sum(t["net_pnl"] for t in json.loads((Y.EVALS / f"{keys['FINAL']}.json").read_text(encoding="utf-8"))["trades"] if t.get("net_pnl") is not None), 2)
    out = {"year": YEAR, "research_replay_net": nets, "frozen_panel_net": frozen, "trades": len(result["trades"]), **REPORT,
           "mismatch_count": len(REPORT["decision_mismatches"]) + len(REPORT["limit_mismatches"]) + len(REPORT["stop_mismatches"]) + len(REPORT["planned_over_limit"]) + (0 if abs(nets - frozen) < 0.01 else 1)}
    (HERE / f"parity-final-{YEAR}.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out)[:1400], flush=True)


if __name__ == "__main__":
    main()
