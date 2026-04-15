const TelegramBot = require('node-telegram-bot-api');
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
SIGNAL — ${signal.ticker.padEnd(12)} Score: ${signal.score}/100
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

const sendSignalAlert = async (signal) => {
  const text = formatSignalMessage(signal);
  
  // callback_data strict size limit is 64 bytes. We use short keys.
  const cbExecute = Buffer.from(JSON.stringify({ a: 'EXEC', id: signal.signal_id, t: Math.floor(Date.now()/1000) })).toString('base64');
  const cbReject = Buffer.from(JSON.stringify({ a: 'REJ', id: signal.signal_id, t: Math.floor(Date.now()/1000) })).toString('base64');

  const options = {
    parse_mode: 'MarkdownV2',
    reply_markup: {
      inline_keyboard: [
        [{ text: 'Execute Market & Place GTT', callback_data: cbExecute }],
        [{ text: 'Reject Signal', callback_data: cbReject }]
      ]
    }
  };

  try {
    const msg = await bot.sendMessage(config.TELEGRAM_CHAT_ID, text, options);
    return msg.message_id;
  } catch (err) {
    logger.error({ event_type: 'telegram_send_error', err }, 'Failed to send signal alert');
    return null;
  }
};

const sendAlert = async (message) => {
  try {
    await bot.sendMessage(config.TELEGRAM_CHAT_ID, message);
  } catch (err) {
    logger.error({ event_type: 'telegram_send_error', err }, 'Failed to send alert');
  }
};

module.exports = {
  bot,
  isValidChat,
  sendSignalAlert,
  sendAlert
};

