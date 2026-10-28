"""O29c: the engine's book (python-engine/fno_book.py) against the research it ports.

  - the engine's opening drive and HIGH/LOW side equal the research table on every session (with the seeded history);
  - the engine's book, replayed through the shipped single-leg book with its own per-strategy exits, trades exactly as
    the research UNION_DRIVE (O28 THEORY_DRIVE, panel C's arm) over Sep 10 - Oct 28.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("o29b_study", HERE / "study.py")
study = importlib.util.module_from_spec(spec)
sys.modules["o29b_study"] = study
spec.loader.exec_module(study)
router, replay = study.router, study.replay

import fno_book  # noqa: E402
from fno_engine_mom import MomSignal, evaluate_fno_mom  # noqa: E402

READY = (study.DATA / "manifest.json").is_file() and (study.EVALS / f"{study.digest(study.UNION_DRIVE)}.json").is_file()
ENGINE_POLICIES = {name: replay.ReplayPolicy(name=f"BOOK_{name}", manage_every_observation=True,
                                             exit_overrides=tuple(sorted(fno_book.EXIT_OVERRIDES[name].items())))
                   for name in fno_book.STRATEGIES}


def _research_sides() -> dict:
    bars = study.futures_bars()
    rows = router.with_sides(router.day_rows({t: f[["open", "high", "low", "close"]] for t, f in bars.items()}))
    return {d: (r["open_drive"], r["side"]["open_drive"]) for d, r in rows.items()}


class EngineBookReplay(router.RouterReplay):
    """The shipped book with the engine's book signal; each leg managed with the engine's exits for its strategy."""

    def __init__(self, data):
        super().__init__(data, {"engine": fno_book.BOOK}, {}, {})

    def route(self, frame, regime, now) -> MomSignal:
        day = now.date()
        value = fno_book.opening_drive(frame, day, now)
        history = [v for d, v in sorted(fno_book.SEED.items()) if d < day.isoformat()]
        side = fno_book.drive_side(value, history)
        sig = fno_book.book_signal(frame, regime, now, shipped=evaluate_fno_mom(frame, regime, now), side=side)
        self._fired = sig.strategy or None
        return sig

    def _manage(self, book, obs, now):
        base, full = self.policy, book.open
        try:
            for leg_id in sorted(full):
                leg, comp = full[leg_id], self.leg_component[leg_id]
                before = len(book.trades)
                book.open = {leg_id: leg}
                self.policy = ENGINE_POLICIES[comp]
                replay.SingleLegReplay._manage(self, book, obs, now)
                for trade in book.trades[before:]:
                    trade["component"], trade["entry_qty"] = comp, leg.initial_qty
                if leg_id not in book.open:
                    del full[leg_id]
        finally:
            book.open, self.policy = full, base


@pytest.mark.skipif(not READY, reason="O29b data not on this machine")
def test_the_engine_drive_and_side_equal_the_research_table():
    research = _research_sides()
    data = study.grid.CachedReplayData(study.DATA, study.CACHE)
    for day in study.sessions():
        obs, _ = data.observations(day)
        frame = data.futures_frame(obs[0].future.contract.token, date.fromisoformat(day))
        at = study.pd.Timestamp(f"{day} 09:46:00").to_pydatetime()
        value = fno_book.opening_drive(frame, date.fromisoformat(day), at)
        history = [v for d, v in sorted(fno_book.SEED.items()) if d < day]
        want_value, want_side = research[day]
        assert value == want_value and fno_book.SEED[day] == want_value, day
        assert fno_book.drive_side(value, history) == want_side, day
        assert fno_book.opening_drive(frame, date.fromisoformat(day), at.replace(minute=44)) is None   # 09:44: not yet


@pytest.mark.skipif(not READY, reason="O29b data not on this machine")
def test_the_engine_book_trades_exactly_as_the_research_union_drive():
    want = json.loads((study.EVALS / f"{study.digest(study.UNION_DRIVE)}.json").read_text(encoding="utf-8"))["trades"]
    study.router.NIFTY_FUTURES.update(study.NOV_FUTURE)
    with router.dispatch():
        got = EngineBookReplay(study.grid.CachedReplayData(study.DATA, study.CACHE)).run(*study.FULL)["trades"]
    keys = ("bar_ts", "tradingsymbol", "entry_time", "entry_premium", "exit_time", "exit_premium", "exit_reason",
            "net_pnl", "component")
    assert [{k: t.get(k) for k in keys} for t in got] == [{k: t.get(k) for k in keys} for t in want]
    assert len(got) == 33 and {t["component"] for t in got} <= set(fno_book.STRATEGIES)
