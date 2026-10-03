"""[B2 2026-10-03] Exact classic Penny CNC Connors lifecycle replay (offline).

Replays what the shipped ``PENNY_PAPER`` CNC book does, not what the Connors
spec describes:

* 09:30 IST entry scan (``run_penny_connors_scan``): the scanner fetches Kite
  day candles *up to today*, so the last bar is today's in-progress candle
  (~09:15-09:30). It is rebuilt here from validated minute bars; the real
  ``evaluate_connors_entry`` then runs with the scanner's exact inputs and a
  real ``PennyRiskEngine``; admission applies the per-ticker reservation,
  CNC/total caps and the executor's drift / stop checks; paper fills at LTP.
* 15:45 IST ``position_tracker.update_daily_positions`` on each final daily
  bar: stop (unless a target was also hit), T2, T1 partial (50%, stop to
  breakeven), 15-calendar-day time stop. Connors rows carry no ATR, so the
  chandelier trail is disabled. ``evaluate_connors_exit`` has no runtime
  caller and is deliberately not used.

The tracker branch order is re-implemented as a pure function and proved
equal to the real tracker by a parity test. Live ``PENNY`` CNC rows are not
managed by the tracker (only a broker SL-M), so that book is UNSUPPORTED.
Not named ``penny_*``: it reuses ``engine.calc_zerodha_costs`` as the tracker
does, which the Penny runtime isolation rule forbids for ``penny_*`` modules.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import math
from typing import Optional

import pandas as pd

from research_data_contracts import IST, DailyDataset, IntradayDataset

LIFECYCLE_VERSION = "penny_cnc_connors_lifecycle_v1"
SCOPE = "LIFECYCLE"
SCAN_MINUTE = 9 * 60 + 30
PARTIAL_LAST_BAR = time(9, 29)
TIME_STOP_CALENDAR_DAYS = 15
NOT_REPLAYED = (
    "point_in_time_universe_ranking (explicit tickers, alphabetical admission order)",
    "historical_penny_regime (one declared constant regime per run)",
    "mis_positions_occupying_total_capacity",
    "broker_blocks_rejections_and_partial_fills",
    "scheduler_jitter (scan at 09:30:00, tracker at 15:45)",
    "partial_candle_trades_after_09:29_and_before_the_scan_instant",
)


@dataclass(frozen=True)
class PennyCncConfig:
    tickers: tuple
    book: str = "PENNY_PAPER"
    regime: str = "PR1_CALM"

    def __post_init__(self):
        clean = tuple(sorted({str(t).strip().upper() for t in self.tickers if str(t).strip()}))
        if not clean:
            raise ValueError("at least one ticker is required")
        object.__setattr__(self, "tickers", clean)
        if self.book not in ("PENNY_PAPER", "PENNY"):
            raise ValueError("book must be PENNY_PAPER or PENNY")
        if self.regime not in ("PR1_CALM", "PR2_ELEVATED", "PR3_HOT"):
            raise ValueError("regime must be PR1_CALM, PR2_ELEVATED or PR3_HOT")


# ---- entry inputs (mirror PennyScanner._evaluate_ticker_connors) ---------------

def partial_candle(bars) -> Optional[dict]:
    """Today's in-progress day candle as Kite reports it at the 09:30 scan."""
    morning = [b for b in bars if b.start.time() <= PARTIAL_LAST_BAR]
    if not morning:
        return None
    return {"open": morning[0].open, "high": max(b.high for b in morning),
            "low": min(b.low for b in morning), "close": morning[-1].close,
            "volume": float(sum(b.volume for b in morning))}


def scanner_daily_frame(daily: DailyDataset, ticker: str, day: date, partial: dict) -> pd.DataFrame:
    """``get_historical(as_of - DAILY_HISTORY_DAYS, today)`` at 09:30, point-in-time."""
    from config import settings
    since = day - timedelta(days=int(settings.DAILY_HISTORY_DAYS))
    rows = [{"date": pd.Timestamp(b.day), "open": b.open, "high": b.high, "low": b.low,
             "close": b.close, "volume": b.volume}
            for b in daily.known_before(ticker, day, since=since)]
    rows.append({"date": pd.Timestamp(day), **partial})
    return pd.DataFrame(rows).set_index("date")


def connors_decision(ticker: str, bars: pd.DataFrame, *, risk_engine, regime: str, as_of: datetime) -> dict:
    """The scanner's exact evaluator call for one ticker (pure; no broker)."""
    from penny_engine_connors import evaluate_connors_entry
    from penny_models import PennyRegime
    from penny_regime import PennyRegimeEngine
    if len(bars) < 250:
        return {"accept": False, "reject_reason": "insufficient_history", "ticker": ticker}
    vol_series = bars["volume"].tail(21)
    today_volume = int(vol_series.iloc[-1] or 0)
    avg20_volume = int(vol_series.tail(20).median() or 0)
    closes = bars["close"].tolist()
    return evaluate_connors_entry(
        ticker=ticker, daily={"closes": closes}, today_volume=today_volume,
        avg20_volume=avg20_volume,
        regime_size_pct=PennyRegimeEngine().size_pct(PennyRegime(regime)),
        risk_engine=risk_engine, as_of=as_of,
    )


# ---- 15:45 tracker (mirror position_tracker.update_daily_positions) ----------

def tracker_step(pos: dict, bar: dict, current_day: date) -> dict:
    """Apply one daily tracker pass; returns the event (``hold`` when unchanged).

    ``pos`` keys: entry_price, entry_date (ISO), shares, stop_loss_initial,
    trailing_stop_current, target_1, target_2, highest_close_since_entry,
    status (OPEN|CLOSED_T1), realised_pnl, atr_14_at_entry, regime_at_entry.
    Mutates ``pos`` exactly as the tracker's UPDATE would.
    """
    from engine import calc_zerodha_costs
    o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]
    highest_close = float(max(float(pos["highest_close_since_entry"]), c))
    if pos.get("atr_14_at_entry"):
        raise ValueError("chandelier trail is not part of the CNC Connors lifecycle")
    trailing_stop = pos["trailing_stop_current"]
    effective_target_2 = pos["target_2"]
    if pos.get("regime_at_entry") == "REGIME_1_NORMAL":
        from config import settings
        risk = pos["entry_price"] - pos["stop_loss_initial"]
        if risk > 0:
            cap = pos["entry_price"] + settings.HARD_CAP_R_REGIME1 * risk
            if effective_target_2 is None or effective_target_2 > cap:
                effective_target_2 = cap
    current_status = pos["status"]
    status, exit_price, hit_t1_today = current_status, None, False
    days_held = (current_day - datetime.fromisoformat(pos["entry_date"]).date()).days
    stop_hit = l <= trailing_stop
    target2_hit = h >= effective_target_2 if effective_target_2 is not None else False
    target1_hit = h >= pos["target_1"]
    if stop_hit and not (target2_hit or target1_hit):
        status, exit_price = "STOPPED_OUT", min(trailing_stop, o)
    elif target2_hit:
        status, exit_price = "CLOSED_T2", max(effective_target_2, o)
    elif target1_hit and current_status == "OPEN":
        status, exit_price, hit_t1_today = "CLOSED_T1", max(pos["target_1"], o), True
    elif days_held >= TIME_STOP_CALENDAR_DAYS:
        status, exit_price = "CLOSED_TIME", c
    pos["highest_close_since_entry"] = highest_close
    if status == current_status:
        pos["trailing_stop_current"] = trailing_stop
        return {"event": "hold"}
    if hit_t1_today:
        closed = math.floor(pos["shares"] * 0.5) or 1
        remaining = pos["shares"] - closed
        gross = (exit_price - pos["entry_price"]) * closed
        costs = calc_zerodha_costs(pos["entry_price"], exit_price, closed, is_intraday=False)
        pnl = gross - costs
        if remaining == 0:
            pos.update(status="CLOSED_T1", trailing_stop_current=trailing_stop, closed=True,
                       exit_price=exit_price, realised_pnl=pnl)
            return {"event": "close", "reason": "CLOSED_T1", "shares": closed,
                    "price": exit_price, "gross": gross, "costs": costs, "pnl": pnl}
        pos.update(status="CLOSED_T1", shares=remaining,
                   trailing_stop_current=max(trailing_stop, pos["entry_price"]),
                   realised_pnl=float(pos.get("realised_pnl") or 0) + pnl)
        return {"event": "partial", "reason": "T1_PARTIAL", "shares": closed,
                "price": exit_price, "gross": gross, "costs": costs, "pnl": pnl}
    gross = (exit_price - pos["entry_price"]) * pos["shares"]
    costs = calc_zerodha_costs(pos["entry_price"], exit_price, pos["shares"], is_intraday=False)
    pnl = gross - costs
    pos.update(status=status, trailing_stop_current=trailing_stop, closed=True,
               exit_price=exit_price,
               realised_pnl=float(pos.get("realised_pnl") or 0) + pnl)
    return {"event": "close", "reason": status, "shares": pos["shares"], "price": exit_price,
            "gross": gross, "costs": costs, "pnl": pnl}


# ---- replay ----------------------------------------------------------------

def _ltp_at(bars, minute: int):
    """(price, executable): open of the bar at ``minute`` if it traded, else a mark."""
    for bar in bars:
        start = bar.start.hour * 60 + bar.start.minute
        if start == minute and bar.executable:
            return bar.open, True
    prior = [b for b in bars if (b.start.hour * 60 + b.start.minute) < minute and b.executable]
    return (prior[-1].close, False) if prior else (None, False)


def run_penny_cnc_lifecycle(
    intraday: IntradayDataset, daily: DailyDataset, config: PennyCncConfig,
    *, start: str, end: str, settle_through: Optional[str] = None,
) -> dict:
    """Replay entries on trading days in [start, end]; manage exits through
    ``settle_through`` (default ``end``) using final daily bars only."""
    from config import settings
    from penny_executor import MAX_ENTRY_DRIFT_PCT
    from penny_risk import PennyRiskEngine
    if config.book != "PENNY_PAPER":
        return {"schema": "sentinel_penny_cnc_lifecycle_v1", "scope": SCOPE,
                "status": "UNSUPPORTED", "config": asdict(config),
                "reason": "live PENNY CNC rows have no shipped exit management besides a broker SL-M",
                "can_place_orders": False, "can_qualify": False}
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    through = date.fromisoformat(settle_through or end)
    if last < first or through < last:
        raise ValueError("require start <= end <= settle_through")
    calendar_days = sorted({d for (t, d) in intraday.bars if first.isoformat() <= d <= last.isoformat()}
                           | {row["trading_date"] for row in intraday.coverage
                              if first.isoformat() <= row["trading_date"] <= last.isoformat()})
    daily_days = sorted({b.day.isoformat() for bars in daily.bars.values() for b in bars
                         if first <= b.day <= through})
    bankroll = float(settings.PENNY_PAPER_BANKROLL)
    risk = PennyRiskEngine(bankroll=bankroll)
    funnel: Counter = Counter()
    rejects: Counter = Counter()
    admissions: Counter = Counter()
    open_positions: dict[str, dict] = {}
    trades: list[dict] = []
    missing_daily: list[dict] = []
    days = sorted(set(calendar_days) | set(daily_days))
    for day_text in days:
        day = date.fromisoformat(day_text)
        # 09:30 scan (entry days only)
        if first <= day <= last and day_text in calendar_days:
            as_of = datetime(day.year, day.month, day.day, 9, 30, tzinfo=IST)
            for ticker in config.tickers:
                if risk.is_disabled(ticker):
                    continue
                bars = intraday.bars.get((ticker, day_text))
                partial = partial_candle(bars) if bars else None
                if partial is None:
                    funnel["NO_PARTIAL_CANDLE_EVIDENCE"] += 1
                    continue
                if ticker in daily.invalid:
                    funnel["DAILY_HISTORY_INVALID"] += 1
                    continue
                funnel["evaluations"] += 1
                frame = scanner_daily_frame(daily, ticker, day, partial)
                decision = connors_decision(ticker, frame, risk_engine=risk,
                                            regime=config.regime, as_of=as_of)
                if not decision.get("accept"):
                    rejects[str(decision.get("reject_reason", "unknown")).split(" (")[0]] += 1
                    continue
                funnel["accepted_signals"] += 1
                if ticker in open_positions:
                    admissions["OCCUPIED_SAME_TICKER"] += 1
                    continue
                if (len(open_positions) >= settings.PENNY_MAX_POSITIONS_CNC
                        or len(open_positions) >= settings.PENNY_MAX_POSITIONS_TOTAL):
                    admissions["CAPACITY_REJECTED"] += 1
                    continue
                ltp, executable = _ltp_at(bars, SCAN_MINUTE)
                entry, stop = float(decision["entry"]), float(decision["stop_loss"])
                if ltp is None:
                    admissions["NO_QUOTE"] += 1
                    continue
                if (abs(ltp - entry) / entry if entry else 1.0) > MAX_ENTRY_DRIFT_PCT:
                    admissions["DRIFT_REJECTED"] += 1
                    continue
                if stop >= ltp:
                    admissions["STOP_ALREADY_BREACHED"] += 1
                    continue
                if not executable:
                    admissions["NO_EXECUTABLE_EVIDENCE"] += 1
                    continue
                admissions["FILLED"] += 1
                pos = {
                    "ticker": ticker, "entry_price": float(ltp),
                    "entry_date": as_of.astimezone(timezone.utc).isoformat(),
                    "shares": int(decision["shares"]), "initial_shares": int(decision["shares"]),
                    "stop_loss_initial": stop, "trailing_stop_current": stop,
                    "target_1": float(decision["target_1"]), "target_2": float(decision["target_2"]),
                    "highest_close_since_entry": float(ltp), "status": "OPEN",
                    "realised_pnl": None, "atr_14_at_entry": float(decision.get("atr_14", 0.0) or 0.0),
                    "regime_at_entry": config.regime, "signal_entry": entry,
                    "rsi_2": decision.get("rsi_2"), "events": [],
                }
                open_positions[ticker] = pos
                trades.append(pos)
        # 15:45 tracker on the final daily bar
        for ticker in sorted(open_positions):
            pos = open_positions[ticker]
            bar = next((b for b in daily.bars.get(ticker, ()) if b.day == day), None)
            if bar is None:
                missing_daily.append({"ticker": ticker, "trading_date": day_text})
                continue
            event = tracker_step(pos, {"open": bar.open, "high": bar.high, "low": bar.low,
                                       "close": bar.close}, day)
            if event["event"] != "hold":
                pos["events"].append({"trading_date": day_text, **{
                    k: (round(v, 4) if isinstance(v, float) else v) for k, v in event.items()}})
            if pos.get("closed"):
                pos["exit_date"] = day_text
                del open_positions[ticker]
    closed = [t for t in trades if t.get("closed")]
    unresolved = [t for t in trades if not t.get("closed")]
    for trade in unresolved:
        trade["status"] = "UNRESOLVED_OPEN_AT_SETTLE_THROUGH"
    for trade in trades:
        risk_initial = (trade["entry_price"] - trade["stop_loss_initial"]) * trade["initial_shares"]
        net = trade.get("realised_pnl")
        trade["net_pnl"] = round(net, 4) if net is not None and trade.get("closed") else None
        trade["r_multiple"] = (round(net / risk_initial, 6)
                               if trade["net_pnl"] is not None and risk_initial > 0 else None)
        trade.pop("closed", None)
    nets = [t["net_pnl"] for t in closed]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x < 0]
    summary = {
        "entries": len(trades), "closed_trades": len(closed), "unresolved_trades": len(unresolved),
        "net_pnl": round(sum(nets), 4) if nets else None,
        "win_rate_pct": round(100 * len(wins) / len(nets), 4) if nets else None,
        "profit_factor": round(sum(wins) / abs(sum(losses)), 6) if nets and losses else None,
        "expectancy": round(sum(nets) / len(nets), 4) if nets else None,
        "net_excluding_best_winner": (round(sum(nets) - max(nets), 4) if nets and max(nets) > 0
                                      else (round(sum(nets), 4) if nets else None)),
        "exit_reasons": dict(Counter(e["reason"] for t in trades for e in t["events"])),
    }
    status = ("UNAVAILABLE" if funnel["evaluations"] == 0
              else "PARTIAL" if unresolved or missing_daily or funnel["NO_PARTIAL_CANDLE_EVIDENCE"]
              else "COMPLETE")
    declared = {"version": LIFECYCLE_VERSION, "config": asdict(config), "start": start, "end": end,
                "settle_through": through.isoformat(),
                "intraday": intraday.manifest.get("dataset_sha256"),
                "daily": daily.manifest.get("dataset_sha256"), "bankroll": bankroll}
    return {
        "schema": "sentinel_penny_cnc_lifecycle_v1", "scope": SCOPE, "status": status,
        "strategy": "classic_penny_cnc_connors",
        "run_fingerprint": "sha256:" + hashlib.sha256(json.dumps(
            declared, sort_keys=True, default=str).encode()).hexdigest(),
        "config": asdict(config),
        "assumptions": {
            "entry_clock": "09:30 IST scan; last daily bar = today's partial candle (09:15-09:29 minutes)",
            "fill": "LTP at 09:30 (open of the traded 09:30 bar); executor drift/stop checks",
            "exits": "15:45 tracker on final daily bars (stop unless target hit, T2, T1 50%, 15-day time)",
            "trail": "disabled: Connors decisions carry no atr_14",
            "costs": "engine.calc_zerodha_costs(is_intraday=False), as the tracker books",
            "regime": f"declared constant {config.regime}",
            "sizing": "PennyRiskEngine.position_size with fixed PENNY_PAPER_BANKROLL",
        },
        "not_replayed": list(NOT_REPLAYED),
        "datasets": {"intraday": intraday.manifest, "daily": daily.manifest},
        "funnel": {**dict(funnel), "reject_reasons": dict(sorted(rejects.items())),
                   "admission_outcomes": dict(sorted(admissions.items()))},
        "missing_final_daily_bars": missing_daily, "summary": summary, "trades": trades,
        "warnings": [
            "LIFECYCLE scope: not a point-in-time universe, regime or full portfolio return.",
            "Retrospective exploratory evidence; no holdout, tuning, funding or partner authority.",
            "Entry-day exits use the whole day's range, including trading before the 09:30 fill (shipped).",
        ],
        "can_place_orders": False, "can_qualify": False,
    }
