/**
 * Integration tests for routes/signals.js
 *
 * Tests POST /api/signals webhook endpoint:
 * - HMAC-SHA256 signature verification
 * - Zod schema validation
 * - Staleness check (>5 min)
 * - Duplicate detection
 * - Signal insertion with PENDING status
 * - Telegram notification
 */

const crypto = require('crypto');

// ── Mock dependencies BEFORE require ──
const mockSendSignalAlert = jest.fn().mockResolvedValue(42);
const mockSendAlert = jest.fn();

jest.mock('../../services/telegram', () => ({
  bot: { on: jest.fn(), sendMessage: jest.fn() },
  isValidChat: jest.fn(() => true),
  sendSignalAlert: mockSendSignalAlert,
  sendAlert: mockSendAlert,
}));

const mockPrepare = jest.fn();
const mockRun = jest.fn();
const mockGet = jest.fn();
mockPrepare.mockReturnValue({ run: mockRun, get: mockGet });

jest.mock('../../db/index', () => ({
  signalsDb: { prepare: mockPrepare },
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
const request = require('supertest');
const config = require('../../config');

// Build a minimal Express app with the signals route
let app;

beforeAll(() => {
  app = express();
  app.use(express.json());
  app.use('/api/signals', require('../../routes/signals'));

  // Error handler
  app.use((err, req, res, next) => {
    const statusCode = err.statusCode || 500;
    res.status(statusCode).json({ error: err.type || 'error', message: err.message });
  });
});

beforeEach(() => {
  jest.clearAllMocks();
  mockGet.mockReturnValue(null); // no duplicates by default
  mockRun.mockReturnValue({});
});

// ── Helpers ──
function makeSignalPayload(overrides = {}) {
  return {
    ticker: 'RELIANCE',
    exchange: 'NSE',
    close: 1000,
    stop_loss: 950,
    target_1: 1075,
    target_2: 1150,
    shares: 5,
    capital_at_risk: 250,
    score: 78,
    signal_time: new Date().toISOString(),
    sector: 'ENERGY',
    market_regime: 'BULL',
    net_ev: 180,
    volume_ratio: 2.3,
    rsi_14: 62,
    ...overrides,
  };
}

function signPayload(payload) {
  const raw = JSON.stringify(payload);
  return crypto
    .createHmac('sha256', config.OPENCLAW_WEBHOOK_SECRET)
    .update(raw)
    .digest('hex');
}

// ─────────────────────────────────────────────────────────────────────

describe('POST /api/signals', () => {

  test('accepts valid signal with correct HMAC signature', async () => {
    const payload = makeSignalPayload();
    const sig = signPayload(payload);

    const res = await request(app)
      .post('/api/signals')
      .set('x-webhook-signature', sig)
      .send(payload);

    expect(res.status).toBe(200);
    expect(res.body.received).toBe(true);
    expect(res.body.signal_id).toBeDefined();
  });

  test('sends Telegram alert on valid signal', async () => {
    const payload = makeSignalPayload();
    const sig = signPayload(payload);

    await request(app)
      .post('/api/signals')
      .set('x-webhook-signature', sig)
      .send(payload);

    expect(mockSendSignalAlert).toHaveBeenCalledTimes(1);
    const sentSignal = mockSendSignalAlert.mock.calls[0][0];
    expect(sentSignal.ticker).toBe('RELIANCE');
    expect(sentSignal.signal_id).toBeDefined();
  });

  test('stores telegram_msg_id after alert', async () => {
    mockSendSignalAlert.mockResolvedValue(42);
    const payload = makeSignalPayload();
    const sig = signPayload(payload);

    await request(app)
      .post('/api/signals')
      .set('x-webhook-signature', sig)
      .send(payload);

    // mockRun should be called for UPDATE telegram_msg_id
    const updateCalls = mockPrepare.mock.calls.filter(c =>
      typeof c[0] === 'string' && c[0].includes('telegram_msg_id')
    );
    expect(updateCalls.length).toBeGreaterThanOrEqual(1);
  });

  // ── Signature Verification ──

  test('rejects request with missing signature', async () => {
    const payload = makeSignalPayload();

    const res = await request(app)
      .post('/api/signals')
      .send(payload);

    expect(res.status).toBe(401);
    expect(res.body.error).toBe('unauthorized');
  });

  test('rejects request with invalid signature', async () => {
    const payload = makeSignalPayload();

    const res = await request(app)
      .post('/api/signals')
      .set('x-webhook-signature', 'deadbeef')
      .send(payload);

    expect(res.status).toBe(401);
  });

  // ── Staleness Check ──

  test('rejects signal older than 5 minutes', async () => {
    const staleTime = new Date(Date.now() - 6 * 60 * 1000).toISOString();
    const payload = makeSignalPayload({ signal_time: staleTime });
    const sig = signPayload(payload);

    const res = await request(app)
      .post('/api/signals')
      .set('x-webhook-signature', sig)
      .send(payload);

    // StaleSignalError should result in 4xx
    expect(res.status).toBeGreaterThanOrEqual(400);
  });

  test('accepts signal within 5-minute window', async () => {
    const freshTime = new Date(Date.now() - 2 * 60 * 1000).toISOString();
    const payload = makeSignalPayload({ signal_time: freshTime });
    const sig = signPayload(payload);

    const res = await request(app)
      .post('/api/signals')
      .set('x-webhook-signature', sig)
      .send(payload);

    expect(res.status).toBe(200);
  });

  // ── Duplicate Detection ──

  test('returns duplicate flag for duplicate signal', async () => {
    // Mock DB to return existing signal
    mockGet.mockReturnValue({ 1: 1 });

    const payload = makeSignalPayload();
    const sig = signPayload(payload);

    const res = await request(app)
      .post('/api/signals')
      .set('x-webhook-signature', sig)
      .send(payload);

    expect(res.status).toBe(200);
    expect(res.body.duplicate).toBe(true);
  });

  // ── Zod Validation ──

  test('rejects missing ticker', async () => {
    const payload = makeSignalPayload();
    delete payload.ticker;
    const sig = signPayload(payload);

    const res = await request(app)
      .post('/api/signals')
      .set('x-webhook-signature', sig)
      .send(payload);

    // Zod error caught by global error handler
    expect(res.status).toBeGreaterThanOrEqual(400);
  });

  test('rejects invalid exchange (must be NSE)', async () => {
    const payload = makeSignalPayload({ exchange: 'BSE' });
    const sig = signPayload(payload);

    const res = await request(app)
      .post('/api/signals')
      .set('x-webhook-signature', sig)
      .send(payload);

    expect(res.status).toBeGreaterThanOrEqual(400);
  });

  test('rejects capital_at_risk exceeding 1500', async () => {
    const payload = makeSignalPayload({ capital_at_risk: 1501 });
    const sig = signPayload(payload);

    const res = await request(app)
      .post('/api/signals')
      .set('x-webhook-signature', sig)
      .send(payload);

    expect(res.status).toBeGreaterThanOrEqual(400);
  });

  test('rejects stop_loss above close', async () => {
    const payload = makeSignalPayload({ close: 1000, stop_loss: 1050 });
    const sig = signPayload(payload);

    const res = await request(app)
      .post('/api/signals')
      .set('x-webhook-signature', sig)
      .send(payload);

    expect(res.status).toBeGreaterThanOrEqual(400);
  });

  test('rejects target_1 below close', async () => {
    const payload = makeSignalPayload({ close: 1000, target_1: 990 });
    const sig = signPayload(payload);

    const res = await request(app)
      .post('/api/signals')
      .set('x-webhook-signature', sig)
      .send(payload);

    expect(res.status).toBeGreaterThanOrEqual(400);
  });

  test('rejects shares = 0', async () => {
    const payload = makeSignalPayload({ shares: 0 });
    const sig = signPayload(payload);

    const res = await request(app)
      .post('/api/signals')
      .set('x-webhook-signature', sig)
      .send(payload);

    expect(res.status).toBeGreaterThanOrEqual(400);
  });

  test('rejects negative close price', async () => {
    const payload = makeSignalPayload({ close: -100 });
    const sig = signPayload(payload);

    const res = await request(app)
      .post('/api/signals')
      .set('x-webhook-signature', sig)
      .send(payload);

    expect(res.status).toBeGreaterThanOrEqual(400);
  });

  test('no Telegram alert sent for duplicate signal', async () => {
    mockGet.mockReturnValue({ 1: 1 }); // duplicate

    const payload = makeSignalPayload();
    const sig = signPayload(payload);

    await request(app)
      .post('/api/signals')
      .set('x-webhook-signature', sig)
      .send(payload);

    expect(mockSendSignalAlert).not.toHaveBeenCalled();
  });
});
