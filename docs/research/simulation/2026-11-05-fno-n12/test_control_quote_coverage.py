from collections import Counter
from dataclasses import replace
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import control_quote_coverage as coverage
from fno_models import Contract, ContractQuote


def test_freshness_and_two_lot_depth_use_the_actual_trade_clock():
    at = datetime(2026, 10, 28, 9, 45, 25, tzinfo=coverage.IST)
    contract = Contract(1, "SENSEXTEST", "SENSEX", date(2026, 10, 29), 80000, "CE", 20)
    quote = ContractQuote(contract, bid=100.0, ask=101.0, oi=5000, volume=1000,
                          last_trade_time=at - timedelta(seconds=120), bid_quantity=40, ask_quantity=40)
    assert coverage.entry_liquidity(quote, at) is None
    assert coverage.entry_liquidity(replace(quote, bid_quantity=39), at) == "top_level_depth"
    assert coverage.entry_liquidity(replace(quote, oi=4999), at) == "open_interest_or_volume"
    assert coverage.entry_liquidity(replace(quote, last_trade_time=at + timedelta(seconds=1)), at) == "last_trade_age"
    assert coverage.entry_liquidity(quote, at + timedelta(seconds=1)) == "last_trade_age"


def test_joint_clocks_need_same_minute_and_ten_second_receipt_skew(monkeypatch):
    day = "2026-10-28"
    at = datetime(2026, 10, 28, 9, 45, 25, tzinfo=coverage.IST)
    master = {name: {"option_expiry": "2026-10-29", "front_expiry": "2026-10-29",
                     "manifest_sha256": name} for name in coverage.VENUES}
    monkeypatch.setattr(coverage, "batch_state", lambda _name, _at, _m, quotes: quotes)
    good = (None, True, (1, 2), ())
    subset = (None, False, (1, 2), ())
    flat = (None, True, (), (2, 3))
    batches = {
        ("NIFTY", at): good, ("SENSEX", at + timedelta(seconds=10)): subset,
        ("NIFTY", at + timedelta(minutes=5)): good,
        ("SENSEX", at + timedelta(minutes=5, seconds=11)): good,
        ("NIFTY", at.replace(hour=15, minute=10)): flat,
    }
    result = coverage.one_day(day, master, batches, Counter())
    assert result["joint_sampled_clocks"] == [585]
    assert result["joint_full_ladder_clocks"] == []
    assert result["venues"]["NIFTY"]["selected_tokens_with_flat_bid"] == 1


def test_zero_raw_depth_normalizes_to_unavailable(monkeypatch):
    contract = Contract(1, "SENSEXTEST", "SENSEX", date(2026, 10, 29), 80000, "CE", 20)
    monkeypatch.setattr(coverage, "verify_archive_event",
                        lambda *_args, **_kwargs: (SimpleNamespace(bid=None, ask=100, ltp=99), None))
    event = {"raw_packet": {"depth": {"buy": [{"quantity": 0}], "sell": [{"quantity": 40}]}},
             "oi": 0, "volume": 0, "last_trade_time": None,
             "buy_depth": [{"quantity": None}], "sell_depth": [{"quantity": 40}]}
    quote = coverage.quote_from_raw(event, contract)
    assert quote.bid_quantity == 0
    assert quote.ask_quantity == 40
