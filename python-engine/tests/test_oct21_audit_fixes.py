"""Regression tests for the Oct 21 2026 Production audit and the overnight shadows.

S21-R1 Momentum shadow terminal pass, S21-R2 RS_PULLBACK identity binds the
index, daily bars and rule constants, S21-R3 overnight replay admission
parity, S21-E1 EDGE entry-day event check, S21-L1 restart overlap on the
exchange calendar, R21-M1 EDGE signal outcomes and the zero-accept alarm,
R21-M2 F&O hourly allocation vs equity, O19-M1 heartbeat hour marked on
delivery, O21-ON overnight forward shadows.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from types import SimpleNamespace

import aiosqlite
import pandas as pd
import pytest
import pytz

from config import settings

IST = pytz.timezone("Asia/Kolkata")
DAY = "2026-10-21"


# ---------------------------------------------------------------------------
# S21-R1: the after-close terminal pass resolves the day's virtual trades
# ---------------------------------------------------------------------------

def _accepted(ticker="AAA", variant="MOM_RS_PULLBACK", stop=98.0, target=104.0):
    return {"trading_date": DAY, "ticker": ticker, "bar_ts": f"{DAY}T14:30:00+05:30", "variant": variant,
            "accepted": True, "reject_reason": None, "features": {}, "config": {"rs_pullback": True},
            "decision": {"entry_price": 100.0, "stop_loss": stop, "target_1": target, "shares": 10},
            "dataset_fingerprint": "sha256:x", "bars": []}


def _bars(rows):
    """[(hh, mm, open, high, low, close)] -> an IST 15-minute frame for DAY."""
    index = pd.DatetimeIndex([IST.localize(datetime(2026, 10, 21, h, m)) for h, m, *_ in rows])
    return pd.DataFrame([{"open": o, "high": hi, "low": lo, "close": c, "volume": 1000}
                         for _h, _m, o, hi, lo, c in rows], index=index)


QUIET = [(14, 45, 100.2, 100.8, 99.6, 100.5), (15, 0, 100.5, 101.0, 100.1, 100.9),
         (15, 15, 100.9, 101.2, 100.4, 100.6)]


async def _events(db, ticker="AAA"):
    async with aiosqlite.connect(db) as conn:
        return await (await conn.execute(
            "SELECT event_type, reason, bar_ts, exit_fill FROM momentum_shadow_trade_events WHERE ticker=? "
            "ORDER BY bar_ts, event_type", (ticker,))).fetchall()


async def _receipt(db, ticker="AAA"):
    async with aiosqlite.connect(db) as conn:
        return await (await conn.execute(
            "SELECT status, detail, terminal_bar_ts FROM momentum_shadow_terminal_receipts WHERE ticker=?",
            (ticker,))).fetchone()


@pytest.mark.asyncio
async def test_terminal_pass_takes_the_time_exit_at_the_1515_open():
    import momentum_shadow as ms
    db = settings.DB_PATH
    await ms.persist_momentum_shadow_results(db, [_accepted()])

    async def fetch(ticker):
        return _bars(QUIET + [(15, 30, 101.0, 101.0, 90.0, 90.0)])    # never passed: after the exit bar

    summary = await ms.resolve_momentum_shadow_day(db, DAY, fetch)
    assert summary == {"open": 1, "closed": 1, "censored": 0, "tickers": 1}
    events = await _events(db)
    assert [e[0] for e in events] == ["OBSERVED", "OBSERVED", "CLOSED"]
    closed = events[-1]
    assert closed[1] == "time_exit" and closed[2] == f"{DAY}T15:15:00+05:30"
    assert closed[3] == pytest.approx(100.9 * (1 - 5 / 10000), abs=1e-6)
    assert await _receipt(db) == ("CLOSED", "time_exit", f"{DAY}T15:15:00+05:30")


@pytest.mark.asyncio
async def test_terminal_pass_applies_the_stop_on_the_bars_the_scans_missed():
    import momentum_shadow as ms
    db = settings.DB_PATH
    await ms.persist_momentum_shadow_results(db, [_accepted()])

    async def fetch(ticker):
        return _bars([(14, 45, 100.2, 100.8, 99.6, 100.5), (15, 0, 100.0, 100.1, 97.5, 97.8),
                      (15, 15, 97.8, 98.5, 97.0, 98.0)])

    await ms.resolve_momentum_shadow_day(db, DAY, fetch)
    closed = (await _events(db))[-1]
    assert closed[:3] == ("CLOSED", "stop", f"{DAY}T15:00:00+05:30")


@pytest.mark.asyncio
async def test_missing_data_is_censored_and_a_later_pass_can_close_it():
    import momentum_shadow as ms
    db = settings.DB_PATH
    await ms.persist_momentum_shadow_results(db, [_accepted("AAA"), _accepted("BBB")])

    async def broken(ticker):
        if ticker == "AAA":
            raise RuntimeError("provider down")
        return _bars(QUIET[:2])                     # nothing at or after 15:15

    summary = await ms.resolve_momentum_shadow_day(db, DAY, broken)
    assert summary["censored"] == 2 and summary["closed"] == 0
    assert (await _receipt(db, "AAA"))[:2] == ("CENSORED", "fetch_failed:RuntimeError")
    assert (await _receipt(db, "BBB"))[:2] == ("CENSORED", "no_terminal_bar")
    comparison = await ms.momentum_shadow_comparison(db)
    row = next(r for r in comparison["variants"] if r["variant"] == "MOM_RS_PULLBACK")
    assert row["open_trades"] == 2 and row["censored_trades"] == 2
    assert any("censored by the terminal pass" in w for w in row["warnings"])

    async def fixed(ticker):
        return _bars(QUIET)

    await ms.resolve_momentum_shadow_day(db, DAY, fixed)
    assert (await _receipt(db, "AAA"))[0] == "CLOSED" and (await _receipt(db, "BBB"))[0] == "CLOSED"


@pytest.mark.asyncio
async def test_a_slow_history_read_holds_no_write_lock(tmp_path):
    """[A22-M2] The audit's reproducer: after the first ticker's writes, the
    second ticker's fetch ran inside the same open transaction, so any other
    writer got "database is locked". Now each fetch runs with no connection."""
    import sqlite3
    import momentum_shadow as ms
    db = settings.DB_PATH
    await ms.persist_momentum_shadow_results(db, [_accepted("AAA"), _accepted("BBB")])
    other_writes = []

    async def fetch(ticker):
        if ticker == "BBB":
            con = sqlite3.connect(db, timeout=0.2)
            try:
                con.execute("CREATE TABLE IF NOT EXISTS other_writer (n INTEGER)")
                con.execute("INSERT INTO other_writer VALUES (1)")
                con.commit()
                other_writes.append("ok")
            finally:
                con.close()
        return _bars(QUIET)

    summary = await ms.resolve_momentum_shadow_day(db, DAY, fetch)
    assert other_writes == ["ok"] and summary["closed"] == 2


@pytest.mark.asyncio
async def test_the_terminal_job_runs_only_when_enabled_on_a_trading_day(monkeypatch):
    import main
    calls = []

    async def fetch_day(_db, day, fetch):
        calls.append(day)
        return {"open": 0, "closed": 0, "censored": 0, "tickers": 0}

    async def trading(_d, _db):
        return True

    monkeypatch.setattr(main, "resolve_momentum_shadow_day", fetch_day)
    monkeypatch.setattr(main, "is_trading_day", trading)
    when = IST.localize(datetime(2026, 10, 21, 15, 32))
    assert (await main.run_momentum_shadow_terminal(when))["open"] == 0 and calls == [DAY]
    monkeypatch.setattr(settings, "MOMENTUM_SHADOW_ENABLED", False)
    assert await main.run_momentum_shadow_terminal(when) is None and calls == [DAY]


# ---------------------------------------------------------------------------
# S21-R2: the RS identity binds what the rule read
# ---------------------------------------------------------------------------

def _rs_rows(index_frame):
    from momentum_shadow import evaluate_momentum_shadows
    from tests.test_oct19_audit_fixes import _daily, _leader
    stock = _leader()
    rows = evaluate_momentum_shadows("AAA", stock, prev_day_high=101.5, bankroll=50000.0, momentum_pool=50000.0,
                                     df_daily=_daily(), index_today=index_frame(len(stock)))
    return {row["variant"]: row for row in rows}


def _rising_index(n):
    from tests.test_oct19_audit_fixes import _frame
    # Up 0.5% a bar: the index outruns the stock, so the RS rule refuses.
    return _frame([22900.0 * (1 + 0.005 * i) for i in range(n)], [1] * n)


def test_rs_fingerprint_changes_with_the_index_and_the_rule_constants(monkeypatch):
    import momentum_rs_pullback as rs
    from momentum_shadow import _frame_fingerprint
    from tests.test_oct19_audit_fixes import _falling_index, _leader
    falling, rising = _rs_rows(_falling_index), _rs_rows(_rising_index)
    assert falling["MOM_RS_PULLBACK"]["accepted"] != rising["MOM_RS_PULLBACK"]["accepted"]
    assert falling["MOM_RS_PULLBACK"]["dataset_fingerprint"] != rising["MOM_RS_PULLBACK"]["dataset_fingerprint"]
    config = falling["MOM_RS_PULLBACK"]["config"]
    assert config["rules"]["version"] == "rs_pullback_v1" and config["rules"]["rs_min_excess"] == 0.0075
    assert config["momentum_pool"] == 50000.0
    monkeypatch.setattr(rs, "RS_MIN_EXCESS", 1.0)
    changed = _rs_rows(_falling_index)["MOM_RS_PULLBACK"]
    assert changed["dataset_fingerprint"] != falling["MOM_RS_PULLBACK"]["dataset_fingerprint"]
    # The older variants keep exactly the identity they had: no index, no extras.
    for name in ("MOM_BASE", "MOM_RECENCY_5", "MOM_SELECTIVE"):
        assert falling[name]["dataset_fingerprint"] == rising[name]["dataset_fingerprint"] == \
            _frame_fingerprint("AAA", _leader(), falling[name]["config"])
        assert "rules" not in falling[name]["config"]


# ---------------------------------------------------------------------------
# S21-R3: the replay's runtime arm admits what the runtime admits
# ---------------------------------------------------------------------------

def _replay_one_pick(split_cash):
    import edge_portfolio_replay as epr
    from daily_portfolio import DailySignal
    days = ["2026-10-19", "2026-10-21"]
    bars = {"AAA": {d: {"open": 20.0, "high": 20.2, "low": 19.8, "close": 20.0, "volume": 10_000_000}
                    for d in days}}
    config = epr.EdgeReplayConfig(tickers=("AAA",), bankroll=25000.0, max_positions=3,
                                  policy="EDGE_OVERNIGHT_RUNTIME" if split_cash else "EDGE_OVERNIGHT")
    signal = DailySignal(ticker="AAA", signal_date=days[0], reference_price=20.0, stop=10.0, target=None,
                         planned_shares=2000, kind="MO_strong")

    def signals_at_close(day, equity):
        return [signal] if day == days[0] else []

    return epr.run_overnight_book(bars, days, end=days[0], signals_at_close=signals_at_close, config=config,
                                  costs=lambda *a: 0.0, split_cash=split_cash)


def test_replay_runtime_arm_matches_the_runtime_dust_floor():
    # The audit's counterexample: Rs 25,000, 3 slots, plan 2,000 at 20.05. The
    # runtime admits 415 (the floor is a quarter of the plan capped at equity/3);
    # the replay recorded CASH_REJECTED_DUST. It now fills the affordable 414
    # (the 0.2% buy-cost buffer is the declared difference).
    result = _replay_one_pick(split_cash=True)
    assert result["admission_outcomes"] == {"CASH_LIMITED_RESIZE": 1, "FILLED": 1}
    [trade] = [t for t in result["trades"] if t.get("ticker") == "AAA"]
    assert trade["shares"] == int((25000.0 / 3) // (20.05 * 1.002)) == 414
    # The study arm keeps its own (older) rule.
    assert _replay_one_pick(split_cash=False)["admission_outcomes"]["FILLED"] == 1


# ---------------------------------------------------------------------------
# S21-E1: the entry-day event window is checked at admission
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_edge_admission_rechecks_the_event_window_on_the_entry_date(tmp_path, monkeypatch):
    import event_calendar
    import penny_edge_orchestrator as peo
    from tests.test_oct13_audit_fixes import _Pos
    entries = []

    class Executor:
        async def execute_entry(self, **kw):
            entries.append(kw["ticker"])
            return {"entry_status": "paper", "fill_price": 10.0}

    async def not_entered(*_a):
        return False

    async def write(**_kw):
        return None

    def event_block(ticker, on_date, csv_path=None):
        # RESULTS on Oct 23 with a two-day window: Oct 19 (signal) is clear, Oct 21 (entry) is not.
        if ticker == "AAA" and on_date.isoformat() == "2026-10-21":
            return True, "event_window: RESULTS on 2026-10-23"
        return False, ""

    monkeypatch.setattr(event_calendar, "event_block", event_block)
    monkeypatch.setattr(peo.pel, "_rank_for_leg", lambda **kw: [_Pos("AAA"), _Pos("BBB")])
    monkeypatch.setattr(peo, "_executor_for", lambda *_a: Executor())
    monkeypatch.setattr(peo, "_already_entered_today", not_entered)
    monkeypatch.setattr(peo, "_write_edge_position", write)
    summary = await peo._run_one_leg(object(), str(tmp_path / "x.db"), "2026-10-21", "PAPER", peo.SOURCE_PAPER,
                                     100000.0, True, [object()])
    assert entries == ["BBB"]
    assert ("AAA", "entry_day_event_window: RESULTS on 2026-10-23") in summary["skipped"]
    assert summary["selected"] == ["AAA", "BBB"]


# ---------------------------------------------------------------------------
# S21-L1: restart overlap counts trading sessions only
# ---------------------------------------------------------------------------

def test_a_holiday_is_not_market_time_in_the_restart_receipt():
    import lifecycle_receipts as lr
    prior = IST.localize(datetime(2026, 10, 19, 22, 44)).timestamp()
    premarket = IST.localize(datetime(2026, 10, 21, 6, 15)).timestamp()
    receipt = lr.startup_receipt(settings.DB_PATH, {"ts_epoch": prior, "boot_id": "b0"}, premarket, "b1")
    # Oct 20 was Dussehra: zero session overlap, the raw weekday figure kept as evidence.
    assert receipt["market_overlap_sec"] == 0.0 and receipt["weekday_overlap_sec"] == 22500.0
    assert lr.restart_alert_text(receipt, {}) is None
    in_session = IST.localize(datetime(2026, 10, 21, 10, 0)).timestamp()
    receipt = lr.startup_receipt(settings.DB_PATH, {"ts_epoch": prior, "boot_id": "b0"}, in_session, "b2")
    assert receipt["market_overlap_sec"] == 45 * 60.0 and receipt["weekday_overlap_sec"] == 22500.0 + 45 * 60


# ---------------------------------------------------------------------------
# R21-M1: EDGE rows say what happened; ranking is not a gate
# ---------------------------------------------------------------------------

def test_edge_candidate_outcome_reports_the_real_reason():
    from penny_edge_orchestrator import edge_candidate_outcome
    paper = {"trades": [{"ticker": "AAA"}], "skipped": [("BBB", "entry_status=drift_rejected")],
             "selected": ["AAA", "BBB", "CCC"]}
    live = {"trades": [], "skipped": [("ALL", "live-master-disabled")], "selected": []}
    assert edge_candidate_outcome("AAA", paper, live) is None
    assert edge_candidate_outcome("BBB", paper, live) == "entry_status=drift_rejected"
    assert edge_candidate_outcome("CCC", paper, live) == "selected_not_entered"
    assert edge_candidate_outcome("ZZZ", paper, live) == "rank_not_selected"


async def _signal_day(db, day, rows):
    from penny_signal_log import init_penny_signal_db
    await init_penny_signal_db(db)
    async with aiosqlite.connect(db) as conn:
        for i, (accepted, reason) in enumerate(rows):
            await conn.execute(
                "INSERT INTO penny_signals (scan_id, scanned_at, ticker, leg, accepted, reject_reason) "
                "VALUES (?,?,?,?,?,?)", (f"EDGE-{day}", f"{day} 09:30:{i % 60:02d}", f"T{i}", "EDGE",
                                        int(accepted), reason))
        await conn.commit()


@pytest.mark.asyncio
async def test_rank_cuts_are_not_a_dead_gate_and_the_alert_names_the_real_reason():
    from penny_accept_watchdog import format_zero_accept_alert, zero_accept_scan
    db = settings.DB_PATH
    for day in ("2026-09-28", "2026-10-21"):
        await _signal_day(db, day, [(0, "rank_not_selected")] * 91 + [(0, "entry_status=drift_rejected")] * 3)
    payload = await zero_accept_scan(db, n_days=2, leg="EDGE")
    assert payload["dead_gate"] == "entry_status=drift_rejected"
    assert payload["not_a_gate"] == {"rank_not_selected": 182}
    text = format_zero_accept_alert(payload)
    assert "across the last 2 evaluation day(s) (2026-09-28 → 2026-10-21, leg=EDGE)" in text
    assert "consecutive" not in text and "unsatisfiable" not in text
    assert "Not a gate (selection by design): 182 rank_not_selected." in text


@pytest.mark.asyncio
async def test_rank_cuts_alone_never_name_a_gate():
    from penny_accept_watchdog import zero_accept_scan
    db = settings.DB_PATH
    for day in ("2026-10-16", "2026-10-21"):
        await _signal_day(db, day, [(0, "rank_not_selected")] * 50)
    payload = await zero_accept_scan(db, n_days=2, leg="EDGE")
    assert payload["dead_gate"] is None and payload["suspect_gate"] is None


@pytest.mark.asyncio
async def test_a_paper_entry_counts_as_an_edge_accept():
    import penny_edge_orchestrator as peo
    from penny_accept_watchdog import zero_accept_scan
    db = settings.DB_PATH
    cands = [SimpleNamespace(ticker=t, signal_subtype="MR", entry_price=10.0, stop_loss=9.5, target=11.0)
             for t in ("AAA", "BBB")]
    paper = {"trades": [{"ticker": "AAA"}], "skipped": [], "selected": ["AAA"]}
    live = {"trades": [], "skipped": [("ALL", "live-master-disabled")], "selected": []}
    await peo._log_edge_signals(db, "2026-10-21", cands, paper, live)
    async with aiosqlite.connect(db) as conn:
        rows = await (await conn.execute(
            "SELECT ticker, accepted, reject_reason FROM penny_signals WHERE leg='EDGE' ORDER BY ticker")).fetchall()
    assert [(t, a, r or None) for t, a, r in rows] == [("AAA", 1, None), ("BBB", 0, "rank_not_selected")]


# ---------------------------------------------------------------------------
# R21-M2: allocation and equity are both shown
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fno_hourly_shows_allocation_and_current_equity(db_path):
    from fno_hourly_report import build_hourly_report
    from performance import fmt_money, init_ledger
    await init_ledger(db_path)
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("INSERT INTO bankroll_ledger (timestamp, event_type, pnl, source) VALUES (?,?,?,?)",
                           ("2026-10-16T12:00:00+05:30", "TRADE_CLOSED", -23202.27, "FNO_PAPER"))
        await conn.commit()
    msg = await build_hourly_report(db_path, IST.localize(datetime(2026, 10, 21, 12, 0)), regime="R1")
    line = next(l for l in msg.split("\n") if "FNO_PAPER" in l)
    assert f"allocation={fmt_money(settings.FNO_PAPER_BANKROLL, 'FNO_PAPER')}" in line
    assert f"equity={fmt_money(settings.FNO_PAPER_BANKROLL - 23202.27, 'FNO_PAPER')}" in line
    assert "pool=" not in line


# ---------------------------------------------------------------------------
# O19-M1 follow-up: the heartbeat says whether it was delivered
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_heartbeat_reports_delivery(monkeypatch):
    import httpx
    import main

    class _Client:
        def __init__(self, status=None, error=None):
            self.status, self.error = status, error

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            if self.error:
                raise self.error
            return SimpleNamespace(status_code=self.status)

    when = datetime(2026, 10, 21, 11, 30)
    for client, expected in ((_Client(200), True), (_Client(413), False),
                             (_Client(error=httpx.ConnectError("down")), False)):
        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, _c=client, **k: _c)
        assert await main._notify_momentum_heartbeat(when, 500, 0, 0, [], 2500.0) is expected


# ---------------------------------------------------------------------------
# O21-ON: overnight forward shadows
# ---------------------------------------------------------------------------

def _wide_quote(c, v, day, first_ask):
    from tests.test_edge_overnight_paper import _quote
    quote = _quote(c, c * 1.01, c * 0.99, c, v, day)
    quote["depth"]["sell"] = [{"price": round(first_ask * (1 + 0.0005 * i), 2), "quantity": 20000, "orders": 3}
                              for i in range(5)]
    return quote


@pytest.fixture
def overnight(tmp_path, monkeypatch):
    import edge_overnight_paper as eop
    from tests.test_edge_overnight_paper import TODAY, _Kite, _at, _cache, _quote

    def pick(ticker):
        return SimpleNamespace(ticker=ticker, signal_subtype="MO_strong", adjusted_strength=1.0, shares=150)

    ranked = [pick("AAA"), pick("BBB")]
    monkeypatch.setattr("penny_edge_live.scan_today", lambda **_k: {"positions": ranked, "candidates": ranked})
    monkeypatch.setattr(eop, "universe_from_cache", lambda _db: ["AAA", "BBB"])
    monkeypatch.setattr(settings, "PENNY_EDGE_MAX_POSITIONS", 3)
    quotes = {"AAA": _quote(20.0, 20.2, 19.8, 20.0, 900000.0),
              # BBB's book starts 0.5% above LTP: its fill costs more than 0.35%.
              "BBB": _wide_quote(20.0, 900000.0, TODAY, 20.10),
              "NIFTYBEES": _quote(20.0, 20.1, 19.9, 20.0, 100000.0)}
    return SimpleNamespace(eop=eop, cache=_cache(tmp_path), kite=_Kite(quotes), at=_at, today=TODAY,
                           quote=_quote)


@pytest.mark.asyncio
async def test_shadows_take_their_own_positions_from_the_same_picks(overnight):
    eop, cache = overnight.eop, overnight.cache
    summary = await eop.run_overnight_entry(overnight.kite, cache, now=overnight.at(overnight.today, 15, 20))
    book = {o["ticker"]: o for o in summary["opened"]}
    assert set(book) == {"AAA", "BBB"}                       # the book is unchanged by its shadows
    assert book["AAA"]["shares"] == 150 and book["BBB"]["entry_price"] > 20.0 * 1.0035
    with sqlite3.connect(eop.overnight_db_path(cache)) as conn:
        rows = conn.execute("SELECT variant, ticker, shares, entry_price FROM edge_overnight_shadow_trades "
                            "ORDER BY variant, ticker").fetchall()
    two = {t: (s, p) for v, t, s, p in rows if v == "ON_TWO_LARGER"}
    tight = {t: (s, p) for v, t, s, p in rows if v == "ON_TIGHT_SPREAD"}
    # Two equal positions, each sized to half the book (not the scan's 150).
    assert set(two) == {"AAA", "BBB"}
    for shares, price in two.values():
        assert shares * price <= settings.EDGE_OVERNIGHT_PAPER_BANKROLL / 2
        assert shares * price > settings.EDGE_OVERNIGHT_PAPER_BANKROLL / 2 - 100
    # The tight-spread shadow keeps the book's sizing and refuses the wide fill.
    assert tight == {"AAA": (150, book["AAA"]["entry_price"])}
    assert summary["shadows"]["ON_TIGHT_SPREAD"]["skipped"] == 1


@pytest.mark.asyncio
async def test_shadows_exit_on_the_same_quotes_and_are_compared_with_the_book(overnight):
    from penny_risk import calc_penny_costs
    from tests.test_edge_overnight_paper import NEXT
    eop, cache = overnight.eop, overnight.cache
    await eop.run_overnight_entry(overnight.kite, cache, now=overnight.at(overnight.today, 15, 20))
    exit_quotes = {"AAA": overnight.quote(20.6, 20.8, 20.1, 20.3, 50000.0, NEXT),
                   "BBB": overnight.quote(20.2, 20.4, 20.0, 20.1, 50000.0, NEXT)}
    from tests.test_edge_overnight_paper import _Kite
    await eop.run_overnight_exit(_Kite(exit_quotes), cache, now=overnight.at(NEXT, 9, 17))
    with sqlite3.connect(eop.overnight_db_path(cache)) as conn:
        rows = conn.execute("SELECT variant, ticker, status, exit_price, net_pnl, entry_price, shares "
                            "FROM edge_overnight_shadow_trades").fetchall()
    assert rows and all(r[2] == "CLOSED" for r in rows)
    for variant, ticker, _status, exit_price, net, entry, shares in rows:
        open_price = 20.6 if ticker == "AAA" else 20.2
        assert exit_price == round(open_price * 0.9995, 4)
        assert net == pytest.approx((exit_price - entry) * shares - calc_penny_costs(entry, exit_price, shares, False),
                                    abs=1e-3)
    comparison = eop.overnight_shadow_comparison(cache)
    assert comparison["since"] == overnight.today.isoformat() and comparison["book"]["closed"] == 2
    by_name = {s["variant"]: s for s in comparison["shadows"]}
    assert by_name["ON_TWO_LARGER"]["closed"] == 2 and by_name["ON_TIGHT_SPREAD"]["closed"] == 1
    assert by_name["ON_TIGHT_SPREAD"]["config"] == {"slots": None, "fill_cash_share": False,
                                                    "max_entry_cost_pct": 0.0035}
    assert by_name["ON_TWO_LARGER"]["avg_position_value"] > 2 * comparison["book"]["avg_position_value"]


@pytest.mark.asyncio
async def test_shadows_can_be_switched_off(overnight, monkeypatch):
    monkeypatch.setattr(settings, "EDGE_OVERNIGHT_SHADOWS_ENABLED", False)
    eop, cache = overnight.eop, overnight.cache
    summary = await eop.run_overnight_entry(overnight.kite, cache, now=overnight.at(overnight.today, 15, 20))
    assert "shadows" not in summary
    with sqlite3.connect(eop.overnight_db_path(cache)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM edge_overnight_shadow_trades").fetchone()[0] == 0
    assert eop.overnight_shadow_comparison(cache)["since"] is None


def test_overnight_experiment_route(monkeypatch):
    import main  # noqa: F401
    import routes_penny_experiments as route
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    monkeypatch.setattr(main, "_check_internal_secret", lambda request, name: None)
    app = FastAPI()
    app.include_router(route.router)
    body = TestClient(app).get("/experiments/edge-overnight").json()
    assert body["declared"] == "2026-10-21" and body["research_only"] is True
