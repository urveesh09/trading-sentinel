import inspect
import sqlite3
from datetime import datetime, timezone

import pytest

import main
import performance
from models import OpenPosition
from penny_daily_attribution import compute_daily_metrics
from penny_scanner import PennyScanner


class _Kite:
    instrument_cache = {}


def test_scanner_source_is_static_from_execution_mode():
    paper = PennyScanner(_Kite(), "unused.json", paper_mode=True)
    live = PennyScanner(_Kite(), "unused.json", paper_mode=False)
    assert paper.source_tag == "PENNY_PAPER"
    assert live.source_tag == "PENNY"
    # Later settings changes cannot rewrite an already-created scanner source.
    assert paper.source_tag == "PENNY_PAPER"


@pytest.mark.asyncio
async def test_ledger_writer_captures_source_once(monkeypatch):
    calls = []

    async def record(db_path, ticker, pnl, *, source):
        calls.append((ticker, pnl, source))

    monkeypatch.setattr(performance, "record_trade_close", record)
    writer = main._make_penny_ledger_writer("PENNY_PAPER")
    await writer("CHEAP", 42.0)
    assert calls == [("CHEAP", 42.0, "PENNY_PAPER")]


def test_position_model_accepts_both_classic_penny_sources():
    base = dict(
        ticker="CHEAP", exchange="NSE", entry_date=datetime.now(timezone.utc),
        entry_price=10, shares=5, stop_loss_initial=9,
        trailing_stop_current=9, target_1=11, target_2=12,
        highest_close_since_entry=10, status="OPEN",
    )
    assert OpenPosition(**base, source="PENNY_PAPER").source == "PENNY_PAPER"
    assert OpenPosition(**base, source="PENNY").source == "PENNY"


def test_daily_monitor_selects_one_source_without_mixing(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE bankroll_ledger (
        id INTEGER PRIMARY KEY, timestamp TEXT,event_type TEXT,ticker TEXT,pnl REAL,
        bankroll_before REAL,bankroll_after REAL,source TEXT,notes TEXT)""")
    conn.execute("CREATE TABLE positions (ticker TEXT,status TEXT,source TEXT)")
    today = "2026-08-10T10:00:00+00:00"
    conn.execute("INSERT INTO bankroll_ledger VALUES (1,?,'TRADE_CLOSED','LIVE',10,0,0,'PENNY','')", (today,))
    conn.execute("INSERT INTO bankroll_ledger VALUES (2,?,'TRADE_CLOSED','PAPER',999,0,0,'PENNY_PAPER','')", (today,))
    conn.execute("INSERT INTO positions VALUES ('LIVEOPEN','OPEN','PENNY')")
    conn.execute("INSERT INTO positions VALUES ('PAPEROPEN','OPEN','PENNY_PAPER')")
    conn.commit(); conn.close()
    now = datetime(2026, 8, 10, 12, tzinfo=timezone.utc)
    live = compute_daily_metrics(db_path, now, source="PENNY")
    paper = compute_daily_metrics(db_path, now, source="PENNY_PAPER")
    assert (live.total_pnl, live.open_positions_count) == (10, 1)
    assert (paper.total_pnl, paper.open_positions_count) == (999, 1)


def test_new_position_writes_use_scanner_source_and_no_relabel_sql():
    scanner_src = inspect.getsource(PennyScanner.scan_once)
    main_src = inspect.getsource(main.run_penny_connors_scan)
    assert 'self.source_tag' in scanner_src
    assert 'scanner.source_tag' in main_src
    assert "UPDATE positions SET source" not in inspect.getsource(main)
