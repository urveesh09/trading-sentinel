/**
 * Retry with exponential backoff and error discrimination.
 *
 * [MED-004 / ROADMAP-4.4 2026-07-13]
 *
 * The previous version retried EVERY error on a fixed 1.5s delay, and it sits
 * on the ORDER PLACEMENT path (executor.js). Both halves of that are wrong:
 *
 *   1. No discrimination. kite.js already translates Zerodha's failures:
 *      TokenException -> TokenExpiredError, InputException ->
 *      OrderExecutionError. Both are DEFINITIVE rejections -- the token is
 *      dead, or the order parameters are invalid. Retrying re-submits the
 *      identical rejected order with the identical dead token. It cannot
 *      succeed; it just delays the failure the operator is waiting on and
 *      burns Zerodha rate-limit budget during the seconds that matter.
 *
 *   2. No backoff. A fixed delay against a struggling upstream is the
 *      classic way to keep it struggling.
 *
 * Classification is by error IDENTITY, deliberately, NOT by HTTP status:
 * AppError.statusCode is the code we would show a CLIENT, not the code the
 * upstream returned. OrderExecutionError carries 502 -- a naive "retry 5xx"
 * rule would retry exactly the rejected order we most need to stop retrying.
 */

// Definitive rejections. Retrying these cannot change the outcome.
const NON_RETRYABLE = new Set([
  'TokenExpiredError',    // token is dead; only a re-login fixes it
  'OrderExecutionError',  // Zerodha rejected the order (InputException)
  'ValidationError',      // the request itself is malformed
  'PriceDriftError',      // price moved; the signal must be re-evaluated
  'MarketClosedError',    // will not become open by trying again
  'StaleSignalError',
  'DuplicateSignalError',
  'ReplayAttackError',
]);

/**
 * Retry network faults and genuine upstream 5xx / 429. Anything we can
 * positively identify as a definitive rejection fails fast.
 *
 * Unknown errors default to RETRYABLE: the Kite SDK throws bare
 * NetworkException / OrderException objects for transient trouble, and
 * kite.js deliberately re-throws those raw ("handled by retry logic in
 * executor"). Defaulting to no-retry would quietly break that path.
 */
function isRetryableError(err) {
  if (!err) return false;
  if (err.retryable === true) return true;
  if (err.retryable === false) return false;

  if (NON_RETRYABLE.has(err.name)) return false;

  // `upstreamStatus` is what the REMOTE returned (set it at the call site).
  const upstream = err.upstreamStatus;
  if (typeof upstream === 'number') {
    if (upstream === 429) return true;          // rate limited -- back off, retry
    if (upstream >= 400 && upstream < 500) return false;  // our fault; retrying won't help
    return upstream >= 500;
  }

  return true;
}

/**
 * Exponential backoff with jitter.
 *
 * Jitter matters here even with a single caller: the order path and the
 * sync-back path can be retrying against the same upstream at the same time,
 * and identical delays make them collide on every attempt.
 */
function backoffMs(baseDelay, attempt, maxDelay = 30_000) {
  const exponential = Math.min(baseDelay * 2 ** (attempt - 1), maxDelay);
  const jitter = exponential * 0.2 * (Math.random() * 2 - 1); // +/-20%
  return Math.max(0, Math.round(exponential + jitter));
}

/**
 * @param {Function} fn        async function to execute
 * @param {number}   retries   max retries (attempts = retries + 1)
 * @param {number|Function} delay  base ms, or a function(attempt) -> ms
 *                                 (a function opts OUT of backoff: it is
 *                                 given full control of the schedule)
 * @param {Object}   [options]
 * @param {Function} [options.isRetryable]  override the classifier
 * @param {Function} [options.onRetry]      (err, attempt, waitMs) side-channel for logging
 */
async function withRetry(fn, retries = 3, delay = 1500, options = {}) {
  const retryable = options.isRetryable || isRetryableError;
  let attempt = 0;

  while (attempt <= retries) {
    try {
      return await fn();
    } catch (error) {
      attempt++;

      // Fail fast on a definitive rejection -- do NOT burn the remaining
      // attempts (or, on the order path, re-submit a rejected order).
      if (!retryable(error)) throw error;

      if (attempt > retries) throw error;

      const waitTime = typeof delay === 'function'
        ? delay(attempt)
        : backoffMs(delay, attempt);

      if (options.onRetry) options.onRetry(error, attempt, waitTime);

      await new Promise((resolve) => setTimeout(resolve, waitTime));
    }
  }
}

module.exports = { withRetry, isRetryableError, backoffMs, NON_RETRYABLE };
