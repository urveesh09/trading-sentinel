import test from 'node:test';
import assert from 'node:assert/strict';
import { buildReviewModel, formatDay, percent, reviewUrl, trendOf } from '../src/utils/partnerReview.js';

test('[O21-PL] the review url carries a valid day only', () => {
  assert.equal(reviewUrl(''), '/api/partner-kite/review');
  assert.equal(reviewUrl('2026-10-19'), '/api/partner-kite/review?day=2026-10-19');
  assert.equal(reviewUrl('2026-10-19&evil=1'), '/api/partner-kite/review');
});

test('days read as a weekday and date, without time-zone drift', () => {
  assert.equal(formatDay('2026-10-19'), 'Mon 19 Oct');
  assert.equal(formatDay('2026-10-24'), 'Sat 24 Oct');
  assert.equal(formatDay('bad'), '');
});

test('trends and rates are labelled plainly', () => {
  assert.equal(trendOf({ trend: 'fewer' }).label, 'fewer than last week');
  assert.equal(trendOf({ trend: 'more' }).tone, 'text-red-300');
  assert.equal(trendOf({}).label, 'same as last week');
  assert.equal(percent(0.5), '50%');
  assert.equal(percent(null), 'n/a');
});

test('the model has safe defaults and keeps the engine text as it is', () => {
  const empty = buildReviewModel(undefined);
  assert.equal(empty.lesson, null);
  assert.deepEqual(empty.trades, []);
  assert.equal(empty.progress.streak, 0);
  const model = buildReviewModel({
    day: '2026-10-19', days_available: ['2026-10-19'], automatic_execution: false,
    review: { headline: { trades: 1, text: '1 trade · −₹1,828 after charges' }, lesson: { code: 'HELD_PAST_STOP' },
      more_lessons: [], well_done: [], trades: [{ option: 'SENSEX 74200 PE' }], untaken: { cards: [] }, notes: [],
      source: 'ZERODHA' },
    progress: { clean_rate: 0.5, clean_streak_days: 2, trades: 4, clean_trades: 2, patterns: [], days: [] },
  });
  assert.equal(model.headline.text, '1 trade · −₹1,828 after charges');
  assert.equal(model.lesson.code, 'HELD_PAST_STOP');
  assert.deepEqual([model.progress.cleanRate, model.progress.streak, model.source, model.noOrders], [0.5, 2, 'ZERODHA', true]);
});
