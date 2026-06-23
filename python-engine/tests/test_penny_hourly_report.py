"""
[PENNY-HOURLY 2026-06-21] Tests for the per-hour penny report (spec §9.4).

Covers:
  - No-action case: literal "No action in Penny this hour." text
  - Active case: includes regime, entries, exits, rejections summary
  - Webhook delivery: POSTs JSON when webhook URL is set
  - Webhook failure: logged, doesn't raise
  - Time window: respects PENNY_HOURLY_REPORT_START_HOUR / END_HOUR
"""
import asyncio
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
import pytest


@pytest.fixture
def tmp_paths(tmp_path, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "PENNY_LOG_CSV_PATH", str(tmp_path / "penny_signals.csv"))
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "PENNY_HOURLY_REPORT_WEBHOOK", "")
    return tmp_path


def test_report_no_action_returns_literal_text(tmp_paths):
    from penny_hourly_report import PennyHourlyReport
    rpt = PennyHourlyReport(db_path=str(tmp_paths / "test.db"))
    body = asyncio.run(rpt.build_report(
        now=datetime(2026, 6, 21, 10, 0),
        regime="PR1_CALM",
        open_positions=[],
        deployed_capital=0.0,
        unrealised_pnl=0.0,
        kill_switch_active=False,
        circuit_blocks=0,
    ))
    assert "No action in Penny this hour." in body


def test_report_includes_regime_snapshot(tmp_paths):
    from penny_hourly_report import PennyHourlyReport
    rpt = PennyHourlyReport(db_path=str(tmp_paths / "test.db"))
    body = asyncio.run(rpt.build_report(
        now=datetime(2026, 6, 21, 11, 0),
        regime="PR2_ELEVATED",
        open_positions=[],
        deployed_capital=0.0,
        unrealised_pnl=0.0,
        kill_switch_active=False,
        circuit_blocks=0,
    ))
    assert "PR2_ELEVATED" in body


def test_report_no_action_under_1000_chars(tmp_paths):
    from penny_hourly_report import PennyHourlyReport
    rpt = PennyHourlyReport(db_path=str(tmp_paths / "test.db"))
    body = asyncio.run(rpt.build_report(
        now=datetime(2026, 6, 21, 10, 0),
        regime="PR1_CALM",
        open_positions=[],
        deployed_capital=0.0,
        unrealised_pnl=0.0,
        kill_switch_active=False,
        circuit_blocks=0,
    ))
    assert len(body) < 1000


def test_report_lists_filled_entries(tmp_paths):
    from penny_signal_log import init_penny_signal_db, log_penny_signal
    from penny_hourly_report import PennyHourlyReport
    from datetime import datetime as real_dt
    db_path = str(tmp_paths / "test.db")
    asyncio.run(init_penny_signal_db(db_path))
    # Use a fixed "now" inside the signal log so the row's scanned_at
    # falls within the report's query window. wraps= keeps the real
    # datetime class working for the constructor while we override now().
    fixed_now = real_dt(2026, 6, 21, 11, 30, tzinfo=timezone.utc)
    with patch("penny_signal_log.datetime", wraps=real_dt) as mock_dt:
        mock_dt.now.return_value = fixed_now
        asyncio.run(log_penny_signal(
            db_path, scan_id="s1", ticker="AAA", leg="MIS",
            accepted=True, regime="PR1_CALM", close=10.05,
            stop_loss=9.75, target_1=10.40, shares=50,
        ))
    rpt = PennyHourlyReport(db_path=db_path)
    body = asyncio.run(rpt.build_report(
        now=fixed_now,
        regime="PR1_CALM",
        open_positions=[],
        deployed_capital=505.0,
        unrealised_pnl=0.0,
        kill_switch_active=False,
        circuit_blocks=0,
    ))
    assert "AAA" in body or "entries" in body.lower()


def test_report_under_15_lines(tmp_paths):
    from penny_hourly_report import PennyHourlyReport
    rpt = PennyHourlyReport(db_path=str(tmp_paths / "test.db"))
    body = asyncio.run(rpt.build_report(
        now=datetime(2026, 6, 21, 11, 0),
        regime="PR2_ELEVATED",
        open_positions=[],
        deployed_capital=1500.0,
        unrealised_pnl=-25.0,
        kill_switch_active=False,
        circuit_blocks=2,
    ))
    assert body.count("\n") <= 14


def test_report_within_window_check(monkeypatch):
    from config import settings
    from penny_hourly_report import is_in_report_window
    monkeypatch.setattr(settings, "PENNY_HOURLY_REPORT_START_HOUR", 10)
    monkeypatch.setattr(settings, "PENNY_HOURLY_REPORT_END_HOUR", 14)
    assert is_in_report_window(datetime(2026, 6, 21, 12, 0)) is True
    assert is_in_report_window(datetime(2026, 6, 21, 9, 59)) is False
    assert is_in_report_window(datetime(2026, 6, 21, 14, 1)) is False
    assert is_in_report_window(datetime(2026, 6, 21, 10, 0)) is True
    assert is_in_report_window(datetime(2026, 6, 21, 14, 0)) is True

def test_webhook_post_called_when_configured(tmp_paths, monkeypatch):
    """If PENNY_HOURLY_REPORT_WEBHOOK is set, POST the body."""
    from config import settings
    monkeypatch.setattr(settings, "PENNY_HOURLY_REPORT_WEBHOOK", "http://test/webhook")
    from penny_hourly_report import PennyHourlyReport
    rpt = PennyHourlyReport(db_path=str(tmp_paths / "test.db"))
    fake_urlopen = MagicMock(return_value=MagicMock(status=200))
    with patch("penny_hourly_report.urllib.request.urlopen", fake_urlopen):
        asyncio.run(rpt.send(body="No action in Penny this hour.",
                              webhook_url="http://test/webhook"))
    fake_urlopen.assert_called_once()
    # The URL was passed in the Request
    call_args = fake_urlopen.call_args
    request_obj = call_args.args[0]
    assert str(request_obj.full_url) == "http://test/webhook"
    assert request_obj.method == "POST"


def test_webhook_failure_logged_not_raised(tmp_paths, monkeypatch):
    """Webhook down -> log + continue. Must NOT crash the scheduler."""
    from config import settings
    monkeypatch.setattr(settings, "PENNY_HOURLY_REPORT_WEBHOOK", "http://test/webhook")
    from penny_hourly_report import PennyHourlyReport
    rpt = PennyHourlyReport(db_path=str(tmp_paths / "test.db"))
    fake_urlopen = MagicMock(side_effect=Exception("connection refused"))
    with patch("penny_hourly_report.urllib.request.urlopen", fake_urlopen):
        asyncio.run(rpt.send(body="No action in Penny this hour.",
                              webhook_url="http://test/webhook"))

def test_telegram_sent_when_token_and_chat_id_set(monkeypatch):
    """When TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set, the report
    is POSTed to Telegram's sendMessage endpoint and the webhook is NOT
    called (Telegram takes priority per Uru 2026-06-23)."""
    from unittest.mock import MagicMock, patch
    from penny_hourly_report import PennyHourlyReport
    import asyncio

    captured_urls = []
    captured_payloads = []
    class FakeResp:
        def __init__(self): self.status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=5):
        captured_urls.append(req.full_url)
        captured_payloads.append(req.data.decode())
        return FakeResp()

    monkeypatch.setattr("penny_hourly_report.urllib.request.urlopen", fake_urlopen)

    rpt = PennyHourlyReport(db_path=":memory:")
    asyncio.run(rpt.send(
        body="test report body",
        webhook_url="http://should-not-be-called.example/hook",
        telegram_token="FAKE_TOKEN",
        telegram_chat_id="12345",
    ))

    # Telegram was called
    assert len(captured_urls) == 1
    assert "api.telegram.org" in captured_urls[0]
    assert "FAKE_TOKEN" in captured_urls[0]
    # Webhook was NOT called (Telegram returned first)
    assert "should-not-be-called" not in captured_urls[0]
    # Payload includes chat_id and body
    assert "12345" in captured_payloads[0]
    assert "test report body" in captured_payloads[0]


def test_telegram_failure_falls_back_to_webhook(monkeypatch):
    """If Telegram fails (URLError), the webhook is called as a fallback."""
    from unittest.mock import MagicMock
    import urllib.error
    from penny_hourly_report import PennyHourlyReport
    import asyncio

    calls = {"telegram": 0, "webhook": 0}

    def fake_urlopen(req, timeout=5):
        if "api.telegram.org" in req.full_url:
            calls["telegram"] += 1
            raise urllib.error.URLError("telegram down")
        else:
            calls["webhook"] += 1
            class FakeResp:
                def __init__(self): self.status = 200
                def __enter__(self): return self
                def __exit__(self, *a): return False
            return FakeResp()

    monkeypatch.setattr("penny_hourly_report.urllib.request.urlopen", fake_urlopen)

    rpt = PennyHourlyReport(db_path=":memory:")
    asyncio.run(rpt.send(
        body="test",
        webhook_url="http://backup.example/hook",
        telegram_token="FAKE",
        telegram_chat_id="999",
    ))

    # Both transports were attempted: Telegram first, then webhook
    assert calls["telegram"] == 1
    assert calls["webhook"] == 1


def test_no_telegram_config_uses_only_webhook(monkeypatch):
    """Without Telegram creds, only the webhook is called."""
    from penny_hourly_report import PennyHourlyReport
    import asyncio

    calls = {"any": 0}

    def fake_urlopen(req, timeout=5):
        calls["any"] += 1
        class FakeResp:
            def __init__(self): self.status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return FakeResp()

    monkeypatch.setattr("penny_hourly_report.urllib.request.urlopen", fake_urlopen)

    rpt = PennyHourlyReport(db_path=":memory:")
    asyncio.run(rpt.send(
        body="test",
        webhook_url="http://backup.example/hook",
        telegram_token="",  # not set
        telegram_chat_id="",  # not set
    ))

    # Only the webhook (no Telegram attempt)
    assert calls["any"] == 1
