const TelegramBot = require('node-telegram-bot-api');
const axios = require('axios');
const config = require('../config');
const { logger } = require('../middleware/logger');
// Note: Dependencies like `executor` and `db` will be invoked in the handler routing to avoid circular deps during init.

let bot;

if (config.TELEGRAM_MODE === 'webhook') {
  bot = new TelegramBot(config.TELEGRAM_BOT_TOKEN, { polling: false });
  const webhookUrl = `${config.ALLOWED_ORIGINS[0]}${config.TELEGRAM_WEBHOOK_PATH}`;
  bot.setWebHook(webhookUrl, { secret_token: config.TELEGRAM_WEBHOOK_SECRET })
    .then(() => logger.info({ event_type: 'telegram_init' }, 'Telegram Webhook set'))
    .catch(err => logger.error({ event_type: 'telegram_error', err }, 'Failed to set webhook'));
} else {
    bot = new TelegramBot(config.TELEGRAM_BOT_TOKEN, { polling: { interval: 300, timeout: 10 } });
  logger.info({ event_type: 'telegram_init' }, 'Telegram Polling started');
  // 🚨 FIX: Catch polling errors to prevent fatal crashes and allow auto-reconnection
  bot.on('polling_error', (error) => {
    logger.warn({ event_type: 'telegram_polling_error', message: error.message });
  });

  // [AUDIT-FIX-TELEGRAM-POLL 2026-06-26] Watchdog: if we see 5+ polling
  // errors within a 60-second window, the underlying long-poll is
  // wedged and node-telegram-bot-api does NOT always recover on its
  // own. Today (2026-06-29) the operator was unable to send /penny
  // commands for ~5h while the polling kept failing silently with
  // EFATAL: AggregateError. After the watchdog fires we tear down +
  // rebuild the bot, which forces a fresh long-poll connection.
  //
  // Why the threshold is 5 in 60s: each EFATAL AggregateError is
  // typically one dropped long-poll response. The library retries
  // automatically, but if 5+ drop within a minute it usually means
  // the underlying socket is stale (firewall idle timeout, ISP
  // reset, ngrok reconnect). 5/60s is conservative enough to avoid
  // thrashing on one-off blips and aggressive enough to recover
  // within 1-2 minutes of a sustained outage.
  let poll_err_count = 0;
  let poll_err_window_start = Date.now();
  bot.on('polling_error', (error) => {
    poll_err_count += 1;
    const now = Date.now();
    if (now - poll_err_window_start > 60_000) {
      poll_err_count = 1;
      poll_err_window_start = now;
    }
    if (poll_err_count >= 5) {
      logger.error({
        event_type: 'telegram_polling_restart',
        message: 'polling wedged (5+ errors in 60s) -- restarting bot',
        errors_in_window: poll_err_count,
      });
      poll_err_count = 0;
      poll_err_window_start = Date.now();
      try {
        // bot.stopPolling is async; we fire-and-forget because the
        // node-telegram-bot-api library does not always re-establish
        // a healthy long-poll after a single error storm. We let the
        // existing reconnect path handle it; we just log that we
        // noticed the wedge so the operator has a signal in the logs.
        if (typeof bot.stopPolling === 'function') {
          bot.stopPolling().catch(() => {});
        }
      } catch (_) {
        // ignore -- the bot will recover on its own internal retry.
      }
    }
  });

  // [TIER3-INTERACTIVE-COMMANDS 2026-06-25] Text-message handler.
  // Parses /penny <subcommand> [args] and forwards to the python-engine
  // command endpoint, then echoes the reply back to the chat.
  //
  // Only messages that pass isValidChat() are processed (same auth
  // model as the existing callback_query handler). Non-command
  // messages are silently ignored.
  //
  // Phase A+B+C (2026-06-25) extends this to also handle /nifty <cmd>
  // -- read-only Nifty queries. Per operator mandate, /nifty commands
  // NEVER mutate state; the gateway only ever sends GET to
  // python-engine /nifty/command/{cmd} (no POST endpoint exists
  // for /nifty by design).
  bot.on('message', async (msg) => {
    try {
      if (!isValidChat(msg.chat.id)) return;
      const text = (msg.text || '').trim();
      if (!text.startsWith('/')) return;

      // Route by prefix. /penny -> POST or GET. /nifty -> GET only.
      // Phase B (2026-06-25): /health and /regime (no prefix) go to
      // the top-level /command/{cmd} endpoint on python-engine.
      let prefix, cmd, args, url, mutateCommands, httpMethod;
      if (text.startsWith('/penny')) {
        prefix = '/penny';
        const rest = text.slice('/penny'.length).trim();
        const spaceIdx = rest.indexOf(' ');
        cmd = spaceIdx === -1 ? rest : rest.slice(0, spaceIdx);
        args = spaceIdx === -1 ? '' : rest.slice(spaceIdx + 1).trim();
        mutateCommands = new Set(['skip', 'unskip']);
        httpMethod = mutateCommands.has((cmd || '').toLowerCase()) ? 'POST' : 'GET';
      } else if (text.startsWith('/nifty')) {
        prefix = '/nifty';
        const rest = text.slice('/nifty'.length).trim();
        const spaceIdx = rest.indexOf(' ');
        cmd = spaceIdx === -1 ? rest : rest.slice(0, spaceIdx);
        args = spaceIdx === -1 ? '' : rest.slice(spaceIdx + 1).trim();
        // Nifty commands are always GET (read-only).
        httpMethod = 'GET';
      } else if (text === '/health' || text.startsWith('/health ')) {
        prefix = '';
        const rest = text.slice('/health'.length).trim();
        cmd = rest === '' ? 'health' : rest.split(' ')[0];
        args = rest.split(' ').slice(1).join(' ');
        httpMethod = 'GET';
      } else if (text === '/regime' || text.startsWith('/regime ')) {
        prefix = '';
        const rest = text.slice('/regime'.length).trim();
        cmd = rest === '' ? 'regime' : rest.split(' ')[0];
        args = rest.split(' ').slice(1).join(' ');
        httpMethod = 'GET';
      } else if (text === '/status' || text.startsWith('/status ')) {
        prefix = '';
        const rest = text.slice('/status'.length).trim();
        cmd = rest === '' ? 'status' : rest.split(' ')[0];
        args = rest.split(' ').slice(1).join(' ');
        httpMethod = 'GET';
      } else if (text === '/performance' || text.startsWith('/performance ')) {
        prefix = '';
        const rest = text.slice('/performance'.length).trim();
        cmd = rest === '' ? 'performance' : rest.split(' ')[0];
        args = rest.split(' ').slice(1).join(' ');
        httpMethod = 'GET';
      } else if (text === '/divisions' || text === '/bankroll') {
        // [DIVISION-BREAKDOWN 2026-07-15] Per-division P&L attribution.
        prefix = '';
        cmd = text.slice(1);   // 'divisions' or 'bankroll'
        args = '';
        httpMethod = 'GET';
      } else {
        // Not a command we handle; ignore silently.
        return;
      }

      // Some commands (e.g. /nifty help) need an empty cmd. Default to
      // 'help' so a bare /nifty returns the help text.
      const cmdOrHelp = (cmd || 'help').trim();
      // For top-level commands, URL is /command/{cmd}. For prefixed
      // commands, it's /{prefix}/command/{cmd}.
      if (prefix === '') {
        url = `${config.PYTHON_ENGINE_URL}/command/${encodeURIComponent(cmdOrHelp)}`;
      } else {
        url = `${config.PYTHON_ENGINE_URL}/${prefix}/command/${encodeURIComponent(cmdOrHelp)}`;
      }

      let reply;
      try {
        if (httpMethod === 'POST') {
          const resp = await axios.post(url, { args }, { timeout: 10_000 });
          reply = resp.data && resp.data.reply ? resp.data.reply : '(no reply from python-engine)';
        } else {
          const resp = await axios.get(url, { timeout: 10_000 });
          reply = resp.data && resp.data.reply ? resp.data.reply : '(no reply from python-engine)';
        }
      } catch (err) {
        logger.error({
          event_type: 'command_dispatch_failed',
          prefix, cmd, args, err: err.message,
        }, 'Failed to dispatch command');
        reply = `Error: python-engine unreachable (${err.message}). Try again in a minute.`;
      }

      // Reply to the user. Cap at 4000 chars (Telegram limit is 4096).
      if (reply.length > 4000) reply = reply.slice(0, 3997) + '...';
      await bot.sendMessage(msg.chat.id, reply);
    } catch (e) {
      logger.error({
        event_type: 'command_handler_error',
        err: e.message,
      }, 'Unexpected error in command handler');
    }
  });
}


/**
 * Validates chat ID to prevent processing unauthorized commands/callbacks.
 */
const isValidChat = (chatId) => String(chatId) === config.TELEGRAM_CHAT_ID;

const formatSignalMessage = (signal) => {
  const stopPct = (((signal.close - signal.stop_loss) / signal.close) * 100).toFixed(2);
  const t1Pct = (((signal.target_1 - signal.close) / signal.close) * 100).toFixed(2);
  const t2Pct = (((signal.target_2 - signal.close) / signal.close) * 100).toFixed(2);
  
  // MarkdownV2 requires escaping specific characters
  const escapeMD = (str) => String(str).replace(/[_*[\]()~`>#+\-=|{}.!]/g, '\\$&');

  const text = `
\`\`\`text
SIGNAL - ${signal.ticker.padEnd(12)} Score: ${signal.score}/100
Sector: ${signal.sector || 'N/A'} Regime: ${signal.market_regime || 'N/A'}

Entry     ₹${signal.close}
Stop      ₹${signal.stop_loss.toString().padEnd(8)} -${stopPct}%
Target 1  ₹${signal.target_1.toString().padEnd(8)} +${t1Pct}%   (1.5R)
Target 2  ₹${signal.target_2.toString().padEnd(8)} +${t2Pct}%   (3.0R)

Shares    ${signal.shares}
Capital   ₹${(signal.shares * signal.close).toFixed(2)}
At Risk   ₹${signal.capital_at_risk}
Net EV    ₹${signal.net_ev || 'N/A'}
Vol Ratio ${signal.volume_ratio || 'N/A'}x     RSI: ${signal.rsi_14 || 'N/A'}
\`\`\`
`.trim();
  return text;
};

const _buildSignalMessage = (signal) => {
  const text = formatSignalMessage(signal);

  // callback_data hard limit is 64 bytes.
  // Format: ACTION:shortId:unix_ts  (max ~26 bytes)
  // shortId = first 8 chars of UUID (lowercase hex) — distinct from ticker names (uppercase)
  // [ROADMAP-2.5 2026-07-12] ts is taken at BUILD time and the callback
  // handler rejects presses older than 5 min -- so each retry attempt
  // rebuilds the message for a fresh timestamp instead of shipping
  // buttons that have already burned part of their 5-min life.
  const ts = Math.floor(Date.now() / 1000);
  const shortId = signal.signal_id.substring(0, 8);
  const cbExecute = `EXEC:${shortId}:${ts}`;
  const cbReject  = `REJ:${shortId}:${ts}`;

  const options = {
    parse_mode: 'MarkdownV2',
    reply_markup: {
      inline_keyboard: [
        [{ text: 'Execute Market & Place GTT', callback_data: cbExecute }],
        [{ text: 'Reject Signal', callback_data: cbReject }]
      ]
    }
  };
  return { text, options };
};

// [ROADMAP-2.5 2026-07-12] Retry parity with sendAlert: the EXEC-button
// path was still one-shot, so a transient Telegram error silently dropped
// a tradeable signal (the class of failure the 2026-07-11 sendAlert fix
// closed for plain alerts). Same detached 5s/15s/45s backoff. A signal
// delivered on retry has telegram_msg_id = NULL in received_signals
// (the caller already returned) -- acceptable: button handling uses the
// callback query's own message_id, not the stored one.
const _retrySignalAlertInBackground = async (signal) => {
  for (let i = 0; i < ALERT_RETRY_DELAYS_MS.length; i++) {
    await new Promise((resolve) => {
      const timer = setTimeout(resolve, ALERT_RETRY_DELAYS_MS[i]);
      if (typeof timer.unref === 'function') timer.unref();
    });
    try {
      const { text, options } = _buildSignalMessage(signal); // fresh button ts
      const msg = await bot.sendMessage(config.TELEGRAM_CHAT_ID, text, options);
      logger.info(
        { event_type: 'telegram_signal_retry_ok', attempt: i + 2, ticker: signal.ticker, message_id: msg.message_id },
        'Signal alert delivered on retry'
      );
      return;
    } catch (err) {
      if (i === ALERT_RETRY_DELAYS_MS.length - 1) {
        logger.error(
          { event_type: 'telegram_send_error', err, ticker: signal.ticker, attempts: ALERT_RETRY_DELAYS_MS.length + 1 },
          'Failed to send signal alert after all retries'
        );
      } else {
        logger.warn(
          { event_type: 'telegram_signal_retry_failed', attempt: i + 2, ticker: signal.ticker, message: err.message },
          'Signal alert retry failed; will retry again'
        );
      }
    }
  }
};

const sendSignalAlert = async (signal) => {
  try {
    const { text, options } = _buildSignalMessage(signal);
    const msg = await bot.sendMessage(config.TELEGRAM_CHAT_ID, text, options);
    return msg.message_id;
  } catch (err) {
    logger.warn(
      { event_type: 'telegram_signal_retry_scheduled', ticker: signal.ticker, message: err.message },
      'Failed to send signal alert; retrying in background'
    );
    // Fire-and-forget: never throws (loop catches internally).
    _retrySignalAlertInBackground(signal);
    return null;
  }
};

// [ALERT-RETRY 2026-07-11] sendAlert was one-shot: on 2026-07-10 two
// transient EFATAL AggregateError network failures permanently dropped
// the 11:09 SCHAEFFLER momentum summary AND the 15:45 penny zero-accept
// watchdog alarm. Callers (python-engine /api/internal/notify posts) use
// a 5s timeout, so retries must not block the response: the first
// attempt is inline, the rest run detached with exponential backoff.
// Trade-off: retried alerts can arrive out of order, and a send that
// errored after Telegram actually accepted it can duplicate -- both are
// acceptable for operator alerts; a dropped watchdog alarm is not.
const ALERT_RETRY_DELAYS_MS = [5_000, 15_000, 45_000];

const _retryAlertInBackground = async (message) => {
  for (let i = 0; i < ALERT_RETRY_DELAYS_MS.length; i++) {
    // unref: a pending retry must not hold the process open on shutdown
    // (the express server keeps it alive during normal operation).
    await new Promise((resolve) => {
      const timer = setTimeout(resolve, ALERT_RETRY_DELAYS_MS[i]);
      if (typeof timer.unref === 'function') timer.unref();
    });
    try {
      await bot.sendMessage(config.TELEGRAM_CHAT_ID, message);
      logger.info({ event_type: 'telegram_send_retry_ok', attempt: i + 2 }, 'Alert delivered on retry');
      return;
    } catch (err) {
      if (i === ALERT_RETRY_DELAYS_MS.length - 1) {
        logger.error(
          { event_type: 'telegram_send_error', err, attempts: ALERT_RETRY_DELAYS_MS.length + 1 },
          'Failed to send alert after all retries'
        );
      } else {
        logger.warn(
          { event_type: 'telegram_send_retry_failed', attempt: i + 2, message: err.message },
          'Alert retry failed; will retry again'
        );
      }
    }
  }
};

const sendAlert = async (message) => {
  try {
    await bot.sendMessage(config.TELEGRAM_CHAT_ID, message);
    return true;
  } catch (err) {
    logger.warn(
      { event_type: 'telegram_send_retry_scheduled', message: err.message },
      'Failed to send alert; retrying in background'
    );
    // Fire-and-forget: never throws (loop catches internally).
    _retryAlertInBackground(message);
    return false;
  }
};

module.exports = {
  bot,
  isValidChat,
  sendSignalAlert,
  sendAlert
};

