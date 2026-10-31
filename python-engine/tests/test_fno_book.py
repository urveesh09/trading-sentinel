"""[O29c] The four-strategy book (fno_book): the opening drive and its side, the order and the drive filter, each
position's own exits, and the book inside the live tick. [O29d] SENSEX too: its own drive history, NIFTY's volume.
The research parity (the engine book trades exactly as the research UNION_DRIVE over Sep 10 - Oct 28) is
docs/research/fno/2026-10-28-chop-study/test_engine_parity.py; on SENSEX, docs/research/fno/2026-10-28-sensex-check/
test_engine_parity.py."""
from dataclasses import replace
from datetime import date, datetime, timedelta

import aiosqlite
import pandas as pd
import pytest

import fno_book
import fno_shadow
from config import settings
from fno_engine_mom import MomSignal
from fno_models import FnoDirection
from tests.test_fno_orchestrator import NOW, FakeKite, _quote_table, book  # noqa: F401

PRIOR = ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09"]


def _bars(opening_closes, prior=PRIOR) -> pd.DataFrame:
    """Flat earlier sessions, then 2026-07-10: the opening's closes as given, and the shipped break at 09:55."""
    frames = [pd.DataFrame({"open": 25000.0, "high": 25005.0, "low": 24995.0, "close": 25000.0, "volume": 100.0},
                           index=pd.date_range(f"{d} 09:15", periods=74, freq="5min")) for d in prior]
    rows, prev = [], 25000.0
    for i, close in enumerate(opening_closes):
        rows.append((f"09:{15 + 5 * i:02d}", prev, 25010, 24990, close, 100))
        prev = close
    rows += [("09:45", prev, 25008, 24995, prev + 2, 100), ("09:50", prev + 2, 25010, 24997, prev + 2, 100),
             ("09:55", prev + 2, 25105, prev, 25100, 300)]
    idx = pd.to_datetime([f"2026-07-10 {hm}" for hm, *_ in rows])
    cols = list(zip(*[r[1:] for r in rows]))
    frames.append(pd.DataFrame({"open": cols[0], "high": cols[1], "low": cols[2], "close": cols[3],
                                "volume": cols[4]}, index=idx))
    return pd.concat(frames)


ONE_WAY = [25001, 25002, 25003, 25004, 25005, 25006]       # drive 1.0
FLAT = [25000] * 6                                         # drive 0.0
TODAY = date(2026, 7, 10)


def at(h, m):
    return datetime(2026, 7, 10, h, m)


# ---- the opening drive ----------------------------------------------------------------------------------------------

def test_the_opening_drive_reads_the_six_closed_opening_bars():
    assert fno_book.opening_drive(_bars(ONE_WAY), TODAY, at(9, 45)) == 1.0
    assert fno_book.opening_drive(_bars(FLAT), TODAY, at(9, 45)) == 0.0
    back = [25004, 25000, 25004, 25000, 25004, 25002]       # |25002 - 25000| / (4+4+4+4+4+2)
    assert fno_book.opening_drive(_bars(back), TODAY, at(10, 0)) == pytest.approx(2 / 22)
    assert fno_book.opening_drive(_bars(ONE_WAY), TODAY, at(9, 44)) is None          # the 09:40 bar is still open
    assert fno_book.opening_drive(_bars(ONE_WAY, prior=PRIOR[1:]), TODAY, at(9, 45)) == 1.0   # 6 earlier sessions
    assert fno_book.opening_drive(_bars(ONE_WAY, prior=PRIOR[2:]), TODAY, at(9, 45)) is None  # 5 are too few
    gap = _bars(ONE_WAY)
    assert fno_book.opening_drive(gap.drop(pd.Timestamp("2026-07-10 09:25")), TODAY, at(9, 45)) is None


def test_the_side_is_high_only_above_the_median_of_the_last_twenty():
    assert fno_book.drive_side(0.5, [0.1, 0.2, 0.3, 0.4]) is None                     # fewer than 5 earlier
    assert fno_book.drive_side(None, [0.1] * 10) is None
    assert fno_book.drive_side(0.31, [0.1, 0.2, 0.3, 0.4, 0.5]) == "HIGH"             # median 0.3
    assert fno_book.drive_side(0.3, [0.1, 0.2, 0.3, 0.4, 0.5]) == "LOW"               # at the median: not above
    assert fno_book.drive_side(0.27, [0.1, 0.2, 0.3, 0.4, 0.5, 0.25]) == "LOW"         # median 0.275
    assert fno_book.drive_side(0.5, [0.9] * 30 + [0.1] * 20) == "HIGH"                 # only the last 20 count


@pytest.mark.asyncio
async def test_the_seeded_research_history_decides_from_the_first_day(db_path):
    await fno_book.init_opening_drive_db(db_path)
    await fno_book.init_opening_drive_db(db_path)                                       # idempotent
    history = await fno_book.drive_history(db_path, date(2026, 10, 29))
    assert len(history) == 20 and history[-1] == fno_book.SEED["2026-10-28"]
    assert fno_book.drive_side(fno_book.SEED["2026-10-28"], await fno_book.drive_history(
        db_path, date(2026, 10, 28))) == "LOW"                                          # Oct 28: LOW, as O28/O29b


@pytest.mark.asyncio
async def test_today_is_recorded_once_and_kept_for_the_day(db_path):
    fno_book._TODAY.clear()
    await fno_book.init_opening_drive_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.executemany("INSERT INTO fno_opening_drive VALUES(?, 'NIFTY', 0.2, 'test', 'x')",
                             [(f"2026-06-{d:02d}",) for d in range(1, 21)])
        await db.commit()
    assert await fno_book.drive_today(db_path, _bars(ONE_WAY), at(9, 44)) == (None, None)
    assert await fno_book.drive_today(db_path, _bars(ONE_WAY), at(9, 46)) == (1.0, "HIGH")
    assert await fno_book.drive_today(db_path, _bars(FLAT), at(10, 30)) == (1.0, "HIGH")   # kept for the day
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute("SELECT value, source FROM fno_opening_drive WHERE session_date='2026-07-10'"
                                       )).fetchall()
    assert rows == [(1.0, "live")]
    fno_book._TODAY.clear()


# ---- the book -------------------------------------------------------------------------------------------------------

def _sig(direction=None, reason=""):
    return MomSignal(bar_ts="2026-07-10 09:55:00", direction=direction, reject_reason=reason, close=25100.0,
                     atr=10.0, stop_underlying=25080.0, target_underlying=25136.0)


@pytest.fixture
def components(monkeypatch):
    fired = {"OR20": None, "EFF": None, "TPB": None}

    def variant(bars, regime, now, v):
        name = "OR20" if v.name == "GRID_OR20_NOEMA" else "TPB"
        assert name != "OR20" or v.ema_filter is False
        return _sig(fired[name], "none")

    monkeypatch.setattr(fno_shadow, "_variant_signal", variant)
    monkeypatch.setattr(fno_book, "efficiency_break", lambda bars, regime, now: _sig(fired["EFF"], "none"))
    return fired


def test_the_first_strategy_in_the_declared_order_trades_and_the_shared_signal_is_not_changed(components):
    shipped = _sig(FnoDirection.LONG)
    components.update(OR20=FnoDirection.SHORT, TPB=FnoDirection.LONG)
    sig = fno_book.book_signal(None, "R", NOW, shipped=shipped, side="HIGH")
    assert (sig.strategy, sig.direction) == ("SHIPPED", FnoDirection.LONG) and shipped.strategy == ""
    sig = fno_book.book_signal(None, "R", NOW, shipped=_sig(None, "no_or_break"), side="HIGH")
    assert (sig.strategy, sig.direction) == ("OR20", FnoDirection.SHORT)
    components.update(OR20=None, EFF=FnoDirection.SHORT)
    assert fno_book.book_signal(None, "R", NOW, shipped=_sig(None, "x"), side="HIGH").strategy == "EFF"


def test_on_a_low_or_unknown_drive_only_the_pullback_trades(components):
    components.update(OR20=FnoDirection.LONG, EFF=FnoDirection.LONG)
    for side in ("LOW", None):
        sig = fno_book.book_signal(None, "R", NOW, shipped=_sig(FnoDirection.LONG), side=side)
        assert sig.direction is None and sig.strategy == ""
        assert sig.reject_reason == f"drive_{(side or 'unknown').lower()}:breakout_skipped"
        assert sig.bar_ts == "2026-07-10 09:55:00"
    assert fno_book.book_signal(None, "R", NOW, shipped=_sig(None, "no_or_break"),
                                side="LOW").reject_reason == "drive_low:no_or_break"
    components["TPB"] = FnoDirection.SHORT
    assert fno_book.book_signal(None, "R", NOW, shipped=_sig(FnoDirection.LONG), side="LOW").strategy == "TPB"


def test_each_strategy_keeps_its_research_exits():
    assert fno_book.exit_overrides("SHIPPED") == {} == fno_book.exit_overrides(None) == fno_book.exit_overrides("?")
    assert fno_book.exit_overrides("OR20")["FNO_TIME_STOP_MIN"] == 75.0
    assert fno_book.exit_overrides("OR20")["FNO_PROFIT_LOCK_ARM_R"] == 0.80
    assert fno_book.exit_overrides("EFF") == {"FNO_TIME_STOP_MIN": 60.0, "FNO_TRAIL_ATR_MULT": 1.5,
                                              "FNO_PROFIT_LOCK_ENABLED": False}
    assert fno_book.exit_overrides("TPB") == {"FNO_PROFIT_LOCK_ENABLED": False, "FNO_TIME_STOP_MIN": 120.0,
                                              "FNO_TRAIL_ATR_MULT": 2.0}
    fno_book.exit_overrides("TPB")["FNO_TIME_STOP_MIN"] = 1.0                       # a copy each time
    assert fno_book.EXIT_OVERRIDES["TPB"]["FNO_TIME_STOP_MIN"] == 120.0


def test_the_book_is_for_every_traded_underlying_and_can_be_switched_back(monkeypatch):
    monkeypatch.setattr(settings, "FNO_BOOK", "UNION_DRIVE")
    assert fno_book.enabled_for("NIFTY") and fno_book.enabled_for("SENSEX") and not fno_book.enabled_for("")
    monkeypatch.setattr(settings, "FNO_BOOK", "SHIPPED")
    assert not fno_book.enabled_for("NIFTY") and not fno_book.enabled_for("SENSEX")


# ---- [O29d] SENSEX ---------------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_each_underlying_has_its_own_seeded_history(db_path):
    await fno_book.init_opening_drive_db(db_path)
    nifty = await fno_book.drive_history(db_path, date(2026, 10, 28), "NIFTY")
    sensex = await fno_book.drive_history(db_path, date(2026, 10, 28), "SENSEX")
    assert nifty[-1] == fno_book.SEED["2026-10-27"] and sensex[-1] == fno_book.SEED_SENSEX["2026-10-27"]
    assert len(nifty) == len(sensex) == 20
    assert fno_book.drive_side(fno_book.SEED["2026-10-28"], nifty) == "LOW"               # NIFTY two-way on Oct 28
    assert fno_book.drive_side(fno_book.SEED_SENSEX["2026-10-28"], sensex) == "HIGH"      # SENSEX not (O29d check)


@pytest.mark.asyncio
async def test_the_o29c_table_is_migrated_to_one_row_per_underlying(db_path):
    async with aiosqlite.connect(db_path) as db:
        await db.execute("CREATE TABLE fno_opening_drive (session_date TEXT PRIMARY KEY, underlying TEXT NOT NULL, "
                         "value REAL NOT NULL, source TEXT NOT NULL, recorded_at TEXT NOT NULL)")
        await db.execute("INSERT INTO fno_opening_drive VALUES('2026-10-29', 'NIFTY', 0.42, 'live', 'x')")
        await db.commit()
    await fno_book.init_opening_drive_db(db_path)
    await fno_book.init_opening_drive_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        kept = await (await db.execute("SELECT underlying, value, source FROM fno_opening_drive "
                                       "WHERE session_date='2026-10-29'")).fetchall()
        seeded = await (await db.execute("SELECT underlying, COUNT(*) FROM fno_opening_drive "
                                         "WHERE source='research_seed' GROUP BY underlying")).fetchall()
    assert kept == [("NIFTY", 0.42, "live")]
    assert sorted(seeded) == [("NIFTY", len(fno_book.SEED)), ("SENSEX", len(fno_book.SEED_SENSEX))]


def test_sensex_strategies_read_nifty_volume_and_their_own_prices():
    sensex = _bars(ONE_WAY)
    sensex["volume"] = 0.0
    nifty = _bars(ONE_WAY).drop(pd.Timestamp("2026-07-10 09:55"))
    out = fno_book.with_participation(sensex, nifty)
    assert out[["open", "high", "low", "close"]].equals(sensex[["open", "high", "low", "close"]])
    assert out.loc["2026-07-10 09:50", "volume"] == 100.0 and out.loc["2026-07-10 09:55", "volume"] == 0.0
    assert (sensex["volume"] == 0.0).all()                                               # a copy
    assert fno_book.with_participation(sensex, None) is sensex


@pytest.mark.asyncio
async def test_each_underlying_keeps_its_own_drive_for_the_day(db_path):
    fno_book._TODAY.clear()
    await _history(db_path, underlying="NIFTY")
    await _history(db_path, underlying="SENSEX")
    assert await fno_book.drive_today(db_path, _bars(ONE_WAY), at(9, 46), underlying="NIFTY") == (1.0, "HIGH")
    assert await fno_book.drive_today(db_path, _bars(FLAT), at(9, 46), underlying="SENSEX") == (0.0, "LOW")
    assert await fno_book.drive_today(db_path, _bars(FLAT), at(10, 30), underlying="NIFTY") == (1.0, "HIGH")
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute("SELECT underlying, value FROM fno_opening_drive WHERE session_date="
                                       "'2026-07-10' ORDER BY underlying")).fetchall()
    assert rows == [("NIFTY", 1.0), ("SENSEX", 0.0)]
    fno_book._TODAY.clear()


# ---- in the live tick -----------------------------------------------------------------------------------------------

async def _history(db_path, value=0.2, underlying="NIFTY"):
    await fno_book.init_opening_drive_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.executemany("INSERT INTO fno_opening_drive VALUES(?, ?, ?, 'test', 'x')",
                             [(f"2026-06-{d:02d}", underlying, value) for d in range(1, 21)])
        await db.commit()


async def _paper(db_path):
    import fno_positions
    await fno_positions.init_fno_positions_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await db.execute(
            "SELECT id, status, strategy, exit_reason FROM fno_positions WHERE source='FNO_PAPER'")).fetchall()]


async def _reasons(db_path, underlying="NIFTY"):
    async with aiosqlite.connect(db_path) as db:
        return [r[0] for r in await (await db.execute(
            "SELECT reject_reason FROM fno_signals WHERE leg='ENGINE' AND underlying=? ORDER BY rowid",
            (underlying,))).fetchall()]


@pytest.fixture
def live(monkeypatch, db_path, book):  # noqa: F811
    from performance import init_ledger
    monkeypatch.setattr(settings, "FNO_BOOK", "UNION_DRIVE")
    monkeypatch.setattr(settings, "FNO_DR_DISABLE_PAPER", True)
    monkeypatch.setattr(settings, "FNO_TIME_STOP_RESPECTS_PREMIUM", True)
    fno_book._TODAY.clear()

    async def make(opening):
        await init_ledger(db_path)
        return FakeKite(_bars(opening), _quote_table(book, NOW))
    yield make
    fno_book._TODAY.clear()


@pytest.mark.asyncio
async def test_a_one_way_morning_lets_the_shipped_break_trade_as_the_book(live, db_path, book):  # noqa: F811
    from fno_orchestrator import format_fno_telegram, run_fno_tick
    await _history(db_path)
    kite = await live(ONE_WAY)
    summary = await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)
    assert [e["source"] for e in summary["entries"]] == ["FNO_PAPER"]
    assert "strategy=SHIPPED" in format_fno_telegram(summary)
    [position] = await _paper(db_path)
    assert position["strategy"] == "SHIPPED"
    # Its exits are its strategy's: as TPB (120-minute time stop) a flat, losing trade 50 minutes in is kept; as the
    # shipped break (45 minutes) it is cut.
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE fno_positions SET strategy='TPB' WHERE id=?", (position["id"],))
        await db.commit()
    later = NOW + timedelta(minutes=settings.FNO_TIME_STOP_MIN + 5)
    kite.quote_table = _quote_table(book, later, opt_bid_shift=-4.0)
    assert (await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=later))["exits"] == []
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE fno_positions SET strategy='SHIPPED' WHERE id=?", (position["id"],))
        await db.commit()
    summary = await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=later + timedelta(minutes=1))
    assert [e["reason"] for e in summary["exits"]] == ["time_stop"]


@pytest.mark.asyncio
@pytest.mark.parametrize("history, reason", [(True, "drive_low:breakout_skipped"),
                                             (False, "drive_unknown:breakout_skipped")])
async def test_a_two_way_morning_keeps_the_breakouts_out(live, db_path, history, reason):
    from fno_orchestrator import run_fno_tick
    if history:
        await _history(db_path)
    kite = await live(FLAT)
    summary = await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)
    assert summary["entries"] == [] and await _paper(db_path) == []
    assert reason in await _reasons(db_path)


@pytest.mark.asyncio
async def test_the_shipped_setting_trades_the_shipped_break_on_any_morning(live, db_path, monkeypatch):
    from fno_orchestrator import run_fno_tick
    kite = await live(FLAT)
    monkeypatch.setattr(settings, "FNO_BOOK", "SHIPPED")
    summary = await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)
    assert [e["source"] for e in summary["entries"]] == ["FNO_PAPER"]
    assert [p["strategy"] for p in await _paper(db_path)] == [None]


@pytest.fixture
def sensex_live(monkeypatch, db_path, book):  # noqa: F811
    """[O29d] The paper book trading SENSEX alone, its future priced like the NIFTY fixture."""
    import fno_underlyings
    from performance import init_ledger
    from tests.test_fno_orchestrator import FUT_TOKEN
    from tests.test_fno_sensex import SENSEX_FUT, _sensex_book
    sensex_book = _sensex_book()
    monkeypatch.setitem(fno_underlyings._books, "SENSEX", sensex_book)
    monkeypatch.setattr(settings, "FNO_TRADING_UNDERLYINGS", "SENSEX")
    monkeypatch.setattr(settings, "FNO_BOOK", "UNION_DRIVE")
    monkeypatch.setattr(settings, "FNO_DR_DISABLE_PAPER", True)
    fno_book._TODAY.clear()

    async def make(opening):
        await init_ledger(db_path)
        table = _quote_table(book, NOW)
        table.update(_quote_table(sensex_book, NOW))
        table[SENSEX_FUT] = dict(table[FUT_TOKEN])
        return FakeKite(_bars(opening), table)
    yield make
    fno_book._TODAY.clear()


@pytest.mark.asyncio
async def test_sensex_trades_the_book_on_its_own_drive(sensex_live, db_path):
    from fno_orchestrator import format_fno_telegram, run_fno_tick
    await _history(db_path, underlying="SENSEX")
    kite = await sensex_live(ONE_WAY)
    summary = await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)
    assert [e["symbol"][:6] for e in summary["entries"]] == ["SENSEX"]
    assert "strategy=SHIPPED" in format_fno_telegram(summary)
    assert [p["strategy"] for p in await _paper(db_path)] == ["SHIPPED"]
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute("SELECT underlying, value, source FROM fno_opening_drive "
                                       "WHERE session_date='2026-07-10'")).fetchall()
    assert rows == [("SENSEX", 1.0, "live")]


@pytest.mark.asyncio
@pytest.mark.parametrize("history, reason", [("SENSEX", "drive_low:breakout_skipped"),
                                             ("NIFTY", "drive_unknown:breakout_skipped")])
async def test_a_two_way_sensex_morning_keeps_its_breakouts_out(sensex_live, db_path, history, reason):
    """NIFTY's history is not SENSEX's: with only NIFTY's, SENSEX's side is not known."""
    from fno_orchestrator import run_fno_tick
    await _history(db_path, underlying=history)
    kite = await sensex_live(FLAT)
    summary = await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)
    assert summary["entries"] == [] and await _paper(db_path) == []
    assert reason in await _reasons(db_path, "SENSEX")


# ---- [O29h] the trend gate: yesterday's NIFTY daily ADX(14) ---------------------------------------------------------

def _daily(kind: str, n: int = 120, end: str = "2026-07-09") -> pd.DataFrame:
    """Daily NIFTY candles ending ``end``: TREND rises steadily (ADX 100); CHOP swings up and down around one level
    every eight sessions (ADX about 11)."""
    import math
    idx = pd.bdate_range(end=end, periods=n)
    rows, price = [], 24000.0
    for i in range(n):
        if kind == "TREND":
            o, c = price, price * 1.006
            rows.append((o, c * 1.002, o * 0.998, c))
        else:
            o, c = price, 24000 * (1 + 0.012 * math.sin(2 * math.pi * i / 8))
            rows.append((o, max(o, c) + 40, min(o, c) - 40, c))
        price = c
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)


def _wilder(frame: pd.DataFrame, n: int = 14) -> float:
    """An independent loop of Wilder's ADX with the same seeding (each smoother starts at its first value)."""
    h, l, c = list(frame["high"]), list(frame["low"]), list(frame["close"])
    atr = plus = minus = adx = None
    for i in range(len(c)):
        tr = h[i] - l[i] if i == 0 else max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        atr = tr if atr is None else atr + (tr - atr) / n
        if i == 0:
            continue
        up, down = h[i] - h[i - 1], l[i - 1] - l[i]
        p = up if (up > down and up > 0) else 0.0
        m = down if (down > up and down > 0) else 0.0
        plus = p if plus is None else plus + (p - plus) / n
        minus = m if minus is None else minus + (m - minus) / n
        pdi, mdi = 100 * plus / atr, 100 * minus / atr
        dx = 100 * abs(pdi - mdi) / (pdi + mdi)
        adx = dx if adx is None else adx + (dx - adx) / n
    return adx


def test_the_daily_adx_is_wilders_and_reads_only_yesterday_and_before():
    for kind in ("TREND", "CHOP"):
        frame = _daily(kind)
        assert float(fno_book.adx(frame).iloc[-1]) == pytest.approx(_wilder(frame), rel=1e-9)
    trend, chop = _daily("TREND"), _daily("CHOP")
    assert fno_book.daily_adx(trend, TODAY)[0] > 25 > fno_book.daily_adx(chop, TODAY)[0]
    today = pd.DataFrame([(1.0, 99999.0, 0.5, 99000.0)], columns=["open", "high", "low", "close"],
                         index=[pd.Timestamp(TODAY)])
    assert fno_book.daily_adx(pd.concat([chop, today]), TODAY) == fno_book.daily_adx(chop, TODAY)
    assert fno_book.daily_adx(chop, TODAY)[1] == date(2026, 7, 9)
    assert fno_book.daily_adx(chop.iloc[-59:], TODAY) == (None, None)                # under 60 daily bars
    with_date_column = chop.reset_index().rename(columns={"index": "date"})
    assert fno_book.daily_adx(with_date_column, TODAY) == fno_book.daily_adx(chop, TODAY)


def test_the_gate_opens_at_the_threshold_and_not_below(monkeypatch):
    monkeypatch.setattr(settings, "FNO_BOOK_ADX_MIN", 25.0)
    assert fno_book.adx_side(25.0) == "HIGH" and fno_book.adx_side(24.99) == "LOW" and fno_book.adx_side(None) is None
    assert fno_book.adx_side(21.0, threshold=20) == "HIGH"


def test_on_a_sideways_market_the_whole_book_sits_out(components):
    components.update(OR20=FnoDirection.LONG, EFF=FnoDirection.LONG, TPB=FnoDirection.SHORT)
    for adx_side in ("LOW", None):
        sig = fno_book.book_signal(None, "R", NOW, shipped=_sig(FnoDirection.LONG), side="HIGH", gate="ADX",
                                   adx_side=adx_side)
        assert sig.direction is None and sig.strategy == ""
        assert sig.reject_reason == f"adx_{(adx_side or 'unknown').lower()}:book_skipped"
    assert fno_book.book_signal(None, "R", NOW, shipped=_sig(None, "no_or_break"), side="HIGH", gate="ADX",
                                adx_side="LOW").reject_reason == "adx_low:no_or_break"
    # trending: the declared order, and the opening drive no longer matters
    sig = fno_book.book_signal(None, "R", NOW, shipped=_sig(None, "x"), side="LOW", gate="ADX", adx_side="HIGH")
    assert (sig.strategy, sig.direction) == ("OR20", FnoDirection.LONG)
    components.update(OR20=None, EFF=None)
    assert fno_book.book_signal(None, "R", NOW, shipped=_sig(None, "x"), side=None, gate="ADX",
                                adx_side="HIGH").strategy == "TPB"


class _DailyKite:
    def __init__(self, frame):
        self.frame, self.calls, self.fail = frame, [], False

    async def get_historical(self, ticker, frm, to):
        self.calls.append((ticker, frm, to))
        if self.fail:
            raise RuntimeError("kite down")
        return self.frame


@pytest.mark.asyncio
async def test_the_gate_is_read_once_a_day_kept_and_told_once(db_path, monkeypatch):
    import operator_alert
    told = []

    async def notify(message, *, event="operator_alert"):
        told.append((event, message))
        return True
    monkeypatch.setattr(operator_alert, "notify_operator", notify)
    monkeypatch.setattr(settings, "FNO_BOOK_ADX_MIN", 25.0)
    fno_book._ADX_TODAY.clear()
    kite = _DailyKite(_daily("CHOP"))
    assert await fno_book.adx_today(db_path, kite, at(9, 29)) == (None, None) and kite.calls == []  # from 09:30
    kite.fail = True
    assert await fno_book.adx_today(db_path, kite, at(9, 30)) == (None, None)          # not kept: tried again
    kite.fail = False
    value, side = await fno_book.adx_today(db_path, kite, at(9, 31))
    assert side == "LOW" and value < 25
    assert await fno_book.adx_today(db_path, kite, at(10, 0)) == (value, side) and len(kite.calls) == 2
    assert kite.calls[-1] == ("NIFTY 50", "2025-05-16", "2026-07-10")    # 420 days through today (dropped later)
    fno_book._ADX_TODAY.clear()                                                         # a restart the same day
    assert await fno_book.adx_today(db_path, kite, at(11, 0)) == (value, side)
    assert [e for e, _ in told] == ["fno_book_adx_gate"] and "sits today out" in told[0][1]
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute("SELECT session_date, side, threshold, last_bar FROM fno_regime_gate")).fetchall()
    assert rows == [("2026-07-10", "LOW", 25.0, "2026-07-09")]
    fno_book._ADX_TODAY.clear()


def _stretch_bars(today=None, prior=True) -> pd.DataFrame:
    """Six opening 5-minute bars from 09:15 ranging 100 to 120 (range 20), then a climb: an earlier session, too."""
    rows = []
    if prior:
        rows.append((pd.Timestamp("2026-07-09 15:25"), 100.0, 101.0, 99.0, 100.0, 1000.0))
    opening = [(100, 104, 100, 103), (103, 108, 102, 106), (106, 112, 105, 110),
               (110, 120, 109, 115), (115, 116, 108, 110), (110, 112, 106, 108)]
    for i, (o, h, l, c) in enumerate(opening):
        rows.append((pd.Timestamp("2026-07-10 09:15") + pd.Timedelta(minutes=5 * i), o, h, l, c, 1000.0))
    for i, c in enumerate(today or [109.0, 112.0, 118.0, 125.0]):
        rows.append((pd.Timestamp("2026-07-10 09:45") + pd.Timedelta(minutes=5 * i), c - 1, c + 1, c - 2, c, 1000.0))
    return pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close", "volume"]).set_index("datetime")


def _expected_stretch(bars, bar, side):
    """An independent reading: running volume-weighted typical price, the close against it, over the opening range."""
    today = bars[bars.index.date == TODAY]
    upto = today[today.index <= pd.Timestamp(bar)]
    num = sum((r.high + r.low + r.close) / 3 * r.volume for r in upto.itertuples())
    vwap = num / sum(r.volume for r in upto.itertuples())
    return round(side * (upto.close.iloc[-1] - vwap) / 20.0, 4)


def test_the_stretch_is_the_researchs_reading_from_closed_bars_only():
    bars = _stretch_bars()
    assert fno_book.entry_stretch(bars, at(10, 0), FnoDirection.LONG) == pytest.approx(
        _expected_stretch(bars, "2026-07-10 09:55", 1))                                 # 10:00 is still open
    assert fno_book.entry_stretch(bars, at(10, 0), FnoDirection.SHORT) == pytest.approx(
        -fno_book.entry_stretch(bars, at(10, 0), FnoDirection.LONG))
    changed = bars.copy()
    changed.loc[changed.index >= pd.Timestamp("2026-07-10 10:00"), ["high", "low", "close", "volume"]] *= 3
    assert fno_book.entry_stretch(changed, at(10, 0), FnoDirection.LONG) == fno_book.entry_stretch(
        bars, at(10, 0), FnoDirection.LONG), "a later bar cannot change it"


def test_the_stretch_does_not_apply_without_its_inputs():
    bars = _stretch_bars()
    assert fno_book.entry_stretch(None, at(10, 0), FnoDirection.LONG) is None
    assert fno_book.entry_stretch(bars.iloc[0:0], at(10, 0), FnoDirection.LONG) is None
    assert fno_book.entry_stretch(_stretch_bars(prior=False), at(10, 0), FnoDirection.LONG) is None      # no earlier session
    missing = bars.drop(pd.Timestamp("2026-07-10 09:25"))
    assert fno_book.entry_stretch(missing, at(10, 0), FnoDirection.LONG) is None                         # an opening bar gone
    flat = bars.copy()
    flat.loc[:, ["high", "low"]] = 100.0
    assert fno_book.entry_stretch(flat, at(10, 0), FnoDirection.LONG) is None                            # no range
    no_volume = bars.copy()
    no_volume["volume"] = 0.0
    today = no_volume[no_volume.index.date == TODAY]
    typical = ((today.high + today.low + today.close) / 3).iloc[:9].mean()
    assert fno_book.entry_stretch(no_volume, at(10, 0), FnoDirection.LONG) == pytest.approx(
        round((today.close.iloc[8] - typical) / 20.0, 4))                                                # as the research


def test_a_stretched_first_signal_takes_no_entry_at_all(components, monkeypatch):
    monkeypatch.setattr(settings, "FNO_BOOK_MAX_STRETCH", 0.5)
    components.update(OR20=None, EFF=FnoDirection.SHORT, TPB=FnoDirection.LONG)
    bars = _stretch_bars()
    now = at(10, 5)
    assert fno_book.entry_stretch(bars, now, FnoDirection.LONG) >= 0.5
    shipped = _sig(FnoDirection.LONG)
    sig = fno_book.book_signal(bars, "R", now, shipped=shipped, side="HIGH", gate="ADX", adx_side="HIGH")
    assert sig.direction is None and sig.strategy == "" and sig.reject_reason == "stretched:SHIPPED"
    assert sig.bar_ts == shipped.bar_ts and shipped.direction == FnoDirection.LONG    # the shared evaluation is untouched
    # below the limit, or against the move, it enters
    assert fno_book.book_signal(bars, "R", now, shipped=_sig(FnoDirection.SHORT), side="HIGH", gate="ADX",
                                adx_side="HIGH").strategy == "SHIPPED"
    monkeypatch.setattr(settings, "FNO_BOOK_MAX_STRETCH", 99.0)
    assert fno_book.book_signal(bars, "R", now, shipped=_sig(FnoDirection.LONG), side="HIGH", gate="ADX",
                                adx_side="HIGH").strategy == "SHIPPED"


def test_the_stretch_check_can_be_turned_off_and_leaves_the_drive_book_alone(components, monkeypatch):
    components.update(OR20=None, EFF=None, TPB=None)
    bars = _stretch_bars()
    now = at(10, 5)
    monkeypatch.setattr(settings, "FNO_BOOK_MAX_STRETCH", 0.0)
    assert fno_book.book_signal(bars, "R", now, shipped=_sig(FnoDirection.LONG), side="HIGH", gate="ADX",
                                adx_side="HIGH").strategy == "SHIPPED"
    monkeypatch.setattr(settings, "FNO_BOOK_MAX_STRETCH", 0.5)
    assert fno_book.book_signal(bars, "R", now, shipped=_sig(FnoDirection.LONG), side="HIGH").strategy == "SHIPPED"


def test_the_trend_gate_book_is_the_default_and_drive_or_shipped_stay_available(monkeypatch):
    from config import Settings
    assert Settings.model_fields["FNO_BOOK"].default == "UNION_ADX"
    assert Settings.model_fields["FNO_BOOK_ADX_MIN"].default == 30.0
    assert Settings.model_fields["FNO_BOOK_MAX_STRETCH"].default == 0.5
    assert Settings.model_fields["FNO_MAX_LOTS"].default == 2 and Settings.model_fields["FNO_MAX_LOTS_PROVEN"].default == 3
    for name in ("UNION_ADX", "UNION_DRIVE"):
        monkeypatch.setattr(settings, "FNO_BOOK", name)
        assert fno_book.enabled_for("NIFTY") and fno_book.enabled_for("SENSEX")
    monkeypatch.setattr(settings, "FNO_BOOK", "SHIPPED")
    assert not fno_book.enabled_for("NIFTY")


@pytest.fixture
def adx_live(live, monkeypatch):
    import operator_alert
    told = []

    async def notify(message, *, event="operator_alert"):
        told.append(event)
        return True
    monkeypatch.setattr(operator_alert, "notify_operator", notify)
    monkeypatch.setattr(settings, "FNO_BOOK", "UNION_ADX")
    fno_book._ADX_TODAY.clear()

    async def make(opening, daily):
        kite = await live(opening)
        kite.get_historical = _DailyKite(daily).get_historical
        return kite
    yield make, told
    fno_book._ADX_TODAY.clear()


@pytest.mark.asyncio
async def test_a_trending_market_trades_the_book_even_on_a_two_way_morning(adx_live, db_path, monkeypatch):
    from fno_orchestrator import format_fno_telegram, run_fno_tick
    monkeypatch.setattr(settings, "FNO_BOOK_MAX_STRETCH", 0.0)     # this bar is far past its narrow morning: see below
    make, told = adx_live
    kite = await make(FLAT, _daily("TREND"))          # the drive would have kept the breakouts out
    summary = await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)
    assert [e["source"] for e in summary["entries"]] == ["FNO_PAPER"]
    assert "strategy=SHIPPED" in format_fno_telegram(summary)
    assert [p["strategy"] for p in await _paper(db_path)] == ["SHIPPED"]
    assert told == ["fno_book_adx_gate"]


@pytest.mark.asyncio
async def test_a_stretched_entry_on_a_trending_market_is_passed_over_and_logged(adx_live, db_path, monkeypatch):
    from fno_orchestrator import run_fno_tick
    monkeypatch.setattr(settings, "FNO_BOOK_MAX_STRETCH", 0.5)
    make, told = adx_live
    kite = await make(FLAT, _daily("TREND"))
    summary = await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)
    assert summary["entries"] == [] and await _paper(db_path) == []
    assert "stretched:SHIPPED" in await _reasons(db_path)
    assert told == ["fno_book_adx_gate"]                # the gate was open; it was the entry that was passed over


@pytest.mark.asyncio
async def test_a_sideways_market_keeps_the_book_out_even_on_a_one_way_morning(adx_live, db_path):
    from fno_orchestrator import run_fno_tick
    make, _told = adx_live
    await _history(db_path)
    kite = await make(ONE_WAY, _daily("CHOP"))
    summary = await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)
    assert summary["entries"] == [] and await _paper(db_path) == []
    assert "adx_low:book_skipped" in await _reasons(db_path)


@pytest.mark.asyncio
async def test_without_a_trend_reading_the_book_sits_out(adx_live, db_path):
    from fno_orchestrator import run_fno_tick
    make, told = adx_live
    kite = await make(ONE_WAY, _daily("TREND").iloc[-30:])        # too few daily bars to read ADX
    summary = await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)
    assert summary["entries"] == [] and "adx_unknown:book_skipped" in await _reasons(db_path)
    assert told == []
