const express = require('express');
const router = express.Router();
const { z } = require('zod');
const { requireInternalSecret } = require('../middleware/auth');
const { validate } = require('../middleware/validate');
const telegram = require('../services/telegram');
const { signalsDb } = require('../db');
const logger = require('pino')();
// [WORKFLOW-J.9 2026-09-13] Phase stamping helper. Mirrors
// the J.6 sessionPhase mirror; result is one of the 10
// documented bounded phases.
const { stampSessionPhaseForSignal } = require('../utils/market-hours');
const config = require('../config');
const { entrySessionVerdict } = require('../services/cas-eligibility');
const { executeMomentum } = require('../services/momentum-execution');

const notifySchema = z.object({
  message: z.string().min(1),
  require_delivery: z.boolean().optional()
});

// [HIGH-007 / ROADMAP-4.5 2026-07-13]
// The sender registers the exact payload it is about to show the operator,
// under the same id it puts in callback_data. See db/schema.sql.
const registerSignalSchema = z.object({
  signal_id: z.string().min(1).max(40),
  ticker: z.string().min(1),
  action: z.enum(['EXEC', 'EM']),
  payload: z.record(z.any())
});

// POST /api/internal/notify
// Auth: X-Internal-Secret header
// Body: { message: string, require_delivery?: boolean }
// Forwards message to TELEGRAM_CHAT_ID.
//
// Default: one send plus the gateway's own background retry/dead-letter;
// always 200 (delivered says whether the first attempt succeeded).
// require_delivery: one attempt and no gateway retry, so the caller's durable
// outbox owns the retry. 422 when Telegram rejected THIS message (HTTP 400:
// it will never be accepted as is); 502 for any other failure (network,
// 429, 5xx), which later messages would also hit.
router.post('/notify', requireInternalSecret, validate(notifySchema, 'body'), async (req, res, next) => {
  try {
    const { message, require_delivery: requireDelivery } = req.body;
    const text = `🚨 [SYSTEM ALERT]\n${message}`;
    if (requireDelivery) {
      const result = await telegram.sendAlertOnceDetailed(text);
      if (result.delivered) return res.status(200).json({ success: true, delivered: true });
      return res.status(result.rejected ? 422 : 502).json({
        success: false, delivered: false, rejected: Boolean(result.rejected), telegram_status: result.status ?? null,
      });
    }
    const delivered = await telegram.sendAlert(text);
    res.json({ success: true, delivered });
  } catch (err) {
    next(err);
  }
});

// POST /api/internal/register-signal
// Auth: X-Internal-Secret header
// Body: { signal_id, ticker, action: 'EXEC'|'EM', payload: {...} }
//
// Records the approved snapshot so the EXEC/EM handler executes the numbers
// the operator SAW, instead of re-fetching live data at press time.
//
// INSERT OR IGNORE, deliberately: the snapshot is immutable once written.
// If the same ticker is re-alerted later in the day, the first (approved)
// payload must win -- silently rewriting it here would reintroduce exactly
// the bug this table exists to close. Returns {registered:false} in that
// case rather than pretending to have stored the new one.
router.post('/register-signal', requireInternalSecret, validate(registerSignalSchema, 'body'), async (req, res, next) => {
  try {
    const { signal_id, ticker, action, payload } = req.body;
    const now = new Date().toISOString();
    const trackedPayload = { ...payload, signal_id };
    const tx = signalsDb.transaction(() => {
      const info = signalsDb.prepare(`
        INSERT OR IGNORE INTO approved_snapshots
          (signal_id, ticker, action, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?)
      `).run(signal_id, ticker, action, JSON.stringify(trackedPayload), now);
      if (action === 'EXEC') {
        // [WORKFLOW-J.9 2026-09-13] Stamp the bounded session
        // phase at insertion time. The Python engine callback
        // arrives when the operator presses EXEC on Telegram;
        // the phase recorded here is the LIVE phase at the
        // moment of callback arrival.
        const sessionPhase = stampSessionPhaseForSignal(ticker);
        signalsDb.prepare(`
          INSERT OR IGNORE INTO received_signals
            (signal_id, ticker, signal_time, received_at, payload_json, status, execution_state, session_phase)
          VALUES (?, ?, ?, ?, ?, 'PENDING', 'IDLE', ?)
        `).run(signal_id, ticker, payload.signal_time || now, now, JSON.stringify(trackedPayload), sessionPhase);
      }
      return info;
    });
    const info = tx();

    const registered = info.changes > 0;
    logger.info({
      event_type: registered ? 'snapshot_registered' : 'snapshot_already_exists',
      signal_id, ticker, action
    });
    res.json({ success: true, registered });
  } catch (err) {
    next(err);
  }
});

// [MOMENTUM-AUTO 2026-10-04] POST /api/internal/momentum-auto-execute
// Auth: X-Internal-Secret header. Body: { signal_id: 'TICKER_MOM' }
//
// Executes a registered Momentum snapshot without a Telegram tap when
// MOMENTUM_AUTO_EXECUTE is on. Same path as the EM button
// (services/momentum-execution.js); never re-fetches live engine data.
// Always 200 with an explicit outcome so the caller can word its alert.
const autoExecuteSchema = z.object({
  signal_id: z.string().min(1).max(40).regex(/_MOM$/)
});

router.post('/momentum-auto-execute', requireInternalSecret, validate(autoExecuteSchema, 'body'), async (req, res, next) => {
  try {
    const { signal_id } = req.body;
    if (!config.MOMENTUM_AUTO_EXECUTE) {
      return res.json({ executed: false, outcome: 'DISABLED', reason: 'auto_execute_disabled' });
    }
    const cleanId = signal_id.replace(/_MOM$/, '');
    const verdict = await entrySessionVerdict(cleanId, new Date());
    if (!verdict.allowed) {
      return res.json({ executed: false, outcome: 'SESSION_BLOCKED',
                        reason: verdict.reason || `market_${verdict.phase}` });
    }
    const result = await executeMomentum({ signalId: signal_id, cleanId, allowLiveFetch: false });
    logger.info({ event_type: 'momentum_auto_execute', signal_id, outcome: result.outcome, held: !!result.held });
    if (result.outcome === 'EXECUTED') {
      return res.json({ executed: true, outcome: 'EXECUTED', order_id: result.result.orderId,
                        fill_price: result.result.fillPrice, shares: result.result.shares,
                        stop_loss: result.result.stop_loss });
    }
    if (result.outcome === 'LOCKED') {
      return res.json({ executed: false, outcome: 'LOCKED', reason: `already_${String(result.status).toLowerCase()}` });
    }
    if (result.held) {
      // Independent of the caller: an unprotected or unknown position pages now.
      await telegram.sendAlert(`❌ Momentum AUTO buy FAILED for ${cleanId}:
${result.error.message}

Outcome locked for broker reconciliation. Do NOT retry.`);
    }
    return res.json({ executed: false, outcome: 'FAILED', held: !!result.held, reason: result.error.message });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
