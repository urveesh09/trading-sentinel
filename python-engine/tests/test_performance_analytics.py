import aiosqlite
import pytest

from config import settings
from performance_analytics import division_performance


async def _schema(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.executescript("""
            CREATE TABLE bankroll_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT, event_type TEXT, ticker TEXT, pnl REAL,
                bankroll_before REAL, bankroll_after REAL, source TEXT,
                notes TEXT
            );
            CREATE TABLE positions (
                ticker TEXT, entry_date TEXT, entry_price REAL, shares INTEGER,
                stop_loss_initial REAL, trailing_stop_current REAL,
                status TEXT, source TEXT, exit_date TEXT,
                realised_pnl REAL, r_multiple REAL
            );
            CREATE TABLE fno_positions (
                id INTEGER PRIMARY KEY, source TEXT, status TEXT,
                pnl REAL, r_multiple REAL, costs REAL, gross_pnl REAL,
                entry_premium REAL, qty INTEGER, max_loss_rupees REAL,
                exit_time TEXT
            );
            CREATE TABLE fno_dr_positions (
                id INTEGER PRIMARY KEY, source TEXT, status TEXT,
                pnl REAL, costs REAL, gross_pnl REAL,
                net_premium_rs REAL, max_loss_rs REAL, closed_at TEXT
            );
        """)
        await db.commit()


def _division(report: dict, source: str) -> dict:
    return next(row for row in report["divisions"] if row["source"] == source)


@pytest.fixture
def analytics_allocations(monkeypatch):
    monkeypatch.setattr(settings, "INITIAL_BANKROLL", 1000.0)
    monkeypatch.setattr(settings, "MOMENTUM_POOL_PCT", 0.4)
    monkeypatch.setattr(settings, "MOMENTUM_PAPER_BANKROLL", 5000.0)
    monkeypatch.setattr(settings, "PENNY_LIVE_TRADING", False)
    monkeypatch.setattr(settings, "PENNY_LIVE_BANKROLL", 200.0)
    monkeypatch.setattr(settings, "PENNY_PAPER_BANKROLL", 2000.0)
    monkeypatch.setattr(settings, "PENNY_EDGE_LIVE_BANKROLL", 300.0)
    monkeypatch.setattr(settings, "PENNY_EDGE_PAPER_BANKROLL", 3000.0)
    monkeypatch.setattr(settings, "FNO_PAPER_BANKROLL", 4000.0)
    monkeypatch.setattr(settings, "FNO_LIVE_BANKROLL", 500.0)
    monkeypatch.setattr(settings, "FNO_LIVE_TRADING", False)


@pytest.mark.asyncio
async def test_isolation_ledger_metrics_drawdown_streak_and_mismatch(
    tmp_path, analytics_allocations
):
    db_path = str(tmp_path / "analytics.db")
    await _schema(db_path)
    async with aiosqlite.connect(db_path) as db:
        # Swing allocation is 600. Equity: 600 -> 700 -> 650 -> 625.
        for i, pnl in enumerate((100.0, -50.0, -25.0), start=1):
            await db.execute(
                "INSERT INTO bankroll_ledger "
                "(timestamp,event_type,ticker,pnl,source) VALUES (?,?,?,?,?)",
                (f"2026-08-0{i}T10:00:00Z", "TRADE_CLOSED", f"S{i}", pnl, "SYSTEM"),
            )
        # A large paper result must not enter any live statistic.
        await db.execute(
            "INSERT INTO bankroll_ledger "
            "(timestamp,event_type,ticker,pnl,source) VALUES (?,?,?,?,?)",
            ("2026-08-01T11:00:00Z", "TRADE_CLOSED", "PAPER", 900.0, "EDGE_PAPER"),
        )
        # Position observation deliberately disagrees: 2 closes / +30 vs
        # ledger's 3 closes / +25.
        for ticker, pnl, r in (("S1", 100.0, 1.0), ("S2", -70.0, -0.7)):
            await db.execute(
                "INSERT INTO positions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (ticker, "2026-08-01", 100, 1, 90, 90, "CLOSED", "SYSTEM",
                 "2026-08-02", pnl, r),
            )
        await db.commit()

    report = await division_performance(db_path)
    swing = _division(report, "SYSTEM")
    ledger = swing["ledger"]
    assert swing["mode"] == "live"
    assert swing["allocation"] == 600.0
    assert ledger["cash_pnl"] == 25.0
    assert ledger["equity"] == 625.0
    assert ledger["trade_close_count"] == 3
    assert ledger["wins"] == 1
    assert ledger["losses"] == 2
    assert ledger["win_rate"] == pytest.approx(1 / 3, abs=1e-6)
    assert ledger["profit_factor"] == pytest.approx(100 / 75, abs=1e-6)
    assert ledger["net_expectancy"] == pytest.approx(25 / 3, abs=1e-4)
    assert ledger["current_losing_streak"] == 2
    assert ledger["max_losing_streak"] == 2
    assert ledger["max_drawdown"] == 75.0
    assert ledger["current_drawdown"] == 75.0
    assert ledger["max_drawdown_pct"] == pytest.approx(75 / 700, abs=1e-6)
    assert swing["positions"]["avg_r"] == 0.15
    assert swing["positions"]["costs"] is None
    assert swing["reconciliation"] == {
        "status": "MISMATCH", "pnl_delta": 5.0, "count_gap": -1,
        "ledger_is_cash_truth": True,
    }
    assert "disagree" in " ".join(swing["warnings"])

    edge_paper = _division(report, "EDGE_PAPER")
    assert edge_paper["ledger"]["cash_pnl"] == 900.0
    assert report["totals"]["live"]["cash_pnl"] == 25.0
    assert report["totals"]["paper"]["cash_pnl"] == 900.0


@pytest.mark.asyncio
async def test_fno_costs_open_risk_and_matching_reconciliation(
    tmp_path, analytics_allocations
):
    db_path = str(tmp_path / "fno.db")
    await _schema(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO bankroll_ledger "
            "(timestamp,event_type,ticker,pnl,source) VALUES (?,?,?,?,?)",
            ("2026-08-01", "TRADE_CLOSED", "NIFTY", 80.0, "FNO_PAPER"),
        )
        await db.execute(
            "INSERT INTO fno_positions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (1, "FNO_PAPER", "CLOSED", 80.0, 0.8, 20.0, 100.0,
             50.0, 2, 40.0, "2026-08-01"),
        )
        await db.execute(
            "INSERT INTO fno_positions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (2, "FNO_PAPER", "OPEN", None, None, None, None,
             60.0, 3, 75.0, None),
        )
        await db.commit()

    row = _division(await division_performance(db_path), "FNO_PAPER")
    assert row["positions"]["costs"] == 20.0
    assert row["positions"]["cost_drag_pct"] == 0.2
    assert row["positions"]["open_count"] == 1
    assert row["positions"]["open_exposure"] == 180.0
    assert row["positions"]["open_risk"] == 75.0
    assert row["positions"]["avg_r"] == 0.8
    assert row["reconciliation"]["status"] == "MATCH"


@pytest.mark.asyncio
async def test_missing_tables_and_incomplete_rows_are_not_fabricated_zeroes(
    tmp_path, analytics_allocations
):
    missing_path = str(tmp_path / "missing.db")
    missing = await division_performance(missing_path)
    swing = _division(missing, "SYSTEM")
    assert swing["ledger"]["cash_pnl"] is None
    assert swing["ledger"]["equity"] is None
    assert swing["ledger"]["profit_factor"] is None
    assert swing["positions"]["closed_pnl"] is None
    assert swing["positions"]["open_exposure"] is None
    assert swing["reconciliation"]["status"] == "UNAVAILABLE"
    assert missing["totals"]["live"]["cash_pnl"] is None
    assert missing["totals"]["live"]["equity"] is None

    incomplete_path = str(tmp_path / "incomplete.db")
    await _schema(incomplete_path)
    async with aiosqlite.connect(incomplete_path) as db:
        await db.execute(
            "INSERT INTO positions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("X", "2026-08-01", 10, 1, 9, 9, "CLOSED", "SYSTEM",
             "2026-08-02", None, None),
        )
        await db.commit()
    incomplete = _division(await division_performance(incomplete_path), "SYSTEM")
    assert incomplete["positions"]["closed_count"] == 1
    assert incomplete["positions"]["closed_pnl"] is None
    assert incomplete["positions"]["avg_r"] is None
    assert incomplete["reconciliation"]["status"] == "UNAVAILABLE"
    assert any("NULL P&L" in warning for warning in incomplete["warnings"])


@pytest.mark.asyncio
async def test_overall_totals_count_shared_nifty_seed_once(
    tmp_path, analytics_allocations
):
    db_path = str(tmp_path / "totals.db")
    await _schema(db_path)
    report = await division_performance(db_path)

    assert _division(report, "SYSTEM")["allocation"] == 600.0
    assert _division(report, "MOMENTUM")["allocation"] == 400.0
    assert report["invariants"] == {
        "nifty_allocation": 1000.0,
        "nifty_allocation_expected": 1000.0,
        "nifty_not_double_counted": True,
    }
    expected_live = 600 + 400 + 200 + 300 + 500
    expected_paper = 5000 + 2000 + 3000 + 4000
    assert report["totals"]["live"]["allocation"] == expected_live
    assert report["totals"]["paper"]["allocation"] == expected_paper


@pytest.mark.asyncio
async def test_cash_flows_change_equity_but_not_strategy_drawdown(
    tmp_path, analytics_allocations
):
    db_path = str(tmp_path / "cashflows.db")
    await _schema(db_path)
    async with aiosqlite.connect(db_path) as db:
        events = [
            ("MANUAL_DEPOSIT", 1000.0),
            ("TRADE_CLOSED", 100.0),
            ("TRADE_CLOSED", -50.0),
            ("MANUAL_WITHDRAWAL", -500.0),
        ]
        for i, (kind, pnl) in enumerate(events):
            await db.execute(
                "INSERT INTO bankroll_ledger "
                "(timestamp,event_type,ticker,pnl,source) VALUES (?,?,?,?,?)",
                (f"2026-08-01T10:0{i}:00Z", kind, "X", pnl, "SYSTEM"),
            )
        await db.commit()

    ledger = _division(await division_performance(db_path), "SYSTEM")["ledger"]
    assert ledger["cash_pnl"] == 550.0
    assert ledger["equity"] == 1150.0
    assert ledger["trade_close_pnl"] == 50.0
    assert ledger["max_drawdown"] == 50.0
    assert ledger["current_drawdown"] == 50.0


@pytest.mark.asyncio
async def test_no_trade_metrics_are_null_but_real_zero_trade_is_observed(
    tmp_path, analytics_allocations
):
    db_path = str(tmp_path / "zero.db")
    await _schema(db_path)
    no_sample = _division(await division_performance(db_path), "SYSTEM")["ledger"]
    assert no_sample["trade_close_count"] == 0
    assert no_sample["net_expectancy"] is None
    assert no_sample["max_drawdown"] is None

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO bankroll_ledger "
            "(timestamp,event_type,ticker,pnl,source) VALUES (?,?,?,?,?)",
            ("2026-08-01", "TRADE_CLOSED", "FLAT", 0.0, "SYSTEM"),
        )
        await db.commit()
    flat = _division(await division_performance(db_path), "SYSTEM")["ledger"]
    assert flat["trade_close_count"] == 1
    assert flat["breakeven"] == 1
    assert flat["net_expectancy"] == 0.0
    assert flat["max_drawdown"] == 0.0


@pytest.mark.asyncio
async def test_avg_r_weights_only_rows_that_retain_r(
    tmp_path, analytics_allocations
):
    db_path = str(tmp_path / "r-count.db")
    await _schema(db_path)
    async with aiosqlite.connect(db_path) as db:
        for row in (
            (1, "FNO_PAPER", "CLOSED", 40.0, 1.25, 10.0, 50.0, 20.0, 1, 20.0, "a"),
            (2, "FNO_PAPER", "CLOSED", -10.0, None, 5.0, -5.0, 20.0, 1, 20.0, "b"),
        ):
            await db.execute("INSERT INTO fno_positions VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)
        await db.execute(
            "INSERT INTO fno_dr_positions VALUES (?,?,?,?,?,?,?,?,?)",
            (3, "FNO_PAPER", "CLOSED", 20.0, 4.0, 24.0, 10.0, 30.0, "c"),
        )
        await db.commit()

    positions = _division(
        await division_performance(db_path), "FNO_PAPER"
    )["positions"]
    assert positions["closed_count"] == 3
    assert positions["r_count"] == 1
    assert positions["avg_r"] == 1.25


@pytest.mark.asyncio
async def test_partial_legacy_position_schema_degrades_to_unavailable(
    tmp_path, analytics_allocations
):
    db_path = str(tmp_path / "partial.db")
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE bankroll_ledger (
                timestamp TEXT, event_type TEXT, pnl REAL, source TEXT
            )
        """)
        # Deliberately lacks exit_time and several required accounting fields.
        await db.execute("""
            CREATE TABLE fno_positions (
                source TEXT, status TEXT, pnl REAL, r_multiple REAL,
                costs REAL, gross_pnl REAL, entry_premium REAL,
                qty INTEGER, max_loss_rupees REAL
            )
        """)
        await db.commit()

    fno = _division(await division_performance(db_path), "FNO_PAPER")
    assert fno["positions"]["available"] is False
    assert fno["positions"]["closed_pnl"] is None
    assert fno["reconciliation"]["status"] == "UNAVAILABLE"
    assert any("missing required" in warning for warning in fno["warnings"])
