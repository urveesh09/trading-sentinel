"""Check real persisted sources; quiet accounting is not a provider outage."""
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone, timedelta
import pytest
from ops_freshness_diagnostic import diagnose_freshness

NOW = datetime(2026, 9, 21, 6, 0, tzinfo=timezone.utc)


def evidence(tmp_path, stamp=NOW):
    token = tmp_path / 'kite_token.json'
    token.write_text(json.dumps({'access_token': 'test-only-secret', 'saved_date_ist': '2026-09-21'}))
    os.utime(token, (NOW.timestamp(), NOW.timestamp()))
    with closing(sqlite3.connect(tmp_path / 'partner-collection-attempts.sqlite3')) as db:
        db.execute('CREATE TABLE partner_collection_attempts(public_observed_at_utc TEXT)')
        db.execute('INSERT INTO partner_collection_attempts VALUES (?)', (stamp.isoformat() if isinstance(stamp, datetime) else stamp,))
        db.commit()
    return token


def test_missing_evidence_is_missing_and_does_not_create_files(tmp_path):
    result = diagnose_freshness(token_path=tmp_path/'missing', archive_root=tmp_path, now=NOW)
    assert result.any_missing
    assert not list(tmp_path.iterdir())


def test_real_sources_are_read_only_and_never_expose_token(tmp_path):
    token = evidence(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    result = diagnose_freshness(token_path=token, archive_root=tmp_path, now=NOW)
    assert not result.any_missing and not result.any_stale
    assert 'test-only-secret' not in json.dumps(result.to_dict())
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
    assert 'ledger' not in {c.name for c in result.channels}


@pytest.mark.parametrize('stamp', [NOW + timedelta(minutes=1), NOW.replace(tzinfo=None), 'bad', None])
def test_invalid_public_clocks_do_not_prove_freshness(tmp_path, stamp):
    token = evidence(tmp_path, stamp)
    result = diagnose_freshness(token_path=token, archive_root=tmp_path, now=NOW)
    assert result.any_missing


def test_stale_public_clock_and_custom_threshold(tmp_path):
    token = evidence(tmp_path, NOW - timedelta(seconds=61))
    result = diagnose_freshness(token_path=token, archive_root=tmp_path, now=NOW, max_input_age_seconds=60)
    assert result.any_stale


def test_previous_session_token_does_not_prove_login(tmp_path):
    token = evidence(tmp_path)
    token.write_text(json.dumps({'access_token': 'secret', 'saved_date_ist': '2026-09-20'}))
    result = diagnose_freshness(token_path=token, archive_root=tmp_path, now=NOW)
    assert result.channels[0].state.value == 'MISSING'
