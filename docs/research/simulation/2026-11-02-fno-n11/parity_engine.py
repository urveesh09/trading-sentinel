"""Does the engine's live N11 decide what research's N11 decided? Replays a year through the research stack and, at every entry tick, asks the engine's own fno_book.n11_signal the same
question on the same bars. Also compares the live size rule and EFF's clock on every trade. Research only. Writes parity-engine-YEAR.json.

    N08_YEAR=<year> python parity_engine.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import n11_lab as L  # noqa: E402
import fno_book  # noqa: E402
import fno_n11  # noqa: E402
from config import settings  # noqa: E402

Y, Z, B, X = L.Y, L.Z, L.B, L.X
YEAR = L.YEAR
REPORT = {"ticks_compared": 0, "signals_research": 0, "signals_engine": 0, "same_signal": 0, "mismatches": [], "ceiling_compared": 0, "ceiling_mismatches": []}
_route = Y.BookReplay.route


def route(self, frame, regime, now):
    """Research decides. The engine then answers from the same frame, with its own retest state and the same trend reading."""
    research = _route(self, frame, regime, now)
    row = self.table.get(now.date().isoformat())
    high, low = Y.ROUTER.allowed(self.members[0]["gate"], row), Y.ROUTER.allowed(self.members[4]["gate"], row)
    side = "HIGH" if high else "LOW" if low else None
    shipped = self._signal(0, frame, regime, now, Y.replay._last_closed_bar(frame, now))
    engine = fno_book.n11_signal(frame, regime, now, shipped=shipped, adx_side=side, underlying="NIFTY")
    REPORT["ticks_compared"] += 1
    r_dir = research.direction.value if research.direction is not None else None
    e_dir = engine.direction.value if engine.direction is not None else None
    if research.reject_reason == "n11:stand_aside":
        # By design: the engine's signal still fires here, for the paper record, and fno_orchestrator refuses the real entry one step later.
        REPORT["stood_aside_ticks"] = REPORT.get("stood_aside_ticks", 0) + 1
        REPORT["stood_aside_engine_fired"] = REPORT.get("stood_aside_engine_fired", 0) + (e_dir is not None)
        return research
    REPORT["signals_research"] += r_dir is not None
    REPORT["signals_engine"] += e_dir is not None
    if r_dir is not None and self._fired is not None:
        names = {0: "N11_SHIPPED", 1: "N11_OR20", 2: "N11_EFF", 3: "N11_TPB", 4: "N11_TPB_LOW"}
        same = r_dir == e_dir and engine.strategy == names[self._fired] and abs(float(engine.stop_underlying) - float(research.stop_underlying)) < 1e-6 and abs(float(engine.target_underlying) - float(research.target_underlying)) < 1e-6 and engine.bar_ts == research.bar_ts
    else:
        same = r_dir == e_dir
    if same:
        REPORT["same_signal"] += r_dir is not None
    elif len(REPORT["mismatches"]) < 40:
        REPORT["mismatches"].append({"at": now.isoformat(), "research": [r_dir, self._fired, research.reject_reason], "engine": [e_dir, engine.strategy, engine.reject_reason]})
    else:
        REPORT["mismatches"].append(None)
    return research


Y.BookReplay.route = route
_planner = L.planner


def planner(sig, snap, regime, now, state):
    """The live ceiling against what research's route left in the settings, whenever research plans an entry."""
    engine = L.T.ENGINE["now"]
    if engine is not None and engine.book.get("n11") and engine._fired is not None:
        names = {0: "N11_SHIPPED", 1: "N11_OR20", 2: "N11_EFF", 3: "N11_TPB", 4: "N11_TPB_LOW"}
        minute = now.hour * 60 + now.minute
        realised = L.realised_today(engine._n10_book, now)
        live = fno_n11.lot_ceiling(names[engine._fired], minute, L.vol_up(now), realised)
        ceiling = min(settings.FNO_MAX_LOTS, settings.FNO_MAX_LOTS_PROVEN)
        ceiling = 1 if realised < 0 else ceiling
        REPORT["ceiling_compared"] += 1
        if live != ceiling and len(REPORT["ceiling_mismatches"]) < 40:
            REPORT["ceiling_mismatches"].append({"at": now.isoformat(), "live": live, "research": ceiling, "fired": engine._fired})
    return _planner(sig, snap, regime, now, state)


L.T._planner = planner


def main() -> None:
    Z.B.L._init()
    Y.dataset("year")
    book = L.n11_book()
    with Y.ROUTER.dispatch():
        engine = Y.BookReplay(Y.dataset("year"), book, Y.table("year"), "year")
        result = engine.run(*B.C.WINDOW)
    nets = round(sum(t["net_pnl"] for t in result["trades"] if t.get("net_pnl") is not None), 2)
    extra = REPORT["mismatches"].count(None)
    REPORT["mismatches"] = [m for m in REPORT["mismatches"] if m]
    out = {"year": YEAR, "research_replay_net": nets, "research_trades": len(result["trades"]), "mismatch_count": len(REPORT["mismatches"]) + extra, **REPORT}
    (HERE / f"parity-engine-{YEAR}.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k not in ("mismatches", "ceiling_mismatches")}), flush=True)
    print("first mismatches", json.dumps(out["mismatches"][:8]), flush=True)
    print("ceiling mismatches", json.dumps(out["ceiling_mismatches"][:6]), flush=True)


if __name__ == "__main__":
    main()
