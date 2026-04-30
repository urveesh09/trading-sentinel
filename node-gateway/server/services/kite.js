const { KiteConnect } = require('kiteconnect');
const config = require('../config');
const tokenStore = require('./token-store');
const { TokenExpiredError, OrderExecutionError } = require('../utils/errors');
const { logger } = require('../middleware/logger');

const kite = new KiteConnect({
  api_key: config.ZERODHA_API_KEY
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
    throw err; // Network or Order exceptions handled by retry logic in executor
  }
}

module.exports = {
  getLoginURL: () => kite.getLoginURL(),
  
  generateSession: async (requestToken, apiSecret) => {
    const response = await kite.generateSession(requestToken, apiSecret);
    return response.access_token;
  },
  
  getLTP: async (instruments) => {
    let lastErr;
    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        const res = await withKite('getLTP', () => kite.getLTP(instruments));

        // SDK silently resolves undefined when response.data.data is absent from
        // Zerodha's JSON body (e.g. {"status":"success"} with no data field).
        if (res == null) {
          throw new OrderExecutionError(
            `Zerodha getLTP returned no data for [${instruments.join(', ')}]`
          );
        }

        // SDK resolves with { error_type, message } instead of throwing when the
        // response Content-Type header doesn't exactly match "application/json"
        // (e.g. "application/json; charset=utf-8"). This is a known v3.2.0 SDK quirk.
        if (res.error_type) {
          throw new OrderExecutionError(
            `Zerodha getLTP SDK error [${res.error_type}]: ${res.message}`
          );
        }

        return res;
      } catch (err) {
        // Token expiry requires user re-login — retrying is pointless.
        if (err.name === 'TokenExpiredError') throw err;

        lastErr = err;
        if (attempt < 3) {
          logger.warn({
            event_type: 'ltp_retry',
            instruments,
            attempt,
            reason: err.message
          }, `getLTP attempt ${attempt} failed, retrying in ${500 * attempt}ms`);
          await new Promise(resolve => setTimeout(resolve, 500 * attempt));
        }
      }
    }
    logger.error({
      event_type: 'ltp_all_retries_failed',
      instruments,
      reason: lastErr.message
    }, 'getLTP failed after 3 attempts');
    throw lastErr;
  },
  
  placeOrder: async (params) => {
    return await withKite('placeOrder', () => kite.placeOrder('regular', params));
  },
  
  getOrderHistory: async (orderId) => {
    return await withKite('getOrderHistory', () => kite.getOrderHistory(orderId));
  },
  
  placeGTT: async (params) => {
    return await withKite('placeGTT', () => kite.placeGTT(params));
  }
};
