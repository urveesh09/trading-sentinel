/**
 * Tests for services/executor.js - order execution engine.
 *
 * Heavy mocking required: kite, token-store, market-hours, db, telegram, config, fetch.
 */

// ── Mock modules BEFORE require ──
jest.mock('../../services/kite', () => ({
  getLTP: jest.fn(),
  placeOrder: jest.fn(),
  getOrderHistory: jest.fn(),
  getOrders: jest.fn(),
  getGTTs: jest.fn(),
  deleteGTT: jest.fn(),
  getPositions: jest.fn(),
  cancelOrder: jest.fn(),
  placeGTT: jest.fn(),
}));

jest.mock('../../services/token-store', () => ({
  isValid: jest.fn(),
}));

jest.mock('../../utils/market-hours', () => ({
  isMarketOpen: jest.fn(),
}));

jest.mock('../../services/telegram', () => ({
  sendAlert: jest.fn(),
  sendSignalAlert: jest.fn(),
}));

// Mock the DB
const mockDbPrepare = jest.fn();
const mockDbRun = jest.fn();
const mockDbGet = jest.fn();
mockDbPrepare.mockReturnValue({ run: mockDbRun, get: mockDbGet });

jest.mock('../../db/index', () => ({
  signalsDb: { prepare: mockDbPrepare },
  appDb: { prepare: mockDbPrepare },
}));

// Mock fetch for syncToEngine
global.fetch = jest.fn();

const kite = require('../../services/kite');
const tokenStore = require('../../services/token-store');
const { isMarketOpen } = require('../../utils/market-hours');
const { executeSignal } = require('../../services/executor');
const {
  TokenExpiredError,
  MarketClosedError,
  PriceDriftError,
  OrderExecutionError,
  ValidationError,
} = require('../../utils/errors');

// ── Helpers ──
const makeSignal = (overrides = {}) => ({
  signal_id: 'test-uuid-1234',
  ticker: 'RELIANCE',
  close: 1000,
  shares: 5,
  stop_loss: 950,
  target_1: 1075,
  target_2: 1150,
  capital_at_risk: 250,
  // [TRAILING-EXITS 2026-06-16] Regime is forwarded by the screener (string
  // from pydantic enum serialization). Default null = legacy behavior.
  regime: null,
  ...overrides,
});

function setupHappyPath() {
  tokenStore.isValid.mockReturnValue(true);
  isMarketOpen.mockReturnValue(true);
  kite.getLTP.mockResolvedValue({
    'NSE:RELIANCE': { last_price: 1005 },
  });
  kite.placeOrder.mockImplementation((params) => Promise.resolve({
    order_id: params.order_type === 'SL' ? 'SL-1' :
      (params.transaction_type === 'SELL' ? 'UNWIND-1' : 'ORD-001')
  }));
  kite.getOrderHistory.mockImplementation((orderId) => Promise.resolve(
    String(orderId).startsWith('SL-')
      ? [{ status: 'TRIGGER PENDING', filled_quantity: 0 }]
      : [{ status: 'COMPLETE', average_price: 1005, filled_quantity: 5 }]
  ));
  kite.getOrders.mockResolvedValue([]);
  kite.getPositions.mockResolvedValue({ net: [], day: [] });
  kite.cancelOrder.mockResolvedValue({ order_id: 'ORD-001' });
  kite.getGTTs.mockResolvedValue([]);
  kite.placeGTT.mockResolvedValue({ trigger_id: 'GTT-OCO-1' });
  mockDbRun.mockReturnValue({});
  mockDbGet.mockReturnValue({ signal_id: 'test-uuid-1234' });
  global.fetch.mockResolvedValue({ ok: true });
}

describe('executeSignal()', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setupHappyPath();
  });

  // ─── Pre-checks ───
  test('throws TokenExpiredError when token is invalid', async () => {
    tokenStore.isValid.mockReturnValue(false);
    await expect(executeSignal(makeSignal(), 'EXEC')).rejects.toThrow(TokenExpiredError);
  });

  test('throws MarketClosedError when market is closed', async () => {
    isMarketOpen.mockReturnValue(false);
    await expect(executeSignal(makeSignal(), 'EXEC')).rejects.toThrow(MarketClosedError);
  });

  test('throws ValidationError when capital_at_risk exceeds 1500', async () => {
    await expect(
      executeSignal(makeSignal({ capital_at_risk: 1501 }), 'EXEC')
    ).rejects.toThrow(ValidationError);
  });

  test('blocks broker placement when signal has no durable received_signals record', async () => {
    mockDbGet.mockReturnValue(null);
    await expect(executeSignal(makeSignal(), 'EXEC')).rejects.toThrow(/not durably registered/);
    expect(kite.getLTP).not.toHaveBeenCalled();
    expect(kite.placeOrder).not.toHaveBeenCalled();
  });

  // ─── Price drift ───
  test('throws PriceDriftError when LTP drifts >2%', async () => {
    kite.getLTP.mockResolvedValue({
      'NSE:RELIANCE': { last_price: 1025 }, // 2.5% drift
    });
    await expect(executeSignal(makeSignal(), 'EXEC')).rejects.toThrow(PriceDriftError);
  });

  test('allows execution when LTP drift is within 2%', async () => {
    kite.getLTP.mockResolvedValue({
      'NSE:RELIANCE': { last_price: 1019 }, // 1.9% drift
    });
    const result = await executeSignal(makeSignal(), 'EXEC');
    expect(result.orderId).toBe('ORD-001');
  });

  // ─── Product type ───
  test('uses CNC product type for swing trades (isIntraday=false)', async () => {
    await executeSignal(makeSignal(), 'EXEC', false);
    expect(kite.placeOrder).toHaveBeenCalledWith(
      expect.objectContaining({ product: 'CNC' }),
      // [HALT 2026-08-05] The entry declares itself an entry, so the kill
      // switch can gate it. Pinned here because a silent change to 'exit'
      // would route the buy leg around the halt.
      expect.objectContaining({ intent: 'entry' })
    );
  });

  test('uses MIS product type for intraday (isIntraday=true)', async () => {
    await executeSignal(makeSignal(), 'EXEC', true);
    expect(kite.placeOrder).toHaveBeenCalledWith(
      expect.objectContaining({ product: 'MIS' }),
      expect.objectContaining({ intent: 'entry' })
    );
  });

  // ─── GTT placement ───
  test('places GTT orders for CNC trades', async () => {
    await executeSignal(makeSignal(), 'EXEC', false);
    expect(kite.placeGTT).toHaveBeenCalledTimes(1);
    expect(kite.placeGTT.mock.calls[0][0].trigger_type).toBe('two-leg');
    expect(kite.placeGTT.mock.calls[0][0].orders.every(o => o.quantity === 5)).toBe(true);
  });

  test('does NOT place GTT orders for intraday trades', async () => {
    await executeSignal(makeSignal(), 'EXEC', true);
    expect(kite.placeGTT).not.toHaveBeenCalled();
  });

  // [FILL-ANCHOR 2026-08-04] The GTT legs are now placed at the FILL-anchored
  // stop and target, not the signal's. The happy path fills at 1005 against a
  // signal close of 1000, so the whole geometry slides up by 5:
  //   risk    = 1000 - 950 = 50        (no floor binds: 1.2% of 1005 is 12.06)
  //   stop    = 1005 - 50   = 955
  //   rTarget = (1075 - 1000) / 50 = 1.5R  ->  t1 = 1005 + 1.5*50 = 1080
  // Anchoring the target to a stale close while the stop moved would have
  // quietly changed this trade's reward:risk from 1.5 to 1.4.
  const ANCHORED_STOP = 955;
  const ANCHORED_T1 = 1080;

  test('GTT stop trigger follows the fill, and its price is executable below the trigger', async () => {
    const signal = makeSignal({ stop_loss: 950 });
    await executeSignal(signal, 'EXEC', false);
    const stopCall = kite.placeGTT.mock.calls[0][0];

    expect(stopCall.trigger_values).toEqual([ANCHORED_STOP, ANCHORED_T1]);
    const stopPrice = stopCall.orders[0].price;
    expect(stopPrice).toBe(Math.floor(Math.round(ANCHORED_STOP * 0.998 * 10 * 100) / 100) / 10);
    expect(stopPrice).toBeLessThan(ANCHORED_STOP);
    // The risk distance the engine sized against is preserved exactly.
    expect(1005 - stopCall.trigger_values[0]).toBe(1000 - 950);
  });

  test('GTT target trigger follows the fill, and its price sits below the trigger', async () => {
    const signal = makeSignal({ target_1: 1075 });
    await executeSignal(signal, 'EXEC', false);
    const targetCall = kite.placeGTT.mock.calls[0][0];

    expect(targetCall.trigger_values).toEqual([ANCHORED_STOP, ANCHORED_T1]);
    const targetPrice = targetCall.orders[1].price;
    // 1080 * 0.998 = 1077.84 → snapToTick DOWN to nearest 0.10 = 1077.8
    expect(targetPrice).toBe(Math.floor(Math.round(ANCHORED_T1 * 0.998 * 10 * 100) / 100) / 10);
    expect(targetPrice).toBeLessThan(ANCHORED_T1);
    // Reward:risk survives the drift.
    expect((ANCHORED_T1 - 1005) / (1005 - ANCHORED_STOP)).toBeCloseTo(1.5, 6);
  });

  test('CNC uses one full-quantity OCO trigger id for both exit legs', async () => {
    await executeSignal(makeSignal(), 'EXEC', false);
    const params = kite.placeGTT.mock.calls[0][0];
    expect(params.trigger_type).toBe('two-leg');
    expect(params.orders).toHaveLength(2);
    expect(params.orders.map(o => o.quantity)).toEqual([5, 5]);
    const syncBody = JSON.parse(global.fetch.mock.calls[0][1].body);
    expect(syncBody.gtt_stop_id).toBe('GTT-OCO-1');
    expect(syncBody.gtt_target_id).toBe('GTT-OCO-1');
  });

  test('ambiguous GTT response recovers the exact OCO and never resubmits', async () => {
    kite.placeGTT.mockRejectedValueOnce(new Error('response timeout'));
    kite.getGTTs.mockImplementation(() => {
      const params = kite.placeGTT.mock.calls[0][0];
      return Promise.resolve([{
        id: 'GTT-RECOVERED', condition: {
          tradingsymbol: params.tradingsymbol, exchange: params.exchange,
          trigger_values: params.trigger_values,
        }, orders: params.orders,
      }]);
    });
    const result = await executeSignal(makeSignal(), 'EXEC', false);
    expect(result.gttStopId).toBe('GTT-RECOVERED');
    expect(kite.placeGTT).toHaveBeenCalledTimes(1);
  });

  test('unreconciled GTT ambiguity remains locked and is not represented as protected', async () => {
    kite.placeGTT.mockRejectedValueOnce(new Error('response timeout'));
    kite.getGTTs.mockResolvedValue([]);
    let caught;
    await executeSignal(makeSignal(), 'EXEC', false).catch(err => { caught = err; });
    expect(caught.positionHeld).toBe(true);
    expect(caught.outcomeUnknown).toBe(true);
    expect(kite.placeGTT).toHaveBeenCalledTimes(1);
    expect(mockDbRun.mock.calls.some(args => args[0] === 'OUTCOME_UNKNOWN')).toBe(true);
  });

  // ─── Fill verification ───
  test('verifies fill status after order placement', async () => {
    await executeSignal(makeSignal(), 'EXEC');
    expect(kite.getOrderHistory).toHaveBeenCalledWith('ORD-001');
  });

  test('throws OrderExecutionError when order is rejected by broker', async () => {
    kite.getOrderHistory.mockResolvedValue([
      { status: 'REJECTED', status_message: 'Insufficient funds' },
    ]);
    await expect(executeSignal(makeSignal(), 'EXEC')).rejects.toThrow(OrderExecutionError);
  });

  test('OPEN timeout is cancelled and never treated as filled or protected', async () => {
    kite.getOrderHistory
      .mockResolvedValueOnce([{ status: 'OPEN', filled_quantity: 0 }])
      .mockResolvedValue([{ status: 'CANCELLED', filled_quantity: 0 }]);
    const { reconcilePlacedOrder } = require('../../services/executor');
    const result = await reconcilePlacedOrder('ORD-001', 5, { attempts: 1, delayMs: 0, ticker: 'RELIANCE', product: 'CNC' });
    expect(kite.cancelOrder).toHaveBeenCalledWith('ORD-001');
    expect(result.state).toBe('CANCELLED');
    expect(result.filledQuantity).toBe(0);
  });

  test('late COMPLETE after cancellation is recognized as a real fill', async () => {
    kite.getOrderHistory
      .mockResolvedValueOnce([{ status: 'OPEN', filled_quantity: 0 }])
      .mockResolvedValueOnce([{ status: 'COMPLETE', filled_quantity: 5, average_price: 1006 }]);
    const { reconcilePlacedOrder } = require('../../services/executor');
    const result = await reconcilePlacedOrder('ORD-001', 5, { attempts: 1, delayMs: 0 });
    expect(result).toEqual(expect.objectContaining({ state: 'COMPLETE', filledQuantity: 5, fillPrice: 1006 }));
  });

  test('cancel failure with an OPEN order remains UNKNOWN and fail-closed', async () => {
    kite.getOrderHistory.mockResolvedValue([{ status: 'OPEN', filled_quantity: 0 }]);
    kite.cancelOrder.mockRejectedValue(new Error('cancel timeout'));
    const { reconcilePlacedOrder } = require('../../services/executor');
    const result = await reconcilePlacedOrder('ORD-001', 5, { attempts: 1, delayMs: 0 });
    expect(result.state).toBe('UNKNOWN');
    expect(result.cancelError).toMatch(/cancel timeout/);
  });

  test('cancelled partial fill returns only the actually filled quantity', async () => {
    kite.getOrderHistory
      .mockResolvedValueOnce([{ status: 'OPEN', filled_quantity: 2, average_price: 1004 }])
      .mockResolvedValueOnce([{ status: 'CANCELLED', filled_quantity: 2, average_price: 1004 }]);
    const { reconcilePlacedOrder } = require('../../services/executor');
    const result = await reconcilePlacedOrder('ORD-001', 5, { attempts: 1, delayMs: 0 });
    expect(result).toEqual(expect.objectContaining({ state: 'PARTIAL', filledQuantity: 2, fillPrice: 1004 }));
  });

  // ─── Sync to Container B ───
  test('syncs position to Container B on success', async () => {
    await executeSignal(makeSignal(), 'EXEC');
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/positions/manual'),
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'X-Internal-Secret': expect.any(String),
        }),
      })
    );
  });

  test('sends source=MOMENTUM for intraday trades', async () => {
    await executeSignal(makeSignal(), 'EXEC', true);
    const fetchCall = global.fetch.mock.calls[0];
    const body = JSON.parse(fetchCall[1].body);
    expect(body.source).toBe('MOMENTUM');
  });

  test('sends source=SYSTEM for swing trades', async () => {
    await executeSignal(makeSignal(), 'EXEC', false);
    const fetchCall = global.fetch.mock.calls[0];
    const body = JSON.parse(fetchCall[1].body);
    expect(body.source).toBe('SYSTEM');
  });

  // [TRAILING-EXITS 2026-06-16] Regime at entry must be forwarded so
  // position_tracker can pick the regime-aware Chandelier multiplier.
  test('forwards regime_at_entry to Container B when present', async () => {
    await executeSignal(makeSignal({ regime: 'REGIME_1_NORMAL' }), 'EXEC');
    const fetchCall = global.fetch.mock.calls[0];
    const body = JSON.parse(fetchCall[1].body);
    expect(body.regime_at_entry).toBe('REGIME_1_NORMAL');
  });

  test('sends regime_at_entry=null when regime is missing (legacy compat)', async () => {
    await executeSignal(makeSignal({ regime: null }), 'EXEC');
    const fetchCall = global.fetch.mock.calls[0];
    const body = JSON.parse(fetchCall[1].body);
    expect(body.regime_at_entry).toBeNull();
  });

  // ─── DB idempotency ───
  test('inserts order into DB immediately after placement', async () => {
    await executeSignal(makeSignal(), 'EXEC');
    // DB prepare called for INSERT INTO executed_orders
    const insertCalls = mockDbPrepare.mock.calls.filter(
      c => c[0] && c[0].includes('INSERT INTO executed_orders')
    );
    expect(insertCalls.length).toBeGreaterThanOrEqual(1);
  });

  // ─── LTP fetch failure ───
  test('throws OrderExecutionError when LTP fetch fails', async () => {
    kite.getLTP.mockRejectedValue(new Error('Network error'));
    await expect(executeSignal(makeSignal(), 'EXEC')).rejects.toThrow(OrderExecutionError);
  });

  test('throws OrderExecutionError when LTP resolves to undefined', async () => {
    kite.getLTP.mockResolvedValue(undefined);
    await expect(executeSignal(makeSignal(), 'EXEC')).rejects.toThrow(OrderExecutionError);
  });

  // ─── Order placement failure ───
  test('ambiguous order placement is not retried and fails UNKNOWN when tag lookup finds nothing', async () => {
    kite.placeOrder.mockRejectedValue(new Error('Kite unavailable'));
    let caught;
    await executeSignal(makeSignal(), 'EXEC').catch(err => { caught = err; });
    expect(caught).toBeInstanceOf(OrderExecutionError);
    expect(caught.outcomeUnknown).toBe(true);
    expect(kite.placeOrder).toHaveBeenCalledTimes(1);
    expect(kite.getOrders).toHaveBeenCalledTimes(1);
  });

  test('definitive placement rejection fails immediately without reconciliation or retry', async () => {
    kite.placeOrder.mockRejectedValue(new OrderExecutionError('Insufficient funds'));
    await expect(executeSignal(makeSignal(), 'EXEC')).rejects.toThrow(/Insufficient funds/);
    expect(kite.placeOrder).toHaveBeenCalledTimes(1);
    expect(kite.getOrders).not.toHaveBeenCalled();
  });

  test('ambiguous placement recovers the uniquely tagged broker order without resubmitting', async () => {
    kite.placeOrder.mockRejectedValueOnce(new Error('response timeout'));
    const { entryTag } = require('../../services/executor');
    kite.getOrders.mockResolvedValue([{
      order_id: 'RECOVERED-1', tag: entryTag(makeSignal().signal_id),
      tradingsymbol: 'RELIANCE', transaction_type: 'BUY', quantity: 5,
    }]);
    kite.getOrderHistory.mockResolvedValue([{ status: 'COMPLETE', average_price: 1005, filled_quantity: 5 }]);
    const result = await executeSignal(makeSignal(), 'EXEC');
    expect(result.orderId).toBe('RECOVERED-1');
    expect(kite.placeOrder).toHaveBeenCalledTimes(1);
  });

  // ─── MIS protective stop (2026-07-15 fix) ───
  // Route placeOrder by leg so we can fail the stop/unwind independently of the buy.
  const routePlaceOrder = ({ buy = { order_id: 'BUY-1' }, stop, unwind } = {}) => {
    kite.placeOrder.mockImplementation((params) => {
      if (params.transaction_type === 'BUY') return Promise.resolve(buy);
      if (params.order_type === 'SL') {
        return stop instanceof Error ? Promise.reject(stop) : Promise.resolve(stop ?? { order_id: 'SL-1' });
      }
      // Anything else is the marketable-LIMIT unwind SELL.
      return unwind instanceof Error ? Promise.reject(unwind) : Promise.resolve(unwind ?? { order_id: 'UNWIND-1' });
    });
    kite.getOrderHistory.mockImplementation((orderId) => {
      if (String(orderId).startsWith('SL-')) {
        return Promise.resolve([{ status: 'TRIGGER PENDING', filled_quantity: 0 }]);
      }
      if (String(orderId).startsWith('UNWIND-')) {
        return Promise.resolve([{ status: 'COMPLETE', average_price: 994, filled_quantity: 5 }]);
      }
      return Promise.resolve([{ status: 'COMPLETE', average_price: 1005, filled_quantity: 5 }]);
    });
  };

  test('MIS buy places a protective SL (limit) order, never SL-M', async () => {
    routePlaceOrder();
    await executeSignal(makeSignal({ stop_loss: 950 }), 'EM', true);
    const stopCall = kite.placeOrder.mock.calls.find(c => c[0].order_type === 'SL');
    expect(stopCall).toBeDefined();
    const p = stopCall[0];
    expect(p.transaction_type).toBe('SELL');
    expect(p.product).toBe('MIS');
    // [FILL-ANCHOR 2026-08-04] Armed at the fill-anchored stop (1005 - 50 = 955),
    // not the signal's 950. Arming 950 against a 1005 fill would have handed the
    // trade 55 of risk on a 50 budget; against a 995 fill it would have handed it
    // 45 and tripped the breakeven ratchet a fifth of an R early.
    expect(p.trigger_price).toBe(955);      // snapToTick(955, down)
    expect(p.price).toBe(945.4);            // snapToTick(955 * 0.99, down) — marketable, <= trigger
    expect(p.price).toBeLessThanOrEqual(p.trigger_price);
    // No leg may be a bare market order (Zerodha rejects those over the API).
    expect(kite.placeOrder.mock.calls.every(c => c[0].order_type !== 'SL-M' && c[0].order_type !== 'MARKET')).toBe(true);
  });

  // ─── [FILL-ANCHOR 2026-08-04] Stop follows the fill, both directions ───
  test('a FAVOURABLE fill moves the MIS stop DOWN so risk stays at the sized distance', async () => {
    // This is the SUMICHEM shape: signalled at 1000, filled 12 minutes later at
    // 995. The old code armed 950 against a 995 fill = 45 of risk on a 50
    // budget, so the +1R breakeven ratchet fired 10% early and scratched the
    // trade before it could work.
    routePlaceOrder();
    kite.getLTP.mockResolvedValue({ 'NSE:RELIANCE': { last_price: 995 } });
    kite.getOrderHistory.mockImplementation(orderId => Promise.resolve(
      String(orderId).startsWith('SL-')
        ? [{ status: 'TRIGGER PENDING', filled_quantity: 0 }]
        : [{ status: 'COMPLETE', average_price: 995, filled_quantity: 5 }]
    ));

    await executeSignal(makeSignal({ stop_loss: 950 }), 'EM', true);

    const stopCall = kite.placeOrder.mock.calls.find(c => c[0].order_type === 'SL');
    expect(stopCall[0].trigger_price).toBe(945);        // 995 - 50, not 950
    expect(995 - stopCall[0].trigger_price).toBe(50);   // the sized risk, intact
  });

  test('an ATR floor wider than the signal risk cuts share count to stay in budget', async () => {
    // atr 100 x 0.35 = 35 of risk per share. The 250 budget affords 7 shares,
    // but the engine only sized 5 — so size must stay at 5, never grow.
    routePlaceOrder();
    await executeSignal(makeSignal({ atr_at_entry: 100 }), 'EM', true);
    const buyCall = kite.placeOrder.mock.calls.find(c => c[0].transaction_type === 'BUY');
    expect(buyCall[0].quantity).toBe(5);

    // atr 200 x 0.35 = 70/share; 250 / 70 = 3 shares. Size must shrink.
    jest.clearAllMocks();
    setupHappyPath();
    routePlaceOrder();
    await executeSignal(makeSignal({ atr_at_entry: 200 }), 'EM', true);
    const buyCall2 = kite.placeOrder.mock.calls.find(c => c[0].transaction_type === 'BUY');
    expect(buyCall2[0].quantity).toBe(3);
  });

  test('refuses the trade when one share of floored risk breaches the whole budget', async () => {
    routePlaceOrder();
    // atr 1000 x 0.35 = 350/share against a 250 budget -> not affordable.
    await expect(
      executeSignal(makeSignal({ atr_at_entry: 1000 }), 'EM', true)
    ).rejects.toThrow(ValidationError);
    expect(kite.placeOrder).not.toHaveBeenCalled();
  });

  test('rejects a malformed signal whose stop is not below its close', async () => {
    routePlaceOrder();
    await expect(
      executeSignal(makeSignal({ stop_loss: 1000 }), 'EM', true)
    ).rejects.toThrow(ValidationError);
    expect(kite.placeOrder).not.toHaveBeenCalled();
  });

  test('when the stop is rejected, unwinds with a marketable LIMIT and a <=20-char tag', async () => {
    routePlaceOrder({ stop: Object.assign(new Error('Market orders without market protection...'), { retryable: false }) });
    await expect(executeSignal(makeSignal(), 'EM', true))
      .rejects.toThrow(/broker-confirmed.*flat/i);
    const unwindCall = kite.placeOrder.mock.calls.find(c => String(c[0].tag).startsWith('UW_'));
    expect(unwindCall).toBeDefined();
    const p = unwindCall[0];
    expect(p.order_type).toBe('LIMIT');
    expect(p.transaction_type).toBe('SELL');
    expect(p.tag.length).toBeLessThanOrEqual(20);
  });

  test('ambiguous stop submission is never retried and does not launch a conflicting unwind', async () => {
    routePlaceOrder({ stop: new Error('stop response timeout') });
    kite.getOrders.mockResolvedValue([]);
    let caught;
    await executeSignal(makeSignal(), 'EM', true).catch(err => { caught = err; });
    const sellCalls = kite.placeOrder.mock.calls.filter(c => c[0].transaction_type === 'SELL');
    expect(sellCalls).toHaveLength(1);
    expect(sellCalls[0][0].order_type).toBe('SL');
    expect(caught.positionHeld).toBe(true);
    expect(caught.outcomeUnknown).toBe(true);
  });

  test('unwind placement acknowledgement is not flat until terminal full-fill truth', async () => {
    routePlaceOrder({ stop: Object.assign(new Error('stop rejected'), { retryable: false }) });
    kite.getOrderHistory.mockImplementation(orderId => {
      if (String(orderId) === 'BUY-1') return Promise.resolve([{ status: 'COMPLETE', average_price: 1005, filled_quantity: 5 }]);
      if (String(orderId) === 'UNWIND-1') return Promise.resolve([{ status: 'CANCELLED', filled_quantity: 0 }]);
      return Promise.resolve([{ status: 'REJECTED', status_message: 'stop rejected' }]);
    });
    let caught;
    await executeSignal(makeSignal(), 'EM', true).catch(err => { caught = err; });
    expect(caught.positionHeld).toBe(true);
    expect(caught.message).toMatch(/not fully confirmed/i);
    expect(mockDbRun.mock.calls.some(args => args[0] === 'HELD_UNPROTECTED')).toBe(true);
  });

  test('broker-confirmed full unwind is flat (positionHeld not set)', async () => {
    routePlaceOrder({ stop: Object.assign(new Error('stop rejected'), { retryable: false }), unwind: { order_id: 'UNWIND-1' } });
    await executeSignal(makeSignal(), 'EM', true).catch(err => {
      expect(err.positionHeld).toBeFalsy();
    });
    expect.assertions(1);
  });

  test('stop AND unwind failing flags positionHeld and does NOT mark the fill CANCELLED', async () => {
    routePlaceOrder({
      stop: Object.assign(new Error('stop rejected'), { retryable: false }),
      unwind: Object.assign(new Error('Invalid tags / no protection'), { retryable: false }),
    });
    let caught;
    await executeSignal(makeSignal(), 'EM', true).catch(err => { caught = err; });
    expect(caught).toBeDefined();
    expect(caught.positionHeld).toBe(true);
    expect(caught.message).toMatch(/FLATTEN THIS POSITION MANUALLY/i);
    // The fill must be durably recorded as held/unprotected using a schema-valid state.
    const updates = mockDbPrepare.mock.calls.map(c => c[0]).filter(Boolean);
    expect(updates.some(sql => sql.includes('execution_state = ?'))).toBe(true);
    expect(mockDbRun.mock.calls.some(args => args[0] === 'HELD_UNPROTECTED')).toBe(true);
    expect(updates.some(sql => sql.includes("'CANCELLED'"))).toBe(false);
  });
});
