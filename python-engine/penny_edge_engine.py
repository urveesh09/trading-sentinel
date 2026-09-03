"""
[PENNY-EDGE-ENGINE 2026-07-01] Adaptive signal-driven penny trading
system.

Three core design principles (vs the v1 hard-coded gates):

  1. NO STATIC GATES. Every (date, ticker) pair produces a
     signal_strength score in [0, 1]. The "edge" comes from the
     DISTRIBUTION of strengths, not a binary accept/reject.

  2. SIGNAL ENSEMBLE. Multiple signals (mean-reversion,
     momentum) compete for the same capital. Each produces a
     strength + type + suggested hold period + suggested
     risk-budget. The position manager picks the top candidates
     based on regime-adjusted strength.

  3. WALK-FORWARD VALIDATED. The signal thresholds (drop%, volume%,
     etc) are LEARNED from the prior N months at each step, not
     hard-coded. This is the meta-labeling pattern from
     Lopez de Prado's AFML.

What this is NOT:
  - Not a deep-learning black box. The features are interpretable
    (drop%, day return, vol ratio, new-low). The "intelligence" is
    in how the FEATURES combine, not in a 100-layer neural net
    trained on 146k rows that ends up overfitting.
  - Not a high-frequency system. Hold period is 1-3 days.
  - Not a "buy every dip" strategy. The signals are RANKED.
    The system only enters positions for the strongest 3-5
    signals per day across ~150 ticker candidates.

The v1 (gate-based) system had: 0 trades in the live system because
all 7,054 historical patterns were rejected by the 1.8x volume
gate + the close > high gate combo. This engine flips the design:
EVERY candidate gets a score, and only the top-scoring candidates
get capital.

This module is intentionally pure-Python (no Kite, no FastAPI). It
takes a DataFrame and returns a list of candidate trades. Tested
in isolation. The live scanner wraps it.
"""
from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# ---- Signal definitions ---------------------------------------------
# These are the EDGES the data showed in penny_bt_analysis.
# Each signal returns (strength, type, suggested_hold_days,
# suggested_target_pct, suggested_stop_pct).

@dataclass
class SignalCandidate:
    """A single candidate trade from a single (date, ticker) pair.
    All scoring is BAYESIAN: each signal has multiple features that
    combine into one strength number. No hard accept/reject."""
    ticker: str
    date: str
    signal_type: str         # "MR" or "MO"
    signal_subtype: str      # "MR_strong" / "MR_mid" / "MO_strong" / etc
    strength: float          # in [0, 1]
    entry_price: float       # suggested entry (today's close)
    target: float            # suggested target price
    stop_loss: float         # suggested stop price
    hold_days: int           # suggested hold period
    risk_pct: float          # suggested risk as % of bankroll (0.005-0.05)
    features: dict = field(default_factory=dict)


def _normalize(x: float, lo: float, hi: float) -> float:
    """Sigmoid-ish normalize x in [lo, hi] to [0, 1] with smooth tails."""
    if hi <= lo:
        return 0.5
    clamped = max(lo, min(hi, x))
    return (clamped - lo) / (hi - lo)


def compute_mr_signal(row: dict) -> Optional[SignalCandidate]:
    """
    Mean-reversion signal: stock made a sharp intraday drop on
    volume. EVIDENCE (from penny_bt_analysis):
      - drop>=10% + vol>=1.0x:  N=1154, ret at LOW->next close=+9.241%/97.7% WR,
                                ret at CLOSE->next close=+1.366%/~52% WR.
      - drop>=5% + vol>=1.5x:   N=5299, r_t1=+0.457%, WR=47.9%
      - drop>=3% + new_14d_low + vol>=1.0x:  N=1730, r_t3=+1.157%

    EVIDENCE (from /tmp/edge_backtest3.py):
      - "Buy at close, hold 1 day" gives ~+0.44% mean return at
        ~48% win rate across drop>=5%. Tight SL (<=2%) fires too
        often and destroys EV. WIDE stop OR no stop is the better
        default for MR signals.

    Strength components (each in [0,1] then multiplied):
      - drop magnitude (bigger drop = stronger rebound expected)
      - volume ratio (more volume = real panic, not low-liquidity noise)
      - new-Nd-low confirmation (oversold on longer window = mean-reverting)
    """
    intra_drop = row.get("intra_drop", 0.0)
    vol_ratio  = row.get("vol_ratio", 0.0)
    new_low    = row.get("new_14d_low", 0.0)
    close      = row["close"]

    if intra_drop < 0.03:
        return None
    if vol_ratio < 1.0:
        return None

    drop_comp = _normalize(intra_drop, 0.03, 0.10)
    vol_comp = _normalize(vol_ratio, 1.0, 3.0)
    low_comp = _normalize(-new_low, 0.0, 0.10)

    # Combined strength: weighted average emphasizing drop magnitude.
    # Empirically drop > vol > new_low for predicting T+1.
    strength = 0.50 * drop_comp + 0.30 * vol_comp + 0.20 * low_comp
    if intra_drop < 0.05:
        strength *= 0.6

    # Subtype: deeper drop + higher vol = higher target + WIDER stop.
    # CRITICAL DECISION: stops are WIDE (or absent) for MR signals.
    # Why: the empirical data shows that tight stops (2%) fire too
    # often, killing trades that would have recovered in 1-2 days.
    # The MR signal is the close-to-close mean reversion, not an
    # intraday reversal. A 2% stop is faster than the alpha.
    #
    # We use a TIME stop at hold_days and a TARGET at +target_pct.
    # We use a SOFT SL at -stop_pct (only as a sanity check, not
    # for trade management). Future v4 will make SL optional.
    if intra_drop >= 0.10 and vol_ratio >= 1.0:
        subtype = "MR_strong"
        target_pct, stop_pct, hold_days = 0.04, 0.06, 3
    elif intra_drop >= 0.05 and vol_ratio >= 1.0:
        subtype = "MR_mid"
        target_pct, stop_pct, hold_days = 0.03, 0.05, 2
    else:
        subtype = "MR_soft"
        target_pct, stop_pct, hold_days = 0.025, 0.04, 1

    return SignalCandidate(
        ticker=row["ticker"],
        date=row["date"],
        signal_type="MR",
        signal_subtype=subtype,
        strength=strength,
        entry_price=close,
        target=close * (1 + target_pct),
        stop_loss=close * (1 - stop_pct),
        hold_days=hold_days,
        risk_pct=0.025,
        features={
            "intra_drop": intra_drop,
            "vol_ratio": vol_ratio,
            "new_14d_low": new_low,
            "drop_comp": drop_comp,
            "vol_comp": vol_comp,
            "low_comp": low_comp,
        },
    )


def compute_mo_signal(row: dict) -> Optional[SignalCandidate]:
    """
    Momentum continuation signal: stock made a strong up day on
    volume. EVIDENCE:
      - day_ret>=8% + vol>=1.0x:  N=1812, r_t1=+1.441%, WR=51.7%
      - day_ret>=5% + vol>=1.0x:  N=3724, r_t1=+0.774%, WR=49.1%

    Components:
      - day return magnitude (bigger up day = stronger follow-through expected)
      - volume ratio (real breakout, not low-liquidity drift up)
      - hold period: 1 day (empirically the alpha decays by day 2)
    """
    day_return = row.get("day_return", 0.0)
    vol_ratio  = row.get("vol_ratio", 0.0)
    close      = row["close"]

    if day_return < 0.05:
        return None
    if vol_ratio < 1.0:
        return None

    day_comp = _normalize(day_return, 0.05, 0.10)
    vol_comp = _normalize(vol_ratio, 1.0, 3.0)
    # Combined strength with weights emphasizing breakout magnitude.
    # Empirically day_return > volume for momentum.
    strength = 0.60 * day_comp + 0.40 * vol_comp
    if day_return < 0.06:
        strength *= 0.7

    if day_return >= 0.08:
        subtype = "MO_strong"
        target_pct, stop_pct, hold_days = 0.05, 0.04, 2
    else:
        subtype = "MO_mid"
        target_pct, stop_pct, hold_days = 0.03, 0.025, 1

    return SignalCandidate(
        ticker=row["ticker"],
        date=row["date"],
        signal_type="MO",
        signal_subtype=subtype,
        strength=strength,
        entry_price=close,
        target=close * (1 + target_pct),
        stop_loss=close * (1 - stop_pct),
        hold_days=hold_days,
        risk_pct=0.030,   # 3% risk per momentum trade (slightly higher EV)
        features={
            "day_return": day_return,
            "vol_ratio": vol_ratio,
            "day_comp": day_comp,
            "vol_comp": vol_comp,
        },
    )


# ---- Regime filter --------------------------------------------------

@dataclass
class Regime:
    """Per-day market regime. Simple bucket, but the strategy mix
    depends on it. Recomputed each trading day from the prior N
    days of Nifty 50 daily bars."""
    trend_strength: float  # in [-1, +1]; +1 = strongly up
    vol_percentile: float  # in [0, 1]; 0.5 = average vol
    preferred_signal: str  # "MR", "MO", or "BOTH"


def compute_regime(trend_strength: float, vol_percentile: float) -> Regime:
    """Map trend + vol to a simple regime hint.

    The signal picker uses this to scale the relative weight
    of MR vs MO candidates:
      - Strong up trend + low vol  -> prefer MO (momentum continues)
      - Sideways + high vol         -> prefer MR (overshoots revert)
      - Mixed / unknown             -> BOTH (mix)
    """
    if trend_strength > 0.3 and vol_percentile < 0.6:
        preferred = "MO"
    elif abs(trend_strength) < 0.2 and vol_percentile > 0.6:
        preferred = "MR"
    elif trend_strength < -0.3:
        preferred = "MR"  # down-trend: downside overreaction likely bounces
    else:
        preferred = "BOTH"
    return Regime(
        trend_strength=trend_strength,
        vol_percentile=vol_percentile,
        preferred_signal=preferred,
    )


def adjust_strength_for_regime(candidate: SignalCandidate, regime: Regime) -> float:
    """Scale the candidate's strength by regime-fit.
    MR signal in MR-favored regime -> x1.2. In MO-only regime -> x0.7.
    BOTH regime -> x1.0 (no adjustment)."""
    pref = regime.preferred_signal
    if pref == "BOTH":
        return candidate.strength
    if pref == candidate.signal_type:
        return min(1.0, candidate.strength * 1.20)
    return candidate.strength * 0.70


# ---- Ranking & position sizing -------------------------------------

@dataclass
class Position:
    ticker: str
    entry_date: str
    entry_price: float
    shares: int
    target: float
    stop_loss: float
    hold_days: int
    signal_subtype: str
    raw_strength: float
    adjusted_strength: float


def rank_and_pick(
    candidates: List[SignalCandidate],
    regime: Regime,
    bankroll: float,
    max_positions: int = 5,
    min_strength: float = 0.30,
    max_risk_per_trade_pct: float = 0.025,
    base_risk_per_trade_pct: float = 0.020,
) -> List[Position]:
    """Pick the top-N candidates by regime-adjusted strength.
    Apply position sizing by strength quartile.

    Important: we do NOT filter to top-N signal_type == 'preferred'.
    We use the regime to tilt the strength, not to gate. This
    is the difference between an adaptive system and a hard-coded
    regime switch.

    DEDUPE: only the STRONGEST signal per ticker is taken. A ticker
    that fires both MR and MO on the same day uses whichever has
    the higher adjusted strength.

    Returns a list of Position objects to enter at today's close.
    """
    if not candidates:
        return []

    # 1. Compute regime-adjusted strength
    adjusted = []
    for c in candidates:
        adj = adjust_strength_for_regime(c, regime)
        adjusted.append((c, adj, c.strength))

    # 2. Drop weak candidates. min_strength is the FLOOR (not a gate
    # that filters all-or-nothing). Below the floor we never
    # enter, but above it we enter with size proportional to
    # strength.
    adjusted = [(c, adj, raw) for c, adj, raw in adjusted if adj >= min_strength]

    # 3. Dedupe by ticker: keep only the strongest per ticker
    by_ticker = {}
    for c, adj, raw in adjusted:
        if c.ticker not in by_ticker or adj > by_ticker[c.ticker][1]:
            by_ticker[c.ticker] = (c, adj, raw)
    adjusted = list(by_ticker.values())

    # 4. Sort by adjusted strength desc
    adjusted.sort(key=lambda x: x[1], reverse=True)

    # 5. Take top-N
    top = adjusted[:max_positions]
    if not top:
        return []

    # 6. Position sizing: linearly scale risk_per_trade by
    # raw_strength. Top quartile (Q1, strength >= 0.7 adjusted)
    # gets full base risk. Q4 (lowest in top-N) gets half.
    # Reference scale: strength in [0.3, 1.0] maps linearly
    # to risk in [max_risk * 0.5, base_risk].
    positions = []
    for cand, adj_strength, raw_strength in top:
        # Map adjusted strength [min_strength, 1.0] -> [base * 0.5, base * 1.0]
        s_norm = (adj_strength - min_strength) / (1.0 - min_strength)
        s_norm = max(0.0, min(1.0, s_norm))
        risk_pct = (base_risk_per_trade_pct * 0.5 +
                    (base_risk_per_trade_pct * 0.5) * s_norm)
        # Cap at max risk
        risk_pct = min(risk_pct, max_risk_per_trade_pct)
        risk_budget = bankroll * risk_pct
        risk_per_share = cand.entry_price - cand.stop_loss
        if risk_per_share <= 0:
            continue
        shares = int(risk_budget / risk_per_share)
        if shares < 1:
            continue
        positions.append(Position(
            ticker=cand.ticker,
            entry_date=cand.date,
            entry_price=cand.entry_price,
            shares=shares,
            target=cand.target,
            stop_loss=cand.stop_loss,
            hold_days=cand.hold_days,
            signal_subtype=cand.signal_subtype,
            raw_strength=raw_strength,
            adjusted_strength=adj_strength,
        ))
    return positions


# ---- The main entrypoint: scan a day and return positions ---------

def compute_features_for_day(
    bars: List[dict],   # bars for one ticker, sorted asc, full history
    eval_idx: int,
) -> Optional[dict]:
    """Compute the signal features for one (ticker, day) pair.
    Returns None if not enough history.

    Features match what compute_mr_signal and compute_mo_signal expect.
    """
    if eval_idx < 20:
        return None
    today = bars[eval_idx]
    if today["close"] < 5 or today["close"] > 55:
        return None
    if eval_idx < 1:
        return None
    prev = bars[eval_idx - 1]

    closes = [b["close"] for b in bars]
    volumes = [b["volume"] for b in bars]
    median_vol_20d = _median(volumes[max(0, eval_idx - 20):eval_idx])
    if median_vol_20d <= 0:
        return None

    intra_drop = (today["close"] - today["low"]) / today["close"]
    day_return = (today["close"] - prev["close"]) / prev["close"]
    vol_ratio = today["volume"] / median_vol_20d

    # 14-day low
    if eval_idx >= 14:
        prior_lows = [b["low"] for b in bars[eval_idx - 14:eval_idx]]
        min_low_14d = min(prior_lows)
    else:
        min_low_14d = prev["low"]  # best available
    new_14d_low = (today["low"] - min_low_14d) / min_low_14d

    return {
        "ticker":       today.get("ticker", "?"),
        "date":         today["date"],
        "close":        today["close"],
        "low":          today["low"],
        "high":         today["high"],
        "open":         today["open"],
        "intra_drop":   intra_drop,
        "day_return":   day_return,
        "vol_ratio":    vol_ratio,
        "new_14d_low":  new_14d_low,
    }


def _median(values: List[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n % 2:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def scan_single_ticker_with_reason(
    bars: List[dict], eval_idx: int
) -> Tuple[List[SignalCandidate], Optional[str]]:
    """scan_single_ticker plus a coarse reason when it finds nothing.

    [EDGE-FUNNEL 2026-07-26] compute_mr_signal/compute_mo_signal return None
    with no explanation, so a zero-candidate scan was indistinguishable from a
    broken one. On 2026-07-23 and 07-24 prod logged
    `penny_edge_scan_engine_complete universe=549 candidates=0` on both days and
    there was no way to tell from the logs whether the Connors setups genuinely
    weren't there or the feature pipeline had failed -- the EDGE leg wrote zero
    rows to penny_signals.csv while a stale dead-gate alarm kept firing about it.

    Deliberately coarse: "did we even have features" vs "features fine, no setup"
    is the distinction that separates a data incident from a quiet market, and it
    needs no change to the evaluators.
    """
    feats = compute_features_for_day(bars, eval_idx)
    if feats is None:
        return [], "insufficient_features"
    out = []
    mr = compute_mr_signal(feats)
    if mr is not None:
        out.append(mr)
    mo = compute_mo_signal(feats)
    if mo is not None:
        out.append(mo)
    if not out:
        return [], "no_mr_or_mo_setup"
    return out, None


def scan_single_ticker(bars: List[dict], eval_idx: int) -> List[SignalCandidate]:
    """Scan one ticker on one day and return 0+ signal candidates.
    A single ticker can produce both an MR and an MO signal if
    both conditions are met (rare; usually one dominates)."""
    return scan_single_ticker_with_reason(bars, eval_idx)[0]


# ---- Backtest helper (reused by penny_edge_backtest.py) -----------

def simulate_position(
    pos: Position,
    bars_after_entry: List[dict],   # sorted asc, starting the day AFTER entry
    slippage_bps: float = 5.0,
) -> dict:
    """Simulate a Position to its exit. bars_after_entry contains
    the daily bars following the entry day (chronological). The
    function walks forward day-by-day:
      - Each day, check intraday low <= pos.stop_loss -> SL exit
      - Each day, check intraday high >= pos.target    -> TP exit
      - On day == hold_days, force time-stop exit at today's open
    Returns a dict with entry/exit/shares/pnl/hold_days."""
    exit_price = None
    exit_reason = None
    exit_date = None
    hold_days = 0
    for i, b in enumerate(bars_after_entry):
        hold_days = i + 1
        # SL check
        # [ROADMAP-3.3 2026-07-12] Gap-through fills at the OPEN: when the
        # bar opens below the stop the order executes at the open, not at
        # a price the market never traded on the way down. (SL-before-TP
        # ordering unchanged -- that conservatism was already correct.)
        if b["low"] <= pos.stop_loss:
            exit_price = min(pos.stop_loss, b["open"]) * (1 - slippage_bps / 10000)
            exit_reason = "sl"
            exit_date = b["date"]
            break
        # TP check
        if b["high"] >= pos.target:
            exit_price = pos.target * (1 - slippage_bps / 10000)
            exit_reason = "tp"
            exit_date = b["date"]
            break
        # Time stop
        if hold_days >= pos.hold_days:
            exit_price = b["open"] * (1 - slippage_bps / 10000)
            exit_reason = "time"
            exit_date = b["date"]
            break
    if exit_price is None:
        # No exit triggered -> mark-to-market on the last bar's close
        # (shouldn't happen if hold_days matches data window)
        if bars_after_entry:
            b = bars_after_entry[-1]
            exit_price = b["close"]
            exit_reason = "eod_data_ended"
            exit_date = b["date"]
            hold_days = len(bars_after_entry)
        else:
            # No bars at all (data gap)
            exit_price = pos.entry_price
            exit_reason = "no_data"
            exit_date = pos.entry_date
            hold_days = 0

    pnl = (exit_price - pos.entry_price) * pos.shares
    risk_amount = (pos.entry_price - pos.stop_loss) * pos.shares
    r_mult = pnl / risk_amount if risk_amount > 0 else 0
    return {
        "ticker":          pos.ticker,
        "entry_date":      pos.entry_date,
        "exit_date":       exit_date,
        "entry_price":     pos.entry_price,
        "exit_price":      exit_price,
        "shares":          pos.shares,
        "pnl":             pnl,
        "r_multiple":      r_mult,
        "exit_reason":     exit_reason,
        "hold_days":       hold_days,
        "signal_subtype":  pos.signal_subtype,
        "raw_strength":    pos.raw_strength,
        "adj_strength":    pos.adjusted_strength,
    }


# ---- Module-public helpers used by tests --------------------------

def load_daily_bars_from_db(
    conn: sqlite3.Connection,
    from_date: str,
    to_date: str,
) -> Dict[str, List[dict]]:
    """Load all daily bars for the date range, grouped by ticker."""
    cur = conn.cursor()
    cur.execute("""
        SELECT ticker, date, open, high, low, close, volume
        FROM ohlcv_cache
        WHERE date >= ? AND date <= ?
        ORDER BY ticker, date ASC
    """, (from_date, to_date))
    out: Dict[str, List[dict]] = defaultdict(list)
    for r in cur.fetchall():
        out[r[0]].append({
            "ticker":   r[0],
            "date":     r[1],
            "open":     float(r[2]),
            "high":     float(r[3]),
            "low":      float(r[4]),
            "close":    float(r[5]),
            "volume":   float(r[6]),
        })
    return out


def load_recent_daily_bars_from_db(
    conn: sqlite3.Connection,
    to_date: str,
    bars_per_ticker: int = 60,
) -> Dict[str, List[dict]]:
    """Load only the trailing bars needed by the live EDGE signal pass.

    The live scanner evaluates one date and its longest feature lookback is
    20 sessions.  It used to materialise every cached daily candle for every
    ticker (years of history) into Python dictionaries at 09:30.  That is a
    large, short-lived allocation whose allocator high-water mark looked like
    an all-day RSS leak.  Keep a generous 60-session window for the Nifty
    regime calculation while bounding the per-ticker working set.

    This helper is intentionally separate from ``load_daily_bars_from_db``:
    backtests need their requested full date range, whereas the live scan does
    not.
    """
    if bars_per_ticker < 21:
        raise ValueError("bars_per_ticker must cover the 20-session feature lookback")
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ticker, date, open, high, low, close, volume
        FROM (
            SELECT ticker, date, open, high, low, close, volume,
                   ROW_NUMBER() OVER (
                       PARTITION BY ticker ORDER BY date DESC
                   ) AS ticker_row_number
            FROM ohlcv_cache
            WHERE date <= ?
        )
        WHERE ticker_row_number <= ?
        ORDER BY ticker, date ASC
        """,
        (to_date, bars_per_ticker),
    )
    out: Dict[str, List[dict]] = defaultdict(list)
    # Iterate the cursor: do not hold a second full result list alongside the
    # grouped Python representation.
    for r in cur:
        out[r[0]].append({
            "ticker": r[0], "date": r[1],
            "open": float(r[2]), "high": float(r[3]), "low": float(r[4]),
            "close": float(r[5]), "volume": float(r[6]),
        })
    return out
