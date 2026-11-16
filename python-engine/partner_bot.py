"""
[PARTNER-TIPS 2026-07-18] Outbound partner Telegram sender (WS4).

[O21-PC 2026-10-21] Cards may carry inline buttons (``reply_markup``) and
``partner_api`` makes the few other Bot API calls the fill capture needs
(getUpdates, answerCallbackQuery, editMessageReplyMarkup, setMessageReaction,
a one-line reply). The same rules hold: partner chat only, plain text, the
token never logged. See partner_fill_capture.py.

A SECOND bot token + a SECOND chat id, wholly separate from the operator
bot that node-gateway owns. Design rules (plan WS4):

  - Direct POST to api.telegram.org (the penny_hourly_report tier-2
    pattern), NEVER through node-gateway's /api/internal/notify: the
    operator relay is hard-wired to the operator chat and a partner tip
    landing there -- or worse, an operator alert landing in the partner
    chat -- is a misroute we make structurally impossible.
  - NO fallback transport. A dropped partner message is an INFO problem;
    a misrouted one is a trust problem. Tier-1 local log is the record.
  - Normal sends use plain text without a parse mode. The give-back stop
    uses an escaped rich heading and falls back to a bold text entity on
    an explicit formatting rejection.
  - Disabled by default (PARTNER_BOT_ENABLED=false or missing creds):
    send_partner() returns False without a single network byte.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Optional

import httpx
import structlog

from config import settings

logger = structlog.get_logger()

TELEGRAM_MAX_LEN = 4096
STOP_STICKER = Path(__file__).with_name("assets") / "partner-stop.webp"
STOP_LEAD_IN_TIMEOUT_SEC = 2.0
STOP_MESSAGE_GAP_SEC = 1.05


@dataclass(frozen=True)
class PartnerSendResult:
    """Outcome of one bounded partner transport attempt.

    ``message_id`` is Telegram's acknowledgement when it is available.  A
    timeout is deliberately reported as ambiguous rather than pretending it
    was not delivered; callers must not promise exactly-once delivery.
    """

    delivered: bool
    message_id: Optional[int] = None
    state: str = "failed"
    error: Optional[str] = None


def provably_unsent(state: Optional[str], error: Optional[str] = None) -> bool:
    """[O24c] Provably not delivered, so safe to send again: no connection was
    made, Telegram's rate limit, or a Telegram 5xx. A timeout after the
    request left may have arrived. [O25M] Shared by the trade watch's outbox
    and the morning login reminder."""
    if state in ("unsent_connect", "rate_limited"):
        return True
    return state == "rejected" and bool(re.fullmatch(r"telegram_http_5\d\d", str(error or "")))


def partner_enabled() -> bool:
    return bool(
        settings.PARTNER_BOT_ENABLED
        and settings.PARTNER_TELEGRAM_BOT_TOKEN
        and settings.PARTNER_TELEGRAM_CHAT_ID
    )


def _masked_chat() -> str:
    cid = str(settings.PARTNER_TELEGRAM_CHAT_ID)
    return f"...{cid[-4:]}" if len(cid) >= 4 else "****"


async def _post_once(client: httpx.AsyncClient, text: str,
                     reply_markup: Optional[dict] = None, *, large_heading: bool = False) -> tuple:
    """Send text, optionally with a rich heading. Returns (result, retry_after_sec_or_None)."""
    body = {
        "chat_id": settings.PARTNER_TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        body["reply_markup"] = reply_markup
    api = f"https://api.telegram.org/bot{settings.PARTNER_TELEGRAM_BOT_TOKEN}"
    if large_heading:
        headline, _, details = text.partition("\n")
        html = f"<h2><b>{escape(headline)}</b></h2>"
        if details:
            html += "<p>" + escape(details).replace("\n", "<br>") + "</p>"
        rich_body = {"chat_id": body["chat_id"], "rich_message": {"html": html}}
        if reply_markup:
            rich_body["reply_markup"] = reply_markup
        resp = await client.post(f"{api}/sendRichMessage", json=rich_body, timeout=10.0)
        if resp.status_code not in (400, 404):
            return _send_outcome(resp)
        # Explicit rejection means the rich message did not reach the chat.
        body["entities"] = [{"type": "bold", "offset": 0, "length": len(headline.encode("utf-16-le")) // 2}]
    resp = await client.post(f"{api}/sendMessage", json=body, timeout=10.0)
    return _send_outcome(resp)


def _send_outcome(resp: httpx.Response) -> tuple:
    if resp.status_code == 429:
        retry_after = None
        try:
            retry_after = int(
                (resp.json().get("parameters") or {}).get("retry_after", 0)
            ) or None
        except Exception:
            pass
        return PartnerSendResult(False, state="rate_limited", error="telegram_429"), retry_after
    try:
        body = resp.json()
    except Exception:
        body = {}
    if resp.status_code == 200 and body.get("ok"):
        result = body.get("result") or {}
        message_id = result.get("message_id")
        return PartnerSendResult(
            True,
            message_id=int(message_id) if isinstance(message_id, int) else None,
            state="acknowledged",
        ), None
    return PartnerSendResult(
        False, state="rejected", error=f"telegram_http_{resp.status_code}",
    ), None


async def _send_stop_lead_in(client: httpx.AsyncClient, headline: str) -> None:
    """Try the two introductory sends once, leaving the full alert to the outbox."""
    try:
        response = await asyncio.wait_for(
            client.post(
                f"https://api.telegram.org/bot{settings.PARTNER_TELEGRAM_BOT_TOKEN}/sendSticker",
                data={"chat_id": str(settings.PARTNER_TELEGRAM_CHAT_ID), "emoji": "🛑"},
                files={"sticker": (STOP_STICKER.name, STOP_STICKER.read_bytes(), "image/webp")},
            ),
            timeout=STOP_LEAD_IN_TIMEOUT_SEC,
        )
        result, _ = _send_outcome(response)
        if not result.delivered:
            logger.warning("partner_stop_sticker_failed state=%s error=%s", result.state, result.error)
    except Exception as exc:
        logger.warning("partner_stop_sticker_failed error=%s", type(exc).__name__)
    await asyncio.sleep(STOP_MESSAGE_GAP_SEC)

    try:
        result, _ = await asyncio.wait_for(
            _post_once(client, headline, large_heading=True), timeout=STOP_LEAD_IN_TIMEOUT_SEC,
        )
        if not result.delivered:
            logger.warning("partner_stop_headline_failed state=%s error=%s", result.state, result.error)
    except Exception as exc:
        logger.warning("partner_stop_headline_failed error=%s", type(exc).__name__)
    await asyncio.sleep(STOP_MESSAGE_GAP_SEC)


async def send_partner_result(text: str, *, kind: str = "partner_msg",
                              reply_markup: Optional[dict] = None, large_heading: bool = False,
                              stop_lead_in: bool = False) -> PartnerSendResult:
    """Deliver one partner message with a bounded, auditable outcome.

    Tier 1: mandatory local log BEFORE any network attempt. Tier 2: one
    direct POST for normal messages, with no retry inside this transport.
    The give-back alert may add its first-attempt sticker and headline.
    A rich heading falls back to bold only after a definite rejection."""
    if not partner_enabled():
        return PartnerSendResult(False, state="disabled", error="partner_transport_disabled")
    if len(text) > TELEGRAM_MAX_LEN:
        # Truncate loudly rather than 400: a clipped brief beats no brief.
        logger.warning(
            "partner_msg_truncated kind=%s len=%d", kind, len(text)
        )
        text = text[: TELEGRAM_MAX_LEN - 20] + "\n[...truncated]"

    logger.info("partner_msg kind=%s body=%s", kind, text)

    async with httpx.AsyncClient() as client:
        if stop_lead_in:
            await _send_stop_lead_in(client, text.partition("\n")[0])
        try:
            if large_heading:
                result, retry_after = await _post_once(client, text, reply_markup, large_heading=True)
            elif reply_markup:
                result, retry_after = await _post_once(client, text, reply_markup)
            else:
                result, retry_after = await _post_once(client, text)
            if retry_after:
                return PartnerSendResult(
                    False, state="rate_limited", error=f"telegram_429_retry_after_{retry_after}",
                )
            return result
        except Exception as exc:
            # A timeout can follow remote acceptance. Do not make another POST
            # from this transport call; the advisory ledger records it as an
            # ambiguity requiring conservative recovery.
            # A transport failure may arrive after Telegram accepted the POST.
            # The API supplies no client idempotency key, so a failure after
            # the connection opened is never evidence that a retry is safe.
            # [O15-M1 2026-10-15] Except a failure to CONNECT (DNS, refused,
            # connect timeout): no request byte left this process, so it is
            # provably unsent and the ledger may retry it within the message's
            # own validity. Oct 15: the 15:10 square-off reminder failed with
            # a DNS ConnectError, went to manual recovery and expired unsent.
            if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
                state = "unsent_connect"
            else:
                state = "ambiguous_timeout" if isinstance(exc, httpx.TimeoutException) else "ambiguous_transport"
            result = PartnerSendResult(False, state=state, error=type(exc).__name__)

    logger.error(
        "partner_send_failed kind=%s chat=%s state=%s err=%s -- message preserved "
        "in the partner_msg log line above", kind, _masked_chat(), result.state, result.error,
    )
    return result


async def send_partner(text: str, *, kind: str = "partner_msg") -> bool:
    """Compatibility wrapper for legacy partner jobs.

    Hedge delivery uses :func:`send_partner_result` so it can persist the
    acknowledgement.  Existing non-hedge callers retain their boolean API.
    """
    return (await send_partner_result(text, kind=kind)).delivered


async def partner_api(method: str, payload: dict, *, timeout: float = 10.0) -> Optional[object]:
    """[O21-PC] One Bot API call on the partner bot; ``result`` or ``None``.

    Used only by partner_fill_capture. Failures are logged by method and
    error class, never with the token or the payload."""
    if not partner_enabled():
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{settings.PARTNER_TELEGRAM_BOT_TOKEN}/{method}",
                json=payload, timeout=timeout,
            )
        body = resp.json()
    except Exception as exc:
        logger.warning("partner_api_failed method=%s err=%s", method, type(exc).__name__)
        return None
    if resp.status_code == 200 and body.get("ok"):
        return body.get("result")
    logger.warning("partner_api_rejected method=%s status=%s desc=%s", method, resp.status_code,
                   str(body.get("description") or "")[:120])
    return None
