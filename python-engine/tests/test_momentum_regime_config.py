"""
Tests for momentum-regime-aware config settings.

[MOMENTUM-REGIME 2026-06-16] These are the new 3-regime settings for
momentum. They replace the single 'market_regime' string dispatch
(BULL/BEAR_RS_ONLY) with the 3-regime system already used for swing.

Settings to test:
  MOMENTUM_BLOCK_R3_ENTRIES:       bool  (default True)  — block all new entries in R3
  MOMENTUM_RISK_PCT_R1:            float (0.07)          — 7% of momentum pool in R1
  MOMENTUM_RISK_PCT_R2:            float (0.05)          — 5% of momentum pool in R2
  MOMENTUM_RISK_PCT_R3:            float (0.00)          — 0% in R3 (gated by BLOCK_R3)
  MOMENTUM_R_TARGET_R1:            float (2.0)           — 2.0R target in R1 (was MOMENTUM_R_TARGET)
  MOMENTUM_R_TARGET_R2:            float (1.5)           — 1.5R target in R2 (was MOMENTUM_R_TARGET_BEAR)

Backward compat:
  MOMENTUM_R_TARGET and MOMENTUM_RISK_PCT must remain as defaults
  so legacy callers don't break. New code should use R1/R2 settings.
"""

import pytest
from config import settings


class TestMomentumRegimeSettingsExist:
    """[MOMENTUM-REGIME 2026-06-16] The 6 new regime-aware settings exist."""

    def test_block_r3_entries_default_true(self):
        """Default: block R3 entries. Pure defense — most likely correct on day 1."""
        assert hasattr(settings, "MOMENTUM_BLOCK_R3_ENTRIES")
        assert settings.MOMENTUM_BLOCK_R3_ENTRIES is True

    def test_risk_pct_r1_default_0_07(self):
        """R1 = 7% of momentum pool (same as legacy MOMENTUM_RISK_PCT)."""
        assert hasattr(settings, "MOMENTUM_RISK_PCT_R1")
        assert settings.MOMENTUM_RISK_PCT_R1 == 0.07

    def test_risk_pct_r2_default_0_05(self):
        """R2 = 5% of momentum pool (smaller in elevated regime)."""
        assert hasattr(settings, "MOMENTUM_RISK_PCT_R2")
        assert settings.MOMENTUM_RISK_PCT_R2 == 0.05

    def test_risk_pct_r3_default_0_00(self):
        """R3 = 0% of momentum pool (block). Even if BLOCK_R3=False, R3 is 0."""
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
        """R1 > R2 > R3 — monotonic decrease as conditions deteriorate."""
        assert settings.MOMENTUM_RISK_PCT_R1 > settings.MOMENTUM_RISK_PCT_R2
        assert settings.MOMENTUM_RISK_PCT_R2 > settings.MOMENTUM_RISK_PCT_R3

    def test_r_target_decreases_with_regime(self):
        """R1 target > R2 target — tighter take-profit in elevated regime."""
        assert settings.MOMENTUM_R_TARGET_R1 > settings.MOMENTUM_R_TARGET_R2

    def test_legacy_settings_still_present(self):
        """Backward compat: MOMENTUM_R_TARGET and MOMENTUM_RISK_PCT must remain.
        MOMENTUM_RISK_PCT stays at the legacy 0.10 value — new code uses
        MOMENTUM_RISK_PCT_R{1,2,3}. Don't conflate them.
        """
        assert hasattr(settings, "MOMENTUM_R_TARGET")
        assert hasattr(settings, "MOMENTUM_RISK_PCT")
        # Legacy value preserved
        assert settings.MOMENTUM_RISK_PCT == 0.10
        # R1 is a NEW conservative default (less than legacy)
        assert settings.MOMENTUM_RISK_PCT_R1 == 0.07
        assert settings.MOMENTUM_RISK_PCT_R1 < settings.MOMENTUM_RISK_PCT


class TestMomentumRegimeSettingsEnvOverride:
    """[MOMENTUM-REGIME 2026-06-16] Settings are env-overridable for fast tuning."""

    def test_block_r3_env_override(self, monkeypatch):
        monkeypatch.setenv("MOMENTUM_BLOCK_R3_ENTRIES", "false")
        # Re-import to pick up env change
        import importlib
        import config
        importlib.reload(config)
        assert config.settings.MOMENTUM_BLOCK_R3_ENTRIES is False

    def test_risk_pct_r1_env_override(self, monkeypatch):
        monkeypatch.setenv("MOMENTUM_RISK_PCT_R1", "0.10")
        import importlib
        import config
        importlib.reload(config)
        assert config.settings.MOMENTUM_RISK_PCT_R1 == 0.10
