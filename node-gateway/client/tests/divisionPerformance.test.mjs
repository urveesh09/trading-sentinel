import test from 'node:test';
import assert from 'node:assert/strict';
import {
  INSUFFICIENT_DATA,
  buildDivisionViewModel,
  formatMoney,
  formatNumber,
  hasReconciliationMismatch,
} from '../src/utils/divisionPerformance.js';

test('view model keeps live and paper divisions strictly separated', () => {
  const model = buildDivisionViewModel({
    totals: { live: { equity: 1200 }, paper: { equity: 9800 } },
    divisions: [
      { key: 'live-a', mode: 'live' },
      { key: 'paper-a', mode: 'paper' },
      { key: 'live-b', mode: 'live' },
    ],
  });
  assert.deepEqual(model.groups[0].divisions.map((row) => row.key), ['live-a', 'live-b']);
  assert.deepEqual(model.groups[1].divisions.map((row) => row.key), ['paper-a']);
  assert.equal(model.groups[1].moneyLabel, 'Simulated INR');
});

test('null and non-finite metrics remain insufficient data', () => {
  assert.equal(formatMoney(null), INSUFFICIENT_DATA);
  assert.equal(formatMoney(Number.NaN), INSUFFICIENT_DATA);
  assert.equal(formatNumber(undefined), INSUFFICIENT_DATA);
  assert.equal(formatNumber(Number.POSITIVE_INFINITY), INSUFFICIENT_DATA);
});

test('money formatting never presents paper balances as real money', () => {
  assert.equal(formatMoney(1234.5, 'live'), 'INR 1,234.50');
  assert.equal(formatMoney(1234.5, 'paper'), 'Simulated INR 1,234.50');
  assert.equal(formatMoney(25, 'paper', { signed: true }), '+Simulated INR 25.00');
});

test('reconciliation mismatch is explicit and counted', () => {
  const mismatch = { mode: 'live', reconciliation: { status: 'MISMATCH' } };
  const unavailable = { mode: 'paper', reconciliation: { status: 'UNAVAILABLE' } };
  assert.equal(hasReconciliationMismatch(mismatch), true);
  assert.equal(hasReconciliationMismatch(unavailable), false);
  assert.equal(buildDivisionViewModel({ divisions: [mismatch, unavailable] }).mismatchCount, 1);
});
