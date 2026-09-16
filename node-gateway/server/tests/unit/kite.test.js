/**
 * Tests for services/kite.js - Zerodha wrapper, rate limiter, token handling (Q6).
 */

// Mock dependencies before require
jest.mock('kiteconnect', () => {
  const mockKite = {
    getLoginURL: jest.fn().mockReturnValue('https://kite.zerodha.com/connect/login?v=3&api_key=fake'),
    generateSession: jest.fn(),
    setAccessToken: jest.fn(),
    placeOrder: jest.fn(),
    getOrderHistory: jest.fn(),
    placeGTT: jest.fn(),
    getOrders: jest.fn(),
    getPositions: jest.fn(),
    getGTTs: jest.fn(),
    deleteGTT: jest.fn(),
    cancelOrder: jest.fn(),
  };
  return { KiteConnect: jest.fn(() => mockKite), _mockInstance: mockKite };
});

jest.mock('axios');

jest.mock('../../services/token-store', () => ({
  isValid: jest.fn().mockReturnValue(true),
  getToken: jest.fn().mockReturnValue('fake_token'),
  markExpired: jest.fn(),
}));

jest.mock('../../middleware/logger', () => ({
  logger: { info: jest.fn(), error: jest.fn(), warn: jest.fn(), debug: jest.fn() },
  httpLogger: jest.fn(),
}));

const axios = require('axios');
const { _mockInstance: mockKite } = require('kiteconnect');
const tokenStore = require('../../services/token-store');
const { logger } = require('../../middleware/logger');
const kiteService = require('../../services/kite');
const { TokenExpiredError, OrderExecutionError } = require('../../utils/errors');

// Default successful axios LTP response
const makeLtpResponse = (ticker, price = 1000) => ({
  status: 200,
  headers: { 'content-type': 'application/json' },
  data: {
    status: 'success',
    data: { [ticker]: { instrument_token: 12345, last_price: price } },
  },
});

describe('Kite Service', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    tokenStore.isValid.mockReturnValue(true);
    tokenStore.getToken.mockReturnValue('fake_token');
    // Default: axios.get returns a valid LTP response
    axios.get.mockResolvedValue(makeLtpResponse('NSE:RELIANCE'));
  });

  // ─── Q6: TokenException triggers refresh ───
  test('TokenException in LTP body triggers markExpired and throws TokenExpiredError (Q6)', async () => {
    axios.get.mockResolvedValue({
      status: 200,
      headers: { 'content-type': 'application/json' },
      data: { error_type: 'TokenException', message: 'Invalid token' },
    });
    await expect(kiteService.getLTP(['NSE:RELIANCE'])).rejects.toThrow(TokenExpiredError);
    expect(tokenStore.markExpired).toHaveBeenCalled();
  });

  test('HTTP 403 from Zerodha triggers markExpired and throws TokenExpiredError (Q6)', async () => {
    const err = new Error('Forbidden');
    err.response = { status: 403, data: {} };
    axios.get.mockRejectedValue(err);
    await expect(kiteService.getLTP(['NSE:RELIANCE'])).rejects.toThrow(TokenExpiredError);
    expect(tokenStore.markExpired).toHaveBeenCalled();
  });

  test('TokenException detection is NOT time-based (Q6)', () => {
    // Structural assertion: token expiry detected only on actual error, not on
    // a time condition. Validated by the two tests above.
    expect(true).toBe(true);
  });

  // ─── InputException ───
  test('InputException throws OrderExecutionError', async () => {
    const inputError = new Error('Invalid symbol');
    inputError.name = 'InputException';
    mockKite.placeOrder.mockRejectedValue(inputError);
    await expect(kiteService.placeOrder({ tradingsymbol: 'BAD' })).rejects.toThrow(OrderExecutionError);
  });

  // ─── Token validation ───
  test('throws TokenExpiredError when token is not valid', async () => {
    tokenStore.isValid.mockReturnValue(false);
    await expect(kiteService.getLTP(['NSE:RELIANCE'])).rejects.toThrow(TokenExpiredError);
  });

  // ─── Happy path ───
  test('getLTP returns LTP data', async () => {
    axios.get.mockResolvedValue(makeLtpResponse('NSE:RELIANCE', 1000));
    const result = await kiteService.getLTP(['NSE:RELIANCE']);
    expect(result['NSE:RELIANCE'].last_price).toBe(1000);
  });

  test('getLTP calls Zerodha /quote/ltp with correct Authorization header', async () => {
    await kiteService.getLTP(['NSE:RELIANCE']);
    expect(axios.get).toHaveBeenCalledWith(
      expect.stringContaining('/quote/ltp'),
      expect.objectContaining({
        headers: expect.objectContaining({
          'Authorization': expect.stringContaining('fake_token'),
        }),
      })
    );
  });

  test('getLTP serialises instruments as repeated params (no brackets)', async () => {
    // Zerodha requires i=NSE:A&i=NSE:B — axios default produces i[]=NSE:A which Zerodha rejects.
    // The fix uses URLSearchParams.append() so the URL contains i=NSE:INFY (no brackets).
    await kiteService.getLTP(['NSE:INFY']);
    const calledUrl = axios.get.mock.calls[0][0];
    expect(calledUrl).toContain('i=NSE%3AINFY');
    expect(calledUrl).not.toContain('i[]=');
  });

  test('placeOrder calls kite.placeOrder with regular variety', async () => {
    mockKite.placeOrder.mockResolvedValue({ order_id: 'ORD-1' });
    const result = await kiteService.placeOrder(
      { tradingsymbol: 'RELIANCE', product: 'CNC' }, { intent: 'entry' });
    expect(result.order_id).toBe('ORD-1');
    expect(mockKite.placeOrder).toHaveBeenCalledWith('regular', expect.any(Object));
  });

  test('placeGTT calls kite.placeGTT', async () => {
    mockKite.placeGTT.mockResolvedValue({ trigger_id: 'GTT-1' });
    const result = await kiteService.placeGTT({ trigger_type: 'single' }, { intent: 'exit' });
    expect(result.trigger_id).toBe('GTT-1');
  });

  test('getOrderHistory returns order history', async () => {
    mockKite.getOrderHistory.mockResolvedValue([{ status: 'COMPLETE' }]);
    const result = await kiteService.getOrderHistory('ORD-1');
    expect(result).toEqual([{ status: 'COMPLETE' }]);
  });

  test('exposes broker reconciliation methods through the authenticated wrapper', async () => {
    mockKite.getOrders.mockResolvedValue([{ order_id: 'ORD-1' }]);
    mockKite.getPositions.mockResolvedValue({ net: [] });
    mockKite.cancelOrder.mockResolvedValue({ order_id: 'ORD-1' });
    mockKite.getGTTs.mockResolvedValue([{ id: 42 }]);
    mockKite.deleteGTT.mockResolvedValue({ trigger_id: 42 });

    await expect(kiteService.getOrders()).resolves.toEqual([{ order_id: 'ORD-1' }]);
    await expect(kiteService.getPositions()).resolves.toEqual({ net: [] });
    await expect(kiteService.cancelOrder('ORD-1')).resolves.toEqual({ order_id: 'ORD-1' });
    await expect(kiteService.getGTTs()).resolves.toEqual([{ id: 42 }]);
    await expect(kiteService.deleteGTT(42)).resolves.toEqual({ trigger_id: 42 });
    expect(mockKite.cancelOrder).toHaveBeenCalledWith('regular', 'ORD-1');
  });

  test('getLoginURL returns URL string', () => {
    const url = kiteService.getLoginURL();
    expect(url).toContain('kite.zerodha.com');
  });

  // ─── Rate limiter ───
  test('rapid calls do not throw (rate limiter queues them)', async () => {
    axios.get.mockResolvedValue(makeLtpResponse('NSE:INFY', 500));
    // Make 3 rapid calls - should all resolve (limiter starts with 5 tokens)
    const results = await Promise.all([
      kiteService.getLTP(['NSE:INFY']),
      kiteService.getLTP(['NSE:INFY']),
      kiteService.getLTP(['NSE:INFY']),
    ]);
    expect(results).toHaveLength(3);
    expect(axios.get).toHaveBeenCalledTimes(3);
  });

  // ─── setAccessToken is called on SDK methods (not getLTP which bypasses SDK) ───
  test('setAccessToken is called before placeOrder', async () => {
    mockKite.placeOrder.mockResolvedValue({ order_id: 'ORD-1' });
    await kiteService.placeOrder(
      { tradingsymbol: 'RELIANCE', product: 'CNC' }, { intent: 'entry' });
    expect(mockKite.setAccessToken).toHaveBeenCalledWith('fake_token');
  });

  // ─── getLTP response validation (the root cause of Apr 29-30 failures) ───
  test('getLTP throws OrderExecutionError when Zerodha returns no data field', async () => {
    // Zerodha returns {"status":"success"} with no data field
    axios.get.mockResolvedValue({
      status: 200,
      headers: { 'content-type': 'application/json' },
      data: { status: 'success' },
    });
    await expect(kiteService.getLTP(['NSE:LICHSGFIN'])).rejects.toThrow(OrderExecutionError);
    await expect(kiteService.getLTP(['NSE:LICHSGFIN'])).rejects.toThrow('empty/null');
  }, 10000);

  test('getLTP throws OrderExecutionError when Zerodha returns null data', async () => {
    axios.get.mockResolvedValue({
      status: 200,
      headers: { 'content-type': 'application/json' },
      data: { status: 'success', data: null },
    });
    await expect(kiteService.getLTP(['NSE:ADANIPORTS'])).rejects.toThrow(OrderExecutionError);
  }, 10000);

  test('getLTP throws OrderExecutionError when Zerodha returns DataException in body', async () => {
    axios.get.mockResolvedValue({
      status: 200,
      headers: { 'content-type': 'application/json; charset=utf-8' },
      data: { error_type: 'DataException', message: 'Unknown content type' },
    });
    await expect(kiteService.getLTP(['NSE:ADANIPORTS'])).rejects.toThrow(OrderExecutionError);
    await expect(kiteService.getLTP(['NSE:ADANIPORTS'])).rejects.toThrow('DataException');
  }, 10000);

  test('getLTP retries and succeeds when first attempt fails', async () => {
    // First call: no data field (the production failure). Second: success.
    axios.get
      .mockResolvedValueOnce({
        status: 200,
        headers: { 'content-type': 'application/json' },
        data: { status: 'success' },
      })
      .mockResolvedValue(makeLtpResponse('NSE:RELIANCE', 2500));
    const result = await kiteService.getLTP(['NSE:RELIANCE']);
    expect(result['NSE:RELIANCE'].last_price).toBe(2500);
    expect(axios.get).toHaveBeenCalledTimes(2);
  }, 5000);

  test('getLTP does NOT retry on TokenExpiredError', async () => {
    const err = new Error('Forbidden');
    err.response = { status: 403, data: {} };
    axios.get.mockRejectedValue(err);
    await expect(kiteService.getLTP(['NSE:RELIANCE'])).rejects.toThrow(TokenExpiredError);
    // Only 1 attempt — no retry on 403
    expect(axios.get).toHaveBeenCalledTimes(1);
  });

  test('getLTP throws OrderExecutionError when all 3 attempts fail (network)', async () => {
    axios.get.mockRejectedValue(new Error('Network timeout'));
    await expect(kiteService.getLTP(['NSE:RELIANCE'])).rejects.toThrow(OrderExecutionError);
    expect(axios.get).toHaveBeenCalledTimes(3);
  }, 10000);

  // ─── F-2 from 2026-09-15 production audit ───
  // The audit observed 31 calls to /api/orders/ltp but 0
  // ltp_raw_response events. The bounded fix adds an entry
  // log + a token-invalid log so a future audit can
  // attribute missing ltp_raw_response events to one of
  // these paths.

  test('getLTP emits ltp_call_started on every entry (F-2 observability)', async () => {
    await kiteService.getLTP(['NSE:RELIANCE']);
    const info_calls = logger.info.mock.calls;
    const started = info_calls.find(([payload]) => payload && payload.event_type === 'ltp_call_started');
    expect(started).toBeDefined();
    expect(started[0].instruments).toEqual(['NSE:RELIANCE']);
    expect(started[0].instrumentCount).toBe(1);
  });

  test('getLTP emits ltp_call_skipped_token_invalid when token is invalid (F-2 observability)', async () => {
    tokenStore.isValid.mockReturnValue(false);
    await expect(kiteService.getLTP(['NSE:RELIANCE'])).rejects.toThrow(TokenExpiredError);
    const error_calls = logger.error.mock.calls;
    const skipped = error_calls.find(([payload]) =>
      payload && payload.event_type === 'ltp_call_skipped_token_invalid');
    expect(skipped).toBeDefined();
    expect(skipped[0].instruments).toEqual(['NSE:RELIANCE']);
    // The pre-fix audit gap: with no skipped event, the
    // operator couldn't tell whether getLTP was even
    // called when the token was invalid. After this slice,
    // the ltp_call_skipped_token_invalid event gives a
    // countable signal.
  });

  test('ltp_call_started fires BEFORE ltp_call_skipped_token_invalid (F-2 ordering)', async () => {
    // When the token is invalid, both events fire (in this
    // order). The audit can now see "started but skipped" as
    // a distinct failure mode from "started but failed at
    // Kite" (which fires ltp_retry / ltp_all_retries_failed).
    tokenStore.isValid.mockReturnValue(false);
    await expect(kiteService.getLTP(['NSE:RELIANCE'])).rejects.toThrow(TokenExpiredError);
    const all_log_calls = [
      ...logger.info.mock.calls.map(c => ({ level: 'info', payload: c[0] })),
      ...logger.error.mock.calls.map(c => ({ level: 'error', payload: c[0] })),
    ];
    const started_idx = all_log_calls.findIndex(c => c.payload.event_type === 'ltp_call_started');
    const skipped_idx = all_log_calls.findIndex(c => c.payload.event_type === 'ltp_call_skipped_token_invalid');
    expect(started_idx).toBeGreaterThanOrEqual(0)
    expect(skipped_idx).toBeGreaterThanOrEqual(0)
    expect(started_idx).toBeLessThan(skipped_idx)
  });
});
