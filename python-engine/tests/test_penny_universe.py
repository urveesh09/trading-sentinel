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
        "KKK": 1011,
    }


# ---- tests -------------------------------------------------------------

def test_loads_static_penny_universe(tmp_penny_json, instrument_cache):
    from penny_universe import PennyUniverse
    u = PennyUniverse(json_path=tmp_penny_json, instrument_cache=instrument_cache)
    assert u.size == 11


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
    """AAA and KKK should be the only two that pass every filter."""
    from penny_universe import PennyUniverse
    u = PennyUniverse(json_path=tmp_penny_json, instrument_cache=instrument_cache)
    symbols = sorted([t["symbol"] for t in u.eligible_tickers()])
    assert symbols == ["AAA", "KKK"]


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