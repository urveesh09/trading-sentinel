/**
 * Unit tests for services/telegram.js
 *
 * Tests: formatSignalMessage, sendSignalAlert, sendAlert, isValidChat.
 * Mocks node-telegram-bot-api to prevent real Telegram calls.
 */

// ── Mock node-telegram-bot-api BEFORE require ──
const mockSendMessage = jest.fn();
const mockSetWebHook = jest.fn().mockResolvedValue(true);

jest.mock('node-telegram-bot-api', () => {
  return jest.fn().mockImplementation(() => ({
    sendMessage: mockSendMessage,
    setWebHook: mockSetWebHook,
    on: jest.fn(),
  }));
});

// Now require the module under test (it will use the mock)
const telegram = require('../../services/telegram');

beforeEach(() => {
  jest.clearAllMocks();
});

// ── Helpers ──
const makeSignal = (overrides = {}) => ({
  signal_id: 'sig-uuid-001',
  ticker: 'RELIANCE',
  close: 1000,
  stop_loss: 950,
  target_1: 1075,
  target_2: 1150,
  shares: 5,
  capital_at_risk: 250,
  score: 78,
  sector: 'ENERGY',
  market_regime: 'BULL',
  net_ev: 180,
  volume_ratio: 2.3,
  rsi_14: 62,
  ...overrides,
});

// ─────────────────────────────────────────────────────────────────────
// isValidChat
// ─────────────────────────────────────────────────────────────────────

describe('isValidChat()', () => {
  const config = require('../../config');

  test('returns true for matching chat ID (string)', () => {
    expect(telegram.isValidChat(config.TELEGRAM_CHAT_ID)).toBe(true);
  });

  test('returns true for matching chat ID (number)', () => {
    expect(telegram.isValidChat(Number(config.TELEGRAM_CHAT_ID))).toBe(true);
  });

  test('returns false for non-matching chat ID', () => {
    expect(telegram.isValidChat('00000000000')).toBe(false);
  });

  test('returns false for undefined', () => {
    expect(telegram.isValidChat(undefined)).toBe(false);
  });
});

// ─────────────────────────────────────────────────────────────────────
// formatSignalMessage (internal - access via sendSignalAlert behaviour)
// We can't directly import formatSignalMessage since it's not exported,
// but we test it indirectly through sendSignalAlert's message content.
// ─────────────────────────────────────────────────────────────────────

describe('sendSignalAlert() message format', () => {
  test('message contains ticker, entry, stop %, target %', async () => {
    mockSendMessage.mockResolvedValue({ message_id: 42 });

    const signal = makeSignal();
    await telegram.sendSignalAlert(signal);

    expect(mockSendMessage).toHaveBeenCalledTimes(1);
    const [chatId, text, options] = mockSendMessage.mock.calls[0];

    // Verify key fields appear in the message text
    expect(text).toContain('RELIANCE');
    expect(text).toContain('1000');     // entry/close
    expect(text).toContain('950');      // stop_loss
    expect(text).toContain('1075');     // target_1
    expect(text).toContain('1150');     // target_2
    expect(text).toContain('78');       // score
    expect(text).toContain('5');        // shares
    expect(text).toContain('250');      // capital_at_risk
  });

  test('message uses MarkdownV2 parse_mode', async () => {
    mockSendMessage.mockResolvedValue({ message_id: 42 });

    await telegram.sendSignalAlert(makeSignal());
    const [, , options] = mockSendMessage.mock.calls[0];

    expect(options.parse_mode).toBe('MarkdownV2');
  });

  test('message contains code block (```text)', async () => {
    mockSendMessage.mockResolvedValue({ message_id: 42 });

    await telegram.sendSignalAlert(makeSignal());
    const [, text] = mockSendMessage.mock.calls[0];

    expect(text).toContain('```text');
    expect(text).toContain('```');
  });
});

// ─────────────────────────────────────────────────────────────────────
// sendSignalAlert - callback buttons
// ─────────────────────────────────────────────────────────────────────

describe('sendSignalAlert() callback buttons', () => {
  test('creates EXEC and REJ inline keyboard buttons', async () => {
    mockSendMessage.mockResolvedValue({ message_id: 100 });

    await telegram.sendSignalAlert(makeSignal());
    const [, , options] = mockSendMessage.mock.calls[0];

    const keyboard = options.reply_markup.inline_keyboard;
    expect(keyboard).toHaveLength(2);

    // Button 1: Execute
    expect(keyboard[0][0].text).toContain('Execute');
    // Button 2: Reject
    expect(keyboard[1][0].text).toContain('Reject');
  });

  // [TEST-FIX 2026-07-11] These two tests still asserted the RETIRED
  // base64-JSON callback encoding. Production moved to the compact
  // `ACTION:shortId:unix_ts` format ([CRIT-001/002], stays under
  // Telegram's 64-byte callback_data limit; shortId = first 8 chars of
  // signal_id) -- the format node-gateway's callback handler and the
  // agent container both use.
  test('callback_data uses ACTION:shortId:ts format with correct action', async () => {
    mockSendMessage.mockResolvedValue({ message_id: 100 });

    const signal = makeSignal({ signal_id: 'test-id-123' });
    await telegram.sendSignalAlert(signal);
    const [, , options] = mockSendMessage.mock.calls[0];

    const keyboard = options.reply_markup.inline_keyboard;

    // EXEC button
    const [execAction, execId, execTs] = keyboard[0][0].callback_data.split(':');
    expect(execAction).toBe('EXEC');
    expect(execId).toBe('test-id-'); // first 8 chars of signal_id
    expect(Number(execTs)).not.toBeNaN();

    // REJ button
    const [rejAction, rejId] = keyboard[1][0].callback_data.split(':');
    expect(rejAction).toBe('REJ');
    expect(rejId).toBe('test-id-');

    // Telegram hard limit
    expect(Buffer.byteLength(keyboard[0][0].callback_data)).toBeLessThanOrEqual(64);
    expect(Buffer.byteLength(keyboard[1][0].callback_data)).toBeLessThanOrEqual(64);
  });

  test('callback_data timestamp is close to current time', async () => {
    mockSendMessage.mockResolvedValue({ message_id: 100 });

    const now = Math.floor(Date.now() / 1000);
    await telegram.sendSignalAlert(makeSignal());
    const [, , options] = mockSendMessage.mock.calls[0];

    const keyboard = options.reply_markup.inline_keyboard;
    const ts = Number(keyboard[0][0].callback_data.split(':')[2]);

    // Timestamp should be within 5 seconds of 'now'
    expect(Math.abs(ts - now)).toBeLessThanOrEqual(5);
  });

  test('returns message_id on success', async () => {
    mockSendMessage.mockResolvedValue({ message_id: 777 });

    const result = await telegram.sendSignalAlert(makeSignal());
    expect(result).toBe(777);
  });

  test('returns null on Telegram API failure', async () => {
    mockSendMessage.mockRejectedValue(new Error('Network error'));

    const result = await telegram.sendSignalAlert(makeSignal());
    expect(result).toBeNull();
  });
});

// ─────────────────────────────────────────────────────────────────────
// sendAlert
// ─────────────────────────────────────────────────────────────────────

describe('sendAlert()', () => {
  test('sends plain text message to configured chat', async () => {
    mockSendMessage.mockResolvedValue({});
    const config = require('../../config');

    await telegram.sendAlert('Test alert message');

    expect(mockSendMessage).toHaveBeenCalledTimes(1);
    const [chatId, message] = mockSendMessage.mock.calls[0];
    expect(chatId).toBe(config.TELEGRAM_CHAT_ID);
    expect(message).toBe('Test alert message');
  });

  test('does not throw on send failure', async () => {
    jest.useFakeTimers();
    mockSendMessage.mockRejectedValue(new Error('fail'));

    // Should not throw
    await expect(telegram.sendAlert('test')).resolves.not.toThrow();

    // Drain the background retry chain (5s + 15s + 45s) so no timers leak.
    await jest.advanceTimersByTimeAsync(70_000);
    jest.useRealTimers();
  });
});

// ─────────────────────────────────────────────────────────────────────
// sendAlert - background retry ([ALERT-RETRY 2026-07-11]: two one-shot
// EFATAL failures on 2026-07-10 permanently dropped a momentum summary
// and the penny zero-accept watchdog alarm)
// ─────────────────────────────────────────────────────────────────────

describe('sendAlert() retry/backoff', () => {
  afterEach(() => {
    jest.useRealTimers();
  });

  test('returns true and sends exactly once on first-try success', async () => {
    mockSendMessage.mockResolvedValue({});

    const result = await telegram.sendAlert('all good');
    expect(result).toBe(true);
    expect(mockSendMessage).toHaveBeenCalledTimes(1);
  });

  test('resolves immediately on failure (never blocks the caller) and retries in background', async () => {
    jest.useFakeTimers();
    mockSendMessage
      .mockRejectedValueOnce(new Error('EFATAL AggregateError'))
      .mockResolvedValueOnce({});

    // Resolves without advancing timers: callers (python-engine posts
    // with a 5s timeout) must never wait on the backoff.
    const result = await telegram.sendAlert('watchdog alarm');
    expect(result).toBe(false);
    expect(mockSendMessage).toHaveBeenCalledTimes(1);

    // First backoff (5s) -> retry delivers the SAME message.
    await jest.advanceTimersByTimeAsync(5_000);
    expect(mockSendMessage).toHaveBeenCalledTimes(2);
    const [chatId, message] = mockSendMessage.mock.calls[1];
    expect(message).toBe('watchdog alarm');

    // Delivered -> no further attempts.
    await jest.advanceTimersByTimeAsync(70_000);
    expect(mockSendMessage).toHaveBeenCalledTimes(2);
  });

  test('gives up after all retries fail (4 total attempts)', async () => {
    jest.useFakeTimers();
    mockSendMessage.mockRejectedValue(new Error('EFATAL AggregateError'));

    await telegram.sendAlert('doomed alert');
    expect(mockSendMessage).toHaveBeenCalledTimes(1);

    await jest.advanceTimersByTimeAsync(5_000);   // retry 1
    expect(mockSendMessage).toHaveBeenCalledTimes(2);
    await jest.advanceTimersByTimeAsync(15_000);  // retry 2
    expect(mockSendMessage).toHaveBeenCalledTimes(3);
    await jest.advanceTimersByTimeAsync(45_000);  // retry 3 (last)
    expect(mockSendMessage).toHaveBeenCalledTimes(4);

    // No fifth attempt, and nothing throws.
    await jest.advanceTimersByTimeAsync(300_000);
    expect(mockSendMessage).toHaveBeenCalledTimes(4);
  });
});
