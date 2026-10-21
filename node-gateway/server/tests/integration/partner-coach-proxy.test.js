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
  app.use(express.json());
  app.use((req, _res, next) => { req.session = { authenticated }; next(); });
  app.use('/api/proxy', router);
  return app;
}

beforeEach(() => jest.clearAllMocks());

test('partner coach and standard capital need a session', async () => {
  for (const path of ['/api/proxy/partner/coach', '/api/proxy/performance/standard-capital']) {
    const response = await request(makeApp(false)).get(path);
    expect(response.status).toBe(401);
  }
  expect(global.fetch).not.toHaveBeenCalled();
});

test('coach view forwards only the days query', async () => {
  global.fetch.mockResolvedValue({ status: 200, json: async () => ({ summary: {} }) });
  const response = await request(makeApp()).get('/api/proxy/partner/coach?days=7&evil=1');
  expect(response.status).toBe(200);
  expect(global.fetch).toHaveBeenCalledWith(
    'http://python-engine:8000/partner/coach?days=7',
    expect.objectContaining({ method: 'GET',
      headers: expect.objectContaining({ 'X-Internal-Secret': 'internal-test-secret' }) }),
  );
});

test('standard capital forwards capital and since', async () => {
  global.fetch.mockResolvedValue({ status: 200, json: async () => ({ books: [] }) });
  await request(makeApp()).get('/api/proxy/performance/standard-capital?capital=500000&since=2026-09-01');
  expect(global.fetch.mock.calls[0][0])
    .toBe('http://python-engine:8000/performance/standard-capital?capital=500000&since=2026-09-01');
});

test('a report POST is forwarded and a bad void id never reaches the engine', async () => {
  global.fetch.mockResolvedValue({ status: 200, json: async () => ({ recorded: true }) });
  const body = { action: 'BUY', trade_at: '2026-10-21T12:09:00+05:30', advisory_id: 'abc123def456', price: 518.5, lots: 1 };
  const response = await request(makeApp()).post('/api/proxy/partner/coach/reports').send(body);
  expect(response.status).toBe(200);
  const [url, options] = global.fetch.mock.calls[0];
  expect(url).toBe('http://python-engine:8000/partner/coach/reports');
  expect(JSON.parse(options.body)).toEqual(body);
  const bad = await request(makeApp()).post('/api/proxy/partner/coach/reports/1%3Bdrop/void').send({});
  expect(bad.status).toBe(400);
  expect(global.fetch).toHaveBeenCalledTimes(1);
  await request(makeApp()).post('/api/proxy/partner/coach/reports/42/void').send({ note: 'typo' });
  expect(global.fetch.mock.calls[1][0]).toBe('http://python-engine:8000/partner/coach/reports/42/void');
});
