const express = require('express');
const router = express.Router();
const { z } = require('zod');
const { signalsDb } = require('../db/index');
const executor = require('../services/executor');
const { requireSession, requireInternalSecret } = require('../middleware/auth');
const kite = require('../services/kite');
const { validate } = require('../middleware/validate');
const { ReplayAttackError } = require('../utils/errors');

const executeSchema = z.object({
  signal_id: z.string().uuid()
});

const squareOffSchema = z.object({
  ticker: z.string().min(1),
  shares: z.number().int().positive(),
  order_type: z.enum(['MARKET', 'LIMIT']),
  limit_price: z.number().optional(),
  product_type: z.enum(['MIS', 'CNC']),
  reason: z.string().optional()
});

// GET /api/orders/ltp?ticker=RELIANCE
// Called by Container B before square-off order type decision
router.get('/ltp', requireInternalSecret, async (req, res, next) => {
  try {
    const { ticker } = req.query;
    if (!ticker) return res.status(400).json({ error: 'missing_ticker' });

    const fullTicker = `NSE:${ticker}`;
    const ltpData = await kite.getLTP([fullTicker]);
    
    if (!ltpData || !ltpData[fullTicker]) {
      return res.status(404).json({ error: 'ticker_not_found' });
    }

    res.json({
      ticker,
      ltp: ltpData[fullTicker].last_price,
      timestamp: new Date().toISOString()
    });
  } catch (err) {
    next(err);
  }
});

// POST /api/orders/square-off
// Called by Container B at 15:15 IST for momentum auto-square
router.post('/square-off', requireInternalSecret, validate(squareOffSchema, 'body'), async (req, res, next) => {
  try {
    const { ticker, shares, order_type, limit_price, product_type, reason } = req.body;
    
    const orderParams = {
      exchange: 'NSE',
      tradingsymbol: ticker,
      transaction_type: 'SELL',
      quantity: shares,
      order_type: order_type,
      product: product_type,
      tag: 'QUANT_SENTINEL'
    };

    if (order_type === 'LIMIT') {
      if (!limit_price) return res.status(400).json({ error: 'limit_price_required' });
      orderParams.price = limit_price;
    }

    const orderId = await kite.placeOrder(orderParams);
    
    // Log the square-off event
    console.log(`[SQUARE-OFF] ${ticker} | Qty: ${shares} | Type: ${order_type} | Reason: ${reason || 'N/A'}`);

    res.json({ success: true, order_id: orderId });
  } catch (err) {
    next(err);
  }
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
