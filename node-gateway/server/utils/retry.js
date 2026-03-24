/**
 * Wraps an async function with retry logic.
 * @param {Function} fn - Async function to execute
 * @param {number} retries - Maximum number of retries
 * @param {number|Function} delay - Milliseconds to wait, or function returning ms
 */
async function withRetry(fn, retries = 3, delay = 1500) {
  let attempt = 0;
  while (attempt <= retries) {
    try {
      return await fn();
    } catch (error) {
      attempt++;
      if (attempt > retries) {
        throw error;
      }
      const waitTime = typeof delay === 'function' ? delay(attempt) : delay;
      await new Promise((resolve) => setTimeout(resolve, waitTime));
    }
  }
}

module.exports = { withRetry };
