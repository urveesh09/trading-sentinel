"""
Tests for python-engine/performance.py - circuit breakers, bankroll ledger, P&L.
All tests use temp SQLite files (aiosqlite needs file paths, not :memory: for multi-connection).
"""
import pytest
import pytest_asyncio
from datetime import datetime
from performance import (
    init_ledger,
    current_bankroll,
    record_trade_close,
    check_circuit_breakers,
)


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

@pytest_asyncio.fixture
async def seeded_db(db_path):
    """Init the ledger with INITIAL_BANKROLL = 5000."""
    await init_ledger(db_path)
    return db_path


# ═══════════════════════════════════════════════════════════════
# LEDGER BASICS
# ═══════════════════════════════════════════════════════════════


class TestLedgerInit:

    @pytest.mark.asyncio
    async def test_initial_bankroll_seeded(self, seeded_db):
        """[BK1] First row should be INITIAL event with 5000."""
        bankroll = await current_bankroll(seeded_db)
        assert bankroll == 5000.0

    @pytest.mark.asyncio
    async def test_init_idempotent(self, seeded_db):
        """Calling init_ledger twice should not duplicate the initial row."""
        await init_ledger(seeded_db)
        bankroll = await current_bankroll(seeded_db)
        assert bankroll == 5000.0

    @pytest.mark.asyncio
    async def test_record_trade_updates_bankroll(self, seeded_db):
        """[BK2] After a winning trade, bankroll should increase."""
        await record_trade_close(seeded_db, "RELIANCE", 100.0)
        bankroll = await current_bankroll(seeded_db)
        assert bankroll == 5100.0

    @pytest.mark.asyncio
    async def test_record_losing_trade(self, seeded_db):
        """After a losing trade, bankroll should decrease."""
        await record_trade_close(seeded_db, "TCS", -200.0)
        bankroll = await current_bankroll(seeded_db)
        assert bankroll == 4800.0

    @pytest.mark.asyncio
    async def test_sequential_trades(self, seeded_db):
        """Multiple trades should chain bankroll correctly."""
        await record_trade_close(seeded_db, "A", 100.0)   # 5100
        await record_trade_close(seeded_db, "B", -50.0)   # 5050
        await record_trade_close(seeded_db, "C", 200.0)   # 5250
        bankroll = await current_bankroll(seeded_db)
        assert bankroll == 5250.0


# ═══════════════════════════════════════════════════════════════
# CIRCUIT BREAKERS
# ═══════════════════════════════════════════════════════════════


class TestCircuitBreakers:

    @pytest.mark.asyncio
    async def test_no_halt_clean_state(self, seeded_db):
        """Fresh ledger should have no circuit breakers triggered."""
        halted, reasons = await check_circuit_breakers(seeded_db)
        assert halted is False
        assert len(reasons) == 0

    @pytest.mark.asyncio
    async def test_cb_floor_breached(self, seeded_db):
        """[CB3/BK5] Bankroll < INITIAL * CB_FLOOR_PCT (0.40) = 2000 triggers floor breach."""
        # Lose 3100 → bankroll = 1900 < 2000
        await record_trade_close(seeded_db, "LOSS1", -3100.0)
        halted, reasons = await check_circuit_breakers(seeded_db)
        assert halted is True
        assert "CB_FLOOR_BREACHED" in reasons

    @pytest.mark.asyncio
    async def test_cb_floor_not_breached_above(self, seeded_db):
        """Bankroll at 2100 (> 2000 floor) should not trigger."""
        await record_trade_close(seeded_db, "LOSS", -2900.0)  # 5000 - 2900 = 2100
        halted, reasons = await check_circuit_breakers(seeded_db)
        assert "CB_FLOOR_BREACHED" not in reasons

    @pytest.mark.asyncio
    async def test_cb_max_drawdown(self, seeded_db):
        """CB_MAX_DRAWDOWN: peak-to-trough >= 50% triggers halt."""
        # First grow to 10000, then drop to 5000 → 50% drawdown
        await record_trade_close(seeded_db, "WIN", 5000.0)   # peak = 10000
        await record_trade_close(seeded_db, "LOSS", -5000.0)  # current = 5000
        halted, reasons = await check_circuit_breakers(seeded_db)
        assert halted is True
        assert "CB_MAX_DRAWDOWN" in reasons

    @pytest.mark.asyncio
    async def test_cb_max_drawdown_not_triggered(self, seeded_db):
        """49% drawdown should NOT trigger."""
        await record_trade_close(seeded_db, "WIN", 5000.0)    # peak = 10000
        await record_trade_close(seeded_db, "LOSS", -4899.0)  # current = 5101, dd = 49%
        halted, reasons = await check_circuit_breakers(seeded_db)
        assert "CB_MAX_DRAWDOWN" not in reasons

    @pytest.mark.asyncio
    async def test_cb_daily_loss(self, seeded_db):
        """[CB1] Daily P&L <= -(bankroll * 0.20) triggers halt.
        Bankroll = 5000, threshold = -1000."""
        await record_trade_close(seeded_db, "BIG_LOSS", -1000.0)
        halted, reasons = await check_circuit_breakers(seeded_db)
        # Bankroll is now 4000, daily_pnl = -1000
        # Threshold = -(4000 * 0.20) = -800. -1000 <= -800 → triggered
        assert halted is True
        assert "CB_DAILY_LOSS" in reasons

    @pytest.mark.asyncio
    async def test_cb_daily_loss_not_triggered(self, seeded_db):
        """Small daily loss should not trigger."""
        await record_trade_close(seeded_db, "SMALL", -100.0)
        halted, reasons = await check_circuit_breakers(seeded_db)
        assert "CB_DAILY_LOSS" not in reasons

    @pytest.mark.asyncio
    async def test_cb_consecutive_losses(self, seeded_db):
        """[CB2] 5 consecutive losses triggers halt."""
        for i in range(5):
            await record_trade_close(seeded_db, f"LOSS{i}", -50.0)
        halted, reasons = await check_circuit_breakers(seeded_db)
        assert "CB_CONSECUTIVE_LOSSES" in reasons

    @pytest.mark.asyncio
    async def test_cb_consecutive_4_losses_no_halt(self, seeded_db):
        """4 consecutive losses should NOT trigger."""
        for i in range(4):
            await record_trade_close(seeded_db, f"LOSS{i}", -50.0)
        halted, reasons = await check_circuit_breakers(seeded_db)
        assert "CB_CONSECUTIVE_LOSSES" not in reasons

    @pytest.mark.asyncio
    async def test_cb_consecutive_reset_by_win(self, seeded_db):
        """A winning trade resets the consecutive loss counter."""
        for i in range(4):
            await record_trade_close(seeded_db, f"LOSS{i}", -50.0)
        await record_trade_close(seeded_db, "WIN", 100.0)  # reset
        await record_trade_close(seeded_db, "LOSS_AFTER", -50.0)
        halted, reasons = await check_circuit_breakers(seeded_db)
        assert "CB_CONSECUTIVE_LOSSES" not in reasons

    @pytest.mark.asyncio
    async def test_cb4_disabled_q2(self, seeded_db):
        """[Q2] CB4 (backtest gate) is commented out. No BACKTEST_GATE_FAILED reason."""
        halted, reasons = await check_circuit_breakers(seeded_db)
        assert "BACKTEST_GATE_FAILED" not in reasons

    @pytest.mark.asyncio
    async def test_multiple_breakers_fire(self, seeded_db):
        """Multiple circuit breakers can fire simultaneously."""
        # 5 consecutive large losses to trigger: consecutive + daily + possibly floor
        for i in range(5):
            await record_trade_close(seeded_db, f"BIG{i}", -500.0)
        halted, reasons = await check_circuit_breakers(seeded_db)
        assert halted is True
        assert len(reasons) >= 2  # at least CB_CONSECUTIVE_LOSSES + one more
