from types import SimpleNamespace

import pytest

from round30 import COMBINED, TREND, TrendEntryReplay, books, mix, r, trend_dispatch


def test_trend_scope_changes_only_lock_values_and_restores_native(monkeypatch):
    def native(_position, *, params, **_kwargs):
        return params

    monkeypatch.setattr(r.exits, "evaluate_single_leg_exit", native)
    params = {"FNO_PROFIT_LOCK_ENABLED": True, "FNO_PROFIT_LOCK_ARM_R": .75,
              "FNO_PROFIT_LOCK_KEEP_FRACTION": .50, "FNO_HARD_FLAT_MIN": 910}
    with pytest.raises(RuntimeError, match="test restore"), trend_dispatch():
        observed = r.exits.evaluate_single_leg_exit(SimpleNamespace(round30_status="ADVERSE"), params=params)
        assert observed == {**params, "FNO_PROFIT_LOCK_ARM_R": .60, "FNO_PROFIT_LOCK_KEEP_FRACTION": .65}
        raise RuntimeError("test restore")
    assert r.exits.evaluate_single_leg_exit is native


def test_two_arms_keep_independent_controls_and_existing_entry_component():
    candidates = books()
    assert "stand" in candidates[TREND]["n11"]
    assert "stand" not in candidates[COMBINED]["n11"]
    assert candidates[COMBINED]["n12_mix"] == mix.ENTRY
    assert TrendEntryReplay.route is mix.MixReplay.route
