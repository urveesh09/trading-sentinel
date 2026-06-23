"""
[PENNY-HOURLY 2026-06-21] Per-hour penny subsystem status report (spec §9.4).

Fires at PENNY_HOURLY_REPORT_START_HOUR through PENNY_HOURLY_REPORT_END_HOUR
IST (default 10:00 - 14:00, five reports per trading day).

Mandatory heartbeat rule: the report fires EVERY hour within the window
regardless of activity. A missing report is itself an alert.

Delivery:
  - Always logged at INFO level (key: penny_hourly_report)
  - Optional webhook POST when PENNY_HOURLY_REPORT_WEBHOOK is configured
  - Webhook failures are logged but never raised

Hard architectural rule (enforced by tests/test_penny_isolation.py):
  this module MUST NOT import from engine, regime, risk_engine, portfolio,
  evaluate_signal, or evaluate_momentum_signal.
  Allowed: penny_models, penny_signal_log, penny_risk, config, stdlib.
  (Uses stdlib urllib for webhook delivery -- the codebase does not
  have the 'requests' package; httpx is also available but stdlib is
  the minimum-dependency choice for a non-critical heartbeat.)
"""
import asyncio
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def is_in_report_window(now: datetime) -> bool:
    """
    True iff now is at the top of an hour within the report window.

    Window: [PENNY_HOURLY_REPORT_START_HOUR, PENNY_HOURLY_REPORT_END_HOUR]
    inclusive at both ends, but the report only fires at minute=0 (the
    top of each hour). This matches the spec §9.4 contract of "every
    :00 IST from 10:00 through 14:00" — 14:00 is in, 14:01 is out.
    """
    from config import settings
    if now.minute != 0:
        return False
    return (settings.PENNY_HOURLY_REPORT_START_HOUR
            <= now.hour
            <= settings.PENNY_HOURLY_REPORT_END_HOUR)


class PennyHourlyReport:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def build_report(
        self,
        now: datetime,
        regime: str,
        open_positions: list,
        deployed_capital: float,
        unrealised_pnl: float,
        kill_switch_active: bool,
        circuit_blocks: int,
    ) -> str:
        """
        Build the report body (markdown, <= 15 lines, < 1000 chars).
        """
        from penny_signal_log import init_penny_signal_db
        await init_penny_signal_db(self.db_path)
        import aiosqlite

        # Normalize now to a UTC ISO string so it matches the format
        # used by penny_signal_log.log_penny_signal (which calls
        # datetime.now(timezone.utc).isoformat() -- always has +00:00
        # suffix). A naive `now` would produce a string without the
        # suffix and break the lex comparison (a tz-aware row string
        # sorts BEFORE a naive boundary string of the same wall-clock
        # time because '+' < '0' in ASCII).
        if now.tzinfo is None:
            now_utc = now.replace(tzinfo=timezone.utc)
        else:
            now_utc = now.astimezone(timezone.utc)
        hour_start = (now_utc - timedelta(hours=1)).isoformat()
        query_now = now_utc.isoformat()
        entries = []
        rejections_count = 0
        reject_reasons = {}

        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT ticker, leg, close, stop_loss, target_1, shares, "
                    "  scanned_at, reject_reason "
                    "FROM penny_signals "
                    "WHERE scanned_at >= ? AND scanned_at <= ?",
                    (hour_start, query_now),
                ) as cur:
                    rows = await cur.fetchall()
            for row in rows:
                ticker, leg, close, sl, t1, shares, scanned_at, reject_reason = row
                if reject_reason:
                    rejections_count += 1
                    reject_reasons[reject_reason] = reject_reasons.get(reject_reason, 0) + 1
                else:
                    entries.append({
                        "ticker": ticker, "leg": leg, "close": close,
                        "stop_loss": sl, "target_1": t1, "shares": shares,
                    })
        except Exception as e:
            logger.error("penny_hourly_query_failed error=%s", str(e))

        has_activity = bool(entries) or kill_switch_active or circuit_blocks > 0

        if not has_activity:
            suffix = f" (regime: {regime}, open: {len(open_positions)}/5, deployed: Rs {deployed_capital:.0f})"
            return f"No action in Penny this hour.{suffix}"

        lines = [f"Penny hourly report ({now.strftime('%H:%M IST')})", f"Regime: {regime}"]

        if entries:
            lines.append(f"Entries ({len(entries)}):")
            for e in entries[:5]:
                lines.append(
                    f"  {e['ticker']} {e['leg']} x{e['shares']} @ {e['close']:.2f} "
                    f"sl={e['stop_loss']:.2f} t1={e['target_1']:.2f}"
                )

        if rejections_count:
            top = sorted(reject_reasons.items(), key=lambda x: -x[1])[:3]
            reasons_str = ", ".join(f"{r}: {c}" for r, c in top)
            lines.append(f"Rejections: {rejections_count} (top: {reasons_str})")

        if kill_switch_active:
            lines.append("KILL-SWITCH ACTIVE - no new entries today")

        if circuit_blocks:
            lines.append(f"Circuit blocks: {circuit_blocks}")

        lines.append(
            f"Open: {len(open_positions)}/5, deployed: Rs {deployed_capital:.0f}, "
            f"unrealised: Rs {unrealised_pnl:+.0f}"
        )
        return "\n".join(lines)

    @staticmethod
    def _post_json(url: str, payload_bytes: bytes, timeout: float = 5.0):
        """
        Synchronous POST with JSON body. Returns the response object
        (caller is responsible for closing it via context manager or
        .close()) or raises urllib errors.

        Wrapped in a static method so the async send() can run it via
        asyncio.to_thread() without blocking the event loop.
        """
        req = urllib.request.Request(
            url, data=payload_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return urllib.request.urlopen(req, timeout=timeout)

    async def send(
        self,
        body: str,
        webhook_url: str,
        telegram_token: str = "",
        telegram_chat_id: str = "",
    ) -> None:
        """Deliver the report via a 3-tier fallback chain.

        Order (per Uru 2026-06-23):
          1. Always log locally (penny_hourly_report body=...).
          2. Try Telegram (if telegram_token + telegram_chat_id are both set).
             Validate Telegram's JSON response ({"ok": true} on success).
          3. Fall back to the urllib webhook (if webhook_url is set).
          4. If both fail, the local log is the source of truth.

        All transports are best-effort: failures are logged but never
        raised. The local log line is the mandatory heartbeat (spec §9.4).

        Network calls are dispatched via asyncio.to_thread() so the
        event loop is not blocked by synchronous HTTP.

        URLs are NEVER logged (they may contain embedded credentials
        for Slack/Discord webhooks or Telegram bot tokens).
        """
        # Tier 1: local log (mandatory heartbeat)
        logger.info("penny_hourly_report body=%s", body)

        # Tier 2: Telegram (preferred). Validate {ok: bool} in response.
        if telegram_token and telegram_chat_id:
            try:
                url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
                payload = json.dumps({
                    "chat_id": telegram_chat_id,
                    "text": body,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                }).encode("utf-8")
                resp = await asyncio.to_thread(
                    self._post_json, url, payload, 5.0,
                )
                try:
                    body_bytes = resp.read()
                finally:
                    resp.close()
                tg_resp = json.loads(body_bytes.decode("utf-8", errors="replace"))
                if tg_resp.get("ok") is True:
                    logger.info(
                        "penny_hourly_telegram_sent chat_id=%s",
                        telegram_chat_id,
                    )
                    return  # Telegram succeeded; skip webhook fallback
                # 200 with ok=false: treat as failure, fall back.
                logger.warning(
                    "penny_hourly_telegram_rejected description=%s -- falling back to webhook",
                    tg_resp.get("description", "ok=false"),
                )
            except (urllib.error.URLError, urllib.error.HTTPError, Exception) as e:
                logger.warning(
                    "penny_hourly_telegram_failed error=%s -- falling back to webhook",
                    type(e).__name__ + ": " + str(e)[:200],
                )

        # Tier 3: webhook (urllib fallback). Accept any 2xx as success.
        if webhook_url:
            try:
                payload = json.dumps({"text": body, "source": "penny_hourly_report"}).encode("utf-8")
                resp = await asyncio.to_thread(
                    self._post_json, webhook_url, payload, 5.0,
                )
                try:
                    # Drain to allow connection reuse, then check status.
                    resp.read()
                finally:
                    resp.close()
                # 2xx is success, anything else is failure.
                if 200 <= resp.status < 300:
                    logger.info("penny_hourly_webhook_sent status=%d", resp.status)
                else:
                    logger.warning(
                        "penny_hourly_webhook_non_2xx status=%d -- body delivered via local log only",
                        resp.status,
                    )
            except (urllib.error.URLError, urllib.error.HTTPError, Exception) as e:
                logger.error(
                    "penny_hourly_webhook_failed error=%s",
                    type(e).__name__ + ": " + str(e)[:200],
                )
        else:
            logger.info(
                "penny_hourly_no_transport body delivered via local log only"
            )


async def run_hourly_report(db_path: str, regime: str, open_positions: list,
                             deployed_capital: float, unrealised_pnl: float,
                             kill_switch_active: bool, circuit_blocks: int,
                             now: Optional[datetime] = None) -> None:
    """Top-level entry point for the scheduler job."""
    from config import settings
    if now is None:
        now = datetime.now(timezone.utc).astimezone()
    if not is_in_report_window(now):
        return
    rpt = PennyHourlyReport(db_path=db_path)
    body = await rpt.build_report(
        now=now, regime=regime,
        open_positions=open_positions, deployed_capital=deployed_capital,
        unrealised_pnl=unrealised_pnl,
        kill_switch_active=kill_switch_active, circuit_blocks=circuit_blocks,
    )
    await rpt.send(
        body=body,
        webhook_url=settings.PENNY_HOURLY_REPORT_WEBHOOK,
        telegram_token=settings.TELEGRAM_BOT_TOKEN,
        telegram_chat_id=settings.TELEGRAM_CHAT_ID,
    )
