const http = require('http');
const app = require('./app');
const config = require('./config');
const { logger } = require('./middleware/logger');
const { signalsDb, appDb } = require('./db/index');
const executor = require('./services/executor');
const telegram = require('./services/telegram');
const { isMarketOpen, currentSessionPhase } = require('./utils/market-hours');
const { entrySessionVerdict } = require('./services/cas-eligibility');
const { getApprovedSnapshot } = require('./services/approved-snapshots');
const { executeMomentum } = require('./services/momentum-execution');

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
      // [WORKFLOW-J.6] Phase-aware user message. The hard guard
      // above remains the contract; the message tells the operator
      // / telegram callback which phase rejected the action
      // (suspicious: CAS_MATCHING; expected: CLOSED).
      const phase = currentSessionPhase();
      const phaseLabel = phase === 'CLOSED'
        ? 'Market closed'
        : `Market in ${phase}`;
      await telegram.bot.answerCallbackQuery(query.id, {
        text: `${phaseLabel}. Cannot execute now.`,
        show_alert: true,
      });
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

    // 7. Execute Action (Swing) — handles both Container A (DB-backed) and Container C
    if (action === 'EXEC') {
      let signalData;
      let fullSignalId = null;

      // [HIGH-007 / ROADMAP-4.5 2026-07-13] Prefer the APPROVED SNAPSHOT.
      // The agent registers the exact payload it displayed, under the same id
      // it put in callback_data. Executing that row means the price, shares
      // and stop that get sent to Zerodha are the ones the operator actually
      // approved -- previously we re-fetched /signals, which serves
      // `current_signals`, a list run_screener REPLACES wholesale on every
      // run. See db/schema.sql.
      const snapshot = getApprovedSnapshot(signal_id, 'EXEC');

      // Agent-originated Swing ids are ticker-based rather than UUID prefixes.
      // Registration now creates the same durable received_signals lock, so
      // resolve it here before choosing the snapshot path.
      if (!row && snapshot) {
        row = signalsDb.prepare(
          `SELECT signal_id, status, payload_json FROM received_signals WHERE signal_id = ?`
        ).get(signal_id);
        if (!row) {
          await telegram.sendAlert(`❌ ${signal_id}: approved snapshot has no durable execution record. No broker order placed.`);
          return;
        }
        if (row.status !== 'PENDING') {
          await telegram.bot.answerCallbackQuery(query.id, { text: `Already ${row.status}. No action taken.`, show_alert: true });
          return;
        }
      }

      if (row) {
        // Container A path: signal pre-stored in DB with full UUID
        signalData   = JSON.parse(row.payload_json);
        fullSignalId = row.signal_id; // full UUID from DB row
      } else if (snapshot) {
        signalData = snapshot;
      } else {
        // Never execute a live re-fetch that has no durable execution record.
        // A broker fill followed by a tracking INSERT failure is worse than a
        // missed signal, and the operator did not approve newly fetched values.
        logger.error({ event_type: 'approved_snapshot_missing_execution_blocked', signal_id, action });
        await telegram.bot.answerCallbackQuery(query.id, { text: 'Signal registration missing. Execution blocked.', show_alert: true });
        await telegram.sendAlert(`❌ ${signal_id}: approved snapshot/registration missing. No broker order placed.`);
        return;
      }

      const sessionVerdict = await entrySessionVerdict(signalData.ticker, new Date());
      if (!sessionVerdict.allowed) {
        await telegram.bot.answerCallbackQuery(query.id, {
          text: sessionVerdict.reason ||
            `Market in ${sessionVerdict.phase}. Cannot execute now.`,
          show_alert: true,
        });
        return;
      }

      if (fullSignalId) {
        signalsDb.prepare(`UPDATE received_signals SET status = 'EXECUTING', execution_state = 'SUBMITTING' WHERE signal_id = ?`).run(fullSignalId);
      }
      await telegram.bot.answerCallbackQuery(query.id, { text: 'Executing Swing Trade...' });

      try {
        const result = await executor.executeSignal(signalData, 'EXEC', false);
        if (fullSignalId) {
          signalsDb.prepare(`UPDATE received_signals SET status = 'EXECUTED', execution_state = 'FILLED' WHERE signal_id = ?`).run(fullSignalId);
        }
        await telegram.bot.editMessageText(query.message.text + `\n\n✅ EXECUTED: ${result.orderId}`, {
          chat_id: query.message.chat.id,
          message_id: query.message.message_id
        });
      } catch (err) {
        if (fullSignalId && (err.positionHeld || err.outcomeUnknown)) {
          signalsDb.prepare(`UPDATE received_signals SET status = 'EXECUTING', execution_state = 'OUTCOME_UNKNOWN' WHERE signal_id = ?`).run(fullSignalId);
        } else if (fullSignalId) {
          signalsDb.prepare(`UPDATE received_signals SET status = 'PENDING', execution_state = 'IDLE' WHERE signal_id = ?`).run(fullSignalId);
        }
        logger.error({ event_type: 'execution_failed', err: err.message });
        // [FIX] callback was already answered with 'Executing...' — second call silently fails.
        // sendAlert ensures the user sees the failure.
        const retryText = (err.positionHeld || err.outcomeUnknown)
          ? 'Outcome locked for broker reconciliation. Do NOT retry.'
          : 'Signal reset to PENDING.';
        await telegram.sendAlert(`❌ Swing execution FAILED for ${signalData?.ticker || signal_id}:\n${err.message}\n\n${retryText}`);
      }
      return;
    }

    // 8. Execute Action (Momentum) -- shared with the automatic route
    // (services/momentum-execution.js): same lock, snapshot and executor.
    if (action === 'EM') {
      const sessionVerdict = await entrySessionVerdict(cleanId, new Date());
      if (!sessionVerdict.allowed) {
        await telegram.bot.answerCallbackQuery(query.id, {
          text: sessionVerdict.reason ||
            `Market in ${sessionVerdict.phase}. Cannot execute now.`,
          show_alert: true,
        });
        return;
      }
      const outcome = await executeMomentum({
        signalId: signal_id, cleanId, allowLiveFetch: true,
        onStart: (fromSnapshot) => telegram.bot.answerCallbackQuery(query.id, {
          text: fromSnapshot ? 'Executing Momentum Trade...' : 'Fetching Momentum Data...',
        }),
      });
      if (outcome.outcome === 'LOCKED') {
        await telegram.bot.answerCallbackQuery(query.id, { text: `Already ${outcome.status}. No double orders.`, show_alert: true });
      } else if (outcome.outcome === 'EXECUTED') {
        await telegram.bot.editMessageText(query.message.text + `

⚡ EXECUTED (MIS): ${outcome.result.orderId}`, {
          chat_id: query.message.chat.id,
          message_id: query.message.message_id
        });
      } else if (outcome.held) {
        await telegram.sendAlert(`❌ Momentum buy FAILED for ${cleanId}:
${outcome.error.message}

Outcome locked for broker reconciliation. Do NOT retry.`);
      } else {
        // The callback was already answered; sendAlert makes the failure visible.
        await telegram.sendAlert(`❌ Momentum buy FAILED for ${cleanId}:
${outcome.error.message}

Signal reset to PENDING — retry the button.`);
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

  // A crash can happen after Kite accepted the order but before we persisted
  // its id. Never make an EXECUTING record retryable merely because Node
  // restarted; that is exactly when broker reconciliation is required.
  const stuckResult = signalsDb.prepare(
    `UPDATE received_signals SET execution_state = 'OUTCOME_UNKNOWN' WHERE status = 'EXECUTING' AND execution_state != 'HELD_UNPROTECTED'`
  ).run();
  if (stuckResult.changes > 0) {
    logger.warn({ event_type: 'stuck_signal_recovery', count: stuckResult.changes },
      `Locked ${stuckResult.changes} interrupted EXECUTING signal(s) for broker reconciliation`);
  }
  
  const unsynced = signalsDb.prepare(`
    SELECT e.*, r.payload_json 
    FROM executed_orders e
    JOIN received_signals r ON e.signal_id = r.signal_id
    WHERE e.sync_to_b IN (0, 2) AND e.status = 'COMPLETE'
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
      // Preserve pending/failed state so the next restart retries it again.
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

  // [ROADMAP-2.1 2026-07-12] Re-arm execution from python-engine's
  // persisted same-day token so a mid-day restart no longer kills the
  // EXEC buttons until manual re-login. No-op before the daily login.
  const { restoreTokenFromEngine } = require('./services/token-restore');
  const restored = await restoreTokenFromEngine();
  if (restored) {
    telegram.sendAlert('♻️ node-gateway restarted mid-day; Kite execution re-armed automatically (no re-login needed).');
  }
});

module.exports = { runStartupRecovery };
