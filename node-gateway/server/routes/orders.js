const express = require('express');
const router = express.Router();
const { z } = require('zod');
const { signalsDb } = require('../db/index');
const executor = require('../services/executor');
const { snapToTick } = executor;
const { requireSession, requireInternalSecret } = require('../middleware/auth');
const kite = require('../services/kite');
const { validate } = require('../middleware/validate');
const { ReplayAttackError } = require('../utils/errors');
const crypto = require('crypto');

// Serialize same-key requests inside this process and retain the known broker
// id. Broker lookup provides restart recovery; this registry closes the small
// eventual-consistency window immediately after a successful submission.
const squareOffLocks = new Map();
const squareOffKnownOrders = new Map();

async function acquireSquareOffLock(key) {
  const previous = squareOffLocks.get(key) || Promise.resolve();
  let releaseGate;
  const gate = new Promise(resolve => { releaseGate = resolve; });
  const tail = previous.then(() => gate);
  squareOffLocks.set(key, tail);
  await previous;
  return () => {
    releaseGate();
    if (squareOffLocks.get(key) === tail) squareOffLocks.delete(key);
  };
}

const executeSchema = z.object({
  signal_id: z.string().uuid()
});

const squareOffSchema = z.object({
  ticker: z.string().min(1),
  shares: z.number().int().positive(),
  order_type: z.enum(['MARKET', 'LIMIT']),
  limit_price: z.number().optional(),
  product_type: z.enum(['MIS', 'CNC']),
  idempotency_key: z.string().min(8).max(128),
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
  let releaseLock = null;
  try {
    const { ticker, shares, order_type, limit_price, product_type, idempotency_key, reason } = req.body;
    releaseLock = await acquireSquareOffLock(idempotency_key);
    const requestFingerprint = JSON.stringify({
      ticker, shares, product_type, order_type, limit_price: limit_price || null,
    });
    const knownOrder = squareOffKnownOrders.get(idempotency_key);
    if (knownOrder && knownOrder.fingerprint !== requestFingerprint) {
      return res.status(409).json({
        success: false, state: 'REJECTED', terminal: true, complete: false,
        order_id: knownOrder.orderId,
        message: 'This square-off idempotency key was already used with different order parameters.',
      });
    }

    // [FIX 2026-07-15] A raw MARKET SELL is rejected by Zerodha over the API
    // ("Market orders without market protection are not allowed"). Callers today
    // (engine auto-square / momentum exits) always send LIMIT, but the schema
    // still permits MARKET — so convert any MARKET request into a marketable
    // LIMIT (0.5% below LTP, snapped down) rather than forward an order the
    // broker will reject. Keeps the square-off's must-fill intent while staying
    // API-legal.
    let effectiveType = order_type;
    let effectivePrice = limit_price;
    if (!knownOrder && order_type === 'MARKET') {
      const fullTicker = `NSE:${ticker}`;
      const ltpData = await kite.getLTP([fullTicker]);
      const ltp = ltpData && ltpData[fullTicker] && ltpData[fullTicker].last_price;
      if (!ltp) return res.status(404).json({ error: 'ticker_not_found_for_market_conversion' });
      effectiveType = 'LIMIT';
      effectivePrice = snapToTick(ltp * 0.995, -1);
    }

    const squareOffTag = `QX_${crypto.createHash('sha256').update(idempotency_key).digest('hex').slice(0, 16)}`;
    const orderParams = {
      exchange: 'NSE',
      tradingsymbol: ticker,
      transaction_type: 'SELL',
      quantity: shares,
      order_type: effectiveType,
      product: product_type,
      tag: squareOffTag
    };

    if (effectiveType === 'LIMIT') {
      if (!effectivePrice) return res.status(400).json({ error: 'limit_price_required' });
      orderParams.price = effectivePrice;
    }

    // Square-off is an EXIT: never halt-gated. Blocking it would leave the
    // position open past its square-off with no protection, which is the
    // opposite of what a kill switch is for.
    let orderResponse = knownOrder ? { order_id: knownOrder.orderId } : null;
    try {
      // Cross-service idempotency: Python may time out after this process (and
      // Kite) accepted the prior request. Look up the stable tag BEFORE every
      // submission so the retry reconciles that order rather than selling twice.
      if (!orderResponse) {
        const existingOrders = await kite.getOrders();
        const existing = (existingOrders || []).filter(order =>
          order.tag === squareOffTag && order.transaction_type === 'SELL' &&
          order.tradingsymbol === ticker && Number(order.quantity) === Number(shares)
        );
        if (existing.length > 1) {
          return res.status(503).json({
            success: false, state: 'UNKNOWN', terminal: false, complete: false,
            order_id: null,
            message: 'Multiple broker orders match this square-off idempotency key; manual reconciliation is required.',
          });
        }
        if (existing.length === 1) orderResponse = { order_id: existing[0].order_id };
      }
    } catch (err) {
      return res.status(503).json({
        success: false, state: 'UNKNOWN', terminal: false, complete: false,
        order_id: null,
        message: 'Unable to check square-off idempotency at the broker; no order was submitted.',
      });
    }

    try {
      // A non-idempotent SELL is submitted once. If the response is lost, find
      // that exact tagged order; never blindly resubmit it.
      if (!orderResponse) {
        orderResponse = await kite.placeOrder(orderParams, { intent: 'exit', channel: 'momentum' });
      }
    } catch (err) {
      if (err.retryable === false || ['OrderExecutionError', 'TokenExpiredError', 'ValidationError'].includes(err.name)) {
        throw err;
      }
      let recovered = null;
      try {
        const orders = await kite.getOrders();
        const matches = (orders || []).filter(order =>
          order.tag === squareOffTag && order.transaction_type === 'SELL' &&
          order.tradingsymbol === ticker && Number(order.quantity) === Number(shares)
        );
        if (matches.length === 1) recovered = matches[0];
      } catch (_) {
        // The original error is more useful; response below remains fail-closed.
      }
      if (!recovered?.order_id) {
        return res.status(503).json({
          success: false, state: 'UNKNOWN', terminal: false, complete: false,
          order_id: null,
          message: 'Square-off submission outcome is unknown; broker reconciliation is required before retrying.',
        });
      }
      orderResponse = { order_id: recovered.order_id };
    }

    const orderId = String(orderResponse?.order_id || orderResponse || '');
    if (!orderId) {
      return res.status(503).json({
        success: false, state: 'UNKNOWN', terminal: false, complete: false, order_id: null,
      });
    }
    squareOffKnownOrders.set(idempotency_key, { orderId, fingerprint: requestFingerprint });

    let fill;
    try {
      // A square-off cannot return while its remaining quantity is still OPEN:
      // the next scheduler tick might otherwise submit another SELL. Poll,
      // cancel any remainder, then return only terminal/UNKNOWN truth.
      fill = await executor.reconcilePlacedOrder(orderId, shares, {
        ticker, product: product_type,
      });
    } catch (err) {
      fill = {
        state: 'UNKNOWN', terminal: false, filledQuantity: 0, fillPrice: null,
        reason: err.message,
      };
    }
    
    // Log the square-off event
    console.log(`[SQUARE-OFF] ${ticker} | Qty: ${shares} | Type: ${order_type} | Reason: ${reason || 'N/A'}`);

    res.status(fill.state === 'COMPLETE' ? 200 : 202).json({
      success: fill.state === 'COMPLETE',
      state: fill.state,
      terminal: fill.terminal,
      complete: fill.state === 'COMPLETE',
      order_id: orderId,
      requested_quantity: shares,
      filled_quantity: fill.filledQuantity,
      remaining_quantity: Math.max(0, shares - fill.filledQuantity),
      average_price: fill.fillPrice,
      rejection_reason: fill.reason || null,
    });
  } catch (err) {
    next(err);
  } finally {
    if (releaseLock) releaseLock();
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
      // UNKNOWN/possibly-held outcomes must retain the EXECUTING lock. Resetting
      // them to PENDING would let a second click stack another BUY.
      if (!execErr.positionHeld && !execErr.outcomeUnknown) {
        signalsDb.prepare(`UPDATE received_signals SET status = 'PENDING' WHERE signal_id = ?`).run(signal_id);
      }
      throw execErr;
    }

  } catch (err) {
    next(err);
  }
});

module.exports = router;
