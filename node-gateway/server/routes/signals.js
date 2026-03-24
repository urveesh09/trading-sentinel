const express = require('express');
const router = express.Router();
const { z } = require('zod');
const crypto = require('crypto');
const { v4: uuidv4 } = require('uuid');
const { signalsDb } = require('../db/index');
const telegram = require('../services/telegram');
const { logger } = require('../middleware/logger');
const { StaleSignalError } = require('../utils/errors');

// Zod Schema for Signal
const signalSchema = z.object({
  ticker: z.string().min(2).max(20).regex(/^[A-Z0-9&-]+$/).transform(val => val.toUpperCase()),
  exchange: z.literal('NSE'),
  close: z.number().positive().finite(),
  stop_loss: z.number().positive(),
  target_1: z.number().positive(),
  target_2: z.number().positive(),
  shares: z.number().int().min(1).max(10000),
  capital_at_risk: z.number().positive().max(50), // Hard limit enforced here
  score: z.number().int().min(0).max(100),
  signal_time: z.string().datetime(),
  sector: z.string().optional(),
  market_regime: z.string().optional(),
  net_ev: z.number().optional(),
  volume_ratio: z.number().optional(),
  rsi_14: z.number().optional()
}).refine(data => data.stop_loss < data.close, {
  message: "Stop loss must be below close price",
  path: ["stop_loss"]
}).refine(data => data.target_1 > data.close, {
  message: "Target 1 must be above close price",
  path: ["target_1"]
}).refine(data => data.target_2 > data.target_1, {
  message: "Target 2 must be above Target 1",
  path: ["target_2"]
});

// Webhook Signature Middleware
const verifySignalWebhook = (req, res, next) => {
  const signature = req.headers['x-webhook-signature'];
  if (!signature) return res.status(401).json({ error: 'unauthorized', message: 'Missing signature' });

  const rawBody = JSON.stringify(req.body); // Assumes body-parser hasn't mutated order
  const expectedSig = crypto.createHmac('sha256', config.OPENCLAW_WEBHOOK_SECRET)
                            .update(rawBody)
                            .digest('hex');

  try {
    if (!crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expectedSig))) {
      throw new Error();
    }
    next();
  } catch {
    return res.status(401).json({ error: 'unauthorized', message: 'Invalid signature' });
  }
};

router.post('/', verifySignalWebhook, async (req, res, next) => {
  try {
    const signalData = signalSchema.parse(req.body);
    const now = Date.now();
    const signalTime = new Date(signalData.signal_time).getTime();

    // 1. Staleness Check (> 5 mins)
    if (now - signalTime > 300000) {
      throw new StaleSignalError('Signal exceeds 5-minute age limit');
    }

    // 2. Duplicate Check
    const isDuplicate = signalsDb.prepare(`
      SELECT 1 FROM received_signals WHERE ticker = ? AND signal_time = ?
    `).get(signalData.ticker, signalData.signal_time);

    if (isDuplicate) {
      logger.info({ event_type: 'duplicate_signal_dropped', ticker: signalData.ticker });
      return res.status(200).json({ received: true, duplicate: true });
    }

    // 3. Process Fresh Signal
    const signalId = uuidv4();
    signalData.signal_id = signalId; // attach ID for telegram formatter

    signalsDb.prepare(`
      INSERT INTO received_signals (signal_id, ticker, signal_time, received_at, payload_json, status)
      VALUES (?, ?, ?, ?, ?, 'PENDING')
    `).run(signalId, signalData.ticker, signalData.signal_time, new Date().toISOString(), JSON.stringify(signalData));

    // 4. Send Telegram Alert
    const msgId = await telegram.sendSignalAlert(signalData);
    if (msgId) {
      signalsDb.prepare(`UPDATE received_signals SET telegram_msg_id = ? WHERE signal_id = ?`)
        .run(msgId, signalId);
    }

    logger.info({ event_type: 'signal_received', signalId, ticker: signalData.ticker });
    res.status(200).json({ received: true, signal_id: signalId });

  } catch (err) {
    next(err);
  }
});

module.exports = router;
