const kite = require('./kite');
const { signalsDb } = require('../db/index');
const { withRetry } = require('../utils/retry');
const config = require('../config');
const telegram = require('./telegram');
const { isMarketOpen } = require('../utils/market-hours');
const { 
  TokenExpiredError, ValidationError, PriceDriftError, 
  MarketClosedError, OrderExecutionError 
} = require('../utils/errors');
const { logger } = require('../middleware/logger');

/**
 * Snap a price to the nearest valid NSE tick (0.10 rupee).
 * 0.10 is the LCM of all NSE equity tick sizes (0.05 and 0.10),
 * so any multiple of 0.10 is always accepted by Zerodha regardless of the stock.
 * dir=1 → round UP (buy orders — guarantees fill above ask)
 * dir=-1 → round DOWN (sell orders — guarantees fill below bid)
 * Uses integer arithmetic to avoid IEEE-754 drift (e.g. 804.10 * 10 = 8041.0000001).
 */
function snapToTick(price, dir = 1) {
  const inTenths = Math.round(price * 10 * 100) / 100; // isolate tenths with 2dp guard
  const fn = dir >= 0 ? Math.ceil : Math.floor;
  return fn(inTenths) / 10;
}

/**
 * SYNC TO CONTAINER B
 */
async function syncToEngine(payload) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), config.PYTHON_ENGINE_TIMEOUT_MS);
  
  try {
    const response = await fetch(`${config.PYTHON_ENGINE_URL}/positions/manual`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Internal-Secret': config.INTERNAL_API_SECRET
      },
      body: JSON.stringify(payload),
      signal: controller.signal
    });
    
    clearTimeout(timeout);
    if (!response.ok) throw new Error(`Engine returned ${response.status}`);
    return true;
  } catch (err) {
    clearTimeout(timeout);
    throw err;
  }
}

/**
 * CORE EXECUTION ENGINE
 */
async function executeSignal(signal, action, isIntraday = false) {
  logger.info({ event_type: 'execution_started', ticker: signal.ticker, id: signal.signal_id, isIntraday });

    // 1. Token & Pre-checks
  if (!require('./token-store').isValid()) throw new TokenExpiredError();
  if (!isMarketOpen()) throw new MarketClosedError();
  if (signal.capital_at_risk > 1500) throw new ValidationError('Capital at risk exceeds absolute maximum limit.');
  
  // 2. Price Drift Check

  let ltpData;
  try {
    ltpData = await kite.getLTP([`NSE:${signal.ticker}`]);
  } catch (err) {
    throw new OrderExecutionError(`Failed to fetch LTP for drift check: ${err.message}`);
  }
  
  const ltp = ltpData?.[`NSE:${signal.ticker}`]?.last_price;
  if (!ltp) {
    logger.warn({ event_type: 'ltp_invalid_response', ticker: signal.ticker, ltpData });
    throw new OrderExecutionError('Invalid LTP response');
  }
  
  const drift = Math.abs(ltp - signal.close) / signal.close;
  if (drift > 0.02) {
    throw new PriceDriftError(`LTP ${ltp} drifted ${Math.round(drift * 100)}% from signal ${signal.close}`);
  }

  // 3. Limit Order Execution
  // [FIX] Zerodha API rejects MARKET orders without market_protection.
  // Buy LIMIT at LTP + 0.5%, snapped UP to the nearest 0.10-rupee tick.
  // 0.10 satisfies both NSE tick sizes (0.05 and 0.10); stays inside the
  // 2% drift window already enforced above.
  const limitPrice = snapToTick(ltp * 1.005, 1);
  let orderResponse;
  try {
    orderResponse = await withRetry(async () => {
      return await kite.placeOrder({
        exchange: "NSE",
        tradingsymbol: signal.ticker,
        transaction_type: "BUY",
        quantity: signal.shares,
        product: isIntraday ? "MIS" : "CNC",
        order_type: "LIMIT",
        price: limitPrice,
        validity: "DAY",
        tag: "QUANT_SENTINEL"
      });

    }, 1, 2000); // 1 retry on OrderException
  } catch (err) {
    throw new OrderExecutionError(`Order Placement Failed: ${err.message}`);
  }


  const orderId = orderResponse.order_id;
  
  // Layer 2 Idempotency: Insert into DB immediately
  try {
    signalsDb.prepare(`
      INSERT INTO executed_orders (signal_id, ticker, order_id, order_type, shares, status, placed_at, sync_to_b)
      VALUES (?, ?, ?, 'LIMIT', ?, 'PLACED', ?, 0)
    `).run(signal.signal_id, signal.ticker, orderId, signal.shares, new Date().toISOString());
  } catch (err) {
    // The INSERT can fail for two distinct reasons:
    //   a) signal_id FK/NOT NULL violation (momentum signal missing signal_id field)
    //   b) order_id UNIQUE violation (genuine replay attack, order already tracked)
    // Both are safety stops: the order is placed but we cannot track it safely.
    logger.error({ event_type: 'layer_2_idempotency_catch', orderId, err: err.message });
    throw new OrderExecutionError('Order tracking failed: ' + err.message);
  }

  // 4. Fill Verification (8 attempts x 1500ms = 12s)
  let isFilled = false;
  // [MED-003] Use LTP (fetched during drift check, ~60s more recent than signal.close)
  // as the fill estimate when order confirmation times out.
  let fillPrice = ltp;
  let rejectionReason = null;

  for (let i = 0; i < 8; i++) {
    await new Promise(r => setTimeout(r, 1500));
    try {
      const history = await kite.getOrderHistory(orderId);
      const latest = history[history.length - 1]; // Current state
      
      if (latest.status === 'COMPLETE') {
        isFilled = true;
        fillPrice = latest.average_price || latest.price;
        break;
      }
      if (latest.status === 'REJECTED' || latest.status === 'CANCELLED') {
        rejectionReason = latest.status_message || latest.status;
        break;
      }
    } catch (err) {
      logger.warn({ event_type: 'fill_check_failed', err: err.message });
    }
  }

  if (rejectionReason) {
    signalsDb.prepare(`UPDATE executed_orders SET status = 'REJECTED', notes = ? WHERE order_id = ?`)
      .run(rejectionReason, orderId);
    throw new OrderExecutionError(`Order rejected by broker: ${rejectionReason}`);
  }

  const finalNotes = isFilled ? "Executed via Telegram" : "fill_unconfirmed - using signal close as estimate";
  if (!isFilled) {
    logger.warn({ event_type: 'fill_unconfirmed', orderId });
  }

    // 5. GTT Order Execution (Only for CNC/Swing)
  let gttStopId = null;
  let gttTargetId = null;
  
  if (!isIntraday) {
    try {
      // Stop-loss Leg
      const stopRes = await kite.placeGTT({
        trigger_type: "single",
        tradingsymbol: signal.ticker,
        exchange: "NSE",
        trigger_values: [signal.stop_loss],
        last_price: ltp,
        orders: [{
          transaction_type: "SELL",
          quantity: signal.shares,
          order_type: "LIMIT",
          product: "CNC",
          // Stop-loss SELL limit must be AT OR ABOVE the trigger to guarantee execution.
          // snapToTick(..., 1) rounds UP to the nearest 0.10-rupee tick.
          price: snapToTick(signal.stop_loss * 1.002, 1)
        }]
      });
      gttStopId = stopRes.trigger_id;

      // Target Leg (Half quantity for T1)
      const t1Shares = Math.floor(signal.shares / 2) || 1;
      const targetRes = await kite.placeGTT({
        trigger_type: "single",
        tradingsymbol: signal.ticker,
        exchange: "NSE",
        trigger_values: [signal.target_1],
        last_price: ltp,
        orders: [{
          transaction_type: "SELL",
          quantity: t1Shares,
          order_type: "LIMIT",
          product: "CNC",
          // [MED-012] Target GTT uses 0.998× (BELOW trigger) — intentional.
          // For a SELL order: setting limit slightly below trigger ensures immediate
          // fill when the target price is touched. This is the opposite of the stop-loss
          // leg (1.002× ABOVE trigger) but both approaches guarantee execution.
          // The inviolable rule "trigger * 1.002" applies to stop-loss legs only.
          // snapToTick(..., -1) rounds DOWN to nearest 0.10-rupee tick.
          price: snapToTick(signal.target_1 * 0.998, -1)
      }]
      });
      gttTargetId = targetRes.trigger_id;

    } catch (err) {
      logger.error({ event_type: 'gtt_placement_error', err: err.message });
      // Note: We don't throw here. Market order is already placed. We must sync the open position.
      telegram.sendAlert(`⚠️ GTT placement failed for ${signal.ticker} (Order ${orderId}). Please place manual exit orders.`);
    }
  }


  // Update DB with Fill + GTTs
  signalsDb.prepare(`
    UPDATE executed_orders 
    SET status = 'COMPLETE', entry_price = ?, filled_at = ?, gtt_stop_id = ?, gtt_target_id = ?, notes = ?
    WHERE order_id = ?
  `).run(fillPrice, new Date().toISOString(), gttStopId, gttTargetId, finalNotes, orderId);

    // 6. Sync to Container B
  const syncPayload = {
    ticker: signal.ticker,
    exchange: "NSE",
    entry_price: fillPrice,
    shares: signal.shares,
    stop_loss: signal.stop_loss,
    target_1: signal.target_1,
    target_2: signal.target_2,
    source: isIntraday ? "MOMENTUM" : "SYSTEM",
    // [MED-008] Pass product_type so Container B can store it in the positions table
    // and auto_square_momentum() can read the correct product type for square-off orders.
    product_type: isIntraday ? "MIS" : "CNC",
    order_id: String(orderId),
    gtt_stop_id: gttStopId ? String(gttStopId) : null,
    gtt_target_id: gttTargetId ? String(gttTargetId) : null,
    notes: finalNotes
  };


  try {
    await withRetry(() => syncToEngine(syncPayload), 3, 5000);
    signalsDb.prepare(`UPDATE executed_orders SET sync_to_b = 1 WHERE order_id = ?`).run(orderId);
  } catch (err) {
    logger.error({ event_type: 'sync_back_failed', err: err.message, orderId });
    signalsDb.prepare(`UPDATE executed_orders SET sync_to_b = 2 WHERE order_id = ?`).run(orderId);
    telegram.sendAlert(`🚨 Order placed (#${orderId}) but sync to quant engine failed entirely. Manual registration required at dashboard.`);
  }

  return { orderId, fillPrice, gttStopId, gttTargetId };
}

module.exports = { executeSignal, syncToEngine };
