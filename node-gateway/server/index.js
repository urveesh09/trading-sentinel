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

    // 1. Parse unified callback format: ACTION:signal_id:unix_ts
    // Built by telegram.js (EXEC:8charUUID:ts) and agent.py (EXEC:TICKER:ts / EM:TICKER_MOM:ts)
    const colonIdx1    = query.data.indexOf(':');
    const colonIdxLast = query.data.lastIndexOf(':');
    if (colonIdx1 === -1 || colonIdxLast === colonIdx1) {
      logger.warn({ event_type: 'callback_parse_error', data: query.data.substring(0, 32) });
      return telegram.bot.answerCallbackQuery(query.id, { text: 'Invalid callback format.' });
    }
    const action    = query.data.substring(0, colonIdx1);
    const signal_id = query.data.substring(colonIdx1 + 1, colonIdxLast);
    const ts        = parseInt(query.data.substring(colonIdxLast + 1), 10);

    // 2. Staleness Check (> 5 minutes — allows reasonable human review time)
    const nowTs = Math.floor(Date.now() / 1000);
    if (!isNaN(ts) && nowTs - ts > 300) {
      await telegram.bot.answerCallbackQuery(query.id, { text: 'Signal expired (> 5 min)', show_alert: true });
      await telegram.bot.editMessageText(query.message.text + '\n\n- EXPIRED', {
        chat_id: query.message.chat.id,
        message_id: query.message.message_id
      });
      return;
    }

    // 3. Resolve signal from DB
    // Container A swing signals: shortId is 8 lowercase hex chars (UUID prefix)
    // Container C signals: signal_id is a ticker name (uppercase letters / hyphens) or TICKER_MOM
    const isMomentum        = action === 'EM';
    const cleanId           = isMomentum ? signal_id.replace('_MOM', '') : signal_id;
    const isContainerASignal = /^[0-9a-f]{8}$/.test(signal_id);

    let row = null;
    if (isContainerASignal) {
      row = signalsDb.prepare(
        `SELECT signal_id, status, payload_json FROM received_signals WHERE signal_id LIKE ?`
      ).get(signal_id + '%');
    }

    // 4. For DB-backed signals, enforce PENDING-only execution
    if (row && row.status !== 'PENDING') {
      await telegram.bot.answerCallbackQuery(query.id, { text: `Already ${row.status}. No action taken.`, show_alert: true });
      return;
    }

    // 5. Market Hours Check (Only for Executions)
    if ((action === 'EXEC' || action === 'EM') && !isMarketOpen()) {
      await telegram.bot.answerCallbackQuery(query.id, { text: 'Market closed. Cannot execute now.', show_alert: true });
      return;
    }

    // 6. Reject Action
    if (action === 'REJ') {
      if (row) {
        signalsDb.prepare(`UPDATE received_signals SET status = 'REJECTED' WHERE signal_id = ?`).run(row.signal_id);
      }
      await telegram.bot.answerCallbackQuery(query.id, { text: 'Signal Rejected' });
      await telegram.bot.editMessageText(query.message.text + '\n\n- REJECTED', {
        chat_id: query.message.chat.id,
        message_id: query.message.message_id
      });
      logger.info({ event_type: 'signal_rejected', signal_id });
      return;
    }

    // 7. Execute Action (Swing) — handles both Container A (DB-backed) and Container C (live fetch)
    if (action === 'EXEC') {
      let signalData;
      let fullSignalId = null;

      if (row) {
        // Container A path: signal pre-stored in DB with full UUID
        signalData   = JSON.parse(row.payload_json);
        fullSignalId = row.signal_id; // full UUID from DB row
        signalsDb.prepare(`UPDATE received_signals SET status = 'EXECUTING' WHERE signal_id = ?`).run(fullSignalId);
        await telegram.bot.answerCallbackQuery(query.id, { text: 'Executing Swing Trade...' });
      } else {
        // Container C path: signal not in DB, fetch live from Container B
        await telegram.bot.answerCallbackQuery(query.id, { text: 'Fetching Signal Data...' });
        try {
          const controller = new AbortController();
          const timeout = setTimeout(() => controller.abort(), config.PYTHON_ENGINE_TIMEOUT_MS);
          const resp = await fetch(`${config.PYTHON_ENGINE_URL}/signals`, {
            headers: { 'X-Internal-Secret': config.INTERNAL_API_SECRET },
            signal: controller.signal
          });
          clearTimeout(timeout);
          const data = await resp.json();
          signalData = data.signals?.find(s => s.ticker === signal_id.toUpperCase());
          if (!signalData) {
            // [FIX] callback already answered above; second answerCallbackQuery silently fails.
            // Use sendAlert so the user actually sees this.
            await telegram.sendAlert(`❌ Signal for ${signal_id.toUpperCase()} not found in Engine — it may have expired. No order placed.`);
            return;
          }
        } catch (err) {
          // [FIX] same — callback already answered, use sendAlert instead.
          await telegram.sendAlert(`❌ Failed to fetch signal for ${signal_id.toUpperCase()}: ${err.message}`);
          return;
        }
      }

      try {
        const result = await executor.executeSignal(signalData, 'EXEC', false);
        if (fullSignalId) {
          signalsDb.prepare(`UPDATE received_signals SET status = 'EXECUTED' WHERE signal_id = ?`).run(fullSignalId);
        }
        await telegram.bot.editMessageText(query.message.text + `\n\n✅ EXECUTED: ${result.orderId}`, {
          chat_id: query.message.chat.id,
          message_id: query.message.message_id
        });
      } catch (err) {
        if (fullSignalId) {
          signalsDb.prepare(`UPDATE received_signals SET status = 'PENDING' WHERE signal_id = ?`).run(fullSignalId);
        }
        logger.error({ event_type: 'execution_failed', err: err.message });
        // [FIX] callback was already answered with 'Executing...' — second call silently fails.
        // sendAlert ensures the user sees the failure.
        await telegram.sendAlert(`❌ Swing execution FAILED for ${signalData?.ticker || signal_id}:\n${err.message}\n\nSignal reset to PENDING.`);
      }
      return;
    }

    // 8. Execute Action (Momentum) — with atomic idempotency lock
    if (action === 'EM') {
      const today         = new Date().toISOString().split('T')[0]; // YYYY-MM-DD
      const momentumLockId = `${cleanId}_MOM_${today}`;

      // Atomic lock:
      //   - First press: INSERT with EXECUTING status.
      //   - Retry after failure (PENDING): UPDATE to EXECUTING — allow the user to retry.
      //   - In-flight (EXECUTING) or done (EXECUTED): block — no double orders.
      const lockTx = signalsDb.transaction(() => {
        const existing = signalsDb.prepare(
          `SELECT status FROM received_signals WHERE signal_id = ?`
        ).get(momentumLockId);

        if (!existing) {
          signalsDb.prepare(`
            INSERT INTO received_signals (signal_id, ticker, signal_time, received_at, payload_json, status)
            VALUES (?, ?, ?, ?, '{}', 'EXECUTING')
          `).run(momentumLockId, cleanId, new Date().toISOString(), new Date().toISOString());
          return { locked: false };
        }

        if (existing.status === 'PENDING') {
          // [FIX] A previous attempt failed and was reset to PENDING.
          // Allow the user to retry by flipping back to EXECUTING.
          signalsDb.prepare(`UPDATE received_signals SET status = 'EXECUTING' WHERE signal_id = ?`)
            .run(momentumLockId);
          return { locked: false };
        }

        // EXECUTING (in-flight) or EXECUTED (already done) — block duplicate
        return { locked: true, status: existing.status };
      });

      const lockResult = lockTx();
      if (lockResult.locked) {
        await telegram.bot.answerCallbackQuery(query.id, { text: `Already ${lockResult.status}. No double orders.`, show_alert: true });
        return;
      }

      try {
        await telegram.bot.answerCallbackQuery(query.id, { text: 'Fetching Momentum Data...' });

        const controller = new AbortController();
        const timeout    = setTimeout(() => controller.abort(), config.PYTHON_ENGINE_TIMEOUT_MS);
        const resp       = await fetch(`${config.PYTHON_ENGINE_URL}/momentum-signals`, {
          headers: { 'X-Internal-Secret': config.INTERNAL_API_SECRET },
          signal: controller.signal
        });
        clearTimeout(timeout);
        const data       = await resp.json();
        const signalData = data.signals?.find(s => s.ticker === cleanId);

        if (!signalData) {
          signalsDb.prepare(`UPDATE received_signals SET status = 'PENDING' WHERE signal_id = ?`).run(momentumLockId);
          throw new Error('Momentum signal not found in Engine state.');
        }

        // [FIX] MomentumSignal model has no signal_id field; without this the executor's
        // INSERT into executed_orders gets NULL for signal_id and fails the NOT NULL
        // constraint, which was being mislabelled as "Order tracking collision detected."
        signalData.signal_id = momentumLockId;

        const result = await executor.executeSignal(signalData, 'EM', true);

        // Persist full payload now that we have it, mark EXECUTED
        signalsDb.prepare(`
          UPDATE received_signals SET status = 'EXECUTED', payload_json = ? WHERE signal_id = ?
        `).run(JSON.stringify(signalData), momentumLockId);

        await telegram.bot.editMessageText(query.message.text + `\n\n⚡ EXECUTED (MIS): ${result.orderId}`, {
          chat_id: query.message.chat.id,
          message_id: query.message.message_id
        });
      } catch (err) {
        // Release lock so user can retry
        signalsDb.prepare(`UPDATE received_signals SET status = 'PENDING' WHERE signal_id = ?`).run(momentumLockId);
        logger.error({ event_type: 'momentum_execution_failed', err: err.message });
        // [FIX] callback was already answered with 'Fetching Momentum Data...' — second call silently fails.
        // sendAlert ensures the user sees the failure and knows to retry.
        await telegram.sendAlert(`❌ Momentum buy FAILED for ${cleanId}:\n${err.message}\n\nSignal reset to PENDING — retry the button.`);
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

  // [HIGH-005] Reset signals stuck in EXECUTING state (process crash mid-execution)
  const stuckResult = signalsDb.prepare(
    `UPDATE received_signals SET status = 'PENDING' WHERE status = 'EXECUTING'`
  ).run();
  if (stuckResult.changes > 0) {
    logger.warn({ event_type: 'stuck_signal_recovery', count: stuckResult.changes },
      `Reset ${stuckResult.changes} stuck EXECUTING signal(s) to PENDING`);
  }
  
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
