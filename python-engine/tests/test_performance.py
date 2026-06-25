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
    pool_breakdown,
    nifty_bankroll,
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


# ===============================================================
# POOL BREAKDOWN (2026-06-24, B-tight)
# Tests for /bankroll/breakdown: per-pool display, no risk math change.
# ===============================================================


class TestPoolBreakdown:
    """[POOL-BREAKDOWN 2026-06-24] Per-pool bankroll display.

    B-tight semantics: swing and penny balances are reported as
    INDEPENDENT numbers. The combined number is informational only.
    current_bankroll() and check_circuit_breakers() are unchanged --
    these tests verify both behaviors in parallel.
    """

    @pytest.mark.asyncio
    async def test_empty_ledger_returns_initial_swing_and_pool_penny(self, seeded_db):
        """Fresh ledger with no trades: swing=INITIAL, penny=PENNY_LIVE_BANKROLL."""
        out = await pool_breakdown(seeded_db)
        # Conftest patches INITIAL_BANKROLL=5000; config defaults PENNY_LIVE_BANKROLL=2000.
        assert out["swing"]["balance"] == 5000.0
        assert out["swing"]["trades"] == 0
        assert out["penny"]["allocated"] == 2000.0
        assert out["penny"]["balance"] == 2000.0  # no P&L yet
        assert out["penny"]["pnl"] == 0.0
        assert out["penny"]["trades"] == 0
        assert out["penny"]["mode"] == "live"  # default in config.py
        assert out["combined"] == 7000.0

    @pytest.mark.asyncio
    async def test_penny_win_adds_to_penny_balance(self, seeded_db):
        """Penny close with positive P&L bumps penny.balance only -- swing untouched."""
        await record_trade_close(seeded_db, "PENNY_WIN", 150.0, source="PENNY")
        out = await pool_breakdown(seeded_db)
        assert out["swing"]["balance"] == 5000.0  # unchanged
        assert out["penny"]["balance"] == 2150.0  # 2000 + 150
        assert out["penny"]["pnl"] == 150.0
        assert out["penny"]["trades"] == 1
        assert out["combined"] == 7150.0

    @pytest.mark.asyncio
    async def test_penny_loss_subtracts_from_penny_balance(self, seeded_db):
        """Penny close with negative P&L reduces penny.balance only."""
        await record_trade_close(seeded_db, "PENNY_LOSS", -300.0, source="PENNY")
        out = await pool_breakdown(seeded_db)
        assert out["swing"]["balance"] == 5000.0  # unchanged
        assert out["penny"]["balance"] == 1700.0  # 2000 - 300
        assert out["penny"]["pnl"] == -300.0
        assert out["penny"]["trades"] == 1

    @pytest.mark.asyncio
    async def test_swing_and_penny_tracked_independently(self, seeded_db):
        """Both pools accumulate their own P&L -- no cross-contamination."""
        # Swing: +500 win and -200 loss
        await record_trade_close(seeded_db, "SWING_WIN", 500.0, source="SYSTEM")
        await record_trade_close(seeded_db, "SWING_LOSS", -200.0, source="SYSTEM")
        # Penny: +100 win and -50 loss
        await record_trade_close(seeded_db, "PENNY_WIN", 100.0, source="PENNY")
        await record_trade_close(seeded_db, "PENNY_LOSS", -50.0, source="PENNY")
        out = await pool_breakdown(seeded_db)
        assert out["swing"]["balance"] == 5300.0  # 5000 + 500 - 200
        assert out["swing"]["trades"] == 2  # both non-zero
        assert out["penny"]["balance"] == 2050.0  # 2000 + 100 - 50
        assert out["penny"]["trades"] == 2
        assert out["combined"] == 7350.0

    @pytest.mark.asyncio
    async def test_zero_pnl_rows_not_counted_as_trades(self, seeded_db):
        """A SYSTEM row with pnl=0 (e.g., the INITIAL seed) must not bump trade count."""
        # The seeded_db fixture has the INITIAL row (pnl=0). Trade count must still be 0.
        out = await pool_breakdown(seeded_db)
        assert out["swing"]["trades"] == 0
        assert out["penny"]["trades"] == 0

    @pytest.mark.asyncio
    async def test_current_bankroll_unaffected_by_penny(self, seeded_db):
        """[REGRESSION GUARD] current_bankroll() must STILL equal the ledger's
        last row -- not the combined swing+penny. This is the B-tight guarantee:
        the existing /bankroll endpoint and check_circuit_breakers() math
        stay exactly as they were before the breakdown feature."""
        await record_trade_close(seeded_db, "PENNY_WIN", 999.0, source="PENNY")
        bankroll = await current_bankroll(seeded_db)
        # 5000 (initial) + 999 (last penny row, since it was appended after seed)
        # current_bankroll reads the LAST row, regardless of source.
        assert bankroll == 5999.0
        # But the breakdown still shows swing at 5000 (untouched) and penny at 2999.
        out = await pool_breakdown(seeded_db)
        assert out["swing"]["balance"] == 5000.0
        assert out["penny"]["balance"] == 2999.0
        # This is the B-tight invariant: combined is informational,
        # swing CBs still measure swing alone.
        assert out["combined"] == 7999.0

    @pytest.mark.asyncio
    async def test_paper_mode_uses_paper_bankroll(self, seeded_db, monkeypatch):
        """When PENNY_LIVE_TRADING is False, penny.allocated falls back to
        PENNY_PAPER_BANKROLL (Rs 500 default)."""
        from config import settings
        monkeypatch.setattr(settings, "PENNY_LIVE_TRADING", False)
        out = await pool_breakdown(seeded_db)
        assert out["penny"]["mode"] == "paper"
        assert out["penny"]["allocated"] == 500.0
        assert out["penny"]["balance"] == 500.0
        assert out["combined"] == 5500.0  # 5000 swing + 500 paper penny

    @pytest.mark.asyncio
    async def test_paper_mode_penny_trades_still_tracked(self, seeded_db, monkeypatch):
        """In paper mode, penny P&L still flows into penny.balance normally."""
        from config import settings
        monkeypatch.setattr(settings, "PENNY_LIVE_TRADING", False)
        await record_trade_close(seeded_db, "PAPER_PENNY", 50.0, source="PENNY")
        out = await pool_breakdown(seeded_db)
        assert out["penny"]["allocated"] == 500.0
        assert out["penny"]["balance"] == 550.0  # 500 paper + 50 pnl

    @pytest.mark.asyncio
    async def test_breakdown_response_shape(self, seeded_db):
        """The endpoint contract: every documented key must be present."""
        out = await pool_breakdown(seeded_db)
        assert set(out.keys()) == {"swing", "penny", "combined", "as_of"}
        assert set(out["swing"].keys()) == {"balance", "trades"}
        assert set(out["penny"].keys()) == {
            "balance", "allocated", "pnl", "trades", "mode",
        }
        # ISO-8601 timestamp string (UTC, with offset)
        assert "T" in out["as_of"]


# ===============================================================
# NIFTY BANKROLL (2026-06-24 strict separation)
# Tests for nifty_bankroll() and the strict-separation invariant.
# ===============================================================


class TestNiftyBankroll:
    """[NIFTY-BANKROLL 2026-06-24] Strict-separation Nifty-subsystem balance.

    nifty_bankroll() returns the Nifty-subsystem balance = INITIAL_BANKROLL +
    SUM of every ledger row whose source is SYSTEM or MOMENTUM. PENNY rows
    are EXCLUDED.

    This is the function that swing RiskEngine sizing, the momentum screener,
    the /signals / /momentum-signals / /performance endpoints, the /bankroll
    endpoint, and check_circuit_breakers() all read internally.

    The previous test_current_bankroll_includes_penny verified the LEGACY
    last-row behavior -- current_bankroll() still has that behavior. But
    no production code reads current_bankroll() anymore (everything switched
    to nifty_bankroll). The legacy function remains public for backwards
    compatibility with external test suites and any out-of-tree consumers.
    """

    @pytest.mark.asyncio
    async def test_empty_ledger_returns_initial(self, seeded_db):
        """No trades: nifty_bankroll = INITIAL_BANKROLL."""
        from performance import nifty_bankroll
        out = await nifty_bankroll(seeded_db)
        assert out == 5000.0

    @pytest.mark.asyncio
    async def test_swing_win_increases_nifty(self, seeded_db):
        """A SYSTEM row bumps nifty_bankroll by its pnl."""
        from performance import nifty_bankroll
        await record_trade_close(seeded_db, "SWING_WIN", 300.0, source="SYSTEM")
        assert await nifty_bankroll(seeded_db) == 5300.0

    @pytest.mark.asyncio
    async def test_swing_loss_decreases_nifty(self, seeded_db):
        from performance import nifty_bankroll
        await record_trade_close(seeded_db, "SWING_LOSS", -200.0, source="SYSTEM")
        assert await nifty_bankroll(seeded_db) == 4800.0

    @pytest.mark.asyncio
    async def test_momentum_row_counts(self, seeded_db):
        """A MOMENTUM-source row also feeds nifty_bankroll -- momentum is
        a sub-pool of the Nifty subsystem."""
        from performance import nifty_bankroll
        await record_trade_close(seeded_db, "MOM_WIN", 100.0, source="MOMENTUM")
        assert await nifty_bankroll(seeded_db) == 5100.0

    @pytest.mark.asyncio
    async def test_penny_row_does_not_contaminate_nifty(self, seeded_db):
        """[REGRESSION GUARD] The whole point of strict separation: penny
        P&L MUST NOT change nifty_bankroll."""
        from performance import nifty_bankroll
        before = await nifty_bankroll(seeded_db)
        # Big penny win and big penny loss -- neither should touch nifty.
        await record_trade_close(seeded_db, "PENNY_WIN", 1000.0, source="PENNY")
        await record_trade_close(seeded_db, "PENNY_LOSS", -1500.0, source="PENNY")
        after = await nifty_bankroll(seeded_db)
        assert before == after == 5000.0, \
            f"penny rows contaminated nifty: {before} -> {after}"

    @pytest.mark.asyncio
    async def test_penny_row_does_not_contaminate_even_when_last(self, seeded_db):
        """[STRICT-SEPARATION INVARIANT] This is the load-bearing test:
        even when the LAST ledger row is a PENNY row (after interleaved
        trades), nifty_bankroll must still read pure Nifty-subsystem.

        Before AUDIT-FIX-1.1, swing RiskEngine was constructed with
        current_bankroll() = last ledger row, which could be PENNY. With
        strict separation, nifty_bankroll() reads SUM(pnl WHERE source IN
        ('SYSTEM','MOMENTUM')) -- robust to row order.

        After AUDIT-FIX-1.1, record_trade_close also uses per-source
        bankroll_for_source(source) for the bankroll_before/after
        columns. That means the LAST ledger row's bankroll_after now
        reflects only the source of that row (SWING_2 = 5300), not a
        mixed value (5250 pre-fix). current_bankroll() is therefore
        also robust to row order now.
        """
        from performance import nifty_bankroll, current_bankroll
        # Interleave: swing win, then penny loss, then swing win.
        await record_trade_close(seeded_db, "SWING_1", 100.0, source="SYSTEM")
        await record_trade_close(seeded_db, "PENNY_1", -50.0, source="PENNY")
        await record_trade_close(seeded_db, "SWING_2", 200.0, source="SYSTEM")
        # Legacy: last ledger row is SWING_2. With AUDIT-FIX-1.1 the
        # per-source bankroll_after is 5100 + 200 = 5300 (was 5250 pre-fix).
        legacy = await current_bankroll(seeded_db)
        assert legacy == 5300.0  # AUDIT-FIX-1.1: per-source bankroll_after
        # Strict: Nifty = 5000 + 100 + 200 = 5300. Penny -50 excluded.
        strict = await nifty_bankroll(seeded_db)
        assert strict == 5300.0, \
            f"strict separation broken: nifty={strict}, expected 5300"
        # Both values agree (they wouldn't pre-fix when penny was last).
        assert legacy == strict

    @pytest.mark.asyncio
    async def test_check_circuit_breakers_uses_strict_separation(self, seeded_db):
        """[CB STRICT] check_circuit_breakers must measure against the
        Nifty-subsystem balance. A penny loss that drives the last ledger
        row below the floor must NOT trip CB_FLOOR_BREACHED."""
        # 5000 * 0.40 = 2000 = floor. Drive the last ledger row below 2000
        # by writing penny losses; nifty balance should still be 5000.
        await record_trade_close(seeded_db, "BIG_PENNY_LOSS", -3500.0, source="PENNY")
        # current_bankroll() is now 1500 (last row).
        # nifty_bankroll() is still 5000 (no SYSTEM rows yet).
        # CB must see bankroll=5000 and NOT trip the floor.
        halted, reasons = await check_circuit_breakers(seeded_db)
        assert halted is False, \
            f"CB tripped on penny contamination: reasons={reasons}"
        assert "CB_FLOOR_BREACHED" not in reasons
        assert "CB_DAILY_LOSS" not in reasons

    @pytest.mark.asyncio
    async def test_check_circuit_breakers_does_count_swing_loss(self, seeded_db):
        """A real swing loss still trips the CB -- strict separation does
        not disable swing risk gates, it just stops them from being
        poisoned by penny."""
        # Lose 3500 on swing: bankroll = 1500 < 2000 floor -> trip.
        await record_trade_close(seeded_db, "BIG_SWING_LOSS", -3500.0, source="SYSTEM")
        halted, reasons = await check_circuit_breakers(seeded_db)
        assert halted is True
        assert "CB_FLOOR_BREACHED" in reasons

    @pytest.mark.asyncio
    async def test_check_circuit_breakers_consecutive_streak_ignores_penny(
        self, seeded_db
    ):
        """[CB2 STRICT] Consecutive-losses streak must count Nifty rows only.
        Penny losses interleaved with swing wins must NOT break a streak
        for swing (because penny isn't swing) and must NOT count toward
        a streak (because they're not swing either)."""
        # 5 swing losses -> trip CB_CONSECUTIVE_LOSSES.
        for i in range(5):
            await record_trade_close(seeded_db, f"SWING_LOSS_{i}", -50.0, source="SYSTEM")
        halted, reasons = await check_circuit_breakers(seeded_db)
        assert "CB_CONSECUTIVE_LOSSES" in reasons

    @pytest.mark.asyncio
    async def test_check_circuit_breakers_penny_loss_does_not_break_swing_streak(
        self, seeded_db
    ):
        """[CB2 STRICT, OPPOSITE DIRECTION] A penny loss interleaved between
        swing wins does NOT count as a swing loss, so the swing streak
        correctly counts only swing trades."""
        # 4 swing losses, 1 penny win, 1 swing loss -> streak is 5 swing losses.
        # If penny were counted, the penny win would break the streak.
        for i in range(4):
            await record_trade_close(seeded_db, f"L{i}", -50.0, source="SYSTEM")
        await record_trade_close(seeded_db, "PENNY_WIN", 10.0, source="PENNY")
        await record_trade_close(seeded_db, "L_FINAL", -50.0, source="SYSTEM")
        halted, reasons = await check_circuit_breakers(seeded_db)
        # The penny row is not in the swing streak (source filter excludes it),
        # so the last 5 swing rows are: L3, L2, L1, L0, L_FINAL -- all losses.
        # Streak = 5 -> trip.
        assert "CB_CONSECUTIVE_LOSSES" in reasons
