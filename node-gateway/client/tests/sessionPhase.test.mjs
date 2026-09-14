// [WORKFLOW-J.8 2026-09-13] Tests for the dashboard session-phase
// utility.
//
// The utility exports pure functions consumed by SessionPhaseBadge
// and SessionPhaseCard. These tests pin the contract so future
// changes to the bounded phase set surface as a single-file review
// here + in market_calendar.py + in market-hours.js (Node side).
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  VALID_SESSION_PHASES,
  PHASE_DISPLAY_LABEL,
  PHASE_COLOR_CLASS,
  coercePhase,
  isExecutionBlockedByPhase,
  describePhase,
} from '../src/utils/sessionPhase.js';

// Every documented phase produces a label and a color class.
// A missing label / color means the bounded-phase set drifted
// from the visualisation -- a future developer must add a
// label before shipping a new phase.
test('every bounded phase has a label and a color class', () => {
  for (const phase of VALID_SESSION_PHASES) {
    assert.ok(
      typeof PHASE_DISPLAY_LABEL[phase] === 'string',
      `missing label for phase ${phase}`
    );
    assert.ok(
      PHASE_DISPLAY_LABEL[phase].length > 0,
      `empty label for phase ${phase}`
    );
    assert.ok(
      typeof PHASE_COLOR_CLASS[phase] === 'string',
      `missing color class for phase ${phase}`
    );
    assert.ok(
      PHASE_COLOR_CLASS[phase].length > 0,
      `empty color class for phase ${phase}`
    );
  }
});

// coercePhase never throws -- the UI contract is "always show a
// coloured phase label". null / undefined / arbitrary strings all
// fall back to UNKNOWN.
test('coercePhase handles null and undefined inputs', () => {
  assert.equal(coercePhase(null), 'UNKNOWN');
  assert.equal(coercePhase(undefined), 'UNKNOWN');
});

test('coercePhase handles non-string inputs', () => {
  assert.equal(coercePhase(42), 'UNKNOWN');
  assert.equal(coercePhase({}), 'UNKNOWN');
  assert.equal(coercePhase([]), 'UNKNOWN');
  assert.equal(coercePhase(true), 'UNKNOWN');
});

test('coercePhase passes through documented phases', () => {
  for (const phase of VALID_SESSION_PHASES) {
    assert.equal(coercePhase(phase), phase);
  }
});

test('coercePhase rejects unrecognised strings', () => {
  assert.equal(coercePhase('CAS_NOPE'), 'UNKNOWN');
  assert.equal(coercePhase('continuous_trading'), 'UNKNOWN'); // case-sensitive
  assert.equal(coercePhase(''), 'UNKNOWN');
});

// isExecutionBlockedByPhase mirrors the J.7 server-side gate
// (Node isExecutionAllowed). Allowed phases: CONTINUOUS_TRADING,
// DERIVATIVES_CAS_ALIGNED. Blocked: every other phase.
test('execution blocked for CLOSED, PRE_MARKET, all CAS_* sub-windows, UNKNOWN', () => {
  for (const phase of [
    'CLOSED',
    'PRE_MARKET',
    'CAS_REFERENCE_PRICE_WINDOW',
    'CAS_ORDER_ENTRY',
    'CAS_LIMIT_ENTRY_ONLY',
    'CAS_MATCHING',
    'CAS_POST',
    'UNKNOWN',
  ]) {
    assert.equal(
      isExecutionBlockedByPhase(phase),
      true,
      `expected ${phase} to block execution`
    );
  }
});

test('execution NOT blocked for CONTINUOUS_TRADING and DERIVATIVES_CAS_ALIGNED', () => {
  for (const phase of ['CONTINUOUS_TRADING', 'DERIVATIVES_CAS_ALIGNED']) {
    assert.equal(
      isExecutionBlockedByPhase(phase),
      false,
      `expected ${phase} to allow execution`
    );
  }
});

test('isExecutionBlockedByPhase never throws on bad input', () => {
  assert.equal(isExecutionBlockedByPhase(null), true);
  assert.equal(isExecutionBlockedByPhase(undefined), true);
  assert.equal(isExecutionBlockedByPhase('UNKNOWN_PHASE'), true);
  assert.equal(isExecutionBlockedByPhase(42), true);
});

// describePhase bundles the four fields components need.
// The bundle must always include a string phase (never null).
test('describePhase returns a complete bundle', () => {
  const result = describePhase('CONTINUOUS_TRADING');
  assert.equal(result.phase, 'CONTINUOUS_TRADING');
  assert.equal(typeof result.label, 'string');
  assert.ok(result.label.length > 0);
  assert.equal(typeof result.colorClass, 'string');
  assert.ok(result.colorClass.length > 0);
  assert.equal(result.executionBlocked, false);
});

test('describePhase handles null by falling back to UNKNOWN', () => {
  const result = describePhase(null);
  assert.equal(result.phase, 'UNKNOWN');
  assert.equal(result.executionBlocked, true);
});

test('describePhase falls back to UNKNOWN for arbitrary strings', () => {
  const result = describePhase('not-a-phase');
  assert.equal(result.phase, 'UNKNOWN');
  assert.equal(result.label, 'Unknown');
  assert.equal(result.executionBlocked, true);
});

// CAS sub-windows must be visually distinct from continuous trading
// (yellow vs green). The colour class is what the operator sees at
// a glance.
test('CAS sub-windows use a yellow colour class', () => {
  for (const phase of [
    'CAS_REFERENCE_PRICE_WINDOW',
    'CAS_ORDER_ENTRY',
    'CAS_LIMIT_ENTRY_ONLY',
    'CAS_MATCHING',
    'CAS_POST',
  ]) {
    const cls = PHASE_COLOR_CLASS[phase];
    assert.match(
      cls,
      /yellow/,
      `expected ${phase} colour class to contain yellow, got: ${cls}`
    );
  }
});

test('CONTINUOUS_TRADING and DERIVATIVES_CAS_ALIGNED use a green colour class', () => {
  for (const phase of ['CONTINUOUS_TRADING', 'DERIVATIVES_CAS_ALIGNED']) {
    const cls = PHASE_COLOR_CLASS[phase];
    assert.match(
      cls,
      /green/,
      `expected ${phase} colour class to contain green, got: ${cls}`
    );
  }
});

test('CLOSED and UNKNOWN use a red colour class', () => {
  for (const phase of ['CLOSED', 'UNKNOWN']) {
    const cls = PHASE_COLOR_CLASS[phase];
    assert.match(
      cls,
      /red/,
      `expected ${phase} colour class to contain red, got: ${cls}`
    );
  }
});

// The Node isExecutionAllowed contract uses the same blocking
// set. The Phase2 sync is: when this list changes, mirror the
// change in market-hours.js (_EXEC_BLOCKING_PHASES) and in
// market_calendar.py (_PHASE_EXECUTION_ALLOWED).
test('BLOCKING_PHASES count matches the documented J.7 translation table', () => {
  // 8 blocking phases: CLOSED, PRE_MARKET, CAS_REFERENCE_PRICE_WINDOW,
  // CAS_ORDER_ENTRY, CAS_LIMIT_ENTRY_ONLY, CAS_MATCHING, CAS_POST,
  // UNKNOWN. 2 allowed: CONTINUOUS_TRADING, DERIVATIVES_CAS_ALIGNED.
  // Total = 10 documented phases.
  assert.equal(VALID_SESSION_PHASES.length, 10);
  let blockedCount = 0;
  for (const phase of VALID_SESSION_PHASES) {
    if (isExecutionBlockedByPhase(phase)) blockedCount += 1;
  }
  assert.equal(blockedCount, 8);
});
