const express = require('express');
const router = express.Router();
const { z } = require('zod');
const { signalsDb } = require('../db/index');
const executor = require('../services/executor');
const { requireSession } = require('../middleware/auth');
const { validate } = require('../middleware/validate');
const { ReplayAttackError } = require('../utils/errors');

const executeSchema = z.object({
  signal_id: z.string().uuid()
});

// Web fallback for Telegram execution
router.post('/execute', requireSession, validate(executeSchema, 'body'), async (req, res, next) => {
  try {
    const { signal_id } = req.body;

    // Layer 1: In-band lock
    const tx = signalsDb.transaction(() => {
      const row = signalsDb.prepare(`SELECT status, payload_json FROM received_signals WHERE signal_id = ?`).get(signal_id);
      
      if (!row) throw new Error('Signal not found');
      if (row.status !== 'PENDING') throw new ReplayAttackError(`Signal is already ${row.status}`);

      signalsDb.prepare(`UPDATE received_signals SET status = 'EXECUTING' WHERE signal_id = ?`).run(signal_id);
      return row;
    });

    let signalRecord;
    try {
      signalRecord = tx();
    } catch (err) {
      if (err instanceof ReplayAttackError) return res.status(409).json({ error: err.type, message: err.message });
      return res.status(404).json({ error: 'not_found', message: 'Signal not found' });
    }

    const signalData = JSON.parse(signalRecord.payload_json);

    // Call Executor
    try {
      const result = await executor.executeSignal(signalData, 'EXEC');
      signalsDb.prepare(`UPDATE received_signals SET status = 'EXECUTED' WHERE signal_id = ?`).run(signal_id);
      
      // Notify via Telegram of web execution
      const telegram = require('../services/telegram');
      telegram.sendAlert(`🌐 Signal ${signalData.ticker} executed via Web Dashboard.\nAvg Price: ₹${result.fillPrice}`);
      
      res.json({ success: true, order_id: result.orderId, fill_price: result.fillPrice });
    } catch (execErr) {
      // Revert lock on execution failure so it can be retried
      signalsDb.prepare(`UPDATE received_signals SET status = 'PENDING' WHERE signal_id = ?`).run(signal_id);
      throw execErr;
    }

  } catch (err) {
    next(err);
  }
});

module.exports = router;
