from datetime import date, timedelta

import pytest

from n012_ab import A, B, entry_volatility, frozen_models, r, volatility_flag


def test_implied_threshold_only_uses_prior_forecasts_and_current_prediction():
    dates = [(date(2023, 1, 1) + timedelta(days=i)).isoformat() for i in range(122)]
    model = {d: (0., -4.) for d in dates}
    model[dates[120]] = (0., -3.)
    assert volatility_flag(dates[120], {}, [], model, dates) == (True, "implied_model")
    model[dates[-1]] = (0., 100.)
    assert volatility_flag(dates[120], {}, [], model, dates) == (True, "implied_model")
    assert volatility_flag(dates[119], {}, [], model, dates) == (None, "native_fallback")


def test_vix_threshold_uses_prior_close_with_sixty_earlier_values():
    dates = [(date(2021, 1, 1) + timedelta(days=i)).isoformat() for i in range(63)]
    closes = {d: {"vix": 15.} for d in dates}
    closes[dates[60]]["vix"] = 14.
    closes[dates[61]]["vix"] = 99.
    assert volatility_flag(dates[61], closes, dates, {}, []) == (False, "prior_vix")
    assert volatility_flag(dates[60], closes, dates, {}, []) == (None, "native_fallback")
    closes[dates[60]]["vix"] = None
    assert volatility_flag(dates[61], closes, dates, {}, []) == (None, "native_fallback")


def test_entry_override_restores_native_and_leaves_stand_aside_function(monkeypatch):
    def native(_):
        return True

    monkeypatch.setattr(r.f.L, "vol_up", native)
    stand = r.f.L.vol_at
    with pytest.raises(RuntimeError, match="test exit"), entry_volatility(False):
        assert r.f.L.vol_up(None) is False and r.f.L.vol_at is stand
        raise RuntimeError("test exit")
    assert r.f.L.vol_up is native


def test_models_preserve_original_configuration_and_do_not_share_nested_state():
    arms = frozen_models()
    for name in (A, B):
        assert {k: v for k, v in arms[name].items() if k != "label"} == {
            k: v for k, v in arms["N11T"].items() if k != "label"}
        assert arms[name]["n11t"] is not arms["N11T"]["n11t"]
