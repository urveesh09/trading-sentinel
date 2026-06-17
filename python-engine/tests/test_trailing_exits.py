"""Tests for the trailing-exit enrichment (Regime 1 wider targets + regime-aware Chandelier)."""


def test_target2_r_regime1_default_is_4_5():
    """TARGET2_R_REGIME1 defaults to 4.5 (was 3.0, bumped to let winners run)."""
    from config import settings
    assert settings.TARGET2_R_REGIME1 == 4.5


def test_target2_r_regime2_unchanged():
    """Regime 2 stays at 3.0R -- only Regime 1 widens (calm markets have trends)."""
    from config import settings
    assert settings.TARGET2_R_REGIME2 == 3.0


def test_target2_r_regime3_unchanged():
    """Regime 3 stays at 1.0R (crisis = exit fast)."""
    from config import settings
    assert settings.TARGET2_R_REGIME3 == 1.0


def test_hard_cap_r_regime1_default_is_5_0():
    """HARD_CAP_R_REGIME1 is the absolute ceiling -- never hold past 5R even in trends."""
    from config import settings
    assert settings.HARD_CAP_R_REGIME1 == 5.0


def test_chandelier_atr_regime1_mult_is_3_5():
    """Chandelier widens from 3.0x to 3.5x in Regime 1 (more room for mid-cap trends)."""
    from config import settings
    assert settings.CHANDELIER_ATR_REGIME1_MULT == 3.5


def test_chandelier_atr_regime2_mult_unchanged():
    """Regime 2 Chandelier stays at 3.0x ATR (elevated uncertainty = normal trail)."""
    from config import settings
    assert settings.CHANDELIER_ATR_REGIME2_MULT == 3.0


def test_chandelier_atr_regime3_mult_is_2_5():
    """Regime 3 Chandelier tightens to 2.5x ATR (crisis = cut losses fast)."""
    from config import settings
    assert settings.CHANDELIER_ATR_REGIME3_MULT == 2.5


def test_legacy_chandelier_atr_mult_default_is_3_0():
    """The legacy CHANDELIER_ATR_MULT setting stays at 3.0 for backward compatibility."""
    from config import settings
    assert settings.CHANDELIER_ATR_MULT == 3.0
