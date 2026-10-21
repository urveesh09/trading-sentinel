// [O21-PK 2026-10-21] The partner's own Zerodha login and their coach view.
//
// The partner's Kite Connect "Personal" app redirects here after login
// (register <public URL>/api/partner-kite/callback as its redirect URL). The
// engine exchanges the one-time request_token, refuses any account other than
// PARTNER_KITE_USER_ID and reads the day's orders, read-only. The browser then
// gets a coach-only session: `partner_view`, never `authenticated`, so every
// /api/proxy, /api/orders and /api/token route stays closed to it.
const express = require('express');
const config = require('../config');
const { logger } = require('../middleware/logger');
const { limiters } = require('../middleware/security');

const router = express.Router();

const REQUEST_TOKEN = /^[A-Za-z0-9]{8,64}$/;
const DAY = /^\d{4}-\d{2}-\d{2}$/;
// Session exchange, the order-book reads, [O21-PX] order histories and the
// traded options' prices (the engine caps those at 20 s), then the coach
// note. Under nginx's 60 s proxy timeout, so the page always gets an answer.
const SESSION_TIMEOUT_MS = 45000;

// Fixed texts only: nothing from the query or the engine reaches the page.
const MESSAGES = {
  not_completed: 'Zerodha login was not completed. Tap the button in Telegram again.',
  wrong_account: 'That Zerodha account is not the one set up for your review.',
  not_configured: 'Your review is not set up yet. Ask the owner to add your Zerodha app.',
  expired: 'The Zerodha login expired before it reached us. Tap the button in Telegram again.',
  unavailable: 'The review is unavailable right now. Try again in a few minutes.',
};
const ENGINE_CODE_MESSAGE = {
  wrong_account: 'wrong_account',
  not_configured: 'not_configured',
  TokenException: 'expired',
  bad_request_token: 'not_completed',
};

function page(res, status, key) {
  res.status(status).type('html').send(
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    + '<meta name="viewport" content="width=device-width, initial-scale=1">'
    + `<title>Today's review</title></head><body><h1>Today's review</h1><p>${MESSAGES[key]}</p></body></html>`,
  );
}

async function engine(path, { method = 'GET', body, timeoutMs = config.PYTHON_ENGINE_TIMEOUT_MS } = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${config.PYTHON_ENGINE_URL}${path}`, {
      method,
      headers: { 'X-Internal-Secret': config.INTERNAL_API_SECRET, 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    const data = await response.json().catch(() => ({}));
    return { status: response.status, data };
  } finally {
    clearTimeout(timeout);
  }
}

router.get('/callback', limiters.authCallback, async (req, res) => {
  const { request_token: token, status } = req.query;
  if (status !== 'success' || typeof token !== 'string' || !REQUEST_TOKEN.test(token)) {
    logger.warn({ event_type: 'partner_kite_login_incomplete' }, 'Partner Zerodha login not completed');
    return page(res, 400, 'not_completed');
  }
  let result;
  try {
    result = await engine('/partner/broker/session', {
      method: 'POST', body: { request_token: token }, timeoutMs: SESSION_TIMEOUT_MS,
    });
  } catch (err) {
    logger.error({ event_type: 'partner_kite_login_failed', err: err.name }, 'Engine unreachable for partner login');
    return page(res, 502, 'unavailable');
  }
  if (result.status !== 200) {
    const code = result.data?.detail?.code;
    logger.warn({ event_type: 'partner_kite_login_refused', status: result.status, code }, 'Partner Zerodha login refused');
    const key = ENGINE_CODE_MESSAGE[code] || 'unavailable';
    return page(res, key === 'wrong_account' ? 403 : result.status === 400 ? 400 : 502, key);
  }
  req.session.partner_view = { since: new Date().toISOString(), account: result.data?.account || null };
  logger.info({ event_type: 'partner_kite_login', note: result.data?.note }, 'Partner Zerodha login; coach view opened');
  return res.redirect('/?view=review');
});

const allowCoach = (req, res, next) => {
  if (req.session?.partner_view || req.session?.authenticated) return next();
  return res.status(401).json({ error: 'unauthorized', message: 'Open the review from the Telegram button' });
};

async function forward(res, path) {
  try {
    const result = await engine(path);
    return res.status(result.status).json(result.data);
  } catch (err) {
    logger.error({ event_type: 'proxy_error', path: path.split('?')[0], err: err.message });
    return res.status(502).json({ error: 'bad_gateway', message: 'Quant Engine is unreachable.' });
  }
}

// The coach view only. `days` is the one parameter passed on.
router.get('/coach', allowCoach, (req, res) => {
  const days = Math.min(Math.max(Number.parseInt(req.query.days, 10) || 1, 1), 120);
  return forward(res, `/partner/coach?days=${days}`);
});

// [O21-PL] The partner's day review (today's learnings) and progress.
router.get('/review', allowCoach, (req, res) => {
  const params = new URLSearchParams();
  if (req.query.day !== undefined) {
    if (typeof req.query.day !== 'string' || !DAY.test(req.query.day)) {
      return res.status(400).json({ error: 'bad_request', message: 'day must be YYYY-MM-DD' });
    }
    params.set('day', req.query.day);
  }
  params.set('days', String(Math.min(Math.max(Number.parseInt(req.query.days, 10) || 30, 14), 120)));
  return forward(res, `/partner/review?${params}`);
});

module.exports = router;
