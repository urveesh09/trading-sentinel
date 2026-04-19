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
// formatSignalMessage (internal — access via sendSignalAlert behaviour)
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
// sendSignalAlert — callback buttons
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

  test('callback_data is base64-encoded JSON with correct action', async () => {
    mockSendMessage.mockResolvedValue({ message_id: 100 });

    const signal = makeSignal({ signal_id: 'test-id-123' });
    await telegram.sendSignalAlert(signal);
    const [, , options] = mockSendMessage.mock.calls[0];

    const keyboard = options.reply_markup.inline_keyboard;

    // Decode EXEC button
    const execData = JSON.parse(Buffer.from(keyboard[0][0].callback_data, 'base64').toString());
    expect(execData.a).toBe('EXEC');
    expect(execData.id).toBe('test-id-123');
    expect(execData.t).toBeDefined();
    expect(typeof execData.t).toBe('number');

    // Decode REJ button
    const rejData = JSON.parse(Buffer.from(keyboard[1][0].callback_data, 'base64').toString());
    expect(rejData.a).toBe('REJ');
    expect(rejData.id).toBe('test-id-123');
  });

  test('callback_data timestamp is close to current time', async () => {
    mockSendMessage.mockResolvedValue({ message_id: 100 });

    const now = Math.floor(Date.now() / 1000);
    await telegram.sendSignalAlert(makeSignal());
    const [, , options] = mockSendMessage.mock.calls[0];

    const keyboard = options.reply_markup.inline_keyboard;
    const execData = JSON.parse(Buffer.from(keyboard[0][0].callback_data, 'base64').toString());

    // Timestamp should be within 5 seconds of 'now'
    expect(Math.abs(execData.t - now)).toBeLessThanOrEqual(5);
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
    mockSendMessage.mockRejectedValue(new Error('fail'));

    // Should not throw
    await expect(telegram.sendAlert('test')).resolves.not.toThrow();
  });
});
