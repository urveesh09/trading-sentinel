const express = require('express');
const router = express.Router();
const { z } = require('zod');
const { requireInternalSecret } = require('../middleware/auth');
const { validate } = require('../middleware/validate');
const telegram = require('../services/telegram');
const { signalsDb } = require('../db');
const logger = require('pino')();

const notifySchema = z.object({
  message: z.string().min(1)
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
// Body: { message: string }
// Forwards message to TELEGRAM_CHAT_ID
router.post('/notify', requireInternalSecret, validate(notifySchema, 'body'), async (req, res, next) => {
  try {
    const { message } = req.body;
    await telegram.sendAlert(`🚨 [SYSTEM ALERT]\n${message}`);
    res.json({ success: true });
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
    const info = signalsDb.prepare(`
      INSERT OR IGNORE INTO approved_snapshots
        (signal_id, ticker, action, payload_json, created_at)
      VALUES (?, ?, ?, ?, ?)
    `).run(signal_id, ticker, action, JSON.stringify(payload), new Date().toISOString());

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

module.exports = router;
