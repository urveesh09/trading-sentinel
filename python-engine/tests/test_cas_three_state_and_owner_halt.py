"""[WORKFLOW-A1 2026-09-20] Tests for the three-state CAS eligibility
contract and the owner entry-only halt surface.

Per audit ``docs/2026-09-20-independent-system-readiness-audit.md``
§3-A1: the legacy ``is_cas_eligible(symbol) -> bool`` collapsed
"configured, symbol absent" with "configuration unavailable" into
a single ``False``. The fix is a three-state enum and an explicit
owner entry-only halt.

Tests pin:

  * Three states returned by ``resolve_cas_eligibility``.
  * Six reason codes from ``cas_eligibility_reason``.
  * ``is_cas_eligible`` boolean shim remains ``True`` ONLY when
    ``state == ELIGIBLE``.
  * Membership metadata surfaces raw CSV sha256, configured size,
    freshness bound and staleness flag.
  * Owner entry-halt surface: global halt, per-channel halt,
    unknown channel, allowed baseline.
  * Existing legacy tests still pass (legacy boolean shim).
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest


PYTHON_ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ENGINE))

import market_calendar as mc  # noqa: E402
from market_calendar import (  # noqa: E402
    CasEligibilityReason,
    CasEligibilityState,
    cas_eligibility_reason,
    cas_membership_max_age_days,
    is_cas_eligible,
    resolve_cas_eligibility,
)
from owner_entry_halt import (  # noqa: E402
    EntryHaltVerdict,
    HaltChannel,
    is_owner_entry_halted,
    normalise_channel,
)


@pytest.fixture(autouse=True)
def _reset_lru_caches():
    """Clear ``market_calendar`` module-level ``lru_cache`` entries so
    monkeypatched settings take effect between tests."""
    mc._normalised_cas_eligibility_set.cache_clear()
    yield
    mc._normalised_cas_eligibility_set.cache_clear()


# -- Three-state resolver tests ------------------------------------------


def test_resolve_cas_eligibility_returns_unknown_for_empty_config(
    monkeypatch,
):
    """Empty configured list must NOT be silently treated as
    NOT_ELIGIBLE. The audit defect A1 was exactly this."""
    import config as _config
    monkeypatch.setattr(
        _config.settings, "CAS_PHASE1_FNO_UNDERLYINGS", "",
    )
    state = resolve_cas_eligibility("RELIANCE")
    assert state is CasEligibilityState.UNKNOWN
    reason = cas_eligibility_reason("RELIANCE")
    assert reason is CasEligibilityReason.EMPTY_MEMBERSHIP_LIST


def test_resolve_cas_eligibility_returns_unknown_for_none_symbol():
    state = resolve_cas_eligibility(None)
    assert state is CasEligibilityState.UNKNOWN
    reason = cas_eligibility_reason(None)
    assert reason is CasEligibilityReason.INVALID_SYMBOL


def test_resolve_cas_eligibility_returns_unknown_for_empty_symbol():
    state = resolve_cas_eligibility("   ")
    assert state is CasEligibilityState.UNKNOWN
    reason = cas_eligibility_reason("   ")
    assert reason is CasEligibilityReason.INVALID_SYMBOL


def test_resolve_cas_eligibility_returns_unknown_for_non_string_symbol():
    state = resolve_cas_eligibility(123)  # type: ignore[arg-type]
    assert state is CasEligibilityState.UNKNOWN
    reason = cas_eligibility_reason(123)  # type: ignore[arg-type]
    assert reason is CasEligibilityReason.INVALID_SYMBOL


def test_resolve_cas_eligibility_returns_eligible_when_listed(
    monkeypatch,
):
    import config as _config
    monkeypatch.setattr(
        _config.settings, "CAS_PHASE1_FNO_UNDERLYINGS", "RELIANCE, INFY",
    )
    state = resolve_cas_eligibility("RELIANCE")
    assert state is CasEligibilityState.ELIGIBLE
    reason = cas_eligibility_reason("RELIANCE")
    assert reason is CasEligibilityReason.LISTED


def test_resolve_cas_eligibility_returns_not_eligible_when_verified_absent(
    monkeypatch,
):
    """Distinct from UNKNOWN: a verified-absent answer is NOT_ELIGIBLE."""
    import config as _config
    monkeypatch.setattr(
        _config.settings, "CAS_PHASE1_FNO_UNDERLYINGS", "RELIANCE",
    )
    state = resolve_cas_eligibility("TCS")
    assert state is CasEligibilityState.NOT_ELIGIBLE
    reason = cas_eligibility_reason("TCS")
    assert reason is CasEligibilityReason.NOT_LISTED


def test_resolve_cas_eligibility_handles_mixed_case_symbol(
    monkeypatch,
):
    import config as _config
    monkeypatch.setattr(
        _config.settings, "CAS_PHASE1_FNO_UNDERLYINGS", " reliance ",
    )
    state = resolve_cas_eligibility("  reliance  ")
    assert state is CasEligibilityState.ELIGIBLE


def test_resolve_cas_eligibility_returns_unknown_when_config_import_fails(
    monkeypatch,
):
    """A config-import failure is a configuration problem, not a
    verified absence. The audit's specific failure mode."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "config" or name.startswith("config."):
            raise ImportError("simulated config import failure")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    state = resolve_cas_eligibility("RELIANCE")
    assert state is CasEligibilityState.UNKNOWN
    reason = cas_eligibility_reason("RELIANCE")
    assert reason is CasEligibilityReason.CONFIG_IMPORT_FAILED


# -- Boolean shim backwards-compat ----------------------------------------


def test_is_cas_eligible_boolean_shim_is_true_only_for_eligible(monkeypatch):
    """Legacy callers reading the boolean must keep their
    character-for-character contract."""
    import config as _config
    monkeypatch.setattr(
        _config.settings, "CAS_PHASE1_FNO_UNDERLYINGS", "RELIANCE",
    )
    assert is_cas_eligible("RELIANCE") is True
    assert is_cas_eligible("TCS") is False
    assert is_cas_eligible(None) is False
    assert is_cas_eligible("") is False


def test_is_cas_eligible_returns_false_for_unknown_state(monkeypatch):
    """UNKNOWNetiologically the shim must NOT grant True."""
    import config as _config
    monkeypatch.setattr(
        _config.settings, "CAS_PHASE1_FNO_UNDERLYINGS", "",
    )
    assert is_cas_eligible("RELIANCE") is False


# -- Membership metadata tests --------------------------------------------


def test_cas_membership_metadata_reports_configured_size(monkeypatch):
    import config as _config
    monkeypatch.setattr(
        _config.settings, "CAS_PHASE1_FNO_UNDERLYINGS", "RELIANCE, INFY, TCS",
    )
    metadata = mc._cas_membership_metadata()
    assert metadata.configured_size == 3
    assert metadata.is_stale is False
    assert len(metadata.raw_csv_sha256) == 64


def test_cas_membership_metadata_marks_empty_list_as_stale(monkeypatch):
    import config as _config
    monkeypatch.setattr(
        _config.settings, "CAS_PHASE1_FNO_UNDERLYINGS", "",
    )
    metadata = mc._cas_membership_metadata()
    assert metadata.is_stale is True
    assert metadata.configured_size == 0


def test_cas_membership_max_age_days_honours_env(monkeypatch):
    monkeypatch.setenv("CAS_MEMBERSHIP_MAX_AGE_DAYS", "7")
    assert cas_membership_max_age_days() == 7


def test_cas_membership_max_age_days_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("CAS_MEMBERSHIP_MAX_AGE_DAYS", raising=False)
    assert cas_membership_max_age_days() == 30


def test_cas_membership_max_age_days_rejects_invalid(monkeypatch):
    monkeypatch.setenv("CAS_MEMBERSHIP_MAX_AGE_DAYS", "not-a-number")
    assert cas_membership_max_age_days() == 30


def test_cas_membership_max_age_days_rejects_zero(monkeypatch):
    monkeypatch.setenv("CAS_MEMBERSHIP_MAX_AGE_DAYS", "0")
    assert cas_membership_max_age_days() == 30


# -- Owner entry-halt tests ----------------------------------------------


def test_owner_entry_halt_unknown_channel_is_refused():
    """A future channel that bypasses the whitelist must fail
    closed. The verdict's ``allowed`` must be False and the reason
    must be ``unknown_channel``."""
    verdict = is_owner_entry_halted("future-channel")
    assert verdict.allowed is False
    assert verdict.reason == "unknown_channel"
    assert verdict.channel == "future-channel"


def test_owner_entry_halt_unknown_channel_for_none():
    verdict = is_owner_entry_halted(None)
    assert verdict.allowed is False
    assert verdict.reason == "unknown_channel"


def test_owner_entry_halt_allowed_by_default():
    verdict = is_owner_entry_halted(
        HaltChannel.MOMENTUM,
        global_halt=False,
        per_channel_csv="",
    )
    assert verdict.allowed is True
    assert verdict.global_halt is False
    assert verdict.per_channel is False
    assert verdict.reason == "allowed"


def test_owner_entry_halt_global_halt_blocks_every_channel():
    verdict = is_owner_entry_halted(
        HaltChannel.MOMENTUM,
        global_halt=True,
        per_channel_csv="",
    )
    assert verdict.allowed is False
    assert verdict.global_halt is True
    assert verdict.reason == "global_owner_entry_halt"


def test_owner_entry_halt_per_channel_blocks_named_only():
    verdict = is_owner_entry_halted(
        HaltChannel.MOMENTUM,
        global_halt=False,
        per_channel_csv="momentum, edge",
    )
    assert verdict.allowed is False
    assert verdict.per_channel is True
    assert verdict.reason == "per_channel_owner_entry_halt"


def test_owner_entry_halt_per_channel_csv_isolates_other_sleeves():
    """A per-channel halt on momentum must NOT block penny or
    fno. The audit's requirement was a per-channel control
    surface, not a global lever."""
    momentum = is_owner_entry_halted(
        HaltChannel.MOMENTUM,
        global_halt=False,
        per_channel_csv="momentum",
    )
    penny = is_owner_entry_halted(
        HaltChannel.PENNY,
        global_halt=False,
        per_channel_csv="momentum",
    )
    assert momentum.allowed is False
    assert penny.allowed is True


def test_owner_entry_halt_global_takes_precedence_over_per_channel():
    verdict = is_owner_entry_halted(
        HaltChannel.PENNY,
        global_halt=True,
        per_channel_csv="",
    )
    assert verdict.allowed is False
    assert verdict.global_halt is True
    assert verdict.per_channel is False
    assert verdict.reason == "global_owner_entry_halt"


def test_owner_entry_halt_config_import_failure_refuses():
    """A config-import failure MUST fail closed; the halt surface
    itself must never be the path that fails open."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "config" or name.startswith("config."):
            raise ImportError("simulated config import failure")
        return real_import(name, *args, **kwargs)

    import builtins as _b
    _b.__import__ = fake_import
    try:
        verdict = is_owner_entry_halted(HaltChannel.MOMENTUM)
        assert verdict.allowed is False
        assert verdict.reason == "config_import_failed"
    finally:
        _b.__import__ = real_import


def test_owner_entry_halt_normalise_channel_handles_whitespace_and_case():
    assert normalise_channel("  MOMENTUM  ") is HaltChannel.MOMENTUM
    assert normalise_channel("Penny") is HaltChannel.PENNY
    assert normalise_channel("fno") is HaltChannel.FNO
    assert normalise_channel("edge") is HaltChannel.EDGE
    assert normalise_channel("") is HaltChannel.UNKNOWN
    assert normalise_channel(None) is HaltChannel.UNKNOWN
    assert normalise_channel("not-a-channel") is HaltChannel.UNKNOWN
    assert normalise_channel(123) is HaltChannel.UNKNOWN  # type: ignore[arg-type]


def test_entry_halt_verdict_serialises_to_dict():
    verdict = EntryHaltVerdict(
        channel="momentum",
        allowed=False,
        global_halt=True,
        per_channel=False,
        reason="global_owner_entry_halt",
    )
    payload = verdict.to_dict()
    assert payload == {
        "channel": "momentum",
        "allowed": False,
        "global_halt": True,
        "per_channel": False,
        "reason": "global_owner_entry_halt",
    }
