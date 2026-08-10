"""Broker-free paper-shadow experiments for the classic Penny MIS breakout."""
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

from penny_engine_breakout import evaluate_breakout_entry
VIRTUAL_QUANTITY = 1
VIRTUAL_SIZING_BASIS = "ONE_SHARE_FIXED"
VIRTUAL_TIME_EXIT_MINUTE = 15 * 60
COST_MODEL_VERSION = "PENNY_ZERODHA_EQUITY_MIS_V1"


@dataclass(frozen=True)
class PennyShadowVariant:
    name: str
    time_start_min: int | None
    volume_multiplier: float | None


_VARIANT_ROWS = (
    PennyShadowVariant("PEN_BASE", None, None),
    PennyShadowVariant("PEN_WINDOW", 10 * 60, None),
    PennyShadowVariant("PEN_VOLUME", None, 1.50),
)
VARIANTS: Mapping[str, PennyShadowVariant] = MappingProxyType({
    variant.name: variant for variant in _VARIANT_ROWS
})


def _json_safe(value):
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
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _ticker(value) -> str:
    ticker = str(value).strip().upper()
    if not ticker:
        raise ValueError("ticker must not be empty")
    return ticker


def _identity(trading_date, bar_ts) -> tuple[str, str]:
    day_text = trading_date.isoformat() if hasattr(trading_date, "isoformat") else str(trading_date)
    bar_text = bar_ts.isoformat() if hasattr(bar_ts, "isoformat") else str(bar_ts)
    try:
        parsed_day = date.fromisoformat(day_text)
        datetime.fromisoformat(bar_text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("trading_date and bar_ts must be valid ISO values") from exc
    if parsed_day.isoformat() != day_text or len(bar_text) < 16:
        raise ValueError("trading_date must be ISO YYYY-MM-DD and bar_ts a timestamp")
    return day_text, bar_text


def _selected(names: Sequence[str] | None) -> tuple[PennyShadowVariant, ...]:
    selected = tuple(names) if names is not None else tuple(VARIANTS)
    if not selected or len(set(selected)) != len(selected):
        raise ValueError("Penny shadow variants must be non-empty and unique")
    unknown = [name for name in selected if name not in VARIANTS]
    if unknown:
        raise ValueError(f"unknown Penny shadow variant(s): {', '.join(unknown)}")
    return tuple(VARIANTS[name] for name in selected)


def _fingerprint(intraday, evidence: dict) -> str:
    digest = hashlib.sha256()
    digest.update(json.dumps(
        _json_safe(evidence), sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8"))
    if isinstance(intraday, pd.DataFrame):
        digest.update(pd.util.hash_pandas_object(intraday, index=True).values.tobytes())
    return digest.hexdigest()


def _execution_snapshot(origin: str = "ENTRY") -> dict:
    from cost_schedules import equity_intraday_cost_snapshot
    schedule = equity_intraday_cost_snapshot(namespace="PENNY")
    active = schedule["rates"]
    return {
        "model": COST_MODEL_VERSION,
        "origin": origin,
        "schedule_version": schedule["schedule_version"],
        "effective_date": schedule["effective_date"],
        "verified_as_of": schedule["verified_as_of"],
        "market": schedule["market"],
        "is_intraday": True,
        "brokerage_bypass_honored": False,
        "rates": {
            "brokerage_pct": active["brokerage_pct"],
            "brokerage_max": active["brokerage_max"],
            "stt_mis": active["stt_sell_pct"],
            "exchange_pct": active["exchange_pct"],
            "stamp_duty_pct": active["stamp_duty_buy_pct"],
            "sebi_pct": active["sebi_pct"],
            "ipft_pct": active["ipft_pct"],
            "gst_pct": active["gst_pct"],
        },
    }


def _costs_from_snapshot(entry: float, exit_price: float, quantity: int, snapshot: dict) -> float:
    if snapshot.get("model") != COST_MODEL_VERSION or snapshot.get("is_intraday") is not True:
        raise ValueError("unsupported virtual execution cost snapshot")
    rates = snapshot.get("rates") or {}
    required = (
        "brokerage_pct", "brokerage_max", "stt_mis", "exchange_pct",
        "stamp_duty_pct", "sebi_pct", "gst_pct",
    )
    values = {}
    for key in required:
        value = float(rates.get(key))
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"invalid frozen execution rate: {key}")
        values[key] = value
    buy_value = entry * quantity
    sell_value = exit_price * quantity
    exchange = (buy_value + sell_value) * values["exchange_pct"]
    ipft = (buy_value + sell_value) * float(rates.get("ipft_pct", 0.0))
    brokerage_buy = min(buy_value * values["brokerage_pct"], values["brokerage_max"])
    brokerage_sell = min(sell_value * values["brokerage_pct"], values["brokerage_max"])
    taxable = brokerage_buy + brokerage_sell + exchange
    # Old stored V1 snapshots predate explicit schedule metadata and must keep
    # their exact historical arithmetic. New schedules include SEBI/IPFT in GST.
    if snapshot.get("schedule_version"):
        taxable += (buy_value + sell_value) * values["sebi_pct"] + ipft
    costs = (
        brokerage_buy + brokerage_sell + sell_value * values["stt_mis"] + exchange
        + buy_value * values["stamp_duty_pct"]
        + (buy_value + sell_value) * values["sebi_pct"]
        + ipft + taxable * values["gst_pct"]
    )
    return round(costs, 4)


def evaluate_penny_shadows(
    *,
    ticker: str,
    cum_vol_today: int,
    median_vol_20d: int,
    breakout_bar: dict,
    day_high: float,
    rsi_14: float,
    as_of: datetime,
    risk_engine,
    intraday=None,
    regime=None,
    variants: Sequence[str] | None = None,
    trading_date: date | str | None = None,
    bar_ts: datetime | str | None = None,
) -> list[dict]:
    """Evaluate declared variants against one immutable prepared scan snapshot."""
    from config import settings

    ticker = _ticker(ticker)
    if trading_date is None:
        trading_date = as_of.date()
    if bar_ts is None:
        if intraday is None or len(intraday) == 0:
            raise ValueError("bar_ts is required without an intraday frame")
        bar_ts = intraday.index[-1]
    day_text, bar_text = _identity(trading_date, bar_ts)
    base_evidence = {
        "cum_vol_today": int(cum_vol_today),
        "median_vol_20d": int(median_vol_20d),
        "bar_close": breakout_bar.get("close"),
        "bar_high": breakout_bar.get("high"),
        "bar_low": breakout_bar.get("low"),
        "bar_volume": breakout_bar.get("volume"),
        "breakout_anchor": day_high,
        "rsi_14": rsi_14,
        "evaluation_minute": as_of.hour * 60 + as_of.minute,
    }
    fingerprint = _fingerprint(intraday, base_evidence)
    rows = []
    for variant in _selected(variants):
        decision = evaluate_breakout_entry(
            ticker=ticker,
            cum_vol_today=cum_vol_today,
            median_vol_20d=median_vol_20d,
            breakout_bar=breakout_bar,
            day_high=day_high,
            rsi_14=rsi_14,
            as_of=as_of,
            risk_engine=risk_engine,
            intraday=intraday,
            regime=regime,
            time_start_min=variant.time_start_min,
            volume_multiplier=variant.volume_multiplier,
        )
        config = {
            **asdict(variant),
            "effective_time_start_min": (
                settings.PENNY_BREAKOUT_TIME_START
                if variant.time_start_min is None else variant.time_start_min
            ),
            "time_end_min": settings.PENNY_BREAKOUT_TIME_END,
            "effective_volume_multiplier": (
                settings.PENNY_BREAKOUT_VOL_MULT
                if variant.volume_multiplier is None else variant.volume_multiplier
            ),
            "rvol_time_adjusted": settings.PENNY_BREAKOUT_RVOL_TIME_ADJUSTED,
            "breakout_buffer_pct": settings.PENNY_BREAKOUT_BUFFER_PCT,
            "rsi_max": settings.PENNY_BREAKOUT_RSI_MAX,
            "regime": getattr(regime, "value", regime),
        }
        accepted = bool(decision and decision.get("accept"))
        rows.append({
            "trading_date": day_text,
            "ticker": ticker,
            "bar_ts": bar_text,
            "variant": variant.name,
            "accepted": accepted,
            "reject_reason": None if accepted else (
                decision.get("reject_reason", "evaluator returned no decision")
                if decision else "evaluator returned no decision"
            ),
            "features": base_evidence,
            "config": config,
            "dataset_fingerprint": fingerprint,
            "decision": decision,
            # Ephemeral and deliberately excluded from persisted evaluation JSON.
            # Persistence uses this already-fetched frame to advance the virtual
            # book; the shadow layer never asks the broker for more data.
            "_intraday_frame": intraday,
        })
    return rows


async def init_penny_shadow_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS penny_shadow_evaluations (
                trading_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                bar_ts TEXT NOT NULL,
                variant TEXT NOT NULL,
                accepted INTEGER NOT NULL CHECK (accepted IN (0,1)),
                reject_reason TEXT,
                dataset_fingerprint TEXT NOT NULL,
                features_json TEXT NOT NULL,
                config_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (trading_date, ticker, bar_ts, variant)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS penny_shadow_virtual_trades (
                variant TEXT NOT NULL,
                trading_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                entry_bar_ts TEXT NOT NULL,
                entry_price REAL NOT NULL CHECK (entry_price > 0),
                stop_price REAL NOT NULL CHECK (stop_price > 0),
                target_price REAL NOT NULL CHECK (target_price > 0),
                quantity INTEGER NOT NULL CHECK (quantity = 1),
                initial_risk REAL NOT NULL CHECK (initial_risk > 0),
                sizing_basis TEXT NOT NULL CHECK (sizing_basis = 'ONE_SHARE_FIXED'),
                dataset_fingerprint TEXT NOT NULL,
                config_json TEXT NOT NULL,
                execution_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('OPEN','CLOSED')),
                last_bar_ts TEXT NOT NULL,
                exit_bar_ts TEXT,
                exit_price REAL,
                gross_pnl REAL,
                costs REAL,
                net_pnl REAL,
                r_multiple REAL,
                exit_reason TEXT,
                created_at TEXT NOT NULL,
                closed_at TEXT,
                PRIMARY KEY (variant, trading_date, ticker)
            )
        """)
        columns = {
            row[1] for row in await (await db.execute(
                "PRAGMA table_info(penny_shadow_virtual_trades)"
            )).fetchall()
        }
        if "execution_json" not in columns:
            await db.execute(
                "ALTER TABLE penny_shadow_virtual_trades ADD COLUMN execution_json TEXT"
            )
        needs_backfill = (await (await db.execute("""
            SELECT COUNT(*) FROM penny_shadow_virtual_trades
            WHERE execution_json IS NULL OR TRIM(execution_json)=''
        """)).fetchone())[0]
        if needs_backfill:
            # A previous tranche may already have installed the closed-row
            # guard. Temporarily remove it inside this schema transaction solely
            # to freeze a migration-time basis for pre-snapshot legacy rows.
            await db.execute("DROP TRIGGER IF EXISTS penny_shadow_trade_closed_immutable")
            migrated_snapshot = json.dumps(
                _execution_snapshot("MIGRATED_AT_INIT"),
                sort_keys=True, separators=(",", ":"), allow_nan=False,
            )
            await db.execute("""
                UPDATE penny_shadow_virtual_trades SET execution_json=?
                WHERE execution_json IS NULL OR TRIM(execution_json)=''
            """, (migrated_snapshot,))
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS penny_shadow_trade_no_delete
            BEFORE DELETE ON penny_shadow_virtual_trades
            BEGIN SELECT RAISE(ABORT, 'virtual trades are immutable'); END
        """)
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS penny_shadow_trade_closed_immutable
            BEFORE UPDATE ON penny_shadow_virtual_trades
            WHEN OLD.status = 'CLOSED'
            BEGIN SELECT RAISE(ABORT, 'closed virtual trades are immutable'); END
        """)
        await db.execute("DROP TRIGGER IF EXISTS penny_shadow_trade_entry_immutable")
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS penny_shadow_trade_entry_immutable
            BEFORE UPDATE ON penny_shadow_virtual_trades
            WHEN NEW.variant != OLD.variant OR NEW.trading_date != OLD.trading_date
              OR NEW.ticker != OLD.ticker OR NEW.entry_bar_ts != OLD.entry_bar_ts
              OR NEW.entry_price != OLD.entry_price OR NEW.stop_price != OLD.stop_price
              OR NEW.target_price != OLD.target_price OR NEW.quantity != OLD.quantity
              OR NEW.initial_risk != OLD.initial_risk OR NEW.sizing_basis != OLD.sizing_basis
              OR NEW.dataset_fingerprint != OLD.dataset_fingerprint
              OR NEW.config_json != OLD.config_json OR NEW.execution_json IS NULL
              OR TRIM(NEW.execution_json)='' OR NEW.execution_json != OLD.execution_json
              OR NEW.created_at != OLD.created_at
            BEGIN SELECT RAISE(ABORT, 'virtual trade entry evidence is immutable'); END
        """)
        await db.commit()


def _finite_price(value, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite positive number") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field} must be a finite positive number")
    return number


def _frame_bars(frame, after_ts: str) -> list[tuple[str, float, float, float, float]]:
    """Return validated, chronological bars strictly after the book cursor."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return []
    after = pd.Timestamp(after_ts)
    rows = []
    for index, bar in frame.sort_index().iterrows():
        stamp = pd.Timestamp(index)
        try:
            comparable_after = after.tz_convert(stamp.tz) if after.tzinfo else after
        except TypeError:
            comparable_after = after.tz_localize(stamp.tz) if stamp.tzinfo else after.tz_localize(None)
        if stamp <= comparable_after:
            continue
        rows.append((
            stamp.isoformat(),
            _finite_price(bar.get("open"), "bar open"),
            _finite_price(bar.get("high"), "bar high"),
            _finite_price(bar.get("low"), "bar low"),
            _finite_price(bar.get("close"), "bar close"),
        ))
    return rows


def _exit_for_bar(
    bar_ts: str, open_price: float, high: float, low: float,
    stop: float, target: float,
) -> tuple[float, str] | None:
    stamp = datetime.fromisoformat(bar_ts.replace("Z", "+00:00"))
    minute = stamp.hour * 60 + stamp.minute
    # A declared 15:00 market exit occurs at the first available bar open at
    # or after 15:00. It precedes any use of that bar's later high/low.
    if minute >= VIRTUAL_TIME_EXIT_MINUTE:
        return open_price, "TIME_EXIT_1500"
    if open_price <= stop:
        return open_price, "STOP_GAP_WORSE"
    if open_price >= target:
        return target, "TARGET_GAP_CAPPED"
    stop_hit = low <= stop
    target_hit = high >= target
    if stop_hit:
        return stop, "STOP_BEFORE_TARGET_SAME_BAR" if target_hit else "STOP"
    if target_hit:
        return target, "TARGET"
    return None


async def _advance_open_trades(db, ticker: str, frame, now_text: str) -> None:
    trades = await (await db.execute("""
        SELECT variant,trading_date,entry_price,stop_price,target_price,quantity,
               initial_risk,last_bar_ts,execution_json FROM penny_shadow_virtual_trades
        WHERE ticker=? AND status='OPEN'
    """, (ticker,))).fetchall()
    for variant, trading_date, entry, stop, target, quantity, risk, cursor, execution_json in trades:
        bars = _frame_bars(frame, cursor)
        if not bars:
            continue
        last_ts = cursor
        exit_result = None
        exit_ts = None
        for bar_ts, open_price, high, low, _close in bars:
            last_ts = bar_ts
            bar_day = datetime.fromisoformat(bar_ts.replace("Z", "+00:00")).date().isoformat()
            exit_result = (
                (open_price, "MIS_OVERNIGHT_GAP_EXIT")
                if bar_day > trading_date else
                _exit_for_bar(bar_ts, open_price, high, low, stop, target)
            )
            if exit_result:
                exit_ts = bar_ts
                break
        if exit_result:
            exit_price, reason = exit_result
            gross = (exit_price - entry) * quantity
            # Shadow evidence always applies the declared real MIS cost model;
            # a paper/test brokerage-bypass setting must not inflate research.
            costs = _costs_from_snapshot(
                entry, exit_price, quantity, json.loads(execution_json),
            )
            net = gross - costs
            await db.execute("""
                UPDATE penny_shadow_virtual_trades SET
                    status='CLOSED',last_bar_ts=?,exit_bar_ts=?,exit_price=?,
                    gross_pnl=?,costs=?,net_pnl=?,r_multiple=?,exit_reason=?,closed_at=?
                WHERE variant=? AND trading_date=? AND ticker=? AND status='OPEN'
            """, (
                last_ts, exit_ts, exit_price, gross, costs, net, net / risk,
                reason, now_text, variant, trading_date, ticker,
            ))
        else:
            await db.execute("""
                UPDATE penny_shadow_virtual_trades SET last_bar_ts=?
                WHERE variant=? AND trading_date=? AND ticker=? AND status='OPEN'
            """, (last_ts, variant, trading_date, ticker))


async def _insert_virtual_trade(db, result: dict, now_text: str) -> None:
    if not bool(result.get("accepted")):
        return
    decision = result.get("decision") or {}
    # Legacy/imported evaluation rows may legitimately lack executable entry
    # evidence. Keep the candidate observation, but never fabricate a trade.
    if not all(decision.get(field) is not None for field in ("entry", "stop_loss", "target")):
        return
    entry = _finite_price(decision.get("entry"), "entry")
    stop = _finite_price(decision.get("stop_loss"), "stop")
    target = _finite_price(decision.get("target"), "target")
    if not stop < entry < target:
        raise ValueError("accepted virtual trade requires stop < entry < target")
    config = {
        **dict(result.get("config") or {}),
        "virtual_sizing_basis": VIRTUAL_SIZING_BASIS,
        "virtual_quantity": VIRTUAL_QUANTITY,
        "time_exit_minute": VIRTUAL_TIME_EXIT_MINUTE,
        "same_bar_rule": "STOP_BEFORE_TARGET",
        "entry_fill_rule": "MARKETABLE_BUY_LIMIT_FILLED_AT_LIMIT_ON_SIGNAL_CLOSE",
        "cost_model": "ZERODHA_EQUITY_MIS_DECLARED_RATES",
        "brokerage_bypass_honored": False,
    }
    execution = _execution_snapshot()
    await db.execute("""
        INSERT OR IGNORE INTO penny_shadow_virtual_trades
            (variant,trading_date,ticker,entry_bar_ts,entry_price,stop_price,
             target_price,quantity,initial_risk,sizing_basis,dataset_fingerprint,
             config_json,execution_json,status,last_bar_ts,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        result["variant"], result["trading_date"], result["ticker"], result["bar_ts"],
        entry, stop, target, VIRTUAL_QUANTITY, entry - stop, VIRTUAL_SIZING_BASIS,
        result["dataset_fingerprint"],
        json.dumps(_json_safe(config), sort_keys=True, separators=(",", ":"), allow_nan=False),
        json.dumps(execution, sort_keys=True, separators=(",", ":"), allow_nan=False),
        "OPEN", result["bar_ts"], now_text,
    ))


async def persist_penny_shadow_results(db_path: str, results: Iterable[dict]) -> int:
    await init_penny_shadow_db(db_path)
    results = list(results)
    inserted = 0
    created_at = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(db_path) as db:
        normalized = []
        frames = {}
        for result in results:
            variant = str(result.get("variant", ""))
            if variant not in VARIANTS:
                raise ValueError(f"unregistered Penny shadow variant: {variant!r}")
            ticker = _ticker(result.get("ticker", ""))
            trading_date, bar_ts = _identity(
                result.get("trading_date"), result.get("bar_ts")
            )
            fingerprint = str(result.get("dataset_fingerprint", "")).strip()
            if not fingerprint:
                raise ValueError("dataset_fingerprint must not be empty")
            clean = dict(result)
            clean.update({
                "variant": variant, "ticker": ticker, "trading_date": trading_date,
                "bar_ts": bar_ts, "dataset_fingerprint": fingerprint,
            })
            normalized.append(clean)
            frame = result.get("_intraday_frame")
            if isinstance(frame, pd.DataFrame):
                frames[ticker] = frame

        # Advance pre-existing positions before creating today's new accepted
        # entries, so the signal bar can never close its own trade by hindsight.
        for ticker, frame in frames.items():
            await _advance_open_trades(db, ticker, frame, created_at)

        for result in normalized:
            variant = result["variant"]
            ticker = result["ticker"]
            trading_date = result["trading_date"]
            bar_ts = result["bar_ts"]
            fingerprint = result["dataset_fingerprint"]
            cursor = await db.execute("""
                INSERT OR IGNORE INTO penny_shadow_evaluations
                    (trading_date,ticker,bar_ts,variant,accepted,reject_reason,
                     dataset_fingerprint,features_json,config_json,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                trading_date, ticker, bar_ts, variant,
                int(bool(result["accepted"])), result.get("reject_reason"),
                fingerprint,
                json.dumps(_json_safe(result.get("features", {})), sort_keys=True,
                           separators=(",", ":"), allow_nan=False),
                json.dumps(_json_safe(result.get("config", {})), sort_keys=True,
                           separators=(",", ":"), allow_nan=False),
                created_at,
            ))
            inserted += max(int(cursor.rowcount or 0), 0)
            await _insert_virtual_trade(db, result, created_at)
        await db.commit()
    return inserted


async def penny_shadow_comparison(db_path: str) -> dict:
    """Compare raw scans with deduplicated ticker/day opportunities honestly."""
    await init_penny_shadow_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        totals = {
            row[0]: row[1:]
            for row in await (await db.execute("""
                SELECT variant, COUNT(*), SUM(accepted),
                       COUNT(DISTINCT CASE WHEN accepted=1
                           THEN trading_date || '|' || ticker END)
                FROM penny_shadow_evaluations GROUP BY variant
            """)).fetchall()
        }
        rows = []
        for name in VARIANTS:
            evaluations, raw_accepts, distinct_candidates = totals.get(name, (0, 0, 0))
            rejects = await (await db.execute("""
                SELECT reject_reason, COUNT(*) FROM penny_shadow_evaluations
                WHERE variant=? AND accepted=0
                GROUP BY reject_reason ORDER BY COUNT(*) DESC, reject_reason LIMIT 5
            """, (name,))).fetchall()
            evaluations = int(evaluations or 0)
            raw_accepts = int(raw_accepts or 0)
            distinct_candidates = int(distinct_candidates or 0)
            trade_totals = await (await db.execute("""
                SELECT COUNT(*),
                       SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN status='CLOSED' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN status='CLOSED' THEN net_pnl END),
                       AVG(CASE WHEN status='CLOSED' THEN net_pnl END),
                       SUM(CASE WHEN status='CLOSED' AND net_pnl>0 THEN net_pnl ELSE 0 END),
                       SUM(CASE WHEN status='CLOSED' AND net_pnl<0 THEN -net_pnl ELSE 0 END),
                       SUM(CASE WHEN status='CLOSED' AND net_pnl>0 THEN 1 ELSE 0 END),
                       SUM(CASE WHEN status='CLOSED' AND net_pnl<0 THEN 1 ELSE 0 END),
                       SUM(CASE WHEN status='CLOSED' AND net_pnl=0 THEN 1 ELSE 0 END),
                       AVG(CASE WHEN status='CLOSED' THEN r_multiple END)
                FROM penny_shadow_virtual_trades WHERE variant=?
            """, (name,))).fetchone()
            (entries, open_count, closed_count, net_pnl, expectancy, winning_pnl,
             losing_pnl, win_count, loss_count, breakeven_count, avg_r) = trade_totals
            entries = int(entries or 0)
            open_count = int(open_count or 0)
            closed_count = int(closed_count or 0)
            closed_rows = await (await db.execute("""
                SELECT net_pnl FROM penny_shadow_virtual_trades
                WHERE variant=? AND status='CLOSED'
                ORDER BY exit_bar_ts, trading_date, ticker
            """, (name,))).fetchall()
            running = peak = max_drawdown = 0.0
            for (pnl,) in closed_rows:
                running += float(pnl)
                peak = max(peak, running)
                max_drawdown = max(max_drawdown, peak - running)
            snapshot_rows = await (await db.execute("""
                SELECT execution_json, COUNT(*) FROM penny_shadow_virtual_trades
                WHERE variant=? GROUP BY execution_json ORDER BY execution_json
            """, (name,))).fetchall()
            rows.append({
                "variant": name,
                "evaluations": evaluations,
                "raw_accepts": raw_accepts,
                "distinct_candidates": distinct_candidates,
                "repeat_accepts": max(raw_accepts - distinct_candidates, 0),
                "accept_rate": round(raw_accepts / evaluations, 6) if evaluations else None,
                "top_rejects": [
                    {"reason": reason, "count": int(count)} for reason, count in rejects
                ],
                "paper_entries": entries if evaluations else None,
                "fills": entries if evaluations else None,
                "open_trades": open_count if evaluations else None,
                "closed_trades": closed_count if evaluations else None,
                "winning_trades": int(win_count or 0) if closed_count else None,
                "losing_trades": int(loss_count or 0) if closed_count else None,
                "breakeven_trades": int(breakeven_count or 0) if closed_count else None,
                "win_rate": (
                    round(int(win_count or 0) / closed_count, 6) if closed_count else None
                ),
                "avg_r": round(float(avg_r), 6) if closed_count and avg_r is not None else None,
                "net_pnl": round(float(net_pnl), 4) if closed_count else None,
                "expectancy": round(float(expectancy), 4) if closed_count else None,
                "profit_factor": (
                    round(float(winning_pnl) / float(losing_pnl), 6)
                    if closed_count and float(losing_pnl or 0) > 0 else None
                ),
                "max_drawdown": round(max_drawdown, 4) if closed_count else None,
                "max_drawdown_pct": None,
                "execution_basis": "FROZEN_AT_VIRTUAL_ENTRY",
                "execution_snapshots": [
                    {"snapshot": json.loads(snapshot), "trade_count": int(count)}
                    for snapshot, count in snapshot_rows
                ],
                "warnings": [
                    "Virtual paper outcomes use one fixed share, never broker orders or live sizing.",
                    "Net outcomes apply declared Zerodha equity MIS costs; fills are bar-based simulations.",
                    "Accepted marketable buy limits are conservatively filled at their limit price; queue and order-book effects are unavailable.",
                    "Drawdown is rupee peak-to-trough for one-share outcomes; no bankroll percentage is inferred.",
                ],
            })
    return {"variants": rows}
