const { KiteConnect } = require('kiteconnect');
const axios = require('axios');
const config = require('../config');
const tokenStore = require('./token-store');
const { TokenExpiredError, OrderExecutionError } = require('../utils/errors');
const { logger } = require('../middleware/logger');

const KITE_API_ROOT = 'https://api.kite.trade';

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
        const response = await axios.get(`${KITE_API_ROOT}/quote/ltp`, {
          params: { i: instruments },
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
