"""Research-only backtest registry, adapters, and immutable run archive.

This module has deliberately no broker client or order-execution imports.  A
BacktestAdapter receives a frozen dataset snapshot and returns research data;
future strategies join the lab by implementing the same contract and adding
one explicit registry entry.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import math
import os
import sqlite3
import tempfile
import traceback
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

import aiosqlite
import pandas as pd


LAB_SCHEMA_VERSION = 1
TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "UNAVAILABLE"}
PROCESS_STARTED_AT = datetime.now(timezone.utc).isoformat()
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return asdict(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _finite_json_value(value: Any) -> Any:
    """Recursively replace non-finite numbers before the JSON encoder sees them.

    ``json.dumps(default=...)`` never invokes the default hook for primitive
    floats, so handling NaN/Inf only in ``_json_default`` is insufficient.
    Persist strict JSON so archived results are always safe to return via an
    RFC-compliant API serializer.
    """
    if dataclasses.is_dataclass(value):
        return _finite_json_value(asdict(value))
    if isinstance(value, dict):
        return {key: _finite_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite_json_value(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "item"):
        try:
            return _finite_json_value(value.item())
        except (TypeError, ValueError):
            pass
    return value


def _json(value: Any) -> str:
    return json.dumps(
        _finite_json_value(value), sort_keys=True, separators=(",", ":"),
        default=_json_default, allow_nan=False,
    )


def _decode(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


@dataclass(frozen=True)
class StrategyMetadata:
    strategy_id: str
    name: str
    version: str
    description: str
    engine: str
    timeframe: str
    capabilities: tuple[str, ...]
    data_requirements: tuple[str, ...]
    limitations: tuple[str, ...]
    default_config: dict[str, Any]
    default_assumptions: dict[str, Any]
    parameter_schema: dict[str, Any]
    research_only: bool = True
    can_place_orders: bool = False


@dataclass(frozen=True)
class BacktestRequest:
    strategy_id: str
    start_date: str
    end_date: str
    config: dict[str, Any]
    assumptions: dict[str, Any]


@dataclass(frozen=True)
class PreparedDataset:
    fingerprint: str
    row_count: int
    details: dict[str, Any]
    payload: Any


class BacktestUnavailable(RuntimeError):
    pass


class BacktestAdapter(ABC):
    """Contract for all current and future Backtest Lab strategies."""

    metadata: StrategyMetadata

    def snapshot_config(self, supplied: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(supplied) - set(self.metadata.default_config))
        if unknown:
            raise ValueError(f"unknown config keys: {', '.join(unknown)}")
        return {**self.metadata.default_config, **supplied}

    def snapshot_assumptions(self, supplied: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(supplied) - set(self.metadata.default_assumptions))
        if unknown:
            raise ValueError(f"unknown assumption keys: {', '.join(unknown)}")
        merged = {**self.metadata.default_assumptions, **supplied}
        # Existing engines hard-code their execution model. Refuse a request
        # that would label a run with assumptions the engine did not apply.
        if merged != self.metadata.default_assumptions:
            raise ValueError(
                "this adapter currently supports only its documented default "
                "assumptions; custom execution assumptions would be misleading"
            )
        return merged

    @abstractmethod
    def prepare(self, db_path: str, request: BacktestRequest) -> PreparedDataset:
        """Read and freeze the exact dataset used by the run."""

    @abstractmethod
    def execute(self, prepared: PreparedDataset, request: BacktestRequest) -> dict[str, Any]:
        """Execute without network access or broker/order side effects."""

    @abstractmethod
    def normalize(self, result: dict[str, Any], request: BacktestRequest) -> tuple[dict[str, Any], list[str]]:
        """Return common metrics and honest warnings."""


def _fingerprint_rows(columns: list[str], rows: list[tuple[Any, ...]]) -> str:
    digest = hashlib.sha256()
    digest.update(_json({"columns": columns, "rows": rows}).encode("utf-8"))
    return f"sha256:{digest.hexdigest()}"


def _daily_rows(db_path: str, start_date: str, end_date: str,
                ticker: str | None = None, include_history: bool = False) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(f"file:{os.path.abspath(db_path)}?mode=ro", uri=True)
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ohlcv_cache'"
        ).fetchone()
        if not exists:
            raise BacktestUnavailable("ohlcv_cache table is unavailable")
        if ticker:
            if include_history:
                sql = ("SELECT ticker,date,open,high,low,close,volume FROM ohlcv_cache "
                       "WHERE ticker=? AND date<=? ORDER BY date")
                args = (ticker, end_date)
            else:
                sql = ("SELECT ticker,date,open,high,low,close,volume FROM ohlcv_cache "
                       "WHERE ticker=? AND date>=? AND date<=? ORDER BY date")
                args = (ticker, start_date, end_date)
        else:
            if include_history:
                sql = ("SELECT ticker,date,open,high,low,close,volume FROM ohlcv_cache "
                       "WHERE date<=? ORDER BY ticker,date")
                args = (end_date,)
            else:
                sql = ("SELECT ticker,date,open,high,low,close,volume FROM ohlcv_cache "
                       "WHERE date>=? AND date<=? ORDER BY ticker,date")
                args = (start_date, end_date)
        return [tuple(row) for row in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


class SwingDailyAdapter(BacktestAdapter):
    metadata = StrategyMetadata(
        strategy_id="swing_regime_daily",
        name="Swing Regime (daily)",
        version="1.0.0",
        description="Walk-forward replay of the existing regime-aware swing engine on cached daily bars.",
        engine="backtest.run_backtest",
        timeframe="1 day",
        capabilities=("single_ticker", "walk_forward", "risk_metrics"),
        data_requirements=("ohlcv_cache daily bars", "at least 200 pre/end rows for the ticker"),
        limitations=(
            "Uses the tested ticker as a NIFTY regime proxy and neutral VIX/breadth assumptions.",
            "No out-of-sample partition is produced by the legacy engine.",
            "Fees are not modelled; entry slippage is fixed at 20 bps in the engine.",
        ),
        default_config={"ticker": "RELIANCE", "initial_bankroll": 5000.0},
        default_assumptions={
            "fees_bps": 0.0, "slippage_bps": 20.0,
            "fill_model": "next_session_open_plus_slippage; gap stops fill at worse of open/stop",
        },
        parameter_schema={
            "ticker": {"type": "string", "required": True},
            "initial_bankroll": {"type": "number", "minimum": 1},
        },
    )

    def prepare(self, db_path: str, request: BacktestRequest) -> PreparedDataset:
        ticker = str(request.config["ticker"]).strip().upper()
        if not ticker or len(ticker) > 40:
            raise ValueError("ticker must be 1..40 characters")
        rows = _daily_rows(db_path, request.start_date, request.end_date,
                           ticker=ticker, include_history=True)
        if len(rows) < 200:
            raise BacktestUnavailable(
                f"{ticker} has {len(rows)} cached daily rows; at least 200 are required"
            )
        columns = ["ticker", "date", "open", "high", "low", "close", "volume"]
        frame = pd.DataFrame(rows, columns=columns).drop(columns=["ticker"])
        frame.index = pd.to_datetime(frame.pop("date"))
        details = {
            "source": "ohlcv_cache", "ticker": ticker, "timeframe": "day",
            "rows": len(rows), "first_bar": rows[0][1], "last_bar": rows[-1][1],
        }
        return PreparedDataset(_fingerprint_rows(columns, rows), len(rows), details, frame)

    def execute(self, prepared: PreparedDataset, request: BacktestRequest) -> dict[str, Any]:
        from backtest import run_backtest
        return run_backtest(
            ticker=str(request.config["ticker"]).strip().upper(),
            df=prepared.payload,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_bankroll=float(request.config["initial_bankroll"]),
        )

    def normalize(self, result: dict[str, Any], request: BacktestRequest) -> tuple[dict[str, Any], list[str]]:
        if result.get("error"):
            raise BacktestUnavailable(str(result["error"]))
        stats = result.get("stats", {})
        initial = float(request.config["initial_bankroll"])
        # Sum the complete trade list instead of relying on an optional legacy
        # summary field; this remains correct across runner versions.
        net_pnl = sum(float(trade.get("pnl", 0.0)) for trade in result.get("trades", []))
        final = initial + net_pnl
        summary = {
            "trade_count": int(stats.get("total_trades", 0)),
            "net_pnl": round(final - initial, 2),
            "net_return_pct": round(100 * (final - initial) / initial, 2),
            "win_rate_pct": float(stats.get("win_rate", 0.0)),
            "profit_factor": float(stats.get("profit_factor", 0.0)),
            "max_drawdown_pct": float(stats.get("max_drawdown_pct", 0.0)),
            "avg_r": float(stats.get("avg_R", 0.0)),
            "oos": {"available": False, "reason": "legacy runner has no train/OOS partition"},
        }
        warnings = list(self.metadata.limitations)
        if not summary["trade_count"]:
            warnings.append("No trades fired in this dataset window; performance inference is unavailable.")
        return summary, warnings


class PennyDailyProxyAdapter(BacktestAdapter):
    metadata = StrategyMetadata(
        strategy_id="penny_breakout_daily_proxy",
        name="Penny Breakout (daily proxy)",
        version="2.0.0",
        description="Executable daily-bar proxy for the existing penny MIS breakout engine.",
        engine="penny_backtest_v2.run_backtest",
        timeframe="1 day proxy for intraday",
        capabilities=("universe", "gate_funnel", "risk_metrics"),
        data_requirements=("ohlcv_cache daily bars in the selected range",),
        limitations=(
            "This is a daily proxy, not the live one-minute MIS strategy; do not derive live parameters from it.",
            "Gross P&L only under a declared zero-fee assumption; intraday path and realistic fills are unavailable.",
            "No out-of-sample partition is produced by the legacy engine.",
        ),
        default_config={"preset": "baseline", "initial_bankroll": 100000.0},
        default_assumptions={
            "fees_bps": 0.0, "slippage_bps": 0.0,
            "fill_model": "daily proxy; stop checked before target; gap stop uses worse of open/stop",
        },
        parameter_schema={
            "preset": {"type": "string", "enum": ["baseline", "relaxed", "phase3"]},
            "initial_bankroll": {"type": "number", "minimum": 1},
        },
    )

    def snapshot_config(self, supplied: dict[str, Any]) -> dict[str, Any]:
        merged = super().snapshot_config(supplied)
        if merged["preset"] not in ("baseline", "relaxed", "phase3"):
            raise ValueError("preset must be baseline, relaxed, or phase3")
        if float(merged["initial_bankroll"]) <= 0:
            raise ValueError("initial_bankroll must be positive")
        return merged

    def prepare(self, db_path: str, request: BacktestRequest) -> PreparedDataset:
        # Include pre-window history in both the frozen payload and fingerprint;
        # the strategy needs 20 prior sessions for its first requested day.
        rows = _daily_rows(db_path, request.start_date, request.end_date, include_history=True)
        if not rows:
            raise BacktestUnavailable("no cached daily bars exist in the selected window")
        columns = ["ticker", "date", "open", "high", "low", "close", "volume"]
        details = {
            "source": "ohlcv_cache", "timeframe": "day", "rows": len(rows),
            "tickers": len({row[0] for row in rows}),
            "first_bar": min(row[1] for row in rows), "last_bar": max(row[1] for row in rows),
        }
        return PreparedDataset(_fingerprint_rows(columns, rows), len(rows), details, rows)

    def execute(self, prepared: PreparedDataset, request: BacktestRequest) -> dict[str, Any]:
        from penny_backtest_v2 import run_backtest
        fd, snapshot_path = tempfile.mkstemp(prefix="sentinel-backtest-", suffix=".db")
        os.close(fd)
        try:
            conn = sqlite3.connect(snapshot_path)
            conn.execute(
                "CREATE TABLE ohlcv_cache (ticker TEXT,date TEXT,open REAL,high REAL,"
                "low REAL,close REAL,volume REAL,PRIMARY KEY(ticker,date))"
            )
            conn.executemany("INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?)", prepared.payload)
            conn.commit()
            conn.close()
            result = run_backtest(
                from_date=request.start_date, to_date=request.end_date,
                config_name=str(request.config["preset"]),
                bankroll=float(request.config["initial_bankroll"]), db_path=snapshot_path,
            )
            return asdict(result)
        finally:
            try:
                os.remove(snapshot_path)
            except FileNotFoundError:
                pass

    def normalize(self, result: dict[str, Any], request: BacktestRequest) -> tuple[dict[str, Any], list[str]]:
        initial = float(request.config["initial_bankroll"])
        pnl = float(result.get("total_pnl", 0.0))
        wins, losses = int(result.get("wins", 0)), int(result.get("losses", 0))
        # Full loss amounts are not retained by the legacy result, so PF cannot
        # honestly be reconstructed from sample trades.
        summary = {
            "trade_count": int(result.get("n_trades", 0)),
            "net_pnl": round(pnl, 2), "net_return_pct": round(100 * pnl / initial, 2),
            "win_rate_pct": round(100 * wins / max(1, wins + losses), 2),
            "profit_factor": None,
            "max_drawdown_pct": float(result.get("max_drawdown_pct", 0.0)),
            "avg_r": round(float(result.get("avg_r_multiple", 0.0)), 4),
            "oos": {"available": False, "reason": "daily proxy has no train/OOS partition"},
        }
        warnings = list(self.metadata.limitations)
        warnings.append("Profit factor is unavailable because the legacy result does not retain full gross win/loss totals.")
        if not summary["trade_count"]:
            warnings.append("No trades fired in this dataset window; performance inference is unavailable.")
        return summary, warnings


@dataclass(frozen=True)
class PennyWalkForwardConfig:
    initial_bankroll: float = 100000.0
    train_days: int = 60
    test_days: int = 20
    step_days: int = 20
    anchored: bool = True

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> "PennyWalkForwardConfig":
        try:
            bankroll = float(values["initial_bankroll"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("initial_bankroll must be a positive number") from exc
        if isinstance(values.get("initial_bankroll"), bool) or not math.isfinite(bankroll) or bankroll <= 0:
            raise ValueError("initial_bankroll must be a positive finite number")
        periods = {}
        for name in ("train_days", "test_days", "step_days"):
            value = values.get(name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
            if not 1 <= value <= 3650:
                raise ValueError(f"{name} must be between 1 and 3650")
            periods[name] = value
        if periods["step_days"] < periods["test_days"]:
            raise ValueError("step_days must be >= test_days to prevent overlapping OOS windows")
        anchored = values.get("anchored")
        if not isinstance(anchored, bool):
            raise ValueError("anchored must be a boolean")
        return cls(bankroll, anchored=anchored, **periods)


class PennyDailyProxyWalkForwardAdapter(BacktestAdapter):
    metadata = StrategyMetadata(
        strategy_id="penny_breakout_daily_proxy_walk_forward",
        name="Penny Breakout Walk-Forward (daily proxy)",
        version="1.0.0",
        description=(
            "Chronological train-only selection among baseline, relaxed, and phase3, "
            "followed by strictly later non-overlapping daily-proxy OOS folds."
        ),
        engine="walk_forward + penny_backtest_v2.run_backtest",
        timeframe="1 day proxy for intraday",
        capabilities=("universe", "walk_forward", "strict_oos", "train_only_selection"),
        data_requirements=(
            "one immutable ohlcv_cache daily snapshot shared by every train and test fold",
            "enough calendar history to produce at least three scored OOS folds",
        ),
        limitations=(
            "DAILY PROXY ONLY: this is not the live one-minute MIS strategy and is never live-equivalent.",
            "ZERO-FEE MODEL: brokerage, taxes, spread, slippage, queue position, and realistic intraday fills are absent.",
            "A scored fold requires at least one trade; fewer than three scored folds produce no aggregate edge metrics.",
            "Fold P&L resets to the declared research bankroll and does not model compounding across folds.",
        ),
        default_config={
            "initial_bankroll": 100000.0,
            "train_days": 60,
            "test_days": 20,
            "step_days": 20,
            "anchored": True,
        },
        default_assumptions={
            "fees_bps": 0.0,
            "slippage_bps": 0.0,
            "fill_model": "daily proxy; stop checked before target; gap stop uses worse of open/stop",
        },
        parameter_schema={
            "initial_bankroll": {"type": "number", "minimum": 1},
            "train_days": {"type": "integer", "minimum": 1},
            "test_days": {"type": "integer", "minimum": 1},
            "step_days": {"type": "integer", "minimum": 1},
            "anchored": {"type": "boolean"},
        },
    )

    def snapshot_config(self, supplied: dict[str, Any]) -> dict[str, Any]:
        merged = super().snapshot_config(supplied)
        return asdict(PennyWalkForwardConfig.from_mapping(merged))

    def prepare(self, db_path: str, request: BacktestRequest) -> PreparedDataset:
        rows = _daily_rows(
            db_path, request.start_date, request.end_date, include_history=True
        )
        if not rows:
            raise BacktestUnavailable("no cached daily bars exist in the selected window")
        columns = ["ticker", "date", "open", "high", "low", "close", "volume"]
        details = {
            "source": "ohlcv_cache",
            "timeframe": "day proxy for intraday",
            "rows": len(rows),
            "tickers": len({row[0] for row in rows}),
            "first_bar": min(row[1] for row in rows),
            "last_bar": max(row[1] for row in rows),
            "requested_start": request.start_date,
            "requested_end": request.end_date,
            "shared_by_all_folds": True,
        }
        return PreparedDataset(
            _fingerprint_rows(columns, rows), len(rows), details, tuple(rows)
        )

    def execute(self, prepared: PreparedDataset, request: BacktestRequest) -> dict[str, Any]:
        from penny_backtest_v2 import run_backtest
        from walk_forward import generate_folds, walk_forward

        cfg = PennyWalkForwardConfig.from_mapping(request.config)
        folds = generate_folds(
            request.start_date,
            request.end_date,
            train_days=cfg.train_days,
            test_days=cfg.test_days,
            step_days=cfg.step_days,
            anchored=cfg.anchored,
        )
        fd, snapshot_path = tempfile.mkstemp(
            prefix="sentinel-penny-walk-forward-", suffix=".db"
        )
        os.close(fd)
        cache: dict[tuple[str, str, str], dict[str, Any]] = {}
        try:
            conn = sqlite3.connect(snapshot_path)
            conn.execute(
                "CREATE TABLE ohlcv_cache (ticker TEXT,date TEXT,open REAL,high REAL,"
                "low REAL,close REAL,volume REAL,PRIMARY KEY(ticker,date))"
            )
            conn.executemany("INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?)", prepared.payload)
            conn.commit()
            conn.close()

            def runner(config_name: str, start: str, end: str) -> float | None:
                key = (config_name, start, end)
                if key not in cache:
                    cache[key] = asdict(run_backtest(
                        from_date=start,
                        to_date=end,
                        config_name=config_name,
                        bankroll=cfg.initial_bankroll,
                        db_path=snapshot_path,
                    ))
                result = cache[key]
                if int(result.get("n_trades", 0)) == 0:
                    return None
                return float(result.get("total_pnl", 0.0))

            report = walk_forward(
                ("baseline", "relaxed", "phase3"), folds, runner
            )
            for fold in report["folds"]:
                selected = fold["chosen_config"]
                raw = cache.get((selected, fold["test"][0], fold["test"][1])) if selected else None
                if raw is None:
                    fold["oos_scores"] = None
                elif fold["out_of_sample_score"] is None:
                    fold["oos_scores"] = {
                        "net_pnl": None, "trade_count": 0,
                        "win_rate_pct": None, "avg_r": None,
                        "max_drawdown_pct": None,
                        "warning": "No OOS trades; this fold is not scored as breakeven.",
                    }
                else:
                    fold["oos_scores"] = {
                        "net_pnl": round(float(raw.get("total_pnl", 0.0)), 2),
                        "trade_count": int(raw.get("n_trades", 0)),
                        "win_rate_pct": round(100 * int(raw.get("wins", 0)) / max(1, int(raw.get("wins", 0)) + int(raw.get("losses", 0))), 2),
                        "avg_r": round(float(raw.get("avg_r_multiple", 0.0)), 4),
                        "max_drawdown_pct": round(float(raw.get("max_drawdown_pct", 0.0)), 4),
                    }
            if report["n_scored_folds"] >= 3:
                scored = [
                    fold["oos_scores"] for fold in report["folds"]
                    if fold["out_of_sample_score"] is not None
                ]
                report["aggregate_oos_net_pnl"] = round(sum(row["net_pnl"] for row in scored), 2)
                report["aggregate_oos_trade_count"] = sum(row["trade_count"] for row in scored)
            report["objective"] = "net_pnl"
            report["configs_considered"] = ["baseline", "relaxed", "phase3"]
            report["dataset_fingerprint"] = prepared.fingerprint
            return report
        finally:
            try:
                os.remove(snapshot_path)
            except FileNotFoundError:
                pass

    def normalize(self, result: dict[str, Any], request: BacktestRequest) -> tuple[dict[str, Any], list[str]]:
        sufficient = int(result.get("n_scored_folds", 0)) >= 3
        oos = {
            "available": sufficient,
            "verdict": result.get("verdict", "insufficient_data"),
            "n_folds": int(result.get("n_folds", 0)),
            "n_scored_folds": int(result.get("n_scored_folds", 0)),
            "minimum_scored_folds": 3,
        }
        if sufficient:
            oos.update({
                "mean_train_net_pnl": result["mean_in_sample_score"],
                "mean_oos_net_pnl": result["mean_out_of_sample_score"],
                "overfit_gap": result["overfit_gap"],
                "selection_stability": result["selection_stability"],
                "positive_oos_fraction": result["positive_oos_fraction"],
                "most_selected_config": result["most_selected_config"],
            })
        summary = {
            "trade_count": result.get("aggregate_oos_trade_count") if sufficient else None,
            "net_pnl": result.get("aggregate_oos_net_pnl") if sufficient else None,
            "net_return_pct": None,
            "win_rate_pct": None,
            "profit_factor": None,
            "max_drawdown_pct": None,
            "avg_r": None,
            "oos": oos,
        }
        warnings = list(self.metadata.limitations)
        if not sufficient:
            warnings.append(
                "Insufficient OOS evidence: aggregate P&L, return, and edge metrics are intentionally unavailable."
            )
        return summary, warnings


def _ticker_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("tickers must be an array of symbols")
    clean = tuple(sorted({str(item).strip().upper() for item in value if str(item).strip()}))
    if any(len(item) > 40 for item in clean):
        raise ValueError("ticker symbols may not exceed 40 characters")
    return clean


def _write_replay_cache(intraday_rows, daily_rows) -> str:
    fd, path = tempfile.mkstemp(prefix="sentinel-intraday-replay-", suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    try:
        conn.execute("""CREATE TABLE intraday_cache (
            ticker TEXT,interval TEXT,datetime TEXT,open REAL,high REAL,low REAL,
            close REAL,volume REAL,fetched_at TEXT,
            PRIMARY KEY(ticker,interval,datetime))""")
        conn.execute("""CREATE TABLE ohlcv_cache (
            ticker TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,
            volume REAL,fetched_at TEXT,PRIMARY KEY(ticker,date))""")
        conn.executemany("INSERT INTO intraday_cache VALUES (?,?,?,?,?,?,?,?,?)", intraday_rows)
        conn.executemany("INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?,?)", daily_rows)
        conn.commit()
    finally:
        conn.close()
    return path


class PennyMinuteReplayAdapter(BacktestAdapter):
    metadata = StrategyMetadata(
        strategy_id="penny_breakout_intraday_1m_replay", name="Penny Breakout (true 1-minute replay)",
        version="1.0.0", description="Chronological replay of the production classic Penny evaluator on provenance-safe one-minute cache bars.",
        engine="penny_intraday_replay", timeframe="1 minute",
        capabilities=("universe", "true_intraday", "gate_funnel", "costs", "risk_metrics", "walk_forward", "strict_oos"),
        data_requirements=("intraday_cache rows explicitly labelled interval='minute'", "strictly prior ohlcv_cache daily volume history"),
        limitations=(
            "One-minute OHLC cannot resolve intrabar sequencing; stop is assumed before target.",
            "One-share simulated fills are not broker fills or scalable returns.",
            "Historical regime state is unavailable; evaluator default PR1_CALM is used.",
        ),
        default_config={
            "tickers": [], "variants": ["PEN_BASE", "PEN_WINDOW", "PEN_VOLUME"],
            "minimum_daily_bars": 5, "walk_forward": False,
            "train_days": 60, "test_days": 20, "step_days": 20, "anchored": True,
        },
        default_assumptions={"quantity": 1, "cost_model": "frozen_real_equity_MIS", "same_bar_rule": "stop_before_target", "time_exit": "15:00_bar_open"},
        parameter_schema={
            "tickers": {"type": "array", "items": {"type": "string"}},
            "variants": {"type": "array", "items": {"enum": ["PEN_BASE", "PEN_WINDOW", "PEN_VOLUME"]}},
            "minimum_daily_bars": {"type": "integer", "minimum": 5},
            "walk_forward": {"type": "boolean"}, "train_days": {"type": "integer", "minimum": 1},
            "test_days": {"type": "integer", "minimum": 1}, "step_days": {"type": "integer", "minimum": 1},
            "anchored": {"type": "boolean"},
        },
    )

    def snapshot_config(self, supplied):
        merged = super().snapshot_config(supplied)
        from penny_intraday_replay import PennyReplayConfig
        tickers = _ticker_list(merged["tickers"])
        variants = tuple(merged["variants"]) if isinstance(merged["variants"], (list, tuple)) else ()
        if isinstance(merged["minimum_daily_bars"], bool) or not isinstance(merged["minimum_daily_bars"], int):
            raise ValueError("minimum_daily_bars must be an integer")
        replay = PennyReplayConfig(variants=variants, minimum_daily_bars=merged["minimum_daily_bars"])
        for key in ("train_days", "test_days", "step_days"):
            if isinstance(merged[key], bool) or not isinstance(merged[key], int) or merged[key] < 1:
                raise ValueError(f"{key} must be a positive integer")
        if merged["step_days"] < merged["test_days"]:
            raise ValueError("step_days must be >= test_days to prevent overlapping OOS windows")
        if not isinstance(merged["walk_forward"], bool) or not isinstance(merged["anchored"], bool):
            raise ValueError("walk_forward and anchored must be booleans")
        return {**merged, "tickers": list(tickers), "variants": list(replay.variants)}

    def prepare(self, db_path, request):
        from penny_intraday_replay import PennyReplayConfig, load_penny_minute_snapshot
        cfg = PennyReplayConfig(tuple(request.config["variants"]), request.config["minimum_daily_bars"])
        snapshot = load_penny_minute_snapshot(
            db_path, request.start_date, request.end_date,
            tickers=request.config["tickers"] or None, config=cfg,
        )
        diagnostics = snapshot["diagnostics"]
        if diagnostics["status"] != "valid":
            raise BacktestUnavailable(diagnostics.get("warning", "one-minute provenance is unavailable"))
        intra = snapshot["intraday"]
        intraday_rows = [tuple(row) for row in intra[["ticker", "datetime", "open", "high", "low", "close", "volume"]].itertuples(index=False, name=None)]
        intraday_rows = [(t, "minute", ts.isoformat(), o, h, l, c, v, "frozen") for t, ts, o, h, l, c, v in intraday_rows]
        daily_rows = [(*row, "frozen") for row in snapshot["daily"][["ticker", "date", "open", "high", "low", "close", "volume"]].itertuples(index=False, name=None)]
        details = {"source": "intraday_cache+ohlcv_cache", "timeframe": "minute", **diagnostics, "shared_by_all_folds": True}
        return PreparedDataset(snapshot["fingerprint"], len(intraday_rows), details, (intraday_rows, daily_rows))

    def execute(self, prepared, request):
        from penny_intraday_replay import PennyReplayConfig, run_penny_intraday_replay, run_penny_intraday_walk_forward
        cfg = PennyReplayConfig(tuple(request.config["variants"]), request.config["minimum_daily_bars"])
        path = _write_replay_cache(*prepared.payload)
        try:
            kwargs = {"tickers": request.config["tickers"] or None, "config": cfg}
            if request.config["walk_forward"]:
                return run_penny_intraday_walk_forward(
                    path, request.start_date, request.end_date,
                    train_days=request.config["train_days"], test_days=request.config["test_days"],
                    step_days=request.config["step_days"], anchored=request.config["anchored"], **kwargs,
                )
            return run_penny_intraday_replay(path, request.start_date, request.end_date, **kwargs)
        finally:
            os.remove(path)

    def normalize(self, result, request):
        warnings = list(self.metadata.limitations) + list(result.get("warnings", []))
        if request.config["walk_forward"]:
            sufficient = int(result.get("n_scored_folds", 0)) >= 3
            return ({
                "trade_count": None, "net_pnl": result.get("mean_out_of_sample_score") if sufficient else None,
                "net_return_pct": None, "win_rate_pct": None, "profit_factor": None,
                "max_drawdown_pct": None, "avg_r": None,
                "oos": {"available": sufficient, "verdict": result.get("verdict"),
                        "n_scored_folds": result.get("n_scored_folds", 0), "minimum_scored_folds": 3},
            }, warnings)
        rows = result.get("variants", [])
        sole = rows[0] if len(rows) == 1 else None
        return ({
            "trade_count": sole.get("closed_trades") if sole else None,
            "net_pnl": sole.get("net_pnl") if sole else None, "net_return_pct": None,
            "win_rate_pct": None, "profit_factor": sole.get("profit_factor") if sole else None,
            "max_drawdown_pct": None, "avg_r": sole.get("avg_r") if sole else None,
            "variant_summaries": [{k: row.get(k) for k in ("variant", "paper_entries", "open_trades", "closed_trades", "net_pnl", "profit_factor", "expectancy", "avg_r", "max_drawdown")} for row in rows],
            "oos": {"available": False, "reason": "walk_forward=false"},
        }, warnings)


class Momentum15MinuteReplayAdapter(BacktestAdapter):
    metadata = StrategyMetadata(
        strategy_id="momentum_intraday_15m_replay", name="Momentum (true 15-minute replay)",
        version="1.0.0", description="Chronological production-evaluator replay using explicit 15-minute cache provenance.",
        engine="momentum_replay", timeframe="15 minute",
        capabilities=("universe", "true_intraday", "gate_funnel", "costs", "risk_metrics", "chronological_oos"),
        data_requirements=("intraday_cache interval='15minute'", "strictly prior ohlcv_cache daily history"),
        limitations=("15-minute OHLC assumes stop before target.", "Full quantity exits at T1; partial runners and trailing stops are not modelled."),
        default_config={
            "tickers": [], "bankroll": 4500.0, "momentum_pool": 2500.0,
            "min_candles": 4, "daily_lookback_rows": 30, "market_regime": "BULL",
            "regime": "REGIME_1_NORMAL", "normal_volume_threshold": 1.5,
            "lunchtime_volume_threshold": 1.75, "lunchtime_start": "11:30",
            "lunchtime_end": "13:15", "variants": ["MOM_BASE", "MOM_RECENCY_5"], "oos_folds": 3,
        },
        default_assumptions={"execution": "frozen_momentum_shadow_slippage_and_MIS_costs", "same_bar_rule": "stop_before_target", "position_lifecycle": "full_quantity_target_1"},
        parameter_schema={
            "tickers": {"type": "array", "items": {"type": "string"}},
            "bankroll": {"type": "number", "minimum": 0.01},
            "momentum_pool": {"type": "number", "minimum": 0.01},
            "min_candles": {"type": "integer", "minimum": 2},
            "daily_lookback_rows": {"type": "integer", "minimum": 14},
            "market_regime": {"type": "string"},
            "regime": {"type": "string", "enum": ["REGIME_1_NORMAL", "REGIME_2_ELEVATED", "REGIME_3_CRISIS", "UNKNOWN"]},
            "normal_volume_threshold": {"type": "number", "minimum": 0},
            "lunchtime_volume_threshold": {"type": "number", "minimum": 0},
            "lunchtime_start": {"type": "string", "format": "HH:MM"},
            "lunchtime_end": {"type": "string", "format": "HH:MM"},
            "variants": {"type": "array", "items": {"enum": ["MOM_BASE", "MOM_RECENCY_5"]}},
            "oos_folds": {"type": "integer", "minimum": 3},
        },
    )

    def _typed(self, values):
        from momentum_replay import MomentumReplayConfig
        fields = {key: value for key, value in values.items() if key != "tickers"}
        fields["variants"] = tuple(fields["variants"]) if isinstance(fields["variants"], (list, tuple)) else ()
        if not fields["variants"] or len(set(fields["variants"])) != len(fields["variants"]):
            raise ValueError("variants must be non-empty and unique")
        for key in ("bankroll", "momentum_pool", "normal_volume_threshold", "lunchtime_volume_threshold"):
            value = fields[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) <= 0:
                raise ValueError(f"{key} must be a positive finite number")
        for key in ("min_candles", "daily_lookback_rows", "oos_folds"):
            if isinstance(fields[key], bool) or not isinstance(fields[key], int):
                raise ValueError(f"{key} must be an integer")
        try:
            start = datetime.strptime(fields["lunchtime_start"], "%H:%M").time()
            end = datetime.strptime(fields["lunchtime_end"], "%H:%M").time()
        except (TypeError, ValueError) as exc:
            raise ValueError("lunchtime_start and lunchtime_end must use HH:MM") from exc
        if start > end:
            raise ValueError("lunchtime_start must not follow lunchtime_end")
        if not isinstance(fields["market_regime"], str) or not fields["market_regime"].strip():
            raise ValueError("market_regime must be a non-empty string")
        return MomentumReplayConfig(**fields)

    def snapshot_config(self, supplied):
        merged = super().snapshot_config(supplied)
        tickers, typed = _ticker_list(merged["tickers"]), self._typed(merged)
        return {**asdict(typed), "variants": list(typed.variants), "tickers": list(tickers)}

    def prepare(self, db_path, request):
        from momentum_replay import ReplayDataError, _read_cache, _validate_frame
        try:
            intra, daily, provenance = _read_cache(db_path, request.config["tickers"] or None, request.start_date, request.end_date)
            validated = _validate_frame(intra)
        except ReplayDataError as exc:
            raise BacktestUnavailable(str(exc)) from exc
        intra_rows = [tuple(row) for row in intra[["ticker", "interval", "datetime", "open", "high", "low", "close", "volume", "fetched_at"]].itertuples(index=False, name=None)]
        daily_rows = [tuple(row) for row in daily[["ticker", "date", "open", "high", "low", "close", "volume", "fetched_at"]].itertuples(index=False, name=None)]
        columns = ["ticker", "interval", "datetime", "open", "high", "low", "close", "volume", "fetched_at"]
        details = {"source": "intraday_cache+ohlcv_cache", "timeframe": "15minute", "rows": len(intra_rows), "daily_rows": len(daily_rows), **provenance, "shared_by_all_folds": True}
        return PreparedDataset(_fingerprint_rows(columns, intra_rows + daily_rows), len(validated), details, (intra_rows, daily_rows))

    def execute(self, prepared, request):
        from momentum_replay import run_momentum_replay
        path = _write_replay_cache(*prepared.payload)
        try:
            return run_momentum_replay(path, self._typed(request.config), tickers=request.config["tickers"] or None, start=request.start_date, end=request.end_date)
        finally:
            os.remove(path)

    def normalize(self, result, request):
        summary = result.get("summary", {})
        sole = len(request.config["variants"]) == 1
        oos = result.get("oos", {})
        return ({
            "trade_count": summary.get("closed_trades") if sole else None,
            "net_pnl": summary.get("net_pnl") if sole else None, "net_return_pct": None,
            "win_rate_pct": None, "profit_factor": summary.get("profit_factor") if sole else None,
            "max_drawdown_pct": None, "avg_r": summary.get("avg_r") if sole else None,
            "variant_comparison": summary,
            "oos": {"available": oos.get("status") == "scored", **oos},
        }, list(self.metadata.limitations) + list(result.get("warnings", [])))


class FnoUnavailableAdapter(BacktestAdapter):
    metadata = StrategyMetadata(
        strategy_id="fno_momentum_5m",
        name="F&O Momentum (5-minute)", version="1.0.0",
        description="Existing F&O replay engine; registered but unavailable until verified futures bars are persisted.",
        engine="fno_backtest.run_fno_backtest", timeframe="5 minute futures",
        capabilities=("modelled_options", "costs", "risk_metrics"),
        data_requirements=("verified NIFTY futures 5-minute OHLCV with interval and instrument provenance",),
        limitations=("Current cache does not establish the required futures instrument/timeframe provenance.",),
        default_config={"initial_bankroll": 250000.0, "iv": 0.12},
        default_assumptions={"fees_bps": 0.0, "slippage_bps": 0.0, "fill_model": "unavailable"},
        parameter_schema={},
    )

    def prepare(self, db_path: str, request: BacktestRequest) -> PreparedDataset:
        raise BacktestUnavailable(self.metadata.limitations[0])

    def execute(self, prepared: PreparedDataset, request: BacktestRequest) -> dict[str, Any]:
        raise BacktestUnavailable(self.metadata.limitations[0])

    def normalize(self, result: dict[str, Any], request: BacktestRequest) -> tuple[dict[str, Any], list[str]]:
        raise BacktestUnavailable(self.metadata.limitations[0])


STRATEGY_REGISTRY: dict[str, BacktestAdapter] = {
    adapter.metadata.strategy_id: adapter
    for adapter in (
        SwingDailyAdapter(), PennyDailyProxyAdapter(),
        PennyDailyProxyWalkForwardAdapter(), PennyMinuteReplayAdapter(),
        Momentum15MinuteReplayAdapter(), FnoUnavailableAdapter(),
    )
}


async def init_backtest_lab_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA busy_timeout=5000")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS backtest_experiments (
                experiment_id TEXT PRIMARY KEY,
                schema_version INTEGER NOT NULL,
                strategy_id TEXT NOT NULL,
                strategy_version TEXT NOT NULL,
                config_json TEXT NOT NULL,
                assumptions_json TEXT NOT NULL,
                dataset_request_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS backtest_runs (
                run_id TEXT PRIMARY KEY,
                experiment_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','UNAVAILABLE')),
                error TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                dataset_fingerprint TEXT,
                dataset_json TEXT,
                summary_json TEXT,
                warnings_json TEXT,
                result_json TEXT,
                FOREIGN KEY(experiment_id) REFERENCES backtest_experiments(experiment_id)
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_backtest_runs_created ON backtest_runs(created_at DESC)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_backtest_runs_experiment ON backtest_runs(experiment_id)")
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS backtest_experiments_immutable_update
            BEFORE UPDATE ON backtest_experiments BEGIN
                SELECT RAISE(ABORT, 'backtest experiments are immutable');
            END
        """)
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS backtest_experiments_immutable_delete
            BEFORE DELETE ON backtest_experiments BEGIN
                SELECT RAISE(ABORT, 'backtest experiments are immutable');
            END
        """)
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS backtest_terminal_runs_immutable
            BEFORE UPDATE ON backtest_runs
            WHEN OLD.status IN ('SUCCEEDED','FAILED','UNAVAILABLE') BEGIN
                SELECT RAISE(ABORT, 'terminal backtest runs are immutable');
            END
        """)
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS backtest_runs_no_delete
            BEFORE DELETE ON backtest_runs BEGIN
                SELECT RAISE(ABORT, 'backtest runs are immutable');
            END
        """)
        # A background task cannot survive a process/container restart. Close
        # only rows that pre-date this Python process; current-process runs are
        # never touched by this idempotent startup recovery.
        recovered_at = _utc_now()
        await db.execute(
            "UPDATE backtest_runs SET status='FAILED',completed_at=?,"
            "error='Process restarted before this background run completed',"
            "warnings_json=? WHERE status IN ('QUEUED','RUNNING') AND created_at < ?",
            (recovered_at, _json([
                "Run interrupted by a process restart; no performance conclusion is available."
            ]), PROCESS_STARTED_AT),
        )
        await db.commit()


def _validate_dates(start_date: str, end_date: str) -> None:
    try:
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    except ValueError as exc:
        raise ValueError("start_date and end_date must use YYYY-MM-DD") from exc
    if start > end:
        raise ValueError("start_date must be on or before end_date")
    if (end - start).days > 3650:
        raise ValueError("date window may not exceed 10 years")


async def list_strategies(db_path: str) -> list[dict[str, Any]]:
    items = []
    for adapter in STRATEGY_REGISTRY.values():
        meta = asdict(adapter.metadata)
        meta["capabilities"] = list(meta["capabilities"])
        meta["data_requirements"] = list(meta["data_requirements"])
        meta["limitations"] = list(meta["limitations"])
        if isinstance(adapter, FnoUnavailableAdapter):
            meta.update({"available": False, "availability_reason": adapter.metadata.limitations[0]})
        else:
            try:
                conn = sqlite3.connect(f"file:{os.path.abspath(db_path)}?mode=ro", uri=True)
                tables = {row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )}
                daily_count = conn.execute("SELECT count(*) FROM ohlcv_cache").fetchone()[0] if "ohlcv_cache" in tables else 0
                if isinstance(adapter, (PennyMinuteReplayAdapter, Momentum15MinuteReplayAdapter)):
                    columns = {row[1] for row in conn.execute("PRAGMA table_info(intraday_cache)")} if "intraday_cache" in tables else set()
                    interval = "minute" if isinstance(adapter, PennyMinuteReplayAdapter) else "15minute"
                    intraday_count = conn.execute(
                        "SELECT count(*) FROM intraday_cache WHERE interval=?", (interval,)
                    ).fetchone()[0] if "interval" in columns else 0
                    available = daily_count > 0 and intraday_count > 0
                    reason = None if available else f"requires ohlcv_cache plus explicit interval='{interval}' intraday rows"
                else:
                    available = daily_count > 0
                    reason = None if available else "ohlcv_cache has no daily bars"
                conn.close()
                meta.update({
                    "available": available,
                    "availability_reason": reason,
                })
            except sqlite3.Error as exc:
                meta.update({"available": False, "availability_reason": f"dataset check failed: {exc}"})
        items.append(meta)
    return items


async def submit_run(db_path: str, strategy_id: str, start_date: str, end_date: str,
                     supplied_config: dict[str, Any] | None = None,
                     supplied_assumptions: dict[str, Any] | None = None) -> dict[str, Any]:
    _validate_dates(start_date, end_date)
    adapter = STRATEGY_REGISTRY.get(strategy_id)
    if not adapter:
        raise ValueError(f"unknown strategy_id: {strategy_id}")
    config = adapter.snapshot_config(supplied_config or {})
    assumptions = adapter.snapshot_assumptions(supplied_assumptions or {})
    if float(config.get("initial_bankroll", 1)) <= 0:
        raise ValueError("initial_bankroll must be positive")

    await init_backtest_lab_db(db_path)
    experiment_id, run_id, created_at = str(uuid.uuid4()), str(uuid.uuid4()), _utc_now()
    dataset_request = {"start_date": start_date, "end_date": end_date, "source": "local_cache_only"}
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA busy_timeout=5000")
        await db.execute(
            "INSERT INTO backtest_experiments VALUES (?,?,?,?,?,?,?,?)",
            (experiment_id, LAB_SCHEMA_VERSION, strategy_id, adapter.metadata.version,
             _json(config), _json(assumptions), _json(dataset_request), created_at),
        )
        await db.execute(
            "INSERT INTO backtest_runs(run_id,experiment_id,status,created_at,warnings_json) VALUES (?,?,?,?,?)",
            (run_id, experiment_id, "QUEUED", created_at, "[]"),
        )
        await db.commit()
    request = BacktestRequest(strategy_id, start_date, end_date, config, assumptions)
    task = asyncio.create_task(_run_background(db_path, run_id, adapter, request))
    # asyncio otherwise retains only a weak reference. A module-level set keeps
    # long replays alive; the callback prevents completed-task accumulation.
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return {"run_id": run_id, "experiment_id": experiment_id, "status": "QUEUED", "created_at": created_at}


async def _run_background(db_path: str, run_id: str, adapter: BacktestAdapter,
                          request: BacktestRequest) -> None:
    started = _utc_now()
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE backtest_runs SET status='RUNNING',started_at=? WHERE run_id=? AND status='QUEUED'", (started, run_id))
        await db.commit()
    prepared: PreparedDataset | None = None
    try:
        prepared = await asyncio.to_thread(adapter.prepare, db_path, request)
        result = await asyncio.to_thread(adapter.execute, prepared, request)
        summary, warnings = adapter.normalize(result, request)
        update = ("SUCCEEDED", None, _utc_now(), prepared.fingerprint, _json(prepared.details),
                  _json(summary), _json(warnings), _json(result), run_id)
    except BacktestUnavailable as exc:
        update = ("UNAVAILABLE", str(exc), _utc_now(),
                  prepared.fingerprint if prepared else None,
                  _json(prepared.details) if prepared else None,
                  None, _json([str(exc)]), None, run_id)
    except Exception as exc:
        # Persist a bounded, operator-useful error without returning a traceback
        # or filesystem detail through the API.
        traceback.print_exc()
        update = ("FAILED", f"{type(exc).__name__}: {str(exc)[:500]}", _utc_now(),
                  prepared.fingerprint if prepared else None,
                  _json(prepared.details) if prepared else None,
                  None, _json(["Run failed; no performance conclusion is available."]), None, run_id)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA busy_timeout=5000")
        await db.execute(
            "UPDATE backtest_runs SET status=?,error=?,completed_at=?,dataset_fingerprint=?,"
            "dataset_json=?,summary_json=?,warnings_json=?,result_json=? "
            "WHERE run_id=? AND status='RUNNING'", update,
        )
        await db.commit()


def _row_to_run(row: aiosqlite.Row, include_result: bool) -> dict[str, Any]:
    item = {
        "run_id": row["run_id"], "experiment_id": row["experiment_id"],
        "strategy_id": row["strategy_id"], "strategy_version": row["strategy_version"],
        "status": row["status"], "error": row["error"], "created_at": row["created_at"],
        "started_at": row["started_at"], "completed_at": row["completed_at"],
        "config": _decode(row["config_json"], {}),
        "assumptions": _decode(row["assumptions_json"], {}),
        "dataset_request": _decode(row["dataset_request_json"], {}),
        "dataset_fingerprint": row["dataset_fingerprint"],
        "dataset": _decode(row["dataset_json"], None),
        "summary": _decode(row["summary_json"], None),
        "warnings": _decode(row["warnings_json"], []),
    }
    if include_result:
        item["result"] = _decode(row["result_json"], None)
    return item


_RUN_SELECT = """
SELECT r.*,e.strategy_id,e.strategy_version,e.config_json,e.assumptions_json,e.dataset_request_json
FROM backtest_runs r JOIN backtest_experiments e ON e.experiment_id=r.experiment_id
"""


async def list_runs(db_path: str, limit: int = 50, strategy_id: str | None = None,
                    status: str | None = None) -> list[dict[str, Any]]:
    await init_backtest_lab_db(db_path)
    where, args = [], []
    if strategy_id:
        where.append("e.strategy_id=?"); args.append(strategy_id)
    if status:
        status = status.upper()
        if status not in {"QUEUED", "RUNNING", *TERMINAL_STATUSES}:
            raise ValueError("invalid status filter")
        where.append("r.status=?"); args.append(status)
    sql = _RUN_SELECT + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY r.created_at DESC LIMIT ?"
    args.append(max(1, min(int(limit), 200)))
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(sql, args)).fetchall()
    return [_row_to_run(row, include_result=False) for row in rows]


async def get_run(db_path: str, run_id: str) -> dict[str, Any] | None:
    await init_backtest_lab_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(_RUN_SELECT + " WHERE r.run_id=?", (run_id,))).fetchone()
    return _row_to_run(row, include_result=True) if row else None
