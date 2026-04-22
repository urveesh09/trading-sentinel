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
  
  const ltp = ltpData[`NSE:${signal.ticker}`]?.last_price;
  if (!ltp) throw new OrderExecutionError('Invalid LTP response');
  
  const drift = Math.abs(ltp - signal.close) / signal.close;
  if (drift > 0.02) {
    throw new PriceDriftError(`LTP ${ltp} drifted ${Math.round(drift * 100)}% from signal ${signal.close}`);
  }

  // 3. Market Order Execution
  let orderResponse;
  try {
    orderResponse = await withRetry(async () => {
      return await kite.placeOrder({
        exchange: "NSE",
        tradingsymbol: signal.ticker,
        transaction_type: "BUY",
        quantity: signal.shares,
        product: isIntraday ? "MIS" : "CNC",
        order_type: "MARKET",
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
      VALUES (?, ?, ?, 'MARKET', ?, 'PLACED', ?, 0)
    `).run(signal.signal_id, signal.ticker, orderId, signal.shares, new Date().toISOString());
  } catch (err) {
    // If UNIQUE constraint fails here, it's a replay. We stop safely.
    logger.error({ event_type: 'layer_2_idempotency_catch', orderId });
    throw new OrderExecutionError('Order tracking collision detected.');
  }

  // 4. Fill Verification (8 attempts x 1500ms = 12s)
  let isFilled = false;
  let fillPrice = signal.close; // Default estimate
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
          //price: Number((signal.stop_loss * 1.002).toFixed(2)) // Sell above trigger
          price: Math.round((signal.stop_loss * 1.002) * 20) / 20 // Rounds to nearest 0.05
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
          //price: Number((signal.target_1 * 0.998).toFixed(2)) // Small buffer below trigger
          price: Math.round((signal.target_1 * 0.998) * 20) / 20 // Rounds to nearest 0.05  
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
