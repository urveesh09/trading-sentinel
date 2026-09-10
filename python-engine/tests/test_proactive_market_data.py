from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from proactive_market_data import CompletedBarDataError, load_kite_completed_bar_snapshot, load_recorded_completed_bar_snapshot


FIXTURE = Path(__file__).parent / "fixtures" / "proactive_completed_bars_recorded_v1.json"


def test_recorded_completed_bar_provider_preserves_completed_only_bars_and_provenance():
    snapshot = load_recorded_completed_bar_snapshot(
        FIXTURE, as_of=datetime(2026, 9, 7, 10, tzinfo=timezone.utc), max_age=timedelta(minutes=15),
    )
    assert len(snapshot.decision_bars["NSE:DEMO"]) == 2
    assert snapshot.outcome_bars == snapshot.decision_bars
    assert snapshot.provenance["instrument_mapping"] == {"NSE:DEMO": "12345"}
    assert snapshot.provenance["adjustment_version"] == "raw-cash-v1"
    assert len(snapshot.provenance["dataset_sha256"]) == 64


@pytest.mark.parametrize("replacement, message", [
    ('"received_at": "2026-09-07T09:00:00+00:00"', "stale"),
    ('"adjustment_version": "raw-cash-v1"', '"adjustment_version": ""'),
])
def test_recorded_completed_bar_provider_rejects_stale_or_unversioned_data(tmp_path, replacement, message):
    content = FIXTURE.read_text(encoding="utf-8")
    if message == "stale":
        content = content.replace('"received_at": "2026-09-07T10:00:00+00:00"', replacement)
    else:
        content = content.replace(replacement, message)
    path = tmp_path / "invalid.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(CompletedBarDataError):
        load_recorded_completed_bar_snapshot(
            path, as_of=datetime(2026, 9, 7, 10, tzinfo=timezone.utc), max_age=timedelta(minutes=15),
        )


def test_recorded_completed_bar_provider_rejects_duplicate_timestamps(tmp_path):
    content = FIXTURE.read_text(encoding="utf-8").replace(
        '"2026-09-07T09:15:00+00:00"', '"2026-09-07T09:30:00+00:00"',
    )
    path = tmp_path / "duplicate.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(CompletedBarDataError, match="duplicate or unordered"):
        load_recorded_completed_bar_snapshot(
            path, as_of=datetime(2026, 9, 7, 10, tzinfo=timezone.utc), max_age=timedelta(minutes=15),
        )


def test_recorded_completed_bar_provider_rejects_bar_after_capture(tmp_path):
    content = FIXTURE.read_text(encoding="utf-8").replace(
        '"2026-09-07T09:30:00+00:00"', '"2026-09-07T10:15:00+00:00"', 1,
    )
    path = tmp_path / "lookahead.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(CompletedBarDataError, match="after received_at"):
        load_recorded_completed_bar_snapshot(
            path, as_of=datetime(2026, 9, 7, 10, tzinfo=timezone.utc), max_age=timedelta(minutes=15),
        )


def test_recorded_completed_bar_provider_retains_corporate_action_adjustment_version(tmp_path):
    content = FIXTURE.read_text(encoding="utf-8").replace("raw-cash-v1", "split-adjusted-v2")
    path = tmp_path / "adjusted.json"
    path.write_text(content, encoding="utf-8")
    snapshot = load_recorded_completed_bar_snapshot(
        path, as_of=datetime(2026, 9, 7, 10, tzinfo=timezone.utc), max_age=timedelta(minutes=15),
    )
    assert snapshot.provenance["adjustment_version"] == "split-adjusted-v2"


@pytest.mark.asyncio
async def test_kite_completed_bar_source_excludes_current_candle_and_preserves_token_provenance():
    import pandas as pd
    as_of = datetime(2026, 9, 10, 5, 32, tzinfo=timezone.utc)
    class Kite:
        access_token = "present"
        async def get_intraday_by_token(self, token, _start, _end, _interval):
            return pd.DataFrame([
                {"date": "2026-09-10T05:20:00+00:00", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 10},
                {"date": "2026-09-10T05:30:00+00:00", "open": 101, "high": 103, "low": 100, "close": 102, "volume": 11},
            ])
    snapshot = await load_kite_completed_bar_snapshot(Kite(), instruments={"NIFTY": 256265}, as_of=as_of, max_age=timedelta(minutes=10))
    assert len(snapshot.decision_bars["NIFTY"]) == 1
    assert snapshot.decision_bars["NIFTY"][0]["timestamp"] == "2026-09-10T05:25:00+00:00"
    assert snapshot.provenance["source_kind"] == "KITE_COMPLETED_BARS_V1"
    assert snapshot.provenance["instrument_mapping"] == {"NIFTY": "256265"}
