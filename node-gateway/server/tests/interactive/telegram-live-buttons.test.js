/**
 * ═══════════════════════════════════════════════════════════════════
 * INTERACTIVE TELEGRAM BUTTON TESTS (LIVE)
 * ═══════════════════════════════════════════════════════════════════
 *
 * These tests send REAL messages to your Telegram chat with inline
 * keyboard buttons. YOU physically press the button, and the test
 * verifies the full callback → decode → action pipeline.
 *
 * Requirements:
 *   1. Set env vars: LIVE_TELEGRAM_BOT_TOKEN, LIVE_TELEGRAM_CHAT_ID
 *   2. The bot's webhook will be temporarily removed for polling.
 *      After tests complete, re-deploy or re-set the webhook.
 *
 * Run:
 *   LIVE_TELEGRAM_BOT_TOKEN=<token> LIVE_TELEGRAM_CHAT_ID=<id> \
 *     npx jest tests/interactive/ --testTimeout=120000
 *
 * These tests are SKIPPED in CI / normal test runs (no live creds).
 * ═══════════════════════════════════════════════════════════════════
 */

const LIVE_TOKEN = process.env.LIVE_TELEGRAM_BOT_TOKEN;
const LIVE_CHAT  = process.env.LIVE_TELEGRAM_CHAT_ID;

const canRun = !!(LIVE_TOKEN && LIVE_CHAT);

const describeIf = canRun ? describe : describe.skip;

// ── Raw Telegram API helper (no library conflicts) ──
async function tgApi(method, body = {}) {
  const res = await fetch(`https://api.telegram.org/bot${LIVE_TOKEN}/${method}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!data.ok) throw new Error(`Telegram ${method}: ${data.description}`);
  return data.result;
}

async function clearPendingUpdates() {
  const updates = await tgApi('getUpdates', { offset: -1 });
  if (updates.length > 0) {
    // Acknowledge the last update to clear the queue
    await tgApi('getUpdates', { offset: updates[updates.length - 1].update_id + 1 });
  }
}

async function waitForCallback(timeoutSec = 90) {
  const result = await tgApi('getUpdates', {
    timeout: timeoutSec,
    allowed_updates: ['callback_query'],
  });
  if (result.length === 0) {
    throw new Error(`⏰ Timeout: No button was pressed within ${timeoutSec}s`);
  }
  const cb = result[0].callback_query;
  // Acknowledge to clear the update
  await tgApi('getUpdates', { offset: result[0].update_id + 1 });
  return cb;
}

// ─────────────────────────────────────────────────────────────────
describeIf('🔴 LIVE: Telegram Button → Callback Verification', () => {
  let webhookWasActive = false;

  beforeAll(async () => {
    // Check current webhook status
    const info = await tgApi('getWebhookInfo');
    webhookWasActive = !!info.url;

    // Must disable webhook to use getUpdates (Telegram API constraint)
    if (webhookWasActive) {
      await tgApi('deleteWebhook');
    }
    // Drain any stale updates
    await clearPendingUpdates();
  });

  afterAll(async () => {
    if (webhookWasActive) {
      console.log(
        '\n⚠️  Webhook was removed for this test. Re-deploy your bot ' +
        'or re-set the webhook to resume production operation.\n'
      );
    }
  });

  // ─── TEST 1: EXECUTE button press ───────────────────────────────
  test('🟢 Press EXECUTE → callback decodes to action EXEC', async () => {
    const signalId = `TEST_EXEC_${Date.now()}`;
    const ts = Math.floor(Date.now() / 1000);

    const cbExec = Buffer.from(JSON.stringify({ a: 'EXEC', id: signalId, t: ts })).toString('base64');
    const cbRej  = Buffer.from(JSON.stringify({ a: 'REJ',  id: signalId, t: ts })).toString('base64');

    // Send the message with inline keyboard
    const msg = await tgApi('sendMessage', {
      chat_id: LIVE_CHAT,
      text: [
        '🧪 *TEST: Execute Button Verification*',
        '',
        '```',
        `Signal:   ${signalId}`,
        'Ticker:   TESTSTOCK',
        'Entry:    ₹1000',
        'Stop:     ₹950',
        'Target:   ₹1075',
        '```',
        '',
        '👆 *Press "Execute" to PASS this test*',
        `⏱ You have 90 seconds`,
      ].join('\n'),
      parse_mode: 'Markdown',
      reply_markup: JSON.stringify({
        inline_keyboard: [
          [{ text: '✅ Execute Market & Place GTT', callback_data: cbExec }],
          [{ text: '❌ Reject Signal',              callback_data: cbRej  }],
        ],
      }),
    });

    expect(msg.message_id).toBeDefined();

    // Wait for the user to press a button
    const callback = await waitForCallback(90);

    // Decode the callback data
    const decoded = JSON.parse(Buffer.from(callback.data, 'base64').toString('utf-8'));

    // Verify the EXECUTE button was pressed
    expect(decoded.a).toBe('EXEC');
    expect(decoded.id).toBe(signalId);
    expect(decoded.t).toBe(ts);

    // Verify chat matches
    expect(String(callback.message.chat.id)).toBe(String(LIVE_CHAT));

    // Answer the callback (clears the spinning indicator)
    await tgApi('answerCallbackQuery', {
      callback_query_id: callback.id,
      text: '✅ TEST PASSED — Execute callback verified!',
    });

    // Edit the message to show success
    await tgApi('editMessageText', {
      chat_id: LIVE_CHAT,
      message_id: msg.message_id,
      text: `✅ TEST PASSED\nAction: EXEC\nSignal: ${signalId}\nDecoded correctly.`,
    });
  }, 120_000); // 120s Jest timeout

  // ─── TEST 2: REJECT button press ───────────────────────────────
  test('🔴 Press REJECT → callback decodes to action REJ', async () => {
    const signalId = `TEST_REJ_${Date.now()}`;
    const ts = Math.floor(Date.now() / 1000);

    const cbExec = Buffer.from(JSON.stringify({ a: 'EXEC', id: signalId, t: ts })).toString('base64');
    const cbRej  = Buffer.from(JSON.stringify({ a: 'REJ',  id: signalId, t: ts })).toString('base64');

    const msg = await tgApi('sendMessage', {
      chat_id: LIVE_CHAT,
      text: [
        '🧪 *TEST: Reject Button Verification*',
        '',
        '```',
        `Signal:   ${signalId}`,
        'Ticker:   REJECTME',
        'Entry:    ₹500',
        'Stop:     ₹480',
        'Target:   ₹530',
        '```',
        '',
        '👆 *Press "Reject" to PASS this test*',
        `⏱ You have 90 seconds`,
      ].join('\n'),
      parse_mode: 'Markdown',
      reply_markup: JSON.stringify({
        inline_keyboard: [
          [{ text: '✅ Execute Market & Place GTT', callback_data: cbExec }],
          [{ text: '❌ Reject Signal',              callback_data: cbRej  }],
        ],
      }),
    });

    expect(msg.message_id).toBeDefined();

    // Wait for button press
    const callback = await waitForCallback(90);

    const decoded = JSON.parse(Buffer.from(callback.data, 'base64').toString('utf-8'));

    // Verify REJECT was pressed
    expect(decoded.a).toBe('REJ');
    expect(decoded.id).toBe(signalId);

    expect(String(callback.message.chat.id)).toBe(String(LIVE_CHAT));

    await tgApi('answerCallbackQuery', {
      callback_query_id: callback.id,
      text: '✅ TEST PASSED — Reject callback verified!',
    });

    await tgApi('editMessageText', {
      chat_id: LIVE_CHAT,
      message_id: msg.message_id,
      text: `✅ TEST PASSED\nAction: REJ\nSignal: ${signalId}\nDecoded correctly.`,
    });
  }, 120_000);

  // ─── TEST 3: EXECUTE MOMENTUM button ──────────────────────────
  test('⚡ Press EXECUTE INTRADAY → callback decodes to action EM', async () => {
    const ticker = 'MOMENTUM_TEST';
    const sigId = `${ticker}_MOM`;
    const ts = Math.floor(Date.now() / 1000);

    const cbEM  = Buffer.from(JSON.stringify({ a: 'EM', id: sigId, t: ts })).toString('base64');
    const cbRej = Buffer.from(JSON.stringify({ a: 'R',  id: sigId, t: ts })).toString('base64');

    const msg = await tgApi('sendMessage', {
      chat_id: LIVE_CHAT,
      text: [
        '🧪 *TEST: Momentum Execute Verification*',
        '',
        `⚡ INTRADAY MOMENTUM: ${ticker} (MIS)`,
        'Entry: ₹2500 | VWAP: ₹2480',
        'Target: ₹2550 | SL: ₹2460',
        '',
        '👆 *Press "Execute Intraday" to PASS this test*',
        '⏱ You have 90 seconds',
      ].join('\n'),
      parse_mode: 'Markdown',
      reply_markup: JSON.stringify({
        inline_keyboard: [[
          { text: '✅ EXECUTE INTRADAY', callback_data: cbEM },
          { text: '❌ REJECT',           callback_data: cbRej },
        ]],
      }),
    });

    const callback = await waitForCallback(90);
    const decoded = JSON.parse(Buffer.from(callback.data, 'base64').toString('utf-8'));

    expect(decoded.a).toBe('EM');
    expect(decoded.id).toBe(sigId);

    await tgApi('answerCallbackQuery', {
      callback_query_id: callback.id,
      text: '✅ TEST PASSED — Momentum callback verified!',
    });

    await tgApi('editMessageText', {
      chat_id: LIVE_CHAT,
      message_id: msg.message_id,
      text: `✅ TEST PASSED\nAction: EM\nSignal: ${sigId}\nDecoded correctly.`,
    });
  }, 120_000);

  // ─── TEST 4: Staleness — callback_data timestamp survives round-trip ──
  test('callback_data timestamp survives base64 round-trip', async () => {
    const signalId = `TEST_TS_${Date.now()}`;
    const ts = Math.floor(Date.now() / 1000);

    const cbData = Buffer.from(JSON.stringify({ a: 'EXEC', id: signalId, t: ts })).toString('base64');

    const msg = await tgApi('sendMessage', {
      chat_id: LIVE_CHAT,
      text: [
        '🧪 *TEST: Timestamp Round-Trip*',
        '',
        '👆 *Press the button to verify timestamp integrity*',
        '⏱ You have 90 seconds',
      ].join('\n'),
      parse_mode: 'Markdown',
      reply_markup: JSON.stringify({
        inline_keyboard: [
          [{ text: '🕐 Verify Timestamp', callback_data: cbData }],
        ],
      }),
    });

    const callback = await waitForCallback(90);
    const decoded = JSON.parse(Buffer.from(callback.data, 'base64').toString('utf-8'));

    // The timestamp embedded in the button must survive the Telegram round-trip
    expect(decoded.t).toBe(ts);

    // Calculate how old the callback is at the moment we received it
    const callbackAge = Math.floor(Date.now() / 1000) - decoded.t;
    expect(callbackAge).toBeGreaterThanOrEqual(0);

    await tgApi('answerCallbackQuery', {
      callback_query_id: callback.id,
      text: `✅ Timestamp intact. Age: ${callbackAge}s`,
    });

    await tgApi('editMessageText', {
      chat_id: LIVE_CHAT,
      message_id: msg.message_id,
      text: `✅ TEST PASSED\nTimestamp: ${ts}\nAge at receipt: ${callbackAge}s\nRound-trip verified.`,
    });
  }, 120_000);
});
