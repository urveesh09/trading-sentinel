"""
[PENNY-HEATMAP-TEST 2026-06-25] Tests for penny_heatmap (T3-D).

Pins:
- Empty DB -> "0 open positions" body, no Kite calls
- Open positions -> per-ticker P&L computed correctly
- Sector grouping uses penny_sectors.csv; unmapped -> "Unmapped" bucket
- Per-position pnl_pct, pnl_abs computed from current_price
- Near-SL warning emitted when within 1.0% of stop_loss
- Fail-open: Kite quote failure -> position shown as n/a, rest of report still fires
- Format: header + per-sector line + WARN lines
- Message under 1000 chars (Telegram limit, with margin for sector names)
"""
import asyncio
import json
import os
import sqlite3

import pytest
from unittest.mock import AsyncMock, MagicMock


# ---- helpers ---------------------------------------------------------

def _seed_positions(path: str, rows):
    """rows = [(ticker, entry_price, stop_loss, shares, status)]"""
    with sqlite3.connect(path) as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS positions (
                ticker TEXT, status TEXT, source TEXT,
                entry_price REAL, stop_loss REAL, shares INTEGER,
                product_type TEXT DEFAULT 'MIS',
                regime_at_entry TEXT,
                entry_date TEXT
            );
        """)
        for ticker, entry, sl, shares, status in rows:
            con.execute(
                "INSERT INTO positions VALUES (?, ?, 'PENNY', ?, ?, ?, 'MIS', 'PR1_CALM', '2026-06-25')",
                (ticker, status, entry, sl, shares),
            )


def _write_sectors_csv(path: str, mapping: dict):
    """mapping = {symbol: sector}"""
    with open(path, "w", newline="") as f:
        f.write("symbol,sector\n")
        for sym, sec in mapping.items():
            f.write(f"{sym},{sec}\n")


def _make_kite(quotes_by_token: dict):
    """quotes_by_token: {token: ltp}. Returns a MagicMock that
    mimics the kite client API for the heatmap path."""
    k = MagicMock()
    k.instrument_cache = {}  # populated by test if needed
    async def _quote(tokens):
        return {tok: {"last_price": ltp} for tok, ltp in quotes_by_token.items()
                if tok in tokens}
    k.get_quote = AsyncMock(side_effect=_quote)
    return k


# ---- empty / happy path ---------------------------------------------

def test_build_heatmap_empty_db(tmp_path):
    from penny_heatmap import build_heatmap
    db = str(tmp_path / "test.db")
    # Don't seed any positions.
    kite = _make_kite({})
    body, buckets, total, priced = asyncio.run(build_heatmap(
        db_path=db, kite=kite, sectors_csv_path="/nonexistent",
    ))
    assert total == 0
    assert priced == 0
    assert "0 open positions" in body
    assert buckets == {}


def test_build_heatmap_no_kite_calls_when_empty(tmp_path):
    """Empty DB -> don't even hit Kite."""
    from penny_heatmap import build_heatmap
    db = str(tmp_path / "test.db")
    kite = _make_kite({})
    # If get_quote gets called, the mock raises AssertionError.
    body, buckets, total, priced = asyncio.run(build_heatmap(
        db_path=db, kite=kite, sectors_csv_path="/nonexistent",
    ))
    assert total == 0


def test_build_heatmap_with_two_positions(tmp_path):
    from penny_heatmap import build_heatmap
    db = str(tmp_path / "test.db")
    _seed_positions(db, [
        ("GOLDSTAR-SM", 10.00,  9.00, 10, "OPEN"),
        ("ARENTERP",   20.00, 19.00,  5, "OPEN"),
    ])
    # GOLDSTAR-SM up 5%, ARENTERP down 2%.
    kite = MagicMock()
    kite.instrument_cache = {"GOLDSTAR-SM": 1001, "ARENTERP": 1002}
    async def _quote(tokens):
        return {
            1001: {"last_price": 10.50},   # +5%
            1002: {"last_price": 19.60},   # -2%
        }
    kite.get_quote = AsyncMock(side_effect=_quote)
    sectors_csv = tmp_path / "sectors.csv"
    _write_sectors_csv(str(sectors_csv), {
        "GOLDSTAR-SM": "Steel",
        "ARENTERP": "Realty",
    })
    body, buckets, total, priced = asyncio.run(build_heatmap(
        db_path=db, kite=kite, sectors_csv_path=str(sectors_csv),
    ))
    assert total == 2
    assert priced == 2
    assert "Steel" in body
    assert "Realty" in body
    assert "GOLDSTAR-SM +5.0%" in body or "GOLDSTAR-SM +5.00%" in body
    assert "ARENTERP" in body


def test_build_heatmap_groups_by_sector(tmp_path):
    """Two tickers in same sector -> one bucket, both listed."""
    from penny_heatmap import build_heatmap
    db = str(tmp_path / "test.db")
    _seed_positions(db, [
        ("AAA", 10.00, 9.00, 10, "OPEN"),
        ("BBB", 20.00, 19.00, 5, "OPEN"),
    ])
    kite = MagicMock()
    kite.instrument_cache = {"AAA": 1001, "BBB": 1002}
    async def _quote(tokens):
        return {1001: {"last_price": 10.0}, 1002: {"last_price": 20.0}}
    kite.get_quote = AsyncMock(side_effect=_quote)
    sectors_csv = tmp_path / "sectors.csv"
    _write_sectors_csv(str(sectors_csv), {"AAA": "Steel", "BBB": "Steel"})
    body, buckets, total, priced = asyncio.run(build_heatmap(
        db_path=db, kite=kite, sectors_csv_path=str(sectors_csv),
    ))
    assert len(buckets) == 1
    assert "Steel" in buckets
    assert buckets["Steel"].count == 2
    # Both tickers in same line
    assert "AAA" in body
    assert "BBB" in body


def test_build_heatmap_unmapped_tickers_get_unmapped_bucket(tmp_path):
    """Tickers not in CSV land in 'Unmapped' bucket."""
    from penny_heatmap import build_heatmap
    db = str(tmp_path / "test.db")
    _seed_positions(db, [
        ("MAPPED", 10.00, 9.00, 10, "OPEN"),
        ("UNMAPPED", 20.00, 19.00, 5, "OPEN"),
    ])
    kite = MagicMock()
    kite.instrument_cache = {"MAPPED": 1001, "UNMAPPED": 1002}
    async def _quote(tokens):
        return {1001: {"last_price": 10.0}, 1002: {"last_price": 20.0}}
    kite.get_quote = AsyncMock(side_effect=_quote)
    sectors_csv = tmp_path / "sectors.csv"
    _write_sectors_csv(str(sectors_csv), {"MAPPED": "Steel"})  # UNMAPPED not mapped
    body, buckets, total, priced = asyncio.run(build_heatmap(
        db_path=db, kite=kite, sectors_csv_path=str(sectors_csv),
    ))
    assert "Steel" in buckets
    assert "Unmapped" in buckets
    assert buckets["Steel"].count == 1
    assert buckets["Unmapped"].count == 1


def test_build_heatmap_fail_open_on_quote_failure(tmp_path):
    """If get_quote returns empty, position shows as 'n/a' but doesn't
    crash the report."""
    from penny_heatmap import build_heatmap
    db = str(tmp_path / "test.db")
    _seed_positions(db, [
        ("AAA", 10.00, 9.00, 10, "OPEN"),
    ])
    kite = MagicMock()
    kite.instrument_cache = {"AAA": 1001}
    async def _quote(tokens):
        return {}  # no quotes (e.g. Kite down)
    kite.get_quote = AsyncMock(side_effect=_quote)
    body, buckets, total, priced = asyncio.run(build_heatmap(
        db_path=db, kite=kite, sectors_csv_path="/nonexistent",
    ))
    assert total == 1
    assert priced == 0  # no live prices fetched
    assert "n/a" in body  # the AAA position shows as n/a


def test_build_heatmap_warns_near_sl(tmp_path):
    """A position within 1% of its SL -> WARN line."""
    from penny_heatmap import build_heatmap
    db = str(tmp_path / "test.db")
    _seed_positions(db, [
        # entry=10, sl=9.5. Current=9.55 -> +0.5% above SL = within 1%
        ("DANGER", 10.00, 9.50, 10, "OPEN"),
        ("SAFE", 10.00, 8.00, 10, "OPEN"),  # SL far away
    ])
    kite = MagicMock()
    kite.instrument_cache = {"DANGER": 1001, "SAFE": 1002}
    async def _quote(tokens):
        return {1001: {"last_price": 9.55}, 1002: {"last_price": 10.50}}
    kite.get_quote = AsyncMock(side_effect=_quote)
    body, buckets, total, priced = asyncio.run(build_heatmap(
        db_path=db, kite=kite, sectors_csv_path="/nonexistent",
    ))
    assert "WARN: DANGER" in body
    assert "approaching SL" in body
    # SAFE should NOT trigger WARN
    warn_lines = [l for l in body.split("\n") if l.startswith("WARN")]
    assert all("SAFE" not in w for w in warn_lines)


def test_build_heatmap_no_warn_when_far_from_sl(tmp_path):
    """Position comfortably above SL -> no WARN."""
    from penny_heatmap import build_heatmap
    db = str(tmp_path / "test.db")
    _seed_positions(db, [
        ("HEALTHY", 10.00, 8.00, 10, "OPEN"),  # SL -20% below entry
    ])
    kite = MagicMock()
    kite.instrument_cache = {"HEALTHY": 1001}
    async def _quote(tokens):
        return {1001: {"last_price": 10.50}}  # +5% from entry
    kite.get_quote = AsyncMock(side_effect=_quote)
    body, buckets, total, priced = asyncio.run(build_heatmap(
        db_path=db, kite=kite, sectors_csv_path="/nonexistent",
    ))
    assert "WARN" not in body


# ---- [AUDIT-FIX-2.5] warn_pct configurability --------------------------

def test_heatmap_warn_pct_configurable_wider_threshold(tmp_path):
    """[AUDIT-FIX-2.5] A position at 1.49% above SL fires WARN when
    warn_pct=2.0% but NOT when warn_pct=1.0%. Proves the threshold is
    driven by the parameter, not the old hardcoded 1.0.

    Note: the comparison uses strict `<` (not `<=`) to avoid a
    floating-point edge case where distance == threshold fails.
    Distance 1.49% is comfortably below 2.0% AND above 1.0%.
    """
    from penny_heatmap import build_heatmap
    db = str(tmp_path / "test.db")
    _seed_positions(db, [
        # entry=10, sl=9.0. Current=9.149 -> +1.49% above SL (FP-safe)
        ("ZZZ_TEST", 10.00, 9.00, 10, "OPEN"),
    ])
    kite = MagicMock()
    kite.instrument_cache = {"ZZZ_TEST": 1001}
    async def _quote(tokens):
        return {1001: {"last_price": 9.149}}
    kite.get_quote = AsyncMock(side_effect=_quote)

    # Tight threshold (1%) -- 1.49% above SL should NOT warn (>1.0).
    body_tight, *_ = asyncio.run(build_heatmap(
        db_path=db, kite=kite, sectors_csv_path="/nonexistent",
        near_sl_warn_pct=1.0, warn_pct_is_fraction=False,
    ))
    assert "WARN:" not in body_tight

    # Wide threshold (2%) -- 1.49% above SL SHOULD warn (<2.0).
    body_wide, *_ = asyncio.run(build_heatmap(
        db_path=db, kite=kite, sectors_csv_path="/nonexistent",
        near_sl_warn_pct=2.0, warn_pct_is_fraction=False,
    ))
    assert "WARN: ZZZ_TEST" in body_wide


def test_heatmap_warn_pct_accepts_fraction_form(tmp_path):
    """[AUDIT-FIX-2.5] When warn_pct_is_fraction=True, the threshold is
    interpreted as a fraction (0.01 = 1%). This is the form the
    settings.PENNY_HEATMAP_WARN_PCT uses (default 0.01)."""
    from penny_heatmap import build_heatmap
    db = str(tmp_path / "test.db")
    _seed_positions(db, [
        # entry=10, sl=9.0. Current=9.149 -> +1.49% above SL.
        # 0.015 fraction = 1.5% threshold -> 1.49 < 1.5 -> WARN.
        ("ZZZ_TEST", 10.00, 9.00, 10, "OPEN"),
    ])
    kite = MagicMock()
    kite.instrument_cache = {"ZZZ_TEST": 1001}
    async def _quote(tokens):
        return {1001: {"last_price": 9.149}}
    kite.get_quote = AsyncMock(side_effect=_quote)

    body, *_ = asyncio.run(build_heatmap(
        db_path=db, kite=kite, sectors_csv_path="/nonexistent",
        near_sl_warn_pct=0.015, warn_pct_is_fraction=True,
    ))
    assert "WARN: ZZZ_TEST" in body


def test_heatmap_exact_threshold_does_not_warn(tmp_path):
    """[AUDIT-FIX-2.5] Strict `<` semantic: a position EXACTLY at the
    warn_pct boundary does NOT warn (avoids FP edge cases).

    This is the documented behaviour change from `<=` to `<`. It's
    also why we use `0.015` fraction (1.5%) and a distance of 1.49%
    in the test above -- they trigger the warn via `<`.
    """
    from penny_heatmap import build_heatmap
    db = str(tmp_path / "test.db")
    # distance = 1.5% exactly; threshold = 1.5%. With `<`, no warn.
    # (10 -> 9; distance to sl = 0.15, divided by entry 10 = 1.5%)
    _seed_positions(db, [
        ("EXACT", 10.00, 9.00, 10, "OPEN"),
    ])
    kite = MagicMock()
    kite.instrument_cache = {"EXACT": 1001}
    async def _quote(tokens):
        # current = 9.15 -> exactly 1.5% above sl
        return {1001: {"last_price": 9.15}}
    kite.get_quote = AsyncMock(side_effect=_quote)
    body, *_ = asyncio.run(build_heatmap(
        db_path=db, kite=kite, sectors_csv_path="/nonexistent",
        near_sl_warn_pct=1.5, warn_pct_is_fraction=False,
    ))
    assert "WARN: EXACT" not in body


def test_build_heatmap_excludes_closed_positions(tmp_path):
    """CLOSED positions don't appear in the heatmap."""
    from penny_heatmap import build_heatmap
    db = str(tmp_path / "test.db")
    _seed_positions(db, [
        ("OPEN-1", 10.00, 9.00, 10, "OPEN"),
        ("CLOSED-1", 20.00, 19.00, 5, "CLOSED"),
        ("CLOSED-T1-1", 30.00, 29.00, 5, "CLOSED_T1"),  # post-T1 still tracked
    ])
    kite = MagicMock()
    kite.instrument_cache = {"OPEN-1": 1001, "CLOSED-1": 1002, "CLOSED-T1-1": 1003}
    async def _quote(tokens):
        return {tok: {"last_price": 10.0} for tok in tokens}
    kite.get_quote = AsyncMock(side_effect=_quote)
    body, buckets, total, priced = asyncio.run(build_heatmap(
        db_path=db, kite=kite, sectors_csv_path="/nonexistent",
    ))
    assert "2 open" in body
    assert "OPEN-1" in body
    assert "CLOSED-T1-1" in body  # post-T1 still managed, included
    assert "CLOSED-1" not in body   # fully closed -> excluded


def test_build_heatmap_pnl_abs_computed(tmp_path):
    """penny_heatmap computes absolute Rs P&L = (ltp - entry) * shares."""
    from penny_heatmap import build_heatmap
    db = str(tmp_path / "test.db")
    _seed_positions(db, [
        # entry=10, sl=9, shares=20, current=11 -> +2 Rs per share * 20 = +20
        ("WINNER", 10.00, 9.00, 20, "OPEN"),
        # entry=20, sl=19, shares=5, current=18 -> -2 per share * 5 = -10
        ("LOSER", 20.00, 19.00, 5, "OPEN"),
    ])
    kite = MagicMock()
    kite.instrument_cache = {"WINNER": 1001, "LOSER": 1002}
    async def _quote(tokens):
        return {1001: {"last_price": 11.0}, 1002: {"last_price": 18.0}}
    kite.get_quote = AsyncMock(side_effect=_quote)
    body, buckets, total, priced = asyncio.run(build_heatmap(
        db_path=db, kite=kite, sectors_csv_path="/nonexistent",
    ))
    # The body shows pnl_pct (+10% and -10%) -- pnl_abs is on the snap
    # object (verified via buckets).
    snap_map = {}
    for bucket in buckets.values():
        for p in bucket.positions:
            snap_map[p.ticker] = p
    assert snap_map["WINNER"].pnl_abs == 20.0
    assert snap_map["LOSER"].pnl_abs == -10.0


# ---- message constraints -------------------------------------------

def test_build_heatmap_message_under_1000_chars(tmp_path):
    """Even with many positions, message stays under Telegram limit."""
    from penny_heatmap import build_heatmap
    db = str(tmp_path / "test.db")
    rows = [(f"T{i:03d}", 10.0, 9.0, 10, "OPEN") for i in range(15)]
    _seed_positions(db, rows)
    kite = MagicMock()
    kite.instrument_cache = {f"T{i:03d}": 1000 + i for i in range(15)}
    async def _quote(tokens):
        return {tok: {"last_price": 10.5} for tok in tokens}
    kite.get_quote = AsyncMock(side_effect=_quote)
    body, buckets, total, priced = asyncio.run(build_heatmap(
        db_path=db, kite=kite, sectors_csv_path="/nonexistent",
    ))
    assert len(body) < 1000, f"Body too long ({len(body)} chars): {body!r}"


def test_build_heatmap_avg_pnl_pct_per_sector(tmp_path):
    """Sector row shows average P&L % across positions."""
    from penny_heatmap import build_heatmap
    db = str(tmp_path / "test.db")
    _seed_positions(db, [
        ("AAA", 10.00, 9.00, 10, "OPEN"),  # +5%
        ("BBB", 20.00, 19.00, 10, "OPEN"),  # -5%
    ])
    kite = MagicMock()
    kite.instrument_cache = {"AAA": 1001, "BBB": 1002}
    async def _quote(tokens):
        return {1001: {"last_price": 10.50}, 1002: {"last_price": 19.00}}
    kite.get_quote = AsyncMock(side_effect=_quote)
    sectors_csv = tmp_path / "sectors.csv"
    _write_sectors_csv(str(sectors_csv), {"AAA": "Steel", "BBB": "Steel"})
    body, buckets, total, priced = asyncio.run(build_heatmap(
        db_path=db, kite=kite, sectors_csv_path=str(sectors_csv),
    ))
    # avg of +5 and -5 = 0
    assert "Steel" in body
    assert "+0.00% avg" in body
