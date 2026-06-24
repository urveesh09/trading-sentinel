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
    penny_pool_pnl,
)


# ===============================================================
# HELPERS
# ===============================================================

@pytest_asyncio.fixture
async def seeded_db(db_path):
    """Init the ledger with INITIAL_BANKROLL = 5000."""
    await init_ledger(db_path)
    return db_path


# ===============================================================
# LEDGER BASICS
# ===============================================================


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


# ===============================================================
# CIRCUIT BREAKERS
# ===============================================================


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
        # Lose 3100 -> bankroll = 1900 < 2000
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
        # First grow to 10000, then drop to 5000 -> 50% drawdown
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
        # Threshold = -(4000 * 0.20) = -800. -1000 <= -800 -> triggered
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


# ===============================================================
# SOURCE COLUMN (2026-06-24 bankroll fix)
# Tests for the per-subsystem source column on bankroll_ledger.
# ===============================================================


class TestSourceColumn:
    """[BK-SOURCE 2026-06-24] The bankroll_ledger now carries a `source`
    column to attribute rows to swing (SYSTEM), momentum (MOMENTUM), or
    penny (PENNY) subsystems. Required so the dashboard's /bankroll and
    /performance endpoints can show penny P&L that previously lived only
    in PennyRiskEngine.daily_pnl.
    """

    @pytest.mark.asyncio
    async def test_source_column_exists(self, seeded_db):
        """Schema migration: source column must exist after init_ledger()."""
        import aiosqlite
        async with aiosqlite.connect(seeded_db) as db:
            async with db.execute("PRAGMA table_info(bankroll_ledger)") as cur:
                cols = await cur.fetchall()
        col_names = {c[1] for c in cols}
        assert "source" in col_names, f"source column missing; got: {col_names}"

    @pytest.mark.asyncio
    async def test_initial_seed_has_system_source(self, seeded_db):
        """The seed INITIAL row should have source='SYSTEM' (back-compat)."""
        import aiosqlite
        async with aiosqlite.connect(seeded_db) as db:
            async with db.execute(
                "SELECT event_type, source FROM bankroll_ledger ORDER BY id LIMIT 1"
            ) as cur:
                row = await cur.fetchone()
        assert row is not None, "no INITIAL row seeded"
        assert row[0] == "INITIAL"
        assert row[1] == "SYSTEM"

    @pytest.mark.asyncio
    async def test_record_trade_close_default_source(self, seeded_db):
        """Without explicit source, record_trade_close writes 'SYSTEM'."""
        await record_trade_close(seeded_db, "RELIANCE", 100.0)
        import aiosqlite
        async with aiosqlite.connect(seeded_db) as db:
            async with db.execute(
                "SELECT source FROM bankroll_ledger WHERE event_type='TRADE_CLOSED'"
            ) as cur:
                row = await cur.fetchone()
        assert row is not None, "TRADE_CLOSED row missing"
        assert row[0] == "SYSTEM"

    @pytest.mark.asyncio
    async def test_record_trade_close_writes_explicit_source(self, seeded_db):
        """Pass source='PENNY' -- the row must persist with that source."""
        await record_trade_close(seeded_db, "PENNYX", 50.0, source="PENNY")
        import aiosqlite
        async with aiosqlite.connect(seeded_db) as db:
            async with db.execute(
                "SELECT source FROM bankroll_ledger WHERE ticker='PENNYX'"
            ) as cur:
                row = await cur.fetchone()
        assert row is not None, "PENNYX row missing"
        assert row[0] == "PENNY"

    @pytest.mark.asyncio
    async def test_init_ledger_is_idempotent(self, seeded_db):
        """Calling init_ledger twice must not raise (ALTER swallows duplicate-column)."""
        # First call already happened via fixture; second call must be safe.
        await init_ledger(seeded_db)
        # Bankroll should still be the initial seed (no duplicate INITIAL row).
        bankroll = await current_bankroll(seeded_db)
        assert bankroll == 5000.0

    @pytest.mark.asyncio
    async def test_migration_on_pre_existing_db(self, tmp_path):
        """Simulate a pre-2026-06-24 DB: create the table WITHOUT the source
        column, then run init_ledger -- the ALTER migration must add it
        without raising."""
        import aiosqlite
        db_path = str(tmp_path / "legacy.db")
        async with aiosqlite.connect(db_path) as db:
            await db.execute("""
                CREATE TABLE bankroll_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT, event_type TEXT,
                    ticker TEXT, pnl REAL,
                    bankroll_before REAL, bankroll_after REAL,
                    notes TEXT
                )
            """)
            await db.execute(
                "INSERT INTO bankroll_ledger "
                "(timestamp, event_type, pnl, bankroll_before, bankroll_after) "
                "VALUES (?, ?, ?, ?, ?)",
                ("2026-06-23T00:00:00+00:00", "INITIAL", 0.0, 5000.0, 5000.0),
            )
            await db.commit()
        # Now run init_ledger on this legacy DB -- should migrate, not crash.
        await init_ledger(db_path)
        # The new column should exist with default 'SYSTEM' on existing rows.
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT source FROM bankroll_ledger WHERE event_type='INITIAL'"
            ) as cur:
                row = await cur.fetchone()
        assert row is not None, "INITIAL row missing after migration"
        assert row[0] == "SYSTEM"

    @pytest.mark.asyncio
    async def test_penny_pool_pnl_aggregates_penny_rows(self, seeded_db):
        """penny_pool_pnl() sums only source='PENNY' rows in the window."""
        # SYSTEM rows (swing side) -- must be excluded from penny totals.
        await record_trade_close(seeded_db, "SWING_WIN", 1000.0, source="SYSTEM")
        await record_trade_close(seeded_db, "SWING_LOSS", -200.0, source="SYSTEM")
        # PENNY rows -- must be included.
        await record_trade_close(seeded_db, "PENNY_A", 150.0, source="PENNY")
        await record_trade_close(seeded_db, "PENNY_B", -50.0, source="PENNY")
        out = await penny_pool_pnl(seeded_db, days=14)
        assert out["total_pnl"] == 100.0    # 150 + (-50), swing excluded
        assert out["trade_count"] == 2      # only 2 penny rows

    @pytest.mark.asyncio
    async def test_penny_pool_pnl_empty_when_no_penny_rows(self, seeded_db):
        """No PENNY rows -> empty buckets (still safe to call)."""
        await record_trade_close(seeded_db, "X", 100.0, source="SYSTEM")
        out = await penny_pool_pnl(seeded_db, days=14)
        assert out["total_pnl"] == 0.0
        assert out["trade_count"] == 0

    @pytest.mark.asyncio
    async def test_current_bankroll_includes_penny(self, seeded_db):
        """The /bankroll endpoint reads the last row -- penny trades must
        move it just like swing trades do (this is the whole point of the fix)."""
        # Seed: 5000 (from fixture).
        assert await current_bankroll(seeded_db) == 5000.0
        # A penny close must move bankroll.
        await record_trade_close(seeded_db, "PENNY_TEST", 75.0, source="PENNY")
        assert await current_bankroll(seeded_db) == 5075.0
        await record_trade_close(seeded_db, "PENNY_TEST2", -25.0, source="PENNY")
        assert await current_bankroll(seeded_db) == 5050.0
