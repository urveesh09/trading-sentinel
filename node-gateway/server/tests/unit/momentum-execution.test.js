// [DISPATCH-LOCK 2026-10-05] Production audit C1 regression: a filled Momentum
// buy whose EXECUTED record fails must stay locked; a retry places no new buy.
let mockRowStatus;
let mockFailExecutedRecord;

jest.mock('../../config', () => ({}));
jest.mock('../../middleware/logger', () => ({ logger: { warn: jest.fn(), error: jest.fn(), info: jest.fn() } }));
jest.mock('../../db/index', () => ({
  signalsDb: {
    transaction: (fn) => () => fn(),
    prepare: (sql) => ({
      get: () => (mockRowStatus ? { status: mockRowStatus } : undefined),
      run: () => {
        if (sql.includes('INSERT INTO received_signals')) mockRowStatus = 'EXECUTING';
        else if (sql.includes("status = 'EXECUTED'")) {
          if (mockFailExecutedRecord) { mockFailExecutedRecord = false; throw new Error('SQLITE_BUSY'); }
          mockRowStatus = 'EXECUTED';
        } else if (sql.includes("status = 'PENDING'")) mockRowStatus = 'PENDING';
        else if (sql.includes("status = 'EXECUTING'")) mockRowStatus = 'EXECUTING';
      },
    }),
  },
}));
jest.mock('../../services/executor', () => ({ executeSignal: jest.fn() }));
jest.mock('../../services/approved-snapshots', () => ({
  getApprovedSnapshot: () => ({ ticker: 'TEST', close: 100 }),
}));

const executor = require('../../services/executor');
const { executeMomentum } = require('../../services/momentum-execution');

const opts = { signalId: 'TEST_MOM', cleanId: 'TEST', allowLiveFetch: false };
const filled = { orderId: 'O1', shares: 1, stop_loss: 90, target_1: 110, fillPrice: 100, risk_per_share: 10 };

beforeEach(() => {
  mockRowStatus = undefined;
  mockFailExecutedRecord = false;
  executor.executeSignal.mockReset().mockResolvedValue(filled);
});

test('failed EXECUTED record after a fill keeps the lock; retry buys nothing', async () => {
  mockFailExecutedRecord = true;
  const first = await executeMomentum(opts);
  expect(first.outcome).toBe('EXECUTED');
  expect(mockRowStatus).toBe('EXECUTING');
  const second = await executeMomentum(opts);
  expect(second.outcome).toBe('LOCKED');
  expect(executor.executeSignal).toHaveBeenCalledTimes(1);
});

test('post-dispatch executor failure keeps the lock', async () => {
  const err = Object.assign(new Error('fill record failed'), { positionHeld: true, outcomeUnknown: true });
  executor.executeSignal.mockRejectedValue(err);
  const first = await executeMomentum(opts);
  expect(first).toMatchObject({ outcome: 'FAILED', held: true });
  expect((await executeMomentum(opts)).outcome).toBe('LOCKED');
  expect(executor.executeSignal).toHaveBeenCalledTimes(1);
});

test('a flat failure is retryable', async () => {
  executor.executeSignal.mockRejectedValueOnce(Object.assign(new Error('rejected'), { brokerFlat: true }));
  expect((await executeMomentum(opts)).outcome).toBe('FAILED');
  expect(mockRowStatus).toBe('PENDING');
  expect((await executeMomentum(opts)).outcome).toBe('EXECUTED');
  expect(executor.executeSignal).toHaveBeenCalledTimes(2);
});
