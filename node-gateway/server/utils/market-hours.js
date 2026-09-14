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

module.exports = {
  isMarketOpen,
  isPreMarket,
  NSE_HOLIDAYS,
  NSE_HOLIDAYS_SOURCE,
  NSE_HOLIDAYS_FALLBACK, // documented degraded-mode (read-only)
  getISTDate,
  initialisationResult: _initialisationResult,
  // Test-only seam: rebind NSE_HOLIDAYS to a curated Set. The
  // jest.config.js + setup.js combination sets NODE_ENV=test
  // before the suite runs. Production code MUST NOT call this;
  // the gate remains a defensive check for live deployment
  // shells that happen to import utils/market-hours.js.
  __resetHolidaysForTest(set) {
    NSE_HOLIDAYS.clear();
    for (const d of set) NSE_HOLIDAYS.add(d);
  },
};
