/**
 * Unit tests for middleware/auth.js
 *
 * Tests: requireSession, requireInternalSecret
 */
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '..', '..', '.env.test'), override: true });

const { requireSession, requireInternalSecret } = require('../../middleware/auth');

// ── Helpers ──
function makeMockReq(overrides = {}) {
  return {
    session: overrides.session || null,
    headers: overrides.headers || {},
  };
}

function makeMockRes() {
  const res = {
    statusCode: null,
    body: null,
    status(code) { res.statusCode = code; return res; },
    json(data) { res.body = data; return res; },
  };
  return res;
}

// ─────────────────────────────────────────────────────────────────
// requireSession
// ─────────────────────────────────────────────────────────────────

describe('requireSession()', () => {
  test('returns 401 when no session exists', () => {
    const req = makeMockReq({ session: null });
    const res = makeMockRes();
    const next = jest.fn();

    requireSession(req, res, next);

    expect(res.statusCode).toBe(401);
    expect(res.body.error).toBe('unauthorized');
    expect(next).not.toHaveBeenCalled();
  });

  test('returns 401 when session exists but not authenticated', () => {
    const req = makeMockReq({ session: { authenticated: false } });
    const res = makeMockRes();
    const next = jest.fn();

    requireSession(req, res, next);

    expect(res.statusCode).toBe(401);
    expect(next).not.toHaveBeenCalled();
  });

  test('calls next() when session is authenticated', () => {
    const req = makeMockReq({ session: { authenticated: true } });
    const res = makeMockRes();
    const next = jest.fn();

    requireSession(req, res, next);

    expect(next).toHaveBeenCalledTimes(1);
    expect(res.statusCode).toBeNull();
  });

  test('returns 401 when session is undefined', () => {
    const req = { headers: {} }; // no session property at all
    const res = makeMockRes();
    const next = jest.fn();

    requireSession(req, res, next);

    expect(res.statusCode).toBe(401);
    expect(next).not.toHaveBeenCalled();
  });
});

// ─────────────────────────────────────────────────────────────────
// requireInternalSecret
// ─────────────────────────────────────────────────────────────────

describe('requireInternalSecret()', () => {
  const VALID_SECRET = process.env.INTERNAL_API_SECRET || 'test_internal_secret_32chars_long';

  test('returns 403 when X-Internal-Secret header is missing', () => {
    const req = makeMockReq({ headers: {} });
    const res = makeMockRes();
    const next = jest.fn();

    requireInternalSecret(req, res, next);

    expect(res.statusCode).toBe(403);
    expect(res.body.error).toBe('forbidden');
    expect(next).not.toHaveBeenCalled();
  });

  test('returns 403 when X-Internal-Secret header is wrong', () => {
    const req = makeMockReq({ headers: { 'x-internal-secret': 'wrong_value' } });
    const res = makeMockRes();
    const next = jest.fn();

    requireInternalSecret(req, res, next);

    expect(res.statusCode).toBe(403);
    expect(next).not.toHaveBeenCalled();
  });

  test('calls next() when X-Internal-Secret matches', () => {
    const req = makeMockReq({ headers: { 'x-internal-secret': VALID_SECRET } });
    const res = makeMockRes();
    const next = jest.fn();

    requireInternalSecret(req, res, next);

    expect(next).toHaveBeenCalledTimes(1);
    expect(res.statusCode).toBeNull();
  });

  test('returns 403 when header is empty string', () => {
    const req = makeMockReq({ headers: { 'x-internal-secret': '' } });
    const res = makeMockRes();
    const next = jest.fn();

    requireInternalSecret(req, res, next);

    expect(res.statusCode).toBe(403);
    expect(next).not.toHaveBeenCalled();
  });
});
