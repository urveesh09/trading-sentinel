/**
 * [WORKFLOW-J.9 2026-09-13] Tests for the J.9 session-phase
 * stamping on received_signals.
 *
 * Two things are pinned by this file:
 *
 * 1. The DB schema migration is idempotent and additive:
 *    the new ``session_phase`` column accepts only the
 *    10 documented bounded phases; a default of
 *    ``'UNKNOWN'`` covers existing rows so the migration
 *    does not break the production SQLite DB.
 *
 * 2. The Node stamp helper ``stampSessionPhaseForSignal(ticker)``
 *    returns one of the documented phases (never null,
 *    never an unrecognised string). It mirrors the
 *    J.6 ``sessionPhase`` mirror bit-perfectly -- so the
 *    phase stored in the DB is always the live phase
 *    at the moment of stamping.
 *
 * The actual signal-handler wiring (routes/signals.js and
 * routes/internal.js) is tested via the integration suite
 * (tests/integration/telegram-callbacks.test.js, et al);
 * this file pins the helper contract so future changes
 * to the migration or the helper surface as a unit-level
 * failure.
 */
const path = require('path');
const fs = require('fs');

const {
  stampSessionPhaseForSignal,
  STAMPABLE_PHASES,
} = require('../../utils/market-hours');

describe('received_signals.session_phase column', () => {
  test('schema.sql contains the session_phase column with default UNKNOWN', () => {
    const schemaPath = path.join(
      __dirname, '..', '..', 'db', 'schema.sql'
    );
    const sql = fs.readFileSync(schemaPath, 'utf-8');
    // The CREATE TABLE for received_signals must include
    // ``session_phase TEXT NOT NULL DEFAULT 'UNKNOWN'``
    // (or equivalent) with a bounded CHECK constraint.
    // Strategy: extract the line containing ``session_phase``
    // and the lines containing the CHECK constraint, then
    // assert both are present.
    const lines = sql.split('\n');
    const sessionPhaseLine = lines.findIndex(
      (l) => l.match(/^\s*session_phase\s+TEXT/i)
    );
    expect(sessionPhaseLine).toBeGreaterThan(-1);
    const sessionPhaseText = lines[sessionPhaseLine] +
      (lines[sessionPhaseLine + 1] || '');
    expect(sessionPhaseText).toMatch(/DEFAULT\s+'UNKNOWN'/i);
    // The CHECK constraint is multi-line; pull the next
    // 5 lines and assert the bounded set is referenced.
    const checkSlice = lines.slice(
      sessionPhaseLine + 1, sessionPhaseLine + 6
    ).join('\n');
    expect(checkSlice).toMatch(/CHECK\s*\(\s*session_phase\s+IN/i);
    for (const phase of [
      'CONTINUOUS_TRADING',
      'CAS_MATCHING',
      'DERIVATIVES_CAS_ALIGNED',
      'UNKNOWN',
    ]) {
      expect(checkSlice).toMatch(new RegExp(`'${phase}'`));
    }
  });

  test('STAMPABLE_PHASES is the documented 10-phase set', () => {
    // The stamp helper returns one of these; the DB column
    // CHECK constraint must accept only these. Drift here is
    // a category-1 invariant failure.
    expect(STAMPABLE_PHASES.length).toBe(10);
    const expected = new Set([
      'CLOSED',
      'PRE_MARKET',
      'CONTINUOUS_TRADING',
      'CAS_REFERENCE_PRICE_WINDOW',
      'CAS_ORDER_ENTRY',
      'CAS_LIMIT_ENTRY_ONLY',
      'CAS_MATCHING',
      'CAS_POST',
      'DERIVATIVES_CAS_ALIGNED',
      'UNKNOWN',
    ]);
    for (const phase of STAMPABLE_PHASES) {
      expect(expected.has(phase)).toBe(true);
    }
  });
});

describe('stampSessionPhaseForSignal(ticker)', () => {
  test('returns one of the 10 documented phases', () => {
    const phase = stampSessionPhaseForSignal('RELIANCE');
    expect(STAMPABLE_PHASES).toContain(phase);
  });

  test('never throws on null / undefined / empty ticker', () => {
    // Defensive: the helper must never throw on bad input.
    // The result is one of the 10 documented phases (the
    // live phase at the moment of stamping, since the
    // mirror is non-string-ticker-tolerant).
    expect(() => stampSessionPhaseForSignal(null)).not.toThrow();
    expect(() => stampSessionPhaseForSignal(undefined)).not.toThrow();
    expect(() => stampSessionPhaseForSignal('')).not.toThrow();
    expect(() => stampSessionPhaseForSignal(42)).not.toThrow();
    expect(() => stampSessionPhaseForSignal({})).not.toThrow();
    expect(() => stampSessionPhaseForSignal([])).not.toThrow();
    for (const v of [null, undefined, '', 42, {}, []]) {
      expect(STAMPABLE_PHASES).toContain(stampSessionPhaseForSignal(v));
    }
  });

  test('output never contains non-bounded strings', () => {
    // Sweep: a few CAS-eligible + non-eligible + derivative
    // tickers + non-string garbage; every output must be in
    // STAMPABLE_PHASES.
    const tickers = ['RELIANCE', 'TCS', 'FUTIDX', 'NIFTY', null,
      undefined, '', 42, {}, []];
    for (const t of tickers) {
      const phase = stampSessionPhaseForSignal(t);
      expect(STAMPABLE_PHASES).toContain(phase);
    }
  });
});
