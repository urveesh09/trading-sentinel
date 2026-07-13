"""[OUTAGE-2026-07-13] Regression tests for the four defects that cost a day.

The chain, verified from prod logs:

  1. The deploy's docker build filled a disk that was already ~86% full.
  2. 09:06 the operator logged in. The engine set the token in memory, then
     _persist_kite_token did open(path, "w") -- TRUNCATE, then write. The
     truncate succeeded; the write failed with ENOSPC. kite_token.json was left
     ZERO BYTES.
  3. The failure was swallowed as "best-effort; the in-memory token still
     works". Which was true, for 38 minutes.
  4. 09:44 the host rebooted. The in-memory token died with the process. The
     restore path read the 0-byte file, raised JSONDecodeError, returned None,
     and the engine came up UNARMED -- and never re-armed.
  5. From 09:44 to close: every scan logged `no_access_token`. Zero trades.
     Zero Telegram messages. All five containers reported "healthy" throughout.

Four defects, four sections below. Each test fails against the pre-fix code.
"""
import json
import os

import pytest

from config import settings


# ===================================================================
# DEFECT 1: truncate-then-write destroyed the token file
# ===================================================================

def test_persist_is_atomic_a_failed_write_does_not_destroy_the_old_token(
    tmp_path, monkeypatch
):
    """THE CORE REGRESSION.

    A good token file exists. A new persist fails mid-write (disk full). The OLD
    FILE MUST SURVIVE. Pre-fix, open(path,"w") truncated it to zero bytes before
    the write was even attempted, so the failure destroyed the only artifact that
    could have re-armed the engine after the reboot 38 minutes later.
    """
    import token_lifecycle

    db = tmp_path / "cache.db"
    monkeypatch.setattr(settings, "DB_PATH", str(db))
    path = tmp_path / "kite_token.json"

    # A perfectly good token already on disk.
    good = {"access_token": "GOOD_TOKEN", "saved_date_ist": "2026-07-13"}
    path.write_text(json.dumps(good))

    # The disk fills.
    real_dump = json.dump

    def enospc(*a, **kw):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(token_lifecycle._json, "dump", enospc)

    ok = token_lifecycle._persist_kite_token("NEW_TOKEN")

    assert ok is False                       # and it SAYS it failed (defect 2)
    assert path.exists()
    assert json.loads(path.read_text()) == good, (
        "the failed write destroyed the existing token file -- this is the "
        "2026-07-13 outage"
    )
    # No half-written temp left lying around for a later reader to trip on.
    assert not (tmp_path / "kite_token.json.tmp").exists()

    monkeypatch.setattr(token_lifecycle._json, "dump", real_dump)


def test_persist_success_writes_a_readable_token_and_reports_true(tmp_path, monkeypatch):
    import token_lifecycle

    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "cache.db"))

    assert token_lifecycle._persist_kite_token("TOK123") is True

    payload = token_lifecycle._load_persisted_kite_token_if_fresh()
    assert payload["access_token"] == "TOK123"


def test_a_zero_byte_token_file_is_survived_not_fatal(tmp_path, monkeypatch):
    """What the engine actually found at 09:44. It must degrade to "no token"
    (which it did), not crash -- but see the readiness watchdog below: it must
    also SAY SO."""
    import token_lifecycle

    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "cache.db"))
    (tmp_path / "kite_token.json").write_text("")   # 0 bytes, as on the day

    assert token_lifecycle._load_persisted_kite_token_if_fresh() is None


# ===================================================================
# DEFECT 3: the watchdog was blind to BOTH sides being dead
# ===================================================================

def test_both_sides_unarmed_is_paged_not_treated_as_agreement():
    """THE SILENCE BUG.

    _token_recon_mismatch_message was written to catch SPLIT-BRAIN, so it
    returned None whenever the two sides agreed -- including when they agreed by
    both being DEAD. On 2026-07-13: python_armed=False, node="expired" ->
    False == False -> "they agree" -> None -> silence. Every 15 minutes. For six
    hours of market time.
    """
    from token_lifecycle import _token_recon_mismatch_message

    msg = _token_recon_mismatch_message(python_armed=False, node_token_status="expired")

    assert msg is not None, (
        "both sides unarmed produced NO alert -- this is the six hours of "
        "silence on 2026-07-13"
    )
    assert "NOT TRADING" in msg


def test_both_sides_armed_is_still_silent():
    """The healthy case must stay quiet, or the fix is just noise."""
    from token_lifecycle import _token_recon_mismatch_message

    assert _token_recon_mismatch_message(True, "active") is None


def test_genuine_split_brain_still_pages():
    """Do not regress the 2026-07-09 case this function was built for."""
    from token_lifecycle import _token_recon_mismatch_message

    assert "SPLIT-BRAIN" in _token_recon_mismatch_message(True, "expired")
    assert "SPLIT-BRAIN" in _token_recon_mismatch_message(False, "active")


def test_node_unreachable_stays_silent():
    from token_lifecycle import _token_recon_mismatch_message

    assert _token_recon_mismatch_message(False, None) is None


# ===================================================================
# DEFECT 4: nothing asked "can I actually trade?"
# ===================================================================

def test_readiness_alerts_immediately_on_the_falling_edge():
    """`None` sentinel, not 0.0: time.monotonic() can be below the dedupe
    interval right after a host boot -- and 09:44 on 2026-07-13 WAS right after
    a host boot. A 0.0 default would have suppressed the only page that
    mattered."""
    from ops_watchdogs import _readiness_should_alert

    state = {"last_alert_monotonic": None, "was_ready": True}
    assert _readiness_should_alert(ready=False, now_monotonic=12.0, state=state) is True


def test_readiness_does_not_spam_while_still_down():
    from ops_watchdogs import (
        READINESS_ALERT_MIN_INTERVAL_SEC,
        _readiness_should_alert,
    )

    state = {"last_alert_monotonic": 1000.0, "was_ready": False}

    assert _readiness_should_alert(False, 1000.0 + 60, state) is False
    assert _readiness_should_alert(
        False, 1000.0 + READINESS_ALERT_MIN_INTERVAL_SEC + 1, state
    ) is True


def test_readiness_is_silent_when_the_engine_can_trade():
    from ops_watchdogs import _readiness_should_alert

    state = {"last_alert_monotonic": None, "was_ready": True}
    assert _readiness_should_alert(ready=True, now_monotonic=99.0, state=state) is False


@pytest.mark.asyncio
async def test_readiness_tick_pages_when_unarmed_during_market_hours(monkeypatch):
    """End-to-end: reproduce 2026-07-13's state (alive, scheduler running, NO
    TOKEN, market open) and assert the operator is actually paged."""
    import main
    import ops_watchdogs

    sent = []

    async def _fake_notify(message, *, event="x"):
        sent.append(message)
        return True

    async def _trading_day(*a, **kw):
        return True

    class _NoToken:
        access_token = ""          # exactly the 09:44 state

    class _RunningScheduler:
        running = True

    monkeypatch.setattr(main, "kite", _NoToken())
    monkeypatch.setattr(main, "scheduler", _RunningScheduler())
    monkeypatch.setattr(ops_watchdogs, "is_trading_day", _trading_day)
    monkeypatch.setattr(
        "operator_alert.notify_operator", _fake_notify, raising=False
    )

    # Force the clock inside market hours (11:00 IST).
    import datetime as _dt

    real_datetime = ops_watchdogs.datetime

    class _FakeDatetime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 7, 13, 11, 0, tzinfo=tz)

    monkeypatch.setattr(ops_watchdogs, "datetime", _FakeDatetime)
    ops_watchdogs._readiness_state["last_alert_monotonic"] = None
    ops_watchdogs._readiness_state["was_ready"] = True

    await ops_watchdogs._trading_readiness_tick()

    assert sent, (
        "the engine had no token, the market was open, and NOTHING was sent -- "
        "this is 2026-07-13"
    )
    assert "NOT TRADING" in sent[0]
