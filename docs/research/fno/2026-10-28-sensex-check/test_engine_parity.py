"""O29d: the engine's SENSEX path against the SENSEX check it was switched on after.

  - the engine's seeded SENSEX drives and sides equal the check's table on every session;
  - the engine path (raw SENSEX bars, the shipped signal with NIFTY as ``rvol_bars``, the seeded SENSEX history and
    ``fno_book.with_participation`` for the book's strategies) trades exactly as the check's UNION_DRIVE arm over
    Sep 10 - Oct 28.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("o29d_check", HERE / "check.py")
check = importlib.util.module_from_spec(spec)
sys.modules["o29d_check"] = check
spec.loader.exec_module(check)
replay, router = check.replay, check.router

import fno_book  # noqa: E402
import fno_costs  # noqa: E402
from fno_engine_mom import MomSignal, evaluate_fno_mom  # noqa: E402

RESULTS = HERE / "results.json"
READY = (check.LOCAL / "drives.json").is_file() and all(
    (check.CACHE / f"{d}.pkl").is_file() for d in json.loads(RESULTS.read_text(encoding="utf-8"))["sessions"])


class RawSensexData(check.SensexData):
    """SENSEX bars with their own (thin) volume, as the engine fetches them."""

    def futures_frame(self, token, day):
        return replay.ReplayData.futures_frame(self, token, day)


class EngineSensexBook(check.SensexBook):
    """The orchestrator's SENSEX path: NIFTY's bars as rvol_bars, the seeded SENSEX history."""

    def route(self, frame, regime, now) -> MomSignal:
        day = now.date()
        nifty = replay.ReplayData.futures_frame(self.data, router.front_token(day), day)
        shipped = evaluate_fno_mom(frame, regime, now, rvol_bars=nifty)
        history = [v for d, v in sorted(fno_book.SEEDS["SENSEX"].items()) if d < day.isoformat()]
        side = fno_book.drive_side(fno_book.opening_drive(frame, day, now), history)
        sig = fno_book.book_signal(fno_book.with_participation(frame, nifty), regime, now, shipped=shipped, side=side)
        self._fired = sig.strategy or None
        return sig


@pytest.mark.skipif(not READY, reason="O29d data not on this machine")
def test_the_engine_sensex_seed_and_sides_equal_the_check():
    drives = json.loads((check.LOCAL / "drives.json").read_text(encoding="utf-8"))
    table = json.loads(RESULTS.read_text(encoding="utf-8"))["sensex_drive"]
    assert fno_book.SEEDS["SENSEX"] == drives
    ordered = sorted(drives)
    for i, d in enumerate(ordered):
        assert fno_book.drive_side(drives[d], [drives[x] for x in ordered[:i]]) == table[d]["side"], d


@pytest.mark.skipif(not READY, reason="O29d data not on this machine")
def test_the_engine_sensex_path_trades_exactly_as_the_check():
    want = json.loads(RESULTS.read_text(encoding="utf-8"))["union_drive_trades"]
    original = fno_costs.calc_fno_costs
    try:
        check._bfo_costs()
        with router.dispatch():
            got = EngineSensexBook(RawSensexData(check.DATA, check.CACHE), "UNION_DRIVE",
                                   json.loads((check.LOCAL / "drives.json").read_text(encoding="utf-8"))
                                   ).run(*check.FULL)["trades"]
    finally:
        fno_costs.calc_fno_costs = original
    keys = ("bar_ts", "component", "tradingsymbol", "entry_premium", "exit_premium", "exit_reason", "net_pnl")
    assert [{k: t.get(k) for k in keys} for t in got] == [{k: t.get(k) for k in keys} for t in want]
    assert len(got) == 30
