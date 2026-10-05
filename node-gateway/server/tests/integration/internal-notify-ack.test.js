/**
 * [EXPIRY-OUTBOX 2026-10-05] POST /api/internal/notify delivery acknowledgement.
 *
 * Callers with a durable outbox send require_delivery: a refused Telegram send
 * must answer non-2xx (so the outbox keeps the notice) and must not also start
 * the gateway's background retry (which would duplicate). Legacy callers keep
 * the old always-200 contract with the gateway owning retries.
 */
const express = require('express');
const request = require('supertest');

const mockSendAlert = jest.fn();
const mockSendAlertOnce = jest.fn();
jest.mock('../../services/telegram', () => ({ sendAlert: mockSendAlert, sendAlertOnce: mockSendAlertOnce }));
jest.mock('../../services/executor', () => ({ executeSignal: jest.fn() }));
jest.mock('../../services/cas-eligibility', () => ({ entrySessionVerdict: jest.fn() }));
jest.mock('../../utils/market-hours', () => ({ stampSessionPhaseForSignal: jest.fn() }));
jest.mock('../../db/index', () => ({ signalsDb: { prepare: jest.fn(), transaction: (fn) => () => fn() } }));

const mockConfig = {
  INTERNAL_API_SECRET: 'test_internal_secret_32chars_long',
  PYTHON_ENGINE_URL: 'http://localhost:8000',
  PYTHON_ENGINE_TIMEOUT_MS: 5000,
  LOG_LEVEL: 'error',
};
jest.mock('../../config', () => mockConfig);

const app = express();
app.use(express.json());
app.use('/api/internal', require('../../routes/internal'));
app.use((err, req, res, next) => res.status(err.statusCode || 500).json({ error: err.type })); // eslint-disable-line no-unused-vars

const post = (body) => request(app)
  .post('/api/internal/notify')
  .set('X-Internal-Secret', mockConfig.INTERNAL_API_SECRET)
  .send(body);

beforeEach(() => jest.clearAllMocks());

test('require_delivery: a refused send answers 502 and leaves retry to the caller', async () => {
  mockSendAlertOnce.mockResolvedValue(false);
  const res = await post({ message: 'A: BUY 1 lot', require_delivery: true });
  expect(res.status).toBe(502);
  expect(res.body).toEqual({ success: false, delivered: false });
  expect(mockSendAlertOnce).toHaveBeenCalledTimes(1);
  expect(mockSendAlert).not.toHaveBeenCalled();
});

test('require_delivery: an accepted send answers 200 delivered', async () => {
  mockSendAlertOnce.mockResolvedValue(true);
  const res = await post({ message: 'A: BUY 1 lot', require_delivery: true });
  expect(res.status).toBe(200);
  expect(res.body).toEqual({ success: true, delivered: true });
  expect(mockSendAlertOnce.mock.calls[0][0]).toContain('A: BUY 1 lot');
});

test('legacy callers keep 200 and the gateway-owned retry', async () => {
  mockSendAlert.mockResolvedValue(false);
  const res = await post({ message: 'watchdog' });
  expect(res.status).toBe(200);
  expect(res.body).toEqual({ success: true, delivered: false });
  expect(mockSendAlert).toHaveBeenCalledTimes(1);
  expect(mockSendAlertOnce).not.toHaveBeenCalled();
});
