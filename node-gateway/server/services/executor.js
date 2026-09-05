const kite = require('./kite');
const { signalsDb } = require('../db/index');
const { withRetry } = require('../utils/retry');
const config = require('../config');
const telegram = require('./telegram');
const { isMarketOpen } = require('../utils/market-hours');
const { 
  TokenExpiredError, ValidationError, PriceDriftError, 
  MarketClosedError, OrderExecutionError, InsufficientMarginError
} = require('../utils/errors');
const { logger } = require('../middleware/logger');
const { resolveRiskDistance, anchorLevels, sizeToRisk } = require('./risk-geometry');
const crypto = require('crypto');

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

function finiteNonNegative(value) {
  // Number(null), Number(false), and Number('') all produce zero. None are
  // broker balance evidence, so only actual finite numeric values count.
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return null;
  return value;
}

function usableEntryMargin(margins) {
  // `live_balance` is the current usable balance, while `cash` is a separate
  // funds component. Prefer the former when supplied; never add collateral.
  const equity = margins?.equity;
  if (!equity || equity.enabled === false) return null;
  const available = equity.available || {};
  // A present live balance is authoritative even if it is invalid: falling
  // back to a raw cash component could authorize an entry while the current
  // usable balance is negative.  Only legacy responses that omit the field
  // altogether may use the documented cash fallback.
  if (Object.prototype.hasOwnProperty.call(available, 'live_balance')) {
    return finiteNonNegative(available.live_balance);
  }
  return finiteNonNegative(available.cash);
}

function requiredOrderMargin(orderMargins) {
  const row = Array.isArray(orderMargins) ? orderMargins[0] : orderMargins;
  const value = row?.initial?.total ?? row?.total;
  return finiteNonNegative(value);
}

async function preflightEntryMargin(notional, context) {
  let margins;
  try {
    margins = await kite.getMargins();
  } catch (err) {
    throw new OrderExecutionError(`MARGIN_EVIDENCE_UNAVAILABLE: ${err.message}`);
  }
  const available = usableEntryMargin(margins);
  if (available === null) {
    throw new OrderExecutionError('MARGIN_EVIDENCE_UNAVAILABLE: broker returned no usable cash balance');
  }
  let required = notional;
  let requirementBasis = 'conservative_notional_policy';
  if (typeof kite.getOrderMargins === 'function') {
    try {
      const calculated = await kite.getOrderMargins([{
        exchange: 'NSE', tradingsymbol: context.ticker, transaction_type: 'BUY',
        variety: 'regular', product: context.product, order_type: 'LIMIT',
        quantity: context.quantity, price: context.price,
      }]);
      const brokerRequired = requiredOrderMargin(calculated);
      if (brokerRequired !== null) {
        required = brokerRequired;
        requirementBasis = 'broker_order_margin';
      }
    } catch (err) {
      throw new OrderExecutionError(`MARGIN_EVIDENCE_UNAVAILABLE: order margin calculation failed: ${err.message}`);
    }
  }
  logger.info({
    event_type: 'entry_margin_preflight', ticker: context.ticker,
    required_margin: required, available_margin: available,
    product: context.product, requirement_basis: requirementBasis,
  });
  if (available < required) throw new InsufficientMarginError(required, available);
  return { required, available, requirementBasis, observedAt: new Date().toISOString() };
}

function entryTag(signalId) {
  // Kite tags are capped at 20 characters. A stable per-signal tag lets us
  // find an order that the broker accepted when the placement response was
  // lost, without ever submitting a second BUY.
  const digest = crypto.createHash('sha256').update(String(signalId)).digest('hex').slice(0, 16);
  return `QS_${digest}`;
}

function exitTag(signalId, kind) {
  const digest = crypto.createHash('sha256').update(String(signalId)).digest('hex').slice(0, 15);
  return `${kind}_${digest}`; // 18 chars, within Kite's 20-character cap
}

function isDefinitivePlacementError(err) {
  return err?.retryable === false ||
    ['OrderExecutionError', 'TokenExpiredError', 'ValidationError'].includes(err?.name);
}

function latestOrder(history) {
  return Array.isArray(history) && history.length ? history[history.length - 1] : null;
}

function orderFillState(order, requestedQuantity) {
  if (!order) return { state: 'UNKNOWN', terminal: false, filledQuantity: 0, fillPrice: null };
  const status = String(order.status || '').toUpperCase();
  const filledQuantity = Math.max(0, Number(order.filled_quantity || 0));
  const fillPrice = Number(order.average_price || order.price) || null;
  if (status === 'COMPLETE') {
    return { state: 'COMPLETE', terminal: true, filledQuantity: filledQuantity || requestedQuantity, fillPrice };
  }
  if (status === 'REJECTED') {
    return { state: 'REJECTED', terminal: true, filledQuantity, fillPrice, reason: order.status_message || status };
  }
  if (status === 'CANCELLED') {
    return {
      state: filledQuantity > 0 ? 'PARTIAL' : 'CANCELLED', terminal: true,
      filledQuantity, fillPrice, reason: order.status_message || status,
    };
  }
  return { state: filledQuantity > 0 ? 'PARTIAL_OPEN' : (status || 'UNKNOWN'), terminal: false, filledQuantity, fillPrice };
}

async function reconcilePlacedOrder(orderId, requestedQuantity, options = {}) {
  const attempts = options.attempts ?? 8;
  const delayMs = options.delayMs ?? 1500;
  let last = null;
  let historyError = null;

  for (let i = 0; i < attempts; i++) {
    if (i > 0 && delayMs > 0) await sleep(delayMs);
    try {
      last = orderFillState(latestOrder(await kite.getOrderHistory(orderId)), requestedQuantity);
      historyError = null;
      if (last.terminal) return last;
    } catch (err) {
      historyError = err;
      logger.warn({ event_type: 'fill_check_failed', order_id: orderId, err: err.message });
    }
  }

  // An OPEN/PARTIAL order must first be cancelled. Until the cancellation is
  // visible in broker history, its remaining quantity can still fill.
  let cancelError = null;
  try {
    await kite.cancelOrder(orderId);
  } catch (err) {
    cancelError = err;
    logger.error({ event_type: 'entry_cancel_failed', order_id: orderId, err: err.message });
  }

  try {
    last = orderFillState(latestOrder(await kite.getOrderHistory(orderId)), requestedQuantity);
    historyError = null;
    if (last.terminal) return last; // includes a late COMPLETE or cancelled partial fill
  } catch (err) {
    historyError = err;
  }

  // Positions are secondary evidence only: an existing holding cannot prove
  // this particular order filled. Capture it for the operator, but fail closed.
  let brokerPosition = null;
  try {
    const positions = await kite.getPositions();
    const rows = [...(positions?.net || []), ...(positions?.day || [])];
    brokerPosition = rows.find(p => String(p.tradingsymbol) === String(options.ticker) &&
      (!options.product || String(p.product) === String(options.product))) || null;
  } catch (err) {
    logger.warn({ event_type: 'position_reconciliation_failed', order_id: orderId, err: err.message });
  }

  return {
    state: 'UNKNOWN', terminal: false,
    filledQuantity: last?.filledQuantity || 0,
    fillPrice: last?.fillPrice || null,
    cancelError: cancelError?.message || null,
    historyError: historyError?.message || null,
    brokerPositionQuantity: brokerPosition ? Number(brokerPosition.quantity || 0) : null,
  };
}

async function recoverAmbiguousPlacement(params, tag) {
  try {
    const orders = await kite.getOrders();
    const matches = (orders || []).filter(order =>
      order.tag === tag &&
      order.tradingsymbol === params.tradingsymbol &&
      order.transaction_type === params.transaction_type &&
      Number(order.quantity) === Number(params.quantity)
    );
    if (matches.length === 1 && matches[0].order_id) return { order_id: matches[0].order_id, recovered: true };
  } catch (err) {
    logger.error({ event_type: 'ambiguous_placement_reconcile_failed', tag, err: err.message });
  }
  return null;
}

function sameNumberArray(left, right) {
  return Array.isArray(left) && Array.isArray(right) && left.length === right.length &&
    left.every((value, index) => Number(value) === Number(right[index]));
}

function gttMatches(gtt, params) {
  const condition = gtt?.condition || gtt || {};
  const orders = Array.isArray(gtt?.orders) ? gtt.orders : [];
  return String(condition.tradingsymbol || gtt?.tradingsymbol) === String(params.tradingsymbol) &&
    String(condition.exchange || gtt?.exchange) === String(params.exchange) &&
    sameNumberArray(condition.trigger_values || gtt?.trigger_values, params.trigger_values) &&
    orders.length === params.orders.length &&
    orders.every((order, index) => {
      const expected = params.orders[index];
      return String(order.transaction_type) === String(expected.transaction_type) &&
        String(order.product) === String(expected.product) &&
        String(order.order_type) === String(expected.order_type) &&
        Number(order.quantity) === Number(expected.quantity) &&
        Number(order.price) === Number(expected.price);
    });
}

async function recoverAmbiguousGTT(params) {
  try {
    const matches = (await kite.getGTTs() || []).filter(gtt => gttMatches(gtt, params));
    if (matches.length === 1) {
      const triggerId = matches[0].id ?? matches[0].trigger_id;
      if (triggerId != null) return { trigger_id: String(triggerId), recovered: true };
    }
  } catch (err) {
    logger.error({ event_type: 'ambiguous_gtt_reconcile_failed', ticker: params.tradingsymbol, err: err.message });
  }
  return null;
}

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
 * One ambiguity-safe submission, then the caller decides whether an unwind is
 * safe — the mandatory-stop discipline from
 * penny_executor.py (spec §7.2): a live position we cannot protect is worse than
 * no position.
 *
 * Returns structured broker truth. UNKNOWN is deliberately distinct from a
 * definitive rejection: an accepted-but-unobserved stop must not be followed
 * by a blind second stop or an unwind that could leave a future short.
 */
async function placeProtectiveStop(signal, stopPrice) {
  // [FILL-ANCHOR 2026-08-04] `stopPrice` is the fill-anchored stop, NOT
  // signal.stop_loss. Arming the signal's stop against a drifted fill is what
  // turned SUMICHEM's 2.80 of risk into 0.90 on 2026-08-03. Callers must pass
  // it explicitly; there is no fallback to the signal, because a silent
  // fallback is exactly the bug.
  if (!(stopPrice > 0)) {
    throw new RangeError(`placeProtectiveStop: invalid stopPrice ${stopPrice} for ${signal.ticker}`);
  }
  // SELL stop: snap the trigger DOWN so it never lands above the intended stop.
  const trigger = snapToTick(stopPrice, -1);
  // Limit 1% below the trigger: <= trigger (valid SELL SL) and marketable on
  // trigger (fills at market bid), so it behaves like a stop-market but is
  // API-legal without market protection.
  const limit = snapToTick(stopPrice * 0.99, -1);

  const tag = exitTag(signal.signal_id, 'SL');
  const params = {
    exchange: "NSE", tradingsymbol: signal.ticker, transaction_type: "SELL",
    quantity: signal.shares, product: "MIS", order_type: "SL",
    trigger_price: trigger, price: limit, validity: "DAY", tag
  };
  let res;
  try {
    res = await kite.placeOrder(params, { intent: "exit", channel: "momentum" });
  } catch (err) {
    logger.error({ event_type: 'mis_stop_submission_failed', ticker: signal.ticker, err: err.message });
    if (isDefinitivePlacementError(err)) return { state: 'FAILED', reason: err.message };
    res = await recoverAmbiguousPlacement(params, tag);
    if (!res) return { state: 'UNKNOWN', reason: err.message };
  }

  const orderId = res?.order_id;
  if (!orderId) {
    res = await recoverAmbiguousPlacement(params, tag);
    if (!res?.order_id) return { state: 'UNKNOWN', reason: 'broker returned no stop order id' };
  }
  const resolvedId = String(res.order_id);
  let lastReason = 'no broker history';
  for (let attempt = 0; attempt < 4; attempt++) {
    if (attempt > 0) await sleep(250);
    try {
      const state = orderFillState(latestOrder(await kite.getOrderHistory(resolvedId)), signal.shares);
      if (state.state === 'REJECTED' || state.state === 'CANCELLED') {
        return { state: 'FAILED', orderId: resolvedId, reason: state.reason || state.state };
      }
      if (state.state === 'COMPLETE') return { state: 'EXITED', orderId: resolvedId };
      if (['TRIGGER PENDING', 'OPEN'].includes(state.state)) {
        logger.info({ event_type: 'mis_stop_armed', ticker: signal.ticker, order_id: resolvedId, trigger, limit });
        return { state: 'ARMED', orderId: resolvedId };
      }
      lastReason = `unexpected stop status ${state.state}`;
    } catch (err) {
      lastReason = `stop reconciliation failed: ${err.message}`;
    }
  }
  return { state: 'UNKNOWN', orderId: resolvedId, reason: lastReason };
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
  const tag = exitTag(signal.signal_id, 'UW');
  const params = {
    exchange: "NSE", tradingsymbol: signal.ticker, transaction_type: "SELL",
    quantity: signal.shares, product: "MIS", order_type: "LIMIT", price: limit,
    validity: "DAY", tag
  };
  let res;
  try {
    res = await kite.placeOrder(params, { intent: "exit", channel: "momentum" });
  } catch (err) {
    logger.error({ event_type: 'mis_unwind_submission_failed', ticker: signal.ticker, err: err.message });
    if (isDefinitivePlacementError(err)) return { state: 'FAILED', reason: err.message };
    res = await recoverAmbiguousPlacement(params, tag);
    if (!res) return { state: 'UNKNOWN', reason: err.message };
  }
  if (!res?.order_id) {
    res = await recoverAmbiguousPlacement(params, tag);
    if (!res?.order_id) return { state: 'UNKNOWN', reason: 'broker returned no unwind order id' };
  }
  const orderId = String(res.order_id);
  const fill = await reconcilePlacedOrder(orderId, signal.shares, {
    attempts: 3, delayMs: 500, ticker: signal.ticker, product: 'MIS'
  });
  if (fill.state === 'COMPLETE' && fill.filledQuantity >= signal.shares) {
    logger.error({ event_type: 'mis_unprotected_flat_confirmed', ticker: signal.ticker, unwind_order_id: orderId });
    return { state: 'FLAT', orderId, fill };
  }
  if (fill.state === 'PARTIAL') return { state: 'PARTIAL', orderId, fill };
  if (fill.state === 'UNKNOWN' || fill.state === 'PARTIAL_OPEN') return { state: 'UNKNOWN', orderId, fill };
  return { state: 'FAILED', orderId, fill, reason: fill.reason || fill.state };
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
  if (!signal.signal_id) throw new ValidationError('signal_id is required before broker execution');
  const trackedSignal = signalsDb.prepare(`SELECT signal_id FROM received_signals WHERE signal_id = ?`).get(signal.signal_id);
  if (!trackedSignal) {
    throw new ValidationError(`Signal ${signal.signal_id} is not durably registered; broker order blocked.`);
  }
  
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

  // [FILL-ANCHOR 2026-08-04] Re-derive the risk geometry against the price we
  // can actually transact at, BEFORE committing size. The 2% drift gate above
  // bounds how far the market has moved, but 2% is roughly 4x a momentum stop:
  // inside that window the signal's stop can land anywhere from "already
  // breached" to "twice as far as intended". See risk-geometry.js.
  let geometry;
  try {
    geometry = resolveRiskDistance({
      signalClose:    signal.close,
      signalStop:     signal.stop_loss,
      price:          ltp,
      minStopPct:     config.MOMENTUM_MIN_STOP_PCT,
      minStopAtrMult: config.MOMENTUM_MIN_STOP_ATR_MULT,
      atr:            signal.atr_at_entry,
    });
  } catch (err) {
    throw new ValidationError(`${signal.ticker}: unusable risk geometry — ${err.message}`);
  }

  // If a floor widened the risk, the engine's share count now carries more
  // rupees than the approved budget. Cut size; never raise it.
  const sizedShares = sizeToRisk({
    originalShares: signal.shares,
    capitalAtRisk:  signal.capital_at_risk,
    risk:           geometry.risk,
  });
  if (sizedShares < 1) {
    throw new ValidationError(
      `${signal.ticker}: risk floor ${geometry.risk.toFixed(2)}/share exceeds the whole ` +
      `${signal.capital_at_risk} budget — no position is affordable at this price.`
    );
  }

  if (sizedShares !== signal.shares || geometry.source !== 'signal') {
    logger.info({
      event_type: 'fill_anchor_resized',
      ticker: signal.ticker,
      signal_close: signal.close, ltp,
      intended_risk: Number(geometry.intendedRisk.toFixed(2)),
      applied_risk:  Number(geometry.risk.toFixed(2)),
      risk_source:   geometry.source,
      shares_before: signal.shares, shares_after: sizedShares,
    });
  }
  signal = { ...signal, shares: sizedShares };

  // 3. Limit Order Execution
  // [FIX] Zerodha API rejects MARKET orders without market_protection.
  // Buy LIMIT at LTP + 0.5%, snapped UP to the nearest 0.10-rupee tick.
  // 0.10 satisfies both NSE tick sizes (0.05 and 0.10); stays inside the
  // 2% drift window already enforced above.
  const limitPrice = snapToTick(ltp * 1.005, 1);
  const product = isIntraday ? "MIS" : "CNC";
  // This evidence is deliberately immediately before a new entry. It is not a
  // promise that the broker will still accept the order, so later rejection
  // handling remains in place and no exit path consults this function.
  await preflightEntryMargin(limitPrice * signal.shares, {
    ticker: signal.ticker, product, quantity: signal.shares, price: limitPrice,
  });
  let orderResponse;
  const idempotencyTag = entryTag(signal.signal_id);
  const entryParams = {
    exchange: "NSE",
    tradingsymbol: signal.ticker,
    transaction_type: "BUY",
    quantity: signal.shares,
    product,
    order_type: "LIMIT",
    price: limitPrice,
    validity: "DAY",
    tag: idempotencyTag
  };
  try {
    // Never retry a non-idempotent submission. A network failure may happen
    // after broker acceptance; retrying would create a duplicate position.
    orderResponse = await kite.placeOrder(entryParams, { intent: "entry", channel: "momentum" });
  } catch (err) {
    if (err.retryable === false || ['OrderExecutionError', 'TokenExpiredError', 'ValidationError'].includes(err.name)) {
      throw new OrderExecutionError(`Order Placement Failed: ${err.message}`);
    }
    orderResponse = await recoverAmbiguousPlacement(entryParams, idempotencyTag);
    if (!orderResponse) {
      const unknown = new OrderExecutionError(
        `Order placement outcome UNKNOWN for ${signal.ticker}; no resubmission was made. Reconcile broker orders manually.`
      );
      unknown.positionHeld = true;
      unknown.outcomeUnknown = true;
      throw unknown;
    }
  }

  const orderId = orderResponse?.order_id;
  if (!orderId) {
    const unknown = new OrderExecutionError(
      `Broker returned no order id for ${signal.ticker}; placement outcome is UNKNOWN and was not retried.`
    );
    unknown.positionHeld = true;
    unknown.outcomeUnknown = true;
    throw unknown;
  }
  
  // Layer 2 Idempotency: Insert into DB immediately
  try {
    signalsDb.prepare(`
      INSERT INTO executed_orders (signal_id, ticker, order_id, order_type, shares, status, placed_at, sync_to_b, execution_state)
      VALUES (?, ?, ?, 'LIMIT', ?, 'PLACED', ?, 0, 'SUBMITTED')
    `).run(signal.signal_id, signal.ticker, orderId, signal.shares, new Date().toISOString());
  } catch (err) {
    // The INSERT can fail for two distinct reasons:
    //   a) signal_id FK/NOT NULL violation (momentum signal missing signal_id field)
    //   b) order_id UNIQUE violation (genuine replay attack, order already tracked)
    // Both are safety stops: the order is placed but we cannot track it safely.
    logger.error({ event_type: 'layer_2_idempotency_catch', orderId, err: err.message });
    const tracking = new OrderExecutionError('Order tracking failed after broker submission: ' + err.message);
    tracking.positionHeld = true;
    tracking.outcomeUnknown = true;
    throw tracking;
  }

  // 4. Fill Verification. An unconfirmed OPEN order is cancelled and then
  // reconciled; it is never assigned an estimated fill or given exit orders.
  const fill = await reconcilePlacedOrder(orderId, signal.shares, {
    ticker: signal.ticker, product: isIntraday ? 'MIS' : 'CNC',
  });
  if (fill.state === 'REJECTED') {
    signalsDb.prepare(`UPDATE executed_orders SET status = 'REJECTED', execution_state = 'REJECTED', notes = ? WHERE order_id = ?`)
      .run(fill.reason, orderId);
    throw new OrderExecutionError(`Order rejected by broker: ${fill.reason}`);
  }
  if (fill.state === 'CANCELLED') {
    signalsDb.prepare(`UPDATE executed_orders SET status = 'CANCELLED', execution_state = 'CANCELLED_UNFILLED', notes = ? WHERE order_id = ?`)
      .run('entry_cancelled_unfilled', orderId);
    throw new OrderExecutionError(`Order ${orderId} was cancelled without a fill.`);
  }
  if (fill.state === 'UNKNOWN' || fill.state === 'PARTIAL_OPEN') {
    signalsDb.prepare(`UPDATE executed_orders SET status = 'PLACED', execution_state = 'OUTCOME_UNKNOWN', notes = ? WHERE order_id = ?`)
      .run(`entry_outcome_unknown:${JSON.stringify(fill)}`, orderId);
    const unknown = new OrderExecutionError(
      `Order ${orderId} outcome is UNKNOWN after cancellation/reconciliation; no exits were armed. Reconcile manually before retrying.`
    );
    unknown.positionHeld = true;
    unknown.outcomeUnknown = true;
    throw unknown;
  }
  const isPartialFill = fill.state === 'PARTIAL';
  const fillPrice = fill.fillPrice;
  if (!(fillPrice > 0) || !(fill.filledQuantity > 0)) {
    const unknown = new OrderExecutionError(`Order ${orderId} reported a fill without valid quantity/price; no exits were armed.`);
    unknown.positionHeld = true;
    unknown.outcomeUnknown = true;
    throw unknown;
  }
  signal = { ...signal, shares: fill.filledQuantity };
  const finalNotes = isPartialFill ? `partial_fill:${fill.filledQuantity}` : "Executed via Telegram";

  // [FILL-ANCHOR 2026-08-04] Centre the geometry on the ACTUAL fill. The risk
  // distance was fixed pre-order (size is committed now, so it must not move);
  // only the anchor point changes. Everything downstream -- the resting stop,
  // the position row, momentum_exits' breakeven ratchet, the r_multiple in
  // trade_outcomes -- reads these levels rather than the signal's.
  const levels = anchorLevels({
    price:         fillPrice,
    risk:          geometry.risk,
    signalClose:   signal.close,
    signalStop:    signal.stop_loss,
    signalTarget1: signal.target_1,
    signalTarget2: signal.target_2,
  });

  logger.info({
    event_type: 'fill_anchored_levels',
    ticker: signal.ticker,
    signal_close: signal.close, fill_price: fillPrice,
    slippage_pct: Number((((fillPrice - signal.close) / signal.close) * 100).toFixed(3)),
    signal_stop: signal.stop_loss, anchored_stop: levels.stop,
    signal_t1:   signal.target_1,  anchored_t1:   levels.target1,
    risk_per_share: Number(geometry.risk.toFixed(2)),
    r_target: Number(levels.rTarget1.toFixed(2)),
  });

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
  let protectionFailure = null;

  if (isIntraday) {
    const stop = await placeProtectiveStop(signal, levels.stop);
    slOrderId = stop.orderId || null;

    if (stop.state === 'EXITED') {
      signalsDb.prepare(
        `UPDATE executed_orders SET status = 'CANCELLED', execution_state = 'FLAT_STOP_EXECUTED', entry_price = ?, shares = ?, filled_at = ?, sl_order_id = ?, notes = ? WHERE order_id = ?`
      ).run(fillPrice, signal.shares, new Date().toISOString(), slOrderId, 'protective_stop_filled_immediately', orderId);
      throw new OrderExecutionError(`${signal.ticker}: protective stop filled immediately; broker position is flat.`);
    }

    if (stop.state === 'UNKNOWN') {
      signalsDb.prepare(
        `UPDATE executed_orders SET status = 'COMPLETE', execution_state = 'OUTCOME_UNKNOWN', entry_price = ?, shares = ?, filled_at = ?, sl_order_id = ?, notes = ? WHERE order_id = ?`
      ).run(fillPrice, signal.shares, new Date().toISOString(), slOrderId, `protective_stop_unknown:${stop.reason || ''}`, orderId);
      const unknown = new OrderExecutionError(
        `${signal.ticker}: protective-stop outcome is UNKNOWN. No unwind was submitted because an unseen live stop could later oversell. Reconcile manually now.`
      );
      unknown.positionHeld = true;
      unknown.outcomeUnknown = true;
      throw unknown;
    }

    if (stop.state !== 'ARMED') {
      // Stop could not be placed. We refuse to hold an unprotected MIS position,
      // so flatten it. The buy has already filled, so distinguish the two exits:
      const unwind = await marketUnwind(signal, ltp);

      if (unwind.state === 'FLAT') {
        // Flat is asserted only after terminal broker history confirms the full
        // unwind quantity, never from a placement acknowledgement.
        signalsDb.prepare(
          `UPDATE executed_orders SET status = 'CANCELLED', execution_state = 'FLAT_CONFIRMED', notes = ? WHERE order_id = ?`
        ).run(`sl_failed_flatten_confirmed:${unwind.orderId}`, orderId);
        throw new OrderExecutionError(
          `${signal.ticker}: protective stop was rejected; full unwind was broker-confirmed. Position is flat.`
        );
      }

      // Stop failed and the unwind was not fully confirmed: the shares may
      // still be held with no stop. Never advertise this as flat/retryable.
      const unknownOutcome = unwind.state === 'UNKNOWN';
      // Do NOT mark this CANCELLED (that hides a real fill from the books) and do
      // NOT let the caller invite a retry (that would stack another naked buy).
      signalsDb.prepare(
        `UPDATE executed_orders SET status = 'COMPLETE', execution_state = ?, entry_price = ?, shares = ?, filled_at = ?, notes = ? WHERE order_id = ?`
      ).run(unknownOutcome ? 'OUTCOME_UNKNOWN' : 'HELD_UNPROTECTED', fillPrice, signal.shares, new Date().toISOString(),
        `sl_failed_unwind_${unwind.state.toLowerCase()}:${unwind.orderId || ''}`, orderId);
      try {
        await telegram.sendAlert(`🚨 ${signal.ticker}: protective stop failed and unwind is ${unwind.state}. Reconcile and flatten manually now.`);
      } catch (alertErr) {
        logger.error({ event_type: 'unprotected_alert_failed', ticker: signal.ticker, err: alertErr.message });
      }
      const held = new OrderExecutionError(
        `${signal.ticker}: HOLDING ${signal.shares} shares with NO protective stop — ` +
        `the unwind was not fully confirmed. FLATTEN THIS POSITION MANUALLY NOW. Do NOT retry the button.`
      );
      held.positionHeld = true;
      held.outcomeUnknown = unknownOutcome;
      throw held;
    }
  } else {
    // A single two-leg GTT is broker-side OCO: once either full-quantity SELL
    // fires, Kite cancels the sibling. Two independent single GTTs can both
    // execute and turn a long position into an accidental short.
    const gttParams = {
        trigger_type: "two-leg",
        tradingsymbol: signal.ticker,
        exchange: "NSE",
        trigger_values: [levels.stop, levels.target1],
        last_price: ltp,
        orders: [
          {
          transaction_type: "SELL",
          quantity: signal.shares,
          order_type: "LIMIT",
          product: "CNC",
          price: snapToTick(levels.stop * 0.998, -1)
          },
          {
          transaction_type: "SELL",
          quantity: signal.shares,
          order_type: "LIMIT",
          product: "CNC",
          price: snapToTick(levels.target1 * 0.998, -1)
          }
        ]
      };
    try {
      let gttRes;
      try {
        gttRes = await kite.placeGTT(gttParams, { intent: "exit", channel: "momentum" });
      } catch (err) {
        if (isDefinitivePlacementError(err)) throw err;
        gttRes = await recoverAmbiguousGTT(gttParams);
        if (!gttRes) {
          protectionFailure = { state: 'OUTCOME_UNKNOWN', reason: err.message };
        }
      }
      if (!protectionFailure && !gttRes?.trigger_id) {
        gttRes = await recoverAmbiguousGTT(gttParams);
        if (!gttRes?.trigger_id) protectionFailure = { state: 'OUTCOME_UNKNOWN', reason: 'broker returned no GTT id' };
      }
      if (!protectionFailure) {
        gttStopId = String(gttRes.trigger_id);
        gttTargetId = gttStopId;
      }
    } catch (err) {
      logger.error({ event_type: 'gtt_placement_error', err: err.message });
      protectionFailure = { state: 'HELD_UNPROTECTED', reason: err.message };
    }
    if (protectionFailure) {
      try {
        await telegram.sendAlert(`🚨 CNC protection ${protectionFailure.state} for ${signal.ticker} (Order ${orderId}). Position remains locked; reconcile/place a manual exit.`);
      } catch (alertErr) {
        logger.error({ event_type: 'gtt_alert_failed', ticker: signal.ticker, err: alertErr.message });
      }
    }
  }


  // Update DB with Fill + protective orders
  const persistedNotes = protectionFailure
    ? `${finalNotes};protection:${protectionFailure.state}:${protectionFailure.reason}`
    : finalNotes;
  signalsDb.prepare(`
    UPDATE executed_orders
    SET status = 'COMPLETE', execution_state = ?, entry_price = ?, shares = ?, filled_at = ?, gtt_stop_id = ?, gtt_target_id = ?, sl_order_id = ?, notes = ?
    WHERE order_id = ?
  `).run(protectionFailure?.state || 'FILLED_PROTECTED', fillPrice, signal.shares, new Date().toISOString(), gttStopId, gttTargetId, slOrderId,
    persistedNotes, orderId);

    // 6. Sync to Container B
  const syncPayload = {
    ticker: signal.ticker,
    exchange: "NSE",
    entry_price: fillPrice,
    shares: signal.shares,
    stop_loss: levels.stop,
    target_1: levels.target1,
    target_2: levels.target2,
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
    // [THESIS-EXIT 2026-08-04] The VWAP this breakout was measured against.
    // The engine's exit ladder uses it to ask whether the SETUP is still true
    // rather than whether a timer expired -- see momentum_exits. Forward null
    // rather than 0 when absent; 0 would read as "price is above VWAP" and
    // defeat every fast stop.
    vwap_at_entry: signal.vwap ?? null,
    order_id: String(orderId),
    gtt_stop_id: gttStopId ? String(gttStopId) : null,
    gtt_target_id: gttTargetId ? String(gttTargetId) : null,
    // The engine's intraday monitor cancels this SL-M before it takes a target
    // or a trail exit, so it must know the id.
    sl_order_id: slOrderId,
    notes: persistedNotes
  };


  try {
    await withRetry(() => syncToEngine(syncPayload), 3, 5000);
    signalsDb.prepare(`UPDATE executed_orders SET sync_to_b = 1 WHERE order_id = ?`).run(orderId);
  } catch (err) {
    logger.error({ event_type: 'sync_back_failed', err: err.message, orderId });
    signalsDb.prepare(`UPDATE executed_orders SET sync_to_b = 2 WHERE order_id = ?`).run(orderId);
    telegram.sendAlert(`🚨 Order placed (#${orderId}) but sync to quant engine failed entirely. Manual registration required at dashboard.`);
  }

  if (protectionFailure) {
    const held = new OrderExecutionError(
      `${signal.ticker}: CNC position is not confirmed protected (${protectionFailure.state}). Do NOT retry; reconcile exits manually.`
    );
    held.positionHeld = true;
    held.outcomeUnknown = protectionFailure.state === 'OUTCOME_UNKNOWN';
    throw held;
  }

  // [FILL-ANCHOR 2026-08-04] Return what was actually armed, not what was
  // signalled. index.js persists this into received_signals.payload_json, and a
  // payload that still carries the signal's stop would make every post-hoc
  // audit reconstruct the wrong R.
  return {
    orderId, fillPrice, gttStopId, gttTargetId,
    shares:    signal.shares,
    stop_loss: levels.stop,
    target_1:  levels.target1,
    target_2:  levels.target2,
    risk_per_share: Number(geometry.risk.toFixed(2)),
  };
}

module.exports = {
  executeSignal, syncToEngine, snapToTick,
  finiteNonNegative, usableEntryMargin, requiredOrderMargin, preflightEntryMargin,
  entryTag, exitTag, orderFillState, reconcilePlacedOrder, recoverAmbiguousPlacement,
  gttMatches, recoverAmbiguousGTT, placeProtectiveStop, marketUnwind,
};
