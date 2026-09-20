"""[WORKFLOW-ITEMS-5/6/9 2026-09-20] Operations freshness diagnostic tests."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


PYTHON_ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ENGINE))


from ops_freshness_diagnostic import (  # noqa: E402
    ChannelReport,
    ChannelState,
    FreshnessDiagnostic,
    diagnose_freshness,
)


@pytest.fixture
def db_path():
    """Yield a temp DB path with the freshness tables.

    [WORKFLOW-ITEMS-5/6/9 2026-09-20] On Windows the file lock
    from the test's sqlite3 connection persists across the
    fixture teardown, so we deliberately skip file removal. The
    test process exits after pytest completes; the OS reclaims
    the temp directory.
    """
    import tempfile as _tempfile
    tmp = _tempfile.TemporaryDirectory()
    path = os.path.join(tmp.name, "test.sqlite3")
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE partner_token_store (
                access_token TEXT PRIMARY KEY,
                updated_at_utc TEXT
            );
            CREATE TABLE partner_collection_attempts (
                attempt_id TEXT PRIMARY KEY,
                public_observed_at_utc TEXT
            );
            CREATE TABLE bankroll_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT
            );
        """)
        db.commit()
    yield path


def _now() -> datetime:
    return datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def _insert(path: str, *, table: str, column: str, ts: datetime) -> None:
    with sqlite3.connect(path) as db:
        db.execute(
            f"INSERT INTO {table} ({column}) VALUES (?)",
            (ts.isoformat(),),
        )
        db.commit()


# -- Audit acceptance: each channel emits a stable outcome ----


def test_missing_db_returns_empty_diagnostic():
    diagnostic = diagnose_freshness("/nonexistent/path.sqlite3", now=_now())
    assert diagnostic.channels == ()
    assert diagnostic.any_stale is False
    assert diagnostic.any_missing is False


def test_all_channels_missing_when_db_empty(db_path):
    """[WORKFLOW-ITEMS-5/6/9 2026-09-20] Empty DB → every channel
    MISSING; ``any_missing=True``."""
    diagnostic = diagnose_freshness(db_path, now=_now())
    assert diagnostic.any_missing is True
    assert {c.name for c in diagnostic.channels} == {"login", "public_input", "ledger"}
    for channel in diagnostic.channels:
        assert channel.state == ChannelState.MISSING
        assert channel.age_seconds is None


def test_recent_evidence_marks_each_channel_pass(db_path):
    """[WORKFLOW-ITEMS-5/6/9 2026-09-20] Recent evidence → every
    channel PASS."""
    now = _now()
    _insert(db_path, table="partner_token_store", column="updated_at_utc", ts=now - timedelta(minutes=5))
    _insert(db_path, table="partner_collection_attempts", column="public_observed_at_utc", ts=now - timedelta(seconds=30))
    _insert(db_path, table="bankroll_ledger", column="timestamp", ts=now - timedelta(seconds=10))
    diagnostic = diagnose_freshness(db_path, now=now)
    assert diagnostic.any_stale is False
    assert diagnostic.any_missing is False
    for channel in diagnostic.channels:
        assert channel.state == ChannelState.PASS


def test_login_stale_after_threshold(db_path):
    """[WORKFLOW-ITEMS-5/6/9 2026-09-20] ``login_stale`` surfaces
    when the last Kite login is older than the configured
    threshold."""
    now = _now()
    # Login 25 hours ago (threshold default is 24h).
    _insert(db_path, table="partner_token_store", column="updated_at_utc", ts=now - timedelta(hours=25))
    diagnostic = diagnose_freshness(db_path, now=now)
    login = next(c for c in diagnostic.channels if c.name == "login")
    assert login.state == ChannelState.STALE
    assert login.age_seconds == 25 * 3600
    assert diagnostic.any_stale is True


def test_input_stale_after_threshold(db_path):
    """[WORKFLOW-ITEMS-5/6/9 2026-09-20] ``input_stale`` surfaces
    when the last public observation is older than the configured
    threshold (default 30 min)."""
    now = _now()
    _insert(db_path, table="partner_collection_attempts", column="public_observed_at_utc", ts=now - timedelta(minutes=45))
    diagnostic = diagnose_freshness(db_path, now=now)
    public_input = next(c for c in diagnostic.channels if c.name == "public_input")
    assert public_input.state == ChannelState.STALE


def test_ledger_stale_after_threshold(db_path):
    """[WORKFLOW-ITEMS-5/6/9 2026-09-20] ``ledger_stale`` surfaces
    when the last ledger write is older than the configured
    threshold (default 5 min)."""
    now = _now()
    _insert(db_path, table="bankroll_ledger", column="timestamp", ts=now - timedelta(minutes=10))
    diagnostic = diagnose_freshness(db_path, now=now)
    ledger = next(c for c in diagnostic.channels if c.name == "ledger")
    assert ledger.state == ChannelState.STALE


def test_audit_log_acceptance_threshold_one_marks_everything_stale(db_path):
    """[WORKFLOW-ITEMS-5/6/9 2026-09-20] A threshold of 1
    second + an evidence row that's a few seconds old is the
    audit's "everything stale" scenario. The diagnostic surfaces
    it as STALE."""
    now = _now()
    _insert(db_path, table="partner_token_store", column="updated_at_utc", ts=now - timedelta(seconds=5))
    _insert(db_path, table="partner_collection_attempts", column="public_observed_at_utc", ts=now - timedelta(seconds=5))
    _insert(db_path, table="bankroll_ledger", column="timestamp", ts=now - timedelta(seconds=5))
    diagnostic = diagnose_freshness(
        db_path, now=now,
        max_login_age_seconds=1,
        max_input_age_seconds=1,
        max_ledger_age_seconds=1,
    )
    assert diagnostic.any_stale is True
    for channel in diagnostic.channels:
        assert channel.state == ChannelState.STALE


def test_unparseable_timestamp_is_treated_as_missing(db_path):
    """A malformed timestamp does NOT crash the diagnostic; it is
    classified as MISSING and ``any_missing=True``."""
    with sqlite3.connect(db_path) as db:
        db.execute(
            "INSERT INTO partner_token_store (access_token, updated_at_utc) "
            "VALUES (?, ?)",
            ("tok", "not-a-real-timestamp"),
        )
        db.commit()
    diagnostic = diagnose_freshness(db_path, now=_now())
    login = next(c for c in diagnostic.channels if c.name == "login")
    assert login.state == ChannelState.MISSING
    assert diagnostic.any_missing is True


def test_custom_thresholds_apply(db_path):
    """The caller can override any threshold (e.g. a tighter
    threshold during deployment)."""
    now = _now()
    _insert(db_path, table="partner_collection_attempts", column="public_observed_at_utc", ts=now - timedelta(seconds=30))
    # 30 seconds old with a 60-second threshold → PASS.
    diagnostic = diagnose_freshness(db_path, now=now, max_input_age_seconds=60)
    public_input = next(c for c in diagnostic.channels if c.name == "public_input")
    assert public_input.state == ChannelState.PASS
    # Same 30-second-old evidence with a 10-second threshold → STALE.
    diagnostic = diagnose_freshness(db_path, now=now, max_input_age_seconds=10)
    public_input = next(c for c in diagnostic.channels if c.name == "public_input")
    assert public_input.state == ChannelState.STALE


def test_diagnostic_to_dict_round_trip(db_path):
    diagnostic = diagnose_freshness(db_path, now=_now())
    payload = diagnostic.to_dict()
    assert set(payload.keys()) == {"channels", "any_stale", "any_missing"}
    assert payload["any_missing"] is True
    assert {c["name"] for c in payload["channels"]} == {"login", "public_input", "ledger"}


def test_naive_timestamps_are_treated_as_utc(db_path):
    """A timestamp without a tz suffix is interpreted as UTC so
    the diagnostic is robust against naive-storage legacy."""
    now = _now()
    naive = (now - timedelta(minutes=10)).replace(tzinfo=None)
    _insert(db_path, table="bankroll_ledger", column="timestamp", ts=naive)
    diagnostic = diagnose_freshness(db_path, now=now)
    ledger = next(c for c in diagnostic.channels if c.name == "ledger")
    # 10 minutes old with default 5-minute threshold → STALE.
    assert ledger.state == ChannelState.STALE
    # But the age is computed correctly: 10 minutes = 600 seconds.
    assert ledger.age_seconds == 600


def test_partial_token_store_table_absent_does_not_crash(db_path):
    """[WORKFLOW-ITEMS-5/6/9 2026-09-20] A partial deployment
    (no partner_token_store table) does NOT crash the diagnostic;
    the channel is reported as MISSING."""
    with sqlite3.connect(db_path) as db:
        db.execute("DROP TABLE partner_token_store")
        db.commit()
    diagnostic = diagnose_freshness(db_path, now=_now())
    login = next(c for c in diagnostic.channels if c.name == "login")
    assert login.state == ChannelState.MISSING
