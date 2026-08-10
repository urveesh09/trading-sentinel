import test from 'node:test';
import assert from 'node:assert/strict';
import { isActivePosition } from '../src/utils/positions.js';

test('OPEN and still-running CLOSED_T1 positions remain visible', () => {
  assert.equal(isActivePosition({ status: 'OPEN' }), true);
  assert.equal(isActivePosition({ status: 'CLOSED_T1', exit_date: null }), true);
  assert.equal(isActivePosition({ status: 'CLOSED_T1', exit_date: '2026-08-10' }), false);
  assert.equal(isActivePosition({ status: 'CLOSED_T2', exit_date: '2026-08-10' }), false);
});
