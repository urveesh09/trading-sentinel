"""
[PENNY-EXECUTOR 2026-06-21] Order execution flow for the penny subsystem.

Spec §7.2: MANDATORY broker-level protective stop for every entry. If the stop
cannot be placed (broker rejection, network error, unsupported order type), the
executor MUST immediately exit the position. No in-engine stop fallback --
gap-down protection only works when the broker holds the trigger.

[2026-07-31] Three corrections after the 2026-07-30 SIGMA incident, where the
buy filled, the stop was rejected, the unwind was ALSO rejected, and the caller
was told the entry had succeeded:

  * the stop is an SL (stop-loss LIMIT), never SL-M. Zerodha refuses MARKET
    orders over the API without market protection, so every SL-M was rejected.
  * the unwind is a marketable SELL LIMIT for the same reason, and the executor
    now waits for its fill before claiming the position was flattened. If it
    cannot confirm, entry_status is "unprotected" and the operator is paged.
  * entries are priced and sanity-checked against a LIVE quote, not against the
    signal's (possibly stale) close, and a ticker the broker has structurally
    refused is not retried for the rest of the session.

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
import math
from typing import Optional

from kite_client import latest_order_state
from penny_models import PennyLeg

logger = logging.getLogger(__name__)

# Broker-terminal order states. An order in one of these states will never
# fill later; anything else is still in flight.
_TERMINAL_DEAD = ("REJECTED", "CANCELLED")

# [EDGE-DRIFT 2026-07-31] Max tolerated gap between the price the signal was
# computed at and the live LTP at execution time. The 2026-07-30 SIGMA entry
# was booked at 52.40 while the stock was trading 48.86 -- a 7.3% phantom
# edge -- because the EDGE scan prices entries off a partially-formed daily
# candle fetched minutes earlier (penny_edge_live.scan_today uses
# `t_bars[t_idx]["close"]`, and t_idx is TODAY when the cron runs at 09:30).
# node-gateway's momentum path has had a 2% drift check since 2026-07-15;
# this is the same guard for the Python side.
MAX_ENTRY_DRIFT_PCT = 0.02

# Worst-case slippage allowed on a protective stop once it triggers, and on
# an emergency unwind. Both are expressed as a fraction below the reference
# price and exist so we can use LIMIT orders (which Kite accepts over the
# API) instead of MARKET orders (which it rejects without market protection).
STOP_LIMIT_SLIP_PCT = 0.01
UNWIND_LIMIT_SLIP_PCT = 0.01


# [RETRY-STORM 2026-07-31] Per-ticker entry circuit breaker.
#
# 2026-07-29: the breakout scanner accepted KCPSUGIND and then placed the same
# order every 30 seconds from 11:34:21 to 11:47:59 -- 25 attempts, every one
# rejected with "MIS orders are currently blocked for KCPSUGIND. Place a CNC
# order instead." Nothing backed off, nothing blacklisted the ticker, and
# nothing alerted; the storm stopped only because the breakout time window
# closed. It also inflated ops_funnel_daily to "penny accepted=25" for what was
# one signal and zero trades.
#
# A rejection naming a condition of the INSTRUMENT (banned, blocked, not
# permitted) cannot succeed on a retry -- the ban lasts the session. Everything
# else gets a small bounded number of attempts.
MAX_ENTRY_ATTEMPTS_PER_TICKER = 3

_NON_RETRYABLE_MARKERS = (
    "are currently blocked",
    "is blocked",
    "blocked for",
    "not allowed",
    "not permitted",
    "banned",
    "ban period",
)

# ticker -> {"attempts": int, "blocked_reason": str|None}
_entry_failures: dict = {}


def _is_non_retryable(message: str) -> bool:
    m = (message or "").lower()
    return any(marker in m for marker in _NON_RETRYABLE_MARKERS)


def note_entry_failure(ticker: str, message: str) -> None:
    """Record a failed entry attempt and block the ticker if warranted."""
    key = (ticker or "").upper()
    st = _entry_failures.setdefault(key, {"attempts": 0, "blocked_reason": None})
    st["attempts"] += 1
    if _is_non_retryable(message):
        st["blocked_reason"] = f"broker refused this instrument: {message[:120]}"
        logger.error(
            "penny_entry_ticker_blocked ticker=%s reason=non_retryable attempts=%d "
            "message=%s -- no further entry attempts today",
            key, st["attempts"], (message or "")[:200],
        )
    elif st["attempts"] >= MAX_ENTRY_ATTEMPTS_PER_TICKER:
        st["blocked_reason"] = (
            f"{st['attempts']} consecutive failed entries; last: {message[:120]}"
        )
        logger.error(
            "penny_entry_ticker_blocked ticker=%s reason=attempt_limit attempts=%d "
            "-- no further entry attempts today",
            key, st["attempts"],
        )


def entry_blocked(ticker: str) -> Optional[str]:
    """Reason this ticker is barred from further entries today, or None."""
    return (_entry_failures.get((ticker or "").upper()) or {}).get("blocked_reason")


def note_entry_success(ticker: str) -> None:
    """A fill clears the failure streak for this ticker."""
    _entry_failures.pop((ticker or "").upper(), None)


def reset_entry_blocks() -> None:
    """Clear every block. Called by the daily reset -- broker ban lists and
    MIS-blocked lists are published per session."""
    n = len(_entry_failures)
    _entry_failures.clear()
    if n:
        logger.info("penny_entry_blocks_reset cleared=%d", n)


def snap_to_tick(price: float, direction: int = -1) -> float:
    """Snap a price to a valid NSE tick (0.10 rupee -- the LCM of the 0.05
    and 0.10 tick sizes). direction=-1 rounds DOWN (sell side), +1 rounds UP
    (buy side). Integer arithmetic avoids IEEE-754 drift.

    Mirrors main.snap_to_tick; duplicated rather than imported because this
    module must not import the Nifty-side modules (see the header rule)."""
    in_tenths = round(price * 10 * 100) / 100
    fn = math.ceil if direction >= 0 else math.floor
    return fn(in_tenths) / 10


class PennyExecutor:
    def __init__(
        self,
        kite,
        paper_mode: bool = True,
        fill_timeout_sec: float = 60.0,
        poll_interval_sec: float = 2.0,
        event_sink=None,
    ):
        self.kite = kite
        self.paper_mode = paper_mode
        self.fill_timeout_sec = fill_timeout_sec
        self.poll_interval_sec = poll_interval_sec
        self.event_sink = event_sink

    async def _emit(self, event_type: str, payload: dict, context: dict | None) -> None:
        """Best-effort observability: journal failure can never alter orders."""
        if self.event_sink is None or context is None:
            return
        try:
            await self.event_sink(event_type, payload, context)
        except Exception as exc:
            logger.error("penny_execution_journal_failed event=%s error=%s",
                         event_type, str(exc))

    async def execute_entry(
        self,
        ticker: str,
        leg: PennyLeg,
        entry_price: float,
        stop_loss: float,
        shares: int,
        attempt_context: dict | None = None,
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
            "fill_price": None,
            "ltp_at_entry": None,
            "reject_reason": None,
        }

        # ---- step 0a: per-ticker circuit breaker ----------------------
        # [RETRY-STORM 2026-07-31] Refuse before spending a broker call.
        blocked = entry_blocked(ticker)
        if blocked and not self.paper_mode:
            result["entry_status"] = "ticker_blocked"
            result["reject_reason"] = blocked
            logger.warning(
                "penny_entry_ticker_blocked_skip ticker=%s reason=%s",
                ticker, blocked,
            )
            await self._emit("VALIDATION_REJECTED", {"status": result["entry_status"], "reason": blocked[:200]}, attempt_context)
            return result

        # ---- step 0b: price reality check -----------------------------
        # [EDGE-DRIFT 2026-07-31] Runs for paper AND live. The paper book is
        # supposed to be a forecast of the live book; letting it enter at a
        # price the market has left makes it a fiction that flatters itself
        # (2026-07-30: paper booked a 7.3% phantom entry edge on SIGMA and
        # then a -45% "loss" against a bankroll it was never sized against).
        ltp = await self._live_ltp(ticker)
        result["ltp_at_entry"] = ltp

        if ltp is not None:
            drift = abs(ltp - entry_price) / entry_price if entry_price else 1.0
            if drift > MAX_ENTRY_DRIFT_PCT:
                result["entry_status"] = "drift_rejected"
                result["reject_reason"] = (
                    f"signal={entry_price:.2f} ltp={ltp:.2f} drift={drift:.2%}"
                )
                logger.warning(
                    "penny_entry_drift_rejected ticker=%s signal=%.2f ltp=%.2f "
                    "drift=%.2f%% max=%.2f%% -- signal price is stale, refusing entry",
                    ticker, entry_price, ltp, drift * 100,
                    MAX_ENTRY_DRIFT_PCT * 100,
                )
                await self._emit("VALIDATION_REJECTED", {"status": result["entry_status"], "reason": result["reject_reason"]}, attempt_context)
                return result

            # A long whose stop already sits at or above the market is not a
            # trade -- it is a position that is born past its stop. This is
            # precisely what Zerodha told us on 2026-07-30 when it refused the
            # SIGMA stop ("trigger price ... should be lower than the last
            # traded price (48.86)"); by then we already owned the stock.
            if stop_loss >= ltp:
                result["entry_status"] = "stop_already_breached"
                result["reject_reason"] = f"stop={stop_loss:.2f} >= ltp={ltp:.2f}"
                logger.warning(
                    "penny_entry_stop_already_breached ticker=%s stop=%.2f ltp=%.2f "
                    "-- entry would be born past its stop, refusing",
                    ticker, stop_loss, ltp,
                )
                await self._emit("VALIDATION_REJECTED", {"status": result["entry_status"], "reason": result["reject_reason"]}, attempt_context)
                return result
        else:
            # No quote is not a licence to trade blind on a stale price.
            result["entry_status"] = "no_quote"
            result["reject_reason"] = "live LTP unavailable"
            logger.warning(
                "penny_entry_no_quote ticker=%s -- cannot verify signal price "
                "%.2f against the market, refusing entry",
                ticker, entry_price,
            )
            await self._emit("VALIDATION_REJECTED", {"status": result["entry_status"], "reason": result["reject_reason"]}, attempt_context)
            return result

        # ---- paper mode: emit IDs, no kite calls ---------------------
        # Paper fills at the live LTP, not at the (possibly stale) signal
        # price, so paper P&L is answerable to the same market the live leg
        # trades in.
        if self.paper_mode:
            from uuid import uuid4
            result["entry_order_id"] = f"PAPER-ENT-{uuid4().hex[:8]}"
            result["sl_order_id"] = f"PAPER-SL-{uuid4().hex[:8]}"
            result["entry_status"] = "paper"
            result["fill_price"] = ltp
            await self._emit("ENTRY_FILLED", {"status": "paper", "entry_order_id": result["entry_order_id"], "fill_price": ltp, "quantity": shares}, attempt_context)
            await self._emit("SL_PLACED", {"sl_order_id": result["sl_order_id"], "stop_loss": stop_loss, "paper": True}, attempt_context)
            logger.info(
                "penny_paper_entry ticker=%s leg=%s signal=%s fill=%s sl=%s shares=%d",
                ticker, leg.value, entry_price, ltp, stop_loss, shares,
            )
            return result

        # ---- step 1: place entry LIMIT -------------------------------
        # Marketable buy limit at LTP + 0.5%, snapped UP to a valid tick --
        # the same route node-gateway's momentum path uses. Priced off the
        # LIVE quote, never off the signal's stale close.
        limit_price = snap_to_tick(ltp * 1.005, 1)
        try:
            entry_resp = await self.kite.place_order(
                variety="regular", exchange="NSE",
                tradingsymbol=ticker,
                transaction_type="BUY",
                quantity=shares,
                product=leg.value,
                order_type="LIMIT",
                price=limit_price,
                validity="DAY",
                intent="entry", channel="penny",
            )
        except Exception as e:
            logger.error("penny_entry_rejected ticker=%s error=%s", ticker, str(e))
            note_entry_failure(ticker, str(e))
            result["entry_status"] = "rejected"
            result["reject_reason"] = str(e)
            await self._emit("ENTRY_REJECTED", {"status": "rejected", "reason": str(e)[:200]}, attempt_context)
            return result

        entry_id = entry_resp.get("order_id")
        result["entry_order_id"] = entry_id
        if not entry_id:
            # [RETRY-STORM 2026-07-31] place_order returns a dict on an HTTP
            # error rather than raising, so this is the path a "MIS orders are
            # currently blocked for X" rejection takes -- the one that was
            # retried 25 times on 2026-07-29.
            msg = entry_resp.get("message", "") or ""
            note_entry_failure(ticker, msg)
            result["entry_status"] = "rejected"
            result["reject_reason"] = msg
            logger.error("penny_entry_broker_rejected ticker=%s message=%s",
                         ticker, msg[:200])
            await self._emit("ENTRY_REJECTED", {"status": "rejected", "reason": msg[:200]}, attempt_context)
            return result
        await self._emit("ENTRY_SUBMITTED", {"entry_order_id": entry_id, "limit_price": limit_price, "quantity": shares}, attempt_context)

        # ---- step 2: poll for fill ------------------------------------
        fill_state = await self._wait_for_fill(entry_id)

        if fill_state in _TERMINAL_DEAD:
            # Broker already killed the order -- there is nothing to cancel
            # (pre-2026-07-17 this path cancelled anyway and got the
            # confusing "order does not exist" OrderException back).
            result["entry_status"] = "rejected"
            logger.warning("penny_entry_dead ticker=%s order_id=%s status=%s",
                           ticker, entry_id, fill_state)
            await self._emit("ENTRY_REJECTED", {"status": str(fill_state), "entry_order_id": entry_id}, attempt_context)
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
                await self._emit("ENTRY_TIMEOUT", {"entry_order_id": entry_id, "reconciled": str(final)}, attempt_context)
                return result
            logger.warning(
                "penny_entry_filled_after_timeout ticker=%s order_id=%s "
                "-- proceeding to SL placement, NOT dropping the position",
                ticker, entry_id,
            )

        result["entry_status"] = "filled"
        result["fill_price"] = await self._fill_price(entry_id) or ltp
        await self._emit("ENTRY_FILLED", {"status": "filled", "entry_order_id": entry_id, "fill_price": result["fill_price"], "quantity": shares}, attempt_context)
        note_entry_success(ticker)

        # ---- step 3: place the protective stop (retry, then unwind) ---
        sl_id = await self._place_sl_m_with_retry(ticker, leg, stop_loss, shares)
        if sl_id:
            result["sl_order_id"] = sl_id
            logger.info("penny_sl_m_placed ticker=%s order_id=%s trigger=%s",
                        ticker, sl_id, stop_loss)
            await self._emit("SL_PLACED", {"sl_order_id": sl_id, "stop_loss": stop_loss, "paper": False}, attempt_context)
            return result

        # ---- step 4: stop failed -> unwind, and PROVE it ---------------
        # [NAKED-POSITION 2026-07-31] The old code set unwound=True
        # unconditionally, so on 2026-07-30 SIGMA the caller was told the
        # position had been flattened when in fact BOTH the stop and the
        # unwind had been rejected by the broker and 14 shares were sitting
        # naked. Now: only claim the unwind if the broker confirms the fill,
        # and if it cannot be confirmed, say so in entry_status so the
        # orchestrator does not record a tidy position over a live mess.
        logger.error("penny_sl_m_failed_unwinding ticker=%s entry_id=%s sl=%s shares=%d",
                     ticker, entry_id, stop_loss, shares)
        await self._emit("SL_FAILED", {"entry_order_id": entry_id, "stop_loss": stop_loss}, attempt_context)
        unwind_id = await self._market_unwind(ticker, leg, shares, ltp)
        result["unwind_order_id"] = unwind_id
        if unwind_id:
            await self._emit("UNWIND_SUBMITTED", {"unwind_order_id": unwind_id, "quantity": shares}, attempt_context)

        unwind_state = ""
        if unwind_id:
            unwind_state = await self._wait_for_fill(unwind_id)
        if unwind_state == "COMPLETE":
            result["unwound"] = True
            result["entry_status"] = "unwound"
            logger.error(
                "penny_unprotected_unwound ticker=%s shares=%d unwind_order_id=%s "
                "-- stop could not be placed; position flattened and CONFIRMED",
                ticker, shares, unwind_id,
            )
            await self._emit("UNWIND_CONFIRMED", {"unwind_order_id": unwind_id, "quantity": shares}, attempt_context)
            return result

        # Stop failed and the unwind is unconfirmed or failed outright. This
        # is the one state a human has to resolve, so it is loud and it is
        # NOT reported as a successful entry.
        result["unwound"] = False
        result["entry_status"] = "unprotected"
        result["reject_reason"] = (
            f"stop rejected; unwind {'unconfirmed' if unwind_id else 'failed'}"
        )
        logger.critical(
            "penny_position_UNPROTECTED ticker=%s shares=%d entry_id=%s "
            "unwind_id=%s unwind_state=%s -- protective stop FAILED and unwind "
            "did not confirm. YOU MAY BE HOLDING %d SHARES WITH NO STOP. "
            "FLATTEN MANUALLY IN THE KITE APP NOW.",
            ticker, shares, entry_id, unwind_id, unwind_state or "none", shares,
        )
        await self._emit("UNPROTECTED", {"entry_order_id": entry_id, "unwind_order_id": unwind_id, "unwind_state": unwind_state or "none", "quantity": shares}, attempt_context)
        await self._page_operator(
            f"{ticker}: protective stop FAILED and unwind did not confirm. "
            f"You may be holding {shares} shares with NO stop. "
            f"FLATTEN MANUALLY NOW."
        )
        return result

    async def _live_ltp(self, ticker: str) -> Optional[float]:
        """Live last-traded price for `ticker`, or None if unavailable."""
        try:
            token = (getattr(self.kite, "instrument_cache", {}) or {}).get(ticker.upper())
            if not token:
                logger.warning("penny_ltp_no_token ticker=%s", ticker)
                return None
            quotes = await self.kite.get_quote([int(token)])
            for q in (quotes or {}).values():
                px = float(q.get("last_price") or 0)
                if px > 0:
                    return px
            return None
        except Exception as e:
            logger.warning("penny_ltp_failed ticker=%s error=%s", ticker, str(e))
            return None

    async def _fill_price(self, order_id: str) -> Optional[float]:
        """Average traded price of a filled order, or None if unreadable.

        [FILL-TRUTH 2026-07-31] The position used to be recorded at the
        SIGNAL price. Recording the price we actually paid is what makes
        the R-multiple and the P&L answerable to reality."""
        try:
            state = latest_order_state(await self.kite.order_history(order_id=order_id))
            px = float(state.get("average_price") or 0)
            return px if px > 0 else None
        except Exception as e:
            logger.warning("penny_fill_price_failed order_id=%s error=%s",
                           order_id, str(e))
            return None

    async def _page_operator(self, message: str) -> None:
        """Best-effort operator page. Never raises into the order path."""
        try:
            from operator_alert import notify_operator
            await notify_operator(f"[EDGE] {message}", event="edge_position_unprotected")
        except Exception as e:
            logger.error("penny_operator_page_failed error=%s msg=%s", str(e), message)

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
        """Try to place the protective stop up to max_attempts.

        [SL-M 2026-07-31] This used to send order_type="SL-M" (stop-loss
        MARKET). Zerodha rejects MARKET orders over the API without market
        protection, which is why every one of these was refused. We now send
        an "SL" (stop-loss LIMIT) with the limit 1% BELOW the trigger: for a
        SELL SL the limit must be <= trigger, and sitting below the trigger
        makes it marketable the instant it fires, so it behaves like a
        stop-market while capping worst-case slippage at ~1%. This is the
        identical route node-gateway's momentum path has used since
        2026-07-15. Returns order_id or None."""
        trigger = snap_to_tick(stop_loss, -1)
        limit = snap_to_tick(stop_loss * (1.0 - STOP_LIMIT_SLIP_PCT), -1)
        for attempt in range(1, max_attempts + 1):
            try:
                resp = await self.kite.place_order(
                    variety="regular", exchange="NSE",
                    tradingsymbol=ticker,
                    transaction_type="SELL",
                    quantity=shares,
                    product=leg.value,
                    order_type="SL",
                    trigger_price=trigger,
                    price=limit,
                    validity="DAY",
                    tag="QUANT_PENNY_SL",
                    # A protective stop is an exit: never halt-gated.
                    intent="exit", channel="penny",
                )
                if resp.get("status") in ("REJECTED", "ERROR"):
                    logger.error(
                        "penny_sl_m_broker_rejected ticker=%s attempt=%d "
                        "trigger=%s limit=%s message=%s",
                        ticker, attempt, trigger, limit, resp.get("message", ""),
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
        ltp: Optional[float] = None,
    ) -> Optional[str]:
        """Emergency exit. Best-effort -- logs but does not raise.

        [UNWIND 2026-07-31] This used to send order_type="MARKET", which
        Zerodha refuses over the API ("Market orders without market
        protection are not allowed"). On 2026-07-30 that meant the SIGMA
        unwind was rejected 1 second after the stop was rejected, and the
        caller still reported success. A marketable SELL LIMIT 1% below the
        live bid fills immediately in practice and is API-legal."""
        ref = ltp or await self._live_ltp(ticker)
        if not ref:
            logger.error(
                "penny_unwind_no_reference_price ticker=%s shares=%d "
                "-- cannot price a marketable limit without a quote",
                ticker, shares,
            )
            return None
        limit = snap_to_tick(ref * (1.0 - UNWIND_LIMIT_SLIP_PCT), -1)
        try:
            resp = await self.kite.place_order(
                variety="regular", exchange="NSE",
                tradingsymbol=ticker,
                transaction_type="SELL",
                quantity=shares,
                product=leg.value,
                order_type="LIMIT",
                price=limit,
                validity="DAY",
                tag="QUANT_PENNY_UNWIND",
                # Unwinding an unprotected position is an exit: never gated.
                intent="exit", channel="penny",
            )
            if resp.get("status") in ("REJECTED", "ERROR"):
                logger.error(
                    "penny_unwind_broker_rejected ticker=%s shares=%d limit=%s "
                    "message=%s",
                    ticker, shares, limit, resp.get("message", ""),
                )
                return None
            return resp.get("order_id")
        except Exception as e:
            logger.error("penny_unwind_failed ticker=%s shares=%d error=%s",
                         ticker, shares, str(e))
            return None
