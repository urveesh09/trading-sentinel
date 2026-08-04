"""
[FNO-EXECUTOR 2026-07-10] Order path for the F&O subsystem (spec §10.1).

LIMIT orders only. Never market. The bid-ask spread on an option is the
single largest controllable cost.

  Entry: LIMIT at ask, FNO_FILL_TIMEOUT_SEC then cancel. NEVER chase --
         a missed fill is free; a chased fill is not.
  Exit:  LIMIT at bid, escalating to bid - 3 ticks after 15s.
  Hard flat (15:10): a marketable limit wide enough to guarantee the
         fill -- the position MUST close.

Paper mode fills honestly against the REAL book: entry at ask, exit at
bid. Paying the spread in paper is deliberate -- it is the cost model's
first-order term and pretending mid-fills would make the paper leg lie
(same reasoning as the missing FNO_BROKERAGE_BYPASS, §10.2).

Every order is tagged with the leg source (spec §10.1).

There is no SL order type anywhere in this module: Zerodha does not
support SL-M on options (VERIFY-1), so the stop is engine-managed. We
accept that ONLY because the long-option structure already bounds the
loss at the premium paid -- a frozen engine costs the premium, nothing
more. This reasoning does not survive a short leg (spec §8.4).
"""
from __future__ import annotations

import asyncio
from typing import Optional
from uuid import uuid4

import structlog

from config import settings
from kite_client import latest_order_state

logger = structlog.get_logger()

# 15:10 hard-flat marketable-limit depth: 100 ticks (Rs 5) through the
# bid. Deep enough to cross any sane NIFTY-option book, still a LIMIT so
# a broken book (bid=0.05) cannot fill us at 0.
HARD_FLAT_TICKS_THROUGH = 100


class FnoExecutor:
    def __init__(self, kite, paper_mode: bool = True, source_tag: str = "FNO_PAPER"):
        self.kite = kite
        self.paper_mode = paper_mode
        self.source_tag = source_tag
        self.fill_timeout_sec = float(settings.FNO_FILL_TIMEOUT_SEC)
        self.poll_interval_sec = 2.0

    # ------------------------------------------------------------------
    # entry
    # ------------------------------------------------------------------

    async def execute_entry(
        self, tradingsymbol: str, qty: int, ask: float,
    ) -> dict:
        """BUY LIMIT at ask. Returns {status, order_id, fill_price}.
        status in: paper | filled | timeout | rejected."""
        if self.paper_mode:
            logger.info(
                "fno_paper_entry symbol=%s qty=%d fill=ask=%.2f tag=%s",
                tradingsymbol, qty, ask, self.source_tag,
            )
            return {
                "status": "paper",
                "order_id": f"PAPER-FNO-ENT-{uuid4().hex[:8]}",
                "fill_price": ask,
            }
        resp = await self._place_limit(tradingsymbol, "BUY", qty, ask, intent="entry")
        order_id = resp.get("order_id")
        if not order_id:
            return {"status": "rejected", "order_id": None, "fill_price": None}
        fill = await self._wait_for_fill(order_id)
        if fill is None:
            await self._cancel_quietly(order_id)
            logger.warning(
                "fno_entry_timeout_cancelled symbol=%s order_id=%s -- never chase",
                tradingsymbol, order_id,
            )
            return {"status": "timeout", "order_id": order_id, "fill_price": None}
        return {"status": "filled", "order_id": order_id, "fill_price": fill}

    # ------------------------------------------------------------------
    # exit
    # ------------------------------------------------------------------

    async def execute_exit(
        self, tradingsymbol: str, qty: int, bid: float,
        tick_size: float, hard_flat: bool = False,
    ) -> dict:
        """SELL LIMIT at bid; escalate to bid-3 ticks after 15s; on the
        hard flat go straight to a deeply marketable limit."""
        if self.paper_mode:
            logger.info(
                "fno_paper_exit symbol=%s qty=%d fill=bid=%.2f hard_flat=%s tag=%s",
                tradingsymbol, qty, bid, hard_flat, self.source_tag,
            )
            return {
                "status": "paper",
                "order_id": f"PAPER-FNO-EXT-{uuid4().hex[:8]}",
                "fill_price": bid,
            }

        if hard_flat:
            price = max(tick_size, bid - HARD_FLAT_TICKS_THROUGH * tick_size)
            resp = await self._place_limit(tradingsymbol, "SELL", qty, price, intent="exit")
            order_id = resp.get("order_id")
            fill = await self._wait_for_fill(order_id) if order_id else None
            if fill is None:
                logger.critical(
                    "fno_hard_flat_unfilled symbol=%s order_id=%s -- OPERATOR "
                    "MUST FLATTEN MANUALLY (position may go to expiry)",
                    tradingsymbol, order_id,
                )
                return {"status": "unfilled", "order_id": order_id, "fill_price": None}
            return {"status": "filled", "order_id": order_id, "fill_price": fill}

        # Normal exit ladder: bid, then bid - 3 ticks.
        resp = await self._place_limit(tradingsymbol, "SELL", qty, bid, intent="exit")
        order_id = resp.get("order_id")
        if not order_id:
            return {"status": "rejected", "order_id": None, "fill_price": None}
        fill = await self._wait_for_fill(order_id, timeout=15.0)
        if fill is not None:
            return {"status": "filled", "order_id": order_id, "fill_price": fill}
        await self._cancel_quietly(order_id)
        price2 = max(tick_size, bid - 3 * tick_size)
        resp2 = await self._place_limit(tradingsymbol, "SELL", qty, price2, intent="exit")
        order_id2 = resp2.get("order_id")
        fill2 = await self._wait_for_fill(order_id2) if order_id2 else None
        if fill2 is None:
            logger.warning(
                "fno_exit_ladder_unfilled symbol=%s -- will retry next tick",
                tradingsymbol,
            )
            if order_id2:
                await self._cancel_quietly(order_id2)
            return {"status": "unfilled", "order_id": order_id2, "fill_price": None}
        return {"status": "filled", "order_id": order_id2, "fill_price": fill2}

    # ------------------------------------------------------------------
    # plumbing
    # ------------------------------------------------------------------

    async def _place_limit(
        self, tradingsymbol: str, txn: str, qty: int, price: float,
        *, intent: str,
    ) -> dict:
        """`intent` is required: see KiteClient.place_order. Entries are
        halt-gated, the exit ladder never is."""
        try:
            return await self.kite.place_order(
                variety="regular",
                exchange="NFO",
                tradingsymbol=tradingsymbol,
                transaction_type=txn,
                quantity=qty,
                product="MIS",           # intraday only in P1 (spec §0)
                order_type="LIMIT",
                price=round(price, 2),
                validity="DAY",
                tag=self.source_tag[:20],
                intent=intent, channel="fno",
            )
        except Exception as e:
            logger.error(
                "fno_place_order_failed symbol=%s txn=%s error=%s",
                tradingsymbol, txn, str(e),
            )
            return {"order_id": None, "status": "ERROR"}

    async def _wait_for_fill(
        self, order_id: Optional[str], timeout: Optional[float] = None,
    ) -> Optional[float]:
        """Poll order_history until COMPLETE. Returns average fill price
        or None on timeout/rejection."""
        if not order_id:
            return None
        deadline = timeout if timeout is not None else self.fill_timeout_sec
        elapsed = 0.0
        while elapsed < deadline:
            try:
                history = await self.kite.order_history(order_id=order_id)
                if history:
                    # [ORDER-HISTORY-2026-07-17] Kite history is
                    # chronological; history[0] is the OLDEST event and
                    # never shows COMPLETE. Same bug as penny_executor.
                    latest = latest_order_state(history)
                    status = latest.get("status")
                    if status == "COMPLETE":
                        avg = latest.get("average_price")
                        price = latest.get("price")
                        # [AUDIT-FIX-PHASE1 2026-07-11] Loud-but-non-blocking:
                        # a COMPLETE row with NEITHER average_price NOR
                        # price is a broker response anomaly. Returning
                        # None silently treats it as "no fill" -> the
                        # order is retried and could double-fill if the
                        # original DID execute at Kite's end. Warn so
                        # the operator sees the bad order row and can
                        # reconcile.
                        if avg is None and price is None:
                            logger.warning(
                                "fno_completed_order_no_price order_id=%s "
                                "-- status=COMPLETE but neither "
                                "average_price nor price present; treating "
                                "as no-fill to avoid double-entry risk",
                                order_id,
                            )
                            return None
                        return float(avg or price or 0.0) or None
                    if status in ("REJECTED", "CANCELLED"):
                        logger.warning(
                            "fno_order_terminal order_id=%s status=%s", order_id, status,
                        )
                        return None
            except Exception as e:
                logger.error("fno_order_history_failed order_id=%s error=%s", order_id, str(e))
            await asyncio.sleep(self.poll_interval_sec)
            elapsed += self.poll_interval_sec
        return None

    async def _cancel_quietly(self, order_id: str) -> None:
        try:
            await self.kite.cancel_order(order_id)
        except Exception as e:
            logger.error("fno_cancel_failed order_id=%s error=%s", order_id, str(e))
