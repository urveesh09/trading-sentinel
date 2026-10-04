"""[B2 2026-10-03] Exact classic Penny MIS breakout lifecycle replay (offline).

Replays the shipped classic Penny MIS book over B1-validated minute bars,
calling the same functions the runtime calls, in the runtime's order:

* entry: ``PennyScanner._evaluate_ticker_breakout`` input construction ->
  ``evaluate_breakout_entry`` (with a real ``PennyRiskEngine`` for sizing) ->
  per-ticker reservation and MIS capacity -> ``PennyExecutor.execute_entry``
  drift / stop-breach checks -> fill at the LTP;
* exits: the 60-second paper LTP stop monitor (``PENNY_PAPER``) or a broker
  stop (``PENNY``), the 14:30 ``run_penny_eod_check`` branch order
  (``time_stop_triggered`` then ``smart_eod_check``) and the 15:00
  ``mis_time_stop_active`` force close. The live book never exits at the
  +2R target; it is used only by the smart-EOD rule.

Clock: the scheduler fires at minute boundary ``k``; the scanner then sees
only bars whose start is before ``k`` (the forming bar is dropped), so bar
``k-1`` is evaluated with ``as_of = k``. The LTP at ``k`` is the open of bar
``k`` when that bar traded, otherwise the last traded close (a mark). A fill
always needs a TRADED bar; a stale mark never proves one.

Scope is LIFECYCLE, not FULL_PORTFOLIO. Universe ranking, historical regime,
sector filter, event calendar, broker blocks/rejections, partial fills, CNC
occupancy and scheduler jitter are not replayed and every report says so.
No network, broker, order, message or database writes.
"""
from __future__ import annotations

from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json

import pandas as pd

from research_data_contracts import (
    COVERAGE_REQUIREMENTS, IST, DailyDataset, IntradayDataset,
)

LIFECYCLE_VERSION = "penny_mis_breakout_lifecycle_v2"
SCOPE = "LIFECYCLE"
BOOKS = ("PENNY_PAPER", "PENNY")
REGIMES = ("PR1_CALM", "PR2_ELEVATED", "PR3_HOT")
# Round 1: PEN_TRADER_V1 (entry change) and _THESIS (same entries + thesis exits).
# Round 2: PEN_BASE_THESIS (shipped entry + thesis exits) and PEN_TRADER_V2.
TRADER_POLICIES = ("PEN_TRADER_V1", "PEN_TRADER_V1_THESIS", "PEN_BASE_THESIS", "PEN_TRADER_V2")
CANDIDATE_POLICIES = ("BASELINE", "PEN_CONTEXT") + TRADER_POLICIES


def trader_policy(name: str) -> tuple:
    """(params or None for the shipped entry, thesis exits?) for a candidate."""
    from adaptive_penny_policy import DEFAULT_PARAMS, V2_PARAMS
    return {
        "PEN_TRADER_V1": (DEFAULT_PARAMS, False),
        "PEN_TRADER_V1_THESIS": (DEFAULT_PARAMS, True),
        "PEN_BASE_THESIS": (None, True),
        "PEN_TRADER_V2": (V2_PARAMS, True),
    }[name]
SESSION_FIRST_BOUNDARY = 9 * 60 + 16
SESSION_LAST_BOUNDARY = 15 * 60 + 30
MEDIAN_LOOKBACK_CALENDAR_DAYS = 30

NOT_REPLAYED = (
    "point_in_time_universe_ranking (explicit tickers, alphabetical admission order)",
    "historical_penny_regime (one declared constant regime per run)",
    "sector_filter (live fail-open sector ETF gate)",
    "operator_event_calendar (no point-in-time event file)",
    "broker_mis_blocks_order_rejections_and_partial_fills",
    "cnc_positions_occupying_total_capacity",
    "scheduler_jitter (one scan per minute boundary assumed)",
    "re-evaluation_of_an_unchanged_last_bar (each completed bar is evaluated once; gaps are not forward-filled)",
    "intraday_volume_of_forming_bar (cumulative volume uses completed bars only)",
    "todays_partial_daily_candle_in_median_volume (strictly prior days used)",
)

_REJECT_CODES = (
    ("outside breakout time window", "TIME_WINDOW"),
    ("volume ", "VOLUME_BELOW_PACE"),
    ("breakout not confirmed", "BREAKOUT_NOT_CONFIRMED"),
    ("RSI(14) overbought", "RSI_OVERBOUGHT"),
    ("non-positive risk", "NON_POSITIVE_RISK"),
    ("regime PR3_HOT", "REGIME_PR3_HOT"),
    ("position size = 0", "SIZE_ZERO"),
    ("circuit_blocked", "CIRCUIT_BLOCKED"),
    ("no 20-day median volume baseline", "NO_MEDIAN_VOLUME_BASELINE"),
    ("insufficient_intraday_bars", "INSUFFICIENT_INTRADAY_BARS"),
    ("zero_complete_bars_after_drop", "INSUFFICIENT_INTRADAY_BARS"),
    ("no prior bars to anchor breakout", "NO_PRIOR_BARS"),
    ("disabled via PENNY_DISABLE_TICKERS", "DISABLED_TICKER"),
    ("quote_unavailable", "NO_QUOTE_EVIDENCE"),
)


def reject_code(reason: str | None) -> str:
    """Bounded research code for an evaluator/scanner reject string."""
    text = str(reason or "")
    for prefix, code in _REJECT_CODES:
        if text.startswith(prefix):
            return code
    return "OTHER"


@dataclass(frozen=True)
class PennyLifecycleConfig:
    tickers: tuple[str, ...]
    book: str = "PENNY_PAPER"
    regime: str = "PR1_CALM"
    session_policy: str = "complete_only"
    candidate_policy: str = "BASELINE"

    def __post_init__(self):
        clean = tuple(sorted({str(t).strip().upper() for t in self.tickers if str(t).strip()}))
        if not clean:
            raise ValueError("at least one ticker is required")
        object.__setattr__(self, "tickers", clean)
        if self.book not in BOOKS:
            raise ValueError(f"book must be one of {BOOKS}")
        if self.regime not in REGIMES:
            raise ValueError(f"regime must be one of {REGIMES}")
        if self.session_policy not in COVERAGE_REQUIREMENTS:
            raise ValueError(f"session_policy must be one of {sorted(COVERAGE_REQUIREMENTS)}")
        if self.candidate_policy not in CANDIDATE_POLICIES:
            raise ValueError(f"candidate_policy must be one of {CANDIDATE_POLICIES}")


def settings_snapshot(book: str) -> dict:
    """Every runtime setting/constant the replay reads, frozen into the report."""
    from config import settings
    from penny_executor import MAX_ENTRY_DRIFT_PCT, STOP_LIMIT_SLIP_PCT, UNWIND_LIMIT_SLIP_PCT
    names = (
        "PENNY_BREAKOUT_TIME_START", "PENNY_BREAKOUT_TIME_END", "PENNY_BREAKOUT_TIME_EXIT",
        "PENNY_BREAKOUT_VOL_MULT", "PENNY_BREAKOUT_TARGET_R", "PENNY_BREAKOUT_BUFFER_PCT",
        "PENNY_BREAKOUT_RSI_MAX", "PENNY_BREAKOUT_USE_VWAP", "PENNY_BREAKOUT_ADAPTIVE_THRESHOLD",
        "PENNY_BREAKOUT_RVOL_TIME_ADJUSTED", "PENNY_TIME_STOP_MIN", "PENNY_MIS_SMART_EOD_TIME",
        "PENNY_MIS_SMART_EOD_WITHIN_R", "PENNY_MIS_SMART_EOD_LOSS_MIN",
        "PENNY_MAX_POSITIONS_TOTAL", "PENNY_MAX_POSITIONS_MIS", "PENNY_PER_STOCK_CAP",
        "PENNY_RISK_PCT_PR1", "PENNY_RISK_PCT_PR2", "PENNY_RISK_PCT_PR3",
        "PENNY_DAILY_KILL_SWITCH_PCT", "PENNY_DISABLE_TICKERS", "PENNY_CIRCUIT_SKIP_DISTANCE",
        "PENNY_CIRCUIT_FROM_HIGH_PCT",
    )
    snapshot = {name: getattr(settings, name) for name in names}
    snapshot["bankroll"] = float(
        settings.PENNY_PAPER_BANKROLL if book == "PENNY_PAPER" else settings.PENNY_LIVE_BANKROLL
    )
    snapshot["bankroll_setting"] = "PENNY_PAPER_BANKROLL" if book == "PENNY_PAPER" else "PENNY_LIVE_BANKROLL"
    snapshot["executor"] = {
        "MAX_ENTRY_DRIFT_PCT": MAX_ENTRY_DRIFT_PCT,
        "STOP_LIMIT_SLIP_PCT": STOP_LIMIT_SLIP_PCT,
        "UNWIND_LIMIT_SLIP_PCT": UNWIND_LIMIT_SLIP_PCT,
        "LIVE_ENTRY_LIMIT_MULTIPLIER": 1.005,
    }
    return snapshot


class _TickerDay:
    """Minute bars of one ticker-day with LTP/fill evidence lookups."""

    def __init__(self, bars):
        self.bars = bars
        self.minutes = [bar.start.hour * 60 + bar.start.minute for bar in bars]
        self.frame = pd.DataFrame(
            {
                "open": [bar.open for bar in bars], "high": [bar.high for bar in bars],
                "low": [bar.low for bar in bars], "close": [bar.close for bar in bars],
                "volume": [bar.volume for bar in bars],
            },
            index=pd.DatetimeIndex([bar.start.replace(tzinfo=None) for bar in bars], name="datetime"),
        )
        self.traded_positions = [i for i, bar in enumerate(bars) if bar.executable]

    def completed_count(self, boundary: int) -> int:
        """Number of bars that started before ``boundary`` (complete at it)."""
        return bisect_left(self.minutes, boundary)

    def bar_at(self, minute: int):
        index = bisect_left(self.minutes, minute)
        if index < len(self.minutes) and self.minutes[index] == minute:
            return index, self.bars[index]
        return None, None

    def ltp_at(self, boundary: int) -> tuple[float | None, bool]:
        """(price, executable) a quote would show just after ``boundary``."""
        index, bar = self.bar_at(boundary)
        if bar is not None and bar.executable:
            return bar.open, True
        upto = bisect_left(self.minutes, boundary)
        for position in range(upto - 1, -1, -1):
            if self.bars[position].executable:
                return self.bars[position].close, False
        return None, False

    def first_traded_from(self, minute: int):
        start = bisect_left(self.minutes, minute)
        for position in range(start, len(self.bars)):
            if self.bars[position].executable:
                return position, self.bars[position]
        return None, None


def _aware(day: date, minute: int) -> datetime:
    return datetime(day.year, day.month, day.day, minute // 60, minute % 60, tzinfo=IST)


def _round(value, digits=4):
    return None if value is None else round(float(value), digits)


class _Replay:
    def __init__(self, intraday: IntradayDataset, daily: DailyDataset,
                 config: PennyLifecycleConfig, start: date, end: date):
        from config import settings
        from penny_models import PennyRegime
        from penny_risk import PennyRiskEngine
        from penny_shadow import _execution_snapshot
        self.settings = settings
        self.config = config
        self.start, self.end = start, end
        self.intraday, self.daily = intraday, daily
        self.snapshot = settings_snapshot(config.book)
        self.regime = PennyRegime(config.regime)
        self.risk = PennyRiskEngine(bankroll=self.snapshot["bankroll"])
        self.execution = _execution_snapshot("LIFECYCLE_REPLAY")
        self.requirement = COVERAGE_REQUIREMENTS[config.session_policy]
        self.reject_counts: Counter = Counter()
        self.admission_counts: Counter = Counter()
        self.evaluations = 0
        self.accepted_signals = 0
        self.trader_counts: Counter = Counter()
        self.trades: list[dict] = []
        self.exclusions: list[dict] = []
        self.usable: list[tuple[str, str]] = []

    # ---- coverage ----------------------------------------------------
    def _select_days(self) -> dict:
        by_day: dict = defaultdict(list)
        for row in self.intraday.coverage:
            ticker, day_text = row["ticker"], row["trading_date"]
            if ticker not in self.config.tickers or not self.start.isoformat() <= day_text <= self.end.isoformat():
                continue
            reason = None
            if row["status"] not in self.requirement.usable_statuses:
                reason = f"coverage_{row['status'].lower()}:" + ",".join(row["reasons"])
            elif ticker in self.daily.invalid:
                reason = "daily_history_invalid"
            else:
                day = date.fromisoformat(day_text)
                warmup_start = day - timedelta(days=MEDIAN_LOOKBACK_CALENDAR_DAYS)
                if self.daily.actions_between(ticker, warmup_start, day - timedelta(days=1)):
                    reason = "suspected_corporate_action_in_warmup"
                elif self.daily.off_calendar_between(ticker, warmup_start, day - timedelta(days=1)):
                    reason = "off_calendar_daily_row_in_warmup"
            if reason:
                self.exclusions.append({"ticker": ticker, "trading_date": day_text, "reason": reason})
                continue
            by_day[day_text].append(ticker)
            self.usable.append((ticker, day_text))
        return {day: sorted(tickers) for day, tickers in sorted(by_day.items())}

    # ---- entry inputs (mirror PennyScanner._evaluate_ticker_breakout) ----
    def _median_volume(self, ticker: str, day: date) -> int:
        window = self.daily.known_before(
            ticker, day, since=day - timedelta(days=MEDIAN_LOOKBACK_CALENDAR_DAYS),
        )
        if len(window) < 5:
            return 0
        volumes = pd.Series([bar.volume for bar in window], dtype="float64")
        return int(volumes.tail(20).median() or 0)

    def _prev_close(self, ticker: str, day: date) -> float | None:
        prior = self.daily.known_before(ticker, day)
        return prior[-1].close if prior else None

    def _same_minute_volume_profile(self, ticker: str, day: date, boundary: int) -> list[float]:
        """Prior-session cumulative volume at this exact completed-bar clock."""
        profile = []
        for (known_ticker, known_day), bars in self.intraday.bars.items():
            if known_ticker != ticker or known_day >= day.isoformat():
                continue
            td = _TickerDay(bars)
            count = td.completed_count(boundary)
            # Gap-sensitivity datasets also contain partial sessions. Require
            # every minute up to the same boundary: missing opening minutes
            # cannot become a deceptively low cumulative-volume baseline.
            expected = boundary - (SESSION_FIRST_BOUNDARY - 1)
            if expected > 0 and td.minutes[:count] == list(range(SESSION_FIRST_BOUNDARY - 1, boundary)):
                profile.append(sum(float(bar.volume) for bar in td.bars[:count]))
        return profile

    def _hard_constraint(self, ticker: str, day: date, td: _TickerDay, boundary: int) -> str | None:
        """Shipped scanner hard blocks shared by every policy: regime, disabled
        ticker, quote evidence and circuit proximity. A candidate never skips them."""
        from penny_risk import PennyRiskEngine
        if self.regime.value == "PR3_HOT":
            return "regime PR3_HOT (no new entries)"
        if self.risk.is_disabled(ticker):
            return "disabled via PENNY_DISABLE_TICKERS"
        ltp, _ = td.ltp_at(boundary)
        if ltp is None:
            return "quote_unavailable"
        completed = td.completed_count(boundary)
        quote_highs = [td.bars[i].high for i in range(completed)] + [ltp]
        quote_lows = [td.bars[i].low for i in range(completed)] + [ltp]
        day_high, day_low = max(quote_highs), min(quote_lows)
        prev_close = self._prev_close(ticker, day)
        if prev_close and prev_close > 0:
            band_pct = PennyRiskEngine.band_pct_from_quote(
                quote={}, prev_close=float(prev_close), day_high=float(day_high), day_low=float(day_low),
            )
            blocked, why = self.risk.circuit_blocked(
                last_price=float(ltp), day_high=float(day_high),
                prev_close=float(prev_close), band_pct=band_pct,
            )
            if blocked:
                return f"circuit_blocked: {why}"
        return None

    def _evaluate(self, ticker: str, day: date, td: _TickerDay, boundary: int) -> dict:
        from penny_engine_breakout import _rsi_14_wilder, evaluate_breakout_entry
        as_of = _aware(day, boundary)
        blocked = self._hard_constraint(ticker, day, td, boundary)
        if blocked:
            return {"accept": False, "reject_reason": blocked}
        completed = td.completed_count(boundary)
        index_k, bar_k = td.bar_at(boundary)
        fetched = completed + (1 if bar_k is not None else 0)
        if fetched < 2:
            return {"accept": False, "reject_reason": "insufficient_intraday_bars"}
        if completed < 1:
            return {"accept": False, "reject_reason": "zero_complete_bars_after_drop"}
        if completed < 2:
            return {"accept": False, "reject_reason": "no prior bars to anchor breakout"}
        visible = td.frame.iloc[:completed]
        last = td.bars[completed - 1]
        median = self._median_volume(ticker, day)
        if median <= 0:
            return {"accept": False, "reject_reason": "no 20-day median volume baseline"}
        decision = evaluate_breakout_entry(
            ticker=ticker,
            cum_vol_today=int(visible["volume"].sum()),
            median_vol_20d=median,
            breakout_bar={"open": last.open, "high": last.high, "low": last.low,
                          "close": last.close, "volume": int(last.volume)},
            day_high=float(visible["high"].iloc[:-1].max()),
            rsi_14=_rsi_14_wilder([float(value) for value in visible["close"].tolist()]),
            as_of=as_of, risk_engine=self.risk, intraday=visible, regime=self.regime,
        )
        decision["_evaluation_bar_ts"] = last.start.isoformat()
        decision["_median_vol_20d"] = median
        decision["_cum_vol_today"] = int(visible["volume"].sum())
        if decision.get("accept") and self.config.candidate_policy == "PEN_CONTEXT":
            from non_fno_research import penny_context_gate
            gate = penny_context_gate(
                decision,
                [{"open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close, "volume": bar.volume}
                 for bar in td.bars[:completed]],
                self._same_minute_volume_profile(ticker, day, boundary),
            )
            decision["candidate_context"] = gate
            if not gate["accepted"]:
                decision["accept"] = False
                decision["reject_reason"] = "PEN_CONTEXT:" + gate["reason"]
        return decision

    # ---- trade bookkeeping ------------------------------------------
    def _open(self, ticker, day, td, boundary, decision, fill_price, fill_index):
        fill_bar = td.bars[fill_index]
        return {
            "ticker": ticker, "trading_date": day.isoformat(), "book": self.config.book,
            "decision_bar_ts": decision["_evaluation_bar_ts"],
            "as_of": _aware(day, boundary).isoformat(),
            "signal_entry": float(decision["entry"]), "stop_price": float(decision["stop_loss"]),
            "target_price": float(decision["target"]), "shares": int(decision["shares"]),
            "entry_fill_ts": fill_bar.start.isoformat(), "entry_fill_price": float(fill_price),
            "entry_time_utc": _aware(day, boundary).astimezone(timezone.utc).isoformat(),
            "rsi_14": decision.get("rsi_14"), "median_vol_20d": decision["_median_vol_20d"],
            "cum_vol_today": decision["_cum_vol_today"],
            "status": "OPEN", "_fill_index": fill_index,
            "_high": fill_bar.high, "_low": fill_bar.low,
        }

    def _close(self, trade, td, exit_index, exit_price, reason, decided_at):
        from penny_shadow import _costs_from_snapshot
        exit_bar = td.bars[exit_index]
        for i in range(trade["_fill_index"], exit_index + 1):
            bar = td.bars[i]
            if bar.executable:
                trade["_high"] = max(trade["_high"], bar.high)
                trade["_low"] = min(trade["_low"], bar.low)
        entry, shares = trade["entry_fill_price"], trade["shares"]
        # A trailed stop moves; R is always measured against the initial stop.
        risk_per_share = entry - trade.get("initial_stop_price", trade["stop_price"])
        partials = [(float(leg["price"]), int(leg["quantity"])) for leg in trade.get("partial_fills", [])]
        legs = partials + [(float(exit_price), shares - sum(q for _, q in partials))]
        gross = sum((price - entry) * quantity for price, quantity in legs)
        costs = round(sum(_costs_from_snapshot(entry, price, quantity, self.execution)
                          for price, quantity in legs), 4)
        net = gross - costs
        executor = self.snapshot["executor"]
        worst_entry = entry * executor["LIVE_ENTRY_LIMIT_MULTIPLIER"]
        slip = 1 - max(executor["STOP_LIMIT_SLIP_PCT"], executor["UNWIND_LIMIT_SLIP_PCT"])
        adverse = sum((price * slip - worst_entry) * quantity - _costs_from_snapshot(
            worst_entry, price * slip, quantity, self.execution) for price, quantity in legs)
        trade.update({
            "status": "CLOSED", "exit_reason": reason, "exit_decided_at": decided_at.isoformat(),
            "exit_fill_ts": exit_bar.start.isoformat(), "exit_fill_price": round(float(exit_price), 4),
            "gross_pnl": round(gross, 4), "costs": costs, "net_pnl": round(net, 4),
            "r_multiple": round(net / (risk_per_share * shares), 6) if risk_per_share > 0 else None,
            "mfe_r": round((trade["_high"] - entry) / risk_per_share, 6) if risk_per_share > 0 else None,
            "mae_r": round((entry - trade["_low"]) / risk_per_share, 6) if risk_per_share > 0 else None,
            "holding_minutes": int((exit_bar.start - td.bars[trade["_fill_index"]].start).total_seconds() // 60),
            "adverse_fill_bound_net": round(adverse, 4),
        })

    def _exit_via_market(self, trade, td, boundary, reason, day):
        """Exit decided at ``boundary``: fill at the first traded bar at/after it."""
        index, bar = td.first_traded_from(boundary)
        if bar is None:
            trade.update({"status": "UNRESOLVED", "exit_reason": f"UNRESOLVED_NO_EXIT_EVIDENCE:{reason}",
                          "exit_decided_at": _aware(day, boundary).isoformat()})
            return
        self._close(trade, td, index, bar.open, reason, _aware(day, boundary))

    def _check_stop(self, trade, td, boundary, now, day):
        """Paper 60-second LTP stop monitor, or the broker stop approximation."""
        if self.config.book == "PENNY_PAPER":
            ltp, executable = td.ltp_at(boundary)
            if ltp is not None and ltp <= trade["stop_price"]:
                if executable:
                    index, _ = td.bar_at(boundary)
                    self._close(trade, td, index, ltp, "PAPER_STOP_LTP", now)
                else:
                    self._exit_via_market(trade, td, boundary, "PAPER_STOP_LTP", day)
        else:
            index, bar = td.bar_at(boundary - 1)
            if bar is not None and bar.executable and index >= trade["_fill_index"]:
                if index > trade["_fill_index"] and bar.open <= trade["stop_price"]:
                    self._close(trade, td, index, bar.open, "BROKER_STOP_GAP", now)
                elif bar.low <= trade["stop_price"]:
                    self._close(trade, td, index, trade["stop_price"], "BROKER_STOP", now)

    # ---- day loop ---------------------------------------------------
    def run_day(self, day_text: str, tickers: list[str]):
        if self.config.candidate_policy in TRADER_POLICIES:
            return self._run_day_trader(day_text, tickers)
        from penny_engine_breakout import mis_time_stop_active, smart_eod_check, time_stop_triggered
        settings = self.settings
        day = date.fromisoformat(day_text)
        tds = {ticker: _TickerDay(self.intraday.bars[(ticker, day_text)]) for ticker in tickers}
        open_trades: dict[str, dict] = {}
        eod_minute = int(settings.PENNY_MIS_SMART_EOD_TIME)
        force_minute = int(settings.PENNY_BREAKOUT_TIME_EXIT)
        for boundary in range(SESSION_FIRST_BOUNDARY, SESSION_LAST_BOUNDARY + 1):
            now = _aware(day, boundary)
            # 1. protective stops
            for ticker in sorted(open_trades):
                trade, td = open_trades[ticker], tds[ticker]
                self._check_stop(trade, td, boundary, now, day)
                if trade["status"] != "OPEN":
                    del open_trades[ticker]
            # 2. 14:30 smart-EOD job (run_penny_eod_check branch order)
            if boundary == eod_minute:
                for ticker in sorted(open_trades):
                    trade, td = open_trades[ticker], tds[ticker]
                    ltp, _ = td.ltp_at(boundary)
                    current = ltp if ltp is not None else trade["entry_fill_price"]
                    position = {
                        "entry_price": trade["entry_fill_price"],
                        "stop_loss_initial": trade["stop_price"],
                        "target_1": trade["target_price"],
                        "entry_date": trade["entry_time_utc"],
                    }
                    if current < trade["entry_fill_price"] and time_stop_triggered(trade["entry_time_utc"], now):
                        decision = {"action": "exit_now", "reason": "time_stop_30min_in_loss"}
                    else:
                        decision = smart_eod_check(position, current, now)
                    trade.setdefault("smart_eod", {"action": decision["action"], "reason": decision["reason"],
                                                   "ltp": _round(current)})
                    if decision["action"] == "exit_now":
                        self._exit_via_market(trade, td, boundary, f"SMART_EOD:{decision['reason']}", day)
                        del open_trades[ticker]
            # 3. 15:00 force close
            if boundary == force_minute and mis_time_stop_active(now):
                for ticker in sorted(open_trades):
                    self._exit_via_market(open_trades[ticker], tds[ticker], boundary, "MIS_TIME_STOP_1500", day)
                open_trades.clear()
            # 4. scan (scheduler runs the paper stop monitor, then the scanner)
            for ticker in tickers:
                td = tds[ticker]
                if td.bar_at(boundary - 1)[1] is None:
                    continue  # no newly completed bar: nothing new to evaluate (no forward-fill)
                self.evaluations += 1
                decision = self._evaluate(ticker, day, td, boundary)
                if not decision.get("accept"):
                    self.reject_counts[reject_code(decision.get("reject_reason"))] += 1
                    continue
                self.accepted_signals += 1
                outcome = self._admit(ticker, day, td, boundary, decision, open_trades)
                self.admission_counts[outcome] += 1
        for ticker in sorted(open_trades):
            trade = open_trades[ticker]
            trade.update({"status": "UNRESOLVED", "exit_reason": "UNRESOLVED_SESSION_DATA_ENDED"})

    # ---- PEN_TRADER_V1 candidates (research only) ---------------------
    def _completed_bars(self, td: _TickerDay, ticker: str):
        from adaptive_penny_policy import CompletedBar
        return [CompletedBar(f"{ticker}|{bar.start.isoformat()}", bar.start, bar.available_at,
                             bar.open, bar.high, bar.low, bar.close, bar.volume) for bar in td.bars]

    def _run_day_trader(self, day_text: str, tickers: list[str]):
        """Same clock, quotes, stop monitor, square-off, costs and cash as the
        baseline; different entry recognition (and, for THESIS, exits)."""
        from adaptive_penny_policy import (
            DEFAULT_PARAMS, TickerMemory, advance_setup, detect_breakout, manage_position,
            resting_partial,
        )
        from penny_engine_breakout import mis_time_stop_active, smart_eod_check, time_stop_triggered
        params, thesis_exits = trader_policy(self.config.candidate_policy)
        base_entries = params is None
        params = params or DEFAULT_PARAMS   # exit parameters for shipped entries
        day = date.fromisoformat(day_text)
        tds = {ticker: _TickerDay(self.intraday.bars[(ticker, day_text)]) for ticker in tickers}
        cbars = {ticker: self._completed_bars(td, ticker) for ticker, td in tds.items()}
        medians = {ticker: self._median_volume(ticker, day) for ticker in tickers}
        setups: dict = {}
        detection: dict = {}
        memory: dict = defaultdict(TickerMemory)
        open_trades: dict[str, dict] = {}
        eod_minute = int(self.settings.PENNY_MIS_SMART_EOD_TIME)
        force_minute = int(self.settings.PENNY_BREAKOUT_TIME_EXIT)

        def settle(ticker, trade, now):
            if trade["status"] == "CLOSED" and trade["net_pnl"] < 0:
                memory[ticker] = memory[ticker].after_failure(trade["anchor"], now, params)
            open_trades.pop(ticker, None)

        for boundary in range(SESSION_FIRST_BOUNDARY, SESSION_LAST_BOUNDARY + 1):
            now = _aware(day, boundary)
            # 1. a resting partial limit fills inside the bar that just completed
            #    (before this minute's LTP poll), then the protective stop.
            for ticker in sorted(open_trades):
                trade, td = open_trades[ticker], tds[ticker]
                index, _ = td.bar_at(boundary - 1)
                if thesis_exits and index is not None and index >= trade["_fill_index"] and td.bars[index].executable:
                    partial = resting_partial(trade["_thesis"], cbars[ticker][index], params)
                    if partial.partial_quantity:
                        trade["_thesis"] = partial.position
                        trade.setdefault("partial_fills", []).append({
                            "price": round(partial.partial_price, 6), "quantity": partial.partial_quantity,
                            "fill_ts": td.bars[index].start.isoformat(), "reason": "RESTING_PARTIAL_2R"})
                self._check_stop(trade, td, boundary, now, day)
                if trade["status"] != "OPEN":
                    settle(ticker, trade, now)
            # 2. exit management on the completed bar
            for ticker in sorted(open_trades):
                trade, td = open_trades[ticker], tds[ticker]
                if thesis_exits:
                    index, _ = td.bar_at(boundary - 1)
                    if index is None or index < trade["_fill_index"]:
                        continue
                    outcome = manage_position(trade["_thesis"], cbars[ticker][index], decision_at=now, params=params)
                    trade["_thesis"] = outcome.position
                    if outcome.new_stop is not None:
                        trade["stop_price"] = outcome.new_stop
                        trade["stop_raises"] = trade.get("stop_raises", 0) + 1
                    if outcome.exit_reason:
                        self._exit_via_market(trade, td, boundary, outcome.exit_reason, day)
                        settle(ticker, trade, now)
                elif boundary == eod_minute:
                    ltp, _ = td.ltp_at(boundary)
                    current = ltp if ltp is not None else trade["entry_fill_price"]
                    position = {"entry_price": trade["entry_fill_price"], "stop_loss_initial": trade["stop_price"],
                                "target_1": trade["target_price"], "entry_date": trade["entry_time_utc"]}
                    if current < trade["entry_fill_price"] and time_stop_triggered(trade["entry_time_utc"], now):
                        decision = {"action": "exit_now", "reason": "time_stop_30min_in_loss"}
                    else:
                        decision = smart_eod_check(position, current, now)
                    trade.setdefault("smart_eod", {"action": decision["action"], "reason": decision["reason"],
                                                   "ltp": _round(current)})
                    if decision["action"] == "exit_now":
                        self._exit_via_market(trade, td, boundary, f"SMART_EOD:{decision['reason']}", day)
                        settle(ticker, trade, now)
            # 3. 15:00 force close
            if boundary == force_minute and mis_time_stop_active(now):
                for ticker in sorted(open_trades):
                    trade = open_trades[ticker]
                    self._exit_via_market(trade, tds[ticker], boundary, "MIS_TIME_STOP_1500", day)
                    settle(ticker, trade, now)
            # 4. recognise/advance setups, then admit intents by evidence rank
            if base_entries:
                self._scan_shipped_entries(day, tds, tickers, boundary, open_trades, cbars, params)
                continue
            intents = []
            for ticker in tickers:
                td = tds[ticker]
                index, _ = td.bar_at(boundary - 1)
                if index is None or ticker in open_trades:
                    continue
                self.evaluations += 1
                bars = cbars[ticker][:index + 1]
                setup = setups.get(ticker)
                if setup is not None:
                    outcome = advance_setup(setup, bars[-1], decision_at=now, params=params)
                    self.trader_counts["advance:" + outcome.action.lower() + ":" + outcome.reason] += 1
                    if outcome.action in ("INVALIDATED", "EXPIRED", "TERMINAL"):
                        setups.pop(ticker, None)
                        detection.pop(ticker, None)
                        if outcome.action == "INVALIDATED":
                            memory[ticker] = memory[ticker].after_failure(setup.anchor, now, params)
                        continue
                    setups[ticker] = outcome.setup
                else:
                    outcome = detect_breakout(ticker=ticker, bars=bars, median_vol_20d=medians[ticker],
                                              decision_at=now, params=params)
                    if outcome.setup is None:
                        self.reject_counts[outcome.reason] += 1
                        for failure in outcome.evidence.get("verdict", {}).get("failures", []):
                            self.trader_counts["condition_failed:" + failure] += 1
                        continue
                    blocked = memory[ticker].allows(anchor=outcome.setup.anchor, now=now, params=params)
                    if blocked:
                        self.reject_counts[blocked] += 1
                        continue
                    self.trader_counts["detected:" + outcome.action.lower()] += 1
                    setups[ticker] = outcome.setup
                    detection[ticker] = outcome.evidence
                if outcome.intent is not None:
                    blocked = self._hard_constraint(ticker, day, td, boundary)
                    setups.pop(ticker, None)   # an intent is one-shot; never reused later
                    evidence = detection.pop(ticker, None)
                    if not outcome.evidence and evidence:
                        outcome = replace(outcome, evidence=evidence)
                    if blocked:
                        self.reject_counts[reject_code(blocked)] += 1
                        continue
                    self.accepted_signals += 1
                    intents.append((ticker, outcome))
            intents.sort(key=lambda item: (-(item[1].intent.score or 0.0), item[0]))
            for ticker, outcome in intents:
                result = self._admit_trader(ticker, day, tds[ticker], boundary, outcome, open_trades, cbars[ticker])
                self.admission_counts[result] += 1
                if result == "FILLED":
                    memory[ticker] = memory[ticker].after_entry(outcome.intent.anchor)
        for ticker in sorted(open_trades):
            open_trades[ticker].update({"status": "UNRESOLVED", "exit_reason": "UNRESOLVED_SESSION_DATA_ENDED"})

    def _scan_shipped_entries(self, day, tds, tickers, boundary, open_trades, cbars, params):
        """PEN_BASE_THESIS: the unchanged shipped evaluator/admission, then a
        thesis record so only the exit policy differs from BASELINE."""
        from adaptive_penny_policy import EntryPlan, open_thesis_position
        from penny_shadow import _costs_from_snapshot
        for ticker in tickers:
            td = tds[ticker]
            index, _ = td.bar_at(boundary - 1)
            if index is None:
                continue
            self.evaluations += 1
            decision = self._evaluate(ticker, day, td, boundary)
            if not decision.get("accept"):
                self.reject_counts[reject_code(decision.get("reject_reason"))] += 1
                continue
            self.accepted_signals += 1
            outcome = self._admit(ticker, day, td, boundary, decision, open_trades)
            self.admission_counts[outcome] += 1
            if outcome != "FILLED":
                continue
            trade = open_trades[ticker]
            entry, stop, shares = trade["entry_fill_price"], trade["stop_price"], trade["shares"]
            visible = cbars[ticker][:index + 1]
            ranges = [bar.high - bar.low for bar in visible[-14:]]
            atr = max(sum(ranges) / len(ranges), params.tick) if ranges else params.tick
            plan = EntryPlan("BASE-" + ticker + "-" + trade["entry_fill_ts"], entry, stop, shares, entry - stop,
                             round((entry - stop) * shares, 6), round(entry * shares, 6),
                             _costs_from_snapshot(entry, stop, shares, self.execution))
            # The shipped breakout level is the thesis structure; it must sit
            # above the stop for the failed-breakout rule to be meaningful.
            anchor = max(min(float(decision["breakout_level"]), entry - params.tick), stop + params.tick)
            trade.update({"policy": self.config.candidate_policy, "thesis_id": plan.thesis_id,
                          "entry_kind": "SHIPPED_BREAKOUT", "baseline_status": "baseline_accepted",
                          "anchor": anchor, "initial_stop_price": stop})
            trade["_thesis"] = open_thesis_position(plan, ticker=ticker, anchor=anchor, atr=atr,
                                                    entry_at=_aware(day, boundary))

    def _admit_trader(self, ticker, day, td, boundary, outcome, open_trades, bars) -> str:
        from adaptive_penny_policy import DEFAULT_PARAMS, open_thesis_position, plan_entry
        from penny_shadow import _costs_from_snapshot
        settings, intent = self.settings, outcome.intent
        if (len(open_trades) >= settings.PENNY_MAX_POSITIONS_MIS
                or len(open_trades) >= settings.PENNY_MAX_POSITIONS_TOTAL):
            return "CAPACITY_REJECTED"
        ltp, executable = td.ltp_at(boundary)
        if ltp is None:
            return "NO_QUOTE"
        if abs(ltp - intent.intended_price) / intent.intended_price > self.snapshot["executor"]["MAX_ENTRY_DRIFT_PCT"]:
            return "DRIFT_REJECTED"
        if intent.stop >= ltp:
            return "STOP_ALREADY_BREACHED"
        if not executable:
            return "NO_EXECUTABLE_EVIDENCE"
        # Own cash only: open notional plus this entry can never exceed the book.
        committed = sum(t["entry_fill_price"] * t["shares"] for t in open_trades.values())
        available = self.snapshot["bankroll"] - committed
        if available <= 0:
            return "CASH_REJECTED"
        max_shares = self.risk.position_size(ltp, intent.stop, self.regime)
        risk_budget = self.snapshot["bankroll"] * self.risk._risk_pct_for_regime(self.regime)
        if max_shares <= 0 or risk_budget <= 0:
            return "SIZE_ZERO"
        plan = plan_entry(intent, executable_price=ltp, own_cash=available, risk_budget=risk_budget,
                          per_position_cash_cap=float(settings.PENNY_PER_STOCK_CAP), max_shares=max_shares,
                          round_trip_cost=lambda e, x, q: _costs_from_snapshot(e, x, q, self.execution))
        if plan is None:
            return "PLAN_REJECTED"
        index, fill_bar = td.bar_at(boundary)
        baseline = self._evaluate(ticker, day, td, boundary)
        evidence = outcome.evidence or {}
        trade = {
            "ticker": ticker, "trading_date": day.isoformat(), "book": self.config.book,
            "policy": self.config.candidate_policy, "thesis_id": intent.thesis_id,
            "decision_bar_ts": td.bars[index - 1].start.isoformat() if index else None,
            "as_of": _aware(day, boundary).isoformat(),
            "entry_kind": intent.entry_kind, "score": intent.score,
            "baseline_status": "baseline_accepted" if baseline.get("accept") else "baseline_rejected",
            "baseline_reject_code": None if baseline.get("accept") else reject_code(baseline.get("reject_reason")),
            "score_components": (evidence.get("verdict") or {}).get("components"),
            "anchor": intent.anchor, "signal_entry": float(intent.intended_price),
            "stop_price": float(plan.stop), "initial_stop_price": float(plan.stop),
            "target_price": round(ltp + 2 * (ltp - plan.stop), 4), "shares": int(plan.shares),
            "entry_fill_ts": fill_bar.start.isoformat(), "entry_fill_price": float(ltp),
            "entry_time_utc": _aware(day, boundary).astimezone(timezone.utc).isoformat(),
            "planned_risk_rupees": plan.risk_rupees, "planned_round_trip_cost": plan.round_trip_cost,
            "median_vol_20d": self._median_volume(ticker, day),
            "status": "OPEN", "_fill_index": index, "_high": fill_bar.high, "_low": fill_bar.low,
        }
        atr = float(((evidence.get("context") or {}).get("atr")) or 0.0)
        if not atr:
            atr = max(DEFAULT_PARAMS.tick, (plan.entry_price - plan.stop) / 2)
        trade["_thesis"] = open_thesis_position(plan, ticker=ticker, anchor=intent.anchor, atr=atr,
                                                entry_at=_aware(day, boundary))
        self.trades.append(trade)
        open_trades[ticker] = trade
        return "FILLED"

    def _admit(self, ticker, day, td, boundary, decision, open_trades) -> str:
        settings = self.settings
        if ticker in open_trades:
            return "OCCUPIED_SAME_TICKER"
        if (len(open_trades) >= settings.PENNY_MAX_POSITIONS_MIS
                or len(open_trades) >= settings.PENNY_MAX_POSITIONS_TOTAL):
            return "CAPACITY_REJECTED"
        ltp, executable = td.ltp_at(boundary)
        if ltp is None:
            return "NO_QUOTE"
        entry, stop = float(decision["entry"]), float(decision["stop_loss"])
        drift = abs(ltp - entry) / entry if entry else 1.0
        if drift > self.snapshot["executor"]["MAX_ENTRY_DRIFT_PCT"]:
            return "DRIFT_REJECTED"
        if stop >= ltp:
            return "STOP_ALREADY_BREACHED"
        if not executable:
            return "NO_EXECUTABLE_EVIDENCE"
        index, _ = td.bar_at(boundary)
        trade = self._open(ticker, day, td, boundary, decision, ltp, index)
        self.trades.append(trade)
        open_trades[ticker] = trade
        return "FILLED"


def _summary(trades: list[dict], bankroll: float, kill_pct: float) -> dict:
    closed = [t for t in trades if t["status"] == "CLOSED"]
    unresolved = [t for t in trades if t["status"] == "UNRESOLVED"]
    if not closed:
        return {
            "paper_entries": len(trades), "closed_trades": 0, "unresolved_trades": len(unresolved),
            "gross_pnl": None, "costs": None, "net_pnl": None, "win_rate_pct": None,
            "profit_factor": None, "expectancy": None, "avg_r": None, "max_drawdown": None,
            "net_excluding_best_winner": None, "adverse_fill_bound_net": None,
            "exit_reasons": dict(Counter(t["exit_reason"] for t in unresolved)),
            "per_day": [], "kill_switch_threshold_breached_days": [],
        }
    net = [t["net_pnl"] for t in closed]
    wins = [x for x in net if x > 0]
    losses = [x for x in net if x < 0]
    running = peak = drawdown = 0.0
    for trade in sorted(closed, key=lambda t: (t["exit_fill_ts"], t["ticker"])):
        running += trade["net_pnl"]
        peak = max(peak, running)
        drawdown = max(drawdown, peak - running)
    per_day: dict = defaultdict(lambda: {"closed": 0, "net_pnl": 0.0, "wins": 0})
    for trade in closed:
        row = per_day[trade["trading_date"]]
        row["closed"] += 1
        row["net_pnl"] += trade["net_pnl"]
        row["wins"] += int(trade["net_pnl"] > 0)
    threshold = -bankroll * kill_pct
    best = max(net)
    return {
        "paper_entries": len(trades), "closed_trades": len(closed),
        "unresolved_trades": len(unresolved),
        "gross_pnl": round(sum(t["gross_pnl"] for t in closed), 4),
        "costs": round(sum(t["costs"] for t in closed), 4),
        "net_pnl": round(sum(net), 4),
        "win_rate_pct": round(100 * len(wins) / len(closed), 4),
        "profit_factor": round(sum(wins) / abs(sum(losses)), 6) if losses else None,
        "expectancy": round(sum(net) / len(closed), 4),
        "avg_r": round(sum(t["r_multiple"] for t in closed) / len(closed), 6),
        "max_drawdown": round(drawdown, 4),
        "net_excluding_best_winner": round(sum(net) - best, 4) if best > 0 else round(sum(net), 4),
        "adverse_fill_bound_net": round(sum(t["adverse_fill_bound_net"] for t in closed), 4),
        "exit_reasons": dict(sorted(Counter(t["exit_reason"] for t in trades if t["status"] != "OPEN").items())),
        "per_day": [{"trading_date": day, **{k: round(v, 4) if isinstance(v, float) else v for k, v in row.items()}}
                    for day, row in sorted(per_day.items())],
        "kill_switch_threshold_breached_days": sorted(
            day for day, row in per_day.items() if row["net_pnl"] <= threshold
        ),
    }


def _trader_breakdown(trades: list[dict]) -> dict:
    """Net outcome by entry kind and by baseline status (recovered setups)."""
    out: dict = {}
    for key in ("entry_kind", "baseline_status", "exit_reason"):
        groups: dict = defaultdict(lambda: {"trades": 0, "closed": 0, "net_pnl": 0.0, "wins": 0})
        for trade in trades:
            row = groups[str(trade.get(key))]
            row["trades"] += 1
            if trade["status"] == "CLOSED":
                row["closed"] += 1
                row["net_pnl"] = round(row["net_pnl"] + trade["net_pnl"], 4)
                row["wins"] += int(trade["net_pnl"] > 0)
        out[key] = dict(sorted(groups.items()))
    return out


def run_penny_lifecycle(
    intraday: IntradayDataset, daily: DailyDataset, config: PennyLifecycleConfig,
    *, start: str, end: str,
) -> dict:
    """Replay the classic Penny MIS book over validated datasets; never fetches."""
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if last < first:
        raise ValueError("end must not precede start")
    if intraday.interval.label != "minute":
        raise ValueError("the classic Penny MIS lifecycle requires the minute interval")
    replay = _Replay(intraday, daily, config, first, last)
    days = replay._select_days()
    for day_text, tickers in days.items():
        replay.run_day(day_text, tickers)
    for trade in replay.trades:
        for key in [k for k in trade if k.startswith("_")]:
            trade.pop(key)
    snapshot = replay.snapshot
    summary = _summary(replay.trades, snapshot["bankroll"], snapshot["PENNY_DAILY_KILL_SWITCH_PCT"])
    requested_days = [row for row in intraday.coverage
                      if row["ticker"] in config.tickers and start <= row["trading_date"] <= end]
    if not replay.usable:
        status = "UNAVAILABLE"
    elif replay.exclusions or summary["unresolved_trades"]:
        status = "PARTIAL"
    else:
        status = "COMPLETE"
    candidate_params = None
    if config.candidate_policy in TRADER_POLICIES:
        from adaptive_penny_policy import DEFAULT_PARAMS
        params, thesis_exits = trader_policy(config.candidate_policy)
        candidate_params = {"entry": "SHIPPED_EVALUATOR" if params is None else params.to_dict(),
                            "thesis_exits": thesis_exits, "exit_params": (params or DEFAULT_PARAMS).to_dict()}
    declared = {
        "lifecycle_version": LIFECYCLE_VERSION, "config": asdict(config),
        "candidate_params": candidate_params,
        "settings": snapshot, "execution_costs": replay.execution,
        "intraday_dataset": intraday.manifest.get("dataset_sha256"),
        "daily_dataset": daily.manifest.get("dataset_sha256"),
        "requested": {"start": start, "end": end},
    }
    fingerprint = "sha256:" + hashlib.sha256(json.dumps(
        declared, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str,
    ).encode()).hexdigest()
    assumptions = {
        "clock": "bar k-1 evaluated at minute boundary k (forming bar dropped, as the live scanner does)",
        "ltp": "open of bar k if it traded, else last traded close (mark only)",
        "entry_fill": "LTP at k after executor drift/stop checks; requires a traded bar k",
        "exit_fill": ("paper stop and scheduled exits fill at the first traded bar at/after the decision"
                      if config.book == "PENNY_PAPER" else
                      "broker stop fills at the stop (or the bar open on a gap); stop-limit non-fill unmodelled"),
        "stop_model": "PAPER_LTP_POLL_60S" if config.book == "PENNY_PAPER" else "BROKER_STOP_APPROXIMATION",
        "target_exit": "none (live book never exits at target; target feeds smart-EOD only)",
        "sizing": f"PennyRiskEngine.position_size with fixed {snapshot['bankroll_setting']}",
        "regime": f"declared constant {config.regime}; historical regime not reconstructed",
        "costs": "frozen real equity MIS schedule (brokerage bypass never honoured)",
        "kill_switch": "replicated inert: runtime settlements never feed PennyRiskEngine.daily_pnl",
        "session_policy": config.session_policy,
        "coverage_assumption": replay.requirement.assumption,
        "adverse_fill_bound": "entry at LTP*1.005 (live entry limit), exits 1% worse (shipped stop/unwind limits)",
    }
    warnings = [
        "LIFECYCLE scope: not a point-in-time universe, regime or full portfolio return.",
        "Retrospective, coverage-selected, exploratory evidence; no holdout, funding or tuning authority.",
        "One-minute bars cannot show the order of trades inside a minute.",
    ]
    if config.book == "PENNY":
        warnings.append("Live broker stop-limit fills are approximated; gaps beyond the 1% limit may not fill live.")
    if candidate_params:
        assumptions["candidate_entry"] = (
            "shipped evaluate_breakout_entry and admission, unchanged" if candidate_params["entry"] == "SHIPPED_EVALUATOR"
            else "structural breakout states (pure adaptive_penny_policy); intent fills at the next LTP after the "
                 "same drift/stop/quote/circuit checks")
        assumptions["candidate_exit"] = ("thesis manager: failed-breakout/stall/14:30 loss cut, breakeven, trail, "
                                         "resting 2R half-partial" if candidate_params["thesis_exits"]
                                         else "baseline exits (stop monitor, 14:30 smart-EOD, 15:00) on the structural stop")
        assumptions["cash"] = "open notional + new entry <= bankroll; no margin/leverage"
        warnings.append("Candidate parameters were declared a priori; this window is development data, not qualification.")
    if replay.requirement.assumption:
        warnings.append(f"Coverage assumption {replay.requirement.assumption} applies to this run.")
    return {
        "schema": "sentinel_penny_lifecycle_replay_v1", "scope": SCOPE, "status": status,
        "strategy": "classic_penny_mis_breakout", "run_fingerprint": fingerprint,
        "config": asdict(config), "settings": snapshot, "assumptions": assumptions,
        "not_replayed": list(NOT_REPLAYED),
        "datasets": {"intraday": intraday.manifest, "daily": {
            k: v for k, v in daily.manifest.items()
        }},
        "coverage": {
            "requested_ticker_days": len(requested_days),
            "usable_ticker_days": len(replay.usable),
            "status_counts": dict(Counter(row["status"] for row in requested_days)),
            "exclusions": replay.exclusions,
        },
        "funnel": {
            "evaluations": replay.evaluations,
            "reject_codes": dict(sorted(replay.reject_counts.items())),
            "accepted_signals": replay.accepted_signals,
            "admission_outcomes": dict(sorted(replay.admission_counts.items())),
        },
        "summary": summary, "trades": replay.trades, "warnings": warnings,
        "candidate": None if not candidate_params else {
            "params": candidate_params, "trader_counts": dict(sorted(replay.trader_counts.items())),
            "breakdown": _trader_breakdown(replay.trades),
        },
        "can_place_orders": False, "can_qualify": False,
    }
