const { KiteConnect } = require('kiteconnect');
const axios = require('axios');
const config = require('../config');
const tokenStore = require('./token-store');
const { TokenExpiredError, OrderExecutionError } = require('../utils/errors');
const { logger } = require('../middleware/logger');
const haltSwitch = require('./halt-switch');

const KITE_API_ROOT = process.env.KITE_BASE_URL || 'https://api.kite.trade';

const kite = new KiteConnect({
  api_key: config.ZERODHA_API_KEY,
  root: KITE_API_ROOT,
});

// TOKEN BUCKET RATE LIMITER: Max 5 req/sec
class RateLimiter {
  constructor(capacity, fillPerSecond) {
    this.capacity = capacity;
    this.tokens = capacity;
    this.fillPerSecond = fillPerSecond;
    this.lastFill = Date.now();
  }
  async waitForToken() {
    return new Promise(resolve => {
      const tryConsume = () => {
        const now = Date.now();
        const deltaSec = (now - this.lastFill) / 1000;
        this.tokens = Math.min(this.capacity, this.tokens + deltaSec * this.fillPerSecond);
        this.lastFill = now;

        if (this.tokens >= 1) {
          this.tokens -= 1;
          resolve();
        } else {
          setTimeout(tryConsume, 200);
        }
      };
      tryConsume();
    });
  }
}
const kiteLimiter = new RateLimiter(5, 5);

// SDK WRAPPER WITH ERROR TRANSLATION
async function withKite(apiCallName, fn) {
  if (!tokenStore.isValid()) {
    throw new TokenExpiredError();
  }
  kite.setAccessToken(tokenStore.getToken());
  
  await kiteLimiter.waitForToken();
  
  try {
    return await fn();
  } catch (err) {
    if (err.name === 'TokenException') {
      tokenStore.markExpired();
      logger.error({ event_type: 'token_exception' }, 'Zerodha token expired mid-session');
      throw new TokenExpiredError();
    }
    if (err.name === 'InputException') {
      logger.error({ event_type: 'kite_input_error', reason: err.message }, 'Kite Input Exception');
      throw new OrderExecutionError(err.message);
    }
    const message = String(err && err.message || '');
    const isOrderApi = apiCallName === 'placeOrder' || apiCallName === 'placeGTT';
    const staticIpDenied = isOrderApi && (err.name === 'PermissionException' ||
      (/\b(?:401|403)\b/.test(message) && /(?:static\s*ip|ip.+not allowed|allow.?list)/i.test(message)) ||
      /(?:static\s*ip|ip.+not allowed to place orders)/i.test(message));
    if (staticIpDenied) {
      let firstTrip = false;
      try {
        firstTrip = haltSwitch.tripGlobal({
          by: 'kite_order_authorization',
          reason: `Kite rejected ${apiCallName}: ${message || err.name}`,
        });
      } catch (_) {
        // tripGlobal logs and fails closed; preserve the broker error below.
      }
      logger.error({
        event_type: 'kite_order_authorization_denied', api: apiCallName,
        reason: message, global_halt_new: firstTrip,
      }, 'Kite order authorization rejected; global entry halt is active');
      if (firstTrip) {
        // Lazy import avoids coupling broker initialization to Telegram startup.
        try {
          await require('./telegram').sendAlert(
            `🚨 LIVE ORDER AUTHORIZATION FAILED (${apiCallName}). Global entries are halted. ` +
            `Verify Zerodha static-IP authorization before re-arming.\n${message}`
          );
        } catch (alertErr) {
          logger.error({ event_type: 'kite_authorization_alert_failed', reason: alertErr.message });
          // The durable HALT file remains the primary safety notification.
        }
      }
      const denied = new OrderExecutionError(`Kite order authorization denied: ${message || err.name}`);
      denied.retryable = false;
      denied.authorizationDenied = true;
      throw denied;
    }
    throw err; // Network or Order exceptions handled by retry logic in executor
  }
}

/**
 * [HALT 2026-08-05] Kill-switch gate, applied at the single broker chokepoint.
 *
 * Every live order in node-gateway funnels through placeOrder/placeGTT, so
 * gating here is exhaustive by construction — a future call site cannot route
 * around it without adding a new Kite method.
 */
function gateOrder(apiCallName, opts) {
  const intent = opts && opts.intent;
  if (intent !== 'entry' && intent !== 'exit') {
    throw new OrderExecutionError(
      `${apiCallName}: opts.intent must be 'entry' or 'exit' (got ${JSON.stringify(intent)})`
    );
  }
  if (intent === 'exit') return; // exits are never halt-gated

  try {
    haltSwitch.assertNotHalted((opts && opts.channel) || null);
  } catch (err) {
    if (err.name === 'TradingHaltedError') {
      logger.error({
        event_type: 'kite_order_blocked_by_halt',
        api: apiCallName,
        scope: err.attribution.scope,
        by: err.attribution.by,
        reason: err.attribution.reason,
      }, 'order blocked by halt sentinel');
      throw new OrderExecutionError(err.message);
    }
    throw err;
  }
}

module.exports = {
  getLoginURL: () => kite.getLoginURL(),
  
  generateSession: async (requestToken, apiSecret) => {
    const response = await kite.generateSession(requestToken, apiSecret);
    return response.access_token;
  },
  
  getLTP: async (instruments) => {
    // Bypass the kiteconnect SDK for LTP — the SDK's response interceptor silently
    // returns response.data.data which is undefined when Zerodha omits the data
    // field or returns an unexpected Content-Type. Direct axios gives us full
    // response visibility and proper error handling.
    if (!tokenStore.isValid()) throw new TokenExpiredError();
    await kiteLimiter.waitForToken();

    const accessToken = tokenStore.getToken();
    let lastErr;
    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        // Zerodha expects repeated params without brackets: i=NSE:A&i=NSE:B
        // Axios default serialises arrays as i[]=NSE:A which Zerodha rejects.
        const searchParams = new URLSearchParams();
        instruments.forEach(inst => searchParams.append('i', inst));

        const response = await axios.get(`${KITE_API_ROOT}/quote/ltp?${searchParams.toString()}`, {
          headers: {
            'X-Kite-Version': '3',
            'Authorization': `token ${config.ZERODHA_API_KEY}:${accessToken}`,
          },
          timeout: 7000,
        });

        // Log the raw response so we can diagnose what Zerodha actually sends
        logger.info({
          event_type: 'ltp_raw_response',
          instruments,
          statusCode: response.status,
          contentType: response.headers['content-type'],
          bodyStatus: response.data?.status,
          hasDataField: response.data != null && 'data' in response.data,
          dataIsNull: response.data?.data == null,
          zerodhaErrorType: response.data?.error_type ?? null,
          zerodhaErrorMessage: response.data?.message ?? null,
        });

        // Zerodha can return 200 OK with an error body (e.g. token expired mid-call)
        if (response.data?.error_type) {
          if (response.data.error_type === 'TokenException') {
            tokenStore.markExpired();
            logger.error({ event_type: 'token_exception' }, 'Zerodha token expired mid-session');
            throw new TokenExpiredError();
          }
          throw new OrderExecutionError(
            `Zerodha LTP error [${response.data.error_type}]: ${response.data.message}`
          );
        }

        const ltpData = response.data?.data;
        if (!ltpData) {
          throw new OrderExecutionError(
            `Zerodha getLTP returned empty/null data for [${instruments.join(', ')}]`
          );
        }

        return ltpData;
      } catch (err) {
        if (err.name === 'TokenExpiredError') throw err;

        // Handle Zerodha HTTP 4xx/5xx errors
        if (err.response) {
          const respData = err.response.data;
          if (respData?.error_type === 'TokenException' || err.response.status === 403) {
            tokenStore.markExpired();
            logger.error({ event_type: 'token_exception' }, 'Zerodha token expired mid-session');
            throw new TokenExpiredError();
          }
          lastErr = new OrderExecutionError(
            `Zerodha LTP HTTP ${err.response.status}: ${respData?.message || err.message}`
          );
        } else {
          lastErr = err instanceof OrderExecutionError ? err : new OrderExecutionError(err.message);
        }

        if (attempt < 3) {
          logger.warn({
            event_type: 'ltp_retry',
            instruments,
            attempt,
            reason: lastErr.message,
          }, `getLTP attempt ${attempt} failed, retrying in ${500 * attempt}ms`);
          await new Promise(resolve => setTimeout(resolve, 500 * attempt));
        }
      }
    }
    logger.error({
      event_type: 'ltp_all_retries_failed',
      instruments,
      reason: lastErr.message,
    }, 'getLTP failed after 3 attempts');
    throw lastErr;
  },
  
  /**
   * @param {object} params Kite order params.
   * @param {{intent: 'entry'|'exit', channel?: string}} opts REQUIRED.
   *
   * [HALT 2026-08-05] `opts.intent` is the kill-switch boundary and has no
   * default. Entries are gated; exits (protective stops, unwinds) never are,
   * because refusing an exit during a halt strands a live position with no
   * stop. Omitting it throws rather than guessing — both directions of that
   * guess are expensive, so neither is worth defaulting to.
   */
  placeOrder: async (params, opts) => {
    gateOrder('placeOrder', opts);
    return await withKite('placeOrder', () => kite.placeOrder('regular', params));
  },

  getOrderHistory: async (orderId) => {
    return await withKite('getOrderHistory', () => kite.getOrderHistory(orderId));
  },

  // Reconciliation primitives. These are deliberately exposed through the
  // same authenticated/rate-limited wrapper as placement: callers use them
  // after an ambiguous response or before deciding that an order is terminal.
  getOrders: async () => {
    return await withKite('getOrders', () => kite.getOrders());
  },

  getPositions: async () => {
    return await withKite('getPositions', () => kite.getPositions());
  },

  getGTTs: async () => {
    return await withKite('getGTTs', () => kite.getGTTs());
  },

  deleteGTT: async (triggerId) => {
    return await withKite('deleteGTT', () => kite.deleteGTT(triggerId));
  },

  cancelOrder: async (orderId) => {
    return await withKite('cancelOrder', () => kite.cancelOrder('regular', orderId));
  },

  /** @param {{intent: 'entry'|'exit', channel?: string}} opts REQUIRED. See placeOrder. */
  placeGTT: async (params, opts) => {
    gateOrder('placeGTT', opts);
    return await withKite('placeGTT', () => kite.placeGTT(params));
  }
};
