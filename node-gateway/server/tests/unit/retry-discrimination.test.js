/**
 * [MED-004 / ROADMAP-4.4 2026-07-13] withRetry must not retry a definitive
 * rejection.
 *
 * This matters because withRetry sits on the ORDER PLACEMENT path. Pre-fix it
 * retried every error on a fixed delay, so when Zerodha rejected an order
 * outright -- bad quantity, dead token -- the gateway obediently re-submitted
 * the identical rejected order with the identical dead token, and only then
 * told the operator it had failed. It cannot succeed, and it burns rate-limit
 * budget in the seconds that matter.
 */
const {
  withRetry,
  isRetryableError,
  backoffMs,
} = require('../../utils/retry');

const {
  TokenExpiredError,
  OrderExecutionError,
  ValidationError,
  PriceDriftError,
} = require('../../utils/errors');

describe('isRetryableError', () => {
  test.each([
    ['TokenExpiredError', new TokenExpiredError()],
    ['OrderExecutionError', new OrderExecutionError('Zerodha rejected')],
    ['ValidationError', new ValidationError()],
    ['PriceDriftError', new PriceDriftError()],
  ])('%s is NOT retryable (definitive rejection)', (_name, err) => {
    expect(isRetryableError(err)).toBe(false);
  });

  test('classifies by identity, NOT by AppError.statusCode', () => {
    // The trap: OrderExecutionError carries statusCode 502, because that is
    // what we would show a CLIENT. A "retry 5xx" rule would therefore retry
    // precisely the rejected order we most need to STOP retrying.
    const err = new OrderExecutionError('rejected');
    expect(err.statusCode).toBe(502);
    expect(isRetryableError(err)).toBe(false);
  });

  test('upstream 5xx is retryable, upstream 4xx is not', () => {
    const down = Object.assign(new Error('Engine returned 503'), { upstreamStatus: 503 });
    const bad = Object.assign(new Error('Engine returned 422'), { upstreamStatus: 422 });
    expect(isRetryableError(down)).toBe(true);
    expect(isRetryableError(bad)).toBe(false);
  });

  test('429 is retryable even though it is 4xx', () => {
    const limited = Object.assign(new Error('rate limited'), { upstreamStatus: 429 });
    expect(isRetryableError(limited)).toBe(true);
  });

  test('unknown/bare errors default to retryable', () => {
    // kite.js deliberately re-throws the Kite SDK's bare NetworkException /
    // OrderException for the executor's retry to handle. Defaulting these to
    // no-retry would quietly break the transient-failure path.
    expect(isRetryableError(new Error('ECONNRESET'))).toBe(true);
  });
});

describe('withRetry fails fast on definitive rejections', () => {
  test('a rejected ORDER is submitted exactly once', async () => {
    const placeOrder = jest.fn()
      .mockRejectedValue(new OrderExecutionError('Invalid quantity'));

    await expect(withRetry(placeOrder, 3, 1)).rejects.toThrow('Invalid quantity');

    // THE POINT. Pre-fix this was 4 (1 + 3 retries) -- four identical
    // rejected orders sent to the broker.
    expect(placeOrder).toHaveBeenCalledTimes(1);
  });

  test('a dead token is not retried', async () => {
    const fn = jest.fn().mockRejectedValue(new TokenExpiredError());
    await expect(withRetry(fn, 3, 1)).rejects.toThrow();
    expect(fn).toHaveBeenCalledTimes(1);
  });

  test('but transient failures ARE still retried and can succeed', async () => {
    const fn = jest.fn()
      .mockRejectedValueOnce(new Error('ECONNRESET'))
      .mockRejectedValueOnce(new Error('ECONNRESET'))
      .mockResolvedValue({ order_id: 'OK' });

    await expect(withRetry(fn, 3, 1)).resolves.toEqual({ order_id: 'OK' });
    expect(fn).toHaveBeenCalledTimes(3);
  });
});

describe('backoff', () => {
  test('grows exponentially', () => {
    // Jitter is +/-20%, so assert on bounds rather than exact values.
    const a1 = backoffMs(1000, 1);
    const a2 = backoffMs(1000, 2);
    const a3 = backoffMs(1000, 3);
    expect(a1).toBeGreaterThanOrEqual(800);
    expect(a1).toBeLessThanOrEqual(1200);
    expect(a2).toBeGreaterThanOrEqual(1600);
    expect(a2).toBeLessThanOrEqual(2400);
    expect(a3).toBeGreaterThanOrEqual(3200);
    expect(a3).toBeLessThanOrEqual(4800);
  });

  test('is capped', () => {
    expect(backoffMs(1000, 20, 5000)).toBeLessThanOrEqual(6000);
  });

  test('a delay FUNCTION opts out of backoff entirely', async () => {
    // Backward compat: callers that pass a function own the schedule.
    const delays = [];
    const fn = jest.fn().mockRejectedValue(new Error('boom'));
    await expect(
      withRetry(fn, 2, (attempt) => { delays.push(attempt); return 1; })
    ).rejects.toThrow('boom');
    expect(delays).toEqual([1, 2]);
  });
});
