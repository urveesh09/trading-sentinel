"""
Tests for python-engine/main.py — FastAPI endpoints via TestClient.
Uses httpx.AsyncClient + app for async endpoint tests.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime
from httpx import AsyncClient, ASGITransport

from main import app, kite, state_lock, post_login_initialization
from config import settings
from performance import init_ledger
from position_tracker import init_positions_db


# ═══════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════

@pytest_asyncio.fixture
async def client(db_path, monkeypatch):
    """Provide an async test client with initialised test DB."""
    monkeypatch.setattr(settings, "DB_PATH", db_path)
    await init_positions_db(db_path)
    await init_ledger(db_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ═══════════════════════════════════════════════════════════════
# GET /health
# ═══════════════════════════════════════════════════════════════


class TestHealthEndpoint:

    @pytest.mark.asyncio
    async def test_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"

    @pytest.mark.asyncio
    async def test_no_auth_required(self, client):
        """Health endpoint is public — no token needed."""
        resp = await client.get("/health")
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════
# GET /signals
# ═══════════════════════════════════════════════════════════════


class TestSignalsEndpoint:

    @pytest.mark.asyncio
    async def test_returns_portfolio_response(self, client):
        resp = await client.get("/signals")
        assert resp.status_code == 200
        body = resp.json()
        assert "market_regime" in body
        assert "signals" in body
        assert "trading_halted" in body
        assert "backtest_gate" in body

    @pytest.mark.asyncio
    async def test_backtest_gate_value(self, client):
        """backtest_gate should be 'PASS' when no CB4 reason is set."""
        resp = await client.get("/signals")
        body = resp.json()
        # CB4 is commented out, so BACKTEST_GATE_FAILED should never appear
        assert body["backtest_gate"] == "PASS"

    @pytest.mark.asyncio
    async def test_signals_empty_initially(self, client):
        resp = await client.get("/signals")
        body = resp.json()
        assert body["signals"] == []

    @pytest.mark.asyncio
    async def test_remaining_slots(self, client):
        resp = await client.get("/signals")
        body = resp.json()
        assert body["remaining_slots"] == settings.MAX_OPEN_POSITIONS


# ═══════════════════════════════════════════════════════════════
# GET /performance
# ═══════════════════════════════════════════════════════════════


class TestPerformanceEndpoint:

    @pytest.mark.asyncio
    async def test_returns_performance_report(self, client):
        resp = await client.get("/performance")
        assert resp.status_code == 200
        body = resp.json()
        assert "total_trades_taken" in body
        assert "current_bankroll" in body
        assert "win_rate" in body

    @pytest.mark.asyncio
    async def test_zero_trades_initially(self, client):
        resp = await client.get("/performance")
        body = resp.json()
        assert body["total_trades_taken"] == 0
        assert body["win_count"] == 0
        assert body["loss_count"] == 0


# ═══════════════════════════════════════════════════════════════
# GET /positions
# ═══════════════════════════════════════════════════════════════


class TestPositionsEndpoint:

    @pytest.mark.asyncio
    async def test_empty_initially(self, client):
        resp = await client.get("/positions")
        assert resp.status_code == 200
        assert resp.json() == []


# ═══════════════════════════════════════════════════════════════
# GET /bankroll
# ═══════════════════════════════════════════════════════════════


class TestBankrollEndpoint:

    @pytest.mark.asyncio
    async def test_returns_initial_bankroll(self, client):
        resp = await client.get("/bankroll")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["bankroll"] == settings.INITIAL_BANKROLL


# ═══════════════════════════════════════════════════════════════
# GET /circuit-breaker
# ═══════════════════════════════════════════════════════════════


class TestCircuitBreakerEndpoint:

    @pytest.mark.asyncio
    async def test_not_halted_initially(self, client):
        resp = await client.get("/circuit-breaker")
        assert resp.status_code == 200
        body = resp.json()
        assert body["trading_halted"] is False
        assert body["halt_reasons"] == []


# ═══════════════════════════════════════════════════════════════
# POST /token  (triggers post_login_initialization)
# ═══════════════════════════════════════════════════════════════


class TestTokenEndpoint:

    @pytest.mark.asyncio
    async def test_token_injection(self, client):
        """POST /token should set the kite token and trigger init [Q4]."""
        with patch.object(kite, "set_token") as mock_set, \
             patch("main.post_login_initialization", new_callable=AsyncMock) as mock_init:
            resp = await client.post("/token", json={"access_token": "fake_token_123"})
            assert resp.status_code == 200
            mock_set.assert_called_once_with("fake_token_123")
            mock_init.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_token_field(self, client):
        """POST /token without access_token should fail."""
        resp = await client.post("/token", json={})
        assert resp.status_code in (400, 422, 500)


# ═══════════════════════════════════════════════════════════════
# POST /positions/manual  (internal API, requires secret)
# ═══════════════════════════════════════════════════════════════


class TestManualPositionEndpoint:

    @pytest.mark.asyncio
    async def test_valid_manual_position(self, client):
        resp = await client.post(
            "/positions/manual",
            json={
                "ticker": "TCS",
                "entry_price": 3500.0,
                "shares": 5,
                "source": "SYSTEM"
            },
            headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # Verify position appears in GET /positions
        resp2 = await client.get("/positions")
        positions = resp2.json()
        assert len(positions) == 1
        assert positions[0]["ticker"] == "TCS"

    @pytest.mark.asyncio
    async def test_unauthorized_without_secret(self, client):
        resp = await client.post(
            "/positions/manual",
            json={"ticker": "TCS", "entry_price": 3500.0, "shares": 5}
        )
        assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════
# POST /positions/close  (internal API, requires secret)
# ═══════════════════════════════════════════════════════════════


class TestClosePositionEndpoint:

    @pytest.mark.asyncio
    async def test_unauthorized_without_secret(self, client):
        resp = await client.post(
            "/positions/close",
            json={"ticker": "TCS", "exit_price": 3600.0}
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_close_nonexistent_position(self, client):
        resp = await client.post(
            "/positions/close",
            json={"ticker": "GHOST", "exit_price": 100.0},
            headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET}
        )
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════
# GET /momentum-signals
# ═══════════════════════════════════════════════════════════════


class TestMomentumSignalsEndpoint:

    @pytest.mark.asyncio
    async def test_returns_momentum_data(self, client):
        resp = await client.get("/momentum-signals")
        assert resp.status_code == 200
        body = resp.json()
        assert "momentum_pool" in body
        assert "signals" in body
        assert "trading_halted" in body


# ═══════════════════════════════════════════════════════════════
# POST /test-momentum
# ═══════════════════════════════════════════════════════════════


class TestMomentumTrigger:

    @pytest.mark.asyncio
    async def test_triggers_scan(self, client):
        """POST /test-momentum should return immediately (fires background task)."""
        with patch("main.run_momentum_screener", new_callable=AsyncMock):
            resp = await client.post("/test-momentum")
            assert resp.status_code == 200
            assert resp.json()["status"] == "momentum_scan_triggered"


# ═══════════════════════════════════════════════════════════════
# Q4: post_login_initialization calls run_screener + run_momentum_screener
# ═══════════════════════════════════════════════════════════════


class TestPostLoginInitQ4:

    @pytest.mark.asyncio
    async def test_calls_both_screeners(self):
        """[Q4] post_login_initialization must call run_screener AND run_momentum_screener."""
        with patch("main.kite") as mock_kite, \
             patch("main.run_screener", new_callable=AsyncMock) as mock_swing, \
             patch("main.run_momentum_screener", new_callable=AsyncMock) as mock_momentum, \
             patch("main.run_backtest", new_callable=AsyncMock):
            mock_kite.refresh_instrument_cache = AsyncMock()
            import pandas as pd
            mock_kite.get_historical = AsyncMock(return_value=pd.DataFrame())

            await post_login_initialization()

            mock_swing.assert_awaited_once()
            mock_momentum.assert_awaited_once()
