const express = require('express');
const request = require('supertest');

const mockUndeliveredAlertSummary = jest.fn();
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
  undeliveredAlertSummary: mockUndeliveredAlertSummary,
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

function configureReadOnlyDb(counts = {}) {
  const c = { pending: 0, stalePending: 0, unsynced: 0, actionable: 0, ...counts };
  mockPrepare.mockImplementation((sql) => {
    expect(sql.trim().toUpperCase()).toMatch(/^SELECT\b/);
    if (sql.includes('received_signals WHERE status')) {
      return { get: () => ({ c: sql.includes('received_at <') ? c.stalePending : c.pending }) };
    }
    if (sql.includes('executed_orders WHERE sync_to_b')) {
      return { get: () => ({ c: sql.includes('placed_at >=') ? c.actionable : c.unsynced }) };
    }
    return { get: () => undefined };
  });
}

const engineUp = () => { global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({}) }); };

beforeEach(() => {
  jest.clearAllMocks();
  mockGetStatus.mockReturnValue({ status: 'valid', generatedAt: null });
  configureReadOnlyDb();
  global.fetch = jest.fn().mockResolvedValue({ ok: false });
});

test('health labels an idle Telegram bot as diagnostic rather than connected', async () => {
  mockUndeliveredAlertSummary.mockReturnValue({ open: 0, recent: 0, oldest_ts: null });

  const response = await request(app()).get('/health');

  expect(response.status).toBe(200);
  expect(response.body.telegram_status).toBe('diagnostic_bot_instance_present');
  expect(response.body.telegram_status_basis).toBe(
    'bot_instance_and_local_dead_letter_backlog_not_transport_probe'
  );
  expect(response.body.undelivered_alerts).toBe(0);
});

test('health surfaces a durable alert backlog without changing queue state', async () => {
  mockUndeliveredAlertSummary.mockReturnValue({ open: 2, recent: 2, oldest_ts: '2026-10-23T05:00:00.000Z' });

  const response = await request(app()).get('/health');

  expect(response.status).toBe(200);
  expect(response.body.status).toBe('degraded');
  expect(response.body.telegram_status).toBe('delivery_backlog_present');
  expect(response.body.undelivered_alerts).toBe(2);
  expect(mockPrepare).toHaveBeenCalled();
});

// [S23-H1] Old, settled backlog is reported, not alarmed.
test('old settled backlog is reported without degrading health', async () => {
  engineUp();
  // Oct 23: 8 dead letters (8-24 Sep), 10 PENDING from 29 Jun-7 Oct,
  // 4 CANCELLED/REJECTED orders never synced.
  mockUndeliveredAlertSummary.mockReturnValue({ open: 8, recent: 0, oldest_ts: '2026-07-31T08:49:00.000Z' });
  configureReadOnlyDb({ pending: 10, stalePending: 10, unsynced: 4, actionable: 0 });

  const response = await request(app()).get('/health');

  expect(response.body.status).toBe('ok');
  expect(response.body.telegram_status).toBe('stale_delivery_backlog_present');
  expect(response.body).toMatchObject({ undelivered_alerts: 8, unsynced_orders: 4, pending_signals: 10,
    recent_undelivered_alerts: 0, actionable_unsynced_orders: 0 });
  expect(response.body.stale_backlog).toMatchObject({ recent_hours: 24, undelivered_alerts: 8,
    unsynced_settled_orders: 4, pending_signals: 10, oldest_undelivered_at: '2026-07-31T08:49:00.000Z' });
});

test('a new dead letter or an unsynced order that may have filled still degrades health', async () => {
  engineUp();
  mockUndeliveredAlertSummary.mockReturnValue({ open: 9, recent: 1, oldest_ts: '2026-07-31T08:49:00.000Z' });
  configureReadOnlyDb();
  let response = await request(app()).get('/health');
  expect(response.body.status).toBe('degraded');
  expect(response.body.telegram_status).toBe('delivery_backlog_present');

  mockUndeliveredAlertSummary.mockReturnValue({ open: 0, recent: 0, oldest_ts: null });
  configureReadOnlyDb({ unsynced: 1, actionable: 1 });     // e.g. an old COMPLETE order never synced
  response = await request(app()).get('/health');
  expect(response.body.status).toBe('degraded');
  expect(response.body.actionable_unsynced_orders).toBe(1);
});
