/**
 * [WORKFLOW-J.7 2026-09-13] Tests for isExecutionAllowed.
 *
 * The J.7 contract:
 *   - isExecutionAllowed(opts) returns {allowed, phase, reason}
 *   - allowed = true ONLY when the bounded phase is
 *     CONTINUOUS_TRADING, or DERIVATIVES_CAS_ALIGNED (when
 *     opts.is_derivative === true), or PRE_MARKET (when the
 *     operator opts in via opts.allow_pre_market === true).
 *   - Every other phase returns allowed = false with a phase-
 *     specific reason string.
 *   - The function is pure / total: never throws, never reads
 *     the clock (caller supplies observation_at).
 *
 * The mirror must be bit-perfect with the Python
 * ``execution_allowed`` helper (added in J.7 to
 * ``python-engine/market_calendar.py``).
 *
 * These tests assert:
 *   1. Each documented phase produces the correct verdict.
 *   2. The CAS sub-windows (CAS_REFERENCE_PRICE_WINDOW,
 *      CAS_ORDER_ENTRY, CAS_LIMIT_ENTRY_ONLY, CAS_MATCHING,
 *      CAS_POST) all block execution.
 *   3. CLOSED blocks. PRE_MARKET blocks by default; allows
 *      when opts.allow_pre_market is true.
 *   4. Derivatives get DERIVATIVES_CAS_ALIGNED during the
 *      cash CAS window (15:30 - 15:35 IST) — that's the
 *      documented continuous-trading-equivalent for F&O.
 *   5. The verdict is consistent with the golden sessionPhase
 *      outputs (same input -> same phase).
 */
const { isExecutionAllowed } = require('../../utils/market-hours');

// IST helper that returns a UTC Date for a given IST instant.
function ist(y, mo, d, h, mi, s = 0) {
  // IST = UTC + 5h30m. To construct a UTC Date that, when the
  // JS mirror's Intl formatter reads it back to IST, yields the
  // requested IST instant -- construct the IST Date, then
  // subtract 5h30m to land on UTC. The mirror's
  // _istClockMinutes treats naive UTC dates as UTC (which is
  // Python's classify_session_phase contract for naive
  // timestamps); for 9:10 IST = 3:40 UTC on the same day.
  const istMillis = Date.UTC(y, mo - 1, d, h, mi, s);
  const utcMillis = istMillis - (5 * 60 + 30) * 60 * 1000;
  return new Date(utcMillis);
}

// Pin a non-holiday Monday (Sep 7 2026 is a Monday, no holiday).
const MONDAY_YEAR = 2026;
const MONDAY_MONTH = 9;
const MONDAY_DAY = 7;

describe('isExecutionAllowed()', () => {
  describe('CLOSE / PRE_MARKET (cash equities)', () => {
    test('CLOSED (weekend Sunday): blocked', () => {
      // Sep 6 2026 is Sunday.
      const result = isExecutionAllowed({
        observation_at: ist(2026, 9, 6, 12, 0),
      });
      expect(result.allowed).toBe(false);
      expect(result.phase).toBe('CLOSED');
      expect(result.reason).toMatch(/closed|weekend/i);
    });

    test('CLOSED (after 15:30 cash close): blocked', () => {
      const result = isExecutionAllowed({
        observation_at: ist(MONDAY_YEAR, MONDAY_MONTH, MONDAY_DAY, 16, 0),
      });
      expect(result.allowed).toBe(false);
      expect(result.phase).toBe('CLOSED');
    });

    test('PRE_MARKET (9:00 - 9:14 IST): blocked by default', () => {
      const result = isExecutionAllowed({
        observation_at: ist(MONDAY_YEAR, MONDAY_MONTH, MONDAY_DAY, 9, 10),
      });
      expect(result.allowed).toBe(false);
      expect(result.phase).toBe('PRE_MARKET');
      expect(result.reason).toMatch(/pre.market/i);
    });

    test('PRE_MARKET: allowed when opts.allow_pre_market is true', () => {
      const result = isExecutionAllowed({
        observation_at: ist(MONDAY_YEAR, MONDAY_MONTH, MONDAY_DAY, 9, 10),
        allow_pre_market: true,
      });
      expect(result.allowed).toBe(true);
      expect(result.phase).toBe('PRE_MARKET');
    });
  });

  describe('CONTINUOUS_TRADING (9:15 - 15:14:59 IST): allowed', () => {
    test('9:15 IST open: allowed', () => {
      const result = isExecutionAllowed({
        observation_at: ist(MONDAY_YEAR, MONDAY_MONTH, MONDAY_DAY, 9, 15),
      });
      expect(result.allowed).toBe(true);
      expect(result.phase).toBe('CONTINUOUS_TRADING');
      expect(result.reason).toBeNull();
    });

    test('mid-day 12:00: allowed', () => {
      const result = isExecutionAllowed({
        observation_at: ist(MONDAY_YEAR, MONDAY_MONTH, MONDAY_DAY, 12, 0),
      });
      expect(result.allowed).toBe(true);
      expect(result.phase).toBe('CONTINUOUS_TRADING');
    });

    test('15:14:59 IST (last continuous-trading second): allowed', () => {
      const result = isExecutionAllowed({
        observation_at: ist(MONDAY_YEAR, MONDAY_MONTH, MONDAY_DAY, 15, 14, 59),
      });
      expect(result.allowed).toBe(true);
      expect(result.phase).toBe('CONTINUOUS_TRADING');
    });
  });

  describe('CAS sub-windows (cash equities): all blocked', () => {
    test('CAS_REFERENCE_PRICE_WINDOW (15:15 IST): blocked', () => {
      // CAS sub-windows only fire when the symbol is CAS-eligible.
      // Pass cas_eligible: true to mirror how a production caller
      // would invoke the mirror (the J.2.1 list resolves to this
      // boolean; production callers wire it explicitly).
      const result = isExecutionAllowed({
        observation_at: ist(MONDAY_YEAR, MONDAY_MONTH, MONDAY_DAY, 15, 15),
        symbol: 'RELIANCE',
        cas_eligible: true,
      });
      expect(result.allowed).toBe(false);
      expect(result.phase).toBe('CAS_REFERENCE_PRICE_WINDOW');
      expect(result.reason).toMatch(/CAS|reference.*price|auction/i);
    });

    test('CAS_ORDER_ENTRY (15:20 - 15:25 IST): blocked', () => {
      // CAS_ORDER_ENTRY window per the Python classifier
      // (CAS_ORDER_ENTRY_END = 15:25 IST). 15:25 IST itself is
      // the boundary into CAS_LIMIT_ENTRY_ONLY.
      const result = isExecutionAllowed({
        observation_at: ist(MONDAY_YEAR, MONDAY_MONTH, MONDAY_DAY, 15, 20),
        symbol: 'RELIANCE',
        cas_eligible: true,
      });
      expect(result.allowed).toBe(false);
      expect(result.phase).toBe('CAS_ORDER_ENTRY');
      expect(result.reason).toMatch(/CAS|order.*entry|auction/i);
    });

    test('CAS_LIMIT_ENTRY_ONLY (15:25 - 15:30 IST): blocked', () => {
      // CAS_LIMIT_ENTRY_ONLY_END = 15:30 IST. 15:29:45 is in
      // the CAS_LIMIT_ENTRY_ONLY window.
      const result = isExecutionAllowed({
        observation_at: ist(MONDAY_YEAR, MONDAY_MONTH, MONDAY_DAY, 15, 29, 45),
        symbol: 'RELIANCE',
        cas_eligible: true,
      });
      expect(result.allowed).toBe(false);
      expect(result.phase).toBe('CAS_LIMIT_ENTRY_ONLY');
    });

    test('CAS_MATCHING (15:30 - 15:35 IST): blocked', () => {
      // CAS_MATCHING_END = 15:35 IST. 15:32 is in the
      // CAS_MATCHING window.
      const result = isExecutionAllowed({
        observation_at: ist(MONDAY_YEAR, MONDAY_MONTH, MONDAY_DAY, 15, 32),
        symbol: 'RELIANCE',
        cas_eligible: true,
      });
      expect(result.allowed).toBe(false);
      expect(result.phase).toBe('CAS_MATCHING');
    });

    test('CAS_POST (15:35 - 16:00 IST): blocked (cash-only window)', () => {
      // CAS_POST fires for CAS-eligible cash equities at 15:35+
      // (CAS_MATCHING_END = 15:35, CAS_POST_CLOSE_END = 16:00).
      const result = isExecutionAllowed({
        observation_at: ist(MONDAY_YEAR, MONDAY_MONTH, MONDAY_DAY, 15, 50),
        symbol: 'RELIANCE',
        cas_eligible: true,
      });
      expect(result.allowed).toBe(false);
      expect(result.phase).toBe('CAS_POST');
    });
  });

  describe('DERIVATIVES_CAS_ALIGNED: allowed for derivatives', () => {
    test('15:32 IST with is_derivative=true: allowed (cash is in CAS_MATCHING)', () => {
      // During CAS_MATCHING for cash (15:30 - 15:35), derivatives
      // are in DERIVATIVES_CAS_ALIGNED — that is the bounded
      // continuous-trading-equivalent for F&O. isExecutionAllowed
      // must allow derivatives to execute here.
      const result = isExecutionAllowed({
        observation_at: ist(MONDAY_YEAR, MONDAY_MONTH, MONDAY_DAY, 15, 32),
        is_derivative: true,
      });
      expect(result.allowed).toBe(true);
      expect(result.phase).toBe('DERIVATIVES_CAS_ALIGNED');
    });

    test('15:39 IST with is_derivative=true: allowed', () => {
      // 15:39 IST is still within DERIVATIVES_CAS_ALIGNED
      // (15:30 - 15:40 IST). allowed = true here.
      const result = isExecutionAllowed({
        observation_at: ist(MONDAY_YEAR, MONDAY_MONTH, MONDAY_DAY, 15, 39),
        is_derivative: true,
      });
      expect(result.allowed).toBe(true);
      expect(result.phase).toBe('DERIVATIVES_CAS_ALIGNED');
    });

    test('15:50 IST with is_derivative=true: blocked with CLOSED', () => {
      // After 15:40 IST, derivatives are CLOSED (the
      // DERIVATIVES_CAS_ALIGNED window closes at 15:40).
      const result = isExecutionAllowed({
        observation_at: ist(MONDAY_YEAR, MONDAY_MONTH, MONDAY_DAY, 15, 50),
        is_derivative: true,
      });
      expect(result.allowed).toBe(false);
      expect(result.phase).toBe('CLOSED');
    });

    test('15:50 IST cash-only (non-CAS-eligible): blocked with CLOSED', () => {
      // The same instant, cash-only WITHOUT cas_eligible: the
      // session is CLOSED (regular cash closes at 15:30 IST for
      // non-CAS-eligible symbols). CAS_POST only fires for
      // CAS-eligible cash equities.
      const result = isExecutionAllowed({
        observation_at: ist(MONDAY_YEAR, MONDAY_MONTH, MONDAY_DAY, 15, 50),
      });
      expect(result.allowed).toBe(false);
      expect(result.phase).toBe('CLOSED');
    });
  });

  describe('Purity / total contract', () => {
    test('NaN input -> blocked with UNKNOWN phase', () => {
      const result = isExecutionAllowed({
        observation_at: 'not-a-date',
      });
      expect(result.allowed).toBe(false);
      expect(result.phase).toBe('UNKNOWN');
    });

    test('null observation_at -> blocked with UNKNOWN phase', () => {
      const result = isExecutionAllowed({ observation_at: null });
      expect(result.allowed).toBe(false);
      expect(result.phase).toBe('UNKNOWN');
    });

    test('verdict shape is always {allowed, phase, reason}', () => {
      const result = isExecutionAllowed({
        observation_at: ist(MONDAY_YEAR, MONDAY_MONTH, MONDAY_DAY, 10, 0),
      });
      // reason is either null (when allowed) or a string
      // (when blocked). Assert by property shape rather than
      // expect.any(String) which rejects null.
      expect(result).toHaveProperty('allowed');
      expect(result).toHaveProperty('phase');
      expect(result).toHaveProperty('reason');
      expect(typeof result.allowed).toBe('boolean');
      expect(typeof result.phase).toBe('string');
      expect(
        result.reason === null || typeof result.reason === 'string'
      ).toBe(true);
    });
  });

  describe('Golden vector parity vs Python', () => {
    // The Python helper ``market_calendar.execution_allowed``
    // produces identical verdicts. This test loads the
    // golden vectors and asserts no mismatches.
    let golden;
    beforeAll(() => {
      const fs = require('fs');
      const path = require('path');
      const goldenPath = path.join(
        __dirname, '..', 'fixtures', 'execution_allowed_golden.json'
      );
      if (!fs.existsSync(goldenPath)) {
        throw new Error(
          `golden vector file missing: ${goldenPath}. Run ` +
          '`python tests/fixtures/regenerate_execution_allowed_golden.py` ' +
          'to recreate it.'
        );
      }
      golden = JSON.parse(fs.readFileSync(goldenPath, 'utf-8'));
    });

    test('mirror is bit-perfect with Python execution_allowed', () => {
      let mismatches = 0;
      let firstMismatch = null;
      for (const v of golden.vectors) {
        // The golden vector's ``cas`` field maps to the
        // mirror's ``cas_eligible`` kwarg; the mirror's
        // sessionPhase() honours ``cas_eligible`` (not a
        // separate flag). Without this mapping the Node
        // mirror's sessionPhase() would route the call
        // through the ``cas_eligible == null`` branch which
        // defaults to ``false`` (senior-dev rule from
        // market_calendar.py).
        const opts = {
          observation_at: new Date(v.ist_utc),
        };
        if (Object.prototype.hasOwnProperty.call(v, 'deriv')) {
          opts.is_derivative = v.deriv;
        }
        if (Object.prototype.hasOwnProperty.call(v, 'cas')) {
          opts.cas_eligible = v.cas;
        }
        if (Object.prototype.hasOwnProperty.call(v, 'allow_pre_market')) {
          opts.allow_pre_market = v.allow_pre_market;
        }
        const got = isExecutionAllowed(opts);
        if (
          got.allowed !== v.expected.allowed ||
          got.phase !== v.expected.phase
        ) {
          mismatches += 1;
          if (firstMismatch == null) {
            firstMismatch = { vector: v, got };
          }
        }
      }
      expect({ mismatches, firstMismatch }).toEqual({
        mismatches: 0,
        firstMismatch: null,
      });
    });
  });
});
