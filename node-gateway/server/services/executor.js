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
    if (!response.ok) {
      // [ROADMAP-4.4 2026-07-13] Tag the error with what the ENGINE actually
      // returned, so withRetry can tell "engine is down, try again" (5xx)
      // from "the engine rejected this payload" (4xx). Untagged, a malformed
      // sync payload was retried 3 times over 35 seconds before giving up.
      const err = new Error(`Engine returned ${response.status}`);
      err.upstreamStatus = response.status;
      throw err;
    }
    return true;
  } catch (err) {
    clearTimeout(timeout);
    throw err;
  }
}

/**
 * Broker-side protective stop for an MIS (intraday) position.
 *
 * Zerodha GTT supports CNC/NRML only, so an MIS position cannot be protected by
 * a GTT — a resting stop order at the exchange is the only broker-side stop
 * available intraday. Until 2026-07-14 the GTT block was guarded by
 * `if (!isIntraday)` and nothing took its place, so every momentum position sat
 * at the exchange with NO stop and NO target from fill until the 15:15
 * auto-square. Position sizing divides by (entry - stop), so the risk-per-trade
 * figure was assuming a stop that did not exist.
 *
 * [FIX 2026-07-15] The stop was an SL-M (stop-loss MARKET) order, which Zerodha
 * rejects over the API with "Market orders without market protection are not
 * allowed via API. Please set market protection or use a Limit order." — so the
 * stop was ALWAYS rejected and every MIS buy was left unprotected. We now use an
 * SL (stop-loss LIMIT) order, exactly the limit-order route the buy leg already
 * uses. Once the trigger fires, the limit sits 1% BELOW the trigger, so it is
 * marketable and fills immediately at the best bid (a SELL limit below market
 * fills at market) while capping worst-case slippage at ~1%. For a SELL SL the
 * limit must be <= trigger, which this also satisfies.
 *
 * Two attempts, then the caller unwinds — the mandatory-stop discipline from
 * penny_executor.py (spec §7.2): a live position we cannot protect is worse than
 * no position.
 *
 * Returns the stop order id, or null if it could not be placed.
 */
async function placeProtectiveStop(signal) {
  // SELL stop: snap the trigger DOWN so it never lands above the intended stop.
  const trigger = snapToTick(signal.stop_loss, -1);
  // Limit 1% below the trigger: <= trigger (valid SELL SL) and marketable on
  // trigger (fills at market bid), so it behaves like a stop-market but is
  // API-legal without market protection.
  const limit = snapToTick(signal.stop_loss * 0.99, -1);

  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      const res = await kite.placeOrder({
        exchange: "NSE",
        tradingsymbol: signal.ticker,
        transaction_type: "SELL",
        quantity: signal.shares,
        product: "MIS",
        order_type: "SL",
        trigger_price: trigger,
        price: limit,
        validity: "DAY",
        tag: "QUANT_SENTINEL_SL"
      });

      if (res && res.order_id) {
        logger.info({
          event_type: 'mis_sl_m_placed',
          ticker: signal.ticker, order_id: res.order_id, trigger, limit
        });
        return String(res.order_id);
      }
      logger.error({ event_type: 'mis_sl_m_no_order_id', ticker: signal.ticker, attempt, res });
    } catch (err) {
      logger.error({ event_type: 'mis_sl_m_failed', ticker: signal.ticker, attempt, err: err.message });
    }
  }
  return null;
}

/**
 * Flatten an MIS position at market. Used when the protective SL-M cannot be
 * placed — we refuse to hold an unprotected intraday position.
 */
async function marketUnwind(signal, ltp) {
  // [FIX 2026-07-15] Was an order_type:"MARKET" order tagged
  // "QUANT_SENTINEL_UNWIND" (21 chars). Zerodha rejected it on BOTH counts:
  // the tag exceeds the 20-char limit ("Invalid tags"), and a MARKET order over
  // the API needs market protection ("Market orders without market protection
  // are not allowed"). So the unwind ALWAYS failed and the just-bought position
  // was left naked while the operator was told it had been unwound. We now sell
  // via a marketable LIMIT (1% below LTP, snapped down) — the same route the buy
  // leg uses — with a <=20-char tag.
  const limit = snapToTick((ltp || signal.close) * 0.99, -1);
  try {
    const res = await kite.placeOrder({
      exchange: "NSE",
      tradingsymbol: signal.ticker,
      transaction_type: "SELL",
      quantity: signal.shares,
      product: "MIS",
      order_type: "LIMIT",
      price: limit,
      validity: "DAY",
      tag: "QUANT_SENT_UNWIND"
    });
    logger.error({
      event_type: 'mis_unprotected_unwound',
      ticker: signal.ticker, unwind_order_id: res && res.order_id, limit
    });
    return res && res.order_id ? String(res.order_id) : null;
  } catch (err) {
    // Both the stop and the unwind failed. This is the one case an operator
    // must handle by hand, so say so loudly rather than logging quietly.
    logger.error({ event_type: 'mis_unwind_failed', ticker: signal.ticker, err: err.message });
    telegram.sendAlert(
      `🚨 ${signal.ticker}: protective stop FAILED and unwind FAILED. ` +
      `You are holding ${signal.shares} shares with NO stop. FLATTEN MANUALLY NOW.`
    );
    return null;
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

    // 5. Protective exit orders.
  //    CNC/swing  -> GTT (stop + T1 legs).
  //    MIS/intraday -> SL-M, because Zerodha GTT does not support MIS.
  //
  //    Only the STOP rests at the broker for MIS. A resting target order would
  //    need OCO to be safe, and Zerodha has no OCO for MIS — if both the stop and
  //    the target filled we would be short. The target is taken by the engine-side
  //    intraday monitor, which cancels this SL-M before it sells.
  let gttStopId = null;
  let gttTargetId = null;
  let slOrderId = null;

  if (isIntraday) {
    slOrderId = await placeProtectiveStop(signal);

    if (!slOrderId) {
      // Stop could not be placed. We refuse to hold an unprotected MIS position,
      // so flatten it. The buy has already filled, so distinguish the two exits:
      const unwindId = await marketUnwind(signal, ltp);

      if (unwindId) {
        // Flat again — the position is closed, so it is safe to retry the signal.
        signalsDb.prepare(
          `UPDATE executed_orders SET status = 'CANCELLED', notes = ? WHERE order_id = ?`
        ).run('sl_failed_position_unwound', orderId);
        throw new OrderExecutionError(
          `${signal.ticker}: protective stop was rejected; position was unwound. Safe to retry.`
        );
      }

      // Stop failed AND unwind failed: the shares are still held with no stop.
      // Do NOT mark this CANCELLED (that hides a real fill from the books) and do
      // NOT let the caller invite a retry (that would stack another naked buy).
      signalsDb.prepare(
        `UPDATE executed_orders SET status = 'OPEN_UNPROTECTED', notes = ? WHERE order_id = ?`
      ).run('sl_and_unwind_failed_manual_flatten', orderId);
      const held = new OrderExecutionError(
        `${signal.ticker}: HOLDING ${signal.shares} shares with NO protective stop — ` +
        `the unwind order also failed. FLATTEN THIS POSITION MANUALLY NOW. Do NOT retry the button.`
      );
      held.positionHeld = true;
      throw held;
    }
  } else {
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


  // Update DB with Fill + protective orders
  signalsDb.prepare(`
    UPDATE executed_orders
    SET status = 'COMPLETE', entry_price = ?, filled_at = ?, gtt_stop_id = ?, gtt_target_id = ?, sl_order_id = ?, notes = ?
    WHERE order_id = ?
  `).run(fillPrice, new Date().toISOString(), gttStopId, gttTargetId, slOrderId, finalNotes, orderId);

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
    // [TRAILING-EXITS 2026-06-16] Forward regime at entry so the position row
    // records it and position_tracker can pick the regime-aware Chandelier
    // multiplier (3.5x R1, 3.0x R2, 2.5x R3). Null when the screener didn't
    // tag it (backward compat — legacy 3.0x trail).
    regime_at_entry: signal.regime ?? null,
    // Chandelier trail sizes off this. Forward null rather than 0 when the
    // screener couldn't compute one — a 0 ATR collapses the trail onto entry.
    atr_14_at_entry: signal.atr_at_entry ?? null,
    order_id: String(orderId),
    gtt_stop_id: gttStopId ? String(gttStopId) : null,
    gtt_target_id: gttTargetId ? String(gttTargetId) : null,
    // The engine's intraday monitor cancels this SL-M before it takes a target
    // or a trail exit, so it must know the id.
    sl_order_id: slOrderId,
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

module.exports = { executeSignal, syncToEngine, snapToTick };
