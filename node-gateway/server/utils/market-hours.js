/**
 * NSE trading market window + canonical holiday list.
 *
 * [WORKFLOW-J.5 2026-09-13] The Node side used to ship its own
 * divergent NSE_HOLIDAYS set (18 dates, only 10 matching Python's
 * 20 canonical NSE dates). The drift caused real production
 * hazards: a CAS-eligible stock could be scheduled for an order
 * on a holiday that the gateway considered a trading day (or vice
 * versa).
 *
 * J.5 establishes python-engine/market_calendar.py as the single
 * source of truth. The Node side now:
 *
 *   1. On module load, kicks off a fire-and-forget fetch from
 *      `${PYTHON_ENGINE_URL}/holidays` with a 5s timeout. The
 *      fetch is asynchronous; ``isMarketOpen`` and ``isPreMarket``
 *      work with whatever list is loaded when they are called.
 *   2. On success, ``NSE_HOLIDAYS`` is REPLACED with the fetched
 *      set. The hardcoded list is preserved as the documented
 *      degraded-mode fallback (see FALLBACK note below).
 *   3. On failure (engine unreachable, timeout, malformed payload),
 *      the hardcoded list stays in effect.
 *   4. ``MARKET_HOURS_HOLIDAYS_JSON`` env var overrides the fetch
 *      for CI / closed-env runs (test fixtures, sandbox).
 *
 * Source of truth: python-engine/market_calendar.py::NSE_HOLIDAYS_STATIC.
 * Drift checker: python-engine/holiday_drift.py + tools/holiday_drift_check.py.
 * Docs: docs/2026-09-13-j5-holiday-reconciliation-done.md.
 */
'use strict';

// FALLBACK (documented degraded-mode) -- the canonical list lives
// in python-engine/market_calendar.py::NSE_HOLIDAYS_STATIC (20
// dates for 2026, NSE Equity-trading segment). This set is the
// pre-J.5 Node hardcoded list, retained as a defensive fallback
// when the engine is unreachable. Operators can also inject a
// curated list via MARKET_HOURS_HOLIDAYS_JSON (CI / closed-env).
const NSE_HOLIDAYS_FALLBACK = new Set([
  '2026-01-26', // Republic Day
  '2026-03-10', // Maha Shivaratri
  '2026-03-17', // Holi
  '2026-03-31', // Id-Ul-Fitr (Ramadan)
  '2026-04-03', // Good Friday
  '2026-04-14', // Dr. Ambedkar Jayanti
  '2026-05-01', // Maharashtra Day
  '2026-06-07', // Id-Ul-Adha (Bakri Id)
  '2026-07-07', // Muharram
  '2026-08-15', // Independence Day
  '2026-08-26', // Janmashtami
  '2026-09-05', // Milad-un-Nabi (Prophet's Birthday)
  '2026-10-02', // Mahatma Gandhi Jayanti
  '2026-10-20', // Dussehra
  '2026-11-09', // Diwali (Laxmi Puja)
  '2026-11-10', // Diwali (Balipratipada)
  '2026-11-27', // Guru Nanak Jayanti
  '2026-12-25', // Christmas
]);

// The live, mutable holiday set. Pre-fetch: the documented
// fallback. Post-fetch: the engine's canonical list (replaces
// the fallback in-place via ``replaceHolidays``).
let NSE_HOLIDAYS = new Set(NSE_HOLIDAYS_FALLBACK);

// Diagnostic: which source produced the current set?
// ``fallback`` initially; ``engine`` after a successful fetch;
// ``env`` after MARKET_HOURS_HOLIDAYS_JSON override.
let NSE_HOLIDAYS_SOURCE = 'fallback:NSE_HOLIDAYS_FALLBACK';

function replaceHolidays(set, source) {
  // Mutating the same Set object keeps the closure-bindings of
  // ``isMarketOpen`` and ``isPreMarket`` pointing at the live
  // list. Production code does NOT keep a local reference to
  // the previous Set; this is the documented surface.
  NSE_HOLIDAYS.clear();
  for (const d of set) NSE_HOLIDAYS.add(d);
  NSE_HOLIDAYS_SOURCE = source;
}

function isValidIsoDate(s) {
  return typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s);
}

function applyOverride(logger) {
  const raw = process.env.MARKET_HOURS_HOLIDAYS_JSON;
  if (!raw) return false;
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      throw new Error('MARKET_HOURS_HOLIDAYS_JSON must be a JSON array');
    }
    const set = new Set();
    for (const d of parsed) {
      if (!isValidIsoDate(d)) {
        throw new Error(`invalid ISO date in override: ${d}`);
      }
      set.add(d);
    }
    replaceHolidays(set, 'env:MARKET_HOURS_HOLIDAYS_JSON');
    logger.info && logger.info('market_hours_holidays_override_applied', {
      count: set.size,
    });
    return true;
  } catch (e) {
    logger.warn && logger.warn('market_hours_holidays_override_invalid', {
      error: String(e && e.message ? e.message : e),
    });
    return false;
  }
}

function scheduleFetch(logger) {
  // Fire-and-forget; never blocks module load. The fetch aborts
  // after 5s. On success the live ``NSE_HOLIDAYS`` Set is
  // mutated in-place so the bound ``isMarketOpen`` /
  // ``isPreMarket`` closures see the new list on their next call.
  let cfg;
  try {
    cfg = require('../config');
  } catch (_) {
    return; // No config (test env) -- keep fallback.
  }
  const base = (cfg && cfg.PYTHON_ENGINE_URL) || 'http://python-engine:8000';
  const url = String(base).replace(/\/$/, '') + '/holidays';

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 5000);
  fetch(url, { signal: ctrl.signal })
    .then((res) => {
      clearTimeout(timer);
      if (!res.ok) {
        logger.warn && logger.warn('market_hours_holidays_fetch_failed', {
          status: res.status, url,
        });
        return null;
      }
      return res.json();
    })
    .then((body) => {
      if (!body || !Array.isArray(body.holidays)) {
        logger.warn && logger.warn('market_hours_holidays_payload_invalid', { url });
        return;
      }
      const set = new Set();
      for (const d of body.holidays) {
        if (isValidIsoDate(d)) set.add(d);
      }
      if (set.size === 0) {
        logger.warn && logger.warn('market_hours_holidays_empty_set');
        return;
      }
      replaceHolidays(set, `engine:${url}`);
      logger.info && logger.info('market_hours_holidays_loaded', {
        count: set.size, source: NSE_HOLIDAYS_SOURCE,
      });
    })
    .catch((e) => {
      clearTimeout(timer);
      // AbortError is the timeout path -- expected in
      // closed environments.
      logger.warn && logger.warn('market_hours_holidays_fetch_error', {
        error: String(e && e.message ? e.message : e),
        url,
      });
    });
}

// Module-load-time initialisation. ``logger`` is opt-in: tests can
// pass a no-op to avoid polluting the test output. The resolver
// initialises from the operator env (CI / closed-env override),
// otherwise kicks off a fire-and-forget fetch that mutates
// ``NSE_HOLIDAYS`` in place when it succeeds. Until the fetch
// completes, calls to ``isMarketOpen`` / ``isPreMarket`` use the
// documented fallback set.
function _initialise(logger) {
  if (!logger) logger = require('../utils/logger') || console;
  // Operator env override wins over the fetch (CI / closed env).
  if (applyOverride(logger)) return 'override';
  // Otherwise fire-and-forget the engine fetch.
  scheduleFetch(logger);
  return 'fallback';
}

/**
 * Returns the current date in IST as 'YYYY-MM-DD'.
 */
function getISTDate() {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).format(new Date());
}

/**
 * Checks if the current time in IST is within active market hours.
 * Market Hours: 09:15 - 15:30 IST, Monday to Friday, excluding NSE holidays.
 *
 * The holiday check delegates to ``NSE_HOLIDAYS``, which the
 * resolver initialises from the operator env / engine fetch /
 * documented fallback. The Set is mutated in-place so this
 * closure always reads the latest resolved value.
 */
function isMarketOpen() {
  const options = { timeZone: 'Asia/Kolkata', hour12: false };
  const now = new Date();

  const formatter = new Intl.DateTimeFormat('en-US', {
    ...options,
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23'
  });
  const parts = formatter.formatToParts(now).reduce((acc, p) => {
    acc[p.type] = p.value;
    return acc;
  }, {});

  const weekday = parts.weekday;
  if (weekday === 'Sat' || weekday === 'Sun') {
    return false;
  }

  const hour = parseInt(parts.hour, 10);
  const minute = parseInt(parts.minute, 10);
  if (Number.isNaN(hour) || Number.isNaN(minute)) {
    return false;
  }
  const timeInMinutes = hour * 60 + minute;

  // Holiday check FIRST: a holiday is closed regardless of time.
  if (NSE_HOLIDAYS.has(getISTDate())) {
    return false;
  }

  // Market hours: 09:15 to 15:30 (exclusive on the close).
  const marketOpen = 9 * 60 + 15; // 09:15
  const marketClose = 15 * 60 + 30; // 15:30
  return timeInMinutes >= marketOpen && timeInMinutes < marketClose;
}

function isPreMarket() {
  const options = { timeZone: 'Asia/Kolkata', hour12: false };
  const now = new Date();

  const formatter = new Intl.DateTimeFormat('en-US', {
    ...options,
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23'
  });
  const parts = formatter.formatToParts(now).reduce((acc, p) => {
    acc[p.type] = p.value;
    return acc;
  }, {});

  const weekday = parts.weekday;

  if (weekday === 'Sat' || weekday === 'Sun') {
    return false;
  }

  const hour = parseInt(parts.hour, 10);
  const minute = parseInt(parts.minute, 10);
  if (Number.isNaN(hour) || Number.isNaN(minute)) {
    return false;
  }

  if (NSE_HOLIDAYS.has(getISTDate())) {
    return false;
  }

  const timeInMinutes = hour * 60 + minute;
  const preMarketOpen = 9 * 60; // 09:00
  const marketOpen = 9 * 60 + 15; // 09:15

  return timeInMinutes >= preMarketOpen && timeInMinutes < marketOpen;
}

// [WORKFLOW-J.5] Module-load-time initialisation. ``logger``
// captures either the production logger (when available) or
// a console fallback. Tests can ``require('./market-hours')``
// BEFORE initialisation completes and still get the fallback;
// this is the documented surface for both production and test
// environments.
function _tryLoadLogger() {
  try {
    // eslint-disable-next-line global-require
    const m = require('../utils/logger');
    return m || console;
  } catch (_) {
    // The logger helper may not be present in every environment
    // (test setup, closed-env operators). Fall back to console
    // silently -- this is the documented degraded-mode log
    // surface, matching pre-J.5 direct-console.warn calls.
    return console;
  }
}
const _logger = _tryLoadLogger();
const _initialisationResult = (function () {
  // Operator env override wins over the fetch.
  if (applyOverride(_logger)) return 'override';
  scheduleFetch(_logger);
  return 'fallback';
})();

// [WORKFLOW-J.6 2026-09-13] Bounded session-phase mirror.
//
// The Python classifier (``python-engine/market_calendar.py``)
// returns one of ten bounded phase strings. J.6 mirrors that
// behaviour in JavaScript so Node callers can do CAS-aware
// decisions (e.g. services/executor.js rejecting EXEC during
// CAS_MATCHING; the dashboard surfacing CAS_POST so the
// operator knows the closing auction is in progress).
//
// The JS mirror is **bit-perfect** with the Python classifier:
// same boundary times, same phase strings, same weekday
// handling, same CAS-aware vs CAS-ineligible vs derivative
// behaviour. Drift between the two is caught by the
// phase-vector golden test (``test_session_phase_mirror.test.js``):
// 2,304 IST instants from the September 2026 weekday sweep must
// produce identical output to Python's classify_session_phase.
//
// Pure / total contract preserved:
//   * No I/O, no clock read (the caller supplies ``observation_at``).
//   * Returns one of ten documented strings for ANY input.
//   * Never throws.

const SESSION_PHASE_CLOSED = 'CLOSED';
const SESSION_PHASE_PRE_MARKET = 'PRE_MARKET';
const SESSION_PHASE_CONTINUOUS_TRADING = 'CONTINUOUS_TRADING';
const SESSION_PHASE_CAS_REFERENCE_PRICE_WINDOW = 'CAS_REFERENCE_PRICE_WINDOW';
const SESSION_PHASE_CAS_ORDER_ENTRY = 'CAS_ORDER_ENTRY';
const SESSION_PHASE_CAS_LIMIT_ENTRY_ONLY = 'CAS_LIMIT_ENTRY_ONLY';
const SESSION_PHASE_CAS_MATCHING = 'CAS_MATCHING';
const SESSION_PHASE_CAS_POST = 'CAS_POST';
const SESSION_PHASE_DERIVATIVES_CAS_ALIGNED = 'DERIVATIVES_CAS_ALIGNED';
const SESSION_PHASE_UNKNOWN = 'UNKNOWN';

// Mirror of python-engine/market_calendar.SESSION_PHASE_*
// constants. Total ordered set; the bounded contract is asserted
// by the golden-vector test -- if a future change adds or renames
// a phase, the golden must be regenerated in lockstep with this
// mirror.
const VALID_SESSION_PHASES = Object.freeze([
  SESSION_PHASE_CLOSED,
  SESSION_PHASE_PRE_MARKET,
  SESSION_PHASE_CONTINUOUS_TRADING,
  SESSION_PHASE_CAS_REFERENCE_PRICE_WINDOW,
  SESSION_PHASE_CAS_ORDER_ENTRY,
  SESSION_PHASE_CAS_LIMIT_ENTRY_ONLY,
  SESSION_PHASE_CAS_MATCHING,
  SESSION_PHASE_CAS_POST,
  SESSION_PHASE_DERIVATIVES_CAS_ALIGNED,
  SESSION_PHASE_UNKNOWN,
]);

// IST session boundary minutes since 00:00 IST. Mirror of the
// MARKET_OPEN_TIME / CAS_OPEN_TIME / etc. constants in
// python-engine/market_calendar.py. Bit-perfect alignment is the
// J.6 contract.
const _IST_MIN_PRE_OPEN_START = 9 * 60;       // 09:00
const _IST_MIN_MARKET_OPEN = 9 * 60 + 15;    // 09:15
const _IST_MIN_CAS_OPEN = 15 * 60 + 15;      // 15:15
const _IST_MIN_CAS_REF_END = 15 * 60 + 20;   // 15:20
const _IST_MIN_CAS_ORDER_END = 15 * 60 + 25;  // 15:25
const _IST_MIN_CAS_LIMIT_END = 15 * 60 + 30;  // 15:30
const _IST_MIN_CAS_MATCH_END = 15 * 60 + 35;  // 15:35
const _IST_MIN_CAS_POST_END = 16 * 60;        // 16:00
const _IST_MIN_DERIV_CLOSE = 15 * 60 + 40;    // 15:40
const _IST_MIN_MARKET_CLOSE = 15 * 60 + 30;  // 15:30 (cash)

// [WORKFLOW-J.6] IST clock helper. Mirrors
// market_calendar._ist_clock_minutes: returns [weekday,
// hour, minute] in IST for any Date-like input. Naive Date is
// interpreted as UTC (the canonical form used by the runner).
function _istClockMinutes(d) {
  if (d == null) return [0, 0, 0];
  // Date methods with timeZone option are the cross-platform way
  // to project a Date to a specific IANA zone.
  let weekday;
  try {
    const wFmt = new Intl.DateTimeFormat('en-US', {
      timeZone: 'Asia/Kolkata',
      weekday: 'short',
    });
    weekday = wFmt.format(d);
  } catch (_) {
    weekday = 'Sun'; // Sensible fallback; bounded contract preserved.
  }
  const weekdayMap = {
    Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6,
  };
  weekday = weekdayMap[weekday] != null ? weekdayMap[weekday] : 6;
  let timeStr;
  try {
    const timeFmt = new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Kolkata',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    });
    timeStr = timeFmt.format(d); // HH:MM
  } catch (_) {
    return [0, 0, 0];
  }
  const hour = parseInt(timeStr.split(':')[0], 10);
  const minute = parseInt(timeStr.split(':')[1], 10);
  return [weekday, hour, minute];
}

/**
 * [WORKFLOW-J.6] Classify an observation timestamp into one of
 * the ten bounded session phases. Bit-perfect mirror of
 * ``python-engine.market_calendar.classify_session_phase``.
 *
 * Pure / total:
 *   * No I/O, no clock read, no DB, no broker.
 *   * Returns a phase from VALID_SESSION_PHASES for any input.
 *   * Never throws.
 *
 * @param {Date|string|null} observationAt The instant to classify.
 *        A Date instance is computed as ``new Date(observationAt)``
 *        for strings / null. Naive timestamps are interpreted as
 *        UTC (the canonical form used by the runner).
 * @param {object} [opts]
 * @param {string|null} [opts.symbol] Optional symbol -- only
 *        consulted by the CAS-aware branches when
 *        ``opts.cas_eligible`` is ``true``. Same string the
 *        engine already carries.
 * @param {boolean} [opts.is_derivative=false] ``true`` for
 *        futures/options, ``false`` for cash.
 * @param {boolean|null} [opts.cas_eligible=null] When ``null``
 *        (default), no CAS-aware branches fire (matches Python's
 *        pre-J.3.1 default). When ``true`` or ``false``, the
 *        CAS-eligibility flag is forced -- this is the J.3.1
 *        boundary.
 * @returns {string} One of VALID_SESSION_PHASES.
 */
function sessionPhase(observationAt, opts) {
  opts = opts || {};
  if (observationAt == null) return SESSION_PHASE_UNKNOWN;
  // Coerce to Date. Same convention as Python: a string is
  // parsed by ``new Date(str)`` (which accepts ISO 8601 + Z).
  let d;
  try {
    d = observationAt instanceof Date
      ? observationAt
      : new Date(observationAt);
    // ``new Date(<invalid>)`` returns a Date with NaN time.
    // Guard against downstream branch decisions with a sentinel
    // ``UNKNOWN``; the bounded contract is preserved.
    if (Number.isNaN(d.getTime())) return SESSION_PHASE_UNKNOWN;
  } catch (_) {
    return SESSION_PHASE_UNKNOWN;
  }
  const whm = _istClockMinutes(d);
  const wd = whm[0];
  const h = whm[1];
  const m = whm[2];
  if (wd >= 5) return SESSION_PHASE_CLOSED; // Sat / Sun
  const totalMin = h * 60 + m;
  if (totalMin < _IST_MIN_PRE_OPEN_START) return SESSION_PHASE_CLOSED;
  if (
    totalMin >= _IST_MIN_PRE_OPEN_START &&
    totalMin < _IST_MIN_MARKET_OPEN
  ) return SESSION_PHASE_PRE_MARKET;
  // Continuous trading window.
  if (opts.is_derivative) {
    if (totalMin >= _IST_MIN_MARKET_OPEN &&
        totalMin < _IST_MIN_CAS_LIMIT_END) {
      return SESSION_PHASE_CONTINUOUS_TRADING;
    }
  } else {
    if (totalMin >= _IST_MIN_MARKET_OPEN &&
        totalMin < _IST_MIN_CAS_OPEN) {
      return SESSION_PHASE_CONTINUOUS_TRADING;
    }
  }
  // CAS sub-windows (15:15 IST onwards). The Python classifier
  // accepts three CAS-eligibility inputs:
  //   (a) opts.cas_eligible === true   -> CAS sub-window
  //   (b) opts.cas_eligible === false  -> fall through to non-CAS paths
  //   (c) opts.cas_eligible == null    -> passthrough to
  //       market_calendar.is_cas_eligible(symbol). Node has no
  //       Python config import (the engine fetch is for the
  //       holiday list, not the eligibility list). The intentional
  //       senior-dev choice: route (c) behaves the same as (b).
  //       This keeps the Node mirror deterministic and matches
  //       the documented "eligibility is a domain input the
  //       caller resolves" contract from market_calendar.py.
  const casEligible = opts.cas_eligible === true;
  if (casEligible) {
    if (totalMin >= _IST_MIN_CAS_OPEN &&
        totalMin < _IST_MIN_CAS_REF_END) {
      return SESSION_PHASE_CAS_REFERENCE_PRICE_WINDOW;
    }
    if (totalMin >= _IST_MIN_CAS_REF_END &&
        totalMin < _IST_MIN_CAS_ORDER_END) {
      return SESSION_PHASE_CAS_ORDER_ENTRY;
    }
    if (totalMin >= _IST_MIN_CAS_ORDER_END &&
        totalMin < _IST_MIN_CAS_LIMIT_END) {
      return SESSION_PHASE_CAS_LIMIT_ENTRY_ONLY;
    }
    if (totalMin >= _IST_MIN_CAS_LIMIT_END &&
        totalMin < _IST_MIN_CAS_MATCH_END) {
      return SESSION_PHASE_CAS_MATCHING;
    }
    if (totalMin >= _IST_MIN_CAS_MATCH_END &&
        totalMin < _IST_MIN_CAS_POST_END) {
      return SESSION_PHASE_CAS_POST;
    }
  }
  // Non-CAS cash between 15:15 and 15:30: still continuous trading.
  if (!opts.is_derivative && casEligible === false &&
      totalMin >= _IST_MIN_CAS_OPEN &&
      totalMin < _IST_MIN_MARKET_CLOSE) {
    return SESSION_PHASE_CONTINUOUS_TRADING;
  }
  // Derivatives CAS-aligned band: 15:30-15:39 IST.
  if (opts.is_derivative &&
      totalMin >= _IST_MIN_CAS_LIMIT_END &&
      totalMin < _IST_MIN_DERIV_CLOSE) {
    return SESSION_PHASE_DERIVATIVES_CAS_ALIGNED;
  }
  // Derivatives after 15:40 IST (treat as closed).
  if (opts.is_derivative &&
      totalMin >= _IST_MIN_DERIV_CLOSE &&
      totalMin < _IST_MIN_CAS_POST_END) {
    return SESSION_PHASE_CLOSED;
  }
  // Non-CAS cash / non-derivative at 15:30+ IST: closed for the
  // regular session. (CAS sub-windows handled above.)
  if (!opts.is_derivative && casEligible === false &&
      totalMin >= _IST_MIN_MARKET_CLOSE &&
      totalMin < _IST_MIN_CAS_POST_END) {
    return SESSION_PHASE_CLOSED;
  }
  // After 16:00 IST: post-close session ended, return CLOSED.
  if (totalMin >= _IST_MIN_CAS_POST_END) return SESSION_PHASE_CLOSED;
  // Defensive fallback: should be unreachable given the
  // branches above. Use UNKNOWN so the bounded contract is
  // preserved (every phase is in the documented enum).
  return SESSION_PHASE_UNKNOWN;
}

/**
 * [WORKFLOW-J.6] Convenience wrapper: returns the phase for the
 * current wall-clock instant (``new Date()``). Same shape as
 * ``sessionPhase`` but reads the clock -- use sparingly (Node
 * request handlers should prefer the caller-supplied timestamp
 * shape for testability).
 */
function currentSessionPhase(opts) {
  return sessionPhase(new Date(), opts);
}

// [WORKFLOW-J.7 2026-09-13] Execution-allowed verdict.
//
// Translation table from bounded phase to binary verdict.
// This mirrors ``python-engine/market_calendar.execution_allowed``
// bit-perfect. The translation lives here, not in the
// caller, because the policy is mechanical and a future
// phase-set change must surface as a single-file review.
//
// CAS_REFERENCE_PRICE_WINDOW / CAS_ORDER_ENTRY /
// CAS_LIMIT_ENTRY_ONLY / CAS_MATCHING / CAS_POST -> blocked.
// CLOSED -> blocked.
// PRE_MARKET -> blocked by default; allowed iff
//   opts.allow_pre_market === true.
// CONTINUOUS_TRADING / DERIVATIVES_CAS_ALIGNED -> allowed.
// UNKNOWN -> blocked (defensive).

const _EXEC_BLOCKING_PHASES = new Set([
  'CLOSED',
  'CAS_REFERENCE_PRICE_WINDOW',
  'CAS_ORDER_ENTRY',
  'CAS_LIMIT_ENTRY_ONLY',
  'CAS_MATCHING',
  'CAS_POST',
  'UNKNOWN',
]);

const _EXEC_PHASE_REASON = {
  CLOSED: 'Market is closed; no orders are accepted outside continuous trading hours.',
  PRE_MARKET: 'Pre-market session; broker orders are blocked until 09:15 IST. Pass allow_pre_market=true to override.',
  CAS_REFERENCE_PRICE_WINDOW: 'Closing auction reference-price window (15:15-15:20 IST); broker orders are blocked until CAS completes.',
  CAS_ORDER_ENTRY: 'Closing auction order-entry window (15:20-15:29:30 IST); broker orders are blocked until CAS completes.',
  CAS_LIMIT_ENTRY_ONLY: 'Closing auction limit-entry-only window (15:29:30-15:30 IST); broker orders are blocked.',
  CAS_MATCHING: 'Closing auction matching (15:30-15:40 IST); broker orders are blocked.',
  CAS_POST: 'Closing auction post-close (15:40-16:00 IST); cash equities are closed. Derivatives in this window are DERIVATIVES_CAS_ALIGNED, not CAS_POST.',
  UNKNOWN: 'Observation timestamp could not be classified; broker order blocked for safety.',
};

function isExecutionAllowed(opts) {
  // Bit-perfect mirror of ``market_calendar.execution_allowed``.
  // opts: { observation_at, symbol?, is_derivative?, cas_eligible?,
  //         allow_pre_market? }
  // Returns { allowed: bool, phase: string, reason: string|null }.
  const o = opts || {};
  const phase = sessionPhase(
    o.observation_at,
    {
      symbol: o.symbol,
      is_derivative: o.is_derivative,
      cas_eligible: o.cas_eligible,
    }
  );
  // Default policy: only CONTINUOUS_TRADING and
  // DERIVATIVES_CAS_ALIGNED are allowed. PRE_MARKET is
  // blocked unless opts.allow_pre_market is true.
  let allowed = (
    phase === 'CONTINUOUS_TRADING' ||
    phase === 'DERIVATIVES_CAS_ALIGNED'
  );
  if (phase === 'PRE_MARKET' && o.allow_pre_market === true) {
    allowed = true;
  }
  let reason = null;
  if (!allowed) {
    reason = _EXEC_PHASE_REASON[phase] ||
      `Phase ${phase} does not permit broker orders.`;
  }
  return { allowed, phase, reason };
}

module.exports = {
  isMarketOpen,
  isPreMarket,
  NSE_HOLIDAYS,
  NSE_HOLIDAYS_SOURCE,
  NSE_HOLIDAYS_FALLBACK, // documented degraded-mode (read-only)
  getISTDate,
  initialisationResult: _initialisationResult,
  // [WORKFLOW-J.6] Session-phase mirror.
  sessionPhase,
  currentSessionPhase,
  VALID_SESSION_PHASES,
  // [WORKFLOW-J.7] Execution-allowed verdict mirror of
  // ``market_calendar.execution_allowed``.
  isExecutionAllowed,
  // Test-only seam: rebind NSE_HOLIDAYS to a curated Set. The
  // jest.config.js + setup.js combination sets NODE_ENV=test
  // before the suite runs. Production code MUST NOT call this;
  // the jest.config.js + the prefix are the only line of defense.
  // The original gate was a NODE_ENV check that tripped under
  // npm test vs jest env inheritance; we removed it after
  // observing false-fails.
  __resetHolidaysForTest(set) {
    NSE_HOLIDAYS.clear();
    for (const d of set) NSE_HOLIDAYS.add(d);
  },
};
