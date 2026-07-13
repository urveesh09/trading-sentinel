/**
 * [ROADMAP-2.1 2026-07-12] Boot-time token re-arm.
 *
 * The token store is in-memory by design, so any mid-day node restart
 * used to silently disarm execution (EXEC buttons dead) while
 * python-engine kept scanning -- until the operator noticed and
 * re-logged-in. python-engine persists the day's token to /data and
 * now serves it back over the authenticated internal channel
 * (GET /token/current, gated by X-Internal-Secret, same-IST-day
 * freshness rule). We ask it once at startup.
 *
 * Node still never writes a token to disk. On a cold morning boot the
 * engine answers { armed: false } (yesterday's token is stale) and the
 * normal /login flow is unchanged.
 */
const config = require('../config');
const tokenStore = require('./token-store');
const { logger } = require('../middleware/logger');

async function restoreTokenFromEngine({ attempts = 3, delayMs = 5000 } = {}) {
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 3000);
      const resp = await fetch(`${config.PYTHON_ENGINE_URL}/token/current`, {
        headers: { 'X-Internal-Secret': config.INTERNAL_API_SECRET },
        signal: controller.signal
      });
      clearTimeout(timeout);
      if (!resp.ok) throw new Error(`Engine returned ${resp.status}`);

      const data = await resp.json();
      if (!data.armed || !data.access_token) {
        logger.info({ event_type: 'token_restore_skipped' },
          'Engine holds no fresh token (normal before the daily login)');
        return false;
      }

      tokenStore.setToken(data.access_token);
      logger.info({ event_type: 'token_restore_success' },
        'Kite token re-armed from python-engine after restart');
      return true;
    } catch (err) {
      logger.warn({ event_type: 'token_restore_attempt_failed', attempt, err: err.message },
        `Token restore attempt ${attempt}/${attempts} failed`);
      if (attempt < attempts) await new Promise(r => setTimeout(r, delayMs));
    }
  }
  // Engine unreachable (e.g. full-stack cold boot where python is still
  // starting). Non-fatal: the reconciliation cron on the python side
  // pages the operator if a real mismatch persists into market hours.
  logger.warn({ event_type: 'token_restore_failed' },
    'Could not reach python-engine to restore token; continuing disarmed');
  return false;
}

module.exports = { restoreTokenFromEngine };
