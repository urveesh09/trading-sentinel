"""
[PARTNER-TIPS 2026-07-18] Outbound-only partner Telegram sender (WS4).

A SECOND bot token + a SECOND chat id, wholly separate from the operator
bot that node-gateway owns. Design rules (plan WS4):

  - Direct POST to api.telegram.org (the penny_hourly_report tier-2
    pattern), NEVER through node-gateway's /api/internal/notify: the
    operator relay is hard-wired to the operator chat and a partner tip
    landing there -- or worse, an operator alert landing in the partner
    chat -- is a misroute we make structurally impossible.
  - NO fallback transport. A dropped partner message is an INFO problem;
    a misrouted one is a trust problem. Tier-1 local log is the record.
  - Plain text, no parse_mode: option tradingsymbols are full of
    characters Markdown parsers choke on, and a formatting 400 must
    never eat a tip.
  - Disabled by default (PARTNER_BOT_ENABLED=false or missing creds):
    send_partner() returns False without a single network byte.
"""
from __future__ import annotations

import asyncio
from typing import Optional

import httpx
import structlog

from config import settings

logger = structlog.get_logger()

# Mirror node-gateway sendAlert's detached backoff (telegram.js
# ALERT_RETRY_DELAYS_MS) -- proven ladder, same total worst-case ~65s.
RETRY_DELAYS_SEC = (5, 15, 45)
TELEGRAM_MAX_LEN = 4096


def partner_enabled() -> bool:
    return bool(
        settings.PARTNER_BOT_ENABLED
        and settings.PARTNER_TELEGRAM_BOT_TOKEN
        and settings.PARTNER_TELEGRAM_CHAT_ID
    )


def _masked_chat() -> str:
    cid = str(settings.PARTNER_TELEGRAM_CHAT_ID)
    return f"...{cid[-4:]}" if len(cid) >= 4 else "****"


async def _post_once(client: httpx.AsyncClient, text: str) -> tuple:
    """One sendMessage attempt. Returns (ok, retry_after_sec_or_None)."""
    resp = await client.post(
        f"https://api.telegram.org/bot{settings.PARTNER_TELEGRAM_BOT_TOKEN}/sendMessage",
        json={
            "chat_id": settings.PARTNER_TELEGRAM_CHAT_ID,
            "text": text,
            "disable_web_page_preview": True,
        },
        timeout=10.0,
    )
    if resp.status_code == 429:
        retry_after = None
        try:
            retry_after = int(
                (resp.json().get("parameters") or {}).get("retry_after", 0)
            ) or None
        except Exception:
            pass
        return False, retry_after
    try:
        body = resp.json()
    except Exception:
        body = {}
    return bool(resp.status_code == 200 and body.get("ok")), None


async def send_partner(text: str, *, kind: str = "partner_msg") -> bool:
    """Deliver one partner message, best-effort. Never raises.

    Tier 1: mandatory local log BEFORE any network attempt -- the log
    line is the source of truth when Telegram is down (penny report §9.4
    discipline). Tier 2: direct send with the retry ladder. Tier 3:
    loud ERROR, return False. No other transport, by design."""
    if not partner_enabled():
        return False
    if len(text) > TELEGRAM_MAX_LEN:
        # Truncate loudly rather than 400: a clipped brief beats no brief.
        logger.warning(
            "partner_msg_truncated kind=%s len=%d", kind, len(text)
        )
        text = text[: TELEGRAM_MAX_LEN - 20] + "\n[...truncated]"

    logger.info("partner_msg kind=%s body=%s", kind, text)

    last_err: Optional[str] = None
    async with httpx.AsyncClient() as client:
        for attempt, delay in enumerate((0,) + RETRY_DELAYS_SEC):
            if delay:
                await asyncio.sleep(delay)
            try:
                ok, retry_after = await _post_once(client, text)
                if ok:
                    if attempt:
                        logger.info(
                            "partner_msg_sent_after_retry kind=%s attempt=%d",
                            kind, attempt + 1,
                        )
                    return True
                last_err = "telegram_not_ok"
                if retry_after:
                    # Telegram told us exactly how long to wait; honor it
                    # in place of (not in addition to) the next rung.
                    await asyncio.sleep(min(retry_after, 60))
            except Exception as exc:
                last_err = str(exc)

    logger.error(
        "partner_send_failed kind=%s chat=%s err=%s -- message preserved "
        "in the partner_msg log line above",
        kind, _masked_chat(), last_err,
    )
    return False
