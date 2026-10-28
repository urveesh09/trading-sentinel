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

NIFTY only: the research replays NIFTY only, so SENSEX keeps the shipped strategy. ``FNO_BOOK=SHIPPED`` restores the
shipped strategy for NIFTY. Each position keeps its strategy (``fno_positions.strategy``) and is managed with that
strategy's exits, whatever the setting is later.
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

from config import settings
from fno_engine_mom import MomSignal
from fno_models import FnoDirection

BOOK = "UNION_DRIVE"
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

_DDL = """
CREATE TABLE IF NOT EXISTS fno_opening_drive (
  session_date TEXT PRIMARY KEY,
  underlying TEXT NOT NULL,
  value REAL NOT NULL,
  source TEXT NOT NULL,
  recorded_at TEXT NOT NULL
)"""


def enabled_for(underlying: str) -> bool:
    return str(settings.FNO_BOOK).upper() == BOOK and underlying.upper() == "NIFTY"


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
        await db.execute(_DDL)
        await db.executemany(
            "INSERT OR IGNORE INTO fno_opening_drive(session_date,underlying,value,source,recorded_at) "
            "VALUES(?, 'NIFTY', ?, 'O29b_seed', '2026-10-28T19:00:00+05:30')", sorted(SEED.items()))
        await db.commit()


async def _record(db_path: str, day: date, value: float, source: str, now: datetime) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("INSERT OR IGNORE INTO fno_opening_drive(session_date,underlying,value,source,recorded_at) "
                         "VALUES(?, 'NIFTY', ?, ?, ?)", (day.isoformat(), float(value), source, now.isoformat()))
        await db.commit()


async def drive_history(db_path: str, day: date) -> list:
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute(
            "SELECT value FROM fno_opening_drive WHERE session_date < ? ORDER BY session_date DESC LIMIT ?",
            (day.isoformat(), DRIVE_LOOKBACK))).fetchall()
    return [float(r[0]) for r in reversed(rows)]


_TODAY: dict = {}


async def drive_today(db_path: str, bars: Optional[pd.DataFrame], now: datetime) -> tuple:
    """(today's drive, its side). Read once the 09:40 bar has closed and then kept for the day; earlier sessions in
    the bars that the table lacks (the engine was down) are backfilled first."""
    day = now.date()
    key = (db_path, day.isoformat())
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
            await _record(db_path, earlier, past, "backfill", now)
    await _record(db_path, day, value, "live", now)
    result = (value, drive_side(value, await drive_history(db_path, day)))
    _TODAY.clear()
    _TODAY[key] = result
    return result


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


# ---- the book -------------------------------------------------------------------------------------------------------

def _variants() -> tuple:
    from fno_shadow import VARIANTS
    return replace(VARIANTS["FNO_OR_20"], name="GRID_OR20_NOEMA", ema_filter=False), VARIANTS["FNO_TREND_PULLBACK"]


def book_signal(bars: pd.DataFrame, regime: str, now: datetime, *, shipped: MomSignal,
                side: Optional[str]) -> MomSignal:
    """The first strategy (SHIPPED, OR20, EFF, TPB) with a signal on this bar, the breakouts only on a HIGH drive; a
    copy carrying ``strategy``. ``shipped`` is the tick's shipped evaluation (never changed: it is shared). Without a
    signal: the shipped evaluation's fields, and why (``drive_low:`` / ``drive_unknown:`` when the breakouts were
    off)."""
    from fno_shadow import _variant_signal
    or20, tpb = _variants()
    for name in STRATEGIES:
        if name in BREAKOUTS and side != "HIGH":
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
            return replace(sig, strategy=name)
    reason = shipped.reject_reason or "no_signal"
    if side != "HIGH":
        reason = f"drive_{(side or 'unknown').lower()}:{'breakout_skipped' if shipped.direction else reason}"
    return replace(shipped, direction=None, strategy="", reject_reason=reason)
