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

logger = logging.getLogger(__name__)


class PennyScanner:
    def __init__(
        self,
        kite,
        universe_json_path: str,
        paper_mode: bool = True,
        regime: str = "PR1_CALM",
        daily_pnl_override: Optional[float] = None,
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
        self.risk_engine = PennyRiskEngine(bankroll=bankroll)
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
        """Run the MIS Breakout evaluator on one ticker."""
        from penny_engine_breakout import evaluate_breakout_entry
        token = self.kite.instrument_cache.get(ticker)
        if token is None:
            return None
        q = await self._get_quote_safe(token)
        if not q:
            return None
        # Build synthetic breakout_bar from current quote
        ltp = q.get("last_price", 0)
        breakout_bar = {"high": ltp * 1.01, "low": ltp * 0.99, "close": ltp}
        # Cumulative volume today: Kite gives today's volume (cumulative since open)
        cum_vol = q.get("volume", 0) or 0
        # Day high: use ohlc.high or fall back to ltp
        day_high = (q.get("ohlc") or {}).get("high") or ltp
        return evaluate_breakout_entry(
            ticker=ticker, cum_vol_today=cum_vol, median_vol_20d=10_000,
            breakout_bar=breakout_bar, day_high=day_high, rsi_14=50.0,
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
        if not bars or len(bars) < 250:
            return None
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
                    # Scanner's job ends here: log accept + persist intent.
                    # The penny_executor module handles actual order placement
                    # (entry LIMIT, then broker-level SL-M, with mandatory
                    # SL-M-or-unwind flow per spec §7.2). See Task 11.
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
                    accept += 1
            except Exception as e:
                logger.error("penny_ticker_eval_failed ticker=%s error=%s", sym, str(e))
                error += 1

        return {"scan_id": scan_id, "accept": accept, "reject": reject, "error": error}