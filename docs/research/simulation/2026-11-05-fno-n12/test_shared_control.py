from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
import sys

import pytest


HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[3] / "python-engine")]
import options_math
from config import settings
from fno_chain import ChainSnapshot, RISK_FREE_RATE, years_to_expiry
from fno_costs import calc_fno_costs
from fno_engine_mom import MomSignal
from fno_exit_rules import IST
from fno_models import Contract, ContractQuote, FnoDirection
from control_gate import GateTape, ShadowClose, VolatilityReading
from shared_control import EarnedQuote, EarnedStage, EntryObservation, SharedControl, Tick, VenueMarks


NOW = IST.localize(datetime(2026, 9, 14, 10, 0, 30))
EXPIRY = date(2026, 9, 22)


def observation(venue, at=NOW, *, short=False, vol_up=False, positive=False, expiry=False, strategy="N11_EFF"):
    forward, lot, step = (25_000, 65, 50) if venue == "NIFTY" else (80_000, 20, 100)
    iv = 0.145 if venue == "NIFTY" else 0.11
    quotes = {}
    for token, offset in enumerate(range(-4, 5), 200):
        strike = forward + offset * step
        for call, right in [(True, "CE"), (False, "PE")]:
            mid = options_math.black76_price(forward, strike, years_to_expiry(EXPIRY, at),
                                             iv, RISK_FREE_RATE, call)
            contract = Contract(token * 2 + int(call), f"{venue}{strike}{right}", venue,
                                EXPIRY, strike, right, lot)
            quotes[strike, right] = ContractQuote(
                contract, bid=round(mid * 0.998, 2), ask=round(mid * 1.002, 2),
                ltp=round(mid, 2), oi=50_000, volume=20_000,
                last_trade_time=at - timedelta(seconds=2), ask_quantity=2 * lot,
            )
    chain = ChainSnapshot(at, EXPIRY, forward, None, lot, None, quotes)
    slot = at.replace(minute=at.minute // 5 * 5, second=0)
    bar = (slot - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    direction = FnoDirection.SHORT if short else FnoDirection.LONG
    sign = -1 if short else 1
    signal = MomSignal(bar_ts=bar, direction=direction, close=forward, atr=26,
                       stop_underlying=forward - sign * 40, target_underlying=forward + sign * 100,
                       strategy=strategy)
    return EntryObservation(signal, chain, "REGIME_1_NORMAL", expiry, False, vol_up, positive)


def marks(at, p, *, premium=None, future=None, quantity=None):
    return VenueMarks(at, future, {
        p.token: (p.entry_premium if premium is None else premium, p.qty if quantity is None else quantity),
    })


def test_same_way_signals_use_nifty_first_and_one_risk_ledger():
    book = SharedControl(250_000)
    out = book.step(Tick(NOW, 100, entries={"SENSEX": observation("SENSEX"), "NIFTY": observation("NIFTY")}))
    first, second = out.entries
    assert (first.venue, first.reason) == ("NIFTY", "accepted")
    assert (second.venue, second.reason) == ("SENSEX", "correlated_exposure_open")
    p = book.positions[first.position_id]
    assert p.qty == 65
    assert first.cash_before_rs == 249_900
    assert second.cash_before_rs == pytest.approx(
        249_900 - p.entry_premium * p.qty - calc_fno_costs(p.entry_premium, 0, p.qty)
    )


def test_same_bar_opposite_directions_and_native_venue_settlement():
    book = SharedControl(250_000)
    out = book.step(Tick(NOW, 0, entries={"SENSEX": observation("SENSEX", short=True),
                                        "NIFTY": observation("NIFTY")}))
    assert [x.reason for x in out.entries] == ["accepted", "accepted"]
    nifty, sensex = book.positions.values()
    assert nifty.qty == 65
    assert sensex.qty == 20
    at = NOW.replace(hour=15, minute=10)
    exit_marks = {p.underlying: marks(at, p, premium=p.entry_premium + 20) for p in (nifty, sensex)}
    out = book.step(Tick(at, 0, marks=exit_marks))
    assert not out.missing_marks and not book.positions
    for exit, p, segment in zip(out.exits, (nifty, sensex), ("NFO", "BFO"), strict=True):
        assert exit.reason == "hard_flat_1510"
        assert exit.fees == calc_fno_costs(p.entry_premium, exit.premium, p.qty, exchange=segment)
        assert exit.net == pytest.approx(20 * p.qty - exit.fees)
    assert book.equity == pytest.approx(250_000 + sum(x.net for x in out.exits))


def test_exits_and_spread_cash_precede_new_entry_and_reentry_is_per_venue():
    book = SharedControl(250_000)
    book.step(Tick(NOW, 0, entries={"NIFTY": observation("NIFTY")}))
    nifty, = book.positions.values()
    at = NOW + timedelta(minutes=5)
    out = book.step(Tick(at, 4000, entries={"NIFTY": observation("NIFTY", at),
                                           "SENSEX": observation("SENSEX", at)},
                         marks={"NIFTY": marks(at, nifty, future=nifty.stop_underlying)}, spread_closes=(750,)))
    exit, = out.exits
    assert exit.reason == "underlying_stop"
    assert [x.reason for x in out.entries] == ["reentry_not_confirmed", "accepted"]
    assert out.entries[1].cash_before_rs == pytest.approx(250_000 + exit.net + 750 - 4000)


def test_expiry_is_venue_specific_and_dedup_preserves_retry_after_rejection():
    book = SharedControl(250_000)
    out = book.step(Tick(NOW, 0, entries={"NIFTY": observation("NIFTY", expiry=True),
                                        "SENSEX": observation("SENSEX", short=True)}))
    assert [x.reason for x in out.entries] == ["expiry_day_block", "accepted"]
    at = NOW + timedelta(seconds=10)
    out = book.step(Tick(at, 0, entries={"NIFTY": observation("NIFTY", at),
                                       "SENSEX": observation("SENSEX", at, short=True)}))
    assert [x.reason for x in out.entries] == ["accepted", "bar_already_entered"]


def test_shared_spread_losses_halt_both_venues_and_reserve_is_not_cash():
    book = SharedControl(250_000)
    entries = {venue: observation(venue) for venue in ("NIFTY", "SENSEX")}
    out = book.step(Tick(NOW, 249_000, entries=entries))
    assert [x.reason for x in out.entries] == ["shared_worst_case_cash_exhausted"] * 2
    assert book.equity == 250_000
    at = NOW + timedelta(seconds=10)
    out = book.step(Tick(at, 0, entries=entries, spread_closes=(-8_000,)))
    assert [x.reason for x in out.entries] == ["kill_switches_clear"] * 2
    assert book.equity == 242_000


def test_wrong_venue_and_insufficient_depth_leave_held_risk_unresolved():
    book = SharedControl(250_000)
    book.step(Tick(NOW, 0, entries={"NIFTY": observation("NIFTY")}))
    p, = book.positions.values()
    at = NOW.replace(hour=15, minute=10)
    out = book.step(Tick(at, 0, marks={"SENSEX": marks(at, p, premium=1)}))
    assert not out.exits
    assert out.missing_marks == (p.id,)
    at += timedelta(seconds=10)
    out = book.step(Tick(at, 0, marks={"NIFTY": marks(at, p, quantity=p.qty - 1)}))
    assert not out.exits
    assert out.missing_marks == (p.id,)
    assert book.equity == 250_000 and p.id in book.positions


def test_bid_only_ticks_can_arm_and_confirm_profit_lock():
    book = SharedControl(250_000)
    book.step(Tick(NOW, 0, entries={"NIFTY": observation("NIFTY", strategy="N11_OR20")}))
    p, = book.positions.values()
    at = NOW + timedelta(seconds=10)
    peak = p.entry_premium * 1.5
    book.step(Tick(at, 0, marks={"NIFTY": marks(at, p, premium=peak)}))
    assert p.best_premium == peak
    at += timedelta(seconds=10)
    below = p.entry_premium * 1.05
    out = book.step(Tick(at, 0, marks={"NIFTY": marks(at, p, premium=below)}))
    assert not out.exits
    at += timedelta(seconds=max(10, settings.FNO_PROFIT_LOCK_CONFIRM_SEC))
    out = book.step(Tick(at, 0, marks={"NIFTY": marks(at, p, premium=below)}))
    assert [x.reason for x in out.exits] == ["profit_lock"]


def test_future_chain_and_reused_management_receipt_cannot_mutate_ledger():
    book = SharedControl(250_000)
    with pytest.raises(ValueError, match="chain must be known"):
        book.step(Tick(NOW, 0, entries={"NIFTY": observation("NIFTY", NOW + timedelta(seconds=1))},
                       spread_closes=(500,)))
    assert book.equity == 250_000
    book.step(Tick(NOW, 0, entries={"NIFTY": observation("NIFTY")}))
    p, = book.positions.values()
    with pytest.raises(ValueError, match="management mark must be new"):
        book.step(Tick(NOW + timedelta(seconds=10), 0, marks={"NIFTY": marks(NOW, p)}))
    assert p.id in book.positions


def test_native_two_lot_reservation_falls_back_to_one_when_shared_cash_is_short(monkeypatch):
    monkeypatch.setattr(settings, "FNO_MAX_LOSS_PER_TRADE", 5000)
    entry = observation("NIFTY", vol_up=True, positive=True)
    ample = SharedControl(250_000)
    decision, = ample.step(Tick(NOW, 0, entries={"NIFTY": entry})).entries
    assert decision.reason == "accepted" and decision.tolerance_reason
    p = ample.positions[decision.position_id]
    assert p.lots == 2
    constrained = SharedControl(250_000)
    reserve = 250_000 - p.entry_premium * p.lot_size - 100
    decision, = constrained.step(Tick(NOW, reserve, entries={"NIFTY": entry})).entries
    assert decision.reason == "accepted" and not decision.tolerance_reason
    assert constrained.positions[decision.position_id].lots == 1



def test_tolerance_does_not_apply_to_sensex_and_thin_ask_does_not_downsize_nifty(monkeypatch):
    monkeypatch.setattr(settings, "FNO_MAX_LOSS_PER_TRADE", 5000)
    sx = SharedControl(250_000)
    decision, = sx.step(Tick(NOW, 0, entries={
        "SENSEX": observation("SENSEX", vol_up=True, positive=True),
    })).entries
    assert decision.reason == "accepted" and not decision.tolerance_reason
    assert sx.positions[decision.position_id].lots == 1

    entry = observation("NIFTY", vol_up=True, positive=True)
    one_lot = {strike: replace(quote, ask_quantity=65) for strike, quote in entry.chain.quotes.items()}
    entry = replace(entry, chain=replace(entry.chain, quotes=one_lot))
    nx = SharedControl(250_000)
    decision, = nx.step(Tick(NOW, 0, entries={"NIFTY": entry})).entries
    assert decision.reason == "entry_depth_unavailable"
    assert not nx.positions and nx.equity == 250_000


def test_eff_soft_clock_uses_sensex_future_and_keeps_the_other_position_open():
    book = SharedControl(250_000)
    book.step(Tick(NOW, 0, entries={"NIFTY": observation("NIFTY"),
                                    "SENSEX": observation("SENSEX", short=True)}))
    nifty, sensex = book.positions.values()
    at = NOW + timedelta(minutes=30)
    out = book.step(Tick(at, 0, marks={
        "NIFTY": marks(at, nifty, premium=nifty.entry_premium + 5, future=nifty.entry_underlying + 30),
        "SENSEX": marks(at, sensex, premium=sensex.entry_premium - 5, future=sensex.entry_underlying),
    }))
    closed, = out.exits
    assert (closed.venue, closed.reason) == ("SENSEX", "time_stop")
    assert set(book.positions) == {nifty.id}


def test_a_quote_gap_does_not_confirm_a_profit_lock():
    book = SharedControl(250_000)
    book.step(Tick(NOW, 0, entries={"NIFTY": observation("NIFTY", strategy="N11_OR20")}))
    p, = book.positions.values()
    at = NOW + timedelta(seconds=10)
    book.step(Tick(at, 0, marks={"NIFTY": marks(at, p, premium=p.entry_premium * 1.5)}))
    at += timedelta(seconds=10)
    below = p.entry_premium * 1.05
    assert not book.step(Tick(at, 0, marks={"NIFTY": marks(at, p, premium=below)})).exits
    at += timedelta(seconds=10)
    assert book.step(Tick(at, 0)).missing_marks == (p.id,)
    at += timedelta(seconds=10)
    out = book.step(Tick(at, 0, marks={"NIFTY": marks(at, p, premium=below)}))
    assert not out.exits and p.id in book.positions


def test_unresolved_position_blocks_transition_to_a_new_session():
    book = SharedControl(250_000)
    book.step(Tick(NOW, 0, entries={"NIFTY": observation("NIFTY")}))
    with pytest.raises(ValueError, match="previous session still has unresolved positions"):
        book.step(Tick(NOW + timedelta(days=1), 0, spread_closes=(10,)))
    assert book.equity == 250_000 and len(book.positions) == 1



def earned_book(monkeypatch):
    monkeypatch.setattr(settings, 'FNO_MAX_RISK_PCT', 0.04)
    monkeypatch.setattr(settings, 'FNO_MAX_LOSS_PER_TRADE', 9000)
    monkeypatch.setattr(settings, "FNO_MAX_OPEN_PREMIUM_PCT", 0.25)
    book = SharedControl(250_000)
    admitted, = book.step(Tick(NOW, 0, entries={
        "SENSEX": observation("SENSEX", vol_up=True),
    })).entries
    assert admitted.reason == "accepted"
    parent = book.positions[admitted.position_id]
    assert parent.lots == 2 and parent.qty == 40
    return book, parent


def add_stage(at, parent, *, reserve=0, ask_quantity=20, received_at=None):
    return EarnedStage(reserve, {
        (parent.underlying, parent.token): EarnedQuote(
            received_at or at, parent.entry_premium + 49, parent.entry_premium + 50, ask_quantity,
        ),
    })


def favorable_mark(at, parent, *, progress=60, quantity=None):
    return marks(at, parent, premium=parent.entry_premium + 49,
                 future=parent.entry_underlying + progress, quantity=quantity)


def test_earned_add_uses_old_spread_reserve_then_regular_entry_sees_the_new_cash(monkeypatch):
    book, parent = earned_book(monkeypatch)
    at = NOW + timedelta(minutes=5)
    tick = Tick(at, 0, marks={"SENSEX": favorable_mark(at, parent)},
                earned=add_stage(at, parent, reserve=235_000),
                spread_closes=(400,), entries={"NIFTY": observation("NIFTY", at, short=True)})
    out = book.step(tick)
    assert [x.reason for x in out.earned] == ["shared_worst_case_cash_exhausted"]
    assert out.earned[0].cash_before_rs == 0
    assert out.entries[0].reason == "accepted"
    assert book.equity == 250_400


def test_earned_cash_and_premium_count_while_trade_slots_exclude_the_child(monkeypatch):
    monkeypatch.setattr(settings, "FNO_MAX_TRADES_PER_DAY", 2)
    book, parent = earned_book(monkeypatch)
    at = NOW + timedelta(minutes=5)
    out = book.step(Tick(at, 0, marks={"SENSEX": favorable_mark(at, parent)},
                         earned=add_stage(at, parent),
                         entries={"NIFTY": observation("NIFTY", at, short=True)}))
    added, = out.earned
    assert added.reason == "accepted"
    child = book.positions[added.position_id]
    assert child.strategy == "N11_ADD" and child.qty == 20
    assert child.token == parent.token and child.stop_underlying == parent.entry_underlying
    assert out.entries[0].reason == "accepted"
    assert len(book.positions) == 3
    assert added.cash_before_rs - out.entries[0].cash_before_rs == pytest.approx(
        child.entry_premium * child.qty + calc_fno_costs(child.entry_premium, 0, child.qty, exchange="BFO")
    )


def test_child_closes_with_parent_and_shared_depth_cannot_be_reused(monkeypatch):
    book, parent = earned_book(monkeypatch)
    at = NOW + timedelta(minutes=5)
    out = book.step(Tick(at, 0, marks={"SENSEX": favorable_mark(at, parent)},
                         earned=add_stage(at, parent)))
    child = book.positions[out.earned[0].position_id]
    at += timedelta(seconds=10)
    out = book.step(Tick(at, 0, marks={"SENSEX": favorable_mark(at, parent, progress=120, quantity=60)},
                         earned=add_stage(at, parent)))
    assert parent.trail_active and not out.earned
    at += timedelta(seconds=10)
    out = book.step(Tick(at, 0, marks={"SENSEX": favorable_mark(at, parent, progress=40, quantity=40)}))
    assert [(x.position_id, x.reason) for x in out.exits] == [(parent.id, "trail_stop")]
    assert out.missing_marks == (child.id,)
    at += timedelta(seconds=10)
    out = book.step(Tick(at, 0, marks={"SENSEX": favorable_mark(at, parent, progress=40, quantity=20)}))
    closed, = out.exits
    assert (closed.position_id, closed.reason) == (child.id, "n11_with_first")
    assert closed.fees == calc_fno_costs(child.entry_premium, closed.premium, 20, exchange="BFO")
    assert book.closes[-1].pnl == closed.net and not book.closes[-1].single_leg


def test_missing_late_or_shallow_earned_quote_never_becomes_an_add(monkeypatch):
    book, parent = earned_book(monkeypatch)
    at = NOW + timedelta(minutes=5)
    source = {"SENSEX": favorable_mark(at, parent)}
    with pytest.raises(ValueError, match="earned quote must follow"):
        book.step(Tick(at, 0, marks=source, earned=add_stage(at, parent, received_at=at + timedelta(seconds=1))))
    out = book.step(Tick(at, 0, marks=source))
    assert [x.reason for x in out.earned] == ["earned_stage_unavailable"]
    at += timedelta(seconds=10)
    out = book.step(Tick(at, 0, marks={"SENSEX": favorable_mark(at, parent)},
                         earned=EarnedStage(0)))
    assert [x.reason for x in out.earned] == ["earned_quote_unavailable"]
    at += timedelta(seconds=10)
    out = book.step(Tick(at, 0, marks={"SENSEX": favorable_mark(at, parent)},
                         earned=add_stage(at, parent, ask_quantity=19)))
    assert [x.reason for x in out.earned] == ["earned_ask_depth_unavailable"]
    assert set(book.positions) == {parent.id} and book.equity == 250_000


def test_closed_child_is_never_added_again_while_its_parent_is_open(monkeypatch):
    book, parent = earned_book(monkeypatch)
    at = NOW + timedelta(minutes=5)
    out = book.step(Tick(at, 0, marks={"SENSEX": favorable_mark(at, parent)},
                         earned=add_stage(at, parent)))
    child_id = out.earned[0].position_id
    at += timedelta(seconds=10)
    out = book.step(Tick(at, 0, marks={"SENSEX": favorable_mark(at, parent, progress=-1, quantity=60)}))
    assert [(x.position_id, x.reason) for x in out.exits] == [(child_id, "underlying_stop")]
    assert book.closes[-1].pnl < 0 and not book.closes[-1].single_leg
    at += timedelta(seconds=10)
    out = book.step(Tick(at, 0, marks={"SENSEX": favorable_mark(at, parent, quantity=39)},
                         earned=add_stage(at, parent)))
    assert out.missing_marks == (parent.id,) and not out.earned
    at += timedelta(seconds=10)
    out = book.step(Tick(at, 0, marks={"SENSEX": favorable_mark(at, parent)},
                         earned=add_stage(at, parent)))
    assert not out.earned and set(book.positions) == {parent.id}



def test_causal_gate_does_not_see_same_time_closes_or_later_volatility():
    start = NOW.replace(hour=9, minute=15)
    old = ShadowClose(1, NOW - timedelta(minutes=10), -100)
    exact = ShadowClose(2, NOW, 200)
    tape = GateTape(start, NOW + timedelta(minutes=20),
                    [VolatilityReading(NOW + timedelta(seconds=10), 1.0, 1.0)],
                    [exact, old], need=1, stand_ratio=.9)
    state = tape.at(NOW)
    assert state.stand_aside and not state.vol_up and state.paper_count == 1
    later = tape.at(NOW + timedelta(seconds=10))
    assert not later.stand_aside and later.vol_up and later.paper_positive
    assert later.paper_count == 2 and later.paper_sum == 200


def test_gate_orders_equal_close_clocks_by_native_id_and_refuses_an_uncovered_day():
    close_at = NOW - timedelta(minutes=10)
    tape = GateTape(NOW.replace(hour=9), NOW + timedelta(days=2),
                    [VolatilityReading(close_at, .8, 1.0)],
                    [ShadowClose(3, close_at, -100), ShadowClose(2, close_at, 200)],
                    need=1, stand_ratio=.9)
    assert tape.at(NOW).paper_sum == -100
    assert tape.at(NOW).stand_aside
    assert tape.at(NOW + timedelta(days=1)) is None


def test_same_point_in_time_gate_controls_both_venues(monkeypatch):
    monkeypatch.setattr(settings, "FNO_MAX_LOSS_PER_TRADE", 5000)
    opens = NOW + timedelta(seconds=10)
    tape = GateTape(NOW.replace(hour=9), NOW + timedelta(minutes=1),
                    [VolatilityReading(opens, 1.0, 1.0)],
                    [ShadowClose(1, NOW - timedelta(minutes=1), -100),
                     ShadowClose(2, NOW, 200)], need=1, stand_ratio=.9)
    book = SharedControl(250_000, gate_tape=tape)
    out = book.step(Tick(NOW, 0, entries={"NIFTY": observation("NIFTY"), "SENSEX": observation("SENSEX")}))
    assert [x.reason for x in out.entries] == ["n11:stand_aside"] * 2
    out = book.step(Tick(opens, 0, entries={"NIFTY": observation("NIFTY", opens)}))
    assert out.entries[0].reason == "accepted" and out.entries[0].tolerance_reason
    assert book.positions[out.entries[0].position_id].lots == 2


def test_uncovered_entry_gate_keeps_existing_exit_management_running():
    tape = GateTape(NOW.replace(hour=9), NOW, [VolatilityReading(NOW, .8, 1.0)],
                    [], need=20, stand_ratio=.9)
    book = SharedControl(250_000, gate_tape=tape)
    book.step(Tick(NOW, 0, entries={"NIFTY": observation("NIFTY")}))
    p, = book.positions.values()
    later = NOW + timedelta(minutes=5)
    result = book.step(Tick(later, 0, marks={"NIFTY": marks(later, p, future=p.stop_underlying)},
                            entries={"SENSEX": observation("SENSEX", later)}))
    assert result.exits[0].reason == "underlying_stop"
    assert result.entries[0].reason == "n11:gate_evidence_unavailable"
    assert not book.positions
