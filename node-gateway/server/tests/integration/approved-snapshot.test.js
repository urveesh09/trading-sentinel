/**
 * [HIGH-007 / ROADMAP-4.5 2026-07-13] The executed payload must be the
 * APPROVED payload.
 *
 * Before this change, pressing EXECUTE made node re-fetch the signal from the
 * engine and execute whatever came back. The numbers in the Telegram message
 * -- the ones the operator actually looked at and approved -- were never the
 * numbers that were guaranteed to reach Zerodha:
 *
 *   - Swing: /signals serves `current_signals`, which run_screener REPLACES
 *     wholesale on every run. A re-run between alert and press silently
 *     changes entry / shares / stop.
 *   - Either book: if the re-fetch no longer holds the ticker, the press dies
 *     with "signal not found" and the approved trade is lost. The engine's
 *     momentum list is in-memory, so an engine restart wipes it -- which is
 *     exactly what happened on 2026-07-13 at 09:44.
 *
 * The tests below fail against the pre-fix handler: the first one executes the
 * engine's NEW numbers instead of the approved ones, and the second throws
 * "not found" instead of trading.
 */

const mockBotOn = jest.fn();
const mockAnswerCallbackQuery = jest.fn().mockResolvedValue(true);
const mockEditMessageText = jest.fn().mockResolvedValue(true);

jest.mock('../../services/telegram', () => ({
  bot: {
    on: mockBotOn,
    answerCallbackQuery: mockAnswerCallbackQuery,
    editMessageText: mockEditMessageText,
    sendMessage: jest.fn().mockResolvedValue({ message_id: 1 }),
  },
  isValidChat: jest.fn(),
  sendSignalAlert: jest.fn(),
  sendAlert: jest.fn(),
}));

jest.mock('../../services/executor', () => ({
  executeSignal: jest.fn(),
  syncToEngine: jest.fn(),
}));

jest.mock('../../utils/market-hours', () => ({ isMarketOpen: jest.fn() }));

// ── A tiny in-memory stand-in for the two tables the handler touches ──
const snapshots = new Map();   // signal_id -> {action, payload_json}
const received = new Map();    // signal_id -> {status, ...}

const mockPrepare = jest.fn((sql) => ({
  get: (...args) => {
    if (sql.includes('approved_snapshots')) {
      const [signalId, action] = args;
      const row = snapshots.get(signalId);
      return row && row.action === action ? row : undefined;
    }
    if (sql.includes('received_signals')) {
      return received.get(args[0]);
    }
    return undefined;
  },
  run: (...args) => {
    if (sql.includes('INSERT') && sql.includes('received_signals')) {
      received.set(args[0], { status: 'EXECUTING' });
    } else if (sql.includes('UPDATE') && sql.includes('received_signals')) {
      const id = args[args.length - 1];
      if (received.has(id)) received.get(id).status = args[0];
    }
    return { changes: 1 };
  },
  all: () => [],
}));

jest.mock('../../db/index', () => ({
  signalsDb: { prepare: mockPrepare, transaction: (fn) => () => fn() },
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
}));

global.fetch = jest.fn();

jest.mock('http', () => ({
  createServer: jest.fn(() => ({ listen: jest.fn((p, cb) => cb && cb()), close: jest.fn() })),
}));
jest.mock('../../app', () => ({}));
jest.mock('../../middleware/logger', () => ({
  logger: { info: jest.fn(), error: jest.fn(), warn: jest.fn(), debug: jest.fn() },
  httpLogger: jest.fn(),
}));

const executor = require('../../services/executor');
const telegram = require('../../services/telegram');
const { isMarketOpen } = require('../../utils/market-hours');

let callbackHandler;
try { require('../../index'); } catch (e) { /* only need the bot.on side effect */ }
callbackHandler = mockBotOn.mock.calls.find(c => c[0] === 'callback_query')[1];

function press(action, signalId) {
  const ts = Math.floor(Date.now() / 1000);
  return callbackHandler({
    id: 'cb1',
    data: `${action}:${signalId}:${ts}`,
    message: { text: 'alert', chat: { id: 99999999999 }, message_id: 5 },
    from: { id: 99999999999 },
  });
}

// The numbers the operator SAW and approved.
const APPROVED = {
  ticker: 'RELIANCE', close: 2800, shares: 10, stop_loss: 2750,
  target_1: 2900, capital_at_risk: 500,
};
// What the engine would hand back on a re-fetch AFTER a later screener run.
const DRIFTED = {
  ticker: 'RELIANCE', close: 2850, shares: 9, stop_loss: 2790,
  target_1: 2950, capital_at_risk: 540,
};

beforeEach(() => {
  jest.clearAllMocks();
  snapshots.clear();
  received.clear();
  // The handler's very first line is a chat guard -- without this the mock
  // returns undefined and every press silently returns before doing anything.
  telegram.isValidChat.mockReturnValue(true);
  isMarketOpen.mockReturnValue(true);
  executor.executeSignal.mockResolvedValue({ orderId: 'ORD1' });
});

describe('EXEC (swing) executes the approved snapshot', () => {
  test('executes the APPROVED numbers even when the engine now serves different ones', async () => {
    snapshots.set('RELIANCE', { action: 'EXEC', payload_json: JSON.stringify(APPROVED) });
    received.set('RELIANCE', { status: 'PENDING', payload_json: JSON.stringify({ ...APPROVED, signal_id: 'RELIANCE' }) });
    // The engine has moved on -- a later run_screener replaced current_signals.
    global.fetch.mockResolvedValue({ json: async () => ({ signals: [DRIFTED] }) });

    await press('EXEC', 'RELIANCE');

    expect(executor.executeSignal).toHaveBeenCalledTimes(1);
    const executed = executor.executeSignal.mock.calls[0][0];

    // THE POINT: what executed is what was approved.
    expect(executed.close).toBe(2800);
    expect(executed.shares).toBe(10);
    expect(executed.stop_loss).toBe(2750);

    // And we did not even ask the engine.
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test('blocks execution when no durable snapshot/registration exists', async () => {
    global.fetch.mockResolvedValue({ json: async () => ({ signals: [DRIFTED] }) });

    await press('EXEC', 'RELIANCE');

    expect(global.fetch).not.toHaveBeenCalled();
    expect(executor.executeSignal).not.toHaveBeenCalled();
    expect(telegram.sendAlert).toHaveBeenCalledWith(expect.stringContaining('No broker order placed'));
  });
});

describe('EM (momentum) executes the approved snapshot', () => {
  const APPROVED_MOM = { ...APPROVED, ticker: 'YESBANK', close: 20, shares: 100 };

  test('survives an engine restart that wiped the in-memory momentum list', async () => {
    snapshots.set('YESBANK_MOM', {
      action: 'EM', payload_json: JSON.stringify(APPROVED_MOM),
    });
    // 2026-07-13 09:44: engine restarted, momentum_signals_today is empty.
    global.fetch.mockResolvedValue({ json: async () => ({ signals: [] }) });

    await press('EM', 'YESBANK_MOM');

    // Pre-fix this threw "Momentum signal not found in Engine state" and the
    // approved trade was lost.
    expect(executor.executeSignal).toHaveBeenCalledTimes(1);
    const executed = executor.executeSignal.mock.calls[0][0];
    expect(executed.ticker).toBe('YESBANK');
    expect(executed.close).toBe(20);
    expect(executed.shares).toBe(100);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test('an EXEC snapshot is never used to satisfy an EM press', async () => {
    // Same ticker, but registered for the swing (CNC) book. Momentum is MIS
    // and sized differently -- resolving across actions would place the wrong
    // KIND of order, so the action is part of the key.
    snapshots.set('YESBANK_MOM', {
      action: 'EXEC', payload_json: JSON.stringify(APPROVED_MOM),
    });
    global.fetch.mockResolvedValue({ json: async () => ({ signals: [DRIFTED] }) });

    await press('EM', 'YESBANK_MOM');

    // Must have ignored the EXEC snapshot and gone to the engine instead.
    expect(global.fetch).toHaveBeenCalled();
  });
});
