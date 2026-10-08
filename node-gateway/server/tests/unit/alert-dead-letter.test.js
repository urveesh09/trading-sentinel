/**
 * [ALERT-DEADLETTER 2026-07-31] An alert that exhausts every retry must leave
 * a durable record.
 *
 * 2026-07-28: a momentum EXEC alert failed, retried three times
 * (telegram_send_retry_failed x2, then telegram_send_error) and vanished. The
 * only trace was one line in a container log that gzip rotation later made
 * unreadable. Telegram is by definition the broken channel when this fires, so
 * the escalation has to be somewhere else.
 */
const fs = require('fs');
const os = require('os');
const path = require('path');

jest.mock('node-telegram-bot-api', () => jest.fn().mockImplementation(() => ({
  on: jest.fn(),
  sendMessage: jest.fn(),
  setWebHook: jest.fn().mockResolvedValue(true),
  stopPolling: jest.fn().mockResolvedValue(true),
})));

describe('undelivered alert dead-letter', () => {
  let tmpFile;
  let telegram;

  beforeEach(() => {
    tmpFile = path.join(
      fs.mkdtempSync(path.join(os.tmpdir(), 'alert-dl-')),
      'undelivered_alerts.jsonl'
    );
    process.env.ALERT_DEAD_LETTER_PATH = tmpFile;
    jest.resetModules();
    telegram = require('../../services/telegram');
  });

  afterEach(() => {
    delete process.env.ALERT_DEAD_LETTER_PATH;
  });

  test('counts zero when nothing has been dropped', () => {
    expect(telegram.undeliveredAlertCount()).toBe(0);
  });

  test('a written record is counted and preserves the message text', () => {
    fs.appendFileSync(tmpFile, JSON.stringify({
      ts: new Date().toISOString(),
      message: 'EXEC HOMEFIRST 2 @ 1187.80',
      error: 'EFATAL: AggregateError',
    }) + '\n');
    expect(telegram.undeliveredAlertCount()).toBe(1);

    const rows = fs.readFileSync(tmpFile, 'utf8')
      .split('\n').filter(Boolean).map(JSON.parse);
    expect(rows[0].message).toContain('HOMEFIRST');
    expect(rows[0].error).toContain('AggregateError');
  });

  test('multiple drops accumulate rather than overwrite', () => {
    for (const t of ['AAA', 'BBB', 'CCC']) {
      fs.appendFileSync(tmpFile, JSON.stringify({ message: t }) + '\n');
    }
    expect(telegram.undeliveredAlertCount()).toBe(3);
  });

  test('a missing file is not an error -- it means nothing was dropped', () => {
    fs.appendFileSync(tmpFile, JSON.stringify({ message: 'x' }) + '\n');
    expect(telegram.undeliveredAlertCount()).toBe(1);
    fs.unlinkSync(tmpFile);
    // A health probe must never throw just because nothing has failed yet.
    expect(telegram.undeliveredAlertCount()).toBe(0);
  });

  // [EXPIRY-OUTBOX 2026-10-05] The caller's outbox owns retries for
  // sendAlertOnce, so a refusal reports false and leaves no dead-letter row.
  test('sendAlertOnce reports a refusal without retrying or dead-lettering', async () => {
    telegram.bot.sendMessage.mockRejectedValueOnce(Object.assign(new Error('boom'), { code: 'EFATAL' }));
    expect(await telegram.sendAlertOnce('x')).toBe(false);
    telegram.bot.sendMessage.mockResolvedValueOnce({});
    expect(await telegram.sendAlertOnce('y')).toBe(true);
    expect(telegram.bot.sendMessage).toHaveBeenCalledTimes(2);
    expect(fs.existsSync(tmpFile)).toBe(false);
  });

  // [OUTBOX-CLASSIFY 2026-10-08] Only Telegram's own 400 marks THIS message
  // as rejected; network failures, 429 and 5xx stay transient.
  test('sendAlertOnceDetailed separates a rejected message from a transient failure', async () => {
    const telegramError = (status) => Object.assign(new Error(`ETELEGRAM ${status}`), {
      code: 'ETELEGRAM', response: { statusCode: status, body: { error_code: status } },
    });
    telegram.bot.sendMessage.mockRejectedValueOnce(telegramError(400));
    expect(await telegram.sendAlertOnceDetailed('too long')).toEqual({ delivered: false, rejected: true, status: 400 });
    telegram.bot.sendMessage.mockRejectedValueOnce(telegramError(429));
    expect(await telegram.sendAlertOnceDetailed('x')).toEqual({ delivered: false, rejected: false, status: 429 });
    telegram.bot.sendMessage.mockRejectedValueOnce(Object.assign(new Error('net'), { code: 'EFATAL' }));
    expect(await telegram.sendAlertOnceDetailed('x')).toEqual({ delivered: false, rejected: false, status: null });
    telegram.bot.sendMessage.mockResolvedValueOnce({});
    expect(await telegram.sendAlertOnceDetailed('ok')).toEqual({ delivered: true, rejected: false });
    expect(fs.existsSync(tmpFile)).toBe(false);
  });
});
