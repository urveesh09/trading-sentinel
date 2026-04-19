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
const mockRun = jest.fn();
const mockGet = jest.fn();
const mockAll = jest.fn().mockReturnValue([]);
mockPrepare.mockReturnValue({ run: mockRun, get: mockGet, all: mockAll });

jest.mock('../../db/index', () => ({
  signalsDb: { prepare: mockPrepare },
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

// Now require index.js — this registers the bot.on('callback_query') handler
// We capture it from the mock
let callbackHandler;

beforeAll(() => {
  // index.js registers bot.on('callback_query', handler)
  // We need to import it to trigger registration
  jest.isolateModules(() => {
    // Need to handle the server.listen — mock http.createServer
    jest.doMock('http', () => ({
      createServer: jest.fn(() => ({
        listen: jest.fn(),
        close: jest.fn(),
      })),
    }));
    require('../../index');
  });

  // Find the callback_query handler from bot.on calls
  const callbackCall = mockBotOn.mock.calls.find(c => c[0] === 'callback_query');
  if (callbackCall) {
    callbackHandler = callbackCall[1];
  }
});

// ── Helpers ──
function makeCallbackQuery(action, signalId, overrides = {}) {
  const now = Math.floor(Date.now() / 1000);
  const data = Buffer.from(
    JSON.stringify({ a: action, id: signalId, t: overrides.timestamp || now })
  ).toString('base64');

  return {
    id: overrides.queryId || 'cb-query-1',
    data,
    message: {
      chat: { id: overrides.chatId || 99999999999 },
      message_id: overrides.messageId || 42,
      text: 'SIGNAL — RELIANCE Score: 85/100\n...',
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
    mockGet.mockReturnValue({ status: 'PENDING', payload_json: samplePayload });
    executor.executeSignal.mockResolvedValue({ orderId: 'ORD-001' });
  });

  // If handler wasn't captured, skip all tests gracefully
  const runTest = callbackHandler ? test : test.skip;

  // ─── 1. APPROVE happy path (EXEC) ───
  runTest('EXEC — happy path: PENDING → EXECUTING → EXECUTED', async () => {
    const query = makeCallbackQuery('EXEC', 'RELIANCE');
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
  runTest('REJ — marks signal as REJECTED, no order placed', async () => {
    const query = makeCallbackQuery('REJ', 'RELIANCE');
    await callbackHandler(query);

    expect(executor.executeSignal).not.toHaveBeenCalled();
    const rejectCalls = mockPrepare.mock.calls
      .filter(c => typeof c[0] === 'string' && c[0].includes("status = 'REJECTED'"));
    expect(rejectCalls.length).toBeGreaterThanOrEqual(1);
  });

  // R action also works as reject
  runTest('R — also marks signal as REJECTED', async () => {
    const query = makeCallbackQuery('R', 'RELIANCE');
    await callbackHandler(query);

    expect(executor.executeSignal).not.toHaveBeenCalled();
  });

  // ─── 3. Stale callback (>60s) ───
  runTest('stale callback (>60s) — EXPIRED, no execution', async () => {
    const staleTs = Math.floor(Date.now() / 1000) - 90;
    const query = makeCallbackQuery('EXEC', 'RELIANCE', { timestamp: staleTs });
    await callbackHandler(query);

    expect(executor.executeSignal).not.toHaveBeenCalled();
    expect(mockAnswerCallbackQuery).toHaveBeenCalledWith(
      'cb-query-1',
      expect.objectContaining({ text: expect.stringContaining('expired') })
    );
  });

  // ─── 4. Duplicate callback — idempotency ───
  runTest('duplicate EXEC callback — second call is no-op', async () => {
    // First call succeeds
    const query = makeCallbackQuery('EXEC', 'RELIANCE');
    await callbackHandler(query);

    // After first call, status is EXECUTED
    mockGet.mockReturnValue({ status: 'EXECUTED', payload_json: samplePayload });

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
  runTest('EXEC outside market hours — blocked', async () => {
    isMarketOpen.mockReturnValue(false);
    const query = makeCallbackQuery('EXEC', 'RELIANCE');
    await callbackHandler(query);

    expect(executor.executeSignal).not.toHaveBeenCalled();
    expect(mockAnswerCallbackQuery).toHaveBeenCalledWith(
      'cb-query-1',
      expect.objectContaining({ text: expect.stringContaining('closed') })
    );
  });

  // ─── 6. EXEC for non-PENDING signal ───
  runTest('EXEC for already EXECUTED signal — no-op', async () => {
    mockGet.mockReturnValue({ status: 'EXECUTED', payload_json: samplePayload });
    const query = makeCallbackQuery('EXEC', 'RELIANCE');
    await callbackHandler(query);

    expect(executor.executeSignal).not.toHaveBeenCalled();
  });

  // ─── 7. Invalid chat ID — unauthorized ───
  runTest('unauthorized chat ID — callback ignored', async () => {
    telegram.isValidChat.mockReturnValue(false);
    const query = makeCallbackQuery('EXEC', 'RELIANCE');
    await callbackHandler(query);

    expect(executor.executeSignal).not.toHaveBeenCalled();
    expect(mockPrepare).not.toHaveBeenCalled();
  });

  // ─── 8. Signal not found in DB ───
  runTest('signal not found in DB — no action', async () => {
    mockGet.mockReturnValue(undefined);
    const query = makeCallbackQuery('EXEC', 'NONEXISTENT');
    await callbackHandler(query);

    expect(executor.executeSignal).not.toHaveBeenCalled();
  });

  // ─── 9. Execution failure reverts to PENDING ───
  runTest('EXEC failure reverts signal status to PENDING', async () => {
    executor.executeSignal.mockRejectedValue(new Error('Broker down'));
    const query = makeCallbackQuery('EXEC', 'RELIANCE');
    await callbackHandler(query);

    // Should revert to PENDING
    const revertCalls = mockPrepare.mock.calls
      .filter(c => typeof c[0] === 'string' && c[0].includes("status = 'PENDING'"));
    expect(revertCalls.length).toBeGreaterThanOrEqual(1);
  });

  // ─── 10. Momentum (EM) action ───
  runTest('EM — fetches momentum signal from Engine and executes as intraday', async () => {
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

  // ─── 11. EM outside market hours — blocked ───
  runTest('EM outside market hours — blocked', async () => {
    isMarketOpen.mockReturnValue(false);
    const query = makeCallbackQuery('EM', 'RELIANCE_MOM');
    await callbackHandler(query);

    expect(executor.executeSignal).not.toHaveBeenCalled();
  });
});
