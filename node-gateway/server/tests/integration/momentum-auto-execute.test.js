/**
 * [MOMENTUM-AUTO 2026-10-04] POST /api/internal/momentum-auto-execute
 *
 * Automatic Momentum execution must be exactly the EM button's path: off by
 * default, only a registered snapshot (never a live re-fetch), one execution
 * per ticker per day, and a held/unknown outcome stays locked and pages.
 */
const express = require('express');
const request = require('supertest');

const mockSendAlert = jest.fn().mockResolvedValue(true);
jest.mock('../../services/telegram', () => ({ sendAlert: mockSendAlert }));

const mockExecuteSignal = jest.fn();
jest.mock('../../services/executor', () => ({ executeSignal: mockExecuteSignal }));

const mockVerdict = jest.fn(() => Promise.resolve({ allowed: true, phase: 'CONTINUOUS_TRADING', reason: null }));
jest.mock('../../services/cas-eligibility', () => ({ entrySessionVerdict: mockVerdict }));

jest.mock('../../utils/market-hours', () => ({ stampSessionPhaseForSignal: jest.fn(() => 'CONTINUOUS_TRADING') }));

const snapshots = new Map();   // signal_id -> {action, payload_json}
const received = new Map();    // signal_id -> {status, execution_state}
const mockPrepare = jest.fn((sql) => ({
  get: (...args) => {
    if (sql.includes('approved_snapshots')) {
      const row = snapshots.get(args[0]);
      return row && row.action === args[1] ? row : undefined;
    }
    if (sql.includes('received_signals')) return received.get(args[0]);
    return undefined;
  },
  run: (...args) => {
    if (sql.includes('INSERT') && sql.includes('received_signals')) {
      received.set(args[0], { status: 'EXECUTING', execution_state: 'SUBMITTING' });
    } else if (sql.includes('UPDATE') && sql.includes('received_signals')) {
      const id = args[args.length - 1];
      const row = received.get(id);
      if (row) {
        const status = sql.match(/status = '(\w+)'/);
        row.status = status ? status[1] : row.status;
        const state = sql.match(/execution_state = '(\w+)'/);
        row.execution_state = state ? state[1] : (sql.includes('execution_state = ?') ? args[0] : row.execution_state);
      }
    }
    return { changes: 1 };
  },
  all: () => [],
}));
jest.mock('../../db/index', () => ({
  signalsDb: { prepare: mockPrepare, transaction: (fn) => () => fn() },
}));

const mockConfig = {
  INTERNAL_API_SECRET: 'test_internal_secret_32chars_long',
  PYTHON_ENGINE_URL: 'http://localhost:8000',
  PYTHON_ENGINE_TIMEOUT_MS: 5000,
  MOMENTUM_AUTO_EXECUTE: false,
  LOG_LEVEL: 'error',
};
jest.mock('../../config', () => mockConfig);

global.fetch = jest.fn();

const app = express();
app.use(express.json());
app.use('/api/internal', require('../../routes/internal'));
// Same status mapping as app.js's global handler.
app.use((err, req, res, next) => res.status(err.statusCode || 500).json({ error: err.type })); // eslint-disable-line no-unused-vars

const SIG = 'ABC_MOM';
const post = (body = { signal_id: SIG }) => request(app)
  .post('/api/internal/momentum-auto-execute')
  .set('X-Internal-Secret', mockConfig.INTERNAL_API_SECRET)
  .send(body);

function registerSnapshot() {
  snapshots.set(SIG, { action: 'EM', payload_json: JSON.stringify({ ticker: 'ABC', close: 100, shares: 5, stop_loss: 98.8 }) });
}

beforeEach(() => {
  snapshots.clear();
  received.clear();
  jest.clearAllMocks();
  mockConfig.MOMENTUM_AUTO_EXECUTE = false;
  mockExecuteSignal.mockResolvedValue({ orderId: 'OID1', fillPrice: 100.1, shares: 5, stop_loss: 98.9,
                                        target_1: 102, target_2: null, risk_per_share: 1.2 });
});

test('off by default: nothing is executed', async () => {
  registerSnapshot();
  const res = await post();
  expect(res.body).toMatchObject({ executed: false, outcome: 'DISABLED' });
  expect(mockExecuteSignal).not.toHaveBeenCalled();
});

test('executes the registered snapshot once per ticker per day', async () => {
  mockConfig.MOMENTUM_AUTO_EXECUTE = true;
  registerSnapshot();
  const first = await post();
  expect(first.body).toMatchObject({ executed: true, outcome: 'EXECUTED', order_id: 'OID1', fill_price: 100.1 });
  expect(mockExecuteSignal).toHaveBeenCalledTimes(1);
  const [signal, action, intraday] = mockExecuteSignal.mock.calls[0];
  expect(signal).toMatchObject({ ticker: 'ABC', close: 100, shares: 5 });
  expect(signal.signal_id).toMatch(/^ABC_MOM_\d{4}-\d{2}-\d{2}$/);
  expect([action, intraday]).toEqual(['EM', true]);
  const second = await post();
  expect(second.body).toMatchObject({ executed: false, outcome: 'LOCKED', reason: 'already_executed' });
  expect(mockExecuteSignal).toHaveBeenCalledTimes(1);
});

test('never re-fetches live engine data when no snapshot is registered', async () => {
  mockConfig.MOMENTUM_AUTO_EXECUTE = true;
  const res = await post();
  expect(res.body).toMatchObject({ executed: false, outcome: 'FAILED', held: false });
  expect(global.fetch).not.toHaveBeenCalled();
  expect(mockExecuteSignal).not.toHaveBeenCalled();
  expect([...received.values()][0].status).toBe('PENDING');      // the button can still be used
});

test('a closed or CAS session blocks before the lock is taken', async () => {
  mockConfig.MOMENTUM_AUTO_EXECUTE = true;
  registerSnapshot();
  mockVerdict.mockResolvedValueOnce({ allowed: false, phase: 'CLOSED', reason: null });
  const res = await post();
  expect(res.body).toMatchObject({ executed: false, outcome: 'SESSION_BLOCKED', reason: 'market_CLOSED' });
  expect(received.size).toBe(0);
});

test('a held or unknown outcome stays locked and pages the operator', async () => {
  mockConfig.MOMENTUM_AUTO_EXECUTE = true;
  registerSnapshot();
  mockExecuteSignal.mockRejectedValueOnce(Object.assign(new Error('stop and unwind failed'), { positionHeld: true }));
  const res = await post();
  expect(res.body).toMatchObject({ executed: false, outcome: 'FAILED', held: true });
  expect(mockSendAlert).toHaveBeenCalledWith(expect.stringContaining('Do NOT retry'));
  const row = [...received.values()][0];
  expect(row).toMatchObject({ status: 'EXECUTING', execution_state: 'HELD_UNPROTECTED' });
  expect((await post()).body.outcome).toBe('LOCKED');
});

test('rejects ids that are not Momentum ids and calls without the secret', async () => {
  expect((await post({ signal_id: 'ABC' })).status).toBe(422);   // ValidationError
  const res = await request(app).post('/api/internal/momentum-auto-execute').send({ signal_id: SIG });
  expect(res.status).toBe(403);
});
