"""Broker-free paper-shadow evaluation for declared Momentum variants.

This module deliberately imports only the pure strategy evaluator plus storage
and serialization libraries. It has no Kite, executor, order, or scheduler
dependency. Evaluation and persistence are separate operations so callers can
test the same immutable frames before choosing where to record the evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import math
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence

import aiosqlite
import pandas as pd

from config import settings
from cost_schedules import (
    EQUITY_INTRADAY_EFFECTIVE_DATE, EQUITY_INTRADAY_SCHEDULE_VERSION,
    EQUITY_INTRADAY_VERIFIED_AS_OF,
)
from engine import evaluate_momentum_signal


@dataclass(frozen=True)
class MomentumShadowVariant:
    name: str
    crossover_lookback: int
    max_vwap_distance_atr: float | None


_VARIANT_ROWS = (
    MomentumShadowVariant("MOM_BASE", 3, None),
    MomentumShadowVariant("MOM_RECENCY_5", 5, 0.50),
)
VARIANTS: Mapping[str, MomentumShadowVariant] = MappingProxyType({
    variant.name: variant for variant in _VARIANT_ROWS
})


@dataclass(frozen=True)
class MomentumShadowExecution:
    entry_slippage_bps: float = 5.0
    exit_slippage_bps: float = 5.0
    time_exit_hour: int = 15
    time_exit_minute: int = 15
    same_bar_priority: str = "stop_before_target"
    cost_model: str = "zerodha_equity_intraday"
    cost_schedule_version: str = EQUITY_INTRADAY_SCHEDULE_VERSION
    cost_schedule_effective_date: str | None = EQUITY_INTRADAY_EFFECTIVE_DATE
    cost_schedule_verified_as_of: str = EQUITY_INTRADAY_VERIFIED_AS_OF
    position_lifecycle: str = "full_quantity_exit_at_target_1_no_runner_or_trailing"
    brokerage_pct: float = 0.0003
    brokerage_max_per_order: float = 20.0
    stt_sell_pct: float = 0.00025
    exchange_pct: float = 0.0000307
    stamp_duty_buy_pct: float = 0.00003
    sebi_pct: float = 0.000001
    ipft_pct: float = 0.000000001
    gst_pct: float = 0.18


EXECUTION = MomentumShadowExecution(
    brokerage_pct=float(settings.ZERODHA_BROKERAGE_PCT),
    brokerage_max_per_order=float(settings.ZERODHA_BROKERAGE_MAX),
    stt_sell_pct=float(settings.ZERODHA_STT_MIS),
    exchange_pct=float(settings.ZERODHA_EXCHANGE_PCT),
    stamp_duty_buy_pct=float(settings.ZERODHA_STAMP_DUTY_PCT),
    sebi_pct=float(settings.ZERODHA_SEBI_PCT),
    ipft_pct=float(settings.ZERODHA_IPFT_PCT),
    gst_pct=float(settings.ZERODHA_GST_PCT),
)


def momentum_shadow_execution_config() -> dict:
    """Published, immutable assumptions used by the virtual outcome book."""
    return asdict(EXECUTION)


def _json_safe(value):
    """Convert pandas/numpy scalar evidence without taking a numpy dependency."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            pass
    return value


def _normalise_timestamp(value) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _frame_fingerprint(ticker: str, df: pd.DataFrame, config: dict) -> str:
    digest = hashlib.sha256()
    digest.update(ticker.encode("utf-8"))
    digest.update(json.dumps(
        _json_safe(config), sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8"))
    digest.update(pd.util.hash_pandas_object(df, index=True).values.tobytes())
    return f"sha256:{digest.hexdigest()}"


def _bars(df: pd.DataFrame) -> list[dict]:
    required = {"open", "high", "low", "close"}
    if df.empty or not required.issubset(df.columns):
        return []
    rows = []
    for index, bar in df.iterrows():
        ts = _normalise_timestamp(index)
        try:
            datetime.fromisoformat(ts.replace("Z", "+00:00"))
            values = {name: float(bar[name]) for name in required}
        except (TypeError, ValueError):
            continue
        if not all(math.isfinite(value) and value > 0 for value in values.values()):
            continue
        rows.append({"bar_ts": ts, **values})
    return rows


def _identity(
    df: pd.DataFrame,
    trading_date: date | str | None,
    bar_ts: datetime | str | None,
) -> tuple[str, str]:
    if bar_ts is None:
        if df.empty:
            raise ValueError("bar_ts is required when the intraday frame is empty")
        bar_ts = df.index[-1]
    bar_text = _normalise_timestamp(bar_ts)
    if trading_date is None:
        if hasattr(bar_ts, "date"):
            trading_date = bar_ts.date()
        elif len(bar_text) >= 10:
            trading_date = bar_text[:10]
        else:
            raise ValueError("trading_date cannot be derived from bar_ts")
    day_text = trading_date.isoformat() if hasattr(trading_date, "isoformat") else str(trading_date)
    try:
        parsed_day = date.fromisoformat(day_text)
        parsed_bar = datetime.fromisoformat(bar_text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("trading_date and bar_ts must be valid ISO values") from exc
    if parsed_day.isoformat() != day_text or len(bar_text) < 16:
        raise ValueError("trading_date must be ISO YYYY-MM-DD")
    return day_text, bar_text


def _ticker(value) -> str:
    ticker = str(value).strip().upper()
    if not ticker:
        raise ValueError("ticker must not be empty")
    return ticker


def _selected_variants(names: Sequence[str] | None) -> tuple[MomentumShadowVariant, ...]:
    selected = tuple(names) if names is not None else tuple(VARIANTS)
    if not selected:
        raise ValueError("at least one Momentum shadow variant is required")
    unknown = [name for name in selected if name not in VARIANTS]
    if unknown:
        raise ValueError(f"unknown Momentum shadow variant(s): {', '.join(unknown)}")
    if len(set(selected)) != len(selected):
        raise ValueError("Momentum shadow variant names must be unique")
    return tuple(VARIANTS[name] for name in selected)


def evaluate_momentum_shadows(
    ticker: str,
    df: pd.DataFrame,
    prev_day_high: float,
    bankroll: float,
    momentum_pool: float,
    *,
    df_daily: pd.DataFrame | None = None,
    min_candles: int = 4,
    vol_surge_threshold: float = 1.5,
    market_regime: str = "BULL",
    regime=None,
    variants: Sequence[str] | None = None,
    trading_date: date | str | None = None,
    bar_ts: datetime | str | None = None,
) -> list[dict]:
    """Purely evaluate named variants against the exact same input frames."""
    ticker = _ticker(ticker)
    day_text, bar_text = _identity(df, trading_date, bar_ts)
    results = []
    for variant in _selected_variants(variants):
        accepted, decision = evaluate_momentum_signal(
            ticker=ticker,
            df=df,
            prev_day_high=prev_day_high,
            bankroll=bankroll,
            momentum_pool=momentum_pool,
            min_candles=min_candles,
            df_daily=df_daily,
            vol_surge_threshold=vol_surge_threshold,
            market_regime=market_regime,
            regime=regime,
            crossover_lookback=variant.crossover_lookback,
            max_vwap_distance_atr=variant.max_vwap_distance_atr,
        )
        config = {
            **asdict(variant),
            "min_candles": min_candles,
            "vol_surge_threshold": vol_surge_threshold,
            "market_regime": market_regime,
            "regime": getattr(regime, "name", None),
        }
        feature_names = (
            "close", "vwap", "volume_ratio", "intraday_high", "intraday_low",
            "daily_atr", "vwap_distance", "vwap_distance_atr",
            "crossover_lookback", "max_vwap_distance_atr",
        )
        features = {name: decision.get(name) for name in feature_names}
        results.append({
            "trading_date": day_text,
            "ticker": ticker,
            "bar_ts": bar_text,
            "variant": variant.name,
            "accepted": bool(accepted),
            "reject_reason": None if accepted else decision.get("reject_reason", "unknown"),
            "features": features,
            "config": config,
            "decision": decision,
            "dataset_fingerprint": _frame_fingerprint(ticker, df, config),
            # Transient lifecycle evidence. Persistence stores observations as
            # immutable events, not this duplicated frame blob.
            "bars": _bars(df),
        })
    return results


async def init_momentum_shadow_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS momentum_shadow_evaluations (
                trading_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                bar_ts TEXT NOT NULL,
                variant TEXT NOT NULL,
                accepted INTEGER NOT NULL CHECK (accepted IN (0,1)),
                reject_reason TEXT,
                features_json TEXT NOT NULL,
                config_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (trading_date, ticker, bar_ts, variant)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS momentum_shadow_trades (
                trading_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                variant TEXT NOT NULL,
                entry_bar_ts TEXT NOT NULL,
                raw_entry REAL NOT NULL,
                entry_fill REAL NOT NULL,
                stop_price REAL NOT NULL,
                target_price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                initial_risk REAL NOT NULL,
                config_json TEXT NOT NULL,
                execution_json TEXT NOT NULL,
                dataset_fingerprint TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (trading_date,ticker,variant)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS momentum_shadow_trade_events (
                trading_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                variant TEXT NOT NULL,
                bar_ts TEXT NOT NULL,
                event_type TEXT NOT NULL CHECK(event_type IN ('OBSERVED','CLOSED')),
                reason TEXT,
                bar_json TEXT NOT NULL,
                exit_fill REAL,
                gross_pnl REAL,
                costs REAL,
                net_pnl REAL,
                r_multiple REAL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (trading_date,ticker,variant,bar_ts,event_type)
            )
        """)
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS momentum_shadow_trades_immutable_update
            BEFORE UPDATE ON momentum_shadow_trades BEGIN
                SELECT RAISE(ABORT, 'momentum shadow trades are immutable');
            END
        """)
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS momentum_shadow_trades_immutable_delete
            BEFORE DELETE ON momentum_shadow_trades BEGIN
                SELECT RAISE(ABORT, 'momentum shadow trades are immutable');
            END
        """)
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS momentum_shadow_events_immutable_update
            BEFORE UPDATE ON momentum_shadow_trade_events BEGIN
                SELECT RAISE(ABORT, 'momentum shadow events are immutable');
            END
        """)
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS momentum_shadow_events_immutable_delete
            BEFORE DELETE ON momentum_shadow_trade_events BEGIN
                SELECT RAISE(ABORT, 'momentum shadow events are immutable');
            END
        """)
        await db.commit()


def _exit_for_bar(trade, bar: dict, *, overnight: bool = False) -> tuple[str, float] | None:
    stop, target = float(trade["stop_price"]), float(trade["target_price"])
    bar_open = float(bar["open"])
    slip = EXECUTION.exit_slippage_bps / 10000.0
    if overnight:
        return "overnight_gap_exit", bar_open * (1.0 - slip)
    parsed = datetime.fromisoformat(str(bar["bar_ts"]).replace("Z", "+00:00"))
    # Bar timestamps are starts. At/after the cutoff only the open was known
    # at the declared exit instant; inspecting this bar's extremes is hindsight.
    if (parsed.hour, parsed.minute) >= (EXECUTION.time_exit_hour, EXECUTION.time_exit_minute):
        return "time_exit", bar_open * (1.0 - slip)
    if bar_open <= stop:
        return "stop_gap", bar_open * (1.0 - slip)
    if bar_open >= target:
        return "target_gap_conservative", target * (1.0 - slip)
    if float(bar["low"]) <= stop:
        return "stop", stop * (1.0 - slip)
    if float(bar["high"]) >= target:
        return "target", target * (1.0 - slip)
    return None


def _declared_costs(entry: float, exit_price: float, quantity: int, execution: dict) -> float:
    """Freeze the cost arithmetic to the assumptions stored with the trade."""
    buy, sell = entry * quantity, exit_price * quantity
    brokerage = min(buy * execution["brokerage_pct"], execution["brokerage_max_per_order"])
    brokerage += min(sell * execution["brokerage_pct"], execution["brokerage_max_per_order"])
    exchange = (buy + sell) * execution["exchange_pct"]
    sebi = (buy + sell) * execution["sebi_pct"]
    ipft = (buy + sell) * execution.get("ipft_pct", 0.0)
    taxable = brokerage + exchange
    if execution.get("cost_schedule_version"):
        taxable += sebi + ipft
    costs = (
        brokerage
        + sell * execution["stt_sell_pct"]
        + exchange
        + buy * execution["stamp_duty_buy_pct"]
        + sebi + ipft
        + taxable * execution["gst_pct"]
    )
    return round(costs, 4)


async def _advance_and_open(db, result: dict, created_at: str) -> None:
    result_key = (result["trading_date"], str(result["ticker"]).upper(), result["variant"])
    db.row_factory = aiosqlite.Row
    open_trades = await (await db.execute("""
        SELECT t.* FROM momentum_shadow_trades t
        WHERE t.ticker=? AND t.variant=? AND NOT EXISTS (
            SELECT 1 FROM momentum_shadow_trade_events e
            WHERE e.trading_date=t.trading_date AND e.ticker=t.ticker
              AND e.variant=t.variant AND e.event_type='CLOSED'
        ) ORDER BY t.trading_date,t.entry_bar_ts
    """, (result_key[1], result_key[2]))).fetchall()
    for trade in open_trades:
        trade_key = (trade["trading_date"], trade["ticker"], trade["variant"])
        entry_ts = datetime.fromisoformat(
            str(trade["entry_bar_ts"]).replace("Z", "+00:00")
        )
        for bar in result.get("bars", []):
            try:
                observed_ts = datetime.fromisoformat(
                    str(bar.get("bar_ts", "")).replace("Z", "+00:00")
                )
            except ValueError:
                continue
            if observed_ts <= entry_ts:
                continue
            overnight = observed_ts.date() > date.fromisoformat(trade["trading_date"])
            exit_event = _exit_for_bar(trade, bar, overnight=overnight)
            if exit_event is None:
                await db.execute("""
                        INSERT OR IGNORE INTO momentum_shadow_trade_events
                            (trading_date,ticker,variant,bar_ts,event_type,reason,
                             bar_json,created_at) VALUES (?,?,?,?,?,?,?,?)
                """, (*trade_key, bar["bar_ts"], "OBSERVED", None,
                      json.dumps(_json_safe(bar), sort_keys=True, allow_nan=False), created_at))
                continue
            reason, exit_fill = exit_event
            quantity = int(trade["quantity"])
            gross = (exit_fill - float(trade["entry_fill"])) * quantity
            # Persisted execution JSON is authoritative. Do not fill missing
            # legacy rate fields from today's schedule after a restart.
            execution = json.loads(trade["execution_json"])
            costs = _declared_costs(
                float(trade["entry_fill"]), exit_fill, quantity, execution,
            )
            net = gross - costs
            r_multiple = net / float(trade["initial_risk"])
            await db.execute("""
                INSERT OR IGNORE INTO momentum_shadow_trade_events
                    (trading_date,ticker,variant,bar_ts,event_type,reason,
                     bar_json,exit_fill,gross_pnl,costs,net_pnl,r_multiple,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (*trade_key, bar["bar_ts"], "CLOSED", reason,
                  json.dumps(_json_safe(bar), sort_keys=True, allow_nan=False),
                  round(exit_fill, 6), round(gross, 6), round(costs, 6),
                  round(net, 6), round(r_multiple, 8), created_at))
            break

    if not result.get("accepted"):
        return
    decision = result.get("decision") or {}
    try:
        raw_entry = float(decision.get("entry_price", decision.get("close")))
        stop = float(decision["stop_loss"])
        target = float(decision.get("target_1", decision.get("target")))
        quantity = int(decision["shares"])
        fingerprint = str(result["dataset_fingerprint"])
    except (KeyError, TypeError, ValueError):
        return
    if not all(math.isfinite(value) and value > 0 for value in (raw_entry, stop, target)):
        return
    if quantity <= 0 or not fingerprint:
        return
    entry_fill = raw_entry * (1.0 + EXECUTION.entry_slippage_bps / 10000.0)
    if not stop < entry_fill < target:
        return
    initial_risk = (entry_fill - stop) * quantity
    if initial_risk <= 0:
        return
    await db.execute("""
        INSERT OR IGNORE INTO momentum_shadow_trades
            (trading_date,ticker,variant,entry_bar_ts,raw_entry,entry_fill,
             stop_price,target_price,quantity,initial_risk,config_json,
             execution_json,dataset_fingerprint,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (*result_key, result["bar_ts"], raw_entry, round(entry_fill, 6), stop,
          target, quantity, round(initial_risk, 6),
          json.dumps(_json_safe(result.get("config", {})), sort_keys=True,
                     separators=(",", ":"), allow_nan=False),
          json.dumps(asdict(EXECUTION), sort_keys=True, separators=(",", ":")),
          fingerprint, created_at))


async def persist_momentum_shadow_results(db_path: str, results: Iterable[dict]) -> int:
    """Insert unseen evaluations and return the number of new rows."""
    await init_momentum_shadow_db(db_path)
    inserted = 0
    created_at = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(db_path) as db:
        for result in results:
            variant = str(result.get("variant", ""))
            if variant not in VARIANTS:
                raise ValueError(f"unregistered Momentum shadow variant: {variant!r}")
            ticker = _ticker(result.get("ticker", ""))
            trading_date, bar_ts = _identity(
                pd.DataFrame(), result.get("trading_date"), result.get("bar_ts")
            )
            cursor = await db.execute(
                """
                INSERT OR IGNORE INTO momentum_shadow_evaluations
                    (trading_date,ticker,bar_ts,variant,accepted,reject_reason,
                     features_json,config_json,created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    trading_date, ticker, bar_ts, variant, int(bool(result["accepted"])),
                    result.get("reject_reason"),
                    json.dumps(_json_safe(result.get("features", {})), sort_keys=True,
                               separators=(",", ":"), allow_nan=False),
                    json.dumps(_json_safe(result.get("config", {})), sort_keys=True,
                               separators=(",", ":"), allow_nan=False),
                    created_at,
                ),
            )
            inserted += max(int(cursor.rowcount or 0), 0)
            await _advance_and_open(db, {
                **result, "trading_date": trading_date, "ticker": ticker,
                "bar_ts": bar_ts, "variant": variant,
            }, created_at)
        await db.commit()
    return inserted


async def momentum_shadow_comparison(db_path: str) -> dict:
    """Funnel and realised virtual-paper outcomes without invented metrics."""
    await init_momentum_shadow_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        totals = await (await db.execute("""
            SELECT variant,
                   COUNT(*) AS evaluations,
                   SUM(accepted) AS accepts,
                   COUNT(DISTINCT CASE WHEN accepted=1
                       THEN trading_date || '|' || ticker END) AS distinct_candidates
            FROM momentum_shadow_evaluations
            GROUP BY variant ORDER BY variant
        """)).fetchall()
        total_by_variant = {row[0]: row[1:] for row in totals}
        rows = []
        for variant in VARIANTS:
            evaluations, accepts, distinct_candidates = total_by_variant.get(
                variant, (0, 0, 0)
            )
            rejects = await (await db.execute("""
                SELECT reject_reason, COUNT(*) AS n
                FROM momentum_shadow_evaluations
                WHERE variant=? AND accepted=0
                GROUP BY reject_reason ORDER BY n DESC, reject_reason LIMIT 5
            """, (variant,))).fetchall()
            trades = await (await db.execute("""
                SELECT COUNT(*) AS entries,
                       SUM(CASE WHEN c.bar_ts IS NULL THEN 1 ELSE 0 END) AS open_count,
                       COUNT(c.bar_ts) AS closed_count
                FROM momentum_shadow_trades t
                LEFT JOIN momentum_shadow_trade_events c
                  ON c.trading_date=t.trading_date AND c.ticker=t.ticker
                 AND c.variant=t.variant AND c.event_type='CLOSED'
                WHERE t.variant=?
            """, (variant,))).fetchone()
            entries, open_count, closed_count = (int(value or 0) for value in trades)
            closes = await (await db.execute("""
                SELECT e.gross_pnl,e.costs,e.net_pnl,e.r_multiple
                FROM momentum_shadow_trade_events e
                WHERE e.variant=? AND e.event_type='CLOSED'
                ORDER BY e.bar_ts,e.trading_date,e.ticker
            """, (variant,))).fetchall()
            outcome = {
                "paper_entries": entries,
                "open_trades": open_count,
                "closed_trades": closed_count,
                "gross_pnl": None,
                "costs": None,
                "net_pnl": None,
                "net_expectancy": None,
                "profit_factor": None,
                "wins": None,
                "losses": None,
                "breakevens": None,
                "win_rate": None,
                "avg_r": None,
                "max_drawdown": None,
                "current_drawdown": None,
            }
            warnings = [
                "Virtual paper outcomes use declared slippage/cost assumptions; they are not broker fills.",
                "The virtual book exits the full quantity at target 1; live partial exits, runners, and trailing stops are not modelled.",
                "Time exits require a later already-fetched bar at or after 15:15; unresolved entries remain open.",
            ]
            if closes:
                gross_values = [float(row[0]) for row in closes]
                cost_values = [float(row[1]) for row in closes]
                net_values = [float(row[2]) for row in closes]
                r_values = [float(row[3]) for row in closes]
                wins = sum(value > 0 for value in net_values)
                losses = sum(value < 0 for value in net_values)
                breakevens = sum(value == 0 for value in net_values)
                directional = wins + losses
                positive = sum(value for value in net_values if value > 0)
                negative = abs(sum(value for value in net_values if value < 0))
                equity = peak = 0.0
                max_drawdown = 0.0
                for value in net_values:
                    equity += value
                    peak = max(peak, equity)
                    max_drawdown = max(max_drawdown, peak - equity)
                outcome.update({
                    "gross_pnl": round(sum(gross_values), 6),
                    "costs": round(sum(cost_values), 6),
                    "net_pnl": round(sum(net_values), 6),
                    "net_expectancy": round(sum(net_values) / len(net_values), 6),
                    "profit_factor": round(positive / negative, 6) if negative else None,
                    "wins": wins,
                    "losses": losses,
                    "breakevens": breakevens,
                    "win_rate": round(wins / directional, 6) if directional else None,
                    "avg_r": round(sum(r_values) / len(r_values), 6),
                    "max_drawdown": round(max_drawdown, 6),
                    "current_drawdown": round(peak - equity, 6),
                })
                if not negative:
                    warnings.append("Profit factor is unavailable until a losing virtual trade closes.")
                if not directional:
                    warnings.append("Win rate excludes breakevens and is unavailable without a win or loss.")
            else:
                warnings.append("No virtual trades have closed; realised outcome metrics are unavailable.")
            if open_count:
                warnings.append(f"{open_count} virtual trade(s) remain unresolved from available bars.")
            rows.append({
                "variant": variant,
                "evaluations": int(evaluations),
                "accepts": int(accepts or 0),
                "distinct_candidates": int(distinct_candidates or 0),
                "accept_rate": round(float(accepts or 0) / evaluations, 6)
                if evaluations else None,
                "top_rejects": [
                    {"reason": reason, "count": int(count)}
                    for reason, count in rejects
                ],
                **outcome,
                "warnings": warnings,
            })
    return {"execution": momentum_shadow_execution_config(), "variants": rows}
