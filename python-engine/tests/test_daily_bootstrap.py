"""[BOOTSTRAP-2026-07-17] Token-aware daily bootstrap registry.

On 2026-07-17 the 08:00 cron cluster fired while the engine held no fresh
Kite token (operator logged in at 08:05); every job failed, nothing
retried, and F&O + penny ran degraded/dead all day. This registry runs
the daily refresh tasks only when a token issued TODAY is armed, defers
with one reminder otherwise, and re-runs them on login. These tests pin
that contract.
"""
from datetime import date, timedelta

import pytest

import daily_bootstrap


class _FakeKite:
    def __init__(self, token="tok", token_date=None):
        self.access_token = token
        self.token_set_ist_date = token_date


class _FakeBook:
    """Stand-in for the FNO instrument book."""
    def __init__(self, ready_after_refresh=True):
        self._ready = False
        self._ready_after_refresh = ready_after_refresh
        self.refresh_calls = 0

    def ready(self, today):
        return self._ready

    async def refresh(self, kite):
        self.refresh_calls += 1
        self._ready = self._ready_after_refresh


@pytest.fixture
def wire(monkeypatch):
    """Wire main.* and fno_instruments.* to controllable fakes. Returns a
    dict the test tweaks. Bootstrap state lives under settings.DB_PATH's
    dir (a tmp path via conftest), so it is isolated per test."""
    import main

    today = date.today()
    state = {
        "kite": _FakeKite(token="tok", token_date=today),
        "trading_day": True,
        "universe_ok": True,
        "universe_calls": 0,
        "book": _FakeBook(),
        "notes": [],
    }

    async def _is_trading_day(d, db_path):
        return state["trading_day"]

    async def _run_universe():
        state["universe_calls"] += 1
        return state["universe_ok"]

    async def _notify(message, *, event="operator_alert"):
        state["notes"].append((event, message))
        return True

    # [PARTNER-TIPS 2026-07-18] The fno_instruments task now delegates to
    # fno_underlyings.refresh_all (NIFTY + analytics books, one dump per
    # segment). These tests pin the REGISTRY contract (token gating, done
    # marks, retries), so refresh_all is faked here; its own refresh
    # semantics are covered by test_fno_underlyings.py.
    async def _refresh_all(kite):
        await state["book"].refresh(kite)
        return {"NIFTY": state["book"].ready(today)}

    monkeypatch.setattr(main, "kite", state["kite"])
    monkeypatch.setattr(main, "is_trading_day", _is_trading_day)
    monkeypatch.setattr(main, "run_penny_universe_refresh", _run_universe)
    import fno_instruments
    monkeypatch.setattr(fno_instruments, "get_fno_instruments",
                        lambda: state["book"])
    import fno_underlyings
    monkeypatch.setattr(fno_underlyings, "refresh_all", _refresh_all)
    import operator_alert
    monkeypatch.setattr(operator_alert, "notify_operator", _notify)
    # Reset the module-level reminder latch between tests.
    monkeypatch.setattr(daily_bootstrap, "_reminder_sent_for", None)
    return state


# -- token freshness ---------------------------------------------------

def test_token_fresh_only_when_dated_today(wire):
    assert daily_bootstrap.token_is_fresh_today() is True

    wire["kite"].token_set_ist_date = date.today() - timedelta(days=1)
    assert daily_bootstrap.token_is_fresh_today() is False, (
        "yesterday's token is set in memory but expired at the broker"
    )

    wire["kite"].access_token = ""
    wire["kite"].token_set_ist_date = date.today()
    assert daily_bootstrap.token_is_fresh_today() is False


# -- run_pending -------------------------------------------------------

def test_run_pending_runs_all_and_marks_done(wire):
    res = _run(daily_bootstrap.run_pending("test"))
    assert res == {"penny_universe": True, "fno_instruments": True}
    assert wire["universe_calls"] == 1
    assert wire["book"].refresh_calls == 1
    # Second call is a no-op: everything already done today.
    res2 = _run(daily_bootstrap.run_pending("test"))
    assert res2 == {}
    assert wire["universe_calls"] == 1


def test_run_pending_skips_without_fresh_token(wire):
    wire["kite"].token_set_ist_date = date.today() - timedelta(days=1)
    res = _run(daily_bootstrap.run_pending("cron_0800"))
    assert res == {}
    assert wire["universe_calls"] == 0
    assert wire["book"].refresh_calls == 0


def test_run_pending_skips_on_non_trading_day(wire):
    wire["trading_day"] = False
    res = _run(daily_bootstrap.run_pending("cron_0800"))
    assert res == {}
    assert wire["universe_calls"] == 0


def test_failed_task_stays_pending_and_retries(wire):
    """A task that fails must NOT be marked done -- it retries on the next
    entry point (this is the whole point: login re-runs what 08:00 could
    not)."""
    wire["universe_ok"] = False
    res = _run(daily_bootstrap.run_pending("cron_0800"))
    assert res["penny_universe"] is False
    assert res["fno_instruments"] is True
    assert "penny_universe" in daily_bootstrap.pending_tasks()
    assert "fno_instruments" not in daily_bootstrap.pending_tasks()

    # Now the retry (e.g. post-login) succeeds.
    wire["universe_ok"] = True
    res2 = _run(daily_bootstrap.run_pending("post_login"))
    assert res2 == {"penny_universe": True}
    assert daily_bootstrap.pending_tasks() == []


# -- 08:00 entry -------------------------------------------------------

def test_0800_runs_when_token_fresh(wire):
    _run(daily_bootstrap.bootstrap_0800_job())
    assert wire["universe_calls"] == 1
    assert wire["notes"] == [], "no reminder needed when the token is fresh"


def test_0800_defers_and_reminds_once_when_no_fresh_token(wire):
    wire["kite"].token_set_ist_date = date.today() - timedelta(days=1)
    _run(daily_bootstrap.bootstrap_0800_job())
    assert wire["universe_calls"] == 0
    assert len(wire["notes"]) == 1
    event, msg = wire["notes"][0]
    assert event == "daily_bootstrap_deferred"
    assert "log in" in msg.lower()

    # A second 08:00-style call the same day must not double-remind.
    _run(daily_bootstrap.bootstrap_0800_job())
    assert len(wire["notes"]) == 1


# -- state file reset --------------------------------------------------

def test_state_resets_on_new_day(wire, monkeypatch):
    _run(daily_bootstrap.run_pending("test"))
    assert daily_bootstrap.pending_tasks() == []

    # Simulate tomorrow: _today_ist advances, done-set no longer matches.
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    monkeypatch.setattr(daily_bootstrap, "_today_ist", lambda: tomorrow)
    assert set(daily_bootstrap.pending_tasks()) == {
        "penny_universe", "fno_instruments",
    }


# -- helper ------------------------------------------------------------

def _run(coro):
    import asyncio
    return asyncio.run(coro)
