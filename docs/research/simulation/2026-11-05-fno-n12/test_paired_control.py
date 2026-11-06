from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from test_shared_control import NOW, marks, observation
from config import settings
from paired_control import compare
from shared_control import SharedControl, Tick


def scenario():
    native = SharedControl(250_000)
    opening = Tick(NOW, 0, entries={"NIFTY": observation("NIFTY", strategy="N11_OR20")})
    native.step(opening)
    nifty, = native.positions.values()
    sx_at = NOW.replace(minute=15, second=20)
    sx_open = observation("SENSEX", sx_at)
    sensex_reference = SharedControl(250_000)
    sensex_reference.step(Tick(sx_at, 0, entries={"SENSEX": sx_open}))
    sensex, = sensex_reference.positions.values()

    ticks = [opening]
    midway = sx_at - timedelta(seconds=10)
    a_first = sx_at + timedelta(seconds=10)
    a_second = a_first + timedelta(seconds=10)
    gain = nifty.entry_premium * .4
    at = NOW + timedelta(seconds=10)
    while at <= a_second:
        keep = 1.0 if at < midway else .4 if at <= sx_at else .3
        source = {"NIFTY": marks(at, nifty, premium=nifty.entry_premium + keep * gain,
                                 future=nifty.entry_underlying + 10 * (at.minute // 5))}
        if at == a_first:
            source["SENSEX"] = marks(at, sensex, premium=sensex.entry_premium - 30,
                                     future=sensex.stop_underlying)
        ticks.append(Tick(at, 0, marks=source, entries={"SENSEX": sx_open} if at == sx_at else {}))
        at += timedelta(seconds=10)
    hard_flat_hour, hard_flat_minute = divmod(settings.FNO_HARD_FLAT_MIN, 60)
    ticks.append(Tick(NOW.replace(hour=hard_flat_hour, minute=hard_flat_minute, second=0), 0))
    return ticks, (NOW, sx_at), a_first, a_second


def test_distinct_wallets_price_later_exit_and_trace_blocked_sensex():
    ticks, scans, a_first, a_second = scenario()
    paired = compare(ticks, scans)
    assert not paired.gaps
    control, candidate = paired.exits["N11T"], paired.exits["N012-A"]
    assert [(x.venue, x.at, x.reason) for x in control] == [
        ("NIFTY", scans[-1], "profit_lock"), ("SENSEX", a_first, "underlying_stop")
    ]
    assert [(x.venue, x.at, x.reason) for x in candidate] == [("NIFTY", a_second, "profit_lock")]

    standalone = SharedControl(250_000)
    observed = tuple(exited for tick in ticks for exited in standalone.step(tick).exits)
    assert control == observed

    change, = paired.entry_changes
    assert change.at == scans[-1] and change.venue == "SENSEX"
    assert (change.control.reason, change.control.qty) == ("accepted", 20)
    assert change.candidate.reason == "correlated_exposure_open"
    assert change.control.cash_before_rs > change.candidate.cash_before_rs

    delta = Decimal(str(candidate[0].net)) - sum(Decimal(str(item.net)) for item in control)
    assert paired.net_delta == delta
    assert paired.summaries["N11T"]["closed"] == 2
    assert paired.summaries["N012-A"]["closed"] == 1


def test_unavailable_post_control_bid_suppresses_score_even_after_later_close():
    ticks, scans, a_first, a_second = scenario()
    tick = next(item for item in ticks if item.at == a_first)
    i = ticks.index(tick)
    # Keep a same-venue futures observation while withholding the option bid.
    nifty = tick.marks["NIFTY"]
    ticks[i] = replace(tick, marks={**tick.marks, "NIFTY": replace(nifty, bids={})})
    later = next(item for item in ticks if item.at == a_second)
    after = a_second + timedelta(seconds=10)
    ticks.insert(-1, Tick(after, 0, marks={"NIFTY": replace(later.marks["NIFTY"], received_at=after)}))
    paired = compare(ticks, scans)
    assert paired.net_delta is None and paired.summaries is None
    assert [(gap.arm, gap.at, gap.reason) for gap in paired.gaps] == [
        ("N012-A", a_first, "held_bid_missing")
    ]
    assert paired.exits["N012-A"][0].at == after


def test_held_gap_detected_when_missing_tick_never_arrives():
    ticks, scans, a_first, _ = scenario()
    paired = compare((tick for tick in ticks if tick.at != a_first), scans)
    assert paired.net_delta is None
    assert any(gap.arm == "N012-A" and gap.reason == "management_clock_gap" for gap in paired.gaps)


def test_missing_scan_or_horizon_cannot_be_treated_as_flat_session():
    opens = NOW
    later = NOW + timedelta(minutes=5)
    paired = compare((Tick(opens, 0),), (opens, later))
    assert paired.net_delta is None
    assert {gap.reason for gap in paired.gaps} == {"entry_scan_missing", "session_horizon_missing"}
    with pytest.raises(ValueError, match="declared entry scan"):
        compare((Tick(opens, 0, entries={"NIFTY": observation("NIFTY")}),), (later,))


def test_external_spread_cash_is_identified_in_conditional_pair():
    flat_hour, flat_minute = divmod(settings.FNO_HARD_FLAT_MIN, 60)
    end = NOW.replace(hour=flat_hour, minute=flat_minute)
    paired = compare((Tick(NOW, 5000), Tick(end, 0, spread_closes=(1000,))), (NOW,))
    assert not paired.gaps and paired.net_delta == 0
    assert paired.uses_external_spreads
    assert [x["net"] for x in paired.summaries.values()] == [Decimal("1000"), Decimal("1000")]
