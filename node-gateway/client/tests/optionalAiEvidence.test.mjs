import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(
  resolve(__dirname, '../src/pages/Dashboard.jsx'),
  'utf-8',
);

test('optional-AI evidence renders producer p95 latency', () => {
  assert.match(source, /P95 response/);
  assert.match(source, /usefulness\.response_seconds_p95/);
});

test('optional-AI evidence renders the producer completion clock', () => {
  assert.match(source, /Last completed/);
  assert.match(source, /usefulness\.last_completed_at/);
});

test('optional-AI cache rate uses the validated producer field', () => {
  assert.match(source, /Number\.isFinite\(usefulness\.cache_hit_rate\)/);
});

