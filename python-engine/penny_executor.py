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

from kite_client import latest_order_state
from penny_models import PennyLeg

logger = logging.getLogger(__name__)

# Broker-terminal order states. An order in one of these states will never
# fill later; anything else is still in flight.
_TERMINAL_DEAD = ("REJECTED", "CANCELLED")


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
        fill_state = await self._wait_for_fill(entry_id)

        if fill_state in _TERMINAL_DEAD:
            # Broker already killed the order -- there is nothing to cancel
            # (pre-2026-07-17 this path cancelled anyway and got the
            # confusing "order does not exist" OrderException back).
            result["entry_status"] = "rejected"
            logger.warning("penny_entry_dead ticker=%s order_id=%s status=%s",
                           ticker, entry_id, fill_state)
            return result

        if fill_state != "COMPLETE":
            # [ORDER-RECONCILE 2026-07-17] Timeout is NOT proof of no-fill.
            # The 2026-07-17 JINDWORLD entry "timed out" because the fill
            # poll read the wrong end of the history list; the old code then
            # declared "skipped" without ever checking whether stock was
            # actually bought -- the same naked-position class as the
            # momentum SL-M bug fixed 2026-07-15. Order of operations:
            # cancel first (so a still-open order can't fill AFTER we
            # decide it didn't), then read back the order's final state and
            # believe THAT, falling back to the broker positions book.
            try:
                await self.kite.cancel_order(entry_id)
            except Exception as e:
                logger.error("penny_cancel_failed order_id=%s error=%s",
                             entry_id, str(e))

            final = await self._reconcile_after_timeout(ticker, entry_id, shares)
            if final != "FILLED":
                result["entry_status"] = "timeout"
                logger.warning(
                    "penny_entry_timeout ticker=%s order_id=%s reconciled=%s",
                    ticker, entry_id, final,
                )
                return result
            logger.warning(
                "penny_entry_filled_after_timeout ticker=%s order_id=%s "
                "-- proceeding to SL placement, NOT dropping the position",
                ticker, entry_id,
            )

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

    async def _wait_for_fill(self, order_id: str) -> str:
        """Poll order_history until a terminal state or timeout.

        Returns the last observed status string: "COMPLETE", "REJECTED",
        "CANCELLED", or whatever non-terminal state it last saw ("OPEN",
        "" if history never came back).

        [ORDER-HISTORY-2026-07-17] Kite's history is chronological --
        history[0] is the oldest event. The old `history[0].get("status")
        == "COMPLETE"` could not see a fill EVER (index 0 is the
        PUT-ORDER-REQ/OPEN event), which is why all 4 edge-live entries
        since 2026-07-15 "timed out". Also bail out early on
        REJECTED/CANCELLED instead of burning the full timeout polling a
        dead order."""
        elapsed = 0.0
        status = ""
        while elapsed < self.fill_timeout_sec:
            try:
                history = await self.kite.order_history(order_id=order_id)
                status = latest_order_state(history).get("status") or status
                if status == "COMPLETE" or status in _TERMINAL_DEAD:
                    return status
            except Exception as e:
                logger.error("penny_order_history_failed order_id=%s error=%s",
                             order_id, str(e))
            await asyncio.sleep(self.poll_interval_sec)
            elapsed += self.poll_interval_sec
        return status

    async def _reconcile_after_timeout(
        self, ticker: str, order_id: str, shares: int,
    ) -> str:
        """After a fill timeout + cancel attempt: did we buy stock or not?

        Returns "FILLED", "DEAD" (rejected/cancelled -- provably no stock),
        or "UNVERIFIED" (could not prove either way; treated as no-fill by
        the caller, but logged at ERROR so the operator checks the broker
        book by hand -- see [ORDER-RECONCILE 2026-07-17] above)."""
        # 1. The order's own final state is authoritative when readable.
        try:
            final = latest_order_state(
                await self.kite.order_history(order_id=order_id)
            ).get("status") or ""
        except Exception as e:
            logger.error("penny_reconcile_history_failed order_id=%s error=%s",
                         order_id, str(e))
            final = ""
        if final == "COMPLETE":
            return "FILLED"
        if final in _TERMINAL_DEAD:
            return "DEAD"

        # 2. History unreadable/inconclusive -> the positions book decides.
        try:
            positions = await self.kite.get_broker_positions()
            for pos in positions.get("net", []) or []:
                if (pos.get("tradingsymbol", "").upper() == ticker.upper()
                        and int(pos.get("quantity") or 0) > 0):
                    logger.error(
                        "penny_reconcile_position_found ticker=%s qty=%s "
                        "order_id=%s -- treating entry as FILLED",
                        ticker, pos.get("quantity"), order_id,
                    )
                    return "FILLED"
        except Exception as e:
            logger.error("penny_reconcile_positions_failed ticker=%s error=%s",
                         ticker, str(e))
            logger.error(
                "penny_entry_unverified ticker=%s order_id=%s shares=%d "
                "-- could not read order state OR positions after a fill "
                "timeout. VERIFY IN THE KITE APP: if the buy filled, this "
                "position has NO stop-loss.",
                ticker, order_id, shares,
            )
            return "UNVERIFIED"
        if not final:
            # No position, but the order's state never became readable and
            # the cancel may have failed -- a resting open order could still
            # fill later with no SL behind it. Loud enough to act on.
            logger.warning(
                "penny_reconcile_order_state_unknown ticker=%s order_id=%s "
                "-- no position held, but confirm in the Kite app that the "
                "order is not still open",
                ticker, order_id,
            )
        return "DEAD"

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
