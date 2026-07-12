/**
 * [ROADMAP-2.1 2026-07-12] Boot-time token re-arm from python-engine.
 */
jest.mock('../../config', () => ({
  PYTHON_ENGINE_URL: 'http://python-engine:8000',
  INTERNAL_API_SECRET: 'test_secret',
  LOG_LEVEL: 'silent'
}));
jest.mock('../../middleware/logger', () => ({
  logger: { info: jest.fn(), warn: jest.fn(), error: jest.fn() }
}));

const tokenStore = require('../../services/token-store');
const { restoreTokenFromEngine } = require('../../services/token-restore');

describe('restoreTokenFromEngine()', () => {
  beforeEach(() => {
    tokenStore.clearToken();
    global.fetch = jest.fn();
  });

  afterAll(() => {
    delete global.fetch;
  });

  test('arms the store when the engine serves a fresh token', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ armed: true, access_token: 'fresh_token_abcd' })
    });

    const restored = await restoreTokenFromEngine({ attempts: 1 });

    expect(restored).toBe(true);
    expect(tokenStore.isValid()).toBe(true);
    expect(tokenStore.getToken()).toBe('fresh_token_abcd');
  });

  test('sends the internal secret header to the engine', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ armed: false })
    });

    await restoreTokenFromEngine({ attempts: 1 });

    expect(global.fetch).toHaveBeenCalledWith(
      'http://python-engine:8000/token/current',
      expect.objectContaining({
        headers: { 'X-Internal-Secret': 'test_secret' }
      })
    );
  });

  test('stays disarmed when the engine has no fresh token (cold morning boot)', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ armed: false })
    });

    const restored = await restoreTokenFromEngine({ attempts: 1 });

    expect(restored).toBe(false);
    expect(tokenStore.isValid()).toBe(false);
  });

  test('retries then returns false when the engine is unreachable', async () => {
    global.fetch.mockRejectedValue(new Error('ECONNREFUSED'));

    const restored = await restoreTokenFromEngine({ attempts: 3, delayMs: 1 });

    expect(restored).toBe(false);
    expect(global.fetch).toHaveBeenCalledTimes(3);
    expect(tokenStore.isValid()).toBe(false);
  });

  test('treats a non-2xx engine response as a failed attempt', async () => {
    // e.g. 403 if the secret ever drifts between the two containers --
    // must not crash the boot sequence.
    global.fetch.mockResolvedValue({ ok: false, status: 403 });

    const restored = await restoreTokenFromEngine({ attempts: 2, delayMs: 1 });

    expect(restored).toBe(false);
    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect(tokenStore.isValid()).toBe(false);
  });
});
