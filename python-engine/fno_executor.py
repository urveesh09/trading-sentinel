"""
[FNO-EXECUTOR 2026-07-10] Order path for the F&O subsystem (spec §10.1).

LIMIT orders only. Never market. The bid-ask spread on an option is the
single largest controllable cost.

  Entry: LIMIT at ask, FNO_FILL_TIMEOUT_SEC then cancel. NEVER chase --
         a missed fill is free; a chased fill is not.
  Exit:  [O25] one SELL LIMIT just under the bid, modified lower in steps
         (EXIT_LADDER) until it fills; one still working is followed up on
         every later pass (follow_exit). Never a second SELL order.
  Hard flat (15:10): the ladder's deepest step at once -- the position
         MUST close.

Paper mode fills honestly against the REAL book: entry at ask, exit at
bid. Paying the spread in paper is deliberate -- it is the cost model's
first-order term and pretending mid-fills would make the paper leg lie
(same reasoning as the missing FNO_BROKERAGE_BYPASS, §10.2).

Every order is tagged with the leg source (spec §10.1).

Zerodha does not support SL-M on options (VERIFY-1), so the stop is
engine-managed. A long option bounds the loss at the premium paid, but a
frozen engine still costs the whole premium: Oct 16 had a 321-minute
outage in market hours. [O21-BS 2026-10-21] ``place_stop_limit`` rests one
SL (stop-limit) SELL at the broker below the engine's stop as a backstop
for LIVE positions (fno_broker_backstop.py); the engine stop still acts
first. This reasoning does not survive a short leg (spec §8.4).
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Optional
from uuid import uuid4

import structlog

from config import settings
from kite_client import latest_order_state

logger = structlog.get_logger()

# 15:10 hard-flat marketable-limit depth: 100 ticks (Rs 5) through the
# bid. Deep enough to cross any sane NIFTY-option book, still a LIMIT so
# a broken book (bid=0.05) cannot fill us at 0.
HARD_FLAT_TICKS_THROUGH = 100

# [O25 2026-10-25] A live exit is one SELL LIMIT that is worked until it
# fills: (share of the bid, minimum ticks) under the bid, and the seconds it
# waits at that price before the order is modified lower. A SELL LIMIT under
# the bid still trades at the best bid (or better), so the deeper steps only
# matter when the bid is falling away; the last step is the hard-flat depth
# or 10%, whichever is deeper. The old exit waited 15 s at the bid and then
# left the order resting at a stale price with the position unmanaged (a
# stop in a falling market is exactly when that happens).
EXIT_LADDER = ((0.005, 2, 4.0), (0.03, 10, 6.0), (0.10, HARD_FLAT_TICKS_THROUGH, 20.0))
# A working exit found unfilled on a later pass is re-priced this far under
# the fresh bid (never above its current price).
FOLLOW_UP_SHARE, FOLLOW_UP_TICKS = 0.10, HARD_FLAT_TICKS_THROUGH
_TERMINAL = ("COMPLETE", "CANCELLED", "REJECTED")


def _tick_floor(value: float, tick: float) -> float:
    return round(max(tick, int(round(value / tick, 6)) * tick), 2)


def _resting_price(latest: dict, fallback: float) -> float:
    """[O25b] The limit the broker shows the order resting at, else ``fallback``
    (the last price the broker accepted)."""
    try:
        price = float(latest.get("price") or 0.0)
    except (TypeError, ValueError):
        price = 0.0
    return round(price, 2) if price > 0 else fallback


async def _emit(on_event, kind: str, **detail) -> None:
    """Tell the caller about the order; its own failure never stops an exit."""
    if on_event is None:
        return
    try:
        await on_event(kind, **detail)
    except Exception as e:
        logger.error("fno_exit_event_callback_failed kind=%s error=%s", kind, str(e))


def exit_ladder_prices(bid: float, tick: float) -> list[tuple[float, float]]:
    """(limit, wait seconds) for each exit step; never rising, never under one tick."""
    steps, last = [], None
    for share, ticks, wait in EXIT_LADDER:
        price = _tick_floor(bid - max(share * bid, ticks * tick), tick)
        price = price if last is None else min(price, last)
        steps.append((price, wait))
        last = price
    return steps


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
        self, tradingsymbol: str, qty: int, ask: float, *, exchange: str = "NFO",
    ) -> dict:
        """BUY LIMIT at ask. Returns {status, order_id, fill_price, evidence}.

        [F0-R2 2026-10-03] status is one of:
          paper | filled             -- a fill with a known average price
          no_dispatch                -- proven never sent (halt/validation/connect)
          rejected                   -- explicit broker 4xx, no order created
          zero_fill_verified         -- final order state re-read after cancel is
                                        CANCELLED/REJECTED with filled_quantity 0
          partial                    -- terminal with 0 < filled_quantity < qty
          unknown                    -- anything that cannot prove the above
        Only the first four can ever free reserved capital; ``partial`` and
        ``unknown`` must be reconciled. A swallowed cancel error or an
        unreadable final state is ``unknown``, never a quiet ``timeout``.
        """
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
        resp = await self._place_limit(tradingsymbol, "BUY", qty, ask, intent="entry", exchange=exchange)
        order_id = resp.get("order_id")
        if not order_id:
            certainty = resp.get("dispatch_certainty") or "AMBIGUOUS"
            status = {"NOT_SENT": "no_dispatch", "BROKER_REJECTED": "rejected"}.get(
                certainty, "unknown")
            evidence = {"dispatch_certainty": certainty, "order_id": None,
                        "message": str(resp.get("message") or "")[:300]}
            if status == "unknown":
                logger.critical(
                    "fno_entry_dispatch_ambiguous symbol=%s certainty=%s -- the broker may "
                    "hold an order; reserved capital is retained until reconciled",
                    tradingsymbol, certainty,
                )
            return {"status": status, "order_id": None, "fill_price": None, "evidence": evidence}
        fill = await self._wait_for_fill(order_id)
        if fill is not None:
            self._settle_account_cash(order_id, "COMPLETE", qty)
            return {"status": "filled", "order_id": order_id, "fill_price": fill,
                    "evidence": {"dispatch_certainty": "ACCEPTED", "order_id": order_id,
                                 "final_status": "COMPLETE", "average_price": fill}}
        cancel_error = await self._cancel_quietly(order_id)
        return await self._verify_unfilled_entry(tradingsymbol, order_id, qty, cancel_error)

    async def _verify_unfilled_entry(
        self, tradingsymbol: str, order_id: str, qty: int, cancel_error: Optional[str],
    ) -> dict:
        """Re-read the broker's final order state after a cancel attempt."""
        latest: dict = {}
        read_error = None
        for attempt in range(3):
            try:
                latest = latest_order_state(await self.kite.order_history(order_id=order_id) or [])
            except Exception as exc:
                read_error = f"{type(exc).__name__}: {exc}"[:200]
                latest = {}
            if latest.get("status") in ("COMPLETE", "CANCELLED", "REJECTED"):
                break
            if attempt < 2:
                await asyncio.sleep(self.poll_interval_sec)
        final_status = latest.get("status")
        filled = latest.get("filled_quantity")
        filled = filled if type(filled) is int and filled >= 0 else None
        average = latest.get("average_price")
        evidence = {
            "dispatch_certainty": "ACCEPTED", "order_id": order_id,
            "final_status": final_status, "filled_quantity": filled,
            "average_price": average, "cancel_error": cancel_error,
            "read_error": read_error, "requested_quantity": qty,
        }
        if final_status == "COMPLETE":
            try:
                price = float(average or latest.get("price") or 0.0)
            except (TypeError, ValueError):
                price = 0.0
            if price > 0:
                logger.warning("fno_entry_filled_during_cancel symbol=%s order_id=%s",
                               tradingsymbol, order_id)
                self._settle_account_cash(order_id, "COMPLETE", filled)
                return {"status": "filled", "order_id": order_id, "fill_price": price,
                        "evidence": evidence}
        elif final_status in ("CANCELLED", "REJECTED") and filled == 0:
            logger.warning(
                "fno_entry_unfilled_verified symbol=%s order_id=%s status=%s -- never chase",
                tradingsymbol, order_id, final_status,
            )
            self._settle_account_cash(order_id, final_status, 0)
            return {"status": "zero_fill_verified", "order_id": order_id, "fill_price": None,
                    "evidence": evidence}
        elif final_status in ("CANCELLED", "REJECTED") and filled is not None and 0 < filled < qty:
            logger.critical(
                "fno_entry_partial_fill symbol=%s order_id=%s filled=%d/%d -- OPERATOR MUST "
                "RECONCILE; full reserved capital retained",
                tradingsymbol, order_id, filled, qty,
            )
            return {"status": "partial", "order_id": order_id, "fill_price": None,
                    "evidence": evidence}
        logger.critical(
            "fno_entry_outcome_unknown symbol=%s order_id=%s status=%s filled=%s "
            "cancel_error=%s read_error=%s -- OPERATOR MUST RECONCILE; reserved capital retained",
            tradingsymbol, order_id, final_status, filled, cancel_error, read_error,
        )
        return {"status": "unknown", "order_id": order_id, "fill_price": None, "evidence": evidence}

    # ------------------------------------------------------------------
    # exit
    # ------------------------------------------------------------------

    async def execute_exit(
        self, tradingsymbol: str, qty: int, bid: float,
        tick_size: float, hard_flat: bool = False, *, exchange: str = "NFO",
        tag: Optional[str] = None, on_event: Optional[Callable[..., Awaitable[None]]] = None,
    ) -> dict:
        """Submit one SELL LIMIT. An uncertain fill requires reconciliation.

        On hard flat use a deeply marketable limit. Never replace an order
        merely because polling or cancellation did not prove its final fill.
        [O25b] ``tag`` is the exit's own broker tag (written by the caller
        before the send, so a lost reply can be found); ``on_event(kind,
        **detail)`` hears ``placed`` before any wait (the caller records the
        order id), then ``modified`` / ``modify_refused``.
        """
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

        # [O25] One order, worked down the ladder (the hard flat starts at its
        # deepest step). Statuses: filled | not_sent (nothing reached the
        # broker) | rejected_verified (terminal, nothing filled) | unfilled
        # (still working at the deepest price: the caller follows it up) |
        # unknown (the broker may hold an order this cannot read).
        steps = exit_ladder_prices(bid, tick_size)
        if hard_flat:
            steps = steps[-1:]
        resp = await self._place_limit(tradingsymbol, "SELL", qty, steps[0][0], intent="exit", exchange=exchange,
                                       tag=tag)
        order_id = resp.get("order_id")
        if not order_id:
            certainty = resp.get("dispatch_certainty") or "AMBIGUOUS"
            status = "not_sent" if certainty in ("NOT_SENT", "BROKER_REJECTED") else "unknown"
            logger.critical("fno_exit_order_not_placed symbol=%s certainty=%s status=%s",
                            tradingsymbol, certainty, status)
            return {"status": status, "order_id": None, "fill_price": None,
                    "evidence": {"dispatch_certainty": certainty,
                                 "message": str(resp.get("message") or "")[:300]}}
        resting = steps[0][0]
        await _emit(on_event, "placed", order_id=order_id, price=resting)
        for index, (price, wait) in enumerate(steps):
            if index and price < resting and await self._reprice(order_id, price, on_event):
                resting = price
            latest = await self._watch(order_id, wait)
            outcome = self._exit_outcome(order_id, latest)
            if outcome is not None:
                return outcome
            resting = _resting_price(latest, resting)
        logger.critical(
            "fno_exit_working symbol=%s order_id=%s limit=%.2f hard_flat=%s -- still unfilled after the "
            "price steps; followed up every pass", tradingsymbol, order_id, resting, hard_flat,
        )
        return {"status": "unfilled", "order_id": order_id, "fill_price": None, "limit": resting}

    def _settle_account_cash(self, order_id: str, final_status: str, filled_quantity) -> None:
        """[O25] Free the BUY's own-cash hold once its outcome is proven (kite_client)."""
        settle = getattr(type(self.kite), "settle_entry_reservation", None)
        if not callable(settle):
            return
        try:
            settle(self.kite, order_id, final_status=final_status, filled_quantity=filled_quantity)
        except Exception as e:
            logger.error("fno_account_cash_release_failed order_id=%s error=%s", order_id, str(e))

    async def follow_exit(self, order_id: str, limit: float, bid: float, tick_size: float,
                          on_event: Optional[Callable[..., Awaitable[None]]] = None) -> dict:
        """[O25] A working exit found on a later pass: read it, and if it still
        rests, move it under the fresh bid (never up). Same statuses as
        ``execute_exit``; ``limit`` is the price the broker shows it resting
        at [O25b]: a refused modification leaves it where it was, so the next
        pass tries again."""
        latest = await self.order_state(order_id)
        outcome = self._exit_outcome(order_id, latest)
        if outcome is not None:
            return outcome
        resting = _resting_price(latest, limit)
        if bid > 0:
            lower = _tick_floor(bid - max(FOLLOW_UP_SHARE * bid, FOLLOW_UP_TICKS * tick_size), tick_size)
            if lower < resting and await self._reprice(order_id, lower, on_event):
                resting = lower
        latest = await self._watch(order_id, 2 * self.poll_interval_sec)
        outcome = self._exit_outcome(order_id, latest)
        return outcome or {"status": "unfilled", "order_id": order_id, "fill_price": None,
                           "limit": _resting_price(latest, resting)}

    def _exit_outcome(self, order_id: str, latest: dict) -> Optional[dict]:
        """A final answer from the order's latest state, or None while it works."""
        status = latest.get("status")
        filled = latest.get("filled_quantity")
        filled = filled if type(filled) is int and filled >= 0 else None
        if status == "COMPLETE":
            try:
                price = float(latest.get("average_price") or latest.get("price") or 0.0)
            except (TypeError, ValueError):
                price = 0.0
            if price > 0:
                return {"status": "filled", "order_id": order_id, "fill_price": price}
            logger.critical("fno_exit_complete_without_price order_id=%s -- reconcile", order_id)
            return {"status": "unknown", "order_id": order_id, "fill_price": None}
        if status in ("CANCELLED", "REJECTED"):
            if filled == 0:
                logger.warning("fno_exit_terminal_unfilled order_id=%s status=%s msg=%s", order_id, status,
                               str(latest.get("status_message") or "")[:200])
                return {"status": "rejected_verified", "order_id": order_id, "fill_price": None,
                        "evidence": {"final_status": status, "filled_quantity": 0}}
            logger.critical("fno_exit_terminal_partial order_id=%s status=%s filled=%s -- reconcile",
                            order_id, status, filled)
            return {"status": "unknown", "order_id": order_id, "fill_price": None,
                    "evidence": {"final_status": status, "filled_quantity": filled}}
        return None

    async def _watch(self, order_id: str, seconds: float) -> dict:
        """Poll until a terminal state or ``seconds`` pass; the latest state read."""
        latest: dict = {}
        elapsed = 0.0
        while True:
            state = await self.order_state(order_id)
            latest = state or latest
            if latest.get("status") in _TERMINAL or elapsed >= seconds:
                return latest
            await asyncio.sleep(self.poll_interval_sec)
            elapsed += self.poll_interval_sec

    async def _reprice(self, order_id: str, price: float,
                       on_event: Optional[Callable[..., Awaitable[None]]] = None) -> bool:
        """Move a working SELL LIMIT. True only when the broker accepted it: a
        refusal (it filled meanwhile, or the price was refused) leaves the
        order where it rests, and the next read or pass decides."""
        try:
            result = await self.kite.modify_order(order_id, price=round(price, 2))
            message = str(result.get("message") or "")[:200]
            accepted = result.get("status") == "MODIFIED"
        except Exception as e:
            accepted, message = False, f"{type(e).__name__}: {e}"[:200]
        if accepted:
            await _emit(on_event, "modified", order_id=order_id, price=round(price, 2))
            return True
        logger.warning("fno_exit_modify_refused order_id=%s price=%.2f msg=%s", order_id, price, message)
        await _emit(on_event, "modify_refused", order_id=order_id, price=round(price, 2), message=message)
        return False

    # ------------------------------------------------------------------
    # plumbing
    # ------------------------------------------------------------------

    async def _place_limit(
        self, tradingsymbol: str, txn: str, qty: int, price: float,
        *, intent: str, exchange: str = "NFO", tag: Optional[str] = None,
    ) -> dict:
        """`intent` is required: see KiteClient.place_order. Entries are
        halt-gated, the exit ladder never is."""
        try:
            return await self.kite.place_order(
                variety="regular",
                exchange=exchange,
                tradingsymbol=tradingsymbol,
                transaction_type=txn,
                quantity=qty,
                product="MIS",           # intraday only in P1 (spec §0)
                order_type="LIMIT",
                price=round(price, 2),
                validity="DAY",
                tag=(tag or self.source_tag)[:20],
                intent=intent, channel="fno",
            )
        except Exception as e:
            logger.error(
                "fno_place_order_failed symbol=%s txn=%s error=%s",
                tradingsymbol, txn, str(e),
            )
            # An exception escaping the client may have occurred after the
            # request reached the broker: never treat it as a rejection.
            return {"order_id": None, "status": "ERROR", "dispatch_certainty": "AMBIGUOUS",
                    "message": f"{type(e).__name__}: {e}"[:300]}

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

    # ------------------------------------------------------------------
    # broker backstop (O21-BS)
    # ------------------------------------------------------------------

    async def place_stop_limit(
        self, tradingsymbol: str, qty: int, trigger: float, limit: float, *, exchange: str = "NFO",
        tag: Optional[str] = None,
    ) -> dict:
        """Rest one SELL SL (stop-limit) order. Returns {status, order_id, evidence}.

        status: paper | placed | rejected | unknown. ``intent="exit"``: a
        protective order is never blocked by an entry halt. ``tag`` is the
        backstop intent's own broker tag [S23-BS1]."""
        if self.paper_mode:
            return {"status": "paper", "order_id": None}
        try:
            resp = await self.kite.place_order(
                variety="regular", exchange=exchange, tradingsymbol=tradingsymbol,
                transaction_type="SELL", quantity=qty, product="MIS", order_type="SL",
                price=round(limit, 2), trigger_price=round(trigger, 2), validity="DAY",
                tag=(tag or self.source_tag)[:20], intent="exit", channel="fno",
            )
        except Exception as e:
            return {"status": "unknown", "order_id": None,
                    "evidence": {"dispatch_certainty": "AMBIGUOUS", "message": f"{type(e).__name__}: {e}"[:300]}}
        order_id = resp.get("order_id")
        if order_id:
            return {"status": "placed", "order_id": order_id, "evidence": {"dispatch_certainty": "ACCEPTED"}}
        certainty = resp.get("dispatch_certainty") or "AMBIGUOUS"
        return {"status": "rejected" if certainty in ("NOT_SENT", "BROKER_REJECTED") else "unknown",
                "order_id": None,
                "evidence": {"dispatch_certainty": certainty, "message": str(resp.get("message") or "")[:300]}}

    async def order_state(self, order_id: str) -> dict:
        """Latest broker state of one order; {} when it cannot be read."""
        try:
            return latest_order_state(await self.kite.order_history(order_id=order_id) or [])
        except Exception as e:
            logger.error("fno_order_state_failed order_id=%s error=%s", order_id, str(e))
            return {}

    async def cancel_and_read(self, order_id: str, variety: str = "regular") -> tuple[dict, Optional[str]]:
        """Cancel, then re-read until a terminal state (3 tries). [O25c] ``variety`` "amo" for an
        after-market order (its cancel is DELETE /orders/amo/{id})."""
        cancel_error = await self._cancel_quietly(order_id, variety)
        latest: dict = {}
        for attempt in range(3):
            latest = await self.order_state(order_id)
            if latest.get("status") in ("COMPLETE", "CANCELLED", "REJECTED", "CANCELLED AMO"):
                break
            if attempt < 2:
                await asyncio.sleep(self.poll_interval_sec)
        return latest, cancel_error

    async def _cancel_quietly(self, order_id: str, variety: str = "regular") -> Optional[str]:
        """Cancel; return the error text (``None`` on success) for evidence."""
        try:
            if variety == "regular":
                await self.kite.cancel_order(order_id)
            else:
                await self.kite.cancel_order(order_id, variety=variety)
            return None
        except Exception as e:
            logger.error("fno_cancel_failed order_id=%s error=%s", order_id, str(e))
            return f"{type(e).__name__}: {e}"[:200]
