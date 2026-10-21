jest.mock('../../config', () => ({
  INTERNAL_API_SECRET: 'internal-test-secret',
  PYTHON_ENGINE_URL: 'http://python-engine:8000',
  PYTHON_ENGINE_TIMEOUT_MS: 5000,
}));
jest.mock('../../middleware/logger', () => ({
  logger: { error: jest.fn(), info: jest.fn(), warn: jest.fn() },
}));
jest.mock('../../middleware/security', () => ({
  limiters: { authCallback: (_req, _res, next) => next() },
}));

const express = require('express');
const request = require('supertest');

global.fetch = jest.fn();
const partnerKite = require('../../routes/partner-kite');
const proxy = require('../../routes/proxy');

function makeApp(session = {}) {
  const app = express();
  app.use(express.json());
  app.use((req, _res, next) => { req.session = session; next(); });
  app.use('/api/partner-kite', partnerKite);
  app.use('/api/proxy', proxy);
  return { app, session };
}

const engineReply = (status, data) => ({ status, json: async () => data });

beforeEach(() => jest.clearAllMocks());

test('a completed login opens a coach-only session and the review page', async () => {
  global.fetch.mockResolvedValue(engineReply(200, { connected: true, account: 'AB***34', note: 'sent' }));
  const { app, session } = makeApp();
  const response = await request(app).get('/api/partner-kite/callback?status=success&request_token=abcDEF123456');
  expect(response.status).toBe(302);
  expect(response.headers.location).toBe('/?view=review');
  const [url, options] = global.fetch.mock.calls[0];
  expect(url).toBe('http://python-engine:8000/partner/broker/session');
  expect(JSON.parse(options.body)).toEqual({ request_token: 'abcDEF123456' });
  expect(options.headers['X-Internal-Secret']).toBe('internal-test-secret');
  expect(session.partner_view).toEqual(expect.objectContaining({ account: 'AB***34' }));
  expect(session.authenticated).toBeUndefined();
});

test('incomplete or malformed logins never reach the engine', async () => {
  const { app, session } = makeApp();
  for (const query of ['status=cancelled&request_token=abcDEF123456', 'status=success',
    'status=success&request_token=a%3Cscript%3E', 'status=success&request_token=abc']) {
    const response = await request(app).get(`/api/partner-kite/callback?${query}`);
    expect(response.status).toBe(400);
    expect(response.text).toContain('Zerodha login was not completed');
    expect(response.text).not.toContain('<script>');
  }
  expect(global.fetch).not.toHaveBeenCalled();
  expect(session.partner_view).toBeUndefined();
});

test('a refused login shows a fixed message and opens nothing', async () => {
  const cases = [
    [403, { detail: { code: 'wrong_account' } }, 403, 'not the one set up'],
    [401, { detail: { code: 'TokenException' } }, 502, 'expired before it reached us'],
    [503, { detail: { code: 'not_configured' } }, 502, 'not set up yet'],
    [502, { detail: { code: '<b>odd</b>' } }, 502, 'unavailable right now'],
  ];
  for (const [engineStatus, body, status, text] of cases) {
    global.fetch.mockResolvedValueOnce(engineReply(engineStatus, body));
    const { app, session } = makeApp();
    const response = await request(app).get('/api/partner-kite/callback?status=success&request_token=abcDEF123456');
    expect(response.status).toBe(status);
    expect(response.text).toContain(text);
    expect(response.text).not.toContain('odd');
    expect(session.partner_view).toBeUndefined();
  }
  global.fetch.mockRejectedValueOnce(new Error('ECONNREFUSED'));
  const response = await request(makeApp().app).get('/api/partner-kite/callback?status=success&request_token=abcDEF123456');
  expect(response.status).toBe(502);
});

test('the coach view needs a partner or owner session and forwards only days', async () => {
  const denied = await request(makeApp().app).get('/api/partner-kite/coach');
  expect(denied.status).toBe(401);
  expect(global.fetch).not.toHaveBeenCalled();
  global.fetch.mockResolvedValue(engineReply(200, { summary: {} }));
  const partner = makeApp({ partner_view: { since: 'x' } }).app;
  await request(partner).get('/api/partner-kite/coach?days=7&evil=1');
  await request(partner).get('/api/partner-kite/coach?days=9999');
  await request(partner).get('/api/partner-kite/coach');
  await request(makeApp({ authenticated: true }).app).get('/api/partner-kite/coach?days=30');
  expect(global.fetch.mock.calls.map(([url]) => url)).toEqual([
    'http://python-engine:8000/partner/coach?days=7',
    'http://python-engine:8000/partner/coach?days=120',
    'http://python-engine:8000/partner/coach?days=1',
    'http://python-engine:8000/partner/coach?days=30',
  ]);
});

test('the review forwards a valid day and a bounded window only', async () => {
  const denied = await request(makeApp().app).get('/api/partner-kite/review');
  expect(denied.status).toBe(401);
  global.fetch.mockResolvedValue(engineReply(200, { review: {} }));
  const partner = makeApp({ partner_view: { since: 'x' } }).app;
  await request(partner).get('/api/partner-kite/review');
  await request(partner).get('/api/partner-kite/review?day=2026-10-19&days=500&evil=1');
  await request(partner).get('/api/partner-kite/review?days=3');
  expect(global.fetch.mock.calls.map(([url]) => url)).toEqual([
    'http://python-engine:8000/partner/review?days=30',
    'http://python-engine:8000/partner/review?day=2026-10-19&days=120',
    'http://python-engine:8000/partner/review?days=14',
  ]);
  for (const bad of ['19-10-2026', '2026-10-19%27%3B', '']) {
    expect((await request(partner).get(`/api/partner-kite/review?day=${bad}`)).status).toBe(400);
  }
  expect(global.fetch).toHaveBeenCalledTimes(3);
});

test('a partner session opens nothing behind /api/proxy', async () => {
  const partner = makeApp({ partner_view: { since: 'x' } }).app;
  for (const path of ['/api/proxy/partner/coach', '/api/proxy/positions', '/api/proxy/performance/standard-capital']) {
    expect((await request(partner).get(path)).status).toBe(401);
  }
  expect((await request(partner).post('/api/proxy/partner/broker/sync')).status).toBe(401);
  expect(global.fetch).not.toHaveBeenCalled();
});

test('the owner can re-read the partner book', async () => {
  global.fetch.mockResolvedValue(engineReply(200, { days: {} }));
  const response = await request(makeApp({ authenticated: true }).app).post('/api/proxy/partner/broker/sync');
  expect(response.status).toBe(200);
  expect(global.fetch.mock.calls[0][0]).toBe('http://python-engine:8000/partner/broker/sync');
  expect(global.fetch.mock.calls[0][1].method).toBe('POST');
});
