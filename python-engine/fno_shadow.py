"""Broker-free F&O opening-range paper-shadow experiment.

The baseline delegates to the production evaluator verbatim. Variants consume
the same already-fetched futures frame and, optionally, an already-resolved
chain snapshot. This module has no executor, order, Kite, sizing, position, or
ledger dependency and cannot influence a trading decision.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
import asyncio
import json
import math
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence

import aiosqlite
import pandas as pd

from config import settings
from fno_chain import ChainSnapshot, select_strike_by_delta
from cost_schedules import options_cost_snapshot
from fno_costs import calc_fno_costs_from_snapshot
from fno_engine_mom import (
    SESSION_OPEN_MIN, MomSignal, _minutes_ist, _rvol_time_adjusted,
    evaluate_fno_mom, wilder_atr,
)
from fno_models import FnoDirection, OptionType


@dataclass(frozen=True)
class FnoShadowVariant:
    name: str
    opening_range_minutes: int
    freshness: str                       # crossing | first_confirmation | crossing_or_pullback
    confirmation_bars: int = 0
    max_extension_atr: float | None = None
    pullback_atr: float | None = None    # crossing_or_pullback: how near the break level a pullback must come
    ema_filter: bool = True              # [O27] False: the multi-day EMA(21/50) agreement is not required
    # [O27b] Research genes for the evolution round (scripts/run_fno_evolution.py). Every default leaves the
    # variant exactly as before; no recorded live shadow sets one.
    ema_spans: tuple[int, int] | None = None     # trend-check EMA spans (None: FNO_EMA_FAST / FNO_EMA_SLOW)
    buffer_atr: float | None = None              # break buffer in ATR (None: FNO_OR_BUFFER_ATR)
    stretch_buffer: bool = False                 # Crabel's stretch: the buffer is the prior 10 sessions' mean
                                                 # distance from the open to its nearer extreme
    min_rvol: float | None = None                # None: FNO_MIN_RVOL
    vwap_side: bool = False                      # the break closes on the trade's side of today's VWAP
    or_bias: str | None = None                   # "with" / "against" the opening range's own direction
                                                 # (its last close vs the day's open)
    gap_align: bool = False                      # only with today's opening gap, when it is at least 0.1%
    max_or_width_ratio: float | None = None      # the range no wider than this x the prior 10 sessions' mean
    narrow_prior_days: int | None = None         # NR-n: the previous session's range the narrowest of the last n
    latest_entry_min: int | None = None          # no signal at or after this IST minute of the day
    stop_atr_mult: float | None = None           # None: FNO_STOP_ATR_MULT
    target_r: float | None = None                # None: FNO_TARGET_R


_VARIANT_ROWS = (
    FnoShadowVariant("FNO_BASE", int(settings.FNO_OR_MINUTES), "crossing"),
    FnoShadowVariant("FNO_CONFIRM_1", int(settings.FNO_OR_MINUTES), "first_confirmation", 1, 0.35),
    FnoShadowVariant("FNO_OR_20", 20, "crossing"),
    FnoShadowVariant("FNO_OR_45", 45, "crossing"),
    # [O24g 2026-10-24] Frozen before any scoring: the base break, or a continuation on a trend day. The book's
    # money came from trends held with a trail (Sep 1 - Oct 23: three trail exits +Rs13,767, every other exit
    # -Rs10,002) while most bars after a break are "not_fresh_break". After the break, the price pulls back to
    # within 0.25 ATR of the break level since its latest extreme, and the last closed bar resumes the trend. One
    # new number (0.25), set a priori; every other check, the stop and the target are the base's.
    FnoShadowVariant("FNO_CONTINUATION", int(settings.FNO_OR_MINUTES), "crossing_or_pullback", pullback_atr=0.25),
)
VARIANTS: Mapping[str, FnoShadowVariant] = MappingProxyType({
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
    return value


def _json(value) -> str:
    return json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _selected(names: Sequence[str] | None) -> tuple[FnoShadowVariant, ...]:
    selected = tuple(names) if names is not None else tuple(VARIANTS)
    if not selected or len(set(selected)) != len(selected):
        raise ValueError("F&O shadow variants must be non-empty and unique")
    unknown = [name for name in selected if name not in VARIANTS]
    if unknown:
        raise ValueError(f"unknown F&O shadow variant(s): {', '.join(unknown)}")
    return tuple(VARIANTS[name] for name in selected)


def pullback_resumed(bars: pd.DataFrame, long: bool, level: float, atr: float, tolerance_atr: float) -> bool:
    """[O24g] A continuation after the opening-range break (today's closed
    bars, the last one being judged). Since the first close beyond ``level``
    today, the price made an extreme (the highest high, for a long), then
    pulled back to within ``tolerance_atr`` ATR of the level, and the last
    bar resumes: it closes beyond the level and beyond the previous bar's
    extreme (its high, for a long). Causal: only closed bars are read."""
    closes = [float(value) for value in bars["close"]]
    highs = [float(value) for value in bars["high"]]
    lows = [float(value) for value in bars["low"]]
    beyond = [close > level if long else close < level for close in closes]
    if len(closes) < 4 or not beyond[-1] or True not in beyond[:-1]:
        return False
    first = beyond.index(True)
    run = range(first, len(closes) - 1)                 # from the break to the bar before the last
    extremes = highs if long else lows
    peak = max(run, key=lambda i: extremes[i]) if long else min(run, key=lambda i: extremes[i])
    after = range(peak + 1, len(closes) - 1)
    if not after:
        return False                                    # no pullback since the latest extreme
    if long:
        return min(lows[i] for i in after) <= level + tolerance_atr * atr and closes[-1] > highs[-2]
    return max(highs[i] for i in after) >= level - tolerance_atr * atr and closes[-1] < lows[-2]


GAP_MIN_FRACTION = 0.001          # [O27b] gap_align ignores opening gaps under 0.1%
_PRIOR_CACHE: dict = {}


def _prior_sessions(closed: pd.DataFrame, day: date, or_minutes: int) -> list[dict]:
    """[O27b] Open, high, low, close and opening-range width of every session before ``day`` in the frame,
    oldest first. Pure; cached per frame window because a replay asks the same day many times."""
    prior = closed[[stamp < day for stamp in closed.index.date]]
    if prior.empty:
        return []
    key = (day, or_minutes, len(prior), prior.index[0], prior.index[-1], float(prior["close"].iloc[-1]))
    if key in _PRIOR_CACHE:
        return _PRIOR_CACHE[key]
    rows = []
    for session, session_bars in prior.groupby(prior.index.date):
        opening = session_bars[[SESSION_OPEN_MIN <= _minutes_ist(stamp) < SESSION_OPEN_MIN + or_minutes
                                for stamp in session_bars.index]]
        rows.append({"day": session, "open": float(session_bars["open"].iloc[0]),
                     "high": float(session_bars["high"].max()), "low": float(session_bars["low"].min()),
                     "close": float(session_bars["close"].iloc[-1]),
                     "or_width": (float(opening["high"].max() - opening["low"].min())
                                  if len(opening) == or_minutes // 5 else None)})
    if len(_PRIOR_CACHE) > 256:
        _PRIOR_CACHE.clear()
    _PRIOR_CACHE[key] = rows
    return rows


def _variant_signal(
    bars: pd.DataFrame, regime: str, now_ist: datetime,
    variant: FnoShadowVariant,
) -> MomSignal:
    """Evaluate one declared variant without mutating global strategy settings."""
    if variant.name == "FNO_BASE":
        return evaluate_fno_mom(bars, regime, now_ist)

    out = MomSignal()
    if bars is None or bars.empty:
        out.reject_reason = "no_bars"
        return out
    naive_now = now_ist.replace(tzinfo=None)
    closed = bars[bars.index + timedelta(minutes=5) <= naive_now]
    today_bars = closed[[stamp == naive_now.date() for stamp in closed.index.date]]
    if today_bars.empty:
        out.reject_reason = "no_closed_bars_today"
        return out
    last_ts = today_bars.index[-1]
    out.bar_ts = last_ts.strftime("%Y-%m-%d %H:%M:%S")
    out.close = float(today_bars["close"].iloc[-1])

    or_end = SESSION_OPEN_MIN + variant.opening_range_minutes
    or_bars = today_bars[[
        SESSION_OPEN_MIN <= _minutes_ist(stamp) < or_end for stamp in today_bars.index
    ]]
    if len(or_bars) < variant.opening_range_minutes // 5:
        out.reject_reason = "opening_range_incomplete"
        return out
    out.or_high = float(or_bars["high"].max())
    out.or_low = float(or_bars["low"].min())
    if _minutes_ist(last_ts) < or_end:
        out.reject_reason = "inside_opening_range_window"
        return out
    if variant.latest_entry_min is not None and now_ist.hour * 60 + now_ist.minute >= variant.latest_entry_min:
        out.reject_reason = "after_latest_entry"
        return out

    atr = wilder_atr(closed, settings.FNO_ATR_LEN)
    if atr is None:
        out.reject_reason = "atr_unavailable"
        return out
    out.atr = atr
    fast_span, slow_span = variant.ema_spans or (settings.FNO_EMA_FAST, settings.FNO_EMA_SLOW)
    if len(closed) < slow_span + 1:
        out.reject_reason = "ema_insufficient_bars"
        return out
    fast = closed["close"].ewm(span=fast_span, adjust=False).mean()
    slow = closed["close"].ewm(span=slow_span, adjust=False).mean()
    out.ema_fast, out.ema_slow = float(fast.iloc[-1]), float(slow.iloc[-1])
    rvol = _rvol_time_adjusted(closed, last_ts)
    out.rvol = rvol if rvol is not None else 0.0

    buffer = (settings.FNO_OR_BUFFER_ATR if variant.buffer_atr is None else variant.buffer_atr) * atr
    history: list[dict] | None = None
    if variant.stretch_buffer:
        history = _prior_sessions(closed, naive_now.date(), variant.opening_range_minutes)
        reach = [min(row["high"] - row["open"], row["open"] - row["low"]) for row in history[-10:]]
        if len(reach) < 5:
            out.reject_reason = "stretch_unavailable"
            return out
        buffer = sum(reach) / len(reach)
    long_level = out.or_high + buffer
    short_level = out.or_low - buffer
    long_break, short_break = out.close > long_level, out.close < short_level
    if not long_break and not short_break:
        out.reject_reason = "no_or_break"
        return out
    closes = [float(value) for value in today_bars["close"].iloc[-3:]]
    prev = closes[-2] if len(closes) >= 2 else out.close

    if variant.freshness == "crossing":
        if (long_break and prev > long_level) or (short_break and prev < short_level):
            out.reject_reason = "not_fresh_break"
            return out
    elif variant.freshness == "crossing_or_pullback":
        fresh = not ((long_break and prev > long_level) or (short_break and prev < short_level))
        if not fresh and not pullback_resumed(today_bars, long_break, long_level if long_break else short_level,
                                              atr, float(variant.pullback_atr or 0.0)):
            out.reject_reason = "no_pullback_resumption"
            return out
    elif variant.freshness == "first_confirmation":
        prior = closes[-3] if len(closes) >= 3 else prev
        first_confirmation = (
            long_break and prev > long_level and prior <= long_level
        ) or (
            short_break and prev < short_level and prior >= short_level
        )
        if not first_confirmation:
            out.reject_reason = (
                "awaiting_confirmation"
                if (long_break and prev <= long_level) or (short_break and prev >= short_level)
                else "confirmation_not_first_bar"
            )
            return out
        extension = out.close - long_level if long_break else short_level - out.close
        if extension > float(variant.max_extension_atr or 0.0) * atr:
            out.reject_reason = "confirmation_extension_exceeded"
            return out
    else:
        raise ValueError(f"unknown freshness {variant.freshness!r} for {variant.name}")

    reason = _gene_reject(variant, closed, today_bars, or_bars, long_break, out, naive_now.date(), history)
    if reason:
        out.reject_reason = reason
        return out

    if regime == "REGIME_3_CRISIS":
        out.reject_reason = "regime_crisis"
        return out
    if variant.ema_filter and ((long_break and out.ema_fast <= out.ema_slow) or (
        short_break and out.ema_fast >= out.ema_slow
    )):
        out.reject_reason = "ema_trend_disagreement"
        return out
    if rvol is None:
        out.reject_reason = "rvol_baseline_unavailable"
        return out
    if rvol < (settings.FNO_MIN_RVOL if variant.min_rvol is None else variant.min_rvol):
        out.reject_reason = "rvol_below_min"
        return out

    distance = (settings.FNO_STOP_ATR_MULT if variant.stop_atr_mult is None else variant.stop_atr_mult) * atr
    target_r = settings.FNO_TARGET_R if variant.target_r is None else variant.target_r
    if long_break:
        out.stop_underlying = max(out.or_low, out.close - distance)
        risk_points = out.close - out.stop_underlying
        out.target_underlying = out.close + target_r * risk_points
        out.direction = FnoDirection.LONG
    else:
        out.stop_underlying = min(out.or_high, out.close + distance)
        risk_points = out.stop_underlying - out.close
        out.target_underlying = out.close - target_r * risk_points
        out.direction = FnoDirection.SHORT
    if risk_points <= 0:
        out.direction, out.reject_reason = None, "degenerate_stop_distance"
    return out


def _gene_reject(variant: FnoShadowVariant, closed: pd.DataFrame, today_bars: pd.DataFrame, or_bars: pd.DataFrame,
                 long: bool, out: MomSignal, day: date, history: list[dict] | None) -> str | None:
    """[O27b] The research genes' checks on a fresh break (the reason it is refused, else None). Causal: closed bars
    of today and earlier sessions only."""
    day_open = float(today_bars["open"].iloc[0])
    if variant.vwap_side:
        volume = today_bars["volume"].astype(float)
        if float(volume.sum()) <= 0:
            return "vwap_unavailable"
        typical = (today_bars["high"] + today_bars["low"] + today_bars["close"]) / 3.0
        vwap = float((typical * volume).sum() / volume.sum())
        if (long and out.close <= vwap) or (not long and out.close >= vwap):
            return "vwap_side_against"
    if variant.or_bias:
        drift = float(or_bars["close"].iloc[-1]) - day_open
        with_bias = drift > 0 if long else drift < 0
        if with_bias != (variant.or_bias == "with"):
            return f"opening_range_bias_not_{variant.or_bias}"
    if not (variant.gap_align or variant.max_or_width_ratio is not None or variant.narrow_prior_days):
        return None
    history = history if history is not None else _prior_sessions(closed, day, variant.opening_range_minutes)
    if not history:
        return "prior_sessions_unavailable"
    if variant.gap_align:
        gap = (day_open - history[-1]["close"]) / history[-1]["close"]
        if abs(gap) >= GAP_MIN_FRACTION and ((long and gap < 0) or (not long and gap > 0)):
            return "against_opening_gap"
    if variant.max_or_width_ratio is not None:
        widths = [row["or_width"] for row in history[-10:] if row["or_width"]]
        if len(widths) < 5:
            return "or_width_history_unavailable"
        if out.or_high - out.or_low > variant.max_or_width_ratio * sum(widths) / len(widths):
            return "opening_range_too_wide"
    if variant.narrow_prior_days:
        if len(history) < variant.narrow_prior_days:
            return "narrow_range_history_unavailable"
        ranges = [row["high"] - row["low"] for row in history[-variant.narrow_prior_days:]]
        if ranges[-1] > min(ranges):
            return "previous_session_not_narrow"
    return None


def evaluate_fno_shadows(
    bars: pd.DataFrame, regime: str, now_ist: datetime,
    *, underlying: str = "NIFTY", variants: Sequence[str] | None = None,
) -> list[dict]:
    """Evaluate every variant on one immutable, already-fetched bar frame."""
    results = []
    for variant in _selected(variants):
        signal = _variant_signal(bars, regime, now_ist, variant)
        day = signal.bar_ts[:10] if signal.bar_ts else now_ist.date().isoformat()
        direction = signal.direction.value if signal.direction else None
        accepted = signal.direction is not None
        # One directional thesis per variant/day/underlying. The evaluation
        # bar stays in the row identity but must not inflate sample size when
        # resident-above bars repeat an accept.
        candidate_key = f"{day}|{underlying}|{direction}" if accepted else None
        results.append({
            "trading_date": day,
            "underlying": underlying,
            "bar_ts": signal.bar_ts or now_ist.replace(tzinfo=None).isoformat(sep=" "),
            "variant": variant.name,
            "accepted": accepted,
            "reject_reason": None if accepted else signal.reject_reason,
            "direction": direction,
            "candidate_key": candidate_key,
            "features": {
                "close": signal.close, "or_high": signal.or_high, "or_low": signal.or_low,
                "atr": signal.atr, "ema_fast": signal.ema_fast,
                "ema_slow": signal.ema_slow, "rvol": signal.rvol,
                "stop_underlying": signal.stop_underlying,
                "target_underlying": signal.target_underlying,
            },
            "config": asdict(variant),
            "post_cost_outcome": {
                "available": False,
                "reason": "no already-resolved option chain for this evaluation",
            },
        })
    return results


def attach_resolved_cost_estimates(
    results: list[dict], snapshot: ChainSnapshot, now_ist: datetime,
) -> list[dict]:
    """Add a one-lot target scenario using an already-resolved chain only.

    This is not a fill or P&L claim. It pays the observed two-sided spread,
    applies the production tax/brokerage model, and uses a linear-delta target
    premium estimate. Stop/time/hard-flat paths remain unavailable.
    """
    for result in results:
        if not result.get("accepted"):
            continue
        opt_type = OptionType.CE if result["direction"] == "LONG" else OptionType.PE
        picked = select_strike_by_delta(snapshot, opt_type, now_ist)
        if picked is None:
            result["post_cost_outcome"] = {"available": False, "reason": "no delta-solvable contract"}
            continue
        quote, iv, delta = picked
        if not quote.two_sided or quote.ask <= 0:
            result["post_cost_outcome"] = {"available": False, "reason": "two-sided option quote unavailable"}
            continue
        features = result["features"]
        target_points = abs(float(features["target_underlying"]) - float(features["close"]))
        half_spread = (quote.ask - quote.bid) / 2.0
        estimated_exit = max(
            float(quote.contract.tick_size), quote.mid + abs(float(delta)) * target_points - half_spread,
        )
        qty = int(snapshot.lot_size or quote.contract.lot_size)
        gross = (estimated_exit - quote.ask) * qty
        from fno_costs import options_exchange_for
        execution = options_cost_snapshot(options_exchange_for(result.get("underlying") or "NIFTY"))
        costs = calc_fno_costs_from_snapshot(quote.ask, estimated_exit, qty, execution)
        result["post_cost_outcome"] = {
            "available": True,
            "kind": "target_scenario_linear_delta_one_lot",
            "entry_at_observed_ask": round(quote.ask, 4),
            "exit_at_estimated_bid": round(estimated_exit, 4),
            "quantity": qty,
            "gross_pnl": round(gross, 2),
            "estimated_costs": round(costs, 2),
            "estimated_net_pnl": round(gross - costs, 2),
            "execution_snapshot": execution,
            "iv_at_evaluation": round(float(iv), 6),
            "delta_at_evaluation": round(float(delta), 6),
            "limitations": [
                "target-hit scenario only; no claim that target was reached",
                "linear delta holds IV constant and omits gamma/theta changes",
                "does not replay premium stop, time stop, trail, or hard flat",
            ],
        }
    return results


async def init_fno_shadow_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS fno_shadow_evaluations (
                trading_date TEXT NOT NULL,
                underlying TEXT NOT NULL,
                bar_ts TEXT NOT NULL,
                variant TEXT NOT NULL,
                accepted INTEGER NOT NULL CHECK(accepted IN (0,1)),
                reject_reason TEXT,
                direction TEXT,
                candidate_key TEXT,
                features_json TEXT NOT NULL,
                config_json TEXT NOT NULL,
                outcome_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(trading_date,underlying,bar_ts,variant)
            )
        """)
        await db.commit()


async def persist_fno_shadow_results(db_path: str, results: Iterable[dict]) -> int:
    await init_fno_shadow_db(db_path)
    inserted, created_at = 0, datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(db_path) as db:
        for result in results:
            if result.get("variant") not in VARIANTS:
                raise ValueError(f"unregistered F&O shadow variant: {result.get('variant')!r}")
            day_text = str(result.get("trading_date") or "")
            bar_text = str(result.get("bar_ts") or "")
            underlying = str(result.get("underlying") or "").strip().upper()
            try:
                parsed_day = date.fromisoformat(day_text)
                parsed_bar = datetime.fromisoformat(bar_text.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("F&O shadow date and bar_ts must be valid ISO values") from exc
            if parsed_day.isoformat() != day_text or parsed_bar.date() != parsed_day:
                raise ValueError("F&O shadow bar_ts must belong to trading_date")
            if not underlying or not all(ch.isalnum() or ch in "_-" for ch in underlying):
                raise ValueError("F&O shadow underlying must be a non-empty safe identifier")
            if not isinstance(result.get("accepted"), bool):
                raise ValueError("F&O shadow accepted must be boolean")
            direction = result.get("direction")
            if direction is not None and direction not in {item.value for item in FnoDirection}:
                raise ValueError("F&O shadow direction must be LONG, SHORT, or null")
            if result["accepted"] and direction is None:
                raise ValueError("accepted F&O shadow rows require a direction")
            features = result.get("features")
            close = features.get("close") if isinstance(features, dict) else None
            if close is None or not math.isfinite(float(close)):
                raise ValueError("F&O shadow rows require a finite close observation")
            candidate_key = f"{day_text}|{underlying}|{direction}" if result["accepted"] else None
            cursor = await db.execute("""
                INSERT OR IGNORE INTO fno_shadow_evaluations
                    (trading_date,underlying,bar_ts,variant,accepted,reject_reason,
                     direction,candidate_key,features_json,config_json,outcome_json,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                day_text, underlying, bar_text,
                result["variant"], int(bool(result["accepted"])), result.get("reject_reason"),
                direction, candidate_key,
                _json(features), _json(result.get("config", {})),
                _json(result.get("post_cost_outcome", {})), created_at,
            ))
            inserted += max(int(cursor.rowcount or 0), 0)
        await db.commit()
    return inserted


def persist_fno_shadow_results_sync(db_path: str, results: Iterable[dict]) -> int:
    """Thread-worker entry point with a self-contained event loop."""
    return asyncio.run(persist_fno_shadow_results(db_path, list(results)))


async def fno_shadow_comparison(db_path: str) -> dict:
    await init_fno_shadow_db(db_path)
    rows = []
    async with aiosqlite.connect(db_path) as db:
        for name in VARIANTS:
            stored = await (await db.execute("""
                SELECT accepted,reject_reason,candidate_key,outcome_json
                FROM fno_shadow_evaluations WHERE variant=?
            """, (name,))).fetchall()
            evaluations = len(stored)
            accepts = sum(int(row[0]) for row in stored)
            candidates = len({row[2] for row in stored if row[2]})
            outcomes = [json.loads(row[3]) for row in stored if row[0]]
            available = [outcome for outcome in outcomes if outcome.get("available")]
            reject_counts: dict[str, int] = {}
            for accepted, reason, _, _ in stored:
                if not accepted:
                    reject_counts[reason or "unknown"] = reject_counts.get(reason or "unknown", 0) + 1
            rows.append({
                "variant": name,
                "evaluations": evaluations,
                "accepted_evaluations": accepts,
                "distinct_candidates": candidates,
                "accept_rate": round(accepts / evaluations, 6) if evaluations else None,
                "top_rejects": [
                    {"reason": reason, "count": count}
                    for reason, count in sorted(reject_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
                ],
                "estimated_post_cost": {
                    "available_samples": len(available),
                    "unavailable_candidates": max(candidates - len(available), 0),
                    "gross_pnl": round(sum(item["gross_pnl"] for item in available), 2) if available else None,
                    "estimated_costs": round(sum(item["estimated_costs"] for item in available), 2) if available else None,
                    "estimated_net_pnl": round(sum(item["estimated_net_pnl"] for item in available), 2) if available else None,
                    "interpretation": "target scenarios, not realised trades or strategy profitability",
                },
            })
    return {"research_only": True, "can_place_orders": False, "variants": rows}
