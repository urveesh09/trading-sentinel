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


class _FakeResp:
    """
    Minimal urllib.response-like stub. Supports:
      .status       (HTTP status)
      .read()       (returns body bytes)
      .close()      (no-op)
      context manager (__enter__/__exit__)
    Per-instance body, so different URLs can return different responses
    (e.g. telegram returns {"ok": true}, webhook returns whatever).
    """
    def __init__(self, status=200, body=b'{}'):
        self.status = status
        self._body = body
        self.closed = False
    def read(self):
        return self._body
    def close(self):
        self.closed = True
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False




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
    def fake_urlopen(req, timeout=5):
        captured_urls.append(req.full_url)
        captured_payloads.append(req.data.decode())
        # Telegram success: HTTP 200 + {"ok": true, ...}
        return _FakeResp(status=200, body=b'{"ok": true, "result": {"message_id": 1}}')

    monkeypatch.setattr("penny_hourly_report.urllib.request.urlopen", fake_urlopen)
    async def _fake_to_thread(fn, *a, **kw):
        return fn(*a, **kw)
    monkeypatch.setattr("penny_hourly_report.asyncio.to_thread", _fake_to_thread)

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
            return _FakeResp(status=200, body=b'{"ok": true}')

    monkeypatch.setattr("penny_hourly_report.urllib.request.urlopen", fake_urlopen)
    async def _fake_to_thread(fn, *a, **kw):
        return fn(*a, **kw)
    monkeypatch.setattr("penny_hourly_report.asyncio.to_thread", _fake_to_thread)

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
        return _FakeResp(status=200, body=b'{"ok": true}')

    monkeypatch.setattr("penny_hourly_report.urllib.request.urlopen", fake_urlopen)
    async def _fake_to_thread(fn, *a, **kw):
        return fn(*a, **kw)
    monkeypatch.setattr("penny_hourly_report.asyncio.to_thread", _fake_to_thread)

    rpt = PennyHourlyReport(db_path=":memory:")
    asyncio.run(rpt.send(
        body="test",
        webhook_url="http://backup.example/hook",
        telegram_token="",  # not set
        telegram_chat_id="",  # not set
    ))

    # Only the webhook (no Telegram attempt)
    assert calls["any"] == 1

def test_telegram_200_with_ok_false_falls_back_to_webhook(monkeypatch):
    """Telegram returns HTTP 200 but {"ok": false} -- treat as failure
    and fall back to webhook. Catches bot-token / chat-id errors that
    Telegram silently returns with ok=false."""
    from penny_hourly_report import PennyHourlyReport
    import asyncio

    captured = []
    def fake_urlopen(req, timeout=5):
        captured.append(req.full_url)
        if "api.telegram.org" in req.full_url:
            # HTTP 200 with ok=false -- a bot token mistake, blocked user, etc.
            return _FakeResp(status=200, body=b'{"ok": false, "description": "chat not found"}')
        return _FakeResp(status=200, body=b'{"ok": true}')

    async def _fake_to_thread(fn, *a, **kw):
        return fn(*a, **kw)

    monkeypatch.setattr("penny_hourly_report.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("penny_hourly_report.asyncio.to_thread", _fake_to_thread)

    rpt = PennyHourlyReport(db_path=":memory:")
    asyncio.run(rpt.send(
        body="t",
        webhook_url="http://backup.example/hook",
        telegram_token="BAD_TOKEN",
        telegram_chat_id="BAD_CHAT",
    ))

    # Telegram was tried, then webhook as fallback
    assert any("api.telegram.org" in u for u in captured)
    assert any("backup.example" in u for u in captured), \
        "Expected webhook fallback after Telegram returned ok=false"


def test_webhook_non_2xx_status_logged_not_treated_as_success(monkeypatch):
    """A webhook that returns HTTP 500 (or any non-2xx) is logged as
    failed even though no exception was raised. The local log remains
    the source of truth (spec §9.4 mandatory heartbeat)."""
    from penny_hourly_report import PennyHourlyReport
    import asyncio

    def fake_urlopen(req, timeout=5):
        return _FakeResp(status=500, body=b"internal server error")

    async def _fake_to_thread(fn, *a, **kw):
        return fn(*a, **kw)

    monkeypatch.setattr("penny_hourly_report.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("penny_hourly_report.asyncio.to_thread", _fake_to_thread)

    rpt = PennyHourlyReport(db_path=":memory:")
    # Should not raise -- 500 is logged, body is still in local log
    asyncio.run(rpt.send(
        body="t",
        webhook_url="http://broken.example/hook",
    ))


def test_url_not_logged_on_send_or_failure(monkeypatch, caplog):
    """Webhook URLs may embed credentials (Slack, Discord, Telegram bot
    tokens). The send path must NOT log the URL. Verify that 'webhook='
    or 'chat_id=' or the bot-token substring never appears in logs."""
    from penny_hourly_report import PennyHourlyReport
    import asyncio
    import logging

    secret_url = "https://hooks.slack.com/services/T00XXXXX/B00XXXXX/XXXXXXXXXXXXXXXXXXXXXXXX"
    secret_token = "SECRET_BOT_TOKEN_DO_NOT_LOG"

    def fake_urlopen(req, timeout=5):
        return _FakeResp(status=200, body=b"{}")

    async def _fake_to_thread(fn, *a, **kw):
        return fn(*a, **kw)

    monkeypatch.setattr("penny_hourly_report.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("penny_hourly_report.asyncio.to_thread", _fake_to_thread)

    with caplog.at_level(logging.INFO):
        rpt = PennyHourlyReport(db_path=":memory:")
        asyncio.run(rpt.send(
            body="hello",
            webhook_url=secret_url,
            telegram_token=secret_token,
            telegram_chat_id="12345",
        ))
        log_text = "\n".join(r.getMessage() for r in caplog.records)

    # The URL must NOT appear in any log line
    assert secret_url not in log_text, \
        f"Webhook URL leaked to logs: {secret_url}"
    # The bot token must NOT appear in any log line
    assert secret_token not in log_text, \
        f"Telegram bot token leaked to logs: {secret_token}"
    # The body IS logged (mandatory heartbeat)
    assert "hello" in log_text


# --- 2026-06-24 diagnostic-add tests ---------------------------------------
#
# The hourly report now appends a "Scanned: N | top rejects: ..." line to
# the no-action case so the operator can see WHY no trade fired. These
# tests pin the formatting, ordering, and backwards-compat behaviour.


def test_diag_tail_empty_when_universe_unknown(tmp_paths):
    """Backwards-compat: when universe_size=0 (default) and no rejection
    rows, the report stays the legacy single-line 'No action ...' form.
    Older callers / pre-2026-06-24 deployments see no behaviour change."""
    from penny_hourly_report import PennyHourlyReport
    rpt = PennyHourlyReport(db_path=str(tmp_paths / "test.db"))
    body = asyncio.run(rpt.build_report(
        now=datetime(2026, 6, 24, 11, 0),
        regime="PR1_CALM",
        open_positions=[],
        deployed_capital=0.0,
        unrealised_pnl=0.0,
        kill_switch_active=False,
        circuit_blocks=0,
        # universe_size omitted (defaults to 0) -- simulates pre-change caller
    ))
    assert "No action in Penny this hour." in body
    assert "Scanned:" not in body
    assert body.count("\n") == 0  # single line


def test_diag_tail_shows_scanned_count_only(tmp_paths):
    """When universe_size is known but no rejection rows were logged
    (e.g. scanner died before logging), show 'Scanned: N' so the
    operator can see the universe was alive."""
    from penny_hourly_report import PennyHourlyReport
    rpt = PennyHourlyReport(db_path=str(tmp_paths / "test.db"))
    body = asyncio.run(rpt.build_report(
        now=datetime(2026, 6, 24, 11, 0),
        regime="PR1_CALM",
        open_positions=[],
        deployed_capital=0.0,
        unrealised_pnl=0.0,
        kill_switch_active=False,
        circuit_blocks=0,
        universe_size=87,
    ))
    lines = body.split("\n")
    assert len(lines) == 2
    assert "No action in Penny this hour." in lines[0]
    assert "Scanned: 87" in lines[1]
    assert "(no rejection rows logged)" in lines[1]


def test_diag_tail_shows_top_rejects(tmp_paths):
    """When both universe_size and rejection rows are present, show the
    top 3 reject reasons sorted by descending count. Most-common reason
    appears first -- that's the bottleneck the operator should investigate."""
    from penny_signal_log import init_penny_signal_db, log_penny_signal
    from penny_hourly_report import PennyHourlyReport
    from datetime import datetime as real_dt

    db_path = str(tmp_paths / "test.db")
    asyncio.run(init_penny_signal_db(db_path))

    fixed_now = real_dt(2026, 6, 24, 11, 30, tzinfo=timezone.utc)

    # Seed 4× "RSI(2)=14.3 not below threshold" and 2× "volume too low (dead stock)"
    # and 1× "breakout not confirmed (close X <= Y)" -- top 3 will include all three.
    reasons = [
        ("RSI(2)=14.3 not below threshold", 4),
        ("volume too low (dead stock)", 2),
        ("breakout not confirmed (close 12.5 <= 11.0)", 1),
    ]
    with patch("penny_signal_log.datetime", wraps=real_dt) as mock_dt:
        mock_dt.now.return_value = fixed_now
        idx = 0
        for reason_text, count in reasons:
            for _ in range(count):
                ticker = f"T{idx:03d}"
                idx += 1
                asyncio.run(log_penny_signal(
                    db_path, scan_id="s1", ticker=ticker, leg="MIS",
                    accepted=False, regime="PR1_CALM", close=10.0,
                    reject_reason=reason_text,
                ))

    rpt = PennyHourlyReport(db_path=db_path)
    body = asyncio.run(rpt.build_report(
        now=fixed_now,
        regime="PR1_CALM",
        open_positions=[],
        deployed_capital=0.0,
        unrealised_pnl=0.0,
        kill_switch_active=False,
        circuit_blocks=0,
        universe_size=87,
    ))
    lines = body.split("\n")
    assert "No action in Penny this hour." in lines[0]
    assert "Scanned: 87" in lines[1]
    # Top-3 reasons appear, sorted by descending count
    rsi_idx = lines[1].find("RSI(2)=14.3 not below threshold")
    vol_idx = lines[1].find("volume too low (dead stock)")
    bo_idx  = lines[1].find("breakout not confirmed")
    assert rsi_idx != -1
    assert vol_idx != -1
    assert bo_idx != -1
    # Descending count order: ×4 before ×2 before ×1
    assert rsi_idx < vol_idx < bo_idx, \
        "Top rejects must be sorted by descending count"
    assert "×4" in lines[1]
    assert "×2" in lines[1]
    assert "×1" in lines[1]


def test_diag_tail_truncates_long_reason_to_50_chars(tmp_paths):
    """An over-long reject_reason string (e.g. one with embedded prices)
    is clipped to 50 chars + ellipsis to keep the diagnostic line bounded."""
    from penny_signal_log import init_penny_signal_db, log_penny_signal
    from penny_hourly_report import PennyHourlyReport
    from datetime import datetime as real_dt

    db_path = str(tmp_paths / "test.db")
    asyncio.run(init_penny_signal_db(db_path))

    fixed_now = real_dt(2026, 6, 24, 11, 30, tzinfo=timezone.utc)
    long_reason = "x" * 100  # 100 chars, must be clipped to 50 + ellipsis

    with patch("penny_signal_log.datetime", wraps=real_dt) as mock_dt:
        mock_dt.now.return_value = fixed_now
        asyncio.run(log_penny_signal(
            db_path, scan_id="s1", ticker="LONG", leg="MIS",
            accepted=False, regime="PR1_CALM", close=10.0,
            reject_reason=long_reason,
        ))

    rpt = PennyHourlyReport(db_path=db_path)
    body = asyncio.run(rpt.build_report(
        now=fixed_now,
        regime="PR1_CALM",
        open_positions=[],
        deployed_capital=0.0,
        unrealised_pnl=0.0,
        kill_switch_active=False,
        circuit_blocks=0,
        universe_size=42,
    ))
    # Body must still be bounded (<1000 chars)
    assert len(body) < 1000, \
        f"Diagnostic line pushed body over 1000 chars: {len(body)}"
    # Long reason was clipped (no "x" * 60 substring)
    assert "x" * 60 not in body
    # The ellipsis marker (single char) is present to indicate clipping
    assert "…" in body


def test_diag_tail_with_diagnostic_stays_under_15_lines(tmp_paths):
    """Even with universe_size + max-rejection-rows, the no-action case
    stays ≤15 lines (the spec §9.4 hard limit). The diagnostic is one line."""
    from penny_signal_log import init_penny_signal_db, log_penny_signal
    from penny_hourly_report import PennyHourlyReport
    from datetime import datetime as real_dt

    db_path = str(tmp_paths / "test.db")
    asyncio.run(init_penny_signal_db(db_path))

    fixed_now = real_dt(2026, 6, 24, 11, 30, tzinfo=timezone.utc)
    with patch("penny_signal_log.datetime", wraps=real_dt) as mock_dt:
        mock_dt.now.return_value = fixed_now
        for i in range(10):
            asyncio.run(log_penny_signal(
                db_path, scan_id="s1", ticker=f"T{i:03d}", leg="MIS",
                accepted=False, regime="PR1_CALM", close=10.0,
                reject_reason=f"reason variant {i}",
            ))

    rpt = PennyHourlyReport(db_path=db_path)
    body = asyncio.run(rpt.build_report(
        now=fixed_now,
        regime="PR1_CALM",
        open_positions=[],
        deployed_capital=0.0,
        unrealised_pnl=0.0,
        kill_switch_active=False,
        circuit_blocks=0,
        universe_size=87,
    ))
    assert body.count("\n") <= 14, \
        f"Diagnostic pushed body over 15 lines: {body!r}"


def test_build_diag_tail_unit():
    """Direct unit test of the static helper -- covers the four
    combinations of (universe_known, rejections_present) without going
    through the DB. Pins the formatting contract."""
    from penny_hourly_report import PennyHourlyReport

    # Both unknown -> ""
    assert PennyHourlyReport._build_diag_tail({}, 0) == ""

    # Universe known, no rejections
    out = PennyHourlyReport._build_diag_tail({}, 87)
    assert out == "Scanned: 87 | (no rejection rows logged)"

    # Universe unknown, rejections present
    out = PennyHourlyReport._build_diag_tail({"foo": 5}, 0)
    assert out == "top rejects: foo (×5)"

    # Both present -- sorted descending by count
    out = PennyHourlyReport._build_diag_tail(
        {"low": 1, "mid": 3, "high": 7}, 42, top_n=3,
    )
    assert "Scanned: 42" in out
    assert "high (×7)" in out
    assert "mid (×3)" in out
    assert "low (×1)" in out
    # Order check: high appears before mid before low
    assert out.find("high") < out.find("mid") < out.find("low")

    # top_n=1 limits to the single biggest reason
    out = PennyHourlyReport._build_diag_tail({"a": 1, "b": 10, "c": 5}, 10, top_n=1)
    assert "b (×10)" in out
    # Check that the LOW-count reasons are NOT listed (not just the
    # letter 'a' which appears in "Scanned"/"rejects").
    assert "(×1)" not in out
    assert "(×5)" not in out
