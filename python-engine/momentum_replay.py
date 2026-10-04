"""Decision-grade, broker-free replay of the production 15-minute Momentum evaluator.

The module is intentionally library-only: it has no API, scheduler, broker, order,
or persistence side effects. Cache access is SQLite read-only and fails closed on
ambiguous intraday provenance.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
import math
import sqlite3
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from config import settings
from engine import evaluate_momentum_signal
from models import Regime
from momentum_shadow import momentum_shadow_execution_config


class ReplayDataError(ValueError):
    """Raised when cache evidence cannot support an honest replay."""


@dataclass(frozen=True)
class ReplayVariant:
    name: str
    crossover_lookback: int
    max_vwap_distance_atr: float | None


VARIANTS: Mapping[str, ReplayVariant] = {
    "MOM_BASE": ReplayVariant("MOM_BASE", 3, None),
    "MOM_RECENCY_5": ReplayVariant("MOM_RECENCY_5", 5, 0.50),
}


EXIT_MODELS = ("TARGET_1_PROXY", "LIVE_EXIT_LIFECYCLE", "THESIS_EXIT")
ENTRY_CLOCKS = ("ACCEPTED_CLOSE", "NEXT_BAR_OPEN")
# MOM_THESIS_EXIT (declared before scoring): half at T1 when two or more shares
# remain, breakeven after a +1R close, trail one R under the highest close once
# the run reaches +1.5R, exit when momentum fails (two closes under the entry
# VWAP) or stalls (no +0.5R excursion after four bars while under entry).
THESIS_BREAKEVEN_R = 1.0
THESIS_TRAIL_START_R = 1.5
THESIS_TRAIL_R = 1.0
THESIS_VWAP_FAIL_CLOSES = 2
THESIS_STALL_BARS = 4
THESIS_STALL_MFE_R = 0.5


@dataclass(frozen=True)
class MomentumReplayConfig:
    bankroll: float = 4500.0
    momentum_pool: float = 2500.0
    min_candles: int = 4
    daily_lookback_rows: int = 30
    market_regime: str = "BULL"
    regime: str = "REGIME_1_NORMAL"
    normal_volume_threshold: float = 1.5
    lunchtime_volume_threshold: float = 1.75
    lunchtime_start: str = "11:30"
    lunchtime_end: str = "13:15"
    # MOM_RECENCY_5 is a declared research comparison, not the runtime
    # evaluator's default. It remains available only when a run names it.
    variants: tuple[str, ...] = ("MOM_BASE",)
    # TARGET_1_PROXY is retained for reproducibility of archived research.
    # LIVE_EXIT_LIFECYCLE is a separate research model that uses the shipped
    # Momentum exit evaluator and never silently substitutes the proxy.
    exit_model: str = "TARGET_1_PROXY"
    # ACCEPTED_CLOSE reproduces archived receipts: it fills at the accepted
    # bar's close, a price only known when that bar ends. NEXT_BAR_OPEN is the
    # executable clock (R3): the next positive-volume bar's open, re-sized to
    # the decision's rupee risk.
    entry_clock: str = "ACCEPTED_CLOSE"
    oos_folds: int = 3

    def __post_init__(self):
        if self.bankroll <= 0 or self.momentum_pool <= 0:
            raise ValueError("bankroll and momentum_pool must be positive")
        if self.min_candles < 2:
            raise ValueError("min_candles must be at least 2")
        if self.daily_lookback_rows < 14:
            raise ValueError("daily_lookback_rows must be at least 14")
        if self.oos_folds < 3:
            raise ValueError("at least three OOS folds are required")
        if not self.variants or any(name not in VARIANTS for name in self.variants):
            raise ValueError("replay variants must be registered and non-empty")
        if self.exit_model not in EXIT_MODELS:
            raise ValueError(f"exit_model must be one of {EXIT_MODELS}")
        if self.entry_clock not in ENTRY_CLOCKS:
            raise ValueError(f"entry_clock must be one of {ENTRY_CLOCKS}")
        Regime[self.regime]


def _settings_snapshot() -> dict:
    names = (
        "MOMENTUM_USE_TIME_GATE", "MOMENTUM_ENTRY_START_MIN", "MOMENTUM_ENTRY_END_MIN",
        "MOMENTUM_USE_RVOL", "MOMENTUM_RVOL_LOOKBACK", "MOMENTUM_RVOL_MIN_RATIO",
        "MOMENTUM_MORPHOLOGY_MIN_SCORE", "MOMENTUM_MIN_STOP_PCT",
        "MOMENTUM_MIN_STOP_ATR_MULT", "MOMENTUM_ATR_FUEL_BUFFER",
        "MOMENTUM_R_TARGET", "MOMENTUM_R_TARGET_BEAR", "MOMENTUM_R_TARGET_R1",
        "MOMENTUM_R_TARGET_R2", "MOMENTUM_RISK_PCT", "MOMENTUM_RISK_PCT_R1",
        "MOMENTUM_RISK_PCT_R2", "MOMENTUM_RISK_PCT_R3",
        "MOMENTUM_BLOCK_R3_ENTRIES", "MOMENTUM_MAX_COST_RATIO",
        "MOMENTUM_MAX_COST_PER_R",
        "ZERODHA_BROKERAGE_PCT", "ZERODHA_BROKERAGE_MAX", "ZERODHA_STT_MIS",
        "ZERODHA_EXCHANGE_PCT", "ZERODHA_STAMP_DUTY_PCT", "ZERODHA_SEBI_PCT",
        "ZERODHA_IPFT_PCT", "ZERODHA_GST_PCT",
    )
    return {name: getattr(settings, name) for name in names}


def _read_cache(
    db_path: str, tickers: Sequence[str] | None, start: str | None, end: str | None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    uri = f"file:{db_path}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise ReplayDataError(f"cache is not readable: {exc}") from exc
    try:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if not {"intraday_cache", "ohlcv_cache"}.issubset(tables):
            raise ReplayDataError("intraday_cache and ohlcv_cache are required")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(intraday_cache)")}
        if "interval" not in columns:
            raise ReplayDataError("intraday_cache lacks interval provenance")

        where, params = [], []
        if tickers:
            clean = tuple(sorted({str(item).strip().upper() for item in tickers if str(item).strip()}))
            if not clean:
                raise ReplayDataError("ticker filter is empty")
            where.append(f"ticker IN ({','.join('?' for _ in clean)})")
            params.extend(clean)
        if start:
            date.fromisoformat(start)
            where.append("substr(datetime,1,10)>=?")
            params.append(start)
        if end:
            date.fromisoformat(end)
            where.append("substr(datetime,1,10)<=?")
            params.append(end)
        scope = f" WHERE {' AND '.join(where)}" if where else ""
        provenance = connection.execute(
            f"SELECT interval,COUNT(*) FROM intraday_cache{scope} GROUP BY interval", params,
        ).fetchall()
        provenance_map = {str(interval or ""): int(count) for interval, count in provenance}
        if not provenance_map:
            raise ReplayDataError("no intraday rows in requested scope")
        if "" in provenance_map or "legacy_unknown" in provenance_map:
            raise ReplayDataError("missing or legacy_unknown interval provenance in requested scope")
        if "15minute" not in provenance_map:
            raise ReplayDataError("requested scope has no interval='15minute' evidence")

        intra_where = list(where) + ["interval='15minute'"]
        intra = pd.read_sql_query(
            f"SELECT ticker,interval,datetime,open,high,low,close,volume,fetched_at "
            f"FROM intraday_cache WHERE {' AND '.join(intra_where)} ORDER BY ticker,datetime",
            connection, params=params,
        )
        daily_where, daily_params = [], []
        if tickers:
            daily_where.append(f"ticker IN ({','.join('?' for _ in clean)})")
            daily_params.extend(clean)
        daily = pd.read_sql_query(
            "SELECT ticker,date,open,high,low,close,volume,fetched_at FROM ohlcv_cache"
            + (f" WHERE {' AND '.join(daily_where)}" if daily_where else "")
            + " ORDER BY ticker,date",
            connection, params=daily_params,
        )
    finally:
        connection.close()
    if intra.empty:
        raise ReplayDataError("no 15-minute rows in requested scope")
    if daily.empty:
        raise ReplayDataError("strictly prior daily OHLC history is missing")
    return intra, daily, {"interval_counts": provenance_map, "selected_interval": "15minute"}


def _validate_frame(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["datetime"] = pd.to_datetime(frame["datetime"], errors="coerce")
    if frame["datetime"].isna().any():
        raise ReplayDataError("intraday cache contains malformed timestamps")
    if frame.duplicated(["ticker", "datetime"]).any():
        raise ReplayDataError("mixed/duplicate 15-minute identities detected")
    if any((stamp.minute % 15) != 0 for stamp in frame["datetime"]):
        raise ReplayDataError("15minute provenance contains non-quarter-hour bars")
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    prices = frame[["open", "high", "low", "close"]]
    if prices.isna().any().any() or (prices <= 0).any().any():
        raise ReplayDataError("intraday OHLC values must be finite and positive")
    if frame["volume"].isna().any() or (frame["volume"] < 0).any():
        raise ReplayDataError("intraday volume must be finite and non-negative")
    if ((frame["high"] < frame[["open", "close", "low"]].max(axis=1)) |
            (frame["low"] > frame[["open", "close", "high"]].min(axis=1))).any():
        raise ReplayDataError("intraday OHLC geometry is invalid")
    frame["trading_date"] = frame["datetime"].dt.date.astype(str)
    return frame


def _daily_frame(daily: pd.DataFrame, ticker: str, before: str, lookback_rows: int) -> pd.DataFrame:
    selected = daily[(daily["ticker"] == ticker) & (daily["date"].astype(str) < before)].copy()
    if selected.empty:
        return selected
    selected.index = pd.to_datetime(selected.pop("date"))
    return selected[["open", "high", "low", "close", "volume"]].sort_index().tail(lookback_rows)


def _volume_threshold(stamp: pd.Timestamp, config: MomentumReplayConfig) -> float:
    current = stamp.strftime("%H:%M")
    return (config.lunchtime_volume_threshold
            if config.lunchtime_start <= current <= config.lunchtime_end
            else config.normal_volume_threshold)


def _exit(trade: dict, bar: pd.Series, stamp: pd.Timestamp, execution: dict) -> tuple[str, float] | None:
    slip = execution["exit_slippage_bps"] / 10000.0
    opening = float(bar["open"])
    if stamp.date().isoformat() > trade["trading_date"]:
        return "overnight_gap_exit", opening * (1 - slip)
    if (stamp.hour, stamp.minute) >= (execution["time_exit_hour"], execution["time_exit_minute"]):
        return "time_exit", opening * (1 - slip)
    if opening <= trade["stop_price"]:
        return "stop_gap", opening * (1 - slip)
    if opening >= trade["target_price"]:
        return "target_gap_conservative", trade["target_price"] * (1 - slip)
    if float(bar["low"]) <= trade["stop_price"]:
        return "stop_before_target_same_bar" if float(bar["high"]) >= trade["target_price"] else "stop", trade["stop_price"] * (1 - slip)
    if float(bar["high"]) >= trade["target_price"]:
        return "target", trade["target_price"] * (1 - slip)
    return None


def _costs(entry: float, exit_price: float, quantity: int, execution: dict) -> float:
    buy, sell = entry * quantity, exit_price * quantity
    brokerage = min(buy * execution["brokerage_pct"], execution["brokerage_max_per_order"])
    brokerage += min(sell * execution["brokerage_pct"], execution["brokerage_max_per_order"])
    exchange = (buy + sell) * execution["exchange_pct"]
    return round(
        brokerage + sell * execution["stt_sell_pct"] + exchange
        + buy * execution["stamp_duty_buy_pct"] + (buy + sell) * execution["sebi_pct"]
        + (brokerage + exchange) * execution["gst_pct"], 4,
    )


def _simulate(candidate: dict, future: pd.DataFrame, execution: dict) -> dict:
    decision = candidate["decision"]
    raw_entry = float(decision["entry_price"])
    entry = raw_entry * (1 + execution["entry_slippage_bps"] / 10000.0)
    trade = {
        "variant": candidate["variant"], "ticker": candidate["ticker"],
        "trading_date": candidate["trading_date"], "entry_bar_ts": candidate["bar_ts"],
        "raw_entry": raw_entry, "entry_fill": round(entry, 6),
        "stop_price": float(decision["stop_loss"]),
        "target_price": float(decision["target_1"]), "quantity": int(decision["shares"]),
        "dataset_fingerprint": candidate["dataset_fingerprint"], "status": "OPEN",
    }
    initial_risk = (entry - trade["stop_price"]) * trade["quantity"]
    trade["initial_risk"] = round(initial_risk, 6)
    for stamp, bar in future.iterrows():
        result = _exit(trade, bar, pd.Timestamp(stamp), execution)
        if result is None:
            continue
        reason, exit_fill = result
        gross = (exit_fill - entry) * trade["quantity"]
        costs = _costs(entry, exit_fill, trade["quantity"], execution)
        net = gross - costs
        trade.update({
            "status": "CLOSED", "exit_bar_ts": pd.Timestamp(stamp).isoformat(),
            "exit_reason": reason, "exit_fill": round(exit_fill, 6),
            "gross_pnl": round(gross, 6), "costs": round(costs, 6),
            "net_pnl": round(net, 6), "r_multiple": round(net / initial_risk, 8),
        })
        break
    return trade


def _multi_order_costs(entry: float, exits: list[tuple[float, int]], execution: dict) -> float:
    """Cost one buy order and every actual sell order in a runner lifecycle.

    Calling the round-trip helper once per partial sale would charge the buy
    brokerage repeatedly.  This mirrors the shipped cash-equity schedule while
    retaining the important per-executed-order brokerage cap.
    """
    quantity = sum(int(qty) for _, qty in exits)
    if quantity <= 0 or entry <= 0 or any(price <= 0 or qty <= 0 for price, qty in exits):
        raise ReplayDataError("lifecycle cost inputs are invalid")
    buy = entry * quantity
    sells = [price * qty for price, qty in exits]
    sell = sum(sells)
    brokerage = min(buy * execution["brokerage_pct"], execution["brokerage_max_per_order"])
    brokerage += sum(min(value * execution["brokerage_pct"], execution["brokerage_max_per_order"])
                     for value in sells)
    exchange = (buy + sell) * execution["exchange_pct"]
    sebi = (buy + sell) * execution["sebi_pct"]
    ipft = (buy + sell) * execution["ipft_pct"]
    gst = (brokerage + exchange + sebi + ipft) * execution["gst_pct"]
    return round(brokerage + sell * execution["stt_sell_pct"] + exchange
                 + buy * execution["stamp_duty_buy_pct"] + sebi + ipft + gst, 4)


def _simulate_live_exit_lifecycle(candidate: dict, future: pd.DataFrame, execution: dict) -> dict:
    """Diagnostic replay of the shipped partial/runner decision using OHLC.

    The entry model deliberately remains the frozen Momentum research entry
    model. A bar's protective stop is checked
    before any favourable high; a target/scale limit needs the high to reach the
    known level; a ratchet only affects later bars; and the 15:15 square-off
    uses that bar's open. A missing final fill stays unresolved. High/partial/
    ratchet ordering and completed-bar clocks still require path evidence;
    this helper is not an exact or uniformly conservative lifecycle.
    """
    from momentum_exits import ACTION_EXIT, ACTION_SCALE_OUT, ACTION_TRAIL, evaluate_momentum_exit

    decision = candidate["decision"]
    raw_entry = float(decision["entry_price"])
    entry = raw_entry * (1 + execution["entry_slippage_bps"] / 10000.0)
    initial_stop = float(decision["stop_loss"])
    target = float(decision["target_1"])
    original_quantity = int(decision["shares"])
    if original_quantity < 1 or not (initial_stop > 0 and entry > initial_stop and target > entry):
        raise ReplayDataError("accepted Momentum decision has invalid lifecycle geometry")
    initial_risk = (entry - initial_stop) * original_quantity
    trade = {
        "variant": candidate["variant"], "ticker": candidate["ticker"],
        "trading_date": candidate["trading_date"], "entry_bar_ts": candidate["bar_ts"],
        "raw_entry": raw_entry, "entry_fill": round(entry, 6), "stop_price": initial_stop,
        "target_price": target, "quantity": original_quantity, "dataset_fingerprint": candidate["dataset_fingerprint"],
        "status": "OPEN", "exit_model": "LIVE_EXIT_LIFECYCLE", "initial_risk": round(initial_risk, 6),
        "fills": [],
    }
    position = {
        "ticker": candidate["ticker"], "entry_price": entry, "stop_loss_initial": initial_stop,
        "trailing_stop_current": initial_stop, "target_1": target, "shares": original_quantity,
        "t1_fired": False, "atr_14_at_entry": decision.get("atr_at_entry"),
        "vwap_at_entry": decision.get("vwap"), "regime_at_entry": candidate.get("regime_at_entry"),
        "entry_date": candidate["bar_ts"],
    }
    remaining = original_quantity
    exit_slip = execution["exit_slippage_bps"] / 10000.0

    def close_all(price: float, reason: str, stamp: pd.Timestamp) -> None:
        nonlocal remaining
        if remaining:
            trade["fills"].append({"quantity": remaining, "price": round(price, 6), "reason": reason,
                                   "bar_ts": stamp.isoformat()})
            remaining = 0

    unresolved_reason = "no_executable_exit_or_square_off_evidence"
    for stamp, bar in future.iterrows():
        stamp = pd.Timestamp(stamp)
        if stamp.date().isoformat() != candidate["trading_date"]:
            unresolved_reason = "missing_intraday_exit_evidence_before_next_session"
            break
        if not math.isfinite(float(bar["volume"])) or float(bar["volume"]) <= 0:
            continue  # A zero-volume mark cannot establish an executable fill.
        open_, high, low, close = (float(bar[name]) for name in ("open", "high", "low", "close"))
        # The runtime square-off is an order at the deadline; do not inspect a
        # later intrabar low/high and pretend a different ordering was known.
        if (stamp.hour, stamp.minute) >= (execution["time_exit_hour"], execution["time_exit_minute"]):
            if (stamp.hour, stamp.minute) != (execution["time_exit_hour"], execution["time_exit_minute"]):
                unresolved_reason = "missing_exact_square_off_bar"
                break
            close_all(open_ * (1 - exit_slip), "hard_square_off", stamp)
            break
        current_stop = float(position["trailing_stop_current"] or initial_stop)
        # A real resting stop has priority over discretionary runner logic.
        if open_ <= current_stop:
            close_all(open_ * (1 - exit_slip), "broker_stop_gap", stamp)
            break
        if low <= current_stop:
            close_all(current_stop * (1 - exit_slip), "broker_stop", stamp)
            break

        # High can establish a known target/partial fill.  Any ratchet set
        # here is intentionally not applied to this same OHLC bar.
        high_action = evaluate_momentum_exit(position, high, stamp.to_pydatetime())
        if high_action["action"] == ACTION_EXIT:
            price = target * (1 - exit_slip) if high >= target else close * (1 - exit_slip)
            close_all(price, high_action["reason"], stamp)
            break
        if high_action["action"] == ACTION_SCALE_OUT:
            quantity = min(int(high_action.get("scale_shares") or 0), remaining)
            if quantity > 0:
                trigger = entry + (entry - initial_stop) * float(settings.MOMENTUM_SCALE_OUT_R)
                trade["fills"].append({"quantity": quantity, "price": round(trigger * (1 - exit_slip), 6),
                                       "reason": high_action["reason"], "bar_ts": stamp.isoformat()})
                remaining -= quantity
                position["shares"] = remaining
                position["t1_fired"] = True
            position["trailing_stop_current"] = max(current_stop, float(high_action["new_stop"]))
        elif high_action["action"] == ACTION_TRAIL:
            position["trailing_stop_current"] = max(current_stop, float(high_action["new_stop"]))

        # Time-stop/close decisions are evaluated on the completed bar close.
        if remaining:
            close_action = evaluate_momentum_exit(position, close, stamp.to_pydatetime())
            if close_action["action"] == ACTION_EXIT:
                close_all(close * (1 - exit_slip), close_action["reason"], stamp)
                break
            if close_action["action"] == ACTION_TRAIL:
                position["trailing_stop_current"] = max(
                    float(position["trailing_stop_current"]), float(close_action["new_stop"])
                )

    return _finish_lifecycle(trade, entry, original_quantity, initial_risk, remaining,
                             float(position["trailing_stop_current"]), unresolved_reason, execution)


def _finish_lifecycle(trade: dict, entry: float, original_quantity: int, initial_risk: float, remaining: int,
                      stop: float, unresolved_reason: str, execution: dict) -> dict:
    """Close the books on a multi-fill lifecycle; a remainder stays UNRESOLVED."""
    if remaining:
        trade.update({"status": "UNRESOLVED", "remaining_quantity": remaining,
                      "trailing_stop": round(stop, 6), "unresolved_reason": unresolved_reason})
        return trade
    exits = [(float(row["price"]), int(row["quantity"])) for row in trade["fills"]]
    gross = sum((price - entry) * quantity for price, quantity in exits)
    costs = _multi_order_costs(entry, exits, execution)
    final = trade["fills"][-1]
    trade.update({
        "status": "CLOSED", "exit_bar_ts": final["bar_ts"], "exit_reason": final["reason"],
        "exit_fill": round(sum(price * quantity for price, quantity in exits) / original_quantity, 6),
        "gross_pnl": round(gross, 6), "costs": costs, "net_pnl": round(gross - costs, 6),
        "r_multiple": round((gross - costs) / initial_risk, 8), "remaining_quantity": 0,
    })
    return trade


def _simulate_thesis_exit(candidate: dict, future: pd.DataFrame, execution: dict) -> dict:
    """MOM_THESIS_EXIT on completed 15-minute bars (research candidate).

    Same clock discipline as the live diagnostic: the resting stop is checked
    first (gap fills at the open), a resting T1 half fills when the high
    reaches it, close-based decisions use that bar's close, and any raised stop
    applies from the next bar. The 15:15 square-off is the exact deadline bar.
    """
    decision = candidate["decision"]
    raw_entry = float(decision["entry_price"])
    entry = raw_entry * (1 + execution["entry_slippage_bps"] / 10000.0)
    stop = float(decision["stop_loss"])
    target = float(decision["target_1"])
    vwap = float(decision.get("vwap") or 0.0)
    original_quantity = int(decision["shares"])
    if original_quantity < 1 or not (stop > 0 and entry > stop and target > entry):
        raise ReplayDataError("accepted Momentum decision has invalid lifecycle geometry")
    risk = entry - stop
    initial_risk = risk * original_quantity
    trade = {
        "variant": candidate["variant"], "ticker": candidate["ticker"],
        "trading_date": candidate["trading_date"], "entry_bar_ts": candidate["bar_ts"],
        "raw_entry": raw_entry, "entry_fill": round(entry, 6), "stop_price": stop,
        "target_price": target, "quantity": original_quantity, "dataset_fingerprint": candidate["dataset_fingerprint"],
        "status": "OPEN", "exit_model": "THESIS_EXIT", "initial_risk": round(initial_risk, 6), "fills": [],
    }
    exit_slip = execution["exit_slippage_bps"] / 10000.0
    remaining, partial_done, bars_held = original_quantity, False, 0
    highest_high, highest_close, below_vwap = entry, entry, 0

    def sell(quantity: int, price: float, reason: str, stamp: pd.Timestamp) -> None:
        nonlocal remaining
        trade["fills"].append({"quantity": quantity, "price": round(price * (1 - exit_slip), 6),
                               "reason": reason, "bar_ts": stamp.isoformat()})
        remaining -= quantity

    unresolved_reason = "no_executable_exit_or_square_off_evidence"
    for stamp, bar in future.iterrows():
        stamp = pd.Timestamp(stamp)
        if stamp.date().isoformat() != candidate["trading_date"]:
            unresolved_reason = "missing_intraday_exit_evidence_before_next_session"
            break
        if not math.isfinite(float(bar["volume"])) or float(bar["volume"]) <= 0:
            continue
        open_, high, low, close = (float(bar[name]) for name in ("open", "high", "low", "close"))
        if (stamp.hour, stamp.minute) >= (execution["time_exit_hour"], execution["time_exit_minute"]):
            if (stamp.hour, stamp.minute) != (execution["time_exit_hour"], execution["time_exit_minute"]):
                unresolved_reason = "missing_exact_square_off_bar"
                break
            sell(remaining, open_, "hard_square_off", stamp)
            break
        if open_ <= stop:
            sell(remaining, open_, "stop_gap", stamp)
            break
        if low <= stop:
            sell(remaining, stop, "stop", stamp)
            break
        bars_held += 1
        next_stop = stop
        if not partial_done and remaining >= 2 and high >= target:
            sell(remaining // 2, target, "thesis_t1_half", stamp)
            partial_done = True
            next_stop = max(next_stop, entry)
        highest_high, highest_close = max(highest_high, high), max(highest_close, close)
        below_vwap = below_vwap + 1 if vwap and close < vwap else 0
        if below_vwap >= THESIS_VWAP_FAIL_CLOSES:
            sell(remaining, close, "thesis_momentum_failed_vwap", stamp)
            break
        if (bars_held >= THESIS_STALL_BARS and highest_high < entry + THESIS_STALL_MFE_R * risk
                and close < entry):
            sell(remaining, close, "thesis_stalled", stamp)
            break
        if close >= entry + THESIS_BREAKEVEN_R * risk:
            next_stop = max(next_stop, entry)
        if highest_high >= entry + THESIS_TRAIL_START_R * risk:
            next_stop = max(next_stop, highest_close - THESIS_TRAIL_R * risk)
        stop = next_stop
    return _finish_lifecycle(trade, entry, original_quantity, initial_risk, remaining, stop,
                             unresolved_reason, execution)


def _next_bar_entry(candidate: dict, future: pd.DataFrame) -> tuple[dict, pd.DataFrame, str | None]:
    """Move entry to the next same-session positive-volume bar's open (R3).

    The accepted bar's close is only known when that bar ends; the first price
    an order can get is the following bar's open. Quantity keeps the decision's
    rupee risk at the new price; an open at or below the stop is a no-fill.
    """
    decision = candidate["decision"]
    same_day = future[(future.index.strftime("%Y-%m-%d") == candidate["trading_date"]) & (future["volume"] > 0)]
    if same_day.empty:
        return candidate, future, "no_same_session_bar_after_acceptance"
    fill_stamp = same_day.index[0]
    fill = float(same_day.iloc[0]["open"])
    stop, raw = float(decision["stop_loss"]), float(decision["entry_price"])
    if fill <= stop:
        return candidate, future, "next_open_at_or_below_stop"
    if fill >= float(decision["target_1"]):
        return candidate, future, "next_open_at_or_above_target"
    shares = int(int(decision["shares"]) * (raw - stop) // (fill - stop))
    if shares < 1:
        return candidate, future, "resized_quantity_zero"
    moved = {**candidate, "decision": {**decision, "entry_price": fill, "shares": shares},
             "bar_ts": fill_stamp.isoformat(), "accepted_bar_ts": candidate["bar_ts"]}
    return moved, future[future.index >= fill_stamp], None


def _summary(trades: list[dict]) -> tuple[dict, list[dict]]:
    closed = sorted((t for t in trades if t["status"] == "CLOSED"), key=lambda t: (t["exit_bar_ts"], t["ticker"], t["variant"]))
    no_fill = sum(t["status"] == "NO_FILL" for t in trades)
    equity, running, peak, drawdown = [], 0.0, 0.0, 0.0
    for trade in closed:
        running += trade["net_pnl"]
        peak = max(peak, running)
        drawdown = max(drawdown, peak - running)
        equity.append({"timestamp": trade["exit_bar_ts"], "equity": round(running, 6)})
    wins = sum(t["net_pnl"] for t in closed if t["net_pnl"] > 0)
    losses = -sum(t["net_pnl"] for t in closed if t["net_pnl"] < 0)
    return ({
        "entries": len(trades) - no_fill, "no_fill": no_fill, "open_trades": len(trades) - no_fill - len(closed),
        "closed_trades": len(closed),
        "net_pnl": round(running, 6) if closed else None,
        "expectancy": round(running / len(closed), 6) if closed else None,
        "profit_factor": round(wins / losses, 6) if losses > 0 else None,
        "avg_r": round(sum(t["r_multiple"] for t in closed) / len(closed), 8) if closed else None,
        "max_drawdown": round(drawdown, 6) if closed else None,
    }, equity)


def chronological_oos(trades: Sequence[dict], variants: Sequence[str], folds: int = 3) -> dict:
    if folds < 3:
        raise ValueError("at least three scored OOS folds are required")
    closed = [trade for trade in trades if trade.get("status") == "CLOSED"]
    dates = sorted({trade["trading_date"] for trade in closed})
    if len(dates) < folds + 1:
        return {"status": "insufficient_data", "required_folds": folds, "scored_folds": 0, "folds": []}
    test_dates = dates[1:]
    chunks = [list(chunk) for chunk in np.array_split(test_dates, folds) if len(chunk)]
    results = []
    scored_folds = 0
    for index, chunk in enumerate(chunks, 1):
        train_dates = [day for day in dates if day < chunk[0]]
        scores = {}
        for variant in variants:
            sample = [t["net_pnl"] for t in closed if t["variant"] == variant and t["trading_date"] in train_dates]
            scores[variant] = (sum(sample) / len(sample), len(sample)) if sample else (float("-inf"), 0)
        eligible = [name for name in variants if scores[name][1] > 0]
        fold_base = {
            "fold": index, "train_start": train_dates[0], "train_end": train_dates[-1],
            "test_start": chunk[0], "test_end": chunk[-1],
            "train_scores": {name: {"expectancy": None if score[0] == float("-inf") else round(score[0], 6), "trades": score[1]} for name, score in scores.items()},
        }
        if not eligible:
            results.append({**fold_base, "scored": False, "reason": "no_train_sample", "selected_variant": None, "oos_trades": 0, "oos_net_pnl": None, "oos_expectancy": None})
            continue
        selected = sorted(eligible, key=lambda name: (-scores[name][0], name))[0]
        oos = [t for t in closed if t["variant"] == selected and t["trading_date"] in chunk]
        if not oos:
            results.append({**fold_base, "scored": False, "reason": "selected_variant_has_no_oos_close", "selected_variant": selected, "oos_trades": 0, "oos_net_pnl": None, "oos_expectancy": None})
            continue
        scored_folds += 1
        results.append({
            **fold_base, "scored": True, "reason": None, "selected_variant": selected,
            "oos_trades": len(oos), "oos_net_pnl": round(sum(t["net_pnl"] for t in oos), 6) if oos else None,
            "oos_expectancy": round(sum(t["net_pnl"] for t in oos) / len(oos), 6) if oos else None,
        })
    return {
        "status": "scored" if scored_folds >= 3 else "insufficient_data",
        "required_folds": folds, "scored_folds": scored_folds, "folds": results,
    }


def run_momentum_replay(
    db_path: str, config: MomentumReplayConfig | None = None, *,
    tickers: Sequence[str] | None = None, start: str | None = None, end: str | None = None,
) -> dict:
    config = config or MomentumReplayConfig(
        bankroll=float(settings.INITIAL_BANKROLL),
        momentum_pool=float(settings.INITIAL_BANKROLL * settings.MOMENTUM_POOL_PCT),
        min_candles=int(settings.MOMENTUM_MIN_CANDLES),
        normal_volume_threshold=float(settings.MOMENTUM_VOL_SURGE_PCT),
        lunchtime_volume_threshold=float(settings.MOMENTUM_VOL_SURGE_LUNCHTIME),
    )
    intra_raw, daily, provenance = _read_cache(db_path, tickers, start, end)
    intra = _validate_frame(intra_raw)
    # Retain only daily rows that could be consumed by at least one replay day;
    # neither evaluator input nor the dataset fingerprint includes later history.
    last_replay_day = intra["trading_date"].max()
    daily = daily[daily["date"].astype(str) < last_replay_day].copy()
    if daily.empty:
        raise ReplayDataError("strictly prior daily OHLC history is missing")
    execution = momentum_shadow_execution_config()
    config_snapshot = {**asdict(config), "variants": list(config.variants), "evaluator_settings": _settings_snapshot()}
    if config.exit_model == "LIVE_EXIT_LIFECYCLE":
        exit_names = (
            "MOMENTUM_USE_SCALE_OUT", "MOMENTUM_SCALE_OUT_R", "MOMENTUM_SCALE_OUT_FRAC",
            "MOMENTUM_BREAKEVEN_R", "MOMENTUM_USE_TRAIL", "MOMENTUM_TRAIL_ATR_MULT",
            "MOMENTUM_TIME_STOP_FAST_MIN", "MOMENTUM_TIME_STOP_FAST_R", "MOMENTUM_FAST_STOP_USES_THESIS",
            "MOMENTUM_TIME_STOP_MIN", "MOMENTUM_TIME_STOP_MIN_R", "MOMENTUM_TIME_STOP_R1_MULT",
            "MOMENTUM_TIME_STOP_R2_MULT", "MOMENTUM_TIME_STOP_R3_MULT",
        )
        config_snapshot["exit_settings"] = {name: getattr(settings, name) for name in exit_names}
        execution["position_lifecycle"] = "shipped_partial_runner_OHLC_diagnostic_not_exact_quote_replay"
        execution["square_off_evidence"] = "positive_volume_exact_deadline_bar_same_session_only"
    if config.exit_model == "THESIS_EXIT":
        config_snapshot["thesis_exit"] = {
            "breakeven_r": THESIS_BREAKEVEN_R, "trail_start_r": THESIS_TRAIL_START_R, "trail_r": THESIS_TRAIL_R,
            "vwap_fail_closes": THESIS_VWAP_FAIL_CLOSES, "stall_bars": THESIS_STALL_BARS,
            "stall_mfe_r": THESIS_STALL_MFE_R}
        execution["position_lifecycle"] = "MOM_THESIS_EXIT_OHLC_research_candidate"
    digest = hashlib.sha256()
    digest.update(pd.util.hash_pandas_object(intra, index=True).values.tobytes())
    digest.update(pd.util.hash_pandas_object(daily, index=True).values.tobytes())
    digest.update(json.dumps(config_snapshot, sort_keys=True, separators=(",", ":")).encode())
    fingerprint = f"sha256:{digest.hexdigest()}"
    funnel = {name: {"evaluations": 0, "accepted_prefixes": 0, "distinct_candidates": 0, "rejects": {}} for name in config.variants}
    candidates, missing_daily = [], 0
    regime = Regime[config.regime]
    for (ticker, trading_date), group in intra.groupby(["ticker", "trading_date"], sort=True):
        group = group.sort_values("datetime").set_index("datetime")
        daily_prior = _daily_frame(daily, ticker, trading_date, config.daily_lookback_rows)
        if daily_prior.empty:
            missing_daily += 1
            continue
        prev_high = float(daily_prior["high"].iloc[-1])
        accepted_variants = set()
        for length in range(1, len(group) + 1):
            prefix = group.iloc[:length][["open", "high", "low", "close", "volume"]].copy()
            stamp = pd.Timestamp(prefix.index[-1])
            for name in config.variants:
                variant = VARIANTS[name]
                fired, decision = evaluate_momentum_signal(
                    ticker=ticker, df=prefix, prev_day_high=prev_high,
                    bankroll=config.bankroll, momentum_pool=config.momentum_pool,
                    min_candles=config.min_candles, df_daily=daily_prior,
                    vol_surge_threshold=_volume_threshold(stamp, config),
                    market_regime=config.market_regime, regime=regime,
                    crossover_lookback=variant.crossover_lookback,
                    max_vwap_distance_atr=variant.max_vwap_distance_atr,
                )
                funnel[name]["evaluations"] += 1
                if fired:
                    funnel[name]["accepted_prefixes"] += 1
                    if name not in accepted_variants:
                        accepted_variants.add(name)
                        funnel[name]["distinct_candidates"] += 1
                        candidates.append({
                            "ticker": ticker, "trading_date": trading_date,
                            "bar_ts": stamp.isoformat(), "variant": name,
                            "decision": decision, "dataset_fingerprint": fingerprint,
                            "prefix_bars": length,
                        })
                        candidates[-1]["regime_at_entry"] = config.regime
                else:
                    reason = str(decision.get("reject_reason", "unknown"))
                    funnel[name]["rejects"][reason] = funnel[name]["rejects"].get(reason, 0) + 1
    trades = []
    runner = {"TARGET_1_PROXY": _simulate, "LIVE_EXIT_LIFECYCLE": _simulate_live_exit_lifecycle,
              "THESIS_EXIT": _simulate_thesis_exit}[config.exit_model]
    for candidate in candidates:
        future = intra[(intra["ticker"] == candidate["ticker"]) &
                       (intra["datetime"] > pd.Timestamp(candidate["bar_ts"]))].sort_values("datetime")
        future = future.set_index("datetime")
        if config.entry_clock == "NEXT_BAR_OPEN":
            candidate, future, refusal = _next_bar_entry(candidate, future)
            if refusal:
                trades.append({"variant": candidate["variant"], "ticker": candidate["ticker"],
                               "trading_date": candidate["trading_date"], "entry_bar_ts": candidate["bar_ts"],
                               "status": "NO_FILL", "no_fill_reason": refusal})
                continue
        trades.append(runner(candidate, future, execution))
    summary, equity = _summary(trades)
    coverage = {
        "tickers": int(intra["ticker"].nunique()), "trading_days": int(intra["trading_date"].nunique()),
        "bars": len(intra), "daily_rows": len(daily), "ticker_days_missing_prior_daily": missing_daily,
        **provenance,
    }
    warnings = [
        "Research replay only; it never calls Kite, an executor, or an order path.",
        "15-minute OHLC cannot reveal intrabar path; simultaneous stop/target resolves stop first.",
        {"TARGET_1_PROXY": "Virtual lifecycle exits the full quantity at T1 and cannot model the production partial-T1 runner/trail.",
         "LIVE_EXIT_LIFECYCLE": "LIVE_EXIT_LIFECYCLE is a shipped-exit OHLC diagnostic, not exact path replay: partial/target order, high-driven ratchets and completed-bar execution clocks remain ambiguous; broker receipts are unavailable.",
         "THESIS_EXIT": "THESIS_EXIT is a research candidate on completed 15-minute bars: stop first, resting T1 half, close-based thesis decisions, raised stops from the next bar."}[config.exit_model],
        ("Entries fill at the next positive-volume bar's open, re-sized to the decision's rupee risk."
         if config.entry_clock == "NEXT_BAR_OPEN" else
         "Entries fill at the accepted bar's close (legacy clock retained for archived receipts; not executable before the bar ends)."),
        "Entry and exit fills use frozen Momentum shadow slippage and equity MIS cost assumptions.",
    ]
    if missing_daily:
        warnings.append("Some ticker-days were skipped because strictly prior daily history was unavailable.")
    return {
        "dataset_fingerprint": fingerprint, "config": config_snapshot,
        "assumptions": execution, "coverage": coverage, "funnel": funnel,
        "trades": trades, "equity": equity, "summary": summary,
        "oos": chronological_oos(trades, config.variants, config.oos_folds),
        "warnings": warnings,
    }
