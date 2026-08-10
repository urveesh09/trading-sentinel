jest.mock('../../config', () => ({
  INTERNAL_API_SECRET: 'internal-test-secret',
  PYTHON_ENGINE_URL: 'http://python-engine:8000',
  PYTHON_ENGINE_TIMEOUT_MS: 5000,
}));
jest.mock('../../middleware/logger', () => ({
  logger: { error: jest.fn(), info: jest.fn(), warn: jest.fn() },
}));

const express = require('express');
const request = require('supertest');

global.fetch = jest.fn();
const router = require('../../routes/proxy');

function makeApp(authenticated = true) {
  const app = express();
  app.use((req, _res, next) => { req.session = { authenticated }; next(); });
  app.use('/api/proxy', router);
  return app;
}

beforeEach(() => jest.clearAllMocks());

test('division performance proxy requires a session', async () => {
  const response = await request(makeApp(false)).get('/api/proxy/performance/divisions');
  expect(response.status).toBe(401);
  expect(global.fetch).not.toHaveBeenCalled();
});

test('division performance proxy forwards internal authentication', async () => {
  const payload = { accounting_truth: 'bankroll_ledger', divisions: [], totals: {} };
  global.fetch.mockResolvedValue({ status: 200, json: async () => payload });
  const response = await request(makeApp()).get('/api/proxy/performance/divisions');
  expect(response.status).toBe(200);
  expect(response.body).toEqual(payload);
  expect(global.fetch).toHaveBeenCalledWith(
    'http://python-engine:8000/performance/divisions',
    expect.objectContaining({
      method: 'GET',
      headers: expect.objectContaining({ 'X-Internal-Secret': 'internal-test-secret' }),
    }),
  );
});
