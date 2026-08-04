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
  kite.placeOrder.mockResolvedValue({ order_id: 'ORD-001' });
  kite.getOrderHistory.mockResolvedValue([
    { status: 'COMPLETE', average_price: 1005 },
  ]);
  kite.placeGTT.mockResolvedValueOnce({ trigger_id: 'GTT-STOP-1' })
    .mockResolvedValueOnce({ trigger_id: 'GTT-TGT-1' });
  mockDbRun.mockReturnValue({});
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
      expect.objectContaining({ product: 'CNC' })
    );
  });

  test('uses MIS product type for intraday (isIntraday=true)', async () => {
    await executeSignal(makeSignal(), 'EXEC', true);
    expect(kite.placeOrder).toHaveBeenCalledWith(
      expect.objectContaining({ product: 'MIS' })
    );
  });

  // ─── GTT placement ───
  test('places GTT orders for CNC trades', async () => {
    await executeSignal(makeSignal(), 'EXEC', false);
    // Should place 2 GTTs: stop-loss and target
    expect(kite.placeGTT).toHaveBeenCalledTimes(2);
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

  test('GTT stop trigger follows the fill, and its price sits above the trigger', async () => {
    const signal = makeSignal({ stop_loss: 950 });
    await executeSignal(signal, 'EXEC', false);
    const stopCall = kite.placeGTT.mock.calls[0][0];

    expect(stopCall.trigger_values).toEqual([ANCHORED_STOP]);
    const stopPrice = stopCall.orders[0].price;
    // 955 * 1.002 = 956.91 → snapToTick UP to nearest 0.10 = 957.0
    expect(stopPrice).toBe(Math.ceil(Math.round(ANCHORED_STOP * 1.002 * 10 * 100) / 100) / 10);
    expect(stopPrice).toBeGreaterThan(ANCHORED_STOP);
    // The risk distance the engine sized against is preserved exactly.
    expect(1005 - stopCall.trigger_values[0]).toBe(1000 - 950);
  });

  test('GTT target trigger follows the fill, and its price sits below the trigger', async () => {
    const signal = makeSignal({ target_1: 1075 });
    await executeSignal(signal, 'EXEC', false);
    const targetCall = kite.placeGTT.mock.calls[1][0];

    expect(targetCall.trigger_values).toEqual([ANCHORED_T1]);
    const targetPrice = targetCall.orders[0].price;
    // 1080 * 0.998 = 1077.84 → snapToTick DOWN to nearest 0.10 = 1077.8
    expect(targetPrice).toBe(Math.floor(Math.round(ANCHORED_T1 * 0.998 * 10 * 100) / 100) / 10);
    expect(targetPrice).toBeLessThan(ANCHORED_T1);
    // Reward:risk survives the drift.
    expect((ANCHORED_T1 - 1005) / (1005 - ANCHORED_STOP)).toBeCloseTo(1.5, 6);
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
  test('throws OrderExecutionError when order placement fails after retries', async () => {
    kite.placeOrder.mockRejectedValue(new Error('Kite unavailable'));
    await expect(executeSignal(makeSignal(), 'EXEC')).rejects.toThrow(OrderExecutionError);
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
    kite.getOrderHistory.mockResolvedValue([{ status: 'COMPLETE', average_price: 995 }]);

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
    routePlaceOrder({ stop: new Error('Market orders without market protection...') });
    await expect(executeSignal(makeSignal(), 'EM', true))
      .rejects.toThrow(/unwound.*Safe to retry/);
    const unwindCall = kite.placeOrder.mock.calls.find(c => c[0].tag === 'QUANT_SENT_UNWIND');
    expect(unwindCall).toBeDefined();
    const p = unwindCall[0];
    expect(p.order_type).toBe('LIMIT');
    expect(p.transaction_type).toBe('SELL');
    expect(p.tag.length).toBeLessThanOrEqual(20);
  });

  test('unwound position is retryable (positionHeld not set)', async () => {
    routePlaceOrder({ stop: new Error('stop rejected'), unwind: { order_id: 'UNWIND-1' } });
    await executeSignal(makeSignal(), 'EM', true).catch(err => {
      expect(err.positionHeld).toBeFalsy();
    });
    expect.assertions(1);
  });

  test('stop AND unwind failing flags positionHeld and does NOT mark the fill CANCELLED', async () => {
    routePlaceOrder({
      stop: new Error('stop rejected'),
      unwind: new Error('Invalid tags / no protection'),
    });
    let caught;
    await executeSignal(makeSignal(), 'EM', true).catch(err => { caught = err; });
    expect(caught).toBeDefined();
    expect(caught.positionHeld).toBe(true);
    expect(caught.message).toMatch(/FLATTEN THIS POSITION MANUALLY/);
    // The fill must be recorded as OPEN_UNPROTECTED, never CANCELLED.
    const updates = mockDbPrepare.mock.calls.map(c => c[0]).filter(Boolean);
    expect(updates.some(sql => sql.includes("'OPEN_UNPROTECTED'"))).toBe(true);
    expect(updates.some(sql => sql.includes("'CANCELLED'"))).toBe(false);
  });
});
