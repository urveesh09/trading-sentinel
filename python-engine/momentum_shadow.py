"""Broker-free paper-shadow evaluation for declared Momentum variants.

This module deliberately imports only the pure strategy evaluator plus storage
and serialization libraries. It has no Kite, executor, order, or scheduler
dependency. Evaluation and persistence are separate operations so callers can
test the same immutable frames before choosing where to record the evidence.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
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
from momentum_rs_pullback import rs_index_known, rs_pullback_rules, rs_pullback_signal
from momentum_selective import selective_gate


@dataclass(frozen=True)
class MomentumShadowVariant:
    name: str
    crossover_lookback: int
    max_vwap_distance_atr: float | None
    # Round-3 MOM_SELECTIVE context gate (momentum_selective.py) on top of the
    # shipped evaluator: forward paper evidence for the untested candidate.
    selective: bool = False
    # [O19-M2] Its own entry rule (momentum_rs_pullback.py) instead of the
    # shipped crossover evaluator; shipped stop/target/size rules.
    rs_pullback: bool = False


_VARIANT_ROWS = (
    MomentumShadowVariant("MOM_BASE", 3, None),
    MomentumShadowVariant("MOM_RECENCY_5", 5, 0.50),
    MomentumShadowVariant("MOM_SELECTIVE", 3, None, selective=True),
    MomentumShadowVariant("MOM_RS_PULLBACK", 3, None, rs_pullback=True),
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
    # [O26d] A closing-auction stock's 15:15 time exit, valued at its 15:00 bar's close (modelled, not a fill),
    # only with dated evidence (``cas_time_exit_evidence``). Versioned: a replay applies it only to an execution
    # that declares it.
    cas_time_exit: str = "cas_phase1_last_continuous_close_v1"


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


def _frame_fingerprint(ticker: str, df: pd.DataFrame, config: dict,
                       extra_frames: Sequence[tuple[str, pd.DataFrame | None]] = ()) -> str:
    """Identity of one decision's inputs. ``extra_frames`` binds other data
    the rule read (index bars, daily bars); none keeps older identities."""
    digest = hashlib.sha256()
    digest.update(ticker.encode("utf-8"))
    digest.update(json.dumps(
        _json_safe(config), sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8"))
    digest.update(pd.util.hash_pandas_object(df, index=True).values.tobytes())
    for name, frame in extra_frames:
        digest.update(f"|{name}:".encode("utf-8"))
        if frame is None or frame.empty:
            digest.update(b"none")
        else:
            digest.update(pd.util.hash_pandas_object(frame, index=True).values.tobytes())
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
    index_today: pd.DataFrame | None = None,
) -> list[dict]:
    """Purely evaluate named variants against the exact same input frames.

    ``index_today`` holds NIFTY 50 bars for the session; selective variants
    fail closed without it.
    """
    ticker = _ticker(ticker)
    day_text, bar_text = _identity(df, trading_date, bar_ts)
    results = []
    for variant in _selected_variants(variants):
        if variant.rs_pullback:
            accepted, decision = rs_pullback_signal(
                df, index_today, momentum_pool=momentum_pool, df_daily=df_daily,
                regime=regime, market_regime=market_regime,
            )
        else:
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
        variant_config = asdict(variant)
        if not variant.rs_pullback:
            # Keeps pre-existing variant configs (and fingerprints) unchanged.
            variant_config.pop("rs_pullback")
        if variant.selective:
            if accepted:
                accepted, reason, evidence = _selective_decision(df, index_today, prev_day_high)
                decision = {**decision, "selective": evidence}
                if not accepted:
                    decision["reject_reason"] = f"selective_{reason}"
        else:
            # Keeps pre-existing variant configs (and fingerprints) unchanged.
            variant_config.pop("selective")
        config = {
            **variant_config,
            "min_candles": min_candles,
            "vol_surge_threshold": vol_surge_threshold,
            "market_regime": market_regime,
            "regime": getattr(regime, "name", None),
        }
        extra_frames: tuple = ()
        if variant.rs_pullback:
            # [S21-R2] The RS rule also reads the index, the daily bars (ATR
            # stop floor), its constants and the sizing pool: all of them are
            # in its identity. Older variants keep their exact fingerprints.
            config["rules"] = rs_pullback_rules()
            config["momentum_pool"] = round(float(momentum_pool), 4)
            signal_ts = df.index[-1] if isinstance(df.index, pd.DatetimeIndex) and not df.empty else None
            extra_frames = (("index_known", rs_index_known(index_today, signal_ts) if signal_ts is not None
                             else None), ("daily", df_daily))
        feature_names = (
            "close", "vwap", "volume_ratio", "intraday_high", "intraday_low",
            "daily_atr", "vwap_distance", "vwap_distance_atr",
            "crossover_lookback", "max_vwap_distance_atr",
        )
        features = {name: decision.get(name) for name in feature_names}
        # MC3 rejects before the accepted-signal payload is assembled and the
        # evaluator calls its measured value ``vol_ratio`` on that path.  Keep
        # the persisted shadow schema stable as ``volume_ratio`` while retaining
        # the evidence that explains how close the candidate was to the gate.
        if features["volume_ratio"] is None:
            features["volume_ratio"] = decision.get("vol_ratio")
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
            "dataset_fingerprint": _frame_fingerprint(ticker, df, config, extra_frames),
            # Transient lifecycle evidence. Persistence stores observations as
            # immutable events, not this duplicated frame blob.
            "bars": _bars(df),
        })
    return results


def _selective_decision(df: pd.DataFrame, index_today: pd.DataFrame | None,
                        prev_day_high: float) -> tuple[bool, str | None, dict]:
    if index_today is None or index_today.empty or df.empty:
        return False, "index_bar_unavailable", {}
    session = df.index[-1].date() if isinstance(df.index, pd.DatetimeIndex) else None
    if session is None or not isinstance(index_today.index, pd.DatetimeIndex):
        return False, "index_bar_unavailable", {}
    stock_today = df[df.index.date == session]
    return selective_gate(stock_today, index_today[index_today.index.date == session], prev_day_high)


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
        # [S21-R1] One receipt per virtual trade from the after-close terminal
        # pass: CLOSED, or CENSORED with why (no bar, fetch failed).
        await db.execute("""
            CREATE TABLE IF NOT EXISTS momentum_shadow_terminal_receipts (
                trading_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                variant TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('CLOSED','CENSORED')),
                detail TEXT NOT NULL,
                terminal_bar_ts TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY (trading_date,ticker,variant)
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


def _saved_execution(trade) -> dict:
    """[O26e] The execution saved with a trade when it opened ({} when unreadable)."""
    try:
        saved = json.loads(trade["execution_json"])
    except (KeyError, IndexError, TypeError, ValueError):
        return {}
    return saved if isinstance(saved, dict) else {}


def _time_exit_of(execution: dict | None) -> tuple[int, int]:
    """[O26e] A saved execution's declared time exit (the published one for a record without it)."""
    execution = execution or {}
    return (int(execution.get("time_exit_hour", EXECUTION.time_exit_hour)),
            int(execution.get("time_exit_minute", EXECUTION.time_exit_minute)))


def _exit_for_bar(trade, bar: dict, *, overnight: bool = False) -> tuple[str, float] | None:
    stop, target = float(trade["stop_price"]), float(trade["target_price"])
    bar_open = float(bar["open"])
    # [O26e] The trade's own saved slippage and time exit (as its costs already are), not today's.
    saved = _saved_execution(trade)
    slip = float(saved.get("exit_slippage_bps", EXECUTION.exit_slippage_bps)) / 10000.0
    if overnight:
        return "overnight_gap_exit", bar_open * (1.0 - slip)
    parsed = datetime.fromisoformat(str(bar["bar_ts"]).replace("Z", "+00:00"))
    # Bar timestamps are starts. At/after the cutoff only the open was known
    # at the declared exit instant; inspecting this bar's extremes is hindsight.
    if (parsed.hour, parsed.minute) >= _time_exit_of(saved):
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


def _at_or_after_time_exit(bar_ts: str, exit_at: tuple[int, int] | None = None) -> bool:
    parsed = datetime.fromisoformat(str(bar_ts).replace("Z", "+00:00"))
    return (parsed.hour, parsed.minute) >= (exit_at or (EXECUTION.time_exit_hour, EXECUTION.time_exit_minute))


LAST_CONTINUOUS = "time_exit_last_continuous"     # [O26c] the receipt detail of a derived 15:15 price
CAS_ELIGIBLE = "ELIGIBLE"


def cas_time_exit_evidence(ticker: str, trading_date: str, *, archive_root: str | None = None,
                           execution: dict | None = None) -> str:
    """[O26d] Whether a session with no 15:15 bar is explained by NSE's closing auction (independent review R3:
    any missing candle had become a synthetic exit). ELIGIBLE only when all hold:
      * the execution declares the model (``cas_time_exit``; older executions did not);
      * the session is one on which CAS stocks' continuous trading ended at 15:15
        (``market_calendar.cas_phase1_in_force``: 2026-08-03 to before 2026-12-07);
      * the ticker had stock futures in the NFO contract master archived that day (dated, not today's list).
    Otherwise NO_MODEL, NOT_IN_FORCE, NO_DATED_MASTER or NOT_LISTED: the trade stays censored.
    [O26e] ``execution`` is the trade's own saved one; the model is defined only for a declared 15:15 exit."""
    from market_calendar import CAS_OPEN_TIME, cas_phase1_in_force
    execution = execution if execution is not None else asdict(EXECUTION)
    if (execution.get("cas_time_exit") != EXECUTION.cas_time_exit
            or _time_exit_of(execution) != (CAS_OPEN_TIME.hour, CAS_OPEN_TIME.minute)):
        return "NO_MODEL"
    try:
        day = date.fromisoformat(str(trading_date)[:10])
    except ValueError:
        return "NOT_IN_FORCE"
    if not cas_phase1_in_force(day):
        return "NOT_IN_FORCE"
    from research_archive import contract_master_underlyings
    names = contract_master_underlyings(archive_root or settings.RESEARCH_ARCHIVE_PATH, provider="KITE",
                                        segment="NFO", day=day.isoformat())
    if names is None:
        return "NO_DATED_MASTER"
    return CAS_ELIGIBLE if str(ticker).strip().upper() in names else "NOT_LISTED"


def _last_continuous_at_time_exit(bars: list[dict], exit_at: tuple[int, int] | None = None) -> dict | None:
    """[O26c] For a stock in NSE's closing auction continuous trading ends at
    15:15, so the session has no 15:15 bar and the declared 15:15 exit never
    got one (Oct 26: 22 of 75 RS_PULLBACK trades, every one an F&O stock,
    censored; only the others were ever scored). The price at 15:15 is then
    the close of the bar just before it (15:00-15:15): returned as the 15:15
    bar, its open that close, marked ``modelled`` (a price, not a fill). None
    when the latest bar is not the 15:00 one (nothing is invented). [O26d] The
    caller first needs ``cas_time_exit_evidence`` ELIGIBLE."""
    if not bars:
        return None
    last = max(bars, key=lambda bar: datetime.fromisoformat(str(bar["bar_ts"]).replace("Z", "+00:00")))
    parsed = datetime.fromisoformat(str(last["bar_ts"]).replace("Z", "+00:00"))
    due = parsed + timedelta(minutes=15)
    if (due.hour, due.minute) != (exit_at or (EXECUTION.time_exit_hour, EXECUTION.time_exit_minute)):
        return None
    price = last["close"]
    return {"bar_ts": due.isoformat(), "open": price, "high": price, "low": price, "close": price,
            "modelled": EXECUTION.cas_time_exit}


async def _terminal_bars(ticker: str, trading_date: str, bars: list[dict], execution: dict) -> tuple:
    """[O26e] One trade's bars for the terminal pass, under its own saved execution (the O26d recheck's F1: one
    ticker-wide decision under today's model had closed a legacy trade by a model it never declared): up to its
    declared time exit; without a bar there, the derived 15:15 bar only when that execution declares the model and
    the dated evidence holds. Returns (bars, terminal, derived, evidence)."""
    exit_at = _time_exit_of(execution)
    terminal = next((bar for bar in bars if _at_or_after_time_exit(bar["bar_ts"], exit_at)), None)
    if terminal is not None:
        return bars[:bars.index(terminal) + 1], terminal, None, None
    derived = _last_continuous_at_time_exit(bars, exit_at)
    if derived is None:
        return bars, None, None, None
    try:
        evidence = await asyncio.to_thread(cas_time_exit_evidence, ticker, trading_date, execution=execution)
    except Exception:                 # unreadable evidence is missing evidence: censored, its receipt says so
        evidence = "EVIDENCE_ERROR"
    if evidence != CAS_ELIGIBLE:
        return bars, None, None, evidence
    return bars + [derived], derived, derived, evidence


async def resolve_momentum_shadow_day(db_path: str, trading_date: str, fetch_bars) -> dict:
    """[S21-R1] After the close, give each still-open virtual trade of the day
    the bars the scans never passed it.

    Scans run 10:15-14:45, so the newest completed bar a virtual trade sees is
    the 14:30 one and the declared 15:15 time exit never arrives (Oct 21: 9 of
    13 MOM_RS_PULLBACK trades unresolved). ``fetch_bars(ticker)`` returns that
    session's completed 15-minute bars; run it after 15:30 so the 15:15 bar
    is complete (only its open is used, as at 15:15). Bars after the 15:15
    bar are not passed. The usual stop/target/time-exit rules decide each
    trade; a trade still open afterwards gets a CENSORED receipt saying why.
    Nothing is invented: a missing bar or a failed fetch stays censored.
    [O26c] A closing-auction stock has no 15:15 bar: its 15:15 price is the
    15:00 bar's close (``_last_continuous_at_time_exit``), receipt detail
    LAST_CONTINUOUS. [O26d] Only with dated evidence that it was one that day
    (``cas_time_exit_evidence``); otherwise the trade stays censored, its
    detail saying which evidence was missing. Bars are taken in time order.
    [O26e] Each trade is judged under its own saved execution
    (``_terminal_bars``): its time exit, and the model only if it declared it.

    [A22-M2] Each ticker's bars are fetched with no database connection
    open, then applied in one short transaction for that ticker: a slow
    history read never holds the write lock other writers need. A rerun
    re-selects only trades still without a CLOSED event, so a pass cut
    short half-way resumes where it stopped.
    """
    await init_momentum_shadow_db(db_path)
    created_at = datetime.now(timezone.utc).isoformat()
    summary = {"open": 0, "closed": 0, "censored": 0, "tickers": 0}
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute("""
            SELECT t.ticker, t.variant, t.execution_json FROM momentum_shadow_trades t
            WHERE t.trading_date=? AND NOT EXISTS (
                SELECT 1 FROM momentum_shadow_trade_events e
                WHERE e.trading_date=t.trading_date AND e.ticker=t.ticker
                  AND e.variant=t.variant AND e.event_type='CLOSED')
            ORDER BY t.ticker, t.variant
        """, (trading_date,))).fetchall()
    by_ticker: dict = {}
    for row in rows:
        by_ticker.setdefault(row["ticker"], []).append((row["variant"], _saved_execution(row)))
    summary.update(open=len(rows), tickers=len(by_ticker))
    for ticker, trades in by_ticker.items():
        error, day_bars = None, []
        try:
            frame = await fetch_bars(ticker)
            day_bars = sorted((bar for bar in _bars(frame if frame is not None else pd.DataFrame())
                               if bar["bar_ts"][:10] == trading_date),
                              key=lambda bar: datetime.fromisoformat(bar["bar_ts"].replace("Z", "+00:00")))
        except Exception as exc:     # a failed fetch is a censored outcome, not a crash
            error = type(exc).__name__
        plans = {variant: ([], None, None, None) if error else
                 await _terminal_bars(ticker, trading_date, day_bars, execution)
                 for variant, execution in trades}
        async with aiosqlite.connect(db_path) as db:
            for variant, _execution in trades:
                bars, terminal, derived, evidence = plans[variant]
                await _advance_and_open(db, {"trading_date": trading_date, "ticker": ticker,
                                             "variant": variant, "accepted": False, "bars": bars}, created_at)
                db.row_factory = aiosqlite.Row
                closed = await (await db.execute(
                    "SELECT reason, bar_ts FROM momentum_shadow_trade_events WHERE trading_date=? AND ticker=? "
                    "AND variant=? AND event_type='CLOSED'", (trading_date, ticker, variant))).fetchone()
                if closed is not None:
                    status, detail, bar_ts = "CLOSED", str(closed["reason"]), closed["bar_ts"]
                    if derived is not None and bar_ts == derived["bar_ts"]:
                        detail = LAST_CONTINUOUS
                    summary["closed"] += 1
                else:
                    status, bar_ts = "CENSORED", None
                    detail = (f"fetch_failed:{error}" if error else
                              (f"no_terminal_bar:cas_{evidence.lower()}" if evidence else "no_terminal_bar")
                              if terminal is None else "unresolved_after_terminal_bar")
                    summary["censored"] += 1
                await db.execute("""
                    INSERT INTO momentum_shadow_terminal_receipts
                        (trading_date,ticker,variant,status,detail,terminal_bar_ts,created_at)
                    VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(trading_date,ticker,variant) DO UPDATE SET
                        status=excluded.status, detail=excluded.detail,
                        terminal_bar_ts=excluded.terminal_bar_ts, created_at=excluded.created_at
                    WHERE momentum_shadow_terminal_receipts.status='CENSORED'
                """, (trading_date, ticker, variant, status, detail, bar_ts, created_at))
            await db.commit()
    return summary


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
            censored = (await (await db.execute("""
                SELECT COUNT(*) FROM momentum_shadow_terminal_receipts r
                WHERE r.variant=? AND r.status='CENSORED' AND NOT EXISTS (
                    SELECT 1 FROM momentum_shadow_trade_events e
                    WHERE e.trading_date=r.trading_date AND e.ticker=r.ticker
                      AND e.variant=r.variant AND e.event_type='CLOSED')
            """, (variant,))).fetchone())[0]
            closes = await (await db.execute("""
                SELECT e.gross_pnl,e.costs,e.net_pnl,e.r_multiple,e.reason
                FROM momentum_shadow_trade_events e
                WHERE e.variant=? AND e.event_type='CLOSED'
                ORDER BY e.bar_ts,e.trading_date,e.ticker
            """, (variant,))).fetchall()
            # [SX-M1 2026-10-21] A close at the next session's open means the
            # declared 15:15 exit never got its bar (before the terminal pass,
            # 72 of MOM_BASE's 92 closes on Production). It measures the
            # overnight gap, not the variant: shown apart, never scored.
            missed = [row for row in closes if row[4] == "overnight_gap_exit"]
            closes = [row for row in closes if row[4] != "overnight_gap_exit"]
            # [O26d] Closing-auction time exits valued at the 15:00 close: scored (else every F&O stock drops
            # out), and counted apart as modelled prices, not fills.
            modelled = await (await db.execute("""
                SELECT COUNT(*), SUM(e.net_pnl) FROM momentum_shadow_terminal_receipts r
                JOIN momentum_shadow_trade_events e
                  ON e.trading_date=r.trading_date AND e.ticker=r.ticker AND e.variant=r.variant
                 AND e.event_type='CLOSED'
                WHERE r.variant=? AND r.status='CLOSED' AND r.detail=?
            """, (variant, LAST_CONTINUOUS))).fetchone()
            outcome = {
                "paper_entries": entries,
                "open_trades": open_count,
                "censored_trades": int(censored or 0),
                "closed_trades": closed_count,
                "scored_closes": len(closes),
                "missed_time_exit_closes": len(missed),
                "missed_time_exit_net_pnl": round(sum(float(row[2]) for row in missed), 6) if missed else None,
                "modelled_time_exit_closes": int(modelled[0] or 0),
                "modelled_time_exit_net_pnl": round(float(modelled[1]), 6) if modelled[0] else None,
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
                "After the close a terminal pass gives each open virtual trade its remaining bars up to the "
                "15:15 open; a trade it cannot resolve is CENSORED (no bar or fetch failed), never filled.",
                "A closing-auction stock (dated F&O evidence, 2026-08-03 to 2026-12-06) has no 15:15 bar: its "
                "15:15 exit is valued at the 15:00 close, a modelled price, not a fill "
                "(modelled_time_exit_closes).",
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
            if missed:
                warnings.append(f"{len(missed)} close(s) came at the next session's open because the 15:15 exit "
                                "bar was never read; they are excluded from every outcome metric above.")
            if open_count:
                warnings.append(f"{open_count} virtual trade(s) remain unresolved from available bars"
                                + (f", {censored} of them censored by the terminal pass." if censored else "."))
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


async def momentum_shadow_near_misses(db_path: str, *, limit: int = 500) -> dict:
    """Read bounded rejected shadow evaluations without changing entry authority.

    A near miss is the evaluator's actual reject receipt, not a reconstructed
    'would have traded' signal.  This gives S7b timing research a separate,
    immutable-receipt source for distinguishing timing hypotheses from absent
    opportunities or deterministic gate failures.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 5_000:
        raise ValueError("limit must be an integer from 1 through 5000")
    await init_momentum_shadow_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute("""
            SELECT trading_date,ticker,bar_ts,variant,reject_reason,features_json,config_json
            FROM momentum_shadow_evaluations WHERE accepted=0
            ORDER BY trading_date DESC,bar_ts DESC,ticker,variant LIMIT ?
        """, (limit,))).fetchall()
    return {"schema": "momentum_shadow_near_misses_v1", "status": "COMPLETE",
            "authority": {"research_only": True, "authorization_effect": "NONE"},
            "near_misses": [{"trading_date": row[0], "ticker": row[1], "bar_ts": row[2],
                              "variant": row[3], "reject_reason": row[4],
                              "features": json.loads(row[5]), "config": json.loads(row[6])}
                             for row in rows]}
