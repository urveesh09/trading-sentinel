from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from test_reclaim_shared import reclaim_quote
from test_shared_control import NOW, add_stage, favorable_mark, marks, observation
from config import settings
from paired_reclaim import BASELINE, CHALLENGER, compare_reclaim
from reclaim_shared import ReclaimControl
from shared_control import SharedControl, Tick


def end():
    hour, minute = divmod(settings.FNO_HARD_FLAT_MIN, 60)
    return Tick(NOW.replace(hour=hour, minute=minute, second=0), 0)


def scenario(monkeypatch, *, earned, reclaim_loss=True):
    if earned:
        monkeypatch.setattr(settings, "FNO_MAX_RISK_PCT", .04)
        monkeypatch.setattr(settings, "FNO_MAX_LOSS_PER_TRADE", 9000)
        monkeypatch.setattr(settings, "FNO_MAX_OPEN_PREMIUM_PCT", .40)
        monkeypatch.setattr(settings, "FNO_N11_ADD_MAX_RUPEES", 9000)
    quote = reclaim_quote(short=True)
    shadow = ReclaimControl(250_000)
    first = Tick(NOW, 0)
    shadow.step_with_reclaim(first, quote)
    reclaim, = shadow.positions.values()
    at = NOW + timedelta(seconds=10)
    native = observation("NIFTY", at, vol_up=True, positive=True)
    future = reclaim.stop_underlying if reclaim_loss else reclaim.target_underlying
    premium = reclaim.entry_premium + (-15 if reclaim_loss else 15)
    reclaim_exit = marks(at, reclaim, future=future, premium=premium)
    entry = Tick(at, 0, entries={"NIFTY": native}, marks={"NIFTY": reclaim_exit})
    baseline = SharedControl(250_000)
    baseline.step(entry)
    parent, = baseline.positions.values()
    ticks = [first, entry]
    if earned:
        at += timedelta(seconds=10)
        ticks.append(Tick(at, 0, marks={"NIFTY": favorable_mark(at, parent, quantity=3 * parent.lot_size)},
                          earned=add_stage(at, parent, ask_quantity=parent.lot_size)))
    at += timedelta(seconds=10)
    close = marks(at, parent, future=parent.stop_underlying, premium=parent.entry_premium - 15,
                  quantity=3 * parent.lot_size)
    ticks.extend((Tick(at, 0, marks={"NIFTY": close}), end()))
    return ticks, (entry.at,), quote


def run(ticks, scans, quote, *, include_quote=True):
    return compare_reclaim(ticks, scans, signals={quote.signal_at: quote.signal},
                           quotes=(quote,) if include_quote else ())


def test_reclaim_stop_and_later_native_size_are_reconciled(monkeypatch):
    ticks, scans, quote = scenario(monkeypatch, earned=False)
    result = run(ticks, scans, quote)
    assert not result.pair.gaps
    closed, = result.reclaim_exits
    assert closed.reason == "underlying_stop" and closed.net < 0
    entry, = result.native_entries
    assert (entry.change.control.qty, entry.change.candidate.qty) == (130, 65)
    assert entry.baseline.directional_net == 0 and entry.challenger.directional_net == closed.net
    assert entry.challenger.trades_today == 1
    native, = result.native_trades
    assert native.ticket.kind == "parent" and native.ticket.at == scans[0]
    assert (native.baseline.qty, native.challenger.qty) == (130, 65)
    assert result.reclaim_net == Decimal(str(closed.net))
    assert result.native_net_delta == Decimal(str(native.challenger.exit.net)) - Decimal(str(native.baseline.exit.net))
    assert result.pair.net_delta == result.reclaim_net + result.native_net_delta


def test_earned_ticket_change_is_linked_to_parent(monkeypatch):
    ticks, scans, quote = scenario(monkeypatch, earned=True)
    result = run(ticks, scans, quote)
    assert not result.pair.gaps
    parent, earned = result.native_trades
    assert earned.ticket.parent_at == parent.ticket.at
    assert earned.ticket.signal_bar == parent.ticket.signal_bar
    assert earned.baseline_earned.reason == "accepted"
    assert earned.baseline.qty == 65 and earned.baseline.exit is not None
    assert earned.challenger is None
    assert result.pair.net_delta == result.reclaim_net + result.native_net_delta


def test_reclaim_open_shifts_native_id_without_changing_native_ticket(monkeypatch):
    ticks, scans, quote = scenario(monkeypatch, earned=False, reclaim_loss=False)
    result = run(ticks, scans, quote)
    assert not result.pair.gaps
    control, = result.pair.exits[BASELINE]
    reclaim, native = result.pair.exits[CHALLENGER]
    assert native.position_id != control.position_id
    assert result.native_trades == result.native_entries == ()
    assert result.native_net_delta == 0
    assert result.pair.net_delta == Decimal(str(reclaim.net))


def test_absent_packet_or_absent_clock_withholds_summary(monkeypatch):
    ticks, scans, quote = scenario(monkeypatch, earned=False)
    for tape, include in ((ticks, False), (ticks[1:], True)):
        result = run(tape, scans, quote, include_quote=include)
        assert result.pair.summaries is None and result.pair.net_delta is None
        assert result.reclaim_net is None and result.native_net_delta is None
        gap, = result.pair.gaps
        assert (gap.arm, gap.at, gap.reason) == (CHALLENGER, quote.signal_at, "reclaim_first_quote_missing")


def test_held_quote_gap_withholds_summary_even_if_later_settled(monkeypatch):
    ticks, scans, quote = scenario(monkeypatch, earned=False)
    # Keep the futures mark and remove only the held reclaim bid.
    stopped = ticks[1]
    ticks[1] = replace(stopped, marks={"NIFTY": replace(stopped.marks["NIFTY"], bids={})})
    final = ticks[2]
    bids = {**final.marks["NIFTY"].bids, **stopped.marks["NIFTY"].bids}
    ticks[2] = replace(final, marks={"NIFTY": replace(final.marks["NIFTY"], future=25_100, bids=bids)})
    result = run(ticks, scans, quote)
    assert result.reclaim_exits
    assert result.pair.summaries is None and result.native_net_delta is None
    assert any(gap.arm == CHALLENGER and gap.reason == "held_bid_missing" for gap in result.pair.gaps)


def test_quote_must_match_declared_frozen_signal(monkeypatch):
    ticks, scans, quote = scenario(monkeypatch, earned=False)
    wrong = replace(quote, signal=replace(quote.signal, target=quote.signal.target + 5))
    with pytest.raises(ValueError, match="declared signal"):
        compare_reclaim(ticks, scans, signals={quote.signal_at: quote.signal}, quotes=(wrong,))
    with pytest.raises(ValueError, match="declared signal"):
        compare_reclaim(ticks, scans, signals={quote.signal_at: quote.signal}, quotes=(quote, quote))


def test_late_reclaim_quote_does_not_count_as_executable_coverage():
    quote = reclaim_quote(at=NOW + timedelta(minutes=1))
    ticks = (Tick(NOW, 0), Tick(quote.chain.taken_at, 0), end())
    result = run(ticks, (NOW,), quote)
    gap, = result.pair.gaps
    assert gap.reason == "first_quote_outside_window"
    assert result.pair.net_delta is None


def test_empty_signal_receipt_preserves_native_parity_and_common_spread_cash():
    final = replace(end(), spread_closes=(700,))
    result = compare_reclaim((Tick(NOW, 5000), final), (NOW,), signals={}, quotes=())
    assert result.pair.uses_external_spreads and not result.pair.gaps
    assert result.pair.summaries[BASELINE] == result.pair.summaries[CHALLENGER]
    assert result.pair.summaries[BASELINE]["net"] == 700
    assert result.pair.net_delta == result.reclaim_net == result.native_net_delta == 0
    assert not result.native_trades and not result.native_entries
