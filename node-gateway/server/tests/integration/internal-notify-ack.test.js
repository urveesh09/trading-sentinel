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
const mockSendAlertOnceDetailed = jest.fn();
jest.mock('../../services/telegram', () => ({
  sendAlert: mockSendAlert, sendAlertOnce: mockSendAlertOnce, sendAlertOnceDetailed: mockSendAlertOnceDetailed,
}));
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

test('require_delivery: a transient refusal answers 502 and leaves retry to the caller', async () => {
  mockSendAlertOnceDetailed.mockResolvedValue({ delivered: false, rejected: false, status: null });
  const res = await post({ message: 'A: BUY 1 lot', require_delivery: true });
  expect(res.status).toBe(502);
  expect(res.body).toEqual({ success: false, delivered: false, rejected: false, telegram_status: null });
  expect(mockSendAlertOnceDetailed).toHaveBeenCalledTimes(1);
  expect(mockSendAlert).not.toHaveBeenCalled();
});

test('require_delivery: a message Telegram rejects answers 422', async () => {
  mockSendAlertOnceDetailed.mockResolvedValue({ delivered: false, rejected: true, status: 400 });
  const res = await post({ message: 'x'.repeat(5000), require_delivery: true });
  expect(res.status).toBe(422);
  expect(res.body).toEqual({ success: false, delivered: false, rejected: true, telegram_status: 400 });
  expect(mockSendAlert).not.toHaveBeenCalled();
});

test('require_delivery: an accepted send answers 200 delivered', async () => {
  mockSendAlertOnceDetailed.mockResolvedValue({ delivered: true, rejected: false });
  const res = await post({ message: 'A: BUY 1 lot', require_delivery: true });
  expect(res.status).toBe(200);
  expect(res.body).toEqual({ success: true, delivered: true });
  expect(mockSendAlertOnceDetailed.mock.calls[0][0]).toContain('A: BUY 1 lot');
});

test('legacy callers keep 200 and the gateway-owned retry', async () => {
  mockSendAlert.mockResolvedValue(false);
  const res = await post({ message: 'watchdog' });
  expect(res.status).toBe(200);
  expect(res.body).toEqual({ success: true, delivered: false });
  expect(mockSendAlert).toHaveBeenCalledTimes(1);
  expect(mockSendAlertOnce).not.toHaveBeenCalled();
});

test('best effort: a message over the Telegram limit goes out as numbered parts (O9-M1)', async () => {
  mockSendAlert.mockResolvedValue(true);
  const long = Array.from({ length: 300 }, (_, i) => `line ${i}: ${'x'.repeat(40)}`).join('\n');
  const res = await post({ message: long });
  expect(res.status).toBe(200);
  expect(res.body).toEqual({ success: true, delivered: true });
  const sent = mockSendAlert.mock.calls.map(([text]) => text);
  expect(sent.length).toBeGreaterThan(1);
  sent.forEach((text, i) => {
    expect(text.length).toBeLessThanOrEqual(4096);
    expect(text.startsWith(`[part ${i + 1}/${sent.length}] `)).toBe(true);
  });
  const rebuilt = sent.map((t) => t.replace(/^\[part \d+\/\d+\] /, '')).join('\n');
  expect(rebuilt).toBe(`🚨 [SYSTEM ALERT]\n${long}`);
});

test('best effort: one failed part reports delivered false (O9-M1)', async () => {
  mockSendAlert.mockResolvedValueOnce(true).mockResolvedValue(false);
  const res = await post({ message: 'y'.repeat(9000) });
  expect(res.body).toEqual({ success: true, delivered: false });
  expect(mockSendAlert.mock.calls.length).toBeGreaterThan(1);
});
