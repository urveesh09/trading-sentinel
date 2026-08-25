const express = require('express');
const request = require('supertest');

jest.mock('../../config', () => ({
  RATE_LIMIT_WINDOW_MS: 60_000,
  ZERODHA_API_SECRET: 'unused-in-this-test',
  PYTHON_ENGINE_URL: 'http://python-engine:8000',
  INTERNAL_API_SECRET: 'test-internal-secret',
  LOG_LEVEL: 'error',
}));

jest.mock('../../services/kite', () => ({
  getLoginURL: jest.fn(() => 'https://kite.example.test/login'),
  generateSession: jest.fn(),
}));

jest.mock('../../services/token-store', () => ({
  getStatus: jest.fn(() => ({})),
  setToken: jest.fn(),
  clearToken: jest.fn(),
}));

jest.mock('../../services/telegram', () => ({ sendAlert: jest.fn() }));

describe('OAuth rate limiting', () => {
  test('login quota never blocks the Zerodha callback', async () => {
    const app = express();
    app.use('/api/auth', require('../../routes/auth'));

    for (let attempt = 0; attempt < 10; attempt += 1) {
      await request(app).get('/api/auth/login').expect(302);
    }

    await request(app).get('/api/auth/login').expect(429);
    await request(app)
      .get('/api/auth/callback?status=error')
      .expect(302)
      .expect('Location', '/login?error=zerodha_failed');
  });
});
