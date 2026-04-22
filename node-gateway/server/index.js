const http = require('http');
const app = require('./app');
const config = require('./config');
const { logger } = require('./middleware/logger');
const { signalsDb, appDb } = require('./db/index');
const executor = require('./services/executor');
const telegram = require('./services/telegram');
const { isMarketOpen } = require('./utils/market-hours');

const server = http.createServer(app);

// ─────────────────────────────────────────────────────────────────────────────
// TELEGRAM CALLBACK QUERY HANDLER (INLINE KEYBOARD)
// ─────────────────────────────────────────────────────────────────────────────
telegram.bot.on('callback_query', async (query) => {
  try {
    if (!telegram.isValidChat(query.message.chat.id)) return;

    // 1. Parse & Decode
    const rawData = Buffer.from(query.data, 'base64').toString('utf-8');
    const { a: action, id: signal_id, t: ts } = JSON.parse(rawData);

    // 2. Staleness Check (> 60s)
    const nowTs = Math.floor(Date.now() / 1000);
    if (nowTs - ts > 60) {
      await telegram.bot.answerCallbackQuery(query.id, { text: "Signal expired", show_alert: true });
      await telegram.bot.editMessageText(query.message.text + '\n\n- EXPIRED', {
        chat_id: query.message.chat.id,
        message_id: query.message.message_id
      });
      return;
    }

        // 3. Execution Lock / Idempotency Gate
    const isMomentum = action === 'EM';
    const cleanId = isMomentum ? signal_id.replace('_MOM', '') : signal_id;

    const row = signalsDb.prepare(`SELECT status, payload_json FROM received_signals WHERE signal_id = ?`).get(cleanId);
    
    if (!row && !isMomentum) {
      return telegram.bot.answerCallbackQuery(query.id, { text: "Signal not found in DB." });
    }
    
    if (row && row.status !== 'PENDING') {
      await telegram.bot.answerCallbackQuery(query.id, { text: `Already ${row.status}. No action taken.`, show_alert: true });
      return;
    }

    // 4. Market Hours Check (Only for Executions)
    if ((action === 'EXEC' || action === 'EM') && !isMarketOpen()) {
      await telegram.bot.answerCallbackQuery(query.id, { text: "Market closed. Cannot execute now.", show_alert: true });
      return;
    }

    // 5. Reject Action
    if (action === 'R' || action === 'REJ') {
      if (row) signalsDb.prepare(`UPDATE received_signals SET status = 'REJECTED' WHERE signal_id = ?`).run(cleanId);
      await telegram.bot.answerCallbackQuery(query.id, { text: "Signal Rejected" });
      await telegram.bot.editMessageText(query.message.text + '\n\n- REJECTED', {
        chat_id: query.message.chat.id,
        message_id: query.message.message_id
      });
      logger.info({ event_type: 'signal_rejected', signal_id });
      return;
    }

        // 6. Execute Action (Swing)
    if (action === 'EXEC') {
      try {
        const signalData = JSON.parse(row.payload_json);
        signalsDb.prepare(`UPDATE received_signals SET status = 'EXECUTING' WHERE signal_id = ?`).run(cleanId);
        
        await telegram.bot.answerCallbackQuery(query.id, { text: "Executing Swing Trade..." });
        const result = await executor.executeSignal(signalData, 'EXEC', false);
        
        signalsDb.prepare(`UPDATE received_signals SET status = 'EXECUTED' WHERE signal_id = ?`).run(cleanId);
        await telegram.bot.editMessageText(query.message.text + `\n\n✅ EXECUTED: ${result.orderId}`, {
          chat_id: query.message.chat.id,
          message_id: query.message.message_id
        });
      } catch (err) {
        signalsDb.prepare(`UPDATE received_signals SET status = 'PENDING' WHERE signal_id = ?`).run(cleanId);
        logger.error({ event_type: 'execution_failed', err: err.message });
        await telegram.bot.answerCallbackQuery(query.id, { text: `Execution Failed: ${err.message}`, show_alert: true });
      }
      return;
    }

    // 7. Execute Action (Momentum)
    if (action === 'EM') {
      try {
        // Momentum signals might not be in DB yet as they come from Container C directly sometimes
        // But the pipeline now ensures they are handled. 
        // For Momentum, we allow 'row' to be null if we can find it in 'current_momentum_signals' (Engine)
        // But easier is to just use the data sent in the callback if we had it.
        // Since we only have the ID, we must fetch the signal from Container B.
        
        await telegram.bot.answerCallbackQuery(query.id, { text: "Fetching Momentum Data..." });
        
        const ticker = signal_id.replace('_MOM', '');
        const engineUrl = config.PYTHON_ENGINE_URL;
        const resp = await fetch(`${engineUrl}/momentum-signals`, {
           headers: { 'X-Internal-Secret': config.INTERNAL_API_SECRET }
        });
        const data = await resp.json();
        const signalData = data.signals.find(s => s.ticker === ticker);

        if (!signalData) {
          throw new Error("Momentum signal not found in Engine state.");
        }

        await telegram.bot.answerCallbackQuery(query.id, { text: "Executing Momentum Trade..." });
        const result = await executor.executeSignal(signalData, 'EM', true);

        // Update DB (Manually create the signal record if it doesn't exist)
        if (!row) {
          signalsDb.prepare(`
            INSERT INTO received_signals (signal_id, ticker, signal_time, received_at, payload_json, status)
            VALUES (?, ?, ?, ?, ?, 'EXECUTED')
          `).run(cleanId, ticker, new Date().toISOString(), new Date().toISOString(), JSON.stringify(signalData), 'EXECUTED');
        } else {
          signalsDb.prepare(`UPDATE received_signals SET status = 'EXECUTED' WHERE signal_id = ?`).run(cleanId);
        }

        await telegram.bot.editMessageText(query.message.text + `\n\n⚡ EXECUTED (MIS): ${result.orderId}`, {
          chat_id: query.message.chat.id,
          message_id: query.message.message_id
        });

      } catch (err) {
        logger.error({ event_type: 'momentum_execution_failed', err: err.message });
        await telegram.bot.answerCallbackQuery(query.id, { text: `Momentum Failed: ${err.message}`, show_alert: true });
      }
      return;
    }


  } catch (err) {
    logger.error({ event_type: 'telegram_callback_error', err: err.message });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// STARTUP RECOVERY: SYNC-BACK 
// ─────────────────────────────────────────────────────────────────────────────
async function runStartupRecovery() {
  logger.info({ event_type: 'startup_recovery' }, 'Checking for unsynced completed orders...');
  
  const unsynced = signalsDb.prepare(`
    SELECT e.*, r.payload_json 
    FROM executed_orders e
    JOIN received_signals r ON e.signal_id = r.signal_id
    WHERE e.sync_to_b = 0 AND e.status = 'COMPLETE'
  `).all();

  for (const order of unsynced) {
    try {
      const signal = JSON.parse(order.payload_json);
      const syncPayload = {
        ticker: order.ticker,
        exchange: "NSE",
        entry_price: order.entry_price,
        shares: order.shares,
        stop_loss: signal.stop_loss,
        target_1: signal.target_1,
        target_2: signal.target_2,
        order_id: order.order_id,
        gtt_stop_id: order.gtt_stop_id,
        gtt_target_id: order.gtt_target_id,
        notes: order.notes || 'Recovered sync on container start'
      };
      
      await executor.syncToEngine(syncPayload);
      signalsDb.prepare(`UPDATE executed_orders SET sync_to_b = 1 WHERE order_id = ?`).run(order.order_id);
      logger.info({ event_type: 'recovery_sync_success', orderId: order.order_id });
    } catch (err) {
      logger.error({ event_type: 'recovery_sync_failed', orderId: order.order_id, err: err.message });
      // Leaves sync_to_b = 0 to retry again next time.
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// GRACEFUL SHUTDOWN & PROCESS ERROR HANDLERS
// ─────────────────────────────────────────────────────────────────────────────
let isShuttingDown = false;

async function gracefulShutdown(signal) {
  if (isShuttingDown) return;
  isShuttingDown = true;
  logger.info({ event_type: 'shutdown_initiated', signal }, 'Graceful shutdown initiated');

  // 1. Stop accepting HTTP connections
  server.close(() => {
    logger.info({ event_type: 'server_closed' }, 'HTTP server closed');
  });

  // 2. Maximum wait of 10 seconds for in-flight requests
  const timeout = setTimeout(() => {
    logger.error({ event_type: 'shutdown_timeout' }, 'Forcing exit after 10s timeout');
    process.exit(1);
  }, 10000);

  try {
    // 3. Stop Telegram Polling / Webhooks safely
    if (config.TELEGRAM_MODE === 'polling') {
      await telegram.bot.stopPolling();
    } else if (config.TELEGRAM_MODE === 'webhook') {
      await telegram.bot.deleteWebHook();
    }
    telegram.sendAlert("⚠️ Container A Gateway shutting down.");

    // 4. Close SQLite connections cleanly to flush WAL
    signalsDb.close();
    appDb.close();
    
    // 5. Confirm shutdown complete
    logger.info({ event_type: 'shutdown_complete' }, 'Graceful shutdown complete');
    
    // 6. Clear timeout and Exit cleanly
    clearTimeout(timeout);
    process.exit(0);
  } catch (err) {
    logger.error({ event_type: 'shutdown_error', err: err.message });
    process.exit(1);
  }
}

process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
process.on('SIGINT', () => gracefulShutdown('SIGINT'));

process.on('unhandledRejection', (reason) => {
  logger.error({ event_type: 'unhandled_rejection', reason }, 'Unhandled Promise Rejection');
  // Constraint: Do NOT exit on unhandled promise rejections.
});

process.on('uncaughtException', (err) => {
  logger.fatal({ event_type: 'uncaught_exception', err }, 'Uncaught Exception');
  gracefulShutdown('uncaughtException'); // Attempt safe shutdown
});

// ─────────────────────────────────────────────────────────────────────────────
// START SERVER
// ─────────────────────────────────────────────────────────────────────────────
server.listen(config.PORT, async () => {
  logger.info({ event_type: 'server_start', port: config.PORT, env: config.NODE_ENV }, 'Container A Gateway started');
  await runStartupRecovery();
});
