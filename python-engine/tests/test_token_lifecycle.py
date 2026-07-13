"""
[ROADMAP-2.1 2026-07-12] Kite token lifecycle tests.

Three surfaces:
  1. GET /token/current -- serves node-gateway's boot-time re-arm from
     the persisted same-IST-day token; same auth gate as POST /token.
  2. _token_recon_mismatch_message -- the pure decision behind the
     15-min scans-vs-execution reconciliation cron.
  3. KiteClient._maybe_alert_invalid_token -- the once-per-hour dedupe
     that turns a 26k-line HTTP-400 storm into ONE operator page.
"""
import json
import time
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import main as main_module
from config import settings
from main import app, _token_recon_mismatch_message


@pytest_asyncio.fixture
async def client(db_path, monkeypatch):
    """Async client with DB_PATH pointed at tmp so the token cache file
    (dirname(DB_PATH)/kite_token.json) is test-local."""
    monkeypatch.setattr(settings, "DB_PATH", db_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _write_token_file(db_path: str, token: str, saved_date_ist: str) -> None:
    import os
    path = os.path.join(os.path.dirname(db_path), "kite_token.json")
    with open(path, "w") as fh:
        json.dump({"access_token": token, "saved_date_ist": saved_date_ist}, fh)


# ===============================================================
# GET /token/current
# ===============================================================

class TestTokenCurrentEndpoint:
    @pytest.mark.asyncio
    async def test_rejected_without_secret(self, client):
        resp = await client.get("/token/current")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_rejected_with_wrong_secret(self, client):
        resp = await client.get(
            "/token/current", headers={"X-Internal-Secret": "wrong-secret"}
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_not_armed_when_no_persisted_token(self, client):
        resp = await client.get(
            "/token/current",
            headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
        )
        assert resp.status_code == 200
        assert resp.json() == {"armed": False}

    @pytest.mark.asyncio
    async def test_serves_same_day_token(self, client, db_path):
        today_ist = datetime.now(main_module.IST).strftime("%Y-%m-%d")
        _write_token_file(db_path, "fresh_token_abcd", today_ist)
        resp = await client.get(
            "/token/current",
            headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
        )
        assert resp.status_code == 200
        assert resp.json() == {"armed": True, "access_token": "fresh_token_abcd"}

    @pytest.mark.asyncio
    async def test_stale_token_not_served(self, client, db_path):
        """Yesterday's token must NOT re-arm node -- serving it would
        recreate the 2026-07-09 HTTP-400 storm on the execution side."""
        _write_token_file(db_path, "yesterdays-token", "2020-01-01")
        resp = await client.get(
            "/token/current",
            headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
        )
        assert resp.status_code == 200
        assert resp.json() == {"armed": False}


# ===============================================================
# Reconciliation decision (pure)
# ===============================================================

class TestTokenReconDecision:
    def test_both_armed_is_silent(self):
        """The healthy case, and the ONLY kind of agreement that is silent."""
        assert _token_recon_mismatch_message(True, "active") is None

    def test_both_unarmed_is_NOT_silent(self):
        """[OUTAGE-2026-07-13 DEFECT 3] CONTRACT CHANGE, and this test used to
        assert the bug.

        It previously read:

            assert _token_recon_mismatch_message(False, "none") is None
            assert _token_recon_mismatch_message(False, "expired") is None

        i.e. it pinned "both sides dead" as an acceptable, silent state -- under
        a test named `test_agreement_is_silent`. On 2026-07-13 that is exactly
        what happened: python unarmed, node "expired", False == False, no alert.
        Every 15 minutes, for six hours of market time, while the engine scanned
        nothing and the operator had no idea.

        Both-unarmed is not agreement. It is the single loudest thing this cron
        can observe: the system is not trading.
        """
        for node_status in ("none", "expired"):
            msg = _token_recon_mismatch_message(False, node_status)
            assert msg is not None, (
                f"both sides unarmed (node={node_status!r}) produced no alert"
            )
            assert "NOT TRADING" in msg

    def test_scans_armed_execution_disarmed_alerts(self):
        """The 2026-07-09 split-brain: node restarted mid-day, EXEC
        buttons dead, scans kept running. Must page."""
        for node_status in ("none", "expired"):
            msg = _token_recon_mismatch_message(True, node_status)
            assert msg is not None
            assert "DISARMED" in msg

    def test_execution_armed_scans_disarmed_alerts(self):
        msg = _token_recon_mismatch_message(False, "active")
        assert msg is not None
        assert "NO token" in msg

    def test_unknown_node_state_is_not_our_alert(self):
        """Node unreachable is healthcheck (roadmap 2.2) territory --
        the recon probe must not page on it."""
        assert _token_recon_mismatch_message(True, None) is None
        assert _token_recon_mismatch_message(False, None) is None


# ===============================================================
# Invalid-token alarm dedupe (kite_client)
# ===============================================================

class TestInvalidTokenAlarmDedupe:
    def test_second_call_within_window_is_deduped(self, monkeypatch):
        from kite_client import KiteClient

        monkeypatch.setattr(
            KiteClient, "_invalid_token_alert_last_monotonic", None
        )
        kc = KiteClient.__new__(KiteClient)  # helper touches class state only

        kc._maybe_alert_invalid_token()
        first = KiteClient._invalid_token_alert_last_monotonic
        assert first is not None

        kc._maybe_alert_invalid_token()
        assert KiteClient._invalid_token_alert_last_monotonic == first

    def test_realerts_after_window_expires(self, monkeypatch):
        from kite_client import KiteClient

        expired = (
            time.monotonic()
            - KiteClient.INVALID_TOKEN_ALERT_MIN_INTERVAL_SEC
            - 1.0
        )
        monkeypatch.setattr(
            KiteClient, "_invalid_token_alert_last_monotonic", expired
        )
        kc = KiteClient.__new__(KiteClient)

        kc._maybe_alert_invalid_token()
        assert KiteClient._invalid_token_alert_last_monotonic > expired

    def test_sync_context_never_raises(self, monkeypatch):
        """Called from get_quote's error path -- must be safe even with
        no running event loop (the Telegram hop is simply skipped)."""
        from kite_client import KiteClient

        monkeypatch.setattr(
            KiteClient, "_invalid_token_alert_last_monotonic", None
        )
        KiteClient.__new__(KiteClient)._maybe_alert_invalid_token()
