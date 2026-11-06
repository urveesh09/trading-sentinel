from dataclasses import replace
from datetime import timedelta

import pytest

from test_reclaim_execution import AT, NORMAL, entry
from test_shared_control import NOW, marks, observation
from config import settings
from fno_costs import calc_fno_costs
from reclaim_shared import RECLAIM, ReclaimControl, ReclaimQuote
from shared_control import SharedControl, Tick


def reclaim_quote(**kwargs):
    signal, chain = entry(**kwargs)
    return ReclaimQuote(signal, AT, chain, NORMAL, False)


def test_same_tick_native_priority_and_one_reclaim_attempt():
    book = ReclaimControl(250_000)
    result = book.step_with_reclaim(Tick(NOW, 0, entries={"NIFTY": observation("NIFTY")}), reclaim_quote())
    native = result.shared.entries[0]
    p = book.positions[native.position_id]
    assert native.reason == "accepted"
    assert result.entry.reason == "correlated_exposure_open"
    assert result.entry.open_premium_rs == p.entry_premium * p.qty
    assert result.entry.trades_today == 1
    at = NOW + timedelta(seconds=5)
    again = book.step_with_reclaim(Tick(at, 0, marks={"NIFTY": marks(at, p, future=25000)}), reclaim_quote(at=at))
    assert again.entry.reason == "already_attempted"
    assert len(book.positions) == 1


def test_shared_spread_reserve_and_reclaim_stress_are_real_cash():
    quote = reclaim_quote()
    plain = ReclaimControl(250_000)
    normal = plain.step_with_reclaim(Tick(NOW, 0), quote)
    p = plain.positions[normal.entry.position_id]
    reserve = p.entry_premium * p.qty + calc_fno_costs(p.entry_premium, 0, p.qty)
    stress = ReclaimControl(250_000, reclaim_stress=205)
    result = stress.step_with_reclaim(Tick(NOW, 250_000 - reserve - 100), quote)
    assert result.entry.cash_before_rs == pytest.approx(reserve + 100)
    assert result.entry.reason == "full_cash_reserve" and not stress.positions


def test_opposite_reclaim_can_use_remaining_book_capacity():
    book = ReclaimControl(250_000)
    outcome = book.step_with_reclaim(Tick(NOW, 0, entries={"NIFTY": observation("NIFTY")}),
                                     reclaim_quote(short=True))
    assert outcome.shared.entries[0].reason == outcome.entry.reason == "accepted"
    assert {p.direction for p in book.positions.values()} == {"LONG", "SHORT"}
    total = sum(p.entry_premium * p.qty for p in book.positions.values())
    assert total <= settings.FNO_MAX_OPEN_PREMIUM_PCT * book.equity
    assert book._trades[NOW.date()] == 2


def test_reclaim_uses_slot_and_blocks_later_native_when_full(monkeypatch):
    monkeypatch.setattr(settings, "FNO_MAX_CONCURRENT", 1)
    book, control = ReclaimControl(250_000), SharedControl(250_000)
    first = book.step_with_reclaim(Tick(NOW, 0), reclaim_quote())
    p = book.positions[first.entry.position_id]
    assert p.strategy == RECLAIM and p.lots == 1
    at = NOW + timedelta(seconds=10)
    tick = Tick(at, 0, entries={"NIFTY": observation("NIFTY", at, short=True)},
                marks={"NIFTY": marks(at, p, future=25000)})
    native = book.step_with_reclaim(tick).shared.entries[0]
    assert control.step(Tick(NOW, 0)).entries == ()
    assert control.step(tick).entries[0].reason == "accepted"
    assert native.reason == "concurrency"
    assert native.cash_before_rs == pytest.approx(250_000 - p.entry_premium * p.qty
                                                  - calc_fno_costs(p.entry_premium, 0, p.qty))


def test_reclaim_loss_changes_later_native_lot_ceiling_and_same_side_reentry():
    book, control = ReclaimControl(250_000), SharedControl(250_000)
    opened = book.step_with_reclaim(Tick(NOW, 0), reclaim_quote()).entry
    p = book.positions[opened.position_id]
    control.step(Tick(NOW, 0))
    at = NOW + timedelta(minutes=5)
    stopped = book.step_with_reclaim(Tick(at, 0, marks={"NIFTY": marks(at, p, future=p.stop_underlying,
                                                                   premium=p.entry_premium - 15)},
                                        entries={"NIFTY": observation("NIFTY", at, vol_up=True, positive=True)}))
    close, = stopped.shared.exits
    assert close.reason == "underlying_stop" and close.net < 0
    assert stopped.shared.entries[0].reason == "reentry_not_confirmed"
    assert book.equity == pytest.approx(250_000 + close.net)
    later = at + timedelta(minutes=5)
    short = Tick(later, 0, entries={"NIFTY": observation("NIFTY", later, short=True, vol_up=True, positive=True)})
    challenger = book.step_with_reclaim(short).shared.entries[0]
    baseline = control.step(short).entries[0]
    assert book.positions[challenger.position_id].lots == 1
    assert control.positions[baseline.position_id].lots == 2


def test_exact_bid_depth_and_futures_gap_are_visible_before_later_close():
    book = ReclaimControl(250_000)
    first = book.step_with_reclaim(Tick(NOW, 0), reclaim_quote())
    p = book.positions[first.entry.position_id]
    at = NOW + timedelta(seconds=10)
    shallow = book.step_with_reclaim(Tick(at, 0, marks={"NIFTY": marks(at, p, quantity=p.qty - 1)}))
    assert shallow.shared.missing_marks == (p.id,)
    at += timedelta(seconds=10)
    gap = book.step_with_reclaim(Tick(at, 0, marks={"NIFTY": marks(at, p)}))
    assert gap.held_gap == (at, "held_future_unavailable")
    at += timedelta(seconds=10)
    settled = book.step_with_reclaim(Tick(at, 0, marks={"NIFTY": marks(at, p, future=p.target_underlying,
                                                                  premium=p.entry_premium + 10)}))
    close, = settled.shared.exits
    assert close.reason == "midpoint_target" and not book.positions
    assert close.net == pytest.approx(p.qty * 10 - close.fees)


def test_no_reclaim_is_native_only_and_wrong_quote_clock_does_not_mutate():
    book, control = ReclaimControl(250_000), SharedControl(250_000)
    tick = Tick(NOW, 0, entries={"NIFTY": observation("NIFTY")})
    quote = reclaim_quote()
    with pytest.raises(ValueError, match="verified quote"):
        book.step_with_reclaim(tick, replace(quote, chain=replace(quote.chain, taken_at=AT)))
    with pytest.raises(ValueError, match="frozen completed bar"):
        book.step_with_reclaim(tick, replace(quote, signal_at=AT - timedelta(minutes=5)))
    assert not book.positions
    assert book.step_with_reclaim(tick).shared == control.step(tick)
    at = NOW.replace(hour=15, minute=10)
    p, = book.positions.values()
    flat = Tick(at, 0, marks={"NIFTY": marks(at, p, future=25000)})
    assert book.step_with_reclaim(flat).shared == control.step(flat)
    assert book.equity == control.equity
