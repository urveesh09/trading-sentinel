"""Decision-grade, broker-free replay of the production 15-minute Momentum evaluator.

The module is intentionally library-only: it has no API, scheduler, broker, order,
or persistence side effects. Cache access is SQLite read-only and fails closed on
ambiguous intraday provenance.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
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
    variants: tuple[str, ...] = ("MOM_BASE", "MOM_RECENCY_5")
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


def _summary(trades: list[dict]) -> tuple[dict, list[dict]]:
    closed = sorted((t for t in trades if t["status"] == "CLOSED"), key=lambda t: (t["exit_bar_ts"], t["ticker"], t["variant"]))
    equity, running, peak, drawdown = [], 0.0, 0.0, 0.0
    for trade in closed:
        running += trade["net_pnl"]
        peak = max(peak, running)
        drawdown = max(drawdown, peak - running)
        equity.append({"timestamp": trade["exit_bar_ts"], "equity": round(running, 6)})
    wins = sum(t["net_pnl"] for t in closed if t["net_pnl"] > 0)
    losses = -sum(t["net_pnl"] for t in closed if t["net_pnl"] < 0)
    return ({
        "entries": len(trades), "open_trades": len(trades) - len(closed),
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
                else:
                    reason = str(decision.get("reject_reason", "unknown"))
                    funnel[name]["rejects"][reason] = funnel[name]["rejects"].get(reason, 0) + 1
    trades = []
    for candidate in candidates:
        future = intra[(intra["ticker"] == candidate["ticker"]) &
                       (intra["datetime"] > pd.Timestamp(candidate["bar_ts"]))].sort_values("datetime")
        future = future.set_index("datetime")
        trades.append(_simulate(candidate, future, execution))
    summary, equity = _summary(trades)
    coverage = {
        "tickers": int(intra["ticker"].nunique()), "trading_days": int(intra["trading_date"].nunique()),
        "bars": len(intra), "daily_rows": len(daily), "ticker_days_missing_prior_daily": missing_daily,
        **provenance,
    }
    warnings = [
        "Research replay only; it never calls Kite, an executor, or an order path.",
        "15-minute OHLC cannot reveal intrabar path; simultaneous stop/target resolves stop first.",
        "Virtual lifecycle exits the full quantity at T1 and cannot model the production partial-T1 runner/trail.",
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
