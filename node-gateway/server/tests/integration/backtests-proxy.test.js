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
  const instance = express();
  instance.use(express.json());
  instance.use((req, _res, next) => { req.session = { authenticated }; next(); });
  instance.use('/api/proxy', router);
  return instance;
}

beforeEach(() => jest.clearAllMocks());

test('backtest routes remain session authenticated', async () => {
  const response = await request(makeApp(false)).get('/api/proxy/backtests/strategies');
  expect(response.status).toBe(401);
  expect(global.fetch).not.toHaveBeenCalled();
});

test('list runs forwards query strings and internal auth', async () => {
  global.fetch.mockResolvedValue({ status: 200, json: async () => ({ runs: [] }) });
  const response = await request(makeApp()).get('/api/proxy/backtests/runs?limit=17&status=SUCCEEDED&strategy_id=swing_regime_daily');
  expect(response.status).toBe(200);
  const [url, options] = global.fetch.mock.calls[0];
  const parsed = new URL(url);
  expect(parsed.pathname).toBe('/backtests/runs');
  expect(Object.fromEntries(parsed.searchParams)).toEqual({
    limit: '17', status: 'SUCCEEDED', strategy_id: 'swing_regime_daily',
  });
  expect(options.headers['X-Internal-Secret']).toBe('internal-test-secret');
});

test('submit forwards JSON to a research endpoint', async () => {
  global.fetch.mockResolvedValue({ status: 202, json: async () => ({ status: 'QUEUED' }) });
  const payload = { strategy_id: 'swing_regime_daily', start_date: '2025-01-01', end_date: '2026-01-01' };
  const response = await request(makeApp()).post('/api/proxy/backtests/runs').send(payload);
  expect(response.status).toBe(202);
  const [url, options] = global.fetch.mock.calls[0];
  expect(url).toBe('http://python-engine:8000/backtests/runs');
  expect(options.method).toBe('POST');
  expect(JSON.parse(options.body)).toEqual(payload);
  expect(url).not.toMatch(/orders|execute/i);
});

test('run id is encoded before proxying', async () => {
  global.fetch.mockResolvedValue({ status: 404, json: async () => ({ detail: 'not found' }) });
  await request(makeApp()).get('/api/proxy/backtests/runs/a%2Fb');
  expect(global.fetch.mock.calls[0][0]).not.toContain('/a/b');
});
