const express = require('express');
const router = express.Router();
const kite = require('../services/kite');
const tokenStore = require('../services/token-store');
const config = require('../config');
const { logger } = require('../middleware/logger');
const { requireSession } = require('../middleware/auth');
const { limiters } = require('../middleware/security');
const { withRetry } = require('../utils/retry');

// [O21-PK] The partner now logs in to Zerodha for their review. Their account
// (or any account that is not the owner's) must never become the system's
// token or an owner session through this callback.
const sameAccount = (a, b) => String(a || '').trim().toUpperCase() === String(b || '').trim().toUpperCase();
function ownerAccount(userId) {
  if (config.ZERODHA_USER_ID) return sameAccount(userId, config.ZERODHA_USER_ID);
  if (config.PARTNER_KITE_USER_ID) return !sameAccount(userId, config.PARTNER_KITE_USER_ID);
  return true;
}

// Generate Zerodha login URL
router.get('/login', limiters.authLogin, (req, res) => {
  logger.info({ event_type: 'auth_initiated' }, 'Zerodha OAuth initiated');
  res.redirect(kite.getLoginURL());
});

// OAuth Callback from Zerodha
router.get('/callback', limiters.authCallback, async (req, res, next) => {
  try {
    const { request_token, status } = req.query;

    if (status !== 'success' || !request_token) {
      logger.warn({ event_type: 'auth_failed', status }, 'Zerodha login failed or denied');
      return res.redirect('/login?error=zerodha_failed');
    }

    // Generate session token
    const { accessToken, userId } = await kite.generateSessionWithUser(request_token, config.ZERODHA_API_SECRET);
    if (!ownerAccount(userId)) {
      // Nothing is stored, provisioned or authenticated; every gateway Kite
      // call re-arms the stored owner token, so the SDK state is harmless.
      logger.warn({ event_type: 'auth_wrong_account' }, 'Zerodha login by a non-owner account refused');
      return res.redirect('/login?error=wrong_account');
    }
    tokenStore.setToken(accessToken);

    // Setup secure session
    req.session.authenticated = true;
    req.session.login_time = new Date().toISOString();

    // Provision token to Container B (Non-fatal if B is unreachable)
    try {
      await withRetry(async () => {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 2000);
        const resp = await fetch(`${config.PYTHON_ENGINE_URL}/token`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Internal-Secret': config.INTERNAL_API_SECRET
          },
          body: JSON.stringify({ access_token: accessToken }),
          signal: controller.signal
        });
        clearTimeout(timeout);
        if (!resp.ok) throw new Error(`Engine returned ${resp.status}`);
      }, 3, 1000);
    } catch (err) {
      logger.warn({ event_type: 'engine_provision_failed', err: err.message }, 'Failed to provision token to Container B');
    }

    // Notify via Telegram
    const telegram = require('../services/telegram');
    telegram.sendAlert('✅ Zerodha authenticated successfully. System ready.');
    logger.info({ event_type: 'auth_success' }, 'Zerodha login complete');

    res.redirect('/');
  } catch (err) {
    next(err);
  }
});

// Check current auth status
router.get('/status', (req, res) => {
  const tokenInfo = tokenStore.getStatus();
  let ageMinutes = null;
  
  if (tokenInfo.generatedAt) {
    ageMinutes = Math.floor((Date.now() - new Date(tokenInfo.generatedAt).getTime()) / 60000);
  }

  res.json({
    authenticated: req.session?.authenticated || false,
    // [O21-PK] A coach-only session from the partner's Zerodha login.
    partner_view: Boolean(req.session?.partner_view),
    login_time: req.session?.login_time || null,
    token_age_min: ageMinutes
  });
});

// Logout and clear tokens
router.post('/logout', requireSession, async (req, res) => {
  tokenStore.clearToken();
  
  // Notify Container B to void token
  try {
    await fetch(`${config.PYTHON_ENGINE_URL}/token/invalidate`, {
      method: 'POST',
      headers: { 'X-Internal-Secret': config.INTERNAL_API_SECRET }
    });
  } catch (err) {
    logger.warn({ event_type: 'engine_invalidate_failed' }, 'Could not notify Container B of logout');
  }

  req.session.destroy(() => {
    res.json({ success: true, message: 'Logged out successfully' });
  });
});

module.exports = router;
