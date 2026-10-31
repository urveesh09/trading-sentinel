"""[O29c 2026-10-28] The paper F&O book's strategy for NIFTY: the four studied strategies in one book, the three
breakouts only on mornings with a HIGH 09:45 opening drive (O28 THEORY_DRIVE; forward panel C's UNION_DRIVE).

The owner, Oct 28 evening, after the O29b chop study: "the best strategy was the combination of the four and if we
have understood that today was not a good day which is two day then I agree. We can not trade on that day ... just,
the best strategy and some other strategies are shadow and go ahead and make the change."

Strategies, in the declared order used when two signal on the same bar:
  - SHIPPED  the shipped opening-range break (``evaluate_fno_mom``), with the live exits;
  - OR20     the 20-minute break without the EMA check (fno_shadow FNO_OR_20, ``ema_filter`` off): the profit lock
             arms at 0.8R, 75-minute time stop, 1.5 ATR trail (O27 grid arm OR20_NOEMA|LOCK_LATE|T75|TR1.5);
  - EFF      the O27e efficiency break (a port of the lab's EFFICIENCY_BREAK genome): 60-minute time stop, 1.5 ATR
             trail, no profit lock;
  - TPB      the trend-day VWAP pullback (fno_shadow FNO_TREND_PULLBACK): 120-minute time stop, 2 ATR trail, no
             profit lock. Always on: it waits for a trend by itself.
SHIPPED, OR20 and EFF trade only when today's opening drive is HIGH: above the median of the previous 20 sessions'
drives (at least 5 needed). LOW or not known: TPB only.

Opening drive (O28 ``day_rows``): |close of the 09:40 bar - the 09:15 open| / the path of the six opening 5-minute
closes, read once the 09:40 bar has closed. Each session's value is kept in ``fno_opening_drive``. The research values
for Sep 2 - Oct 28 are seeded, so the threshold is the research's from the first day, and a session the engine missed
is backfilled from the futures history (from the contract that is front now: a small difference from the research,
which read each day's own front contract).

Evidence, all on seen sessions: over the 16 sessions O28's walk-forward held out, +Rs 33,828 (worst day -Rs 2,500),
against +Rs 9,528 for the shipped break and +Rs 27,706 for the four always on. Over 31 sessions, Sep 10 - Oct 28,
the drive filter was the only one that held up out of sample (O29b), and on Oct 28 it kept the book out. Forward
panels A-D keep scoring the alternatives from Oct 28; fno_shadow's variants (FNO_BASE is the shipped break) keep
running as shadows.

[O29d] Every underlying the paper book trades: the owner's call (Oct 28 night: "Let them also be used on other than
nifty. At least on paper."). SENSEX reads its own prices and drive (seeded from its own research values) and
NIFTY's futures volume wherever a strategy reads volume (``with_participation``), as its shipped signal does. On
SENSEX the O29d check (docs/research/fno/2026-10-28-sensex-check) made +Rs 12,759 where the shipped break lost
Rs 8,622, but its worst day (-Rs 5,317) was past the frozen -Rs 5,000 bound: SENSEX runs it on the owner's call,
not on that check. The real-money test stays NIFTY only (fno_live_test). ``FNO_BOOK=SHIPPED`` restores the shipped
strategy everywhere. Each position keeps its strategy (``fno_positions.strategy``) and is managed with that
strategy's exits, whatever the setting is later.

[O29h 2026-10-29] UNION_ADX, the default. The year of NIFTY minutes the owner's ICICI history made possible (O29f)
showed all four strategies are trend strategies: they made their money in trending months and lost in the
range-bound ones, and the opening drive did not tell the two apart over the year. Yesterday's daily trend strength
did, in both halves of the year (O29g, docs/research/fno/2026-10-29-why-study). So UNION_ADX trades the same four
strategies, in the same order with the same exits, only on a session whose previous day's NIFTY daily ADX(14)
(Wilder, the research's formula) is at least FNO_BOOK_ADX_MIN (25, the textbook strong-trend level); below it, or
when it cannot be read, the book sits the day out. It is decided before the session from the market, not from the
book's own results. SENSEX reads NIFTY's ADX (the market's regime; the research tested NIFTY only). The owner's
go-ahead (Oct 29): "you are allowed to implement all of this ... Merge the code and deployed in production". The
evidence is in-sample on Jan 1 - Oct 28 2026 (TPB at ADX >= 20 and all four at ADX >= 25 were the most consistent
books per lot); NIFTY 2025, never used to find it, is the clean test that follows. The opening drive is still read
and kept in ``fno_opening_drive``.

[O31d 2026-10-31] The main book, the owner's call after the one-time NIFTY 2024 exam ("the best strategy that we have
come up with that has been consistent ... you put that as a main strategy"). UNION_ADX now trades at ADX >= 30 and
passes over an entry whose last closed 5-minute close already stands at least FNO_BOOK_MAX_STRETCH (0.5) of the first
30 minutes' range beyond VWAP, in the trade's direction; a later bar may still enter at a better place. It reads the
price at entry, never the book's own results. Lots, exits and brakes are unchanged. Replays, with an assumed extra cost
(docs/FNO_FINAL_STRATEGY_2026-10-31.md): +16,371 / +5,710 / +30,540 on Rs 2.5 lakh in 2024 / 2025 / 2026, worst fall
7.5%. All three years are seen and it failed a plateau test fixed in advance, narrowly: this is the owner's decision,
not a proof. ``FNO_BOOK_ADX_MIN=25`` and ``FNO_BOOK_MAX_STRETCH=0`` restore the Oct 29 book.
"""
from __future__ import annotations

import statistics
import weakref
from collections import OrderedDict
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Optional

import aiosqlite
import pandas as pd
import structlog

from config import settings
from fno_engine_mom import MomSignal
from fno_models import FnoDirection

logger = structlog.get_logger()

BOOK = "UNION_DRIVE"
ADX_BOOK = "UNION_ADX"
BOOKS = (BOOK, ADX_BOOK)
ADX_LEN = 14
ADX_HISTORY_CALENDAR_DAYS = 420   # about 285 daily bars: Wilder's smoothing has long forgotten its first value
ADX_MIN_BARS = 60
# Read from 09:30: by then the 09:20 swing scan has refreshed the daily cache through today, so yesterday's candle
# is the complete one (a cache row saved by the 14:45 scan holds yesterday's candle only as it was at 14:45).
# Entries start at 09:45 (FNO_ENTRY_START_MIN), so nothing is lost.
ADX_READ_FROM_MIN = 9 * 60 + 30
STRATEGIES = ("SHIPPED", "OR20", "EFF", "TPB")
BREAKOUTS = ("SHIPPED", "OR20", "EFF")
DRIVE_LOOKBACK = 20
DRIVE_MIN_PRIOR = 5
DRIVE_MIN_PRIOR_SESSIONS = 6  # O28 day_rows computed a day's features only after 6 earlier sessions of its contract
EFF_GENOME = {"family": "EFFICIENCY_BREAK", "lookback": 4, "efficiency": 0.35, "buffer": 0.2, "body": 0.55,
              "vwap": False, "rvol": 1.2, "stop": 2.0, "target": 1.8}
EXIT_OVERRIDES = {
    "SHIPPED": {},
    "OR20": {"FNO_PROFIT_LOCK_ENABLED": True, "FNO_PROFIT_LOCK_ARM_R": 0.80, "FNO_PROFIT_LOCK_FLOOR_R": 0.10,
             "FNO_PROFIT_LOCK_KEEP_FRACTION": 0.5, "FNO_TIME_STOP_MIN": 75.0, "FNO_TRAIL_ATR_MULT": 1.5},
    "EFF": {"FNO_TIME_STOP_MIN": 60.0, "FNO_TRAIL_ATR_MULT": 1.5, "FNO_PROFIT_LOCK_ENABLED": False},
    "TPB": {"FNO_PROFIT_LOCK_ENABLED": False, "FNO_TIME_STOP_MIN": 120.0, "FNO_TRAIL_ATR_MULT": 2.0},
}
# The O28/O29b research values (NIFTY front future, 09:45), from docs/research/fno/2026-10-28-chop-study.
SEED = {"2026-09-02": 0.23665659617320556, "2026-09-03": 0.6990521327014098, "2026-09-04": 0.2139037433154997,
        "2026-09-07": 0.5934065934065934, "2026-09-08": 0.591351351351336, "2026-09-09": 0.46632124352333365,
        "2026-09-10": 0.0039032006245119225, "2026-09-11": 0.6060606060606283, "2026-09-15": 1.0,
        "2026-09-16": 0.15148698884757894, "2026-09-17": 0.1379800853485182, "2026-09-18": 0.47205707491081683,
        "2026-09-21": 0.5060240963855092, "2026-09-22": 0.31235955056183046, "2026-09-23": 0.21382289416845363,
        "2026-09-24": 0.6207674943566693, "2026-09-25": 0.018707482993172764, "2026-09-28": 0.9773242630385488,
        "2026-09-29": 0.6556962025316456, "2026-09-30": 0.11294117647057111, "2026-10-01": 0.18127786032690726,
        "2026-10-05": 0.6262042389209844, "2026-10-06": 0.3877005347593432, "2026-10-07": 0.10937499999998922,
        "2026-10-08": 0.956589147286779, "2026-10-09": 0.8493677844969696, "2026-10-12": 0.4385266301642663,
        "2026-10-13": 1.0, "2026-10-14": 0.10561797752807899, "2026-10-15": 0.7561705310396466,
        "2026-10-16": 0.37540603248260535, "2026-10-19": 0.08088458043017613, "2026-10-21": 0.7017766497461901,
        "2026-10-22": 0.0003769317753431727, "2026-10-23": 0.7142857142857143, "2026-10-26": 0.13912310286678078,
        "2026-10-27": 0.3424657534246523, "2026-10-28": 0.08783783783784904}
# [O29d] SENSEX's own values (SENSEX front future, 09:46), from docs/research/fno/2026-10-28-sensex-check.
SEED_SENSEX = {"2026-09-02": 0.5206670214653346, "2026-09-03": 0.07812500000000197, "2026-09-04": 0.8199568910866009,
               "2026-09-07": 0.5546093672640945, "2026-09-08": 0.646492434663006, "2026-09-09": 0.6567525259712429,
               "2026-09-10": 0.06832901554405643, "2026-09-11": 0.6770186335403531, "2026-09-15": 0.5,
               "2026-09-16": 0.3166630739383402, "2026-09-17": 0.40712589073633004,
               "2026-09-18": 0.22617625985194414, "2026-09-21": 0.5654787462430162,
               "2026-09-22": 0.006041707269549378, "2026-09-23": 0.2727768685215667, "2026-09-24": 0.290939318370768,
               "2026-09-25": 0.2048624440179141, "2026-09-28": 0.9186135580237452, "2026-09-29": 0.6917313717477305,
               "2026-09-30": 0.6485435050764045, "2026-10-01": 0.3739040742650963, "2026-10-05": 0.7957108114084162,
               "2026-10-06": 0.22972972972977718, "2026-10-07": 0.34905533967573904,
               "2026-10-08": 0.8101077666294882, "2026-10-09": 1.0, "2026-10-12": 0.2505499877780458,
               "2026-10-13": 1.0, "2026-10-14": 0.22093237516122727, "2026-10-15": 0.77087451755627,
               "2026-10-16": 0.3105278974256272, "2026-10-19": 0.0, "2026-10-21": 0.8022445162387518,
               "2026-10-22": 0.16455166643424773, "2026-10-23": 0.05419639823308506,
               "2026-10-26": 0.18177194588546974, "2026-10-27": 0.055809800200915645,
               "2026-10-28": 0.4937735302635278}
SEEDS = {"NIFTY": SEED, "SENSEX": SEED_SENSEX}

# [O29d] One row per session per underlying (the O29c table was keyed by the session alone; it is migrated).
_DDL = """
CREATE TABLE IF NOT EXISTS fno_opening_drive (
  session_date TEXT NOT NULL,
  underlying TEXT NOT NULL,
  value REAL NOT NULL,
  source TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  PRIMARY KEY (session_date, underlying)
)"""


def mode() -> str:
    return str(settings.FNO_BOOK).upper()


def enabled_for(underlying: str) -> bool:
    """[O29d] The book trades every underlying the paper book trades (NIFTY and SENSEX)."""
    return mode() in BOOKS and bool(str(underlying or "").strip())


def with_participation(bars: Optional[pd.DataFrame], volume_bars: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """[O29d] ``bars`` carrying the volume of ``volume_bars`` for the same 5-minute bar (0 where it has none). SENSEX
    futures volume is too thin to measure participation, so SENSEX reads NIFTY's, as its shipped signal does
    (``evaluate_fno_mom(rvol_bars=...)``); every price stays the underlying's own. None: ``bars`` unchanged."""
    if volume_bars is None or bars is None or bars.empty:
        return bars
    source = volume_bars[~volume_bars.index.duplicated(keep="last")]
    out = bars.copy()
    out["volume"] = source["volume"].reindex(out.index).fillna(0.0).values
    return out


def exit_overrides(strategy: Optional[str]) -> dict:
    """The exits a position's strategy is managed with (none for the shipped break or an older position)."""
    return dict(EXIT_OVERRIDES.get(strategy or "", {}))


# ---- the opening drive --------------------------------------------------------------------------------------------

def _closed(bars: pd.DataFrame, now: datetime) -> pd.DataFrame:
    naive = pd.Timestamp(now.replace(tzinfo=None))
    frame = bars[~bars.index.duplicated(keep="last")].sort_index()
    return frame[frame.index + pd.Timedelta(minutes=5) <= naive]


def opening_drive(bars: Optional[pd.DataFrame], day: date, now: datetime) -> Optional[float]:
    """Today's opening drive from closed 5-minute futures bars, or None: before the 09:40 bar has closed, without the
    six exact opening bars from 09:15, or with fewer than 6 earlier sessions in the frame."""
    if bars is None or bars.empty:
        return None
    closed = _closed(bars, now)
    dates = closed.index.date
    if len({d for d in dates if d < day}) < DRIVE_MIN_PRIOR_SESSIONS:
        return None
    today = closed[dates == day]
    if today.empty:
        return None
    mins = today.index.hour * 60 + today.index.minute
    if mins[0] != 555:
        return None
    opening = today[(mins >= 555) & (mins < 585)]
    expected = pd.date_range(pd.Timestamp(day) + pd.Timedelta(minutes=555), periods=6, freq="5min")
    if not opening.index.equals(expected):
        return None
    o0 = float(opening["open"].iloc[0])
    c = [float(v) for v in opening["close"]]
    path = abs(c[0] - o0) + sum(abs(c[i] - c[i - 1]) for i in range(1, 6))
    return abs(c[-1] - o0) / path if path > 0 else 0.0


def drive_side(value: Optional[float], history: list) -> Optional[str]:
    """HIGH when above the median of the previous DRIVE_LOOKBACK values (oldest first), LOW otherwise; None without
    a value or with fewer than DRIVE_MIN_PRIOR earlier values."""
    history = [v for v in history if v is not None][-DRIVE_LOOKBACK:]
    if value is None or len(history) < DRIVE_MIN_PRIOR:
        return None
    return "HIGH" if value > statistics.median(history) else "LOW"


async def init_opening_drive_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        keys = [r[1] for r in sorted((r for r in await (await db.execute(
            "PRAGMA table_info(fno_opening_drive)")).fetchall() if r[5]), key=lambda r: r[5])]
        if keys == ["session_date"]:      # [O29d] the O29c layout: keep its rows under the per-underlying key
            await db.execute("ALTER TABLE fno_opening_drive RENAME TO fno_opening_drive_o29c")
            await db.execute(_DDL)
            await db.execute("INSERT OR IGNORE INTO fno_opening_drive SELECT session_date, underlying, value, source, "
                             "recorded_at FROM fno_opening_drive_o29c")
            await db.execute("DROP TABLE fno_opening_drive_o29c")
        await db.execute(_DDL)
        for underlying, seed in SEEDS.items():
            await db.executemany(
                "INSERT OR IGNORE INTO fno_opening_drive(session_date,underlying,value,source,recorded_at) "
                "VALUES(?, ?, ?, 'research_seed', '2026-10-28T19:00:00+05:30')",
                [(d, underlying, v) for d, v in sorted(seed.items())])
        await db.commit()


async def _record(db_path: str, day: date, value: float, source: str, now: datetime, underlying: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("INSERT OR IGNORE INTO fno_opening_drive(session_date,underlying,value,source,recorded_at) "
                         "VALUES(?, ?, ?, ?, ?)", (day.isoformat(), underlying, float(value), source, now.isoformat()))
        await db.commit()


async def drive_history(db_path: str, day: date, underlying: str = "NIFTY") -> list:
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute(
            "SELECT value FROM fno_opening_drive WHERE underlying=? AND session_date < ? "
            "ORDER BY session_date DESC LIMIT ?", (underlying, day.isoformat(), DRIVE_LOOKBACK))).fetchall()
    return [float(r[0]) for r in reversed(rows)]


_TODAY: dict = {}


async def drive_today(db_path: str, bars: Optional[pd.DataFrame], now: datetime, underlying: str = "NIFTY") -> tuple:
    """(today's drive, its side) for ``underlying``, from its own futures bars. Read once the 09:40 bar has closed
    and then kept for the day; earlier sessions in the bars that the table lacks (the engine was down) are
    backfilled first."""
    day = now.date()
    underlying = underlying.upper()
    key = (db_path, underlying, day.isoformat())
    if key in _TODAY:
        return _TODAY[key]
    value = opening_drive(bars, day, now)
    if value is None:
        return None, None
    await init_opening_drive_db(db_path)
    closed = _closed(bars, now)
    for earlier in sorted({d for d in closed.index.date if d < day}):
        past = opening_drive(closed, earlier, datetime.combine(earlier, datetime.min.time()) + timedelta(hours=16))
        if past is not None:
            await _record(db_path, earlier, past, "backfill", now, underlying)
    await _record(db_path, day, value, "live", now, underlying)
    result = (value, drive_side(value, await drive_history(db_path, day, underlying)))
    for stale in [k for k in _TODAY if k[2] != day.isoformat()]:
        del _TODAY[stale]
    _TODAY[key] = result
    return result


# ---- [O29h] the trend gate: yesterday's NIFTY daily ADX(14) ----------------------------------------------------------

_ADX_DDL = """
CREATE TABLE IF NOT EXISTS fno_regime_gate (
  session_date TEXT PRIMARY KEY,
  adx14 REAL NOT NULL,
  threshold REAL NOT NULL,
  side TEXT NOT NULL,
  last_bar TEXT NOT NULL,
  bars INTEGER NOT NULL,
  recorded_at TEXT NOT NULL
)"""


def adx(daily: pd.DataFrame, n: int = ADX_LEN) -> pd.Series:
    """Wilder's ADX on daily bars, exactly the O29g research formula (features.adx)."""
    high, low, close = daily["high"], daily["low"], daily["close"]
    up, down = high.diff(), -low.diff()
    plus = ((up > down) & (up > 0)) * up
    minus = ((down > up) & (down > 0)) * down
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * plus.ewm(alpha=1 / n, adjust=False).mean() / atr
    mdi = 100 * minus.ewm(alpha=1 / n, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, float("nan"))
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def daily_adx(daily: Optional[pd.DataFrame], day: date) -> tuple:
    """(ADX of the last daily bar before ``day``, that bar's date) - a bar dated ``day`` (today's running candle)
    is never read; (None, None) with fewer than ADX_MIN_BARS bars."""
    if daily is None or daily.empty:
        return None, None
    frame = daily.copy()
    if "date" in frame.columns:
        frame = frame.set_index("date")
    frame.index = pd.to_datetime(frame.index).normalize()
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    frame = frame[frame.index.date < day]
    if len(frame) < ADX_MIN_BARS:
        return None, None
    value = float(adx(frame).iloc[-1])
    return (None, None) if pd.isna(value) else (value, frame.index[-1].date())


def adx_side(value: Optional[float], threshold: Optional[float] = None) -> Optional[str]:
    threshold = float(settings.FNO_BOOK_ADX_MIN if threshold is None else threshold)
    return None if value is None else ("HIGH" if value >= threshold else "LOW")


_ADX_TODAY: dict = {}


async def adx_today(db_path: str, kite, now: datetime) -> tuple:
    """(yesterday's NIFTY ADX(14), its side against FNO_BOOK_ADX_MIN) for today's session, read once a day from 09:30
    from the daily candles and kept in ``fno_regime_gate``. The owner gets one message a day saying whether the book
    trades. A failed read is not kept: the next tick tries again, and until then the book sits out
    (``adx_unknown``)."""
    day = now.date()
    key = (db_path, day.isoformat())
    if key in _ADX_TODAY:
        return _ADX_TODAY[key]
    if now.hour * 60 + now.minute < ADX_READ_FROM_MIN:
        return None, None
    try:
        # Through today: the cache then holds yesterday's complete candle (today's running one is dropped below).
        daily = await kite.get_historical(
            "NIFTY 50", (day - timedelta(days=ADX_HISTORY_CALENDAR_DAYS)).isoformat(), day.isoformat())
    except Exception as exc:  # the book sits out rather than trading unfiltered
        logger.warning("fno_book_adx_read_failed", err=str(exc))
        return None, None
    value, last_bar = daily_adx(daily, day)
    if value is None:
        logger.warning("fno_book_adx_unavailable", bars=0 if daily is None else len(daily))
        return None, None
    threshold = float(settings.FNO_BOOK_ADX_MIN)
    side = adx_side(value, threshold)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(_ADX_DDL)
        cur = await db.execute(
            "INSERT OR IGNORE INTO fno_regime_gate(session_date,adx14,threshold,side,last_bar,bars,recorded_at) "
            "VALUES(?,?,?,?,?,?,?)", (day.isoformat(), value, threshold, side, last_bar.isoformat(),
                                      int(len(daily)), now.isoformat()))
        first = cur.rowcount == 1
        await db.commit()
    if first:
        from operator_alert import notify_operator
        verdict = ("trending market - the F&O book trades today" if side == "HIGH" else
                   "sideways market - the F&O book sits today out (no new trades)")
        await notify_operator(
            f"📈 F&O trend gate {day:%d %b}: NIFTY ADX(14) {value:.1f} (yesterday's daily candle; trades at "
            f"{threshold:g} or more) → {verdict}. Paper only; the real-money test follows the paper book.",
            event="fno_book_adx_gate")
    for stale in [k for k in _ADX_TODAY if k[1] != day.isoformat()]:
        del _ADX_TODAY[stale]
    _ADX_TODAY[key] = (value, side)
    return value, side


# ---- the efficiency break (O27e lab, EFFICIENCY_BREAK only) ----------------------------------------------------------

_FEATURES: "OrderedDict[int, tuple]" = OrderedDict()


def _features(frame: pd.DataFrame) -> pd.DataFrame:
    """The lab's causal features: later rows cannot change an earlier row."""
    cached = _FEATURES.get(id(frame))
    if cached and cached[0]() is frame:
        return cached[1]
    n = EFF_GENOME["lookback"]
    x = frame.copy()
    by_day = x.groupby(x.index.date, sort=False)
    previous = x.close.shift(1)
    tr = pd.concat([x.high - x.low, (x.high - previous).abs(), (x.low - previous).abs()], axis=1).max(axis=1)
    x["atr"] = tr.ewm(alpha=1 / settings.FNO_ATR_LEN, adjust=False).mean()
    x["vwap"] = (((x.high + x.low + x.close) / 3 * x.volume).groupby(x.index.date).cumsum()
                 / x.volume.groupby(x.index.date).cumsum().replace(0, float("nan")))
    x["rvol"] = float("nan")
    for _, slots in x.groupby([x.index.hour, x.index.minute]):
        base = slots.volume.rolling(f"{int(settings.FNO_RVOL_LOOKBACK_DAYS)}D", closed="left", min_periods=3).mean()
        x.loc[slots.index, "rvol"] = slots.volume / base.replace(0, float("nan"))
    x[f"hi{n}"] = by_day.high.transform(lambda s: s.shift(1).rolling(n).max())
    x[f"lo{n}"] = by_day.low.transform(lambda s: s.shift(1).rolling(n).min())
    changes = by_day.close.transform(lambda s: s.diff().abs().rolling(n).sum())
    displacement = by_day.close.transform(lambda s: (s - s.shift(n)).abs())
    x[f"er{n}"] = displacement / changes.replace(0, float("nan"))
    _FEATURES[id(frame)] = (weakref.ref(frame), x)
    while len(_FEATURES) > 3:
        _FEATURES.popitem(last=False)
    return x


def efficiency_break(frame: pd.DataFrame, regime: str, now: datetime) -> MomSignal:
    """A close through the last 4 bars' high (low) by 0.2 ATR, from a bar that was not through it, with efficiency
    >= 0.35 over those bars, a body >= 55% of the bar and participation >= 1.2; stop 2 ATR or the 4-bar extreme
    (the nearer), target 1.8R. Closed bars only."""
    g, out = EFF_GENOME, MomSignal()
    if frame is None or frame.empty or not frame.index.is_monotonic_increasing or not frame.index.is_unique:
        out.reject_reason = "eff:invalid_frame"
        return out
    naive = now.replace(tzinfo=None)
    end = int(frame.index.searchsorted(pd.Timestamp(naive - timedelta(minutes=5)), side="right"))
    if end < settings.FNO_ATR_LEN + 1:
        out.reject_reason = "eff:warmup"
        return out
    rows = _features(frame).iloc[:end]
    today = rows[rows.index.date == naive.date()]
    n = g["lookback"]
    if len(today) < max(n + 2, 7):
        out.reject_reason = "eff:session_warmup"
        return out
    minutes = today.index.hour * 60 + today.index.minute
    opening = today[(minutes >= 555) & (minutes < 585)]
    expected = pd.date_range(pd.Timestamp(naive.date()) + pd.Timedelta(minutes=555), periods=6, freq="5min")
    if not opening.index.equals(expected) or today.index[-1] < expected[-1] + pd.Timedelta(minutes=5):
        out.reject_reason = "eff:opening_range"
        return out
    tail = today.iloc[-(n + 2):]
    if not (tail.index.to_series().diff().dropna() == pd.Timedelta(minutes=5)).all():
        out.reject_reason = "eff:bar_gap"
        return out
    r, p = today.iloc[-1], today.iloc[-2]
    out.bar_ts = today.index[-1].strftime("%Y-%m-%d %H:%M:%S")
    out.close, out.atr = float(r.close), float(r.atr)
    out.or_high, out.or_low = float(opening.high.max()), float(opening.low.min())
    out.rvol = float(r.rvol) if pd.notna(r.rvol) else 0.0
    if regime == "REGIME_3_CRISIS":
        out.reject_reason = "eff:crisis"
        return out
    if pd.isna(r.rvol) or r.rvol < g["rvol"]:
        out.reject_reason = "eff:rvol"
        return out
    hi, lo, er = float(r[f"hi{n}"]), float(r[f"lo{n}"]), float(r[f"er{n}"])
    body = abs(r.close - r.open) / max(float(r.high - r.low), 1e-9)
    if not all(pd.notna(v) for v in (hi, lo, er, r.vwap)) or out.atr <= 0 or body < g["body"]:
        out.reject_reason = "eff:shape"
        return out
    long = r.close > hi + g["buffer"] * r.atr and p.close <= p[f"hi{n}"] + g["buffer"] * p.atr
    short = r.close < lo - g["buffer"] * r.atr and p.close >= p[f"lo{n}"] - g["buffer"] * p.atr
    if er < g["efficiency"]:
        out.reject_reason = "eff:efficiency"
        return out
    if not (long or short):
        out.reject_reason = "eff:no_trigger"
        return out
    distance = g["stop"] * out.atr
    stop = max(lo, r.close - distance) if long else min(hi, r.close + distance)
    risk = (r.close - stop) if long else (stop - r.close)
    if risk <= 0:
        out.reject_reason = "eff:degenerate_stop"
        return out
    out.direction = FnoDirection.LONG if long else FnoDirection.SHORT
    out.stop_underlying = float(stop)
    out.target_underlying = float(r.close + (1 if long else -1) * g["target"] * risk)
    return out


# ---- [O31d] the stretched entry ---------------------------------------------------------------------------------------

def entry_stretch(bars: Optional[pd.DataFrame], now: datetime, direction: FnoDirection) -> Optional[float]:
    """How far the last closed 5-minute close stands beyond today's VWAP, in the trade's direction, as a share of the
    first 30 minutes' range, exactly the research's lab_s.stretch_at. None without the six opening bars from 09:15, a
    range, or an earlier session in the frame: the check then does not apply."""
    if bars is None or bars.empty:
        return None
    naive = now.replace(tzinfo=None)
    frame = bars[~bars.index.duplicated(keep="last")].sort_index()
    today = frame[frame.index.date == naive.date()]
    if today.empty or not (frame.index.date < naive.date()).any():
        return None
    minutes = today.index.hour * 60 + today.index.minute
    opening = today[minutes < 585]
    if len(opening) != 6 or minutes[0] != 555:
        return None
    high, low = float(opening["high"].max()), float(opening["low"].min())
    if high <= low:
        return None
    position = int(today.index.searchsorted(pd.Timestamp(naive) - pd.Timedelta(minutes=5), side="right"))
    if position == 0:
        return None
    typical = (today["high"] + today["low"] + today["close"]) / 3
    volume = today["volume"].astype(float)
    vwap = ((typical * volume).cumsum() / volume.cumsum().replace(0, float("nan"))).fillna(typical.expanding().mean())
    side = 1 if direction == FnoDirection.LONG else -1
    return round(side * (float(today["close"].iloc[position - 1]) - float(vwap.iloc[position - 1])) / (high - low), 4)


# ---- the book -------------------------------------------------------------------------------------------------------

def _variants() -> tuple:
    from fno_shadow import VARIANTS
    return replace(VARIANTS["FNO_OR_20"], name="GRID_OR20_NOEMA", ema_filter=False), VARIANTS["FNO_TREND_PULLBACK"]


def book_signal(bars: pd.DataFrame, regime: str, now: datetime, *, shipped: MomSignal,
                side: Optional[str], gate: str = "DRIVE", adx_side: Optional[str] = None) -> MomSignal:
    """The first strategy (SHIPPED, OR20, EFF, TPB) with a signal on this bar; a copy carrying ``strategy``.
    gate DRIVE (UNION_DRIVE): the breakouts only on a HIGH opening drive ``side``. gate ADX (UNION_ADX): all four
    only when ``adx_side`` is HIGH, and [O31d] the first signal is passed over when its entry is stretched: the tick
    takes no entry at all, as in the research (``stretched:<strategy>``). ``shipped`` is the tick's shipped evaluation
    (never changed: it is shared). Without a signal: the shipped evaluation's fields, and why (``drive_low:`` /
    ``drive_unknown:`` / ``adx_low:`` / ``adx_unknown:`` when the gate kept strategies off)."""
    from fno_shadow import _variant_signal
    or20, tpb = _variants()
    for name in STRATEGIES:
        if gate == "ADX" and adx_side != "HIGH":
            break
        if gate != "ADX" and name in BREAKOUTS and side != "HIGH":
            continue
        if name == "SHIPPED":
            sig = shipped
        elif name == "OR20":
            sig = _variant_signal(bars, regime, now, or20)
        elif name == "EFF":
            sig = efficiency_break(bars, regime, now)
        else:
            sig = _variant_signal(bars, regime, now, tpb)
        if sig.direction is not None:
            limit = float(settings.FNO_BOOK_MAX_STRETCH)
            stretch = entry_stretch(bars, now, sig.direction) if gate == "ADX" and limit > 0 else None
            if stretch is not None and stretch >= limit:
                logger.info("fno_book_entry_stretched", strategy=name, direction=sig.direction.value, stretch=stretch)
                return replace(sig, direction=None, strategy="", reject_reason=f"stretched:{name}")
            return replace(sig, strategy=name)
    reason = shipped.reject_reason or "no_signal"
    if gate == "ADX" and adx_side != "HIGH":
        reason = f"adx_{(adx_side or 'unknown').lower()}:{'book_skipped' if shipped.direction else reason}"
    elif gate != "ADX" and side != "HIGH":
        reason = f"drive_{(side or 'unknown').lower()}:{'breakout_skipped' if shipped.direction else reason}"
    return replace(shipped, direction=None, strategy="", reject_reason=reason)
