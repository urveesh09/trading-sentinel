from datetime import datetime
import math
from types import SimpleNamespace

import pytest

import round24 as mix


def test_forecast_gate_compares_volatility_with_missing_and_bad_values():
    assert mix.forecast_supports_invalidation((0., 2 * math.log(.90)))
    assert not mix.forecast_supports_invalidation((0., 2 * math.log(.91)))
    assert not mix.forecast_supports_invalidation((0., 2 * math.log(1.1)))
    assert not mix.forecast_supports_invalidation(None)
    assert not mix.forecast_supports_invalidation((math.inf, 0.))


def test_mix_scopes_delegate_in_order_and_restore_after_error(monkeypatch):
    arms = mix.books()
    assert "stand" not in arms[mix.ENTRY]["n11"]
    assert "stand" in mix.r.books()["N11T"]["n11"]
    engine = SimpleNamespace(book=arms[mix.CONDITIONED])
    monkeypatch.setitem(mix.T.ENGINE, "now", engine)
    assert mix.fallback.planner_previous is mix.BASE_PLANNER
    assert mix.recovery.route_previous is mix.BASE_ROUTE
    assert mix.invalidation.MANAGE is mix.BASE_MANAGE

    def fail(*_args):
        assert engine.book["n12"] == "CHAIN_FALLBACK"
        raise RuntimeError("test dispatch cleanup")

    monkeypatch.setattr(mix.fallback, "planner", fail)
    with pytest.raises(RuntimeError, match="cleanup"), mix.mix_dispatch():
        mix.T._planner(None, None, None, None, None)
    assert mix.T._planner is mix.BASE_PLANNER
    assert "n12" not in engine.book


def test_recovery_and_invalidation_have_separate_scopes(monkeypatch):
    engine = SimpleNamespace(book=mix.books()[mix.CONDITIONED])
    now = datetime(2024, 1, 1, 10)
    holdings = SimpleNamespace(open={1: None})
    monkeypatch.setattr(mix, "forecasts", lambda: {"2024-01-01": (0., -1.)})
    monkeypatch.setattr(mix.recovery, "route", lambda self, *_: self.book["n12"])
    monkeypatch.setattr(mix.invalidation, "manage", lambda self, *_: self.book["n12"])
    assert mix.MixReplay.route(engine, None, None, now) == "RECOVERY"
    assert "n12" not in engine.book
    assert mix.MixReplay._manage(engine, holdings, None, now) == "INVALIDATED"
    assert "n12" not in engine.book
