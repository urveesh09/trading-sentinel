"""Tests for the new universe-expansion config settings (Task 4)."""


def test_universe_size_default_is_500():
    """UNIVERSE_SIZE defaults to 500 (Nifty 500 expansion)."""
    from config import settings
    assert settings.UNIVERSE_SIZE == 500


def test_universe_tickers_file_default():
    """UNIVERSE_TICKERS_FILE points at nifty500.json by default."""
    from config import settings
    assert settings.UNIVERSE_TICKERS_FILE == "nifty500.json"


def test_universe_min_adv_crore_default():
    """UNIVERSE_MIN_ADV_CRORE defaults to 2.0 (₹2 crore median daily traded value floor)."""
    from config import settings
    assert settings.UNIVERSE_MIN_ADV_CRORE == 2.0


def test_universe_liquidity_lookback_default():
    """UNIVERSE_LIQUIDITY_LOOKBACK_DAYS defaults to 20."""
    from config import settings
    assert settings.UNIVERSE_LIQUIDITY_LOOKBACK_DAYS == 20
