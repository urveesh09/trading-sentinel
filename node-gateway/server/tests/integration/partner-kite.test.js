jest.mock('../../config', () => ({
  INTERNAL_API_SECRET: 'internal-test-secret',
  PYTHON_ENGINE_URL: 'http://python-engine:8000',
  PYTHON_ENGINE_TIMEOUT_MS: 5000,
}));
jest.mock('../../middleware/logger', () => ({
  logger: { error: jest.fn(), info: jest.fn(), warn: jest.fn() },
}));
jest.mock('../../middleware/security', () => ({
  limiters: { authCallback: (_req, _res, next) => next(), reviewPdf: (_req, _res, next) => next() },
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
  global.fetch.mockResolvedValue(engineReply(200, { connected: true, account: 'AB***34', sync: { state: 'enriching' } }));
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

test('[O23-PH] the day list needs a session and asks the engine for its 120 days', async () => {
  expect((await request(makeApp().app).get('/api/partner-kite/review/days')).status).toBe(401);
  global.fetch.mockResolvedValue(engineReply(200, { days: ['2026-10-23'], today: '2026-10-23' }));
  const response = await request(makeApp({ partner_view: { since: 'x' } }).app).get('/api/partner-kite/review/days?evil=1');
  expect(response.status).toBe(200);
  expect(response.body.days).toEqual(['2026-10-23']);
  expect(global.fetch.mock.calls.map(([url]) => url)).toEqual(['http://python-engine:8000/partner/review/days']);
});

const PDF = Buffer.from('%PDF-1.4\nreview\n%%EOF\n');
const pdfReply = (status, type, disposition, body = PDF) => ({
  status,
  headers: { get: (name) => ({ 'content-type': type, 'content-disposition': disposition })[name.toLowerCase()] ?? null },
  arrayBuffer: async () => body.buffer.slice(body.byteOffset, body.byteOffset + body.length),
  json: async () => ({ detail: { code: '<b>odd</b>' } }),
});
const binary = (res, done) => {
  const chunks = [];
  res.on('data', (chunk) => chunks.push(chunk));
  res.on('end', () => done(null, Buffer.concat(chunks)));
};

test('[O23-PD] the PDF needs a session, passes a valid day only and returns the file under a fixed name', async () => {
  expect((await request(makeApp().app).get('/api/partner-kite/review/pdf')).status).toBe(401);
  const partner = makeApp({ partner_view: { since: 'x' } }).app;
  for (const bad of ['19-10-2026', '2026-10-19%27%3B', '']) {
    expect((await request(partner).get(`/api/partner-kite/review/pdf?day=${bad}`)).status).toBe(400);
  }
  expect(global.fetch).not.toHaveBeenCalled();
  global.fetch.mockResolvedValue(pdfReply(200, 'application/pdf', 'attachment; filename="trading-review-2026-10-23.pdf"'));
  const response = await request(partner).get('/api/partner-kite/review/pdf?day=2026-10-23&evil=1').buffer(true).parse(binary);
  expect(response.status).toBe(200);
  expect(response.headers['content-type']).toBe('application/pdf');
  expect(response.headers['content-disposition']).toBe('attachment; filename="trading-review-2026-10-23.pdf"');
  expect(response.headers['cache-control']).toBe('no-store');
  expect(Buffer.compare(response.body, PDF)).toBe(0);
  const [url, options] = global.fetch.mock.calls[0];
  expect(url).toBe('http://python-engine:8000/partner/review/pdf?day=2026-10-23');
  expect(options.headers['X-Internal-Secret']).toBe('internal-test-secret');
  // No day: the engine picks it; an odd file name from the engine is replaced.
  global.fetch.mockResolvedValue(pdfReply(200, 'application/pdf', 'attachment; filename="../../etc/passwd"'));
  const owner = await request(makeApp({ authenticated: true }).app).get('/api/partner-kite/review/pdf').buffer(true).parse(binary);
  expect(owner.headers['content-disposition']).toBe('attachment; filename="trading-review.pdf"');
  expect(global.fetch.mock.calls[1][0]).toBe('http://python-engine:8000/partner/review/pdf');
});

test('[O23-PD] anything but a PDF from the engine becomes a fixed error', async () => {
  const partner = makeApp({ partner_view: { since: 'x' } }).app;
  const cases = [
    [pdfReply(503, 'application/json'), 502],
    [pdfReply(422, 'application/json'), 400],
    [pdfReply(200, 'text/html', null, Buffer.from('<script>x</script>')), 502],
  ];
  for (const [reply, status] of cases) {
    global.fetch.mockResolvedValueOnce(reply);
    const response = await request(partner).get('/api/partner-kite/review/pdf?day=2026-10-23');
    expect(response.status).toBe(status);
    expect(response.body).toEqual({ error: 'pdf_unavailable', message: 'The PDF could not be made. Try again in a minute.' });
    expect(response.text).not.toContain('odd');
  }
  global.fetch.mockRejectedValueOnce(new Error('ECONNREFUSED'));
  const down = await request(partner).get('/api/partner-kite/review/pdf?day=2026-10-23');
  expect(down.status).toBe(502);
  expect(down.body.error).toBe('bad_gateway');
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
