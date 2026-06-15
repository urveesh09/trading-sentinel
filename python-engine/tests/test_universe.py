"""Tests for the static Nifty 100 universe loader."""
import json
import pytest

from universe import Universe, UniverseError


@pytest.fixture
def fake_kite_cache():
    """Mock instrument_cache with 100 valid + 1 missing symbol."""
    cache = {f"SYM{i:03d}": 100000 + i for i in range(100)}
    cache["SYM042"] = None  # Simulate one unresolvable symbol
    return cache


def test_universe_loads_all_100_tickers(fake_kite_cache, tmp_path):
    """Universe should resolve 99 of 100 tokens (1 missing excluded, not raised)."""
    data_file = tmp_path / "nifty100.json"
    data_file.write_text(json.dumps({
        "as_of_date": "2026-06-14",
        "tickers": [{"symbol": f"SYM{i:03d}", "instrument_token": None} for i in range(100)]
    }))

    u = Universe(str(data_file), instrument_cache=fake_kite_cache)
    tokens = u.get_nifty100_tokens()

    assert len(tokens) == 99, f"Expected 99 (1 missing), got {len(tokens)}"


def test_universe_raises_on_missing_file(tmp_path):
    """Universe should fail-fast if JSON file is missing."""
    with pytest.raises(UniverseError, match="not found"):
        Universe(str(tmp_path / "does_not_exist.json"))


def test_universe_raises_on_malformed_json(tmp_path):
    """Universe should fail-fast if JSON is malformed."""
    data_file = tmp_path / "bad.json"
    data_file.write_text("not valid json {[}")

    with pytest.raises(UniverseError, match="malformed"):
        Universe(str(data_file))


def test_universe_raises_on_missing_tickers_key(tmp_path):
    """Universe should fail-fast if 'tickers' key is missing."""
    data_file = tmp_path / "no_tickers.json"
    data_file.write_text(json.dumps({"as_of_date": "2026-06-14"}))

    with pytest.raises(UniverseError, match="tickers"):
        Universe(str(data_file))


def test_universe_caches_tokens_on_second_call(fake_kite_cache, tmp_path):
    """Universe should return same tokens on repeat calls (in-memory cache)."""
    data_file = tmp_path / "nifty100.json"
    data_file.write_text(json.dumps({
        "as_of_date": "2026-06-14",
        "tickers": [{"symbol": f"SYM{i:03d}", "instrument_token": None} for i in range(100)]
    }))

    u = Universe(str(data_file), instrument_cache=fake_kite_cache)
    tokens1 = u.get_nifty100_tokens()
    tokens2 = u.get_nifty100_tokens()
    assert tokens1 == tokens2
    assert tokens1 is not tokens2  # returns a copy, not the internal set


def test_universe_token_to_symbol_roundtrip(fake_kite_cache, tmp_path):
    """token_to_symbol should map a resolved token back to its NSE symbol.

    Added for Task 7: the breadth wiring needs to convert token → symbol
    when calling kite.get_historical (which is keyed by symbol).
    """
    data_file = tmp_path / "nifty100.json"
    data_file.write_text(json.dumps({
        "as_of_date": "2026-06-14",
        "tickers": [{"symbol": f"SYM{i:03d}", "instrument_token": None} for i in range(100)]
    }))

    u = Universe(str(data_file), instrument_cache=fake_kite_cache)
    # Token 100042 is the missing one (set to None) — should NOT be in the map
    assert u.token_to_symbol(100042) is None
    # Tokens 0..98 and 43..99 should round-trip
    assert u.token_to_symbol(100000) == "SYM000"
    assert u.token_to_symbol(100041) == "SYM041"  # adjacent to missing, must still work
    assert u.token_to_symbol(100043) == "SYM043"
    # An unknown token returns None (not KeyError)
    assert u.token_to_symbol(999999) is None
