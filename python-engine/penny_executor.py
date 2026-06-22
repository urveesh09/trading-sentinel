"""
[PENNY-EXECUTOR 2026-06-21] Order execution flow for the penny subsystem.

Spec §7.2: MANDATORY broker-level SL-M for every entry. If SL-M cannot be
placed (broker rejection, network error, unsupported order type), the
executor MUST immediately market-exit the position. No in-engine stop
fallback -- gap-down protection only works when the broker holds the trigger.

Public API:
  PennyExecutor.execute_entry(ticker, leg, entry_price, stop_loss, shares)
    -> dict with entry_order_id, sl_order_id, entry_status, unwound,
       unwind_order_id, paper

Paper mode (default, PENNY_LIVE_TRADING=False): emits PAPER-* IDs, never
calls kite.place_order. Live mode: real orders.

Hard architectural rule: this module MAY import kite_client (it has to, to
place orders), but MUST NOT import from engine/regime/risk_engine/portfolio
(Nifty-side modules).

Allowed shared imports: kite_client, penny_models, penny_risk, config,
position_tracker, stdlib.
"""
import asyncio
import logging
from typing import Optional

from penny_models import PennyLeg

logger = logging.getLogger(__name__)


class PennyExecutor:
    def __init__(
        self,
        kite,
        paper_mode: bool = True,
        fill_timeout_sec: float = 60.0,
        poll_interval_sec: float = 2.0,
    ):
        self.kite = kite
        self.paper_mode = paper_mode
        self.fill_timeout_sec = fill_timeout_sec
        self.poll_interval_sec = poll_interval_sec

    async def execute_entry(
        self,
        ticker: str,
        leg: PennyLeg,
        entry_price: float,
        stop_loss: float,
        shares: int,
    ) -> dict:
        """
        Spec §7.2 order flow:
          1. Place entry LIMIT
          2. Wait for fill (with timeout)
          3. Place SL-M at broker
          4. If SL-M rejected or fails twice -> market-exit
        """
        result = {
            "entry_order_id": None,
            "entry_status": None,
            "sl_order_id": None,
            "unwind_order_id": None,
            "unwound": False,
            "paper": self.paper_mode,
        }

        # ---- paper mode: emit IDs, no kite calls ---------------------
        if self.paper_mode:
            from uuid import uuid4
            result["entry_order_id"] = f"PAPER-ENT-{uuid4().hex[:8]}"
            result["sl_order_id"] = f"PAPER-SL-{uuid4().hex[:8]}"
            result["entry_status"] = "paper"
            logger.info(
                "penny_paper_entry ticker=%s leg=%s entry=%s sl=%s shares=%d",
                ticker, leg.value, entry_price, stop_loss, shares,
            )
            return result

        # ---- step 1: place entry LIMIT -------------------------------
        try:
            entry_resp = await self.kite.place_order(
                variety="regular", exchange="NSE",
                tradingsymbol=ticker,
                transaction_type="BUY",
                quantity=shares,
                product=leg.value,
                order_type="LIMIT",
                price=entry_price,
                validity="DAY",
            )
        except Exception as e:
            logger.error("penny_entry_rejected ticker=%s error=%s", ticker, str(e))
            result["entry_status"] = "rejected"
            return result

        entry_id = entry_resp.get("order_id")
        result["entry_order_id"] = entry_id
        if not entry_id:
            result["entry_status"] = "rejected"
            return result

        # ---- step 2: poll for fill ------------------------------------
        filled = await self._wait_for_fill(entry_id)
        if not filled:
            try:
                await self.kite.cancel_order(entry_id)
            except Exception as e:
                logger.error("penny_cancel_failed order_id=%s error=%s",
                             entry_id, str(e))
            result["entry_status"] = "timeout"
            logger.warning("penny_entry_timeout ticker=%s order_id=%s",
                           ticker, entry_id)
            return result

        result["entry_status"] = "filled"

        # ---- step 3: place SL-M (with one retry, then unwind) ---------
        sl_id = await self._place_sl_m_with_retry(ticker, leg, stop_loss, shares)
        if sl_id:
            result["sl_order_id"] = sl_id
            logger.info("penny_sl_m_placed ticker=%s order_id=%s trigger=%s",
                        ticker, sl_id, stop_loss)
            return result

        # ---- step 4: SL-M failed -> market unwind ---------------------
        logger.error("penny_sl_m_failed_unwinding ticker=%s entry_id=%s sl=%s shares=%d",
                     ticker, entry_id, stop_loss, shares)
        unwind_id = await self._market_unwind(ticker, leg, shares)
        result["unwind_order_id"] = unwind_id
        result["unwound"] = True
        return result

    async def _wait_for_fill(self, order_id: str) -> bool:
        """Poll order_history until COMPLETE or timeout."""
        elapsed = 0.0
        while elapsed < self.fill_timeout_sec:
            try:
                history = await self.kite.order_history(order_id=order_id)
                if history and history[0].get("status") == "COMPLETE":
                    return True
            except Exception as e:
                logger.error("penny_order_history_failed order_id=%s error=%s",
                             order_id, str(e))
            await asyncio.sleep(self.poll_interval_sec)
            elapsed += self.poll_interval_sec
        return False

    async def _place_sl_m_with_retry(
        self, ticker: str, leg: PennyLeg, stop_loss: float, shares: int,
        max_attempts: int = 2,
    ) -> Optional[str]:
        """Try to place SL-M up to max_attempts. Returns order_id or None."""
        for attempt in range(1, max_attempts + 1):
            try:
                resp = await self.kite.place_order(
                    variety="regular", exchange="NSE",
                    tradingsymbol=ticker,
                    transaction_type="SELL",
                    quantity=shares,
                    product=leg.value,
                    order_type="SL-M",
                    trigger_price=stop_loss,
                    validity="DAY",
                )
                if resp.get("status") in ("REJECTED", "ERROR"):
                    logger.error(
                        "penny_sl_m_broker_rejected ticker=%s attempt=%d message=%s",
                        ticker, attempt, resp.get("message", ""),
                    )
                    return None
                order_id = resp.get("order_id")
                if order_id:
                    return order_id
                logger.error("penny_sl_m_no_order_id ticker=%s attempt=%d resp=%s",
                             ticker, attempt, resp)
                return None
            except Exception as e:
                logger.error("penny_sl_m_attempt_failed ticker=%s attempt=%d error=%s",
                             ticker, attempt, str(e))
                if attempt < max_attempts:
                    await asyncio.sleep(0.5)
        return None

    async def _market_unwind(
        self, ticker: str, leg: PennyLeg, shares: int,
    ) -> Optional[str]:
        """Emergency market exit. Best-effort -- logs but does not raise."""
        try:
            resp = await self.kite.place_order(
                variety="regular", exchange="NSE",
                tradingsymbol=ticker,
                transaction_type="SELL",
                quantity=shares,
                product=leg.value,
                order_type="MARKET",
                validity="DAY",
            )
            return resp.get("order_id")
        except Exception as e:
            logger.error("penny_unwind_failed ticker=%s shares=%d error=%s",
                         ticker, shares, str(e))
            return None
