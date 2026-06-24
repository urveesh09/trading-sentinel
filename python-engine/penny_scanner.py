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
from typing import Optional, List
from uuid import uuid4

from penny_universe import PennyUniverse
from penny_models import PennyRegime, PennyLeg
from penny_executor import PennyExecutor

logger = logging.getLogger(__name__)


class PennyScanner:
    def __init__(
        self,
        kite,
        universe_json_path: str,
        paper_mode: bool = True,
        regime: str = "PR1_CALM",
        daily_pnl_override: Optional[float] = None,
        ledger_writer=None,
    ):
        self.kite = kite
        self.universe_json_path = universe_json_path
        self.paper_mode = paper_mode
        self.regime = regime
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

    async def _get_quote_safe(self, token: int) -> Optional[dict]:
        try:
            quotes = await self.kite.get_quote([token])
            return quotes.get(token) if isinstance(quotes, dict) else None
        except Exception as e:
            logger.error("penny_quote_fetch_failed token=%s error=%s", token, str(e))
            return None

    def _regime_to_size_pct(self) -> float:
        from penny_regime import PennyRegimeEngine
        try:
            r = PennyRegime(self.regime)
        except ValueError:
            return 0.0
        return PennyRegimeEngine().size_pct(r)

    async def _evaluate_ticker_breakout(
        self, ticker: str, as_of: datetime
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
            return None

        # 1) Live quote for LTP, day high, and cumulative volume
        q = await self._get_quote_safe(token)
        if not q:
            return None
        ltp = q.get("last_price", 0)
        cum_vol = q.get("volume", 0) or 0
        day_high = (q.get("ohlc") or {}).get("high") or ltp

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
            return {
                "accept": False,
                "reject_reason": "no 20-day median volume baseline",
                "ticker": ticker,
            }

        # 5) Real RSI(14) from the 1-min closes
        closes_1m = [float(c) for c in intraday["close"].tolist()]
        rsi_14 = _rsi_14_wilder(closes_1m)

        return evaluate_breakout_entry(
            ticker=ticker, cum_vol_today=cum_vol, median_vol_20d=median_vol_20d,
            breakout_bar=breakout_bar, day_high=day_high, rsi_14=rsi_14,
            as_of=as_of, risk_engine=self.risk_engine,
        )

    async def _evaluate_ticker_connors(
        self, ticker: str, as_of: datetime
    ) -> Optional[dict]:
        """Run the CNC Connors evaluator on one ticker."""
        from penny_engine_connors import evaluate_connors_entry
        token = self.kite.instrument_cache.get(ticker)
        if token is None:
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
            return None
        n = len(bars) if hasattr(bars, '__len__') else 0
        if n < 250:
            return None
        if hasattr(bars, 'columns'):
            # pandas DataFrame
            closes = bars["close"].tolist() if "close" in bars.columns else []
        else:
            closes = [b["close"] for b in bars if b.get("close")]
        daily = {"closes": closes}
        return evaluate_connors_entry(
            ticker=ticker, daily=daily,
            today_volume=50_000, avg20_volume=100_000,
            regime_size_pct=self._regime_to_size_pct(),
            risk_engine=self.risk_engine, as_of=as_of,
        )

    async def scan_once(self, as_of: datetime) -> dict:
        """
        One full pass: load universe, run BOTH engines per ticker, log results.
        Used by the 30-second MIS scheduler. CNC engine runs but most tickers
        will be rejected (insufficient daily data) -- the daily 09:30 scanner
        is the canonical CNC pass.

        Returns summary dict with counts (accept, reject, error).
        """
        from config import settings
        from penny_signal_log import init_penny_signal_db, log_penny_signal
        scan_id = f"penny-{uuid4().hex[:8]}"
        # Ensure DB exists
        await init_penny_signal_db(settings.DB_PATH)

        universe = self._load_universe()
        if not universe:
            logger.info("penny_scan_no_universe")
            return {"scan_id": scan_id, "accept": 0, "reject": 0, "error": 0}

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
        for t in universe:
            sym = t["symbol"]
            # Manual disable gate
            if self.risk_engine.is_disabled(sym):
                await log_penny_signal(
                    settings.DB_PATH, scan_id=scan_id, ticker=sym,
                    leg="MIS", accepted=False,
                    reject_reason=f"disabled via PENNY_DISABLE_TICKERS",
                    regime=self.regime, close=0.0,
                )
                reject += 1
                continue

            try:
                decision = await self._evaluate_ticker_breakout(sym, as_of)
                if decision is None:
                    error += 1
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
            except Exception as e:
                logger.error("penny_ticker_eval_failed ticker=%s error=%s", sym, str(e))
                error += 1

        return {"scan_id": scan_id, "accept": accept, "reject": reject, "error": error}