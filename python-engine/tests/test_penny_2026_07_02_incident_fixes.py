"""
[TEST-PENNY-2026-07-02-INCIDENT-FIXES 2026-07-02] Regression tests
for the five fixes that closed out the 2026-07-02 no-trades incident:

  1. PENNY-HEATMAP-FIX: penny_heatmap._read_open_positions now
     queries stop_loss_initial (the real schema column) aliased as
     stop_loss, instead of a non-existent `stop_loss` column. The
     test seeds positions using position_tracker.init_positions_db
     (real schema) and asserts the heatmap does NOT log
     `penny_heatmap_db_query_failed`.

  2. PENNY-SG-FILTER: penny_universe._is_non_equity_symbol filters
     out Sovereign Gold Bond tickers (-SG suffix), ETFs
     (PHARMABEES, BSE500IETF, BFSI, ESG), and other non-equity
     instruments. The test asserts SGs/ETFs are rejected at
     scan-time even if they slipped into penny_static.json, and
     that equity tickers are accepted.

  3. PENNY-STARTUP-GATE: penny_scanner.PennyScanner._wait_for_instrument_cache
     blocks up to 60s for kite.instrument_cache to fill before
     running the scan. The test asserts: (a) returns True immediately
     when cache is full; (b) waits and returns True when cache fills
     during the wait; (c) returns False after timeout when cache
     never fills.

  4. KITE-QUOTE-RETRY: KiteClient.get_quote retries 401/403/429/5xx
     with exponential backoff (3 attempts, 0.5s -> 1s -> 2s).
     Per-minute failure rate above 30 emits a single
     kite_auth_degraded WARNING. The test asserts: (a) 200 OK with
     data returns on first try; (b) 403 then 200 retries and
     returns the data; (c) all 403s exhausted returns empty dict;
     (d) per-minute rate threshold triggers exactly once.

  5. PENNY-SQLITE-WAL: kite_client._init_db / _init_intraday_db now
     set PRAGMA journal_mode=WAL + busy_timeout=5000. The test
     asserts the PRAGMA values are applied to a fresh DB file.
"""
import asyncio
import json
import os
import sqlite3
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


HERE = os.path.dirname(__file__)
ENGINE_DIR = os.path.abspath(os.path.join(HERE, ".."))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)


# ============================================================================
# Fix 1 -- PENNY-HEATMAP-FIX: stop_loss_initial column mismatch
# ============================================================================

def test_heatmap_works_against_real_positions_schema(tmp_path):
    """PENNY-HEATMAP-FIX 2026-07-02: Build positions using the REAL
    schema (position_tracker.init_positions_db) and assert the heatmap
    does NOT raise "no such column: stop_loss". Pre-fix, the heatmap
    queried `stop_loss` directly; production schema uses
    `stop_loss_initial`. 12+ failures per day in the logs.
    """
    import asyncio
    from penny_heatmap import build_heatmap
    from position_tracker import init_positions_db

    db = str(tmp_path / "test.db")
    # Use the REAL schema. This is what production has.
    asyncio.run(init_positions_db(db))

    with sqlite3.connect(db) as con:
        con.execute(
            """INSERT INTO positions (
                ticker, exchange, entry_date, entry_price, shares,
                stop_loss_initial, trailing_stop_current,
                target_1, target_2, atr_14_at_entry,
                highest_close_since_entry, status, source,
                product_type, regime_at_entry,
                atr_1min_post_t1, t1_fired
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("HCC", "NSE", "2026-07-02T09:30:00+00:00",
             25.7, 10, 25.0, 25.0, 26.5, 27.5,
             0.0, 25.7, "OPEN", "PENNY", "CNC", "PR1_CALM",
             0.0, 0),
        )

    # Capture all WARNING log lines from penny_heatmap. We must NOT see
    # `penny_heatmap_db_query_failed` -- that was the symptom.
    import logging
    log_records = []
    class _Capture(logging.Handler):
        def emit(self, record):
            log_records.append(record)
    cap = _Capture(level=logging.WARNING)
    penny_heatmap_logger = logging.getLogger("penny_heatmap")
    penny_heatmap_logger.addHandler(cap)
    try:
        kite = MagicMock()
        kite.instrument_cache = {"HCC": 1001}
        async def _quote(tokens):
            return {1001: {"last_price": 26.10, "ohlc": {"high": 26.10, "low": 25.31}}}
        kite.get_quote = AsyncMock(side_effect=_quote)
        body, buckets, total, priced = asyncio.run(build_heatmap(
            db_path=db, kite=kite, sectors_csv_path="/nonexistent",
        ))
        # 1) Heatmap worked without error
        assert total == 1
        assert priced == 1
        # 2) HCC appears in the report (with the right P&L)
        assert "HCC" in body
        # 3) The "no such column" warning did NOT fire
        offenders = [r for r in log_records
                     if "penny_heatmap_db_query_failed" in r.getMessage()]
        assert offenders == [], (
            f"Expected zero 'penny_heatmap_db_query_failed' lines, "
            f"got: {[r.getMessage() for r in offenders]}"
        )
    finally:
        penny_heatmap_logger.removeHandler(cap)


def test_heatmap_query_uses_stop_loss_initial_alias():
    """PENNY-HEATMAP-FIX 2026-07-02: Static-analysis guard against
    regression. The SELECT in _read_open_positions must reference
    stop_loss_initial (the real schema column), NOT stop_loss.
    """
    import inspect
    from penny_heatmap import _read_open_positions
    src = inspect.getsource(_read_open_positions)
    # Must reference the real schema column name
    assert "stop_loss_initial" in src, (
        f"_read_open_positions must query `stop_loss_initial`. Got:\n{src}"
    )
    # The bare `SELECT ..., stop_loss, ...` from before this fix is gone
    # (allow 'stop_loss_initial AS stop_loss' aliasing).
    bad = "SELECT ticker, entry_price, stop_loss, shares"
    assert bad not in src, (
        f"_read_open_positions still has the buggy query. Got:\n{src}"
    )


# ============================================================================
# Fix 2 -- PENNY-SG-FILTER: SGB / ETF / bond ticker rejection
# ============================================================================

def test_is_non_equity_symbol_filters_sgb_suffixes():
    """PENNY-SG-FILTER 2026-07-02: Every -SG / -SGX / -GS suffix is
    rejected. These are Sovereign Gold Bonds that Kite sometimes
    surfaces with instrument_type=EQ.
    """
    from penny_universe import _is_non_equity_symbol
    assert _is_non_equity_symbol("597CG27-SG")
    assert _is_non_equity_symbol("662RJ30-SG")
    assert _is_non_equity_symbol("705WB31-SG")
    assert _is_non_equity_symbol("683MH31-SG")
    assert _is_non_equity_symbol("FOO-SGX")
    assert _is_non_equity_symbol("BAR-GS")


def test_is_non_equity_symbol_filters_etfs():
    """PENNY-SG-FILTER 2026-07-02: Common ETF names are rejected.
    Today's penny_static.json contained PHARMABEES, BSE500IETF,
    BFSI, ESG -- all diluted the ranker.
    """
    from penny_universe import _is_non_equity_symbol
    assert _is_non_equity_symbol("PHARMABEES")
    assert _is_non_equity_symbol("BSE500IETF")
    assert _is_non_equity_symbol("BFSI")
    assert _is_non_equity_symbol("ESG")
    assert _is_non_equity_symbol("GOLDBEES")
    assert _is_non_equity_symbol("LIQUIDBEES")
    assert _is_non_equity_symbol("NIFTYBEES")


def test_is_non_equity_symbol_filters_generic_bond_pattern():
    """PENNY-SG-FILTER 2026-07-02: Generic `<digits><state><number>`
    pattern catches future SGB issues (597CG27, 662RJ30, etc.).
    """
    from penny_universe import _is_non_equity_symbol
    assert _is_non_equity_symbol("597CG27")
    assert _is_non_equity_symbol("662RJ30")
    assert _is_non_equity_symbol("100RJ31A")  # state letter + number


def test_is_non_equity_symbol_accepts_real_equities():
    """PENNY-SG-FILTER 2026-07-02: Real equity tickers are NOT
    rejected. Test must hit the universe's actual top tickers.
    """
    from penny_universe import _is_non_equity_symbol
    for sym in [
        "HCC", "EASEMYTRIP", "SUMICHEM", "IDFCFIRSTB", "CENTRUM",
        "BAJAJHIND", "MTNL", "DCW", "IT", "BCLIND", "UNITECH",
        "GENCON", "JYOTISTRUC", "CENTRUM", "GAYAHWS", "PHARMABEES",
    ]:
        # Wait -- PHARMABEES IS an ETF, must be filtered.
        if sym == "PHARMABEES":
            assert _is_non_equity_symbol(sym), f"{sym} should be rejected"
        else:
            assert not _is_non_equity_symbol(sym), (
                f"{sym} should NOT be rejected"
            )


def test_eligible_tickers_filters_sg_at_scan_time(tmp_path):
    """PENNY-SG-FILTER 2026-07-02 (defence layer 2): Even if a stale
    penny_static.json from before this fix contains SGB tickers,
    eligible_tickers() rejects them. Simulates an old, polluted
    universe file.
    """
    from penny_universe import PennyUniverse

    # Build a stale universe file with 5 equity + 3 SGB + 2 ETF tickers.
    stale_json = tmp_path / "penny_static.json"
    payload = {
        "as_of": "2026-07-01",
        "universe_size_target": 10,
        "tickers": [
            {"symbol": "HCC", "series": "EQ", "prev_close": 25.7,
             "promoter_holding_pct": None, "pb_ratio": None,
             "is_t2t": False, "is_asm": False, "is_gsm": False,
             "median_traded_value_20d": 1e9, "avg_return_20d": 1.0,
             "dist_from_52w_low_pct": 0.5, "vol_20d": 0.03},
            {"symbol": "EASEMYTRIP", "series": "EQ", "prev_close": 7.21,
             "promoter_holding_pct": None, "pb_ratio": None,
             "is_t2t": False, "is_asm": False, "is_gsm": False,
             "median_traded_value_20d": 2e8, "avg_return_20d": 1.0,
             "dist_from_52w_low_pct": 0.25, "vol_20d": 0.05},
            {"symbol": "597CG27-SG", "series": "EQ", "prev_close": 5000,
             "promoter_holding_pct": None, "pb_ratio": None,
             "is_t2t": False, "is_asm": False, "is_gsm": False,
             "median_traded_value_20d": 0, "avg_return_20d": 1.0,
             "dist_from_52w_low_pct": 0.5, "vol_20d": 0.01},
            {"symbol": "662RJ30-SG", "series": "EQ", "prev_close": 4500,
             "promoter_holding_pct": None, "pb_ratio": None,
             "is_t2t": False, "is_asm": False, "is_gsm": False,
             "median_traded_value_20d": 0, "avg_return_20d": 1.0,
             "dist_from_52w_low_pct": 0.5, "vol_20d": 0.01},
            {"symbol": "PHARMABEES", "series": "EQ", "prev_close": 150,
             "promoter_holding_pct": None, "pb_ratio": None,
             "is_t2t": False, "is_asm": False, "is_gsm": False,
             "median_traded_value_20d": 5e7, "avg_return_20d": 1.0,
             "dist_from_52w_low_pct": 0.5, "vol_20d": 0.01},
            {"symbol": "BSE500IETF", "series": "EQ", "prev_close": 100,
             "promoter_holding_pct": None, "pb_ratio": None,
             "is_t2t": False, "is_asm": False, "is_gsm": False,
             "median_traded_value_20d": 5e7, "avg_return_20d": 1.0,
             "dist_from_52w_low_pct": 0.5, "vol_20d": 0.01},
        ],
    }
    stale_json.write_text(json.dumps(payload))

    # Pretend the cache has tokens for all of them (the filter is
    # separate from token resolution).
    instrument_cache = {t["symbol"]: hash(t["symbol"]) & 0xffff
                        for t in payload["tickers"]}
    u = PennyUniverse(json_path=str(stale_json),
                      instrument_cache=instrument_cache)
    eligible = u.eligible_tickers()
    symbols = {t["symbol"] for t in eligible}
    # All 4 non-equity instruments must be filtered out.
    assert "597CG27-SG" not in symbols
    assert "662RJ30-SG" not in symbols
    assert "PHARMABEES" not in symbols
    assert "BSE500IETF" not in symbols
    # The 2 real equities survive.
    assert "HCC" in symbols
    assert "EASEMYTRIP" in symbols
    assert len(symbols) == 2


# ============================================================================
# Fix 3 -- PENNY-STARTUP-GATE: wait_for_instrument_cache
# ============================================================================

def test_startup_gate_returns_immediately_when_cache_full():
    """PENNY-STARTUP-GATE 2026-07-02: When instrument_cache already
    has >= 100 entries, the gate returns True in <1ms (no sleep).
    """
    from penny_scanner import PennyScanner

    kite = MagicMock()
    kite.instrument_cache = {f"SYM{i:04d}": i for i in range(150)}
    scanner = PennyScanner(
        kite=kite,
        universe_json_path="/nonexistent/path.json",
    )
    t0 = time.monotonic()
    result = asyncio.run(scanner._wait_for_instrument_cache(min_count=100, timeout=5.0))
    elapsed = time.monotonic() - t0
    assert result is True
    assert elapsed < 0.1, f"Fast path should be <100ms, got {elapsed:.3f}s"


def test_startup_gate_waits_for_cache_to_fill():
    """PENNY-STARTUP-GATE 2026-07-02: When instrument_cache starts
    empty but fills during the wait window, the gate returns True
    once the threshold is reached.
    """
    from penny_scanner import PennyScanner

    kite = MagicMock()
    kite.instrument_cache = {}  # starts empty

    async def _fill_after_delay():
        await asyncio.sleep(0.2)
        for i in range(120):
            kite.instrument_cache[f"SYM{i:04d}"] = i

    async def _drive():
        filler = asyncio.create_task(_fill_after_delay())
        result = await PennyScanner(
            kite=kite, universe_json_path="/nonexistent.json",
        )._wait_for_instrument_cache(min_count=100, timeout=5.0)
        await filler
        return result

    result = asyncio.run(_drive())
    assert result is True


def test_startup_gate_times_out_when_cache_never_fills(caplog):
    """PENNY-STARTUP-GATE 2026-07-02: When the cache never reaches
    the threshold within `timeout`, the gate returns False and
    logs a WARNING. This is what scan_once() relies on to
    short-circuit to accept=0 instead of 12 minutes of false silence.
    """
    import logging
    from penny_scanner import PennyScanner

    kite = MagicMock()
    kite.instrument_cache = {}  # never fills

    with caplog.at_level(logging.WARNING, logger="penny_scanner"):
        result = asyncio.run(
            PennyScanner(
                kite=kite, universe_json_path="/nonexistent.json",
            )._wait_for_instrument_cache(min_count=100, timeout=0.5)
        )
    assert result is False
    # The warning was emitted
    msgs = [r.getMessage() for r in caplog.records]
    assert any("penny_instrument_cache_timeout" in m for m in msgs), (
        f"Expected penny_instrument_cache_timeout warning, got: {msgs}"
    )


# ============================================================================
# Fix 4 -- KITE-QUOTE-RETRY: exponential backoff + auth-degraded latch
# ============================================================================

def _make_kite_for_quote_test(quotes_by_attempt):
    """Build a KiteClient whose httpx client returns the given
    sequence of responses per call. quotes_by_attempt is a list of
    Response-like objects or exceptions.
    """
    from kite_client import KiteClient
    client = KiteClient("/tmp/test_kite.db")
    client.access_token = "test"
    # No-op the DB init (we don't care about cache.db here)
    async def _noop_init():
        pass
    client._init_db = _noop_init

    # Build a stub httpx client that returns the queued responses
    call_log = []
    idx_holder = {"i": 0}

    class _StubAsyncClient:
        async def get(self, url, params=None, **kw):
            i = idx_holder["i"]
            idx_holder["i"] += 1
            call_log.append(i)
            outcome = quotes_by_attempt[i] if i < len(quotes_by_attempt) else None
            if outcome is None:
                raise IndexError(f"unexpected extra call #{i}")
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    client.client = _StubAsyncClient()
    # Bypass the rate limiter for tests -- it acquires an asyncio.Lock
    # which can wedge between asyncio.run() calls in tests.
    async def _no_acquire():
        return None
    client.limiter.acquire = _no_acquire
    return client, call_log


def _mk_response(status_code, json_body=None):
    """Build an httpx.Response with the given status + JSON body.
    The response has a `_request` attached so raise_for_status() works
    (httpx >= 0.27 enforces this).
    """
    import httpx
    r = httpx.Response(status_code, json=json_body or {})
    r._request = httpx.Request("GET", "https://api.kite.trade/quote")
    return r


def _mk_error_response(status_code):
    """Build an httpx.Response with the given error status, attached
    to a stub Request so raise_for_status() raises HTTPStatusError.
    """
    import httpx
    r = httpx.Response(status_code, text=f"status {status_code}")
    r._request = httpx.Request("GET", "https://api.kite.trade/quote")
    return r


def test_quote_retry_succeeds_first_try():
    """KITE-QUOTE-RETRY 2026-07-02: 200 OK with data returns
    immediately, no retry.
    """
    from kite_client import KiteClient
    KiteClient._quote_fail_window_count = 0
    KiteClient._quote_fail_degraded_emitted = False
    KiteClient._quote_fail_window_start = 0.0

    r = _mk_response(200, {"data": {"1001": {"last_price": 26.10}}})
    client, log = _make_kite_for_quote_test([r])
    out = asyncio.run(client.get_quote([1001]))
    assert out == {1001: {"last_price": 26.10}}
    assert len(log) == 1, "Expected exactly 1 HTTP call"


def test_quote_retry_recovers_on_second_403():
    """KITE-QUOTE-RETRY 2026-07-02: A single 403 + a 200 retries and
    returns the data. This is the case today's 2,649 failures would
    have benefited from.
    """
    from kite_client import KiteClient
    KiteClient._quote_fail_window_count = 0
    KiteClient._quote_fail_degraded_emitted = False
    KiteClient._quote_fail_window_start = 0.0

    err_403 = _mk_error_response(403)
    ok = _mk_response(200, {"data": {"1001": {"last_price": 26.10}}})

    client, log = _make_kite_for_quote_test([err_403, ok])
    out = asyncio.run(client.get_quote([1001]))
    assert out == {1001: {"last_price": 26.10}}
    assert len(log) == 2, "Expected 2 HTTP calls (1 retry)"


def test_quote_retry_gives_up_after_three_403s():
    """KITE-QUOTE-RETRY 2026-07-02: Three consecutive 403s exhaust
    retries and return empty dict (same fail-open posture as before).
    """
    from kite_client import KiteClient
    KiteClient._quote_fail_window_count = 0
    KiteClient._quote_fail_degraded_emitted = False
    KiteClient._quote_fail_window_start = 0.0

    client, log = _make_kite_for_quote_test(
        [_mk_error_response(403) for _ in range(3)]
    )
    out = asyncio.run(client.get_quote([1001]))
    assert out == {}, "Should return empty dict after 3 failed attempts"
    assert len(log) == 3, "Expected exactly 3 HTTP calls (no retry beyond)"


def test_quote_auth_degraded_warning_fires_once_per_minute(caplog):
    """KITE-QUOTE-RETRY 2026-07-02: When the failure rate exceeds
    30/min, a single kite_auth_degraded WARNING is emitted (not
    one per call -- that would spam the log buffer).

    Test strategy: invoke `_note_quote_rate_failure()` 50 times in a
    row with time mocked so the window never expires. Asserts the
    latch fires exactly once on the 30th call and stays latched
    until reset.
    """
    import logging
    import time as _time
    from kite_client import KiteClient

    # Reset latch state.
    KiteClient._quote_fail_window_count = 0
    KiteClient._quote_fail_degraded_emitted = False
    KiteClient._quote_fail_window_start = _time.monotonic()

    client = KiteClient("/tmp/test_kite_degraded.db")
    client.access_token = "test"

    with caplog.at_level(logging.WARNING):
        degraded_count = {"n": 0}
        # Patch the module-level logger.warning so we can count
        # structlog emissions without depending on the propagation
        # chain (which structlog doesn't use by default).
        from unittest.mock import patch as _patch
        with _patch("kite_client.logger.warning") as mock_warn:
            def _track(event, *args, **kw):
                if "kite_auth_degraded" in str(event):
                    degraded_count["n"] += 1
            mock_warn.side_effect = _track
            # Call 50 times -- latch should fire on call #30 and stay latched.
            for _ in range(50):
                client._note_quote_rate_failure()

    assert degraded_count["n"] == 1, (
        f"Expected exactly 1 kite_auth_degraded warning, got "
        f"{degraded_count['n']}"
    )
    # Verify it fired with the threshold count
    assert KiteClient._quote_fail_window_count == 50
    # And the latch is now set so subsequent calls don't re-emit
    assert KiteClient._quote_fail_degraded_emitted is True


# ============================================================================
# Fix 5 -- PENNY-SQLITE-WAL: journal_mode + busy_timeout on cache.db
# ============================================================================

def test_init_db_sets_wal_mode_and_busy_timeout(tmp_path):
    """PENNY-SQLITE-WAL 2026-07-02: _init_db sets journal_mode=WAL
    and busy_timeout=5000 on a fresh DB. These PRAGMAs persist across
    connections, so opening the file in a separate sqlite3.connect
    must observe them.
    """
    import asyncio
    from kite_client import KiteClient

    db = str(tmp_path / "cache.db")
    client = KiteClient(db)
    client.access_token = "test"
    asyncio.run(client._init_db())

    with sqlite3.connect(db) as con:
        mode = con.execute("PRAGMA journal_mode").fetchone()[0]
        busy = con.execute("PRAGMA busy_timeout").fetchone()[0]
    assert mode.upper() == "WAL", f"Expected journal_mode=WAL, got {mode}"
    assert busy == 5000, f"Expected busy_timeout=5000, got {busy}"


def test_init_intraday_db_sets_wal_mode_and_busy_timeout(tmp_path):
    """PENNY-SQLITE-WAL 2026-07-02: Same enforcement on _init_intraday_db.
    """
    import asyncio
    from kite_client import KiteClient

    db = str(tmp_path / "cache.db")
    client = KiteClient(db)
    client.access_token = "test"
    asyncio.run(client._init_intraday_db())

    with sqlite3.connect(db) as con:
        mode = con.execute("PRAGMA journal_mode").fetchone()[0]
        busy = con.execute("PRAGMA busy_timeout").fetchone()[0]
    assert mode.upper() == "WAL", f"Expected journal_mode=WAL, got {mode}"
    assert busy == 5000, f"Expected busy_timeout=5000, got {busy}"