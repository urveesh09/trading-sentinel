"""[S23] Runtime fixes from the Oct 23 audit."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _engine_service(compose: str) -> str:
    match = re.search(r"\n  python-engine:\n(.*?)(?=\n  \S)", compose, re.S)
    assert match, "python-engine service not found"
    return match.group(1)


@pytest.mark.skipif(not (ROOT / "docker-compose.yml").exists(), reason="repository checkout only")
def test_the_engine_gets_time_to_shut_down_cleanly():
    # [S23-SG] uvicorn graceful wait + liveness join + background drain +
    # exit-path writer, each bounded, must fit the compose stop grace.
    service = _engine_service((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    grace = re.search(r"stop_grace_period:\s*(\d+)s", service)
    assert grace and int(grace.group(1)) >= 10 + 10 + 5 + 5 + 10
    dockerfile = (ROOT / "python-engine" / "Dockerfile").read_text(encoding="utf-8")
    cmd = re.search(r'^CMD \[(.*)\]$', dockerfile, re.M).group(1)
    assert '"--timeout-graceful-shutdown", "10"' in cmd


def test_a_second_terminal_pass_runs_after_the_close():
    # [S23-R1] Oct 23: two trades had no 15:15 bar at 15:32. A 16:05 pass
    # re-reads the trades still without a CLOSED event.
    import ast
    tree = ast.parse((ROOT / "python-engine" / "main.py").read_text(encoding="utf-8"))
    jobs = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "add_job":
            kw = {}
            for k in node.keywords:
                if k.arg in ("id", "hour", "minute", "kwargs"):
                    try:
                        kw[k.arg] = ast.literal_eval(k.value)
                    except ValueError:      # a loop variable (the scan grid)
                        pass
            jobs[kw.get("id")] = kw
    first, retry = jobs["momentum_shadow_terminal"], jobs["momentum_shadow_terminal_retry"]
    assert (first["hour"], first["minute"]) == (15, 32)
    assert (retry["hour"], retry["minute"], retry["kwargs"]) == (16, 5, {"pass_name": "retry"})


@pytest.mark.asyncio
async def test_the_retry_pass_resolves_what_the_first_left_censored(monkeypatch):
    import main
    import pytz
    from datetime import datetime
    seen = []

    async def resolve(_db, day, _fetch):
        seen.append(day)
        return {"open": 2, "closed": 2, "censored": 0, "tickers": 2}

    async def trading(_d, _db):
        return True

    monkeypatch.setattr(main, "resolve_momentum_shadow_day", resolve)
    monkeypatch.setattr(main, "is_trading_day", trading)
    when = pytz.timezone("Asia/Kolkata").localize(datetime(2026, 10, 23, 16, 5))
    assert (await main.run_momentum_shadow_terminal(when, pass_name="retry"))["closed"] == 2
    assert seen == ["2026-10-23"]


@pytest.mark.parametrize("symbol, non_equity", [
    ("GOLDSHINAV", True), ("TECHINAV", True), ("SBIVALINAV", True), ("ITBEESINAV", True),
    ("MTNL", False), ("FISCHER", False), ("GLOTTIS", False), ("INAVRIA", False),
])
def test_etf_indicative_navs_are_not_equities(symbol, non_equity):
    # [S23-U1] 251 of Oct 23's 259 skipped histories were empty responses;
    # every sampled one was an ETF iNAV that Kite lists as EQ.
    from penny_universe import _is_non_equity_symbol
    assert _is_non_equity_symbol(symbol) is non_equity


def test_the_login_nudge_quotes_the_measured_refresh(tmp_path, monkeypatch):
    # [S23-M1] Oct 23 the nudge said "~55 min"; the refresh took 337.7 s.
    import daily_bootstrap as boot
    from config import settings
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "cache.db"))
    assert boot.last_universe_refresh() is None
    assert "needs the token" in boot.login_nudge_text(None, ["penny_universe"])
    boot.record_universe_refresh(337.7)
    timing = boot.last_universe_refresh()
    assert timing["penny_universe_sec"] == 337.7
    text = boot.login_nudge_text({"penny_universe_sec": 337.7, "at": "2026-10-23T08:00:29+05:30"},
                                 ["penny_universe", "fno_instruments"])
    assert "~6 min last time (23 Oct)" in text and "55" not in text
    assert text.endswith("Pending: penny_universe, fno_instruments.")
    (tmp_path / "daily_bootstrap_timing.json").write_text("{torn", encoding="utf-8")
    assert boot.last_universe_refresh() is None


def _oct23_books(tmp_path, monkeypatch):
    """The three books as they stood after Oct 23 (audit F1/F3/F5/F6)."""
    import json
    import sqlite3
    from config import settings
    monkeypatch.setattr(settings, "PENNY_SMART_V2_ENABLED", True)
    db = str(tmp_path / "cache.db")
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE bankroll_ledger (id INTEGER PRIMARY KEY, timestamp TEXT, event_type TEXT, "
                     "ticker TEXT, pnl REAL, source TEXT)")
        conn.executemany("INSERT INTO bankroll_ledger (timestamp,event_type,ticker,pnl,source) VALUES (?,?,?,?,?)", [
            ("2026-10-22T10:15:00.182683+00:00", "TRADE_CLOSED", "DCMSRIND", -2489.9696, "EDGE_PAPER"),  # Oct 22
            ("2026-10-22T19:00:00+00:00", "TRADE_CLOSED", "LATE", 7.0, "EDGE_PAPER"),     # 00:30 IST Oct 23
        ])
    with sqlite3.connect(db + ".penny-smart-paper.db") as conn:
        conn.execute("CREATE TABLE penny_smart_paper_events (event_id TEXT PRIMARY KEY, policy TEXT, at TEXT, "
                     "ticker TEXT, kind TEXT, payload_json TEXT)")
        for i, (policy, at, net) in enumerate([
                ("PEN_SMART_V1", "2026-10-23T13:09:15+05:30", -2.9966),
                ("PEN_SMART_V1", "2026-10-23T15:00:16+05:30", 19.3988),
                ("PEN_SMART_V2", "2026-10-23T13:10:15+05:30", -2.8372),
                ("PEN_SMART_V2", "2026-10-23T15:00:17+05:30", 13.8563),
                ("PEN_SMART_V1", "2026-10-22T14:00:00+05:30", -22.6164)]):
            conn.execute("INSERT INTO penny_smart_paper_events VALUES (?,?,?,?,?,?)",
                         (str(i), policy, at, "X", "EXIT_FILLED", json.dumps({"net_pnl": net})))
    import edge_overnight_paper as overnight
    with overnight._store(overnight.overnight_db_path(db)) as conn:
        rows = [("2026-10-22", "MTNL", "CLOSED", "2026-10-23", -494.9329, 25.0926, 320),
                ("2026-10-23", "FISCHER", "OPEN", None, None, 25.0525, 317),
                ("2026-10-23", "GLOTTIS", "OPEN", None, None, 54.8568, 144),
                ("2026-10-23", "HEADSUP", "OPEN", None, None, 5.9147, 427)]
        for trade_date, ticker, status, exit_date, net, price, shares in rows:
            conn.execute("INSERT INTO edge_overnight_paper_trades (trade_date,ticker,kind,strength,entry_ltp,"
                         "entry_price,shares,entry_ts,status,exit_date,net_pnl) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (trade_date, ticker, "X", 1.0, price, price, shares, "t", status, exit_date, net))
    return db


def test_the_digest_reports_every_book(tmp_path, monkeypatch):
    # [S23-M2] Oct 23's digest said "+Rs 0"; the closed day was -478.53.
    from datetime import date
    from day_books import all_books_day, format_all_books
    from operator_status import format_eod_digest
    db = _oct23_books(tmp_path, monkeypatch)
    books = all_books_day(db, date(2026, 10, 23))
    assert books["main"] == {"closes": 1, "net": 7.0}                       # by IST date, not UTC
    assert books["smart"]["PEN_SMART_V1"] == {"closes": 2, "net": 16.4022}
    assert books["smart"]["PEN_SMART_V2"] == {"closes": 2, "net": 11.0191}
    assert books["overnight"] == {"closes": 1, "net": -494.9329, "open": 3, "open_principal": 18366.6}
    assert books["closed_subtotal"] == round(7.0 + 16.4022 - 494.9329, 4) and books["subtotal_complete"]
    lines = format_all_books(books)
    assert "  Smart V1: Rs +16.40 (2 closes)" in lines
    assert "  Overnight: Rs -494.93 (1 close); holding 3, Rs 18,366.60 at entry" in lines
    assert "  Smart V2 (parallel experiment, not added): Rs +11.02 (2 closes)" in lines
    snap = {"penny": {"regime": "PR2_ELEVATED", "pnl_today": 0.0, "open_positions": 0},
            "nifty": {"market_regime": "BEAR_RS_ONLY", "pnl_today": 0.0, "open_positions": 0},
            "halted": False, "halt_reasons": [], "all_books": books}
    body = format_eod_digest(snap)
    assert "Classic Penny: +Rs 0" in body and "Closed subtotal: Rs -471.53" in body


def test_an_unreadable_book_is_unavailable_not_zero(tmp_path, monkeypatch):
    from datetime import date
    from day_books import all_books_day, format_all_books
    db = _oct23_books(tmp_path, monkeypatch)
    import sqlite3
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TABLE bankroll_ledger")
    books = all_books_day(db, date(2026, 10, 23))
    assert books["main"] is None and books["unavailable"] == ["main:OperationalError"]
    lines = format_all_books(books)
    assert "  Main ledger: unavailable" in lines
    assert any("overnight, partial)" in line for line in lines)


from tests.test_oct21_audit_fixes import overnight  # noqa: E402,F401  (fixture)


@pytest.mark.asyncio
async def test_overnight_trades_record_the_spread_and_the_exit_bid(overnight):
    # [S23-S1] Oct 23: GLOTTIS/HEADSUP passed ON_TIGHT_SPREAD with ~3% displayed
    # spreads, and the exit is modelled at the open less 5 bp although it runs
    # at 09:17. Both are now recorded so the comparison can measure them.
    import sqlite3
    from penny_risk import calc_penny_costs
    from tests.test_edge_overnight_paper import NEXT, _Kite
    eop, cache = overnight.eop, overnight.cache
    await eop.run_overnight_entry(overnight.kite, cache, now=overnight.at(overnight.today, 15, 20))
    store = eop.overnight_db_path(cache)
    with sqlite3.connect(store) as conn:
        entry = dict(((t, (b, a)) for t, b, a in conn.execute(
            "SELECT ticker, entry_bid, entry_ask FROM edge_overnight_paper_trades")))
    assert entry["AAA"] == (19.99, 20.01)                    # best bid / best ask at entry
    exit_quotes = {"AAA": overnight.quote(20.6, 20.8, 20.1, 20.3, 50000.0, NEXT),
                   "BBB": overnight.quote(20.2, 20.4, 20.0, 20.1, 50000.0, NEXT)}
    await eop.run_overnight_exit(_Kite(exit_quotes), cache, now=overnight.at(NEXT, 9, 17))
    with sqlite3.connect(store) as conn:
        rows = {t: r for t, *r in conn.execute(
            "SELECT ticker, entry_price, shares, net_pnl, exit_bid, exit_bid_net, entry_day_close "
            "FROM edge_overnight_paper_trades")}
    entry_price, shares, net, bid, bid_net, day_close = rows["AAA"]
    assert bid == 20.29 and day_close == 20.0
    assert bid_net == pytest.approx((bid - entry_price) * shares - calc_penny_costs(entry_price, bid, shares, False),
                                    abs=1e-3)
    with sqlite3.connect(store) as conn:
        shadow_bids = conn.execute("SELECT COUNT(*) FROM edge_overnight_shadow_trades "
                                   "WHERE exit_bid IS NOT NULL AND entry_bid IS NOT NULL").fetchone()[0]
    assert shadow_bids == 3                                   # both shadows record the same fields
    realism = eop.overnight_shadow_comparison(cache)["book"]["realism"]
    assert realism["exit_at_bid"]["closes"] == 2 and realism["entry_at_close"]["closes"] == 2
    model_minus_bid = sum(r[2] - r[4] for r in rows.values())
    assert realism["exit_at_bid"]["model_minus_bid"] == pytest.approx(model_minus_bid, abs=0.01)
    assert realism["exit_at_bid"]["model_minus_bid"] > 0      # the open-auction model sits above the bid
    assert realism["entry_spread_pct"] == pytest.approx(
        (100 * (20.01 - 19.99) / 20.0 + 100 * (20.10 - 19.99) / 20.0) / 2, abs=0.001)


def test_the_comparison_reads_a_store_from_before_the_new_fields(overnight):
    import sqlite3
    eop, cache = overnight.eop, overnight.cache
    store = eop.overnight_db_path(cache)
    with sqlite3.connect(store) as conn:
        conn.execute(eop._SCHEMA[0])
        conn.execute(eop._SCHEMA[3])
        conn.execute("INSERT INTO edge_overnight_paper_trades (trade_date,ticker,kind,strength,entry_ltp,entry_price,"
                     "shares,entry_ts,status,exit_date,net_pnl,costs) VALUES ('2026-10-22','MTNL','X',1,25.03,25.0926,"
                     "320,'t','CLOSED','2026-10-23',-494.9329,32.7249)")
        conn.execute("INSERT INTO edge_overnight_shadow_trades (variant,trade_date,ticker,kind,entry_ltp,entry_price,"
                     "shares,entry_ts,status) VALUES ('ON_TIGHT_SPREAD','2026-10-22','MTNL','X',25.03,25.0926,320,'t',"
                     "'OPEN')")
    comparison = eop.overnight_shadow_comparison(cache)
    assert comparison["book"]["closed"] == 1 and comparison["book"]["net_pnl"] == -494.93
    assert comparison["book"]["realism"]["exit_at_bid"] == {"closes": 0, "net": 0, "model_minus_bid": 0}


@pytest.mark.asyncio
async def test_a_short_quote_batch_names_the_missing_symbols(tmp_path, monkeypatch):
    # [S23-Q1] Oct 23 15:20: "requested=15 returned=0" with no names.
    import kite_client
    from tests.test_oct12_audit_fixes import _Resp, _budget_client
    client = _budget_client(tmp_path, rate=50.0)
    warnings = []

    class _Log:
        def warning(self, message, *args, **_kw):
            warnings.append(message % args if args else message)

        def __getattr__(self, _name):
            return lambda *a, **k: None

    monkeypatch.setattr(kite_client, "logger", _Log())

    async def fake_get(path, params=None):
        return _Resp(data={"NSE:AAA": {"last_price": 1.0}})

    monkeypatch.setattr(client.client, "get", fake_get)
    result, timing = await client.get_quote_by_instruments_with_timing(
        {1: "NSE:AAA", 2: "NSE:HEADSUP", 3: "NSE:GLOTTIS"})
    assert sorted(result) == [1] and timing["outcome"] == "PARTIAL"
    assert warnings == ["kite_quote_instrument_partial requested=3 returned=1 missing=NSE:GLOTTIS,NSE:HEADSUP"]
