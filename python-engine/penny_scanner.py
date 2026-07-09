"""
[PENNY-SCANNER 2026-06-21] Orchestrator for the penny subsystem.

Spec §9. Ties together:
  - PennyUniverse (eligibility + ranking)
  - PennyRegimeEngine (regime gate)
  - PennyRiskEngine (sizing + kill-switch + caps + circuit)
  - penny_engine_connors + penny_engine_breakout (signal generators)
  - penny_signal_log (CSV + SQLite persistence)
  - kite (quote + historical fetch + place_order in live mode)

Two modes:
  - Paper (PENNY_LIVE_TRADING=False, default): signals fire, logged, but
    NO real orders via kite.place_order()
  - Live (PENNY_LIVE_TRADING=True): real orders + SL-M

Cadence (spec §9.1):
  - 30-second polling: run_penny_scanner_once() (MIS Breakout leg)
  - Once daily 09:30 IST: run_penny_connors_scan() (CNC leg)
  - 14:30 IST: smart-EOD check on open MIS positions

Hard architectural rule (enforced by tests/test_penny_isolation.py):
  this module MUST NOT import from engine, regime, risk_engine, portfolio,
  evaluate_signal, or evaluate_momentum_signal.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Callable, Optional, List
from uuid import uuid4

from penny_universe import PennyUniverse
from penny_models import PennyRegime, PennyLeg
from penny_risk import PennyRiskEngine
from penny_executor import PennyExecutor

logger = logging.getLogger(__name__)


class PennyScanner:
    def __init__(
        self,
        kite,
        universe_json_path: str,
        paper_mode: bool = True,
        regime=None,  # str (legacy, frozen) or Callable[[], str]
        daily_pnl_override: Optional[float] = None,
        ledger_writer=None,
    ):
        self.kite = kite
        self.universe_json_path = universe_json_path
        self.paper_mode = paper_mode
        # [PENNY-STARTUP-GATE 2026-07-02] Default threshold for the
        # startup-gate to consider the instrument_cache "populated".
        # NSE_EQ has ~2,000 instruments; 100 is a safe lower-bound
        # that catches the empty-cache race condition without
        # blocking when only a handful of tickers are eligible.
        # Tests can override per-instance.
        self.instrument_cache_min_count = 100
        # [AUDIT-FIX-1.3 2026-06-25] Regime used to be a frozen string
        # captured at construction. That meant a mid-day regime
        # transition (PR1->PR2->PR3) was invisible to the MIS scanner
        # until the singleton was rebuilt. The CNC scan rebuilds the
        # singleton (run_penny_connors_scan sets _penny_scanner=None),
        # but the 30s MIS loop doesn't -- so PR3_HOT (block all entries)
        # could miss a transition by hours.
        #
        # Now `regime` can be:
        #   - a string (legacy behaviour: frozen)
        #   - a callable returning the current regime (live behaviour:
        #     re-reads the regime engine every access)
        #   - None (default to PR1_CALM callable)
        # The property getter below normalises all three.
        self._regime_getter = self._normalise_regime_getter(regime)
        self.daily_pnl_override = daily_pnl_override
        # Risk engine owns sizing + kill-switch (lazy init to read bankroll)
        from config import settings
        from penny_risk import PennyRiskEngine
        bankroll = settings.PENNY_PAPER_BANKROLL if paper_mode else settings.PENNY_LIVE_BANKROLL
        # 2026-06-24 bankroll fix: pass ledger_writer through so the scanner's
        # risk_engine writes penny P&L to bankroll_ledger with source='PENNY'.
        # The writer is provided by main.py -- the scanner itself doesn't
        # import from performance (isolation rule).
        self.risk_engine = PennyRiskEngine(
            bankroll=bankroll, ledger_writer=ledger_writer,
        )
        # Executor handles the entry LIMIT -> fill poll -> SL-M -> unwind flow
        # (spec §7.2). The scanner logs + delegates; the executor places orders.
        self.executor = PennyExecutor(
            kite=kite,
            paper_mode=paper_mode,
            fill_timeout_sec=settings.PENNY_ENTRY_FILL_TIMEOUT_SEC,
            poll_interval_sec=2.0,
        )
        if daily_pnl_override is not None:
            self.risk_engine.daily_pnl = daily_pnl_override
            self.risk_engine.daily_pnl_date = datetime.now(timezone.utc).date().isoformat()

    # ---- [AUDIT-FIX-1.3] regime property + helper -------------------

    @staticmethod
    def _normalise_regime_getter(regime):
        """Convert the constructor's `regime` argument into a zero-arg
        callable returning a PennyRegime string.

        Behaviour:
          - callable (incl. bound method) -> used as-is
          - str                          -> wrapped: always returns that string
                                         (legacy frozen behaviour, preserved
                                         for any existing call sites that
                                         pass a string)
          - None                         -> wrapped: always returns "PR1_CALM"
                                         (defensive default for tests that
                                         don't construct with a regime)
        """
        if callable(regime):
            return regime
        if isinstance(regime, str):
            frozen = regime
            return lambda: frozen
        # None or anything else
        return lambda: "PR1_CALM"

    @property
    def regime(self) -> str:
        """Live regime value.

        Returns the current regime string. When the scanner was built
        with a callable (the production wiring), this re-reads the
        regime engine on every access -- so PR3_HOT transitions mid-day
        are visible to the 30s MIS scan loop without rebuilding the
        singleton.

        When the scanner was built with a string, this returns the
        frozen string (legacy behaviour, preserved for tests).
        """
        try:
            v = self._regime_getter()
        except Exception as e:
            # [AUDIT-FIX-1.3] Fail-open: if the regime getter throws
            # (e.g. the regime engine was never initialised in a test),
            # return "UNKNOWN" -- which sizes at 0% per the risk engine's
            # _risk_pct_for_regime table. Better to skip than to crash
            # the scanner loop.
            logger.warning("penny_regime_getter_failed error=%s", str(e))
            return "UNKNOWN"
        if not v:
            return "UNKNOWN"
        # Always return the .value string (handle PennyRegime enum too)
        try:
            from penny_models import PennyRegime
            if isinstance(v, PennyRegime):
                return v.value
        except Exception:
            pass
        return str(v)

    @regime.setter
    def regime(self, value):
        """Setter preserved for back-compat. Sets the regime to a
        frozen string (legacy callers expecting .regime = "..." to
        work). For live-tracking, prefer passing a callable to __init__.
        """
        self._regime_getter = self._normalise_regime_getter(value)

    def _load_universe(self) -> List[dict]:
        try:
            u = PennyUniverse(
                json_path=self.universe_json_path,
                instrument_cache=self.kite.instrument_cache,
            )
            return u.eligible_tickers()
        except Exception as e:
            logger.error("penny_universe_load_failed error=%s", str(e))
            return []

    async def _wait_for_instrument_cache(
        self, min_count: Optional[int] = None, timeout: float = 60.0,
    ) -> bool:
        """[PENNY-STARTUP-GATE 2026-07-02] Wait for the kite
        instrument_cache to be populated before running the scanner.

        Today's bug: refresh_instrument_cache() runs async on a parallel
        task, while run_penny_scanner_once fires on a 30s interval
        cron. On a fresh container restart, the first 12 minutes of
        scans ran with an EMPTY instrument_cache, logging
        `penny_universe_tokens_unresolved count=100` on every tick.
        The scanner then proceeded with `reject=0` -- no candidate
        could be tokenised, no signals generated, no orders placed.

        Fix: scan_once() awaits this helper first. If the cache has
        fewer than `min_count` entries (default 100, well below
        NSE_EQ's ~2,000), wait up to `timeout` seconds for it to
        fill. Once full, subsequent scans skip the wait (it's <1ms
        when the cache is already populated).

        Returns True if the cache is ready (either immediately or
        after waiting), False if the timeout elapsed. A False return
        causes scan_once to short-circuit to `accept=0 reject=0`
        with a logged warning -- better than 12 minutes of false
        silence.

        `min_count` defaults to the instance-level attribute
        `instrument_cache_min_count` (default 100) so tests can
        override without rewiring production code.
        """
        if min_count is None:
            min_count = getattr(self, "instrument_cache_min_count", 100)
        # Fast path: cache already populated.
        if len(self.kite.instrument_cache) >= min_count:
            return True
        # Slow path: wait up to `timeout` seconds for refresh.
        deadline = asyncio.get_event_loop().time() + timeout
        poll_interval = 1.0
        attempts = 0
        while asyncio.get_event_loop().time() < deadline:
            attempts += 1
            await asyncio.sleep(poll_interval)
            if len(self.kite.instrument_cache) >= min_count:
                logger.info(
                    "penny_instrument_cache_ready attempts=%d size=%d",
                    attempts, len(self.kite.instrument_cache),
                )
                return True
        logger.warning(
            "penny_instrument_cache_timeout attempts=%d size=%d "
            "min_required=%d -- scan will skip this tick",
            attempts, len(self.kite.instrument_cache), min_count,
        )
        return False

    async def _get_quote_safe(self, token) -> Optional[dict]:
        # [INSTRUMENT-CACHE-INT 2026-07-03] Coerce to int -- the instrument
        # cache may be populated from the CSV `refresh_instrument_cache`
        # path (str values, pre-fix) or the JSON `get_instruments_nse_eq`
        # path (int values, correct). Coercion here makes the consumer
        # safe for both. The /quote response is keyed by int via
        # `KiteClient.get_quote`'s `result = {int(k): v for k, v in ...}`,
        # so the dict lookup needs an int key.
        try:
            token_int = int(token)
        except (TypeError, ValueError):
            logger.warning(
                "penny_quote_token_coerce_failed token=%s type=%s",
                token, type(token).__name__,
            )
            return None
        try:
            quotes = await self.kite.get_quote([token_int])
            return quotes.get(token_int) if isinstance(quotes, dict) else None
        except Exception as e:
            logger.error("penny_quote_fetch_failed token=%s error=%s", token_int, str(e))
            return None

    def _regime_to_size_pct(self) -> float:
        from penny_regime import PennyRegimeEngine
        try:
            r = PennyRegime(self.regime)
        except ValueError:
            return 0.0
        return PennyRegimeEngine().size_pct(r)

    async def _evaluate_ticker_breakout(
        self, ticker: str, as_of: datetime,
        prev_close: Optional[float] = None,
        day_low: Optional[float] = None,  # passed through from quote; defaults to None for tests
    ) -> Optional[dict]:
        """Run the MIS Breakout evaluator on one ticker.

        Real 1-min intraday bars (per Uru 2026-06-22 deviation):
        - breakout_bar: latest complete 1-min candle (open/high/low/close/volume)
          fetched via kite.get_intraday(interval="minute"). The in-progress
          bar (whose timestamp minute == current minute) is dropped.
        - median_vol_20d: median cumulative volume of last 20 daily bars
          (from kite.get_historical for the same ticker).
        - rsi_14: Wilder 14-period RSI computed locally from the 1-min closes.
          Computed via penny_engine_breakout._rsi_14_wilder to keep the
          isolation rule (no import from engine.py).
        - day_high: from the live quote ohlc.high, fallback to ltp.
        - cum_vol: live cumulative volume from the quote snapshot.
        """
        from penny_engine_breakout import (
            evaluate_breakout_entry,
            _rsi_14_wilder,
        )
        token = self.kite.instrument_cache.get(ticker)
        if token is None:
            logger.warning("penny_eval_skipped ticker=%s reason=token_unresolved", ticker)
            return None

        # 1) Live quote for LTP, day high, and cumulative volume
        q = await self._get_quote_safe(token)
        if not q:
            logger.warning("penny_eval_skipped ticker=%s reason=quote_unavailable", ticker)
            return None
        ltp = q.get("last_price", 0)
        cum_vol = q.get("volume", 0) or 0
        ohlc = q.get("ohlc") or {}
        day_high = ohlc.get("high") or ltp
        day_low = ohlc.get("low") or ltp

        # [FIX-PHASE2-AUDIT 2026-07-09] Wire NSE circuit-band filter
        # (PennyRiskEngine.circuit_blocked, spec §7.4) into the MIS-leg
        # scanner. The function was implemented but never called from
        # anywhere except tests. Now that prev_close comes through from
        # the universe record at the call site, we can enforce the
        # "stay away from stocks at the daily price band" rule and
        # avoid the -5%/ATM-trap risk the spec §4.3 warns about.
        if prev_close and prev_close > 0:
            try:
                band_pct = PennyRiskEngine.infer_band_pct_from_quote(
                    prev_close=float(prev_close),
                    day_high=float(day_high) if day_high else float(prev_close),
                    day_low=float(day_low) if day_low else float(prev_close),
                )
                blocked, block_reason = self.risk_engine.circuit_blocked(
                    last_price=float(ltp), day_high=float(day_high),
                    prev_close=float(prev_close), band_pct=band_pct,
                )
                if blocked:
                    logger.info(
                        "penny_circuit_blocked ticker=%s band=%.2f%% ltp=%.2f day_high=%.2f "
                        "prev_close=%.2f reason=%s",
                        ticker, band_pct * 100, ltp, day_high, prev_close, block_reason,
                    )
                    return {
                        "accept": False,
                        "reject_reason": f"circuit_blocked: {block_reason}",
                        "ticker": ticker,
                    }
            except Exception as e:
                # Never let a circuit-check error crash the scan.
                logger.warning("penny_circuit_check_failed ticker=%s error=%s",
                               ticker, str(e))

        # 2) Real 1-min bars (cached by kite.get_intraday)
        try:
            today = as_of.strftime("%Y-%m-%d")
            start_dt = f"{today} 09:15:00"
            end_dt = as_of.strftime("%Y-%m-%d %H:%M:%S")
            intraday = await self.kite.get_intraday(
                ticker=ticker,
                from_datetime=start_dt,
                to_datetime=end_dt,
                interval="minute",
            )
        except Exception as e:
            logger.error("penny_intraday_fetch_failed ticker=%s error=%s", ticker, str(e))
            return None

        if intraday is None or len(intraday) < 2:
            # Not enough data; the day is too early or the feed is down
            logger.warning(
                "penny_eval_skipped ticker=%s reason=insufficient_intraday_bars "
                "bars=%s", ticker, 0 if intraday is None else len(intraday),
            )
            return None

        # 3) Drop the in-progress bar (its timestamp minute == current minute)
        # and use the last COMPLETE 1-min bar as the breakout bar.
        # intraday index is a DatetimeIndex from kite_client.
        try:
            last_ts = intraday.index[-1]
            if hasattr(last_ts, "minute") and last_ts.minute == as_of.minute                     and last_ts.hour == as_of.hour and last_ts.date() == as_of.date():
                intraday = intraday.iloc[:-1]
        except Exception:
            pass  # if we cannot index, fall through with the full df

        if len(intraday) < 1:
            logger.warning(
                "penny_eval_skipped ticker=%s reason=zero_complete_bars_after_drop",
                ticker,
            )
            return None

        last_bar = intraday.iloc[-1]
        breakout_bar = {
            "open":   float(last_bar.get("open", ltp)),
            "high":   float(last_bar.get("high", ltp)),
            "low":    float(last_bar.get("low",  ltp)),
            "close":  float(last_bar.get("close", ltp)),
            "volume": int(last_bar.get("volume", 0) or 0),
        }

        # 4) Real 20-day median cumulative volume
        try:
            from datetime import timedelta
            from_date = (as_of - timedelta(days=30)).strftime("%Y-%m-%d")
            to_date = today
            daily = await self.kite.get_historical(
                ticker=ticker, from_date=from_date, to_date=to_date
            )
            if daily is not None and len(daily) >= 5 and "volume" in daily.columns:
                median_vol_20d = int(daily["volume"].tail(20).median() or 0)
            else:
                median_vol_20d = 0
        except Exception as e:
            logger.error("penny_daily_vol_fetch_failed ticker=%s error=%s", ticker, str(e))
            median_vol_20d = 0

        if median_vol_20d <= 0:
            # No usable 20-day baseline. Reject rather than accept on a
            # fabricated number (deviation: was hardcoded 10_000).
            # NOTE: this is a STRUCTURED REJECT, not a silent skip, so
            # we return a dict instead of None to surface the reason
            # in the hourly diagnostic breakdown (2026-06-25).
            logger.info(
                "penny_eval_skipped ticker=%s reason=no_20d_median_volume",
                ticker,
            )
            return {
                "accept": False,
                "reject_reason": "no 20-day median volume baseline",
                "ticker": ticker,
            }

        # 5) Real RSI(14) from the 1-min closes
        closes_1m = [float(c) for c in intraday["close"].tolist()]
        rsi_14 = _rsi_14_wilder(closes_1m)

        # [FIX-PHASE2-AUDIT 2026-07-09] Feed per-ticker realized vol rank
        # into the day's regime classifier (spec §6.2, 40% weight). Pre-fix
        # update_vol_rank was never called, so _vol_rank stayed None and
        # classify() always returned PR1_CALM via the fail-open branch.
        # We compute once per ticker using the 1-min closes (which we
        # already have). The engine picks the WORST (highest) rank across
        # the universe to be conservative.
        try:
            from penny_regime import PennyRegimeEngine
            PennyRegimeEngine().update_vol_rank(
                PennyRegimeEngine().compute_vol_rank(closes_1m)
            )
        except Exception as e:
            # Never let regime-feeding crash a scan tick.
            logger.warning("penny_vol_rank_feed_failed ticker=%s error=%s",
                           ticker, str(e))

        return evaluate_breakout_entry(
            ticker=ticker, cum_vol_today=cum_vol, median_vol_20d=median_vol_20d,
            breakout_bar=breakout_bar, day_high=day_high, rsi_14=rsi_14,
            as_of=as_of, risk_engine=self.risk_engine,
            # [TIER2-BREAKOUT-REFINEMENT 2026-06-25] Pass intraday so the
            # breakout engine can compute VWAP and adaptive threshold.
            # The engine uses intraday only if PENNY_BREAKOUT_USE_VWAP
            # or PENNY_BREAKOUT_ADAPTIVE_THRESHOLD is True; otherwise the
            # param is ignored and behaviour is identical to pre-fix.
            intraday=intraday,
            # [FIX-PHASE1-AUDIT 2026-07-09] Pass the day's penny regime so
            # the engine honours the spec §6.3 ladder:
            #   PR1_CALM     -> full risk budget
            #   PR2_ELEVATED -> half risk budget
            #   PR3_HOT      -> no new entries (rejected pre-sizing)
            # self.regime is a PennyRegime enum (or string-compatible) read
            # via _normalise_regime_getter above; the engine coerces if needed.
            regime=PennyRegime(self.regime),
        )

    async def _evaluate_ticker_connors(
        self, ticker: str, as_of: datetime,
        prev_close: Optional[float] = None,
        day_low: Optional[float] = None,  # unused here but kept for symmetry with breakout
        # Inherit new params with default None: callers from older test
        # signatures still work.
        **kwargs,
    ) -> Optional[dict]:
        """Run the CNC Connors evaluator on one ticker.

        [PENNY-CONNORS-VOL 2026-06-25] The volume sanity gate in
        evaluate_connors_entry (line 124 of penny_engine_connors.py)
        requires today_volume >= 0.5 * avg20_volume. Previously this
        method hard-coded today_volume=50_000 / avg20_volume=100_000
        which made the volume gate a constant pass-through -- any
        ticker with valid SMA+RSI that hit the Connors trigger was
        accepted regardless of actual volume. Now we compute real
        today_volume from the latest daily bar and avg20_volume from
        the 20-day median of daily volume, mirroring the breakout
        path. If volume cannot be computed (missing column, etc.) we
        return None to be safe -- a phantom signal is worse than no
        signal at this bankroll.
        """
        from penny_engine_connors import evaluate_connors_entry
        token = self.kite.instrument_cache.get(ticker)
        if token is None:
            logger.warning("penny_eval_skipped ticker=%s reason=token_unresolved", ticker)
            return None
        # Need 250+ daily closes for the SMA + RSI trend filter
        try:
            bars = await self.kite.get_historical(
                ticker=ticker,
                from_date="2025-01-01",
                to_date=as_of.strftime("%Y-%m-%d"),
            )
        except Exception as e:
            logger.error("penny_historical_failed ticker=%s error=%s", ticker, str(e))
            bars = None
        if bars is None:
            logger.warning("penny_eval_skipped ticker=%s reason=historical_unavailable", ticker)
            return None
        n = len(bars) if hasattr(bars, '__len__') else 0
        if n < 250:
            logger.warning("penny_eval_skipped ticker=%s reason=insufficient_history bars=%d", ticker, n)
            return None
        # Real volume extraction (P1a). If the column is missing or
        # unusable, return None rather than fabricate numbers.
        today_volume = 0
        avg20_volume = 0
        if hasattr(bars, 'columns') and 'volume' in bars.columns:
            try:
                vol_series = bars["volume"].tail(21)  # 21 to allow median of last 20
                today_volume = int(vol_series.iloc[-1] or 0)
                avg20_volume = int(vol_series.tail(20).median() or 0)
            except Exception as e:
                logger.warning(
                    "penny_eval_skipped ticker=%s reason=volume_extract_failed error=%s",
                    ticker, str(e),
                )
                return None
        else:
            logger.warning(
                "penny_eval_skipped ticker=%s reason=no_volume_column",
                ticker,
            )
            return None
        if hasattr(bars, 'columns'):
            # pandas DataFrame
            closes = bars["close"].tolist() if "close" in bars.columns else []
        else:
            closes = [b["close"] for b in bars if b.get("close")]
        daily = {"closes": closes}

        # [FIX-PHASE2-AUDIT 2026-07-09] Also feed vol_rank from the
        # Connors path. The daily closes we already have are perfect
        # input for compute_vol_rank (250 bars gives a robust 60d proxy).
        # The scanner's per-scan-tick universe is small (~78 tickers),
        # so this is one extra divide per ticker.
        try:
            from penny_regime import PennyRegimeEngine
            PennyRegimeEngine().update_vol_rank(
                PennyRegimeEngine().compute_vol_rank(closes)
            )
        except Exception as e:
            logger.warning("penny_vol_rank_feed_failed ticker=%s error=%s",
                           ticker, str(e))

        # [FIX-PHASE2-AUDIT 2026-07-09] Circuit-block check for the
        # Connors path. We fetch a quote (cache hit in production) and
        # run the same PennyRiskEngine.circuit_blocked guard as the
        # breakout engine so both legs respect the band filter.
        if prev_close and prev_close > 0:
            try:
                q = await self._get_quote_safe(token)
                if q:
                    cnc_ltp = float(q.get("last_price") or 0)
                    ohlc = q.get("ohlc") or {}
                    cnc_day_high = float(ohlc.get("high") or cnc_ltp or prev_close)
                    cnc_day_low = float(ohlc.get("low") or cnc_ltp or prev_close)
                    band_pct_c = PennyRiskEngine.infer_band_pct_from_quote(
                        prev_close=float(prev_close),
                        day_high=cnc_day_high, day_low=cnc_day_low,
                    )
                    blocked, block_reason = self.risk_engine.circuit_blocked(
                        last_price=cnc_ltp, day_high=cnc_day_high,
                        prev_close=float(prev_close), band_pct=band_pct_c,
                    )
                    if blocked:
                        logger.info(
                            "penny_circuit_blocked_connors ticker=%s band=%.2f%% ltp=%.2f "
                            "day_high=%.2f prev_close=%.2f reason=%s",
                            ticker, band_pct_c * 100, cnc_ltp, cnc_day_high,
                            prev_close, block_reason,
                        )
                        return {
                            "accept": False,
                            "reject_reason": f"circuit_blocked: {block_reason}",
                            "ticker": ticker,
                        }
            except Exception as e:
                logger.warning("penny_connors_circuit_check_failed ticker=%s error=%s",
                               ticker, str(e))

        decision = evaluate_connors_entry(
            ticker=ticker, daily=daily,
            today_volume=today_volume, avg20_volume=avg20_volume,
            regime_size_pct=self._regime_to_size_pct(),
            risk_engine=self.risk_engine, as_of=as_of,
        )
        if not decision or not decision.get("accept"):
            return decision

        # [TIER2-TIME-OF-DAY 2026-06-25] Reject late-day CNC signals.
        # Connors RSI(2) is a morning mean-reversion signal -- after lunch
        # the signal is much less reliable because:
        #   - morning gaps have already played out
        #   - afternoon volume is thinner, so fills + SL-M protection are
        #     both less robust
        #   - the operator can no longer react to a midday trigger before
        #     EOD
        # PENNY_CONNORS_LAST_ENTRY_MIN=195 (12:30 IST) is the default;
        # 0 disables. The check is intentionally simple: minutes since
        # 09:15 IST. We could use market_calendar-aware sunrise but the
        # signal is independent of holidays (just time-of-day).
        from config import settings as _settings
        last_entry_min = _settings.PENNY_CONNORS_LAST_ENTRY_MIN
        if last_entry_min > 0:
            market_open = as_of.replace(hour=9, minute=15, second=0, microsecond=0)
            minutes_since_open = (as_of - market_open).total_seconds() / 60.0
            if minutes_since_open > last_entry_min:
                logger.info(
                    "penny_eval_skipped ticker=%s reason=late_day minutes_since_open=%.0f limit=%d",
                    ticker, minutes_since_open, last_entry_min,
                )
                decision["accept"] = False
                decision["reject_reason"] = (
                    f"late-day entry blocked (minutes_since_open={minutes_since_open:.0f}, "
                    f"limit={last_entry_min})"
                )
                return decision

        # [PENNY-G2 2026-06-25] Compute real ATR(1min) from today's intraday
        # bars and include it in the decision so downstream exit logic
        # (evaluate_connors_exit) can use it for the post-T1 trailing stop.
        # Previously this was always 0.0 because no caller fetched intraday
        # for CNC entries -- the trail-stop effectively became a hard floor
        # at breakeven+0.5% and the ATR component never moved it.
        # NOTE: run_penny_connors_scan does NOT currently write a CNC
        # position row to the positions table -- that's a separate fix
        # (G5 / P3). When that lands, atr_1min_post_t1 will be read from
        # the position. Until then this is computed but not consumed.
        try:
            from datetime import timedelta as _td
            today = as_of.strftime("%Y-%m-%d")
            start_dt = f"{today} 09:15:00"
            end_dt = as_of.strftime("%Y-%m-%d %H:%M:%S")
            intraday = await self.kite.get_intraday(
                ticker=ticker,
                from_datetime=start_dt,
                to_datetime=end_dt,
                interval="minute",
            )
            if intraday is not None and len(intraday) >= 1:
                from penny_engine_connors import atr_1min as _atr_1min
                atr = _atr_1min(intraday)
                decision["atr_1min_post_t1"] = float(atr)
            else:
                decision["atr_1min_post_t1"] = 0.0
        except Exception as e:
            logger.warning(
                "penny_atr_intraday_failed ticker=%s error=%s atr_1min_set_to_0",
                ticker, str(e),
            )
            decision["atr_1min_post_t1"] = 0.0
        return decision

    async def scan_once(self, as_of: datetime) -> dict:
        """
        One full pass: load universe, run BOTH engines per ticker, log results.
        Used by the 30-second MIS scheduler. CNC engine runs but most tickers
        will be rejected (insufficient daily data) -- the daily 09:30 scanner
        is the canonical CNC pass.

        Returns summary dict with counts (accept, reject, error).

        Observability (2026-06-25):
        - Logs `penny_scan_loop_summary` at start with universe size and
          degraded-quality count so silent-empty-eligible scenarios
          surface immediately.
        - Logs `penny_eval_skipped` at every silent None-return path in
          the per-ticker evaluator with the actual reason.
        - Treats a None decision from _evaluate_ticker_breakout as a
          `reject` with a structured reason (not a silent error count).
          This matches the CNC path's counting convention.
        """
        from config import settings
        from penny_signal_log import init_penny_signal_db, log_penny_signal
        scan_id = f"penny-{uuid4().hex[:8]}"
        # Ensure DB exists
        await init_penny_signal_db(settings.DB_PATH)

        universe = self._load_universe()
        # [PENNY-STARTUP-GATE 2026-07-02] If the universe is empty,
        # check whether the instrument_cache is the reason (race on
        # container startup). If yes, wait up to 60s for it to fill;
        # if it never fills, log + return zeros rather than spam
        # `penny_universe_tokens_unresolved count=100` for 12 minutes.
        if not universe:
            cache_size = len(getattr(self.kite, "instrument_cache", {}) or {})
            if cache_size < 100:
                if not await self._wait_for_instrument_cache():
                    return {"scan_id": scan_id, "accept": 0, "reject": 0, "error": 0}
                # Cache filled -- reload universe once.
                universe = self._load_universe()
            if not universe:
                # 2026-06-25: surface this loudly so future silent-empty
                # scenarios don't go unnoticed.
                logger.warning(
                    "penny_scan_no_eligible_universe scan_id=%s "
                    "(check penny_universe_quality_audit + corp_data source)",
                    scan_id,
                )
                return {"scan_id": scan_id, "accept": 0, "reject": 0, "error": 0}

        # Surface universe size + degraded count at scan start
        degraded_count = sum(
            1 for t in universe if (t.get("data_quality") or "").startswith("DEGRADED")
        )
        logger.info(
            "penny_scan_loop_summary scan_id=%s eligible=%d degraded=%d regime=%s",
            scan_id, len(universe), degraded_count, self.regime,
        )

        # Regime gate: PR3 blocks all new entries
        if self.regime == PennyRegime.PR3_HOT.value:
            for t in universe:
                await log_penny_signal(
                    settings.DB_PATH, scan_id=scan_id, ticker=t["symbol"],
                    leg="MIS", accepted=False,
                    reject_reason="regime PR3_HOT (no new entries)",
                    regime=self.regime, close=0.0,
                )
            return {"scan_id": scan_id, "accept": 0, "reject": len(universe), "error": 0}

        # Kill-switch gate
        if self.risk_engine.kill_switch_active():
            for t in universe:
                await log_penny_signal(
                    settings.DB_PATH, scan_id=scan_id, ticker=t["symbol"],
                    leg="MIS", accepted=False,
                    reject_reason="kill_switch active (daily loss limit)",
                    regime=self.regime, close=0.0,
                )
            return {"scan_id": scan_id, "accept": 0, "reject": len(universe), "error": 0}

        accept = reject = error = 0
        # [PENNY-G9 2026-06-25] Parallelise the per-ticker evaluation with
        # asyncio.gather. The previous sequential loop ran ~100 tickers
        # back-to-back. Each ticker does 3 kite calls (quote, intraday,
        # historical) gated by the kite_client RateLimiter (3 req/sec,
        # burst 1). Parallelising lets the limiter queue N requests at
        # once instead of N serial round-trips, giving an effective
        # speedup of ~5-10x for 100-ticker universes.
        #
        # Sequential steps that stay serial:
        # - manual disable check (sync, no I/O)
        # - DB writes (log_penny_signal, positions INSERT) -- these have
        #   their own aiosqlite connection and concurrent writes could race.
        # - executor.execute_entry -- places real orders, MUST be serial.
        #
        # We therefore split the loop into two phases:
        # Phase 1 (parallel): evaluate all non-disabled tickers via gather
        # Phase 2 (serial): for each result, log signal + (if accept) execute
        surviving = []
        for t in universe:
            sym = t["symbol"]
            if self.risk_engine.is_disabled(sym):
                await log_penny_signal(
                    settings.DB_PATH, scan_id=scan_id, ticker=sym,
                    leg="MIS", accepted=False,
                    reject_reason=f"disabled via PENNY_DISABLE_TICKERS",
                    regime=self.regime, close=0.0,
                )
                reject += 1
                continue
            surviving.append(t)

        # [PENNY-T2C-SECTOR-FILTER 2026-06-25] Load sector CSV once per
        # scan (not per ticker). Empty CSV or missing file = filter is
        # effectively OFF (fail-open). The dedupe batch helper below
        # groups tickers by ETF so we only hit Kite once per unique sector.
        sector_map: dict = {}
        if settings.PENNY_USE_SECTOR_FILTER:
            try:
                from penny_sector_filter import load_sector_map
                sector_map = load_sector_map(settings.PENNY_SECTORS_CSV_PATH)
            except Exception as e:
                logger.warning("penny_sector_filter_load_failed error=%s (fail-open)", str(e))
                sector_map = {}

        # Phase 1a: parallel per-ticker evaluation (breakout engine).
        # [FIX-PHASE2-AUDIT 2026-07-09] Pass prev_close from each
        # universe record so circuit_blocked (spec §7.4) can be enforced
        # inside the evaluator.
        if surviving:
            results = await asyncio.gather(
                *[self._evaluate_ticker_breakout(
                      t["symbol"], as_of,
                      prev_close=t.get("prev_close"),
                  )
                  for t in surviving],
                return_exceptions=True,
            )
        else:
            results = []

        # Phase 1a (continued): drop records that the breakout engine
        # rejected so we don't waste Kite calls on the Connors leg.
        # Still need the *universe record* (t) for connors kwargs (prev_close, etc).

        # Phase 1b: sector check. Only runs on tickers that PASSED the
        # breakout engine (we don't waste Kite calls on rejects). Uses
        # the batch dedupe helper so the Kite rate limiter isn't hammered.
        # The CSV-tickers dict has whatever mapping was loaded (possibly
        # empty if CSV missing); the helper handles that case.
        post_breakout = []  # list of (ticker_dict, decision)
        for t, result in zip(surviving, results):
            sym = t["symbol"]
            if isinstance(result, Exception):
                continue  # handled below
            if result is None or not result.get("accept"):
                continue  # not a candidate
            post_breakout.append((t, result))

        sector_decisions: dict = {}
        if post_breakout and sector_map:
            try:
                from penny_sector_filter import filter_universe_by_sector
                post_tickers = [td[0]["symbol"] for td in post_breakout]
                sector_decisions = await filter_universe_by_sector(
                    tickers=post_tickers,
                    kite=self.kite,
                    sector_map=sector_map,
                    top_losers_pct=settings.PENNY_SECTOR_TOP_LOSERS_PCT,
                    etf_change_threshold_pct=settings.PENNY_SECTOR_ETF_CHANGE_THRESHOLD_PCT,
                )
            except Exception as e:
                logger.warning("penny_sector_filter_batch_failed error=%s (fail-open)", str(e))
                sector_decisions = {}

        # Phase 2: serial result processing. Each surviving ticker has a
        # corresponding result (decision dict or Exception).
        for t, result in zip(surviving, results):
            sym = t["symbol"]
            if isinstance(result, Exception):
                # Should not normally happen -- the evaluator catches its own
                # exceptions and returns None -- but be defensive.
                logger.error(
                    "penny_ticker_eval_exception ticker=%s error=%s",
                    sym, str(result),
                )
                error += 1
                continue
            decision = result
            if decision is None:
                # 2026-06-25: this is not a system ERROR -- it is a
                # structured "skipped" outcome. The evaluator already
                # logged the specific reason (e.g. penny_intraday_fetch_failed,
                # penny_daily_vol_fetch_failed). Count it as a reject
                # so the diagnostic breakdown in the hourly report is
                # accurate. Also log the DB row so operators can see
                # the rejection without waiting for the hourly message.
                logger.info(
                    "penny_eval_skipped ticker=%s reason=evaluator_returned_none",
                    sym,
                )
                await log_penny_signal(
                    settings.DB_PATH, scan_id=scan_id, ticker=sym,
                    leg="MIS", accepted=False,
                    reject_reason="evaluator returned None (see prior warn/error)",
                    regime=self.regime, close=0.0,
                )
                reject += 1
                continue

            # [PENNY-T2C-SECTOR-FILTER 2026-06-25] Apply sector gate AFTER
            # the breakout engine accepts, BEFORE we go to DB + executor.
            # The gate is fail-open: UNKNOWN -> ALLOW. REJECT -> structured
            # reject with a sector-specific reason in the diagnostic
            # breakdown.
            if decision.get("accept") and sym in sector_decisions:
                sd = sector_decisions[sym]
                if sd.is_blocked:
                    logger.info(
                        "penny_sector_filter_rejected ticker=%s sector=%s etf=%s change=%.2f%% reason=%s",
                        sym, sd.sector, sd.etf_symbol,
                        (sd.etf_change_pct or 0) * 100,
                        sd.reason,
                    )
                    await log_penny_signal(
                        settings.DB_PATH, scan_id=scan_id, ticker=sym,
                        leg="MIS", accepted=False,
                        reject_reason=f"sector_filter: {sd.reason}",
                        regime=self.regime, close=0.0,
                    )
                    reject += 1
                    continue

            if not decision.get("accept"):
                await log_penny_signal(
                    settings.DB_PATH, scan_id=scan_id, ticker=sym,
                    leg="MIS", accepted=False,
                    reject_reason=decision.get("reject_reason", ""),
                    regime=self.regime, close=0.0,
                )
                reject += 1
            else:
                # Log accept + delegate to executor (per 2026-06-22 deviation).
                # The executor handles the full entry flow per spec §7.2:
                # entry LIMIT -> fill poll -> SL-M with retry -> market-unwind.
                await log_penny_signal(
                    settings.DB_PATH, scan_id=scan_id, ticker=sym,
                    leg="MIS", accepted=True,
                    regime=self.regime, close=decision.get("entry", 0.0),
                    stop_loss=decision.get("stop_loss"),
                    target_1=decision.get("target"),
                    rsi_14=decision.get("rsi_14"),
                    breakout_level=decision.get("breakout_level"),
                    shares=decision.get("shares"),
                )
                try:
                    from penny_models import PennyLeg
                    from position_tracker import init_positions_db
                    await init_positions_db(settings.DB_PATH)
                    order_result = await self.executor.execute_entry(
                        ticker=sym,
                        leg=PennyLeg.MIS,
                        entry_price=decision.get("entry", 0.0),
                        stop_loss=decision.get("stop_loss", 0.0),
                        shares=decision.get("shares", 0),
                    )
                    logger.info(
                        "penny_entry_attempted ticker=%s entry=%.2f sl=%.2f shares=%d paper=%s order_id=%s",
                        sym, decision.get("entry", 0.0),
                        decision.get("stop_loss", 0.0),
                        decision.get("shares", 0),
                        order_result.get("paper"),
                        order_result.get("entry_order_id"),
                    )
                    if (not order_result.get("unwound")
                            and order_result.get("entry_status") == "filled"):
                        import aiosqlite
                        from datetime import datetime, timezone
                        async with aiosqlite.connect(settings.DB_PATH) as db:
                            await db.execute(
                                """INSERT INTO positions (
                                    ticker, exchange, entry_date, entry_price, shares,
                                    stop_loss_initial, trailing_stop_current,
                                    target_1, target_2, atr_14_at_entry,
                                    highest_close_since_entry, status, source,
                                    product_type, regime_at_entry
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (sym, "NSE",
                                 datetime.now(timezone.utc).isoformat(),
                                 decision.get("entry", 0.0),
                                 decision.get("shares", 0),
                                 decision.get("stop_loss", 0.0),
                                 decision.get("stop_loss", 0.0),
                                 decision.get("target", 0.0),
                                 decision.get("target", 0.0) * 1.05,
                                 0.0, decision.get("entry", 0.0),
                                 "OPEN", "PENNY", "MIS", self.regime)
                            )
                            await db.commit()
                except Exception as e:
                    logger.error("penny_entry_wiring_failed ticker=%s error=%s", sym, str(e))
                accept += 1

        return {"scan_id": scan_id, "accept": accept, "reject": reject, "error": error}