/**
 * Integration tests for routes/token.js
 *
 * Tests:
 * - GET /api/token - returns token data with internal auth
 * - POST /api/token/invalidate - marks token expired, sends Telegram alert
 */

// ── Mock dependencies BEFORE require ──
jest.mock('../../services/telegram', () => ({
  bot: { on: jest.fn(), sendMessage: jest.fn() },
  isValidChat: jest.fn(() => true),
  sendSignalAlert: jest.fn(),
  sendAlert: jest.fn(),
}));

jest.mock('../../services/token-store', () => ({
  isValid: jest.fn(),
  getToken: jest.fn(),
  getStatus: jest.fn(),
  markExpired: jest.fn(),
}));

jest.mock('../../db/index', () => ({
  signalsDb: { prepare: jest.fn().mockReturnValue({ run: jest.fn(), get: jest.fn() }) },
  appDb: { prepare: jest.fn().mockReturnValue({ run: jest.fn(), get: jest.fn() }) },
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
  ZERODHA_API_KEY: 'fake_api_key_12345678',
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
const tokenStore = require('../../services/token-store');
const telegram = require('../../services/telegram');

let app;

beforeAll(() => {
  app = express();
  app.use(express.json());
  app.use('/api/token', require('../../routes/token'));

  // Error handler
  app.use((err, req, res, next) => {
    const statusCode = err.statusCode || 500;
    res.status(statusCode).json({ error: err.type || 'error', message: err.message });
  });
});

beforeEach(() => {
  jest.clearAllMocks();
});

// ─────────────────────────────────────────────────────────────────────
// GET /api/token
// ─────────────────────────────────────────────────────────────────────

describe('GET /api/token', () => {

  test('returns token data with valid internal auth', async () => {
    tokenStore.isValid.mockReturnValue(true);
    tokenStore.getToken.mockReturnValue('test-access-token-123');
    tokenStore.getStatus.mockReturnValue({
      status: 'active',
      generatedAt: '2025-06-10T09:00:00Z',
    });

    const res = await request(app)
      .get('/api/token')
      .set('Authorization', `Bearer ${config.INTERNAL_API_SECRET}`);

    expect(res.status).toBe(200);
    expect(res.body.access_token).toBe('test-access-token-123');
    expect(res.body.generated_at).toBe('2025-06-10T09:00:00Z');
    expect(res.body.api_key).toBe(config.ZERODHA_API_KEY);
  });

  test('returns 401 when no valid token exists', async () => {
    tokenStore.isValid.mockReturnValue(false);
    tokenStore.getStatus.mockReturnValue({
      status: 'expired',
      generatedAt: null,
    });

    const res = await request(app)
      .get('/api/token')
      .set('Authorization', `Bearer ${config.INTERNAL_API_SECRET}`);

    expect(res.status).toBe(401);
    expect(res.body.error).toBe('no_token');
  });

  test('returns 401 without auth header', async () => {
    const res = await request(app)
      .get('/api/token');

    expect(res.status).toBe(401);
    expect(res.body.error).toBe('unauthorized');
  });

  test('returns 401 with wrong Bearer token', async () => {
    const res = await request(app)
      .get('/api/token')
      .set('Authorization', 'Bearer wrong_token_value_here');

    expect(res.status).toBe(401);
  });

  test('returns 401 with non-Bearer auth', async () => {
    const res = await request(app)
      .get('/api/token')
      .set('Authorization', 'Basic dGVzdDp0ZXN0');

    expect(res.status).toBe(401);
  });
});

// ─────────────────────────────────────────────────────────────────────
// POST /api/token/invalidate
// ─────────────────────────────────────────────────────────────────────

describe('POST /api/token/invalidate', () => {

  test('marks token as expired with valid auth', async () => {
    const res = await request(app)
      .post('/api/token/invalidate')
      .set('Authorization', `Bearer ${config.INTERNAL_API_SECRET}`);

    expect(res.status).toBe(200);
    expect(res.body.success).toBe(true);
    expect(tokenStore.markExpired).toHaveBeenCalledTimes(1);
  });

  test('sends Telegram alert on invalidation', async () => {
    await request(app)
      .post('/api/token/invalidate')
      .set('Authorization', `Bearer ${config.INTERNAL_API_SECRET}`);

    expect(telegram.sendAlert).toHaveBeenCalledTimes(1);
    const alertMsg = telegram.sendAlert.mock.calls[0][0];
    expect(alertMsg).toContain('Token');
  });

  test('returns 401 without auth', async () => {
    const res = await request(app)
      .post('/api/token/invalidate');

    expect(res.status).toBe(401);
    expect(tokenStore.markExpired).not.toHaveBeenCalled();
  });

  test('returns 401 with invalid token', async () => {
    const res = await request(app)
      .post('/api/token/invalidate')
      .set('Authorization', 'Bearer invalid_secret_value_here');

    expect(res.status).toBe(401);
    expect(tokenStore.markExpired).not.toHaveBeenCalled();
  });
});
