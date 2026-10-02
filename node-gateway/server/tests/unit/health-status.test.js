const express = require('express');
const request = require('supertest');

const mockUndeliveredAlertCount = jest.fn();
const mockGetStatus = jest.fn();
const mockPrepare = jest.fn();

jest.mock('../../config', () => ({
  TELEGRAM_MODE: 'webhook',
  PYTHON_ENGINE_URL: 'http://python-engine:8000',
}));
jest.mock('../../services/token-store', () => ({ getStatus: mockGetStatus }));
jest.mock('../../utils/market-hours', () => ({
  isMarketOpen: () => true,
  currentSessionPhase: () => 'CONTINUOUS_TRADING',
  sessionPhase: () => 'CONTINUOUS_TRADING',
}));
jest.mock('../../db/index', () => ({
  signalsDb: { prepare: mockPrepare },
}));
jest.mock('../../services/telegram', () => ({
  undeliveredAlertCount: mockUndeliveredAlertCount,
}));
jest.mock('../../release-identity', () => ({
  releaseIdentity: () => ({ component: 'node-gateway' }),
}));

const router = require('../../routes/health');

function app() {
  const instance = express();
  instance.use('/health', router);
  return instance;
}

function configureReadOnlyDb() {
  mockPrepare.mockImplementation((sql) => {
    expect(sql.trim().toUpperCase()).toMatch(/^SELECT\b/);
    if (sql.includes('received_signals WHERE status')) return { get: () => ({ c: 0 }) };
    if (sql.includes('executed_orders WHERE sync_to_b')) return { get: () => ({ c: 0 }) };
    return { get: () => undefined };
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  mockGetStatus.mockReturnValue({ status: 'valid', generatedAt: null });
  configureReadOnlyDb();
  global.fetch = jest.fn().mockResolvedValue({ ok: false });
});

test('health labels an idle Telegram bot as diagnostic rather than connected', async () => {
  mockUndeliveredAlertCount.mockReturnValue(0);

  const response = await request(app()).get('/health');

  expect(response.status).toBe(200);
  expect(response.body.telegram_status).toBe('diagnostic_bot_instance_present');
  expect(response.body.telegram_status_basis).toBe(
    'bot_instance_and_local_dead_letter_backlog_not_transport_probe'
  );
  expect(response.body.undelivered_alerts).toBe(0);
});

test('health surfaces a durable alert backlog without changing queue state', async () => {
  mockUndeliveredAlertCount.mockReturnValue(2);

  const response = await request(app()).get('/health');

  expect(response.status).toBe(200);
  expect(response.body.status).toBe('degraded');
  expect(response.body.telegram_status).toBe('delivery_backlog_present');
  expect(response.body.undelivered_alerts).toBe(2);
  expect(mockPrepare).toHaveBeenCalled();
});
