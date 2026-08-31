/**
 * Integration tests for routes/orders.js
 *
 * Tests:
 * - GET /api/orders/ltp (internal secret auth, returns LTP)
 * - POST /api/orders/square-off (internal auth, Zod validation, sell order)
 * - POST /api/orders/execute (session auth, PENDING→EXECUTING→EXECUTED, replay)
 */

// ── Mock dependencies BEFORE require ──
jest.mock('../../services/kite', () => ({
  getLTP: jest.fn(),
  placeOrder: jest.fn(),
  placeGTT: jest.fn(),
  getOrderHistory: jest.fn(),
  getOrders: jest.fn(),
}));

jest.mock('../../services/executor', () => ({
  executeSignal: jest.fn(),
  reconcilePlacedOrder: jest.fn(),
  // Real tick-snap: the square-off route uses it to convert MARKET -> marketable LIMIT.
  snapToTick: (price, dir = 1) => {
    const t = 0.10;
    const ticks = price / t;
    const snapped = dir >= 0 ? Math.ceil(Math.round(ticks * 100) / 100) : Math.floor(Math.round(ticks * 100) / 100);
    return Math.round(snapped * t * 100) / 100;
  },
  orderFillState: (order, requested) => {
    if (!order) return { state: 'UNKNOWN', terminal: false, filledQuantity: 0, fillPrice: null };
    const filledQuantity = Number(order.filled_quantity || 0);
    if (order.status === 'COMPLETE') return { state: 'COMPLETE', terminal: true, filledQuantity: filledQuantity || requested, fillPrice: order.average_price || null };
    if (order.status === 'REJECTED') return { state: 'REJECTED', terminal: true, filledQuantity, fillPrice: null, reason: order.status_message };
    if (order.status === 'CANCELLED') return { state: filledQuantity ? 'PARTIAL' : 'CANCELLED', terminal: true, filledQuantity, fillPrice: order.average_price || null };
    return { state: filledQuantity ? 'PARTIAL_OPEN' : order.status, terminal: false, filledQuantity, fillPrice: order.average_price || null };
  },
}));

jest.mock('../../services/telegram', () => ({
  bot: { on: jest.fn(), sendMessage: jest.fn() },
  isValidChat: jest.fn(() => true),
  sendSignalAlert: jest.fn(),
  sendAlert: jest.fn(),
}));

jest.mock('../../services/token-store', () => ({
  isValid: jest.fn(() => true),
  getToken: jest.fn(() => 'test-token'),
  getStatus: jest.fn(() => ({ status: 'active', generatedAt: new Date().toISOString() })),
}));

jest.mock('../../utils/market-hours', () => ({
  isMarketOpen: jest.fn(() => true),
}));

const mockPrepare = jest.fn();
const mockRun = jest.fn();
const mockGet = jest.fn();
const mockTransaction = jest.fn();
mockPrepare.mockReturnValue({ run: mockRun, get: mockGet });

jest.mock('../../db/index', () => ({
  signalsDb: { prepare: mockPrepare, transaction: mockTransaction },
  appDb: { prepare: mockPrepare },
}));

jest.mock('../../config', () => ({
  TELEGRAM_CHAT_ID: '99999999999',
  TELEGRAM_BOT_TOKEN: 'fake-token',
  TELEGRAM_MODE: 'polling',
  TELEGRAM_WEBHOOK_PATH: '/webhook/telegram',
  TELEGRAM_WEBHOOK_SECRET: 'a]9Kz!2Qf#Lm$Wp^Rv&Tn*Xb8Ye3Hj5Gd',
  ALLOWED_ORIGINS: ['http://localhost:3001'],
  PORT: 3001,
  NODE_ENV: 'test',
  ZERODHA_API_KEY: 'fake_key',
  ZERODHA_API_SECRET: 'fake_secret',
  ZERODHA_REDIRECT_URL: 'http://localhost:3001/callback',
  SESSION_SECRET: 'test_session_secret_32chars_long!!',
  INTERNAL_API_SECRET: 'test_internal_secret_32chars_long',
  OPENCLAW_WEBHOOK_SECRET: 'test_openclaw_secret_32chars_long',
  PYTHON_ENGINE_URL: 'http://localhost:8000',
  PYTHON_ENGINE_TIMEOUT_MS: 5000,
  LOG_LEVEL: 'error',
  RATE_LIMIT_WINDOW_MS: 60000,
  RATE_LIMIT_MAX: 1000,
}));

const express = require('express');
const session = require('express-session');
const request = require('supertest');
const config = require('../../config');
const kite = require('../../services/kite');
const executor = require('../../services/executor');

let app;

beforeAll(() => {
  app = express();
  app.use(express.json());

  // Session middleware for /execute route
  app.use(session({
    secret: config.SESSION_SECRET,
    resave: false,
    saveUninitialized: false,
    cookie: { httpOnly: true },
  }));

  // Inject session for testing (middleware to authenticate)
  app.use((req, res, next) => {
    // If X-Test-Auth header is present, set session as authenticated
    if (req.headers['x-test-auth'] === 'true') {
      req.session.authenticated = true;
    }
    next();
  });

  app.use('/api/orders', require('../../routes/orders'));

  // Error handler
  app.use((err, req, res, next) => {
    const statusCode = err.statusCode || 500;
    res.status(statusCode).json({ error: err.type || 'error', message: err.message });
  });
});

beforeEach(() => {
  jest.clearAllMocks();
  mockRun.mockReturnValue({});
  mockGet.mockReturnValue(null);
  kite.getOrders.mockResolvedValue([]);
  kite.getOrderHistory.mockResolvedValue([{ status: 'OPEN', filled_quantity: 0 }]);
  executor.reconcilePlacedOrder.mockResolvedValue({
    state: 'CANCELLED', terminal: true, filledQuantity: 0, fillPrice: null,
  });
});

// ─────────────────────────────────────────────────────────────────────
// GET /api/orders/ltp
// ─────────────────────────────────────────────────────────────────────

describe('GET /api/orders/ltp', () => {

  test('returns LTP for valid ticker with internal secret', async () => {
    kite.getLTP.mockResolvedValue({
      'NSE:RELIANCE': { last_price: 2500.50 },
    });

    const res = await request(app)
      .get('/api/orders/ltp?ticker=RELIANCE')
      .set('X-Internal-Secret', config.INTERNAL_API_SECRET);

    expect(res.status).toBe(200);
    expect(res.body.ticker).toBe('RELIANCE');
    expect(res.body.ltp).toBe(2500.50);
    expect(res.body.timestamp).toBeDefined();
  });

  test('returns 403 without internal secret', async () => {
    const res = await request(app)
      .get('/api/orders/ltp?ticker=RELIANCE');

    expect(res.status).toBe(403);
  });

  test('returns 403 with wrong internal secret', async () => {
    const res = await request(app)
      .get('/api/orders/ltp?ticker=RELIANCE')
      .set('X-Internal-Secret', 'wrong_secret');

    expect(res.status).toBe(403);
  });

  test('returns 400 when ticker is missing', async () => {
    const res = await request(app)
      .get('/api/orders/ltp')
      .set('X-Internal-Secret', config.INTERNAL_API_SECRET);

    expect(res.status).toBe(400);
    expect(res.body.error).toBe('missing_ticker');
  });

  test('returns 404 when ticker not found in Kite', async () => {
    kite.getLTP.mockResolvedValue({});

    const res = await request(app)
      .get('/api/orders/ltp?ticker=UNKNOWN')
      .set('X-Internal-Secret', config.INTERNAL_API_SECRET);

    expect(res.status).toBe(404);
  });
});

// ─────────────────────────────────────────────────────────────────────
// POST /api/orders/square-off
// ─────────────────────────────────────────────────────────────────────

describe('POST /api/orders/square-off', () => {

  test('converts a MARKET square-off into a marketable LIMIT (Zerodha rejects raw MARKET)', async () => {
    kite.placeOrder.mockResolvedValue({ order_id: 'SQ-001' });
    kite.getLTP.mockResolvedValue({ 'NSE:RELIANCE': { last_price: 1000 } });

    const res = await request(app)
      .post('/api/orders/square-off')
      .set('X-Internal-Secret', config.INTERNAL_API_SECRET)
      .send({
        ticker: 'RELIANCE',
        shares: 5,
        order_type: 'MARKET',
        product_type: 'MIS',
        idempotency_key: 'sq-reliance-market-1',
      });

    expect(res.status).toBe(202);
    expect(res.body.success).toBe(false);
    expect(res.body.state).toBe('CANCELLED');
    expect(res.body.complete).toBe(false);
    expect(res.body.order_id).toBeDefined();

    // Verify Kite was called with a marketable LIMIT, never a raw MARKET order.
    expect(kite.placeOrder).toHaveBeenCalledTimes(1);
    const orderParams = kite.placeOrder.mock.calls[0][0];
    expect(orderParams.transaction_type).toBe('SELL');
    expect(orderParams.quantity).toBe(5);
    expect(orderParams.tradingsymbol).toBe('RELIANCE');
    expect(orderParams.order_type).toBe('LIMIT');
    expect(orderParams.price).toBe(995);   // snapToTick(1000 * 0.995, down)
    expect(executor.reconcilePlacedOrder).toHaveBeenCalledWith(
      'SQ-001', 5, { ticker: 'RELIANCE', product: 'MIS' }
    );
  });

  test('returns COMPLETE only when broker history confirms the full fill', async () => {
    kite.placeOrder.mockResolvedValue({ order_id: 'SQ-FILLED' });
    executor.reconcilePlacedOrder.mockResolvedValue({ state: 'COMPLETE', terminal: true, filledQuantity: 5, fillPrice: 998 });
    kite.getLTP.mockResolvedValue({ 'NSE:RELIANCE': { last_price: 1000 } });
    const res = await request(app).post('/api/orders/square-off')
      .set('X-Internal-Secret', config.INTERNAL_API_SECRET)
      .send({ ticker: 'RELIANCE', shares: 5, order_type: 'MARKET', product_type: 'MIS', idempotency_key: 'sq-reliance-complete-1' });
    expect(res.status).toBe(200);
    expect(res.body).toEqual(expect.objectContaining({ success: true, state: 'COMPLETE', complete: true, filled_quantity: 5 }));
  });

  test('reports PARTIAL without claiming the position is closed', async () => {
    kite.placeOrder.mockResolvedValue({ order_id: 'SQ-PART' });
    executor.reconcilePlacedOrder.mockResolvedValue({ state: 'PARTIAL', terminal: true, filledQuantity: 2, fillPrice: 999 });
    const res = await request(app).post('/api/orders/square-off')
      .set('X-Internal-Secret', config.INTERNAL_API_SECRET)
      .send({ ticker: 'TCS', shares: 5, order_type: 'LIMIT', limit_price: 999, product_type: 'CNC', idempotency_key: 'sq-tcs-partial-1' });
    expect(res.status).toBe(202);
    expect(res.body).toEqual(expect.objectContaining({ success: false, state: 'PARTIAL', complete: false, filled_quantity: 2, remaining_quantity: 3 }));
  });

  test('ambiguous square-off submission is looked up once and never resubmitted', async () => {
    kite.placeOrder.mockRejectedValue(new Error('response timeout'));
    kite.getOrders.mockResolvedValue([]);
    const res = await request(app).post('/api/orders/square-off')
      .set('X-Internal-Secret', config.INTERNAL_API_SECRET)
      .send({ ticker: 'TCS', shares: 5, order_type: 'LIMIT', limit_price: 999, product_type: 'CNC', idempotency_key: 'sq-tcs-ambiguous-1' });
    expect(res.status).toBe(503);
    expect(res.body).toEqual(expect.objectContaining({ state: 'UNKNOWN', complete: false }));
    expect(kite.placeOrder).toHaveBeenCalledTimes(1);
    expect(kite.getOrders).toHaveBeenCalledTimes(2); // pre-flight + post-timeout recovery
  });

  test('concurrent requests with the same idempotency key submit exactly one SELL', async () => {
    kite.getOrders.mockResolvedValue([]);
    kite.placeOrder.mockImplementation(async () => {
      await new Promise(resolve => setTimeout(resolve, 10));
      return { order_id: 'SQ-CONCURRENT' };
    });
    executor.reconcilePlacedOrder.mockResolvedValue({
      state: 'COMPLETE', terminal: true, filledQuantity: 5, fillPrice: 999,
    });
    const payload = {
      ticker: 'TCS', shares: 5, order_type: 'LIMIT', limit_price: 999,
      product_type: 'CNC', idempotency_key: 'sq-concurrent-same-key',
    };
    const [first, second] = await Promise.all([
      request(app).post('/api/orders/square-off').set('X-Internal-Secret', config.INTERNAL_API_SECRET).send(payload),
      request(app).post('/api/orders/square-off').set('X-Internal-Secret', config.INTERNAL_API_SECRET).send(payload),
    ]);
    expect(first.status).toBe(200);
    expect(second.status).toBe(200);
    expect(first.body.order_id).toBe('SQ-CONCURRENT');
    expect(second.body.order_id).toBe('SQ-CONCURRENT');
    expect(kite.placeOrder).toHaveBeenCalledTimes(1);
  });

  test('includes limit_price for LIMIT orders', async () => {
    kite.placeOrder.mockResolvedValue({ order_id: 'SQ-002' });

    const res = await request(app)
      .post('/api/orders/square-off')
      .set('X-Internal-Secret', config.INTERNAL_API_SECRET)
      .send({
        ticker: 'TCS',
        shares: 3,
        order_type: 'LIMIT',
        limit_price: 3500,
        product_type: 'CNC',
        idempotency_key: 'sq-tcs-limit-1',
      });

    expect(res.status).toBe(202);
    const orderParams = kite.placeOrder.mock.calls[0][0];
    expect(orderParams.price).toBe(3500);
    expect(orderParams.order_type).toBe('LIMIT');
  });

  test('rejects LIMIT order without limit_price', async () => {
    const res = await request(app)
      .post('/api/orders/square-off')
      .set('X-Internal-Secret', config.INTERNAL_API_SECRET)
      .send({
        ticker: 'TCS',
        shares: 3,
        order_type: 'LIMIT',
        product_type: 'CNC',
        idempotency_key: 'sq-tcs-missing-price-1',
      });

    expect(res.status).toBe(400);
  });

  test('rejects without internal secret', async () => {
    const res = await request(app)
      .post('/api/orders/square-off')
      .send({
        ticker: 'TCS',
        shares: 3,
        order_type: 'MARKET',
        product_type: 'CNC',
        idempotency_key: 'sq-tcs-no-auth-1',
      });

    expect(res.status).toBe(403);
  });

  test('rejects invalid order_type', async () => {
    const res = await request(app)
      .post('/api/orders/square-off')
      .set('X-Internal-Secret', config.INTERNAL_API_SECRET)
      .send({
        ticker: 'TCS',
        shares: 3,
        order_type: 'STOP_LOSS',
        product_type: 'CNC',
        idempotency_key: 'sq-tcs-invalid-type-1',
      });

    // Zod validation should reject
    expect(res.status).toBe(422);
  });

  test('rejects zero shares', async () => {
    const res = await request(app)
      .post('/api/orders/square-off')
      .set('X-Internal-Secret', config.INTERNAL_API_SECRET)
      .send({
        ticker: 'TCS',
        shares: 0,
        order_type: 'MARKET',
        product_type: 'CNC',
        idempotency_key: 'sq-tcs-zero-shares-1',
      });

    expect(res.status).toBe(422);
  });
});

// ─────────────────────────────────────────────────────────────────────
// POST /api/orders/execute
// ─────────────────────────────────────────────────────────────────────

describe('POST /api/orders/execute', () => {

  test('returns 401 without session auth', async () => {
    const res = await request(app)
      .post('/api/orders/execute')
      .send({ signal_id: '550e8400-e29b-41d4-a716-446655440000' });

    expect(res.status).toBe(401);
  });

  test('executes PENDING signal and returns success', async () => {
    const signalId = '550e8400-e29b-41d4-a716-446655440000';
    const signalPayload = JSON.stringify({
      ticker: 'RELIANCE', close: 1000, shares: 5,
      stop_loss: 950, target_1: 1075, target_2: 1150,
      capital_at_risk: 250,
    });

    // Mock transaction: return the signal row
    mockTransaction.mockImplementation((fn) => {
      return () => fn(); // execute the transaction function
    });
    // Inside the transaction, prepare().get() returns the row
    mockGet.mockReturnValue({ status: 'PENDING', payload_json: signalPayload });
    mockRun.mockReturnValue({});

    executor.executeSignal.mockResolvedValue({
      orderId: 'ORD-001',
      fillPrice: 1005,
    });

    const res = await request(app)
      .post('/api/orders/execute')
      .set('x-test-auth', 'true')
      .send({ signal_id: signalId });

    expect(res.status).toBe(200);
    expect(res.body.success).toBe(true);
    expect(res.body.order_id).toBe('ORD-001');
    expect(res.body.fill_price).toBe(1005);
  });

  test('returns 409 for non-PENDING signal (ReplayAttackError)', async () => {
    const signalId = '550e8400-e29b-41d4-a716-446655440000';

    // Mock transaction to throw ReplayAttackError
    const { ReplayAttackError } = require('../../utils/errors');
    mockTransaction.mockImplementation((fn) => {
      return () => { throw new ReplayAttackError('Signal is already EXECUTED'); };
    });

    const res = await request(app)
      .post('/api/orders/execute')
      .set('x-test-auth', 'true')
      .send({ signal_id: signalId });

    expect(res.status).toBe(409);
  });

  test('returns 404 for non-existent signal', async () => {
    mockTransaction.mockImplementation((fn) => {
      return () => { throw new Error('Signal not found'); };
    });

    const res = await request(app)
      .post('/api/orders/execute')
      .set('x-test-auth', 'true')
      .send({ signal_id: '550e8400-e29b-41d4-a716-446655440000' });

    expect(res.status).toBe(404);
  });

  test('rejects invalid UUID format', async () => {
    const res = await request(app)
      .post('/api/orders/execute')
      .set('x-test-auth', 'true')
      .send({ signal_id: 'not-a-uuid' });

    expect(res.status).toBe(422);
  });

  test('reverts to PENDING on execution failure', async () => {
    const signalId = '550e8400-e29b-41d4-a716-446655440000';
    const signalPayload = JSON.stringify({
      ticker: 'RELIANCE', close: 1000, shares: 5,
      stop_loss: 950, target_1: 1075, target_2: 1150,
      capital_at_risk: 250,
    });

    mockTransaction.mockImplementation((fn) => {
      return () => {
        mockGet.mockReturnValue({ status: 'PENDING', payload_json: signalPayload });
        return fn();
      };
    });

    executor.executeSignal.mockRejectedValue(new Error('Kite API down'));

    const res = await request(app)
      .post('/api/orders/execute')
      .set('x-test-auth', 'true')
      .send({ signal_id: signalId });

    // Should return 500 (error propagated)
    expect(res.status).toBe(500);

    // The revert SQL should have been called (UPDATE status='PENDING')
    const revertCalls = mockPrepare.mock.calls.filter(c =>
      typeof c[0] === 'string' && c[0].includes('PENDING') && c[0].includes('UPDATE')
    );
    expect(revertCalls.length).toBeGreaterThanOrEqual(1);
  });

  test('keeps execution locked when placement outcome may hold a position', async () => {
    const signalId = '550e8400-e29b-41d4-a716-446655440000';
    mockTransaction.mockImplementation((fn) => () => {
      mockGet.mockReturnValue({ status: 'PENDING', payload_json: JSON.stringify({ ticker: 'RELIANCE' }) });
      return fn();
    });
    const uncertain = new Error('unknown broker outcome');
    uncertain.positionHeld = true;
    uncertain.outcomeUnknown = true;
    executor.executeSignal.mockRejectedValue(uncertain);

    const res = await request(app).post('/api/orders/execute')
      .set('x-test-auth', 'true').send({ signal_id: signalId });
    expect(res.status).toBe(500);
    const pendingUpdates = mockPrepare.mock.calls.filter(c =>
      typeof c[0] === 'string' && c[0].includes("status = 'PENDING'")
    );
    expect(pendingUpdates).toHaveLength(0);
  });
});
