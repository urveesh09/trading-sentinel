import test from 'node:test';
import assert from 'node:assert/strict';
import {
  STATUS_LABEL, buildCoachModel, buildReportBody, coachUrl, fillLabel, fillSource, formatRs, istIsoFromLocal,
  zerodhaLine,
} from '../src/utils/partnerCoach.js';
import { formatCapital, formatPct, rowsByReturn, standardCapitalUrl } from '../src/utils/standardCapital.js';

test('rupees carry a sign and a true minus', () => {
  assert.equal(formatRs(1240.4), '+₹1,240');
  assert.equal(formatRs(-1094), '−₹1,094');
  assert.equal(formatRs(0), '₹0');
  assert.equal(formatRs(null), 'n/a');
});

test('a tap estimate is marked with ≈ and a missing price is said', () => {
  assert.equal(fillLabel({ price: 516, price_basis: 'ASK_AT_TAP', lots: 1, at: '2026-10-19T12:09:00+05:30' }),
    '1 lot ≈₹516 at 12:09');
  assert.equal(fillLabel({ price: 518.5, price_basis: 'PARTNER_STATED', lots: 2, at: '2026-10-19T12:10:00+05:30' }),
    '2 lots ₹518.5 at 12:10');
  assert.equal(fillLabel({ price: null, lots: null, at: '2026-10-19T15:12:00+05:30' }), 'price not reported at 15:12');
});

test('report form validates and reads the time as IST', () => {
  assert.equal(istIsoFromLocal('2026-10-21T12:09'), '2026-10-21T12:09:00+05:30');
  assert.equal(istIsoFromLocal('12:09'), null);
  const ok = buildReportBody({ action: 'buy', time: '2026-10-21T12:09', advisoryId: 'abc', price: '518.5', lots: '2' });
  assert.deepEqual(ok, { errors: [], body: { action: 'BUY', trade_at: '2026-10-21T12:09:00+05:30',
    advisory_id: 'abc', price: 518.5, lots: 2 } });
  const off = buildReportBody({ action: 'SELL', time: '2026-10-21T13:00', underlying: 'NIFTY', strike: '',
    optType: 'PE', price: '-1', lots: '0' });
  assert.equal(off.errors.length, 3);
  const skip = buildReportBody({ action: 'SKIP', time: '2026-10-21T12:00', advisoryId: 'abc', price: '9' });
  assert.deepEqual(skip.body, { action: 'SKIP', trade_at: '2026-10-21T12:00:00+05:30', advisory_id: 'abc' });
});

test('coach model lists cards for the form and keeps the safety flags', () => {
  const model = buildCoachModel({
    summary: { cards_delivered: 1 }, leaks: [], automatic_execution: false, blocks_cards: false,
    days: [{ day: '2026-10-19', cards: [{ advisory_id: 'c1', time: '12:06', option: 'SENSEX 74200 PE' }] }],
  });
  assert.deepEqual(model.cardOptions, [{ value: 'c1', label: '2026-10-19 12:06 SENSEX 74200 PE' }]);
  assert.equal(model.noOrders, true);
  assert.equal(buildCoachModel({}).noOrders, false);
});

test('standard capital labels, url and ordering', () => {
  assert.equal(formatCapital(200000), '₹2L');
  assert.equal(formatCapital(12500), '₹12,500');
  assert.equal(formatPct(3.62), '+3.6%');
  assert.equal(formatPct(-2.89), '-2.9%');
  assert.equal(standardCapitalUrl(500000, '2026-09-01'),
    '/api/proxy/performance/standard-capital?capital=500000&since=2026-09-01');
  assert.deepEqual(rowsByReturn([{ key: 'a', return_pct: -1 }, { key: 'b', return_pct: null }, { key: 'c', return_pct: 3 }])
    .map((row) => row.key), ['c', 'a', 'b']);
});

test('[O21-PK] Zerodha fills, the partner url and the owner status line', () => {
  assert.equal(fillSource({ source: 'ZERODHA' }), 'from Zerodha');
  assert.equal(fillSource({ source: 'DASHBOARD' }), 'entered here');
  assert.equal(fillSource({ source: 'TELEGRAM_BUTTON' }), 'from Telegram');
  assert.equal(fillLabel({ price: 518.5, price_basis: 'BROKER_FILL', lots: 2, at: '2026-10-19T12:09:10+05:30' }),
    '2 lots ₹518.5 at 12:09');
  assert.equal(STATUS_LABEL.NOT_TRADED, 'Not traded');
  assert.equal(coachUrl(true, 1), '/api/partner-kite/coach?days=1');
  assert.equal(coachUrl(false, 30), '/api/proxy/partner/coach?days=30');
  assert.match(zerodhaLine(null, '2026-10-19'), /not set up/);
  const read = { configured: true, connected: true, account: 'AB***34',
    days: { '2026-10-19': { synced_at: '2026-10-19T15:41:02+05:30', complete: true, option_orders: 2 } } };
  assert.equal(zerodhaLine(read, '2026-10-19'),
    'Zerodha connected (AB***34) · today read at 15:41, whole day · 2 option order(s)');
  assert.match(zerodhaLine({ configured: true, connected: false, days: {} }, '2026-10-19'),
    /^Zerodha not connected now · today not read yet/);
  assert.deepEqual(buildCoachModel({ zerodha: read }).zerodha, read);
});
