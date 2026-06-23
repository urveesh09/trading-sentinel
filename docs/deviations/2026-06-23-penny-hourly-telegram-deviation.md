# Deviation 2026-06-23: Penny hourly report — Telegram primary, urllib fallback

**Where:** python-engine/penny_hourly_report.py, config.py,
python-engine/.env, tests/test_penny_hourly_report.py.

## What Uru asked for (2026-06-23):

> "no no I want it to send to me on telegram as a message if not keep urllib
> as the backup"

Translation: the hourly report should be sent via **Telegram** as
the primary transport, with the **urllib webhook** as a backup if
Telegram fails.

## The change

`PennyHourlyReport.send()` now uses a 3-tier fallback chain:

  Tier 1 (mandatory): local log via stdlib `logger.info()`
  Tier 2 (preferred): Telegram sendMessage via `urllib.request`
  Tier 3 (backup):   webhook POST via `urllib.request`

If Telegram succeeds, the webhook is NOT called.
If Telegram raises (URLError, HTTPError, network issue, invalid token),
the webhook is attempted. If the webhook also fails, the local log is
the source of truth.

All three tiers log success/failure with `penny_hourly_*` event
names. None raise.

## What the report looks like on Telegram

Telegram receives a message via
`https://api.telegram.org/bot<TOKEN>/sendMessage` with:
  - `chat_id`: numeric user/group ID
  - `text`: the report body (HTML parse mode)
  - `disable_web_page_preview`: true

Example body (penny busy hour):
```
Penny hourly report (10:00 IST)
Regime: PR1_CALM
Entries (1):
  AAA MIS x33 @ 14.74 sl=14.60 t1=15.02
Rejections: 87 (top: outside breakout time window: 84, RSI(14) overbought: 2, ...)
Open: 1/5, deployed: Rs 500, unrealised: Rs +12
```

Example body (no activity):
```
No action in Penny this hour. (regime: PR1_CALM, open: 0/5, deployed: Rs 0)
```

The mandatory heartbeat rule (spec §9.4) holds in all three tiers —
the local log fires regardless.

## Settings added to config.py

```python
TELEGRAM_BOT_TOKEN:  str = ""  # @BotFather token (for hourly report)
TELEGRAM_CHAT_ID:    str = ""  # numeric chat ID (user/group)
```

Read from `python-engine/.env`. If both are set, Telegram is tried.
If either is empty, the report skips Telegram and uses the webhook
(if set) or local log only.

## .env updates

`python-engine/.env` did not previously have Telegram creds (the
Nifty system reads them from `~/trading-sentinel/.env` via the
node-gateway, not from the Python engine). Copied them over:

```
TELEGRAM_BOT_TOKEN=869517...5Yq4
TELEGRAM_CHAT_ID=917185439
```

**Live impact (today):** after merge to Desktop, the next
10:00-14:00 IST hourly cron will POST the report to Telegram.
If Telegram rejects (token invalid, chat_id wrong, rate limit), the
urllib webhook (currently empty) is the backup. If both are empty,
the local log fires. The system is robust by default.

## Tests added

3 new tests in test_penny_hourly_report.py:
  - test_telegram_sent_when_token_and_chat_id_set: Telegram is hit,
    webhook is NOT called.
  - test_telegram_failure_falls_back_to_webhook: Telegram raises,
    webhook is called.
  - test_no_telegram_config_uses_only_webhook: Telegram creds empty,
    only the webhook is called.

All 11 hourly-report tests pass.

## Live-mode impact

- The first report at 10:00 IST today (after merge) will be the
  Telegram send attempt. If it succeeds, you'll see the report in
  your Telegram chat. If it fails, you'll see the failure in the
  python-engine logs and the local log will have the body.
- No risk of "report lost": Tier 1 (local log) is unconditional.
- The Telegram API has its own rate limits (1 message per second per
  chat, 30 messages per second per bot). At 5 reports per day, this
  is well under any limit.
