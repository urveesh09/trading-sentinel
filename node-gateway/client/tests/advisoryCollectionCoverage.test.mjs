import test from 'node:test';
import assert from 'node:assert/strict';
import { advisoryCoverageRows } from '../src/utils/advisoryCollectionCoverage.js';

test('unavailable evidence is distinct from a real zero-attempt session', () => {
  const unavailable = advisoryCoverageRows(null);
  assert.equal(unavailable[0].state, 'UNAVAILABLE');
  assert.equal(unavailable[0].attempted, null);

  const observedZero = advisoryCoverageRows({ advisory_collection_attempts: {
    session_date: '2026-09-14',
    per_index: { NIFTY: { state: 'NEVER_ATTEMPTED', attempted: 0, expected: 1,
      missing_schedule_count: 1, incomplete_count: 0 } },
  } });
  assert.equal(observedZero[0].state, 'NEVER_ATTEMPTED');
  assert.equal(observedZero[0].attempted, 0);
  assert.equal(observedZero[0].missing, 1);
  assert.equal(observedZero[1].state, 'UNAVAILABLE');
});

test('complete and partial states preserve typed counts', () => {
  const rows = advisoryCoverageRows({ advisory_collection_attempts: { session_date: '2026-09-14', per_index: {
    NIFTY: { state: 'COMPLETE', attempted: 2, expected: 2, missing_schedule_count: 0, incomplete_count: 0 },
    SENSEX: { state: 'PARTIAL', attempted: 2, expected: 2, missing_schedule_count: 0, incomplete_count: 1 },
  } } });
  assert.deepEqual(rows.map((row) => [row.state, row.incomplete]), [['COMPLETE', 0], ['PARTIAL', 1]]);
});
