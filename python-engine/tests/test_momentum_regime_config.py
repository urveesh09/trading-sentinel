"""
Tests for momentum-regime-aware config settings.

[MOMENTUM-REGIME 2026-06-16] These are the new 3-regime settings for
momentum. They replace the single 'market_regime' string dispatch
(BULL/BEAR_RS_ONLY) with the 3-regime system already used for swing.

Settings to test:
  MOMENTUM_BLOCK_R3_ENTRIES:       bool  (default True)  -- block all new entries in R3
  MOMENTUM_RISK_PCT_R1:            float (0.07)          -- 7% of momentum pool in R1
  MOMENTUM_RISK_PCT_R2:            float (0.05)          -- 5% of momentum pool in R2
  MOMENTUM_RISK_PCT_R3:            float (0.00)          -- 0% in R3 (gated by BLOCK_R3)
  MOMENTUM_R_TARGET_R1:            float (2.0)           -- 2.0R target in R1 (was MOMENTUM_R_TARGET)
  MOMENTUM_R_TARGET_R2:            float (1.5)           -- 1.5R target in R2 (was MOMENTUM_R_TARGET_BEAR)

Backward compat:
  MOMENTUM_R_TARGET and MOMENTUM_RISK_PCT must remain as defaults
  so legacy callers don't break. New code should use R1/R2 settings.
"""

import pytest
from config import settings


class TestMomentumRegimeSettingsExist:
    """[MOMENTUM-REGIME 2026-06-16] The 6 new regime-aware settings exist."""

    def test_block_r3_entries_default_false(self):
        """[MOMENTUM-AGGRESSIVE 2026-06-16] Default: R3 block OFF.
        R3 still cannot trade by default because MOMENTUM_RISK_PCT_R3=0.00.
        Defense-in-depth: opt-in to R3 trading by setting R3 risk > 0 in .env.
        """
        assert hasattr(settings, "MOMENTUM_BLOCK_R3_ENTRIES")
        assert settings.MOMENTUM_BLOCK_R3_ENTRIES is False

    def test_risk_pct_r1_default_0_10(self):
        """[MOMENTUM-AGGRESSIVE 2026-06-16] R1 = 10% of momentum pool (aggressive, restored from legacy)."""
        assert hasattr(settings, "MOMENTUM_RISK_PCT_R1")
        assert settings.MOMENTUM_RISK_PCT_R1 == 0.10

    def test_risk_pct_r2_default_0_07(self):
        """[MOMENTUM-AGGRESSIVE 2026-06-16] R2 = 7% of momentum pool."""
        assert hasattr(settings, "MOMENTUM_RISK_PCT_R2")
        assert settings.MOMENTUM_RISK_PCT_R2 == 0.07

    def test_risk_pct_r3_default_0_00(self):
        """R3 = 0% of momentum pool. Even with BLOCK_R3=False, R3 cannot open positions."""
        assert hasattr(settings, "MOMENTUM_RISK_PCT_R3")
        assert settings.MOMENTUM_RISK_PCT_R3 == 0.0

    def test_r_target_r1_default_2_0(self):
        """R1 = 2.0R target (same as legacy MOMENTUM_R_TARGET)."""
        assert hasattr(settings, "MOMENTUM_R_TARGET_R1")
        assert settings.MOMENTUM_R_TARGET_R1 == 2.0

    def test_r_target_r2_default_1_5(self):
        """R2 = 1.5R target (same as legacy MOMENTUM_R_TARGET_BEAR)."""
        assert hasattr(settings, "MOMENTUM_R_TARGET_R2")
        assert settings.MOMENTUM_R_TARGET_R2 == 1.5

    def test_risk_pct_decreases_with_regime(self):
        """R1 > R2 > R3 -- monotonic decrease as conditions deteriorate."""
        assert settings.MOMENTUM_RISK_PCT_R1 > settings.MOMENTUM_RISK_PCT_R2
        assert settings.MOMENTUM_RISK_PCT_R2 > settings.MOMENTUM_RISK_PCT_R3

    def test_r_target_decreases_with_regime(self):
        """R1 target > R2 target -- tighter take-profit in elevated regime."""
        assert settings.MOMENTUM_R_TARGET_R1 > settings.MOMENTUM_R_TARGET_R2

    def test_legacy_settings_still_present(self):
        """Backward compat: MOMENTUM_R_TARGET and MOMENTUM_RISK_PCT must remain.
        MOMENTUM_RISK_PCT stays at the legacy 0.10 value -- new code uses
        MOMENTUM_RISK_PCT_R{1,2,3}. Don't conflate them.
        """
        assert hasattr(settings, "MOMENTUM_R_TARGET")
        assert hasattr(settings, "MOMENTUM_RISK_PCT")
        # Legacy value preserved
        assert settings.MOMENTUM_RISK_PCT == 0.10
        # [MOMENTUM-AGGRESSIVE 2026-06-16] R1 now matches legacy (was 0.07, now 0.10)
        assert settings.MOMENTUM_RISK_PCT_R1 == 0.10
        assert settings.MOMENTUM_RISK_PCT_R1 == settings.MOMENTUM_RISK_PCT


class TestMomentumRegimeSettingsEnvOverride:
    """[MOMENTUM-REGIME 2026-06-16] Settings are env-overridable for fast tuning."""

    # [TEST-POLLUTION-FIX 2026-07-10] These two tests previously did
    # `importlib.reload(config)`, which rebinds config.settings to a NEW
    # Settings instance mid-suite. Every module first-imported (or doing a
    # run-time `from config import settings`) AFTER the reload got the new
    # object while modules imported earlier kept the old one -- so
    # monkeypatches landed on the wrong instance and 3 later tests
    # (test_universe_expansion CSV fallback, both TestPoolBreakdown
    # paper-mode tests) failed order-dependently in the full suite while
    # passing in isolation. Constructing a fresh local Settings() proves
    # the same property (env overridability) without nuking module
    # identity for the rest of the run.

    def test_block_r3_env_override(self, monkeypatch):
        monkeypatch.setenv("MOMENTUM_BLOCK_R3_ENTRIES", "false")
        from config import Settings
        assert Settings().MOMENTUM_BLOCK_R3_ENTRIES is False

    def test_risk_pct_r1_env_override(self, monkeypatch):
        monkeypatch.setenv("MOMENTUM_RISK_PCT_R1", "0.10")
        from config import Settings
        assert Settings().MOMENTUM_RISK_PCT_R1 == 0.10
