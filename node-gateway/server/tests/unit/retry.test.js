/**
 * Tests for utils/retry.js - retry logic.
 */
const { withRetry } = require('../../utils/retry');

describe('withRetry()', () => {
  test('returns result on first successful call', async () => {
    const fn = jest.fn().mockResolvedValue('success');
    const result = await withRetry(fn);
    expect(result).toBe('success');
    expect(fn).toHaveBeenCalledTimes(1);
  });

  test('retries on failure and succeeds', async () => {
    const fn = jest.fn()
      .mockRejectedValueOnce(new Error('fail1'))
      .mockResolvedValue('recovered');
    
    const result = await withRetry(fn, 3, 10); // short delay for tests
    expect(result).toBe('recovered');
    expect(fn).toHaveBeenCalledTimes(2);
  });

  test('exhausts all retries and throws', async () => {
    const fn = jest.fn().mockRejectedValue(new Error('always fails'));
    
    await expect(withRetry(fn, 2, 10)).rejects.toThrow('always fails');
    expect(fn).toHaveBeenCalledTimes(3); // initial + 2 retries
  });

  test('respects retry count', async () => {
    const fn = jest.fn().mockRejectedValue(new Error('fail'));
    
    await expect(withRetry(fn, 0, 10)).rejects.toThrow('fail');
    expect(fn).toHaveBeenCalledTimes(1); // 0 retries = 1 attempt only
  });

  test('accepts delay as a function', async () => {
    const fn = jest.fn()
      .mockRejectedValueOnce(new Error('fail'))
      .mockResolvedValue('ok');
    
    const delayFn = jest.fn().mockReturnValue(10);
    const result = await withRetry(fn, 3, delayFn);
    
    expect(result).toBe('ok');
    expect(delayFn).toHaveBeenCalledWith(1); // called with attempt number
  });
});
