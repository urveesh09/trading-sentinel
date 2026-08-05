/**
 * [HALT 2026-08-05] Filesystem kill switch — node-gateway half.
 *
 * The mirror of python-engine/halt_switch.py. Both containers mount the same
 * `trading_data` volume at /data, so one `touch /data/HALT` stops every order
 * path in the system regardless of which container owns it.
 *
 * This half is READ-ONLY BY DESIGN. Trips and clears happen in python-engine.
 * node-gateway keeps its long-standing "writes nothing to /data" posture (see
 * services/token-store.js) — it only needs to obey the switch, not operate it.
 *
 * FAIL-CLOSED, PRECISELY
 * ----------------------
 * The file's EXISTENCE is the halt; its JSON is attribution only and can never
 * un-halt. `fs.existsSync` is deliberately NOT used: it swallows every error
 * into `false`, so an EACCES or EIO on /data would read as "not halted" and
 * fail OPEN on exactly the storage faults that should stop us cold. We stat
 * directly and treat any error that is not ENOENT as halted.
 *
 * ENTRIES ONLY
 * ------------
 * Callers gate entries. Exits — protective stops, unwinds, GTT legs — are
 * never gated: refusing an exit during a halt strands a live position with no
 * stop, which is strictly worse than whatever tripped the halt.
 */

const fs = require('fs');
const path = require('path');
const { logger } = require('../middleware/logger');

const HALT_DIR = process.env.HALT_DIR || '/data';
const GLOBAL_SENTINEL = 'HALT';

class TradingHaltedError extends Error {
  constructor(attribution) {
    const scope = (attribution && attribution.scope) || 'global';
    const by = (attribution && attribution.by) || 'unknown';
    const reason = (attribution && attribution.reason) || 'no reason recorded';
    super(`trading halted (${scope}) by ${by}: ${reason}`);
    this.name = 'TradingHaltedError';
    this.attribution = attribution || {};
  }
}

/** Sanitise a channel name so it cannot escape HALT_DIR. */
function safeChannel(channel) {
  const cleaned = String(channel).trim().toLowerCase().replace(/[^a-z0-9_-]/g, '');
  if (!cleaned) throw new Error(`channel name is empty after sanitising: ${channel}`);
  return cleaned;
}

function sentinelPath(channel) {
  if (channel === null || channel === undefined) {
    return path.join(HALT_DIR, GLOBAL_SENTINEL);
  }
  return path.join(HALT_DIR, `${GLOBAL_SENTINEL}.${safeChannel(channel)}`);
}

/**
 * Read one sentinel. Returns null when it is definitively absent, or an
 * attribution object when present or indeterminate.
 */
function readSentinel(p) {
  try {
    fs.statSync(p);
  } catch (err) {
    if (err && err.code === 'ENOENT') return null;
    // Cannot determine the kill switch state. Do not trade.
    logger.error({ event_type: 'halt_sentinel_stat_failed', path: p, reason: err.message },
      'halt sentinel unreadable — failing closed');
    return {
      by: 'unknown',
      reason: `halt sentinel unreadable (${err.code || err.message}); failing closed`,
      tripped_at: null,
      unreadable: true,
    };
  }

  let payload = {};
  try {
    const raw = fs.readFileSync(p, 'utf8');
    if (raw.trim()) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) payload = parsed;
    }
  } catch (err) {
    logger.warn({ event_type: 'halt_sentinel_payload_unparsed', path: p, reason: err.message },
      'halt sentinel present but unparseable — still halted');
  }

  if (payload.by === undefined) payload.by = 'manual_file';
  if (payload.reason === undefined) payload.reason = 'sentinel present with no recorded reason';
  if (payload.tripped_at === undefined) payload.tripped_at = null;
  return payload;
}

/**
 * Is trading halted? The global sentinel is checked first and always wins.
 * @returns {{halted: boolean, attribution: object|null}}
 */
function haltState(channel = null) {
  const globalPayload = readSentinel(sentinelPath(null));
  if (globalPayload !== null) {
    return { halted: true, attribution: { ...globalPayload, scope: 'global' } };
  }

  if (channel !== null && channel !== undefined) {
    let p;
    try {
      p = sentinelPath(channel);
    } catch (err) {
      // A malformed channel must not resolve to "not halted".
      logger.error({ event_type: 'halt_channel_invalid', channel, reason: err.message });
      return {
        halted: true,
        attribution: {
          by: 'unknown',
          reason: `invalid halt channel ${channel}; failing closed`,
          tripped_at: null,
          scope: String(channel),
        },
      };
    }
    const payload = readSentinel(p);
    if (payload !== null) {
      return { halted: true, attribution: { ...payload, scope: safeChannel(channel) } };
    }
  }

  return { halted: false, attribution: null };
}

/** Throw TradingHaltedError when a sentinel is present. Call before entries. */
function assertNotHalted(channel = null) {
  const { halted, attribution } = haltState(channel);
  if (halted) throw new TradingHaltedError(attribution);
}

/** One-line human summary for /status and Telegram. */
function describe(channel = null) {
  const { halted, attribution } = haltState(channel);
  if (!halted) return 'ARMED - no halt sentinel present';
  const a = attribution || {};
  return `HALTED (${a.scope || 'global'}) since ${a.tripped_at || 'unknown time'} `
       + `by ${a.by || 'unknown'}: ${a.reason || 'no reason recorded'}`;
}

module.exports = {
  TradingHaltedError,
  assertNotHalted,
  haltState,
  describe,
  sentinelPath,
  HALT_DIR,
};
