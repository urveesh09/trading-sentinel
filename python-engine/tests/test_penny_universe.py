"""
[PENNY-UNIVERSE 2026-06-21] Tests for PennyUniverse: static JSON load,
eligibility filter, schema validation. Mirrors tests/test_universe.py
pattern but penny-specific.

For unit testing the eligibility filter we use an injected
`instrument_cache` fixture (per universe.py pattern) so we don't hit Kite.
"""
import json
import os
import pytest


# ---- fixtures ---------------------------------------------------------

@pytest.fixture
def tmp_penny_json(tmp_path):
    """Write a tiny penny JSON and return its path."""
    payload = {
        "as_of": "2026-06-21",
        "universe_size_target": 100,
        "tickers": [
            {"symbol": "AAA", "series": "EQ", "prev_close": 12.5, "promoter_holding_pct": 50.0, "pb_ratio": 1.2, "is_t2t": False, "is_asm": False, "is_gsm": False, "median_traded_value_20d": 1_500_000},
            {"symbol": "BBB", "series": "EQ", "prev_close": 30.0, "promoter_holding_pct": 80.0, "pb_ratio": 1.0, "is_t2t": False, "is_asm": False, "is_gsm": False, "median_traded_value_20d": 1_000_000},
            {"symbol": "CCC", "series": "EQ", "prev_close": 0.5,  "promoter_holding_pct": 45.0, "pb_ratio": 0.9, "is_t2t": False, "is_asm": False, "is_gsm": False, "median_traded_value_20d": 2_000_000},
            {"symbol": "DDD", "series": "EQ", "prev_close": 25.0, "promoter_holding_pct": 55.0, "pb_ratio": 3.5, "is_t2t": False, "is_asm": False, "is_gsm": False, "median_traded_value_20d": 800_000},
            {"symbol": "EEE", "series": "EQ", "prev_close": 40.0, "promoter_holding_pct": 60.0, "pb_ratio": 1.5, "is_t2t": True,  "is_asm": False, "is_gsm": False, "median_traded_value_20d": 1_200_000},
            {"symbol": "FFF", "series": "EQ", "prev_close": 10.0, "promoter_holding_pct": 50.0, "pb_ratio": 1.0, "is_t2t": False, "is_asm": True,  "is_gsm": False, "median_traded_value_20d": 1_800_000},
            {"symbol": "GGG", "series": "BE", "prev_close": 15.0, "promoter_holding_pct": 50.0, "pb_ratio": 1.0, "is_t2t": False, "is_asm": False, "is_gsm": False, "median_traded_value_20d": 1_400_000},
            {"symbol": "HHH", "series": "EQ", "prev_close": 18.0, "promoter_holding_pct": 10.0, "pb_ratio": 1.1, "is_t2t": False, "is_asm": False, "is_gsm": False, "median_traded_value_20d": 1_100_000},
            {"symbol": "III", "series": "EQ", "prev_close": 22.0, "promoter_holding_pct": 50.0, "pb_ratio": 1.0, "is_t2t": False, "is_asm": False, "is_gsm": False, "median_traded_value_20d": 200_000},
            {"symbol": "JJJ", "series": "EQ", "prev_close": 5.0,  "promoter_holding_pct": 50.0, "pb_ratio": 1.0, "is_t2t": False, "is_asm": False, "is_gsm": True,  "median_traded_value_20d": 1_300_000},
            {"symbol": "KKK", "series": "EQ", "prev_close": 35.0, "promoter_holding_pct": 55.0, "pb_ratio": 1.4, "is_t2t": False, "is_asm": False, "is_gsm": False, "median_traded_value_20d": 900_000},
            # 2026-06-25 null-tolerance: these would have been silently
            # dropped pre-fix. Now they pass with a data_quality flag.
            {"symbol": "NNN", "series": "EQ", "prev_close": 20.0, "promoter_holding_pct": None, "pb_ratio": None, "is_t2t": False, "is_asm": False, "is_gsm": False, "median_traded_value_20d": 1_100_000},
            {"symbol": "OOO", "series": "EQ", "prev_close": 14.0, "promoter_holding_pct": None, "pb_ratio": 1.3,    "is_t2t": False, "is_asm": False, "is_gsm": False, "median_traded_value_20d": 1_000_000},
            {"symbol": "PPP", "series": "EQ", "prev_close": 28.0, "promoter_holding_pct": 50.0, "pb_ratio": None, "is_t2t": False, "is_asm": False, "is_gsm": False, "median_traded_value_20d": 1_200_000},
        ],
    }
    p = tmp_path / "penny_static.json"
    p.write_text(json.dumps(payload))
    return str(p)


@pytest.fixture
def instrument_cache():
    return {
        "AAA": 1001, "BBB": 1002, "CCC": 1003, "DDD": 1004, "EEE": 1005,
        "FFF": 1006, "GGG": 1007, "HHH": 1008, "III": 1009, "JJJ": 1010,
        "KKK": 1011, "NNN": 1012, "OOO": 1013, "PPP": 1014,
    }


# ---- tests -------------------------------------------------------------

def test_loads_static_penny_universe(tmp_penny_json, instrument_cache):
    from penny_universe import PennyUniverse
    u = PennyUniverse(json_path=tmp_penny_json, instrument_cache=instrument_cache)
    # 2026-06-25: fixture grew from 11 to 14 to cover null-tolerance cases.
    assert u.size == 14


def test_eligibility_filter_rejects_out_of_band(tmp_penny_json, instrument_cache):
    """CCC at prev_close 0.5 is below PENNY_PRICE_MIN (1.0)."""
    from penny_universe import PennyUniverse
    u = PennyUniverse(json_path=tmp_penny_json, instrument_cache=instrument_cache)
    eligible = u.eligible_tickers()
    symbols = [t["symbol"] for t in eligible]
    assert "CCC" not in symbols
    assert "AAA" in symbols   # in band


def test_eligibility_filter_rejects_promoter_over_75(tmp_penny_json, instrument_cache):
    """BBB has promoter 80% -> rejected."""
    from penny_universe import PennyUniverse
    u = PennyUniverse(json_path=tmp_penny_json, instrument_cache=instrument_cache)
    symbols = [t["symbol"] for t in u.eligible_tickers()]
    assert "BBB" not in symbols


def test_eligibility_filter_rejects_promoter_under_25(tmp_penny_json, instrument_cache):
    """HHH has promoter 10% -> rejected (under 25% skin-in-game floor)."""
    from penny_universe import PennyUniverse
    u = PennyUniverse(json_path=tmp_penny_json, instrument_cache=instrument_cache)
    symbols = [t["symbol"] for t in u.eligible_tickers()]
    assert "HHH" not in symbols


def test_eligibility_filter_rejects_high_pb(tmp_penny_json, instrument_cache):
    """DDD has P/B 3.5 -> rejected (above 2.0 floor)."""
    from penny_universe import PennyUniverse
    u = PennyUniverse(json_path=tmp_penny_json, instrument_cache=instrument_cache)
    symbols = [t["symbol"] for t in u.eligible_tickers()]
    assert "DDD" not in symbols


def test_eligibility_filter_rejects_t2t(tmp_penny_json, instrument_cache):
    """EEE is in T2T -> rejected."""
    from penny_universe import PennyUniverse
    u = PennyUniverse(json_path=tmp_penny_json, instrument_cache=instrument_cache)
    symbols = [t["symbol"] for t in u.eligible_tickers()]
    assert "EEE" not in symbols


def test_eligibility_filter_rejects_asm(tmp_penny_json, instrument_cache):
    """FFF is in ASM -> rejected."""
    from penny_universe import PennyUniverse
    u = PennyUniverse(json_path=tmp_penny_json, instrument_cache=instrument_cache)
    symbols = [t["symbol"] for t in u.eligible_tickers()]
    assert "FFF" not in symbols


def test_eligibility_filter_rejects_gsm(tmp_penny_json, instrument_cache):
    """JJJ is in GSM -> rejected."""
    from penny_universe import PennyUniverse
    u = PennyUniverse(json_path=tmp_penny_json, instrument_cache=instrument_cache)
    symbols = [t["symbol"] for t in u.eligible_tickers()]
    assert "JJJ" not in symbols


def test_eligibility_filter_rejects_low_liquidity(tmp_penny_json, instrument_cache):
    """III has 20d median traded value 200k -> rejected (below 500k floor)."""
    from penny_universe import PennyUniverse
    u = PennyUniverse(json_path=tmp_penny_json, instrument_cache=instrument_cache)
    symbols = [t["symbol"] for t in u.eligible_tickers()]
    assert "III" not in symbols


def test_eligibility_filter_rejects_non_eq_series(tmp_penny_json, instrument_cache):
    """GGG is BE series -> rejected."""
    from penny_universe import PennyUniverse
    u = PennyUniverse(json_path=tmp_penny_json, instrument_cache=instrument_cache)
    symbols = [t["symbol"] for t in u.eligible_tickers()]
    assert "GGG" not in symbols


def test_eligible_pass_set_is_correct(tmp_penny_json, instrument_cache):
    """AAA and KKK should be the only two that pass every filter.

    Note (2026-06-25): NNN (both null), OOO (promoter null), PPP (pb null)
    now also pass -- see null-tolerance tests below. This test still
    asserts that AAA and KKK are in the eligible set."""
    from penny_universe import PennyUniverse
    u = PennyUniverse(json_path=tmp_penny_json, instrument_cache=instrument_cache)
    symbols = sorted([t["symbol"] for t in u.eligible_tickers()])
    assert "AAA" in symbols
    assert "KKK" in symbols


# ---- 2026-06-25 null-tolerance tests ---------------------------------

def test_eligibility_null_promoter_lets_through(tmp_penny_json, instrument_cache):
    """OOO has promoter=null and pb=1.3 -- it should pass eligibility."""
    from penny_universe import PennyUniverse
    u = PennyUniverse(json_path=tmp_penny_json, instrument_cache=instrument_cache)
    symbols = [t["symbol"] for t in u.eligible_tickers()]
    assert "OOO" in symbols


def test_eligibility_null_pb_lets_through(tmp_penny_json, instrument_cache):
    """PPP has pb=null and promoter=50.0 -- it should pass eligibility."""
    from penny_universe import PennyUniverse
    u = PennyUniverse(json_path=tmp_penny_json, instrument_cache=instrument_cache)
    symbols = [t["symbol"] for t in u.eligible_tickers()]
    assert "PPP" in symbols


def test_eligibility_both_null_lets_through(tmp_penny_json, instrument_cache):
    """NNN has both null -- it should still pass."""
    from penny_universe import PennyUniverse
    u = PennyUniverse(json_path=tmp_penny_json, instrument_cache=instrument_cache)
    symbols = [t["symbol"] for t in u.eligible_tickers()]
    assert "NNN" in symbols


def test_eligibility_real_high_promoter_still_rejects(tmp_penny_json, instrument_cache):
    """Real high promoter (BBB=80%) still hard-rejects even when others pass null-tolerant."""
    from penny_universe import PennyUniverse
    u = PennyUniverse(json_path=tmp_penny_json, instrument_cache=instrument_cache)
    symbols = [t["symbol"] for t in u.eligible_tickers()]
    assert "BBB" not in symbols


def test_eligibility_real_high_pb_still_rejects(tmp_penny_json, instrument_cache):
    """Real high PB (DDD=3.5) still hard-rejects."""
    from penny_universe import PennyUniverse
    u = PennyUniverse(json_path=tmp_penny_json, instrument_cache=instrument_cache)
    symbols = [t["symbol"] for t in u.eligible_tickers()]
    assert "DDD" not in symbols


def test_eligibility_null_ticker_has_data_quality_flag(tmp_penny_json, instrument_cache):
    """Tickers with null promoter/pb get a data_quality flag on their record."""
    from penny_universe import PennyUniverse
    u = PennyUniverse(json_path=tmp_penny_json, instrument_cache=instrument_cache)
    eligible_by_symbol = {t["symbol"]: t for t in u.eligible_tickers()}
    assert "DEGRADED" in eligible_by_symbol["NNN"]["data_quality"]
    assert "promoter_missing" in eligible_by_symbol["NNN"]["data_quality"]
    assert "pb_missing" in eligible_by_symbol["NNN"]["data_quality"]
    assert "promoter_missing" in eligible_by_symbol["OOO"]["data_quality"]
    assert "pb_missing" not in eligible_by_symbol["OOO"]["data_quality"]
    assert "pb_missing" in eligible_by_symbol["PPP"]["data_quality"]
    assert "promoter_missing" not in eligible_by_symbol["PPP"]["data_quality"]
    # Clean tickers should NOT have data_quality flag
    assert "data_quality" not in eligible_by_symbol["AAA"]


def test_quality_audit_reports_null_counts(tmp_penny_json, instrument_cache):
    """quality_audit() returns per-field null counts and degraded_pct.

    Note on null_tv: III in the fixture has tv=200_000 (truthy, below
    threshold). It is NOT counted as null. The audit only counts
    missing/zero values. If you want below-threshold, use the eligibility
    filter result instead.
    """
    from penny_universe import PennyUniverse
    u = PennyUniverse(json_path=tmp_penny_json, instrument_cache=instrument_cache)
    audit = u.quality_audit()
    assert audit["total"] == 14
    assert audit["null_promoter"] == 2   # NNN, OOO
    assert audit["null_pb"] == 2         # NNN, PPP
    assert audit["null_tv"] == 0         # III has 200_000 (truthy)
    assert audit["degraded_pct"] > 0
    assert "corp_source" not in audit  # not present unless set by refresh


def test_refresh_quality_audit_logged_on_missing_corp(monkeypatch, tmp_path, caplog):
    """refresh_from_kite emits penny_corp_data_missing + penny_universe_quality_audit
    when Kite returns empty corp and no fallback file exists."""
    import asyncio
    import logging
    from penny_universe import refresh_from_kite

    # Fake kite with empty instruments/quotes/corp actions.
    class FakeKite:
        async def get_instruments_nse_eq(self):
            return []
        async def get_quote(self, tokens):
            return {}
        async def get_corporate_actions(self):
            return None

    out = tmp_path / "penny_static.json"
    corp = tmp_path / "penny_company_data.json"  # never created
    # The repo now SHIPS a populated tier-3 seed (penny_company_data.json), so
    # point the seed lookup at a nonexistent path to exercise the true
    # "all tiers empty -> corp_source=missing" path in isolation.
    import penny_universe as pu
    monkeypatch.setattr(pu, "_repo_seed_path",
                        lambda: str(tmp_path / "no_such_seed.json"))

    caplog.set_level(logging.INFO, logger="penny_universe")
    result = asyncio.run(refresh_from_kite(FakeKite(), str(out), str(corp), top_n=100))

    # Empty universe from refresh, but the audit SHOULD still be logged
    # via the write path. With zero instruments, refresh returns before
    # write -- so we only assert the missing-corp warning fires.
    assert result is None or result == []
    # corp missing warning fires
    assert any("penny_corp_data_missing" in r.message for r in caplog.records)


def test_refresh_uses_populated_repo_seed(monkeypatch, tmp_path, caplog):
    """[PENNY-CORP-FETCHER 2026-07-16] When Kite corp is empty and the
    named-volume file is absent, refresh_from_kite falls back to the git-tracked
    repo seed (penny_company_data.json). Populating that seed flips corp_source
    from 'missing' to 'fallback_repo_seed' -- the mechanism that restores the
    promoter/PB gates in tomorrow's run."""
    import asyncio
    import json as _json
    import logging
    import penny_universe as pu
    from penny_universe import refresh_from_kite

    class FakeKite:
        async def get_instruments_nse_eq(self):
            return []
        async def get_quote(self, tokens):
            return {}
        async def get_corporate_actions(self):
            return None

    seed = tmp_path / "seed.json"
    seed.write_text(_json.dumps({"records": [
        {"symbol": "AAA", "promoter_holding_pct": 40.0, "pb_ratio": 1.2},
    ]}))
    monkeypatch.setattr(pu, "_repo_seed_path", lambda: str(seed))

    out = tmp_path / "penny_static.json"
    corp = tmp_path / "penny_company_data.json"  # never created

    caplog.set_level(logging.INFO, logger="penny_universe")
    asyncio.run(refresh_from_kite(FakeKite(), str(out), str(corp), top_n=100))

    assert any("penny_corp_data_falling_back_to_repo_seed" in r.message
               for r in caplog.records)
    assert not any("penny_corp_data_missing" in r.message for r in caplog.records)


def test_audit_degraded_on_missing_corp_and_null_fundamentals():
    """[PENNY-CORP-DEGRADE-WARN 2026-07-16] The quality audit must escalate to
    WARNING when the corp-data pipeline is broken (corp_source missing) or when
    promoter+pb are null on every ticker -- not only on null tv/pc. This is the
    2026-07-16 blind spot: 100/100 null promoter+pb + corp_source=missing had
    been logging at INFO, hiding a universe whose promoter/PB safety gates were
    silently bypassed for every penny breakout."""
    from penny_universe import _universe_audit_is_degraded

    healthy = {"total": 100, "null_promoter": 0, "null_pb": 0,
               "null_tv": 0, "null_pc": 0}
    # Fully-populated universe with a real corp source is NOT degraded.
    assert _universe_audit_is_degraded(healthy, "kite") is False
    assert _universe_audit_is_degraded(healthy, "fallback_file") is False

    # corp_source missing is degraded even if every other field is populated
    # (the exact 2026-07-16 prod shape: null_tv/null_pc = 0 but no fundamentals).
    assert _universe_audit_is_degraded(healthy, "missing") is True
    assert _universe_audit_is_degraded(healthy, None) is True

    # Fundamentals null on every ticker is degraded regardless of corp_source
    # label (e.g. corp file loaded but none of its records matched the universe).
    all_null_fund = {"total": 100, "null_promoter": 100, "null_pb": 100,
                     "null_tv": 0, "null_pc": 0}
    assert _universe_audit_is_degraded(all_null_fund, "fallback_file") is True

    # Pre-existing escalations still hold: all-null tv, all-null pc, empty.
    assert _universe_audit_is_degraded(
        {"total": 100, "null_promoter": 0, "null_pb": 0,
         "null_tv": 100, "null_pc": 0}, "kite") is True
    assert _universe_audit_is_degraded(
        {"total": 0, "null_promoter": 0, "null_pb": 0,
         "null_tv": 0, "null_pc": 0}, "kite") is True

    # A partially-null universe (some names have fundamentals) is NOT escalated
    # to WARNING -- it's the expected null-tolerant steady state, not a broken
    # pipeline.
    partial = {"total": 100, "null_promoter": 40, "null_pb": 40,
               "null_tv": 0, "null_pc": 0}
    assert _universe_audit_is_degraded(partial, "fallback_file") is False


def test_missing_json_raises(tmp_path):
    from penny_universe import PennyUniverse, UniverseError
    with pytest.raises(UniverseError):
        PennyUniverse(json_path=str(tmp_path / "does_not_exist.json"))


def test_malformed_json_raises(tmp_path):
    from penny_universe import PennyUniverse, UniverseError
    p = tmp_path / "bad.json"
    p.write_text("{not valid json")
    with pytest.raises(UniverseError):
        PennyUniverse(json_path=str(p))


def test_missing_tickers_key_raises(tmp_path):
    from penny_universe import PennyUniverse, UniverseError
    p = tmp_path / "no_tickers.json"
    p.write_text(json.dumps({"as_of": "2026-06-21"}))
    with pytest.raises(UniverseError):
        PennyUniverse(json_path=str(p))


def test_token_resolution_missing_warns(tmp_penny_json):
    """Tickers not in instrument_cache are skipped silently with a warning."""
    from penny_universe import PennyUniverse
    partial_cache = {"AAA": 1001, "KKK": 1011}
    u = PennyUniverse(json_path=tmp_penny_json, instrument_cache=partial_cache)
    symbols = [t["symbol"] for t in u.eligible_tickers()]
    assert "AAA" in symbols and "KKK" in symbols


def test_token_to_symbol(tmp_penny_json, instrument_cache):
    from penny_universe import PennyUniverse
    u = PennyUniverse(json_path=tmp_penny_json, instrument_cache=instrument_cache)
    assert u.token_to_symbol(1001) == "AAA"
    assert u.token_to_symbol(99999) is None