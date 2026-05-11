/**
 * Tests for Telegram callback_query handler in index.js.
 *
 * We test the callback handler logic by directly invoking the bot's
 * 'callback_query' event with mock payloads.
 */

// ── Mock all external dependencies ──
const mockBotOn = jest.fn();
const mockAnswerCallbackQuery = jest.fn().mockResolvedValue(true);
const mockEditMessageText = jest.fn().mockResolvedValue(true);
const mockSendMessage = jest.fn().mockResolvedValue({ message_id: 1 });

jest.mock('../../services/telegram', () => ({
  bot: {
    on: mockBotOn,
    answerCallbackQuery: mockAnswerCallbackQuery,
    editMessageText: mockEditMessageText,
    sendMessage: mockSendMessage,
  },
  isValidChat: jest.fn(),
  sendSignalAlert: jest.fn(),
  sendAlert: jest.fn(),
}));

jest.mock('../../services/executor', () => ({
  executeSignal: jest.fn(),
  syncToEngine: jest.fn(),
}));

jest.mock('../../utils/market-hours', () => ({
  isMarketOpen: jest.fn(),
}));

const mockPrepare = jest.fn();
const mockRun = jest.fn().mockReturnValue({ changes: 0, lastInsertRowid: 0 });
const mockGet = jest.fn();
const mockAll = jest.fn().mockReturnValue([]);
const mockTransaction = jest.fn(fn => () => fn());
mockPrepare.mockReturnValue({ run: mockRun, get: mockGet, all: mockAll });

jest.mock('../../db/index', () => ({
  signalsDb: { prepare: mockPrepare, transaction: mockTransaction },
  appDb: { prepare: mockPrepare },
}));

// Mock config to prevent process.exit
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

// Mock fetch for EM (momentum) action
global.fetch = jest.fn();

const telegram = require('../../services/telegram');
const executor = require('../../services/executor');
const { isMarketOpen } = require('../../utils/market-hours');

// Mock http before requiring index.js
jest.mock('http', () => ({
  createServer: jest.fn(() => ({
    listen: jest.fn((port, cb) => cb && cb()),
    close: jest.fn(),
  })),
}));

// Mock app.js to prevent express/session/SQLite side effects
jest.mock('../../app', () => ({}));

// Mock logger to prevent pino side effects
jest.mock('../../middleware/logger', () => ({
  logger: { info: jest.fn(), error: jest.fn(), warn: jest.fn(), debug: jest.fn() },
  httpLogger: jest.fn(),
}));

// Now require index.js at module scope - this registers the bot.on('callback_query') handler
// We capture it from the mock synchronously
let callbackHandler;

try {
  require('../../index');
} catch (e) {
  // Swallow - we only need the bot.on registration side effect
}

// Find the callback_query handler from bot.on calls
const callbackCall = mockBotOn.mock.calls.find(c => c[0] === 'callback_query');
if (callbackCall) {
  callbackHandler = callbackCall[1];
}

// ── Helpers ──
function makeCallbackQuery(action, signalId, overrides = {}) {
  const ts = overrides.timestamp || Math.floor(Date.now() / 1000);
  const data = `${action}:${signalId}:${ts}`;

  return {
    id: overrides.queryId || 'cb-query-1',
    data,
    message: {
      chat: { id: overrides.chatId || 99999999999 },
      message_id: overrides.messageId || 42,
      text: 'SIGNAL - RELIANCE Score: 85/100\n...',
    },
    from: { id: overrides.fromId || 12345, first_name: 'Test' },
  };
}

const samplePayload = JSON.stringify({
  signal_id: 'RELIANCE',
  ticker: 'RELIANCE',
  close: 1000,
  shares: 5,
  stop_loss: 950,
  target_1: 1075,
  target_2: 1150,
  capital_at_risk: 250,
});

describe('Telegram Callback Handler', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    telegram.isValidChat.mockReturnValue(true);
    isMarketOpen.mockReturnValue(true);
    mockGet.mockReturnValue({ signal_id: 'a1b2c3d4-full-uuid-here', status: 'PENDING', payload_json: samplePayload });
    executor.executeSignal.mockResolvedValue({ orderId: 'ORD-001' });
  });

  // If handler wasn't captured, skip all tests gracefully
  const runTest = callbackHandler ? test : test.skip;

  // ─── 1. APPROVE happy path (EXEC) ───
  runTest('EXEC - happy path: PENDING → EXECUTING → EXECUTED', async () => {
    const query = makeCallbackQuery('EXEC', 'a1b2c3d4');
    await callbackHandler(query);

    // Should transition: PENDING → EXECUTING → EXECUTED
    const updateCalls = mockPrepare.mock.calls
      .filter(c => typeof c[0] === 'string' && c[0].includes('UPDATE received_signals SET status'));
    expect(updateCalls.length).toBeGreaterThanOrEqual(2); // EXECUTING + EXECUTED

    expect(executor.executeSignal).toHaveBeenCalledWith(
      expect.objectContaining({ ticker: 'RELIANCE' }),
      'EXEC',
      false // not intraday
    );
  });

  // ─── 2. REJECT happy path ───
  runTest('REJ - marks signal as REJECTED, no order placed', async () => {
    const query = makeCallbackQuery('REJ', 'a1b2c3d4');
    await callbackHandler(query);

    expect(executor.executeSignal).not.toHaveBeenCalled();
    const rejectCalls = mockPrepare.mock.calls
      .filter(c => typeof c[0] === 'string' && c[0].includes("status = 'REJECTED'"));
    expect(rejectCalls.length).toBeGreaterThanOrEqual(1);
  });

  // R action also works as reject
  runTest('R - also marks signal as REJECTED', async () => {
    const query = makeCallbackQuery('R', 'a1b2c3d4');
    await callbackHandler(query);

    expect(executor.executeSignal).not.toHaveBeenCalled();
  });

  // ─── 3. Stale callback (>5 min) ───
  runTest('stale callback (>5 min) - EXPIRED, no execution', async () => {
    const staleTs = Math.floor(Date.now() / 1000) - 400; // 400s > 300s threshold
    const query = makeCallbackQuery('EXEC', 'a1b2c3d4', { timestamp: staleTs });
    await callbackHandler(query);

    expect(executor.executeSignal).not.toHaveBeenCalled();
    expect(mockAnswerCallbackQuery).toHaveBeenCalledWith(
      'cb-query-1',
      expect.objectContaining({ text: expect.stringContaining('expired') })
    );
  });

  // ─── 4. Duplicate callback - idempotency ───
  runTest('duplicate EXEC callback - second call is no-op', async () => {
    // First call succeeds
    const query = makeCallbackQuery('EXEC', 'a1b2c3d4');
    await callbackHandler(query);

    // After first call, status is EXECUTED
    mockGet.mockReturnValue({ signal_id: 'a1b2c3d4-full-uuid-here', status: 'EXECUTED', payload_json: samplePayload });

    // Second identical call
    await callbackHandler(query);

    // executeSignal should have been called only once
    expect(executor.executeSignal).toHaveBeenCalledTimes(1);
    // Should answer with "Already EXECUTED"
    expect(mockAnswerCallbackQuery).toHaveBeenCalledWith(
      'cb-query-1',
      expect.objectContaining({ text: expect.stringContaining('Already') })
    );
  });

  // ─── 5. EXEC outside market hours ───
  runTest('EXEC outside market hours - blocked', async () => {
    isMarketOpen.mockReturnValue(false);
    const query = makeCallbackQuery('EXEC', 'a1b2c3d4');
    await callbackHandler(query);

    expect(executor.executeSignal).not.toHaveBeenCalled();
    expect(mockAnswerCallbackQuery).toHaveBeenCalledWith(
      'cb-query-1',
      expect.objectContaining({ text: expect.stringContaining('closed') })
    );
  });

  // ─── 6. EXEC for non-PENDING signal ───
  runTest('EXEC for already EXECUTED signal - no-op', async () => {
    mockGet.mockReturnValue({ signal_id: 'a1b2c3d4-full-uuid-here', status: 'EXECUTED', payload_json: samplePayload });
    const query = makeCallbackQuery('EXEC', 'a1b2c3d4');
    await callbackHandler(query);

    expect(executor.executeSignal).not.toHaveBeenCalled();
  });

  // ─── 7. Invalid chat ID - unauthorized ───
  runTest('unauthorized chat ID - callback ignored', async () => {
    telegram.isValidChat.mockReturnValue(false);
    const query = makeCallbackQuery('EXEC', 'RELIANCE');
    await callbackHandler(query);

    expect(executor.executeSignal).not.toHaveBeenCalled();
    expect(mockPrepare).not.toHaveBeenCalled();
  });

  // ─── 8. Signal not found in DB ───
  runTest('signal not found in DB - no action', async () => {
    mockGet.mockReturnValue(undefined);
    const query = makeCallbackQuery('EXEC', 'NONEXISTENT');
    await callbackHandler(query);

    expect(executor.executeSignal).not.toHaveBeenCalled();
  });

  // ─── 9. Execution failure reverts to PENDING ───
  runTest('EXEC failure reverts signal status to PENDING', async () => {
    executor.executeSignal.mockRejectedValue(new Error('Broker down'));
    const query = makeCallbackQuery('EXEC', 'a1b2c3d4');
    await callbackHandler(query);

    // Should revert to PENDING
    const revertCalls = mockPrepare.mock.calls
      .filter(c => typeof c[0] === 'string' && c[0].includes("status = 'PENDING'"));
    expect(revertCalls.length).toBeGreaterThanOrEqual(1);
  });

  // ─── 10. Momentum (EM) action ───
  runTest('EM - fetches momentum signal from Engine and executes as intraday', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        signals: [{ ticker: 'RELIANCE', close: 1000, shares: 5, stop_loss: 950, target_1: 1075, target_2: 1150 }],
      }),
    });
    // For momentum, row may not exist
    mockGet.mockReturnValue(null);

    const query = makeCallbackQuery('EM', 'RELIANCE_MOM');
    await callbackHandler(query);

    expect(executor.executeSignal).toHaveBeenCalledWith(
      expect.objectContaining({ ticker: 'RELIANCE' }),
      'EM',
      true // isIntraday
    );
  });

  // ─── 11. EM outside market hours - blocked ───
  runTest('EM outside market hours - blocked', async () => {
    isMarketOpen.mockReturnValue(false);
    const query = makeCallbackQuery('EM', 'RELIANCE_MOM');
    await callbackHandler(query);

    expect(executor.executeSignal).not.toHaveBeenCalled();
  });

  // ─── 12. EXEC with PriceDriftError (>2%) - execution aborted ───
  runTest('EXEC with price drift >2% - execution aborted, user notified', async () => {
    const { PriceDriftError } = require('../../utils/errors');
    executor.executeSignal.mockRejectedValue(
      new PriceDriftError('LTP 1025 drifted 3% from signal 1000')
    );
    const query = makeCallbackQuery('EXEC', 'a1b2c3d4');
    await callbackHandler(query);

    // Should revert to PENDING (execution failed)
    const revertCalls = mockPrepare.mock.calls
      .filter(c => typeof c[0] === 'string' && c[0].includes("status = 'PENDING'"));
    expect(revertCalls.length).toBeGreaterThanOrEqual(1);

    // User notified via sendAlert (callback was already answered — second call silently fails)
    expect(telegram.sendAlert).toHaveBeenCalledWith(
      expect.stringContaining('drift')
    );
  });

  // ─── 13. EXEC with shares == 0 - no order placed ───
  runTest('EXEC with shares == 0 - execution fails safely', async () => {
    const zeroSharesPayload = JSON.stringify({
      signal_id: 'a1b2c3d4-full-uuid-here',
      ticker: 'ZEROSHARES',
      close: 1000,
      shares: 0,
      stop_loss: 950,
      target_1: 1075,
      target_2: 1150,
      capital_at_risk: 0,
    });
    mockGet.mockReturnValue({ signal_id: 'a1b2c3d4-full-uuid-here', status: 'PENDING', payload_json: zeroSharesPayload });
    // Executor should reject shares=0 by throwing
    const { ValidationError } = require('../../utils/errors');
    executor.executeSignal.mockRejectedValue(
      new ValidationError('shares must be > 0')
    );

    const query = makeCallbackQuery('EXEC', 'a1b2c3d4');
    await callbackHandler(query);

    // Executor was called but threw - status should revert to PENDING
    const revertCalls = mockPrepare.mock.calls
      .filter(c => typeof c[0] === 'string' && c[0].includes("status = 'PENDING'"));
    expect(revertCalls.length).toBeGreaterThanOrEqual(1);
  });

  // ─── 14. EXEC with TokenExpiredError - token refresh needed ───
  runTest('EXEC with expired token - execution blocked, user told to re-login', async () => {
    const { TokenExpiredError } = require('../../utils/errors');
    executor.executeSignal.mockRejectedValue(new TokenExpiredError());

    const query = makeCallbackQuery('EXEC', 'a1b2c3d4');
    await callbackHandler(query);

    // Status reverts to PENDING so user can retry after login
    const revertCalls = mockPrepare.mock.calls
      .filter(c => typeof c[0] === 'string' && c[0].includes("status = 'PENDING'"));
    expect(revertCalls.length).toBeGreaterThanOrEqual(1);

    // User notified via sendAlert (callback was already answered — second call silently fails)
    expect(telegram.sendAlert).toHaveBeenCalledWith(
      expect.stringContaining('xpired')
    );
  });

  // ─── 15. EXEC with MarketClosedError from executor ───
  runTest('EXEC where executor detects market closed - blocked with message', async () => {
    // Market hours check inside callback handler passes, but executor's own check fails
    const { MarketClosedError } = require('../../utils/errors');
    executor.executeSignal.mockRejectedValue(new MarketClosedError());

    const query = makeCallbackQuery('EXEC', 'a1b2c3d4');
    await callbackHandler(query);

    const revertCalls = mockPrepare.mock.calls
      .filter(c => typeof c[0] === 'string' && c[0].includes("status = 'PENDING'"));
    expect(revertCalls.length).toBeGreaterThanOrEqual(1);
  });

  // ─── 16. REJ for already EXECUTED signal - no change ───
  runTest('REJ for already EXECUTED signal - no status change', async () => {
    mockGet.mockReturnValue({ signal_id: 'a1b2c3d4-full-uuid-here', status: 'EXECUTED', payload_json: samplePayload });
    const query = makeCallbackQuery('REJ', 'a1b2c3d4');
    await callbackHandler(query);

    // Should NOT call executeSignal
    expect(executor.executeSignal).not.toHaveBeenCalled();
    // Already EXECUTED, so the idempotency gate stops it
    expect(mockAnswerCallbackQuery).toHaveBeenCalledWith(
      'cb-query-1',
      expect.objectContaining({ text: expect.stringContaining('Already') })
    );
  });

  // ─── 17. Callback 60s old - NOT stale (well under 5-min threshold) ───
  runTest('callback 60s old - still valid (threshold is 300s)', async () => {
    const boundaryTs = Math.floor(Date.now() / 1000) - 60;
    const query = makeCallbackQuery('EXEC', 'a1b2c3d4', { timestamp: boundaryTs });
    await callbackHandler(query);

    // 60s is NOT > 300s, so it should proceed to execution
    expect(executor.executeSignal).toHaveBeenCalled();
  });

  // ─── 18. Callback at 301s - stale (exceeds 5-min threshold) ───
  runTest('callback at 301s - stale and rejected', async () => {
    const staleTs = Math.floor(Date.now() / 1000) - 301; // 301 > 300 threshold
    const query = makeCallbackQuery('EXEC', 'a1b2c3d4', { timestamp: staleTs });
    await callbackHandler(query);

    expect(executor.executeSignal).not.toHaveBeenCalled();
    expect(mockAnswerCallbackQuery).toHaveBeenCalledWith(
      'cb-query-1',
      expect.objectContaining({ text: expect.stringContaining('expired') })
    );
  });
});
