// [O21-PK] The owner's Zerodha callback refuses the partner's account (and,
// when ZERODHA_USER_ID is set, every account but the owner's): nothing is
// stored, provisioned or authenticated.
const express = require('express');
const request = require('supertest');

const mockConfig = {
  ZERODHA_API_SECRET: 'unused-in-this-test',
  PYTHON_ENGINE_URL: 'http://python-engine:8000',
  INTERNAL_API_SECRET: 'test-internal-secret',
  LOG_LEVEL: 'error',
};
jest.mock('../../config', () => mockConfig);
jest.mock('../../services/kite', () => ({
  getLoginURL: jest.fn(() => 'https://kite.example.test/login'),
  generateSessionWithUser: jest.fn(),
}));
jest.mock('../../services/token-store', () => ({
  getStatus: jest.fn(() => ({})),
  setToken: jest.fn(),
  clearToken: jest.fn(),
}));
jest.mock('../../services/telegram', () => ({ sendAlert: jest.fn() }));

const kite = require('../../services/kite');
const tokenStore = require('../../services/token-store');

function makeApp(session) {
  const app = express();
  app.use((req, _res, next) => { req.session = session; next(); });
  app.use('/api/auth', require('../../routes/auth'));
  return app;
}

const callback = '/api/auth/callback?status=success&request_token=abcDEF123456';

beforeEach(() => {
  jest.clearAllMocks();
  delete mockConfig.ZERODHA_USER_ID;
  delete mockConfig.PARTNER_KITE_USER_ID;
  global.fetch = jest.fn().mockResolvedValue({ ok: true });
});

test('the partner account is refused on the owner callback', async () => {
  mockConfig.PARTNER_KITE_USER_ID = 'pt5678';
  kite.generateSessionWithUser.mockResolvedValue({ accessToken: 'partner-token', userId: 'PT5678' });
  const session = {};
  await request(makeApp(session)).get(callback).expect(302).expect('Location', '/login?error=wrong_account');
  expect(tokenStore.setToken).not.toHaveBeenCalled();
  expect(global.fetch).not.toHaveBeenCalled();
  expect(session.authenticated).toBeUndefined();
});

test('with ZERODHA_USER_ID only the owner gets in', async () => {
  mockConfig.ZERODHA_USER_ID = 'OW1234';
  kite.generateSessionWithUser.mockResolvedValue({ accessToken: 'other-token', userId: 'ZZ9999' });
  const refused = {};
  await request(makeApp(refused)).get(callback).expect('Location', '/login?error=wrong_account');
  expect(refused.authenticated).toBeUndefined();
  kite.generateSessionWithUser.mockResolvedValue({ accessToken: 'owner-token', userId: 'ow1234' });
  const owner = {};
  await request(makeApp(owner)).get(callback).expect(302).expect('Location', '/');
  expect(tokenStore.setToken).toHaveBeenCalledWith('owner-token');
  expect(owner.authenticated).toBe(true);
});

test('with neither id set the callback behaves as before', async () => {
  kite.generateSessionWithUser.mockResolvedValue({ accessToken: 'owner-token', userId: 'OW1234' });
  const session = {};
  await request(makeApp(session)).get(callback).expect(302).expect('Location', '/');
  expect(tokenStore.setToken).toHaveBeenCalledWith('owner-token');
  expect(session.authenticated).toBe(true);
});
