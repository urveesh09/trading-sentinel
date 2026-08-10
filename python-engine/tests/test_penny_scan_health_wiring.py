from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_successful_scan_sets_aware_last_scan_timestamp(monkeypatch):
    import main

    scanner = MagicMock()
    scanner.scan_once = AsyncMock(return_value={"accept": 0, "reject": 1, "error": 0})
    scanner._load_universe.return_value = [{}]
    scanner.kite.instrument_cache = {"AAA": 1}
    scanner.regime = "PR1_CALM"
    monkeypatch.setattr(main, "_last_penny_scan_at", None)
    monkeypatch.setattr(main.kite, "access_token", "token")
    monkeypatch.setattr(main, "_within_penny_market_hours", lambda now: True)
    monkeypatch.setattr(main, "is_trading_day", AsyncMock(return_value=True))
    monkeypatch.setattr(main, "_get_penny_scanner", lambda: scanner)

    await main.run_penny_scanner_once()
    assert main._last_penny_scan_at is not None
    assert main._last_penny_scan_at.tzinfo is not None
    assert main._last_penny_scan_at.utcoffset() == timedelta(0)


@pytest.mark.asyncio
async def test_failed_scan_does_not_set_last_scan_timestamp(monkeypatch):
    import main

    scanner = MagicMock()
    scanner.scan_once = AsyncMock(side_effect=RuntimeError("scan failed"))
    monkeypatch.setattr(main, "_last_penny_scan_at", None)
    monkeypatch.setattr(main.kite, "access_token", "token")
    monkeypatch.setattr(main, "_within_penny_market_hours", lambda now: True)
    monkeypatch.setattr(main, "is_trading_day", AsyncMock(return_value=True))
    monkeypatch.setattr(main, "_get_penny_scanner", lambda: scanner)

    await main.run_penny_scanner_once()
    assert main._last_penny_scan_at is None


@pytest.mark.asyncio
async def test_health_reports_never_stale_and_recent_healthy(monkeypatch, db_path):
    import main
    from penny_health import build_health_snapshot

    monkeypatch.setattr(main, "_penny_regime_engine", None)
    monkeypatch.setattr(main, "last_run", datetime.now(timezone.utc))
    monkeypatch.setattr(main, "_last_penny_scan_at", None)
    never = await build_health_snapshot(db_path, penny_source="PENNY_PAPER")
    assert never["penny"]["last_scan_at"] is None
    assert never["penny"]["last_scan_age"] == "never"
    assert never["penny"]["is_stale"] is True

    monkeypatch.setattr(
        main, "_last_penny_scan_at",
        datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    recent = await build_health_snapshot(db_path, penny_source="PENNY_PAPER")
    assert recent["penny"]["last_scan_at"] is not None
    assert recent["penny"]["last_scan_age"] == "5 min ago"
    assert recent["penny"]["is_stale"] is False

    monkeypatch.setattr(
        main, "_last_penny_scan_at",
        datetime.now(timezone.utc) - timedelta(hours=25),
    )
    stale = await build_health_snapshot(db_path, penny_source="PENNY_PAPER")
    assert stale["penny"]["is_stale"] is True


def test_sync_health_command_uses_current_paper_source(monkeypatch, db_path):
    import penny_health
    import main
    from config import settings

    captured = []

    async def fake_snapshot(path, penny_source="PENNY"):
        captured.append(penny_source)
        return {
            "overall_status": "OK", "halted": False, "halt_reasons": [],
            "penny": {
                "regime": "PR1_CALM", "last_regime_age": "today",
                "last_scan_age": "just now", "open_positions": 0,
                "is_stale": False,
            },
            "nifty": {
                "market_regime": "BULL", "last_swing_scan_age": "just now",
                "open_positions": 0, "is_stale": False,
            },
            "security": {"internal_api_secret_configured": True},
            "bankroll": {"penny": 100000.0, "nifty": 5000.0},
        }

    monkeypatch.setattr(settings, "PENNY_LIVE_TRADING", False)
    monkeypatch.setattr(main, "_penny_scanner", None)
    monkeypatch.setattr(penny_health, "build_health_snapshot", fake_snapshot)
    output = penny_health.cmd_health(db_path)
    assert captured == ["PENNY_PAPER"]
    assert output.startswith("System health: OK")
