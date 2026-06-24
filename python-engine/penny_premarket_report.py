"""
[PENNY-PREMARKET 2026-06-24] Pre-market penny universe digest.

Fires at PENNY_PREMARKET_REPORT_HOUR:PENNY_PREMARKET_REPORT_MIN IST every
weekday. Reads the latest penny_universe JSON file (written by
penny_universe.refresh at PENNY_REFRESH_HOUR), builds a short Telegram-
bound summary, and delivers it via the same 3-tier chain as the hourly
report (local log -> Telegram -> webhook fallback).

The point is to surface BEFORE market opens whether the universe has
feed (or no eligible tickers), so the operator can decide whether to
expect action today -- not after a day of "no entries" silence.

Hard architectural rule (mirrors penny_hourly_report): this module MUST
NOT import from engine, regime, risk_engine, portfolio, evaluate_signal,
or evaluate_momentum_signal. Allowed: penny_models, penny_signal_log,
penny_risk, config, stdlib.

Public API:
  build_premarket_body(universe_path, top_n) -> str
  is_in_premarket_window(now) -> bool
  run_premarket_report(universe_path, top_n, now=None) -> None
"""
import asyncio
import json
import logging
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def is_in_premarket_window(now: datetime) -> bool:
    """
    True iff `now` is at exactly the pre-market minute within the
    configured hour. Example: default 7:50 IST -> fires once per day
    at 07:50 IST. Setting PENNY_PREMARKET_REPORT_HOUR = 0 disables.
    """
    from config import settings
    hour = settings.PENNY_PREMARKET_REPORT_HOUR
    if hour <= 0:
        return False
    return now.hour == hour and now.minute == settings.PENNY_PREMARKET_REPORT_MIN


def build_premarket_body(universe_path: str, top_n: int = 10) -> str:
    """
    Build the pre-market Telegram body. Reads the JSON written by
    penny_universe.refresh; if the file is missing or unparseable,
    returns a "universe not yet refreshed" body instead of raising
    (a missing pre-market digest is not worth crashing the scheduler).

    Body format (kept under ~600 chars to fit Telegram cleanly):

      Penny pre-market (YYYY-MM-DD)
      Universe: N tickers (as_of: YYYY-MM-DD)
      Top by score:
        1. SYM Rs XX.XX (score 0.NN)
        2. ...
      Refresh at 08:00 IST -- if stale, penny_universe_refresh will re-run.

    Args:
        universe_path: path to the penny JSON (default PENNY_UNIVERSE_PATH).
        top_n: how many tickers to list (default settings.PENNY_PREMARKET_TOP_N).
    """
    from config import settings
    today = datetime.now().strftime("%Y-%m-%d")
    if not os.path.exists(universe_path):
        return (
            f"Penny pre-market ({today})\n"
            f"Universe: 0 tickers (file missing at {universe_path})\n"
            f"Refresh job will re-run at {settings.PENNY_REFRESH_HOUR}:00 IST."
        )
    try:
        with open(universe_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("penny_premarket_read_failed path=%s error=%s", universe_path, str(e))
        return (
            f"Penny pre-market ({today})\n"
            f"Universe: unreadable JSON at {universe_path} ({type(e).__name__})."
        )
    tickers = data.get("tickers", []) if isinstance(data, dict) else []
    as_of = data.get("as_of", "unknown") if isinstance(data, dict) else "unknown"
    if not tickers:
        return (
            f"Penny pre-market ({today})\n"
            f"Universe: 0 tickers (as_of: {as_of})\n"
            f"Refresh job will re-run at {settings.PENNY_REFRESH_HOUR}:00 IST."
        )
    n = len(tickers)
    top_n = min(top_n, n)
    lines = [
        f"Penny pre-market ({today})",
        f"Universe: {n} tickers (as_of: {as_of})",
        f"Top by composite score:",
    ]
    for i, t in enumerate(tickers[:top_n], start=1):
        sym = t.get("symbol", "?")
        pc = t.get("prev_close", 0.0) or 0.0
        # Composite score isn't stored in JSON; rank order IS the score
        # proxy (rank_tickers sorts by score desc). We display rank + price
        # so the operator can spot concentration / stale prices at a glance.
        lines.append(f"  {i:>2}. {sym} Rs {pc:.2f}")
    lines.append(f"Refresh at {settings.PENNY_REFRESH_HOUR}:00 IST if stale.")
    return "\n".join(lines)


async def run_premarket_report(
    universe_path: Optional[str] = None,
    top_n: Optional[int] = None,
    now: Optional[datetime] = None,
) -> None:
    """
    Top-level entry point for the scheduler job. Builds the body, logs
    it locally (mandatory heartbeat), then tries Telegram -> webhook
    fallback chain (same shape as PennyHourlyReport.send).
    """
    from config import settings
    if now is None:
        now = datetime.now(timezone.utc).astimezone()
    if not is_in_premarket_window(now):
        return
    if universe_path is None:
        universe_path = str(settings.PENNY_UNIVERSE_JSON_PATH)
    if top_n is None:
        top_n = int(settings.PENNY_PREMARKET_TOP_N)
    body = build_premarket_body(universe_path, top_n)

    # Tier 1: local log (mandatory heartbeat)
    logger.info("penny_premarket_report body=%s", body)

    # Tier 2: Telegram (preferred) -- reuse penny_hourly_report's static
    # helper to keep the transport consistent.
    tg_token = settings.TELEGRAM_BOT_TOKEN
    tg_chat = settings.TELEGRAM_CHAT_ID
    if tg_token and tg_chat:
        try:
            from penny_hourly_report import PennyHourlyReport
            report = PennyHourlyReport(db_path=settings.DB_PATH)
            await report.send(
                body=body,
                webhook_url="",  # skip webhook fallback when Telegram succeeds
                telegram_token=tg_token,
                telegram_chat_id=tg_chat,
            )
            return
        except Exception as e:
            logger.warning(
                "penny_premarket_telegram_failed error=%s -- trying webhook",
                type(e).__name__ + ": " + str(e)[:200],
            )

    # Tier 3: webhook fallback (urllib). The webhook expects JSON {"text": ...}.
    webhook = settings.PENNY_HOURLY_REPORT_WEBHOOK
    if webhook:
        try:
            payload = json.dumps({"text": body, "source": "penny_premarket_report"}).encode("utf-8")
            req = urllib.request.Request(
                webhook, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = await asyncio.to_thread(
                lambda: urllib.request.urlopen(req, timeout=5.0)
            )
            try:
                resp.read()
            finally:
                resp.close()
            if 200 <= resp.status < 300:
                logger.info("penny_premarket_webhook_sent status=%d", resp.status)
                return
            logger.warning(
                "penny_premarket_webhook_non_2xx status=%d -- local log only",
                resp.status,
            )
        except (urllib.error.URLError, urllib.error.HTTPError, Exception) as e:
            logger.error(
                "penny_premarket_webhook_failed error=%s",
                type(e).__name__ + ": " + str(e)[:200],
            )
    else:
        logger.info("penny_premarket_no_transport body delivered via local log only")
