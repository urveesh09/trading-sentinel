"""Decision-grade, broker-free replay of classic Penny one-minute evidence.

The loader is intentionally strict: only explicitly labelled ``minute`` cache
rows are admissible. A requested ticker/day with unknown or mixed interval
provenance invalidates the run instead of silently manufacturing confidence.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime
import hashlib
import json
import math
import sqlite3
from typing import Iterable, Sequence

import pandas as pd

from penny_engine_breakout import _rsi_14_wilder, evaluate_breakout_entry
from penny_shadow import (
    VARIANTS,
    VIRTUAL_QUANTITY,
    VIRTUAL_SIZING_BASIS,
    VIRTUAL_TIME_EXIT_MINUTE,
    _costs_from_snapshot,
    _execution_snapshot,
    _exit_for_bar,
)
from walk_forward import generate_folds, walk_forward


@dataclass(frozen=True)
class PennyReplayConfig:
    variants: tuple[str, ...] = ("PEN_BASE", "PEN_WINDOW", "PEN_VOLUME")
    minimum_daily_bars: int = 5
    quantity: int = VIRTUAL_QUANTITY
    sizing_basis: str = VIRTUAL_SIZING_BASIS

    def __post_init__(self):
        if not self.variants or len(set(self.variants)) != len(self.variants):
            raise ValueError("variants must be non-empty and unique")
        unknown = set(self.variants) - set(VARIANTS)
        if unknown:
            raise ValueError(f"unknown Penny replay variants: {sorted(unknown)}")
        if self.minimum_daily_bars < 5:
            raise ValueError("minimum_daily_bars must be at least 5")
        if self.quantity != 1 or self.sizing_basis != "ONE_SHARE_FIXED":
            raise ValueError("Penny replay sizing is frozen to one share")


class _OneShareRisk:
    def position_size(self, entry, stop, regime):
        return 1


def _iso_day(value) -> str:
    text = value.isoformat() if isinstance(value, date) else str(value)
    if date.fromisoformat(text).isoformat() != text:
        raise ValueError("dates must be ISO YYYY-MM-DD")
    return text


def _schema_columns(db, table: str) -> set[str]:
    return {row[1] for row in db.execute(f"PRAGMA table_info({table})")}


def _fingerprint(intraday: pd.DataFrame, daily: pd.DataFrame, config: dict) -> str:
    digest = hashlib.sha256(json.dumps(
        config, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode())
    digest.update(pd.util.hash_pandas_object(intraday, index=True).values.tobytes())
    digest.update(pd.util.hash_pandas_object(daily, index=True).values.tobytes())
    return f"sha256:{digest.hexdigest()}"


def load_penny_minute_snapshot(
    db_path: str,
    from_date: str,
    to_date: str,
    *,
    tickers: Sequence[str] | None = None,
    config: PennyReplayConfig | None = None,
) -> dict:
    """Read and validate a frozen local cache snapshot; never fetch data."""
    config = config or PennyReplayConfig()
    start, end = _iso_day(from_date), _iso_day(to_date)
    if end < start:
        raise ValueError("to_date must not precede from_date")
    requested = tuple(sorted({str(t).strip().upper() for t in (tickers or ()) if str(t).strip()}))
    diagnostics = {
        "status": "valid", "requested_from": start, "requested_to": end,
        "requested_tickers": list(requested), "minute_rows": 0,
        "ticker_days": 0, "daily_rows": 0, "invalid_provenance": [],
        "missing_daily_history": [], "coverage": [],
    }
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
        intraday_required = {
            "ticker", "interval", "datetime", "open", "high", "low", "close", "volume"
        }
        daily_required = {"ticker", "date", "open", "high", "low", "close", "volume"}
        if not intraday_required.issubset(_schema_columns(db, "intraday_cache")):
            diagnostics.update(status="invalid_data", warning="intraday_cache lacks interval provenance")
            return {"diagnostics": diagnostics, "intraday": pd.DataFrame(), "daily": pd.DataFrame(), "fingerprint": None}
        if not daily_required.issubset(_schema_columns(db, "ohlcv_cache")):
            diagnostics.update(status="invalid_data", warning="ohlcv_cache daily history is missing or incomplete")
            return {"diagnostics": diagnostics, "intraday": pd.DataFrame(), "daily": pd.DataFrame(), "fingerprint": None}
        ticker_clause = ""
        params: list = [start, end]
        if requested:
            ticker_clause = f" AND ticker IN ({','.join('?' for _ in requested)})"
            params.extend(requested)
        provenance = db.execute(
            "SELECT ticker,substr(datetime,1,10),GROUP_CONCAT(DISTINCT interval) "
            "FROM intraday_cache WHERE substr(datetime,1,10) BETWEEN ? AND ?"
            + ticker_clause + " GROUP BY ticker,substr(datetime,1,10)", params,
        ).fetchall()
        available_tickers = {row[0] for row in provenance}
        missing_requested = sorted(set(requested) - available_tickers)
        if missing_requested:
            diagnostics.update(
                status="invalid_data", missing_requested_tickers=missing_requested,
                warning="requested tickers lack interval-provenance rows",
            )
            return {"diagnostics": diagnostics, "intraday": pd.DataFrame(), "daily": pd.DataFrame(), "fingerprint": None}
        for ticker, day, raw_intervals in provenance:
            intervals = sorted(set((raw_intervals or "").split(",")))
            if intervals != ["minute"]:
                diagnostics["invalid_provenance"].append({
                    "ticker": ticker, "trading_date": day, "intervals": intervals,
                })
        if diagnostics["invalid_provenance"]:
            diagnostics.update(
                status="invalid_data",
                warning="legacy_unknown, mixed, or non-minute interval provenance present",
            )
            return {"diagnostics": diagnostics, "intraday": pd.DataFrame(), "daily": pd.DataFrame(), "fingerprint": None}
        rows = db.execute(
            "SELECT ticker,datetime,open,high,low,close,volume FROM intraday_cache "
            "WHERE interval='minute' AND substr(datetime,1,10) BETWEEN ? AND ?"
            + ticker_clause + " ORDER BY ticker,datetime", params,
        ).fetchall()
        if not rows:
            diagnostics.update(status="invalid_data", warning="no explicit minute rows in requested range")
            return {"diagnostics": diagnostics, "intraday": pd.DataFrame(), "daily": pd.DataFrame(), "fingerprint": None}
        symbols = sorted({row[0] for row in rows})
        # Load through the day before the requested end. Per-evaluation slicing
        # below remains strictly ``date < trading_day`` while allowing a later
        # replay day to use earlier days inside the requested range.
        daily_params = [end, *symbols]
        daily_rows = db.execute(
            f"SELECT ticker,date,open,high,low,close,volume FROM ohlcv_cache "
            f"WHERE date < ? AND ticker IN ({','.join('?' for _ in symbols)}) "
            "ORDER BY ticker,date", daily_params,
        ).fetchall()

    intraday = pd.DataFrame(rows, columns=("ticker", "datetime", "open", "high", "low", "close", "volume"))
    intraday["datetime"] = pd.to_datetime(intraday["datetime"], errors="coerce")
    numeric = ("open", "high", "low", "close", "volume")
    for column in numeric:
        intraday[column] = pd.to_numeric(intraday[column], errors="coerce")
    malformed = intraday["datetime"].isna() | intraday[list(numeric)].isna().any(axis=1)
    malformed |= (intraday[list(numeric)] <= 0).any(axis=1)
    if malformed.any():
        diagnostics.update(status="invalid_data", warning="minute rows contain malformed OHLCV evidence")
        return {"diagnostics": diagnostics, "intraday": pd.DataFrame(), "daily": pd.DataFrame(), "fingerprint": None}
    intraday["trading_date"] = intraday["datetime"].dt.date.astype(str)
    daily = pd.DataFrame(daily_rows, columns=("ticker", "date", "open", "high", "low", "close", "volume"))
    for column in numeric:
        daily[column] = pd.to_numeric(daily[column], errors="coerce")
    diagnostics["minute_rows"] = len(intraday)
    diagnostics["ticker_days"] = int(intraday[["ticker", "trading_date"]].drop_duplicates().shape[0])
    diagnostics["daily_rows"] = len(daily)
    for (ticker, day), group in intraday.groupby(["ticker", "trading_date"], sort=True):
        stamps = group.datetime.sort_values()
        deltas = stamps.diff().dropna().dt.total_seconds().div(60)
        diagnostics["coverage"].append({
            "ticker": ticker, "trading_date": day, "rows": len(group),
            "first_bar": stamps.iloc[0].isoformat(), "last_bar": stamps.iloc[-1].isoformat(),
            "duplicate_timestamps": int(stamps.duplicated().sum()),
            "missing_minutes_within_span": int(sum(max(int(delta) - 1, 0) for delta in deltas)),
            "has_time_exit_bar": bool(
                stamps.iloc[-1].hour * 60 + stamps.iloc[-1].minute >= VIRTUAL_TIME_EXIT_MINUTE
            ),
        })
    for ticker, day in intraday[["ticker", "trading_date"]].drop_duplicates().itertuples(index=False):
        count = len(daily[(daily.ticker == ticker) & (daily.date < day)])
        if count < config.minimum_daily_bars:
            diagnostics["missing_daily_history"].append({
                "ticker": ticker, "trading_date": day, "available": count,
                "required": config.minimum_daily_bars,
            })
    if diagnostics["missing_daily_history"]:
        diagnostics.update(status="invalid_data", warning="insufficient pre-day daily volume history")
        return {"diagnostics": diagnostics, "intraday": intraday, "daily": daily, "fingerprint": None}
    frozen_config = asdict(config)
    frozen_config["variants"] = list(config.variants)
    fingerprint = _fingerprint(intraday, daily, frozen_config)
    return {"diagnostics": diagnostics, "intraday": intraday, "daily": daily, "fingerprint": fingerprint}


def _variant_config(name: str) -> dict:
    from config import settings
    variant = VARIANTS[name]
    return {
        "name": name,
        "time_start_min": variant.time_start_min,
        "volume_multiplier": variant.volume_multiplier,
        "effective_time_start_min": settings.PENNY_BREAKOUT_TIME_START if variant.time_start_min is None else variant.time_start_min,
        "time_end_min": settings.PENNY_BREAKOUT_TIME_END,
        "effective_volume_multiplier": settings.PENNY_BREAKOUT_VOL_MULT if variant.volume_multiplier is None else variant.volume_multiplier,
        "rvol_time_adjusted": settings.PENNY_BREAKOUT_RVOL_TIME_ADJUSTED,
        "breakout_buffer_pct": settings.PENNY_BREAKOUT_BUFFER_PCT,
        "use_vwap": settings.PENNY_BREAKOUT_USE_VWAP,
        "adaptive_threshold": settings.PENNY_BREAKOUT_ADAPTIVE_THRESHOLD,
        "rsi_max": settings.PENNY_BREAKOUT_RSI_MAX,
        "target_r": settings.PENNY_BREAKOUT_TARGET_R,
    }


def _run_fingerprint(snapshot_fingerprint: str, config: PennyReplayConfig) -> str:
    declared = {
        "snapshot": snapshot_fingerprint,
        "variants": [_variant_config(name) for name in config.variants],
        "execution": _execution_snapshot("INTRADAY_REPLAY"),
        "replay_config": {**asdict(config), "variants": list(config.variants)},
    }
    return "sha256:" + hashlib.sha256(json.dumps(
        declared, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()


def _summarize(name: str, evaluations: int, rejects: Counter, trades: list[dict]) -> dict:
    closed = [trade for trade in trades if trade["status"] == "CLOSED"]
    net = [trade["net_pnl"] for trade in closed]
    positive, negative = sum(x for x in net if x > 0), abs(sum(x for x in net if x < 0))
    equity = []
    running = peak = max_dd = 0.0
    for trade in sorted(closed, key=lambda row: (row["exit_bar_ts"], row["ticker"])):
        running += trade["net_pnl"]
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)
        equity.append({"timestamp": trade["exit_bar_ts"], "equity": round(running, 4)})
    return {
        "variant": name, "config": _variant_config(name), "evaluations": evaluations,
        "distinct_candidates": len(trades), "top_rejects": [
            {"reason": reason, "count": count} for reason, count in rejects.most_common(10)
        ],
        "trades": trades, "paper_entries": len(trades),
        "open_trades": len(trades) - len(closed), "closed_trades": len(closed),
        "gross_pnl": round(sum(t["gross_pnl"] for t in closed), 4) if closed else None,
        "costs": round(sum(t["costs"] for t in closed), 4) if closed else None,
        "net_pnl": round(sum(net), 4) if closed else None,
        "profit_factor": round(positive / negative, 6) if closed and negative else None,
        "expectancy": round(sum(net) / len(net), 4) if closed else None,
        "avg_r": round(sum(t["r_multiple"] for t in closed) / len(closed), 6) if closed else None,
        "max_drawdown": round(max_dd, 4) if closed else None,
        "equity": equity,
    }


def _run_snapshot(snapshot: dict, config: PennyReplayConfig, from_date: str, to_date: str) -> dict:
    if snapshot["diagnostics"]["status"] != "valid":
        return {
            "status": "invalid_data", "dataset_fingerprint": None,
            "config": asdict(config), "assumptions": None, "funnel": {},
            "variants": [], "diagnostics": snapshot["diagnostics"],
            "warnings": [snapshot["diagnostics"].get("warning", "invalid data")],
        }
    intra = snapshot["intraday"]
    intra = intra[(intra.trading_date >= from_date) & (intra.trading_date <= to_date)]
    daily = snapshot["daily"]
    execution = _execution_snapshot("INTRADAY_REPLAY")
    outputs = []
    for variant_name in config.variants:
        variant = VARIANTS[variant_name]
        trades: list[dict] = []
        rejects: Counter = Counter()
        evaluations = 0
        for (ticker, trading_day), bars in intra.groupby(["ticker", "trading_date"], sort=True):
            bars = bars.sort_values("datetime").reset_index(drop=True)
            history_daily = daily[(daily.ticker == ticker) & (daily.date < trading_day)].tail(20)
            median_volume = int(history_daily.volume.median())
            decision = None
            signal_index = None
            for index in range(1, len(bars)):
                visible = bars.iloc[:index + 1].set_index("datetime")
                breakout = bars.iloc[index].to_dict()
                as_of = bars.iloc[index]["datetime"].to_pydatetime()
                evaluations += 1
                decision = evaluate_breakout_entry(
                    ticker=ticker,
                    cum_vol_today=int(visible.volume.sum()),
                    median_vol_20d=median_volume,
                    breakout_bar=breakout,
                    day_high=float(bars.iloc[:index].high.max()),
                    rsi_14=_rsi_14_wilder([float(value) for value in visible.close]),
                    as_of=as_of,
                    risk_engine=_OneShareRisk(),
                    intraday=visible,
                    time_start_min=variant.time_start_min,
                    volume_multiplier=variant.volume_multiplier,
                )
                if decision.get("accept"):
                    signal_index = index
                    break
                rejects[decision.get("reject_reason", "unknown")] += 1
            if signal_index is None:
                continue
            entry, stop, target = (float(decision[k]) for k in ("entry", "stop_loss", "target"))
            trade = {
                "variant": variant_name, "ticker": ticker, "trading_date": trading_day,
                "entry_bar_ts": bars.iloc[signal_index].datetime.isoformat(),
                "entry_price": entry, "stop_price": stop, "target_price": target,
                "quantity": 1, "status": "OPEN", "exit_bar_ts": None,
                "exit_price": None, "exit_reason": None, "gross_pnl": None,
                "costs": None, "net_pnl": None, "r_multiple": None,
                "signal_features": {
                    "cumulative_volume": int(visible.volume.sum()),
                    "median_daily_volume_20d": median_volume,
                    "prior_intraday_high": float(bars.iloc[:signal_index].high.max()),
                    "rsi_14": round(_rsi_14_wilder([float(value) for value in visible.close]), 6),
                    "signal_open": float(bars.iloc[signal_index].open),
                    "signal_high": float(bars.iloc[signal_index].high),
                    "signal_low": float(bars.iloc[signal_index].low),
                    "signal_close": float(bars.iloc[signal_index].close),
                },
            }
            for next_index in range(signal_index + 1, len(bars)):
                bar = bars.iloc[next_index]
                exit_result = _exit_for_bar(
                    bar.datetime.isoformat(), float(bar.open), float(bar.high),
                    float(bar.low), stop, target,
                )
                if exit_result is None:
                    continue
                exit_price, reason = exit_result
                gross = exit_price - entry
                costs = _costs_from_snapshot(entry, exit_price, 1, execution)
                net = gross - costs
                trade.update({
                    "status": "CLOSED", "exit_bar_ts": bar.datetime.isoformat(),
                    "exit_price": exit_price, "exit_reason": reason,
                    "gross_pnl": round(gross, 4), "costs": costs,
                    "net_pnl": round(net, 4),
                    "r_multiple": round(net / (entry - stop), 6),
                })
                break
            trades.append(trade)
        outputs.append(_summarize(variant_name, evaluations, rejects, trades))
    return {
        "status": "complete", "dataset_fingerprint": _run_fingerprint(snapshot["fingerprint"], config),
        "config": {**asdict(config), "variants": list(config.variants)},
        "assumptions": {
            "data_interval": "minute", "candidate_rule": "first_accept_per_ticker_day_variant",
            "entry_rule": "signal_close_marketable_limit_at_declared_entry",
            "exit_rule": "subsequent_bars_only_stop_before_target_gap_worse_time_exit_1500_at_open",
            "sizing": "one_share_fixed", "execution": execution,
            "regime": "production_default_PR1_CALM",
        },
        "funnel": {row["variant"]: {
            "evaluations": row["evaluations"], "distinct_candidates": row["distinct_candidates"],
            "top_rejects": row["top_rejects"],
        } for row in outputs},
        "variants": outputs, "diagnostics": snapshot["diagnostics"],
        "warnings": [
            "One-minute OHLC cannot resolve intrabar sequencing; stop is assumed before target.",
            "One-share fills and declared MIS costs are simulations, not broker fills or scalable returns.",
            "Open trades remain unscored when no later cached bar proves an exit.",
            "Replay uses the evaluator's default PR1_CALM regime; it does not reconstruct historical market-regime state.",
        ],
    }


def run_penny_intraday_replay(
    db_path: str, from_date: str, to_date: str, *,
    tickers: Sequence[str] | None = None,
    config: PennyReplayConfig | None = None,
) -> dict:
    config = config or PennyReplayConfig()
    start, end = _iso_day(from_date), _iso_day(to_date)
    snapshot = load_penny_minute_snapshot(
        db_path, start, end, tickers=tickers, config=config,
    )
    return _run_snapshot(snapshot, config, start, end)


def run_penny_intraday_walk_forward(
    db_path: str, from_date: str, to_date: str, *, train_days: int,
    test_days: int, step_days: int | None = None, anchored: bool = False,
    tickers: Sequence[str] | None = None,
    config: PennyReplayConfig | None = None,
) -> dict:
    """Select on train only and score the chosen variant on later test folds."""
    config = config or PennyReplayConfig()
    start, end = _iso_day(from_date), _iso_day(to_date)
    snapshot = load_penny_minute_snapshot(db_path, start, end, tickers=tickers, config=config)
    if snapshot["diagnostics"]["status"] != "valid":
        return {"verdict": "invalid_data", "dataset_fingerprint": None,
                "diagnostics": snapshot["diagnostics"], "folds": []}
    folds = generate_folds(start, end, train_days, test_days, step_days, anchored)

    def score(variant: str, period_start: str, period_end: str):
        scoped = PennyReplayConfig((variant,), config.minimum_daily_bars)
        result = _run_snapshot(snapshot, scoped, period_start, period_end)
        row = result["variants"][0]
        return row["net_pnl"] if row["closed_trades"] else None

    result = walk_forward(config.variants, folds, score)
    result.update({
        "dataset_fingerprint": _run_fingerprint(snapshot["fingerprint"], config),
        "config": {
            "train_days": train_days, "test_days": test_days,
            "step_days": step_days or test_days, "anchored": anchored,
            "variants": list(config.variants),
        },
        "diagnostics": snapshot["diagnostics"],
        "warnings": [
            "Every fold reuses one frozen local minute-cache snapshot.",
            "A verdict requires at least three scored, strictly later non-overlapping test folds.",
        ],
    })
    return result
