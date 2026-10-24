import test from 'node:test';
import assert from 'node:assert/strict';
import { buildReviewModel, formatDay, percent, reviewUrl, syncNote, syncRefreshMs, trendOf } from '../src/utils/partnerReview.js';

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

test('[O21-PX] rules kept, signed shares, minutes and prices read plainly', async () => {
  const { scoreTone, signedPercent, minutesLabel, formatPrice } = await import('../src/utils/partnerReview.js');
  assert.deepEqual([scoreTone(100), scoreTone(80), scoreTone(79), scoreTone(50), scoreTone(49), scoreTone(null)],
    ['text-emerald-300', 'text-emerald-300', 'text-amber-300', 'text-amber-300', 'text-red-300', 'text-gray-300']);
  assert.deepEqual([signedPercent(-0.0123), signedPercent(0.05), signedPercent(0), signedPercent(null)],
    ['−1.2%', '+5.0%', '0.0%', 'n/a']);
  assert.deepEqual([minutesLabel(45), minutesLabel(130), minutesLabel(120), minutesLabel(undefined)],
    ['45 min', '2 h 10 min', '2 h', 'n/a']);
  assert.equal(formatPrice(131), '₹131');
  assert.equal(formatPrice(null), '?');
});

test('[O21-PX] the chart maps minutes and prices into the box and keeps far levels off it', async () => {
  const { chartGeometry } = await import('../src/utils/partnerReview.js');
  assert.equal(chartGeometry(undefined), null);
  assert.equal(chartGeometry({ points: [[1, 100]] }), null);
  const chart = {
    points: [[55, 100], [75, 131], [104, 110]],
    marks: [{ t: 75, price: 131, kind: 'buy', at: '10:30' }, { t: 91, price: 110, kind: 'sell', at: '10:46' }],
    levels: [{ label: 'Your stop', price: 105, kind: 'your_stop' }, { label: 'Card target', price: 400, kind: 'target' }],
    start: '10:10', end: '10:59',
  };
  const geo = chartGeometry(chart, { width: 100, height: 100, padX: 0, padY: 0 });
  // x: 55 -> 0, 104 -> 100; y: the highest price at the top, the lowest at the bottom (with an 8% margin).
  assert.ok(geo.path.startsWith('M0,'));
  assert.ok(geo.path.endsWith(`L100,${geo.path.split(' ').at(-1).split(',')[1]}`));
  const [buy, sell] = geo.marks;
  assert.ok(buy.y < sell.y, 'a higher price is drawn higher');
  assert.equal(buy.x, Math.round(((75 - 55) / 49) * 1000) / 10);
  assert.deepEqual(geo.levels.map((l) => l.label), ['Your stop']);
  assert.deepEqual(geo.hiddenLevels.map((l) => l.label), ['Card target']);
  assert.deepEqual([geo.start, geo.end], ['10:10', '10:59']);
});

test('[O21-PX] the model carries the score, day numbers, orders, focus and window stats', () => {
  const model = buildReviewModel({
    review: { score: { kept: 4, of: 6, pct: 67, rules: [] }, stats: { wins: 1 }, account: { cash: 50000 },
      orders: { placed: 3, rejected: [] } },
    progress: { focus: { rule: 'Wait for a card.' }, stats: { trades: 6 } },
  });
  assert.deepEqual([model.score.kept, model.stats.wins, model.account.cash, model.orders.placed, model.focus.rule,
    model.progress.stats.trades], [4, 1, 50000, 3, 'Wait for a card.', 6]);
  const empty = buildReviewModel({});
  assert.deepEqual([empty.score, empty.stats, empty.account, empty.orders, empty.focus, empty.progress.stats],
    [null, null, null, null, null, null]);
});

test('[A22-P4] the page says what the background read is doing and refreshes only while it runs', () => {
  assert.equal(syncRefreshMs({ state: 'reading' }), 4000);
  assert.equal(syncRefreshMs({ state: 'enriching' }), 4000);
  for (const state of ['done', 'partial', 'failed', 'idle']) assert.equal(syncRefreshMs({ state }), 0);
  assert.equal(syncRefreshMs(undefined), 0);
  assert.match(syncNote({ state: 'enriching' }), /updates itself/);
  assert.equal(syncNote({ state: 'done' }), null);
  assert.equal(syncNote(null), null);
  assert.deepEqual(buildReviewModel({ sync: { state: 'reading' } }).sync, { state: 'reading' });
  assert.equal(buildReviewModel(undefined).sync, null);
});

test('[O23-PD] the PDF url carries a valid day only', async () => {
  const { reviewPdfUrl } = await import('../src/utils/partnerReview.js');
  assert.equal(reviewPdfUrl('2026-10-23'), '/api/partner-kite/review/pdf?day=2026-10-23');
  assert.equal(reviewPdfUrl(''), '/api/partner-kite/review/pdf');
  assert.equal(reviewPdfUrl('2026-10-23&evil=1'), '/api/partner-kite/review/pdf');
});

test('[O23-PH] the day list joins the sources newest first, and steps a day back or forward', async () => {
  const { dayList, dayNeighbours } = await import('../src/utils/partnerReview.js');
  const days = dayList(['2026-10-23', '2026-10-19'], ['2026-10-19', '2026-10-15', 'bad'], '2026-10-21', undefined);
  assert.deepEqual(days, ['2026-10-23', '2026-10-21', '2026-10-19', '2026-10-15']);
  assert.deepEqual(dayList(undefined, null, ''), []);
  assert.deepEqual(dayNeighbours(days, '2026-10-19'), { older: '2026-10-15', newer: '2026-10-21' });
  assert.deepEqual(dayNeighbours(days, '2026-10-23'), { older: '2026-10-21', newer: null });
  assert.deepEqual(dayNeighbours(days, '2026-10-15'), { older: null, newer: '2026-10-19' });
  assert.deepEqual(dayNeighbours(days, '2026-09-01'), { older: null, newer: null });
});

test('[O23-PH] an earlier day says "that day" and only the newest day shows tomorrow\'s focus', async () => {
  const { dayWords } = await import('../src/utils/partnerReview.js');
  assert.deepEqual(dayWords(false), { lesson: 'Your lesson for today', more: 'More to learn from today',
    rules: 'Rules kept today', orders: 'Your orders today' });
  assert.deepEqual(dayWords(true), { lesson: 'Your lesson from that day', more: 'More to learn from that day',
    rules: 'Rules kept that day', orders: 'Your orders that day' });
  const past = buildReviewModel({ day: '2026-10-19', today: '2026-10-23', newest: false });
  assert.deepEqual([past.day, past.today, past.past, past.newest], ['2026-10-19', '2026-10-23', true, false]);
  const today = buildReviewModel({ day: '2026-10-23', today: '2026-10-23', newest: true });
  assert.deepEqual([today.past, today.newest], [false, true]);
  // An engine from before O23 sends neither field: the page reads as before.
  const older = buildReviewModel({ day: '2026-10-19' });
  assert.deepEqual([older.past, older.newest], [false, true]);
});

test('[O24-PW] the page says when the trade watch is on, and what quiet keeps', async () => {
  const { watchNote } = await import('../src/utils/partnerReview.js');
  const on = buildReviewModel({ day: '2026-10-26', today: '2026-10-26', watch: { on: true, until: '15:40', quiet: false } });
  assert.deepEqual(on.watch, { until: '15:40', quiet: false });
  assert.equal(watchNote(on.watch), 'Trade watch on until 15:40: messages on Telegram when a buy has no stop or only part of it is covered, a stop is moved down, cancelled or does not sell, Zerodha refuses an order, and before the close. It never places an order.');
  assert.equal(watchNote({ until: '15:40', quiet: true }), 'Trade watch on until 15:40, quiet today: you hear only when a stop is moved down, cancelled or does not sell, or Zerodha refuses an order.');
  // Off, or an engine from before O24: nothing is shown.
  assert.equal(buildReviewModel({ watch: { on: false } }).watch, null);
  assert.equal(buildReviewModel({}).watch, null);
  assert.equal(watchNote(null), '');
});

test('[O24-SB] the rules a day was checked with are named', async () => {
  const { rulesAsOf } = await import('../src/utils/partnerReview.js');
  assert.equal(rulesAsOf({ rules_version: '2026-10-24' }), ' Rules of 24 Oct 2026.');
  assert.equal(rulesAsOf({}), '');
  assert.equal(rulesAsOf(null), '');
  assert.equal(rulesAsOf({ rules_version: 'soon' }), '');
});
