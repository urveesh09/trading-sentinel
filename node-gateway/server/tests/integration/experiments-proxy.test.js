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

test('experiment proxy routes require a session', async () => {
  const response = await request(makeApp(false)).get('/api/proxy/experiments/momentum');
  expect(response.status).toBe(401);
  expect(global.fetch).not.toHaveBeenCalled();
});

test.each([
  ['momentum', '/experiments/momentum'],
  ['penny', '/experiments/penny'],
  ['fno-opening-range', '/experiments/fno-opening-range'],
])('proxies authenticated %s experiment evidence', async (route, enginePath) => {
  const payload = { enabled: true, status: 'empty', registry: {}, comparison: { variants: [] } };
  global.fetch.mockResolvedValue({ status: 200, json: async () => payload });
  const response = await request(makeApp()).get(`/api/proxy/experiments/${route}`);
  expect(response.status).toBe(200);
  expect(response.body).toEqual(payload);
  expect(global.fetch).toHaveBeenCalledWith(
    `http://python-engine:8000${enginePath}`,
    expect.objectContaining({
      method: 'GET',
      headers: expect.objectContaining({ 'X-Internal-Secret': 'internal-test-secret' }),
    }),
  );
});

test('promotion readiness proxy requires a session', async () => {
  const response = await request(makeApp(false)).get('/api/proxy/research/promotion-readiness');
  expect(response.status).toBe(401);
  expect(global.fetch).not.toHaveBeenCalled();
});

test('forwards authenticated promotion readiness with the internal secret', async () => {
  const payload = {
    research_only: true, can_place_orders: false, authorization_effect: 'NONE', families: [],
  };
  global.fetch.mockResolvedValue({ status: 200, json: async () => payload });
  const response = await request(makeApp()).get('/api/proxy/research/promotion-readiness');
  expect(response.status).toBe(200);
  expect(response.body).toEqual(payload);
  expect(global.fetch).toHaveBeenCalledWith(
    'http://python-engine:8000/research/promotion-readiness',
    expect.objectContaining({
      method: 'GET',
      headers: expect.objectContaining({ 'X-Internal-Secret': 'internal-test-secret' }),
    }),
  );
});
