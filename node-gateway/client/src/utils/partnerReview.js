// [O21-PL] Helpers for the partner's review page. The engine writes every
// sentence and number; this module only picks URLs and labels.

const DAY = /^\d{4}-\d{2}-\d{2}$/;
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function reviewUrl(day) {
  return DAY.test(String(day || '')) ? `/api/partner-kite/review?day=${day}` : '/api/partner-kite/review';
}

// "2026-10-19" -> "Mon 19 Oct" (a calendar date, no time zone involved).
export function formatDay(day) {
  if (!DAY.test(String(day || ''))) return '';
  const [y, m, d] = day.split('-').map(Number);
  const weekday = WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
  return `${weekday} ${d} ${MONTHS[m - 1]}`;
}

export const TREND = {
  fewer: { label: 'fewer than last week', tone: 'text-emerald-300' },
  more: { label: 'more than last week', tone: 'text-red-300' },
  same: { label: 'same as last week', tone: 'text-gray-400' },
};

export function trendOf(pattern) {
  return TREND[pattern?.trend] || TREND.same;
}

export function percent(rate) {
  if (rate === null || rate === undefined || !Number.isFinite(Number(rate))) return 'n/a';
  return `${Math.round(Number(rate) * 100)}%`;
}

// [O21-PX] "Rules kept" reads green from 80%, amber from 50%, else red.
export function scoreTone(pct) {
  if (pct === null || pct === undefined || !Number.isFinite(Number(pct))) return 'text-gray-300';
  if (Number(pct) >= 80) return 'text-emerald-300';
  return Number(pct) >= 50 ? 'text-amber-300' : 'text-red-300';
}

// A signed share with a true minus sign, as the engine writes rupees: "−1.2%".
export function signedPercent(value, digits = 1) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'n/a';
  const number = Number(value) * 100;
  const body = `${Math.abs(number).toFixed(digits)}%`;
  if (Number(body.slice(0, -1)) === 0) return body;
  return number < 0 ? `−${body}` : `+${body}`;
}

// 45 -> "45 min", 130 -> "2 h 10 min".
export function minutesLabel(minutes) {
  if (minutes === null || minutes === undefined || !Number.isFinite(Number(minutes))) return 'n/a';
  const total = Math.round(Number(minutes));
  if (total < 60) return `${total} min`;
  const rest = total % 60;
  return rest ? `${Math.floor(total / 60)} h ${rest} min` : `${Math.floor(total / 60)} h`;
}

export function formatPrice(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '?';
  return `₹${Number(value).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
}

export const LEVEL_STYLE = {
  stop: 'stroke-red-400',
  target: 'stroke-emerald-400',
  limit: 'stroke-sky-400',
  your_stop: 'stroke-amber-400',
};
export const LEVEL_TEXT = {
  stop: 'fill-red-300',
  target: 'fill-emerald-300',
  limit: 'fill-sky-300',
  your_stop: 'fill-amber-300',
};

const finitePair = (point) => Array.isArray(point) && Number.isFinite(Number(point[0])) && Number.isFinite(Number(point[1]));

// [O21-PX] The trade's price chart, drawn by the page as SVG: x is minutes
// since 09:15, y is the option price. A reference line (card SL, target,
// your stop) widens the price range only when it is near the prices, so a
// far target cannot flatten the line; the ones left out are counted.
export function chartGeometry(chart, { width = 320, height = 140, padX = 6, padY = 10 } = {}) {
  const points = (Array.isArray(chart?.points) ? chart.points : []).filter(finitePair).map(([t, p]) => [Number(t), Number(p)]);
  if (points.length < 2) return null;
  const marks = (Array.isArray(chart?.marks) ? chart.marks : [])
    .filter((m) => Number.isFinite(Number(m?.t)) && Number.isFinite(Number(m?.price)));
  const levels = (Array.isArray(chart?.levels) ? chart.levels : []).filter((l) => Number.isFinite(Number(l?.price)));
  const prices = [...points.map((p) => p[1]), ...marks.map((m) => Number(m.price))];
  let lo = Math.min(...prices);
  let hi = Math.max(...prices);
  const span = Math.max(hi - lo, hi * 0.02, 0.5);
  const near = levels.filter((l) => Number(l.price) >= lo - span * 0.5 && Number(l.price) <= hi + span * 0.5);
  lo = Math.min(lo, ...near.map((l) => Number(l.price)));
  hi = Math.max(hi, ...near.map((l) => Number(l.price)));
  const pad = (hi - lo) * 0.08 || 1;
  lo -= pad;
  hi += pad;
  const ts = [...points.map((p) => p[0]), ...marks.map((m) => Number(m.t))];
  const t0 = Math.min(...ts);
  const t1 = Math.max(...ts);
  const x = (t) => padX + ((t - t0) / Math.max(t1 - t0, 1)) * (width - 2 * padX);
  const y = (price) => padY + (1 - (price - lo) / (hi - lo)) * (height - 2 * padY);
  const round = (value) => Math.round(value * 10) / 10;
  return {
    width,
    height,
    path: points.map((p, i) => `${i ? 'L' : 'M'}${round(x(p[0]))},${round(y(p[1]))}`).join(' '),
    marks: marks.map((m) => ({ ...m, x: round(x(Number(m.t))), y: round(y(Number(m.price))) })),
    levels: near.map((l) => ({ ...l, y: round(y(Number(l.price))) })),
    hiddenLevels: levels.filter((l) => !near.includes(l)),
    start: chart.start || '',
    end: chart.end || '',
  };
}

// Everything the page renders, with safe empty defaults.
export function buildReviewModel(payload) {
  const review = payload?.review || {};
  const progress = payload?.progress || {};
  return {
    day: payload?.day || '',
    days: Array.isArray(payload?.days_available) ? payload.days_available : [],
    headline: review.headline || { trades: 0, text: '' },
    lesson: review.lesson || null,
    moreLessons: Array.isArray(review.more_lessons) ? review.more_lessons : [],
    wellDone: Array.isArray(review.well_done) ? review.well_done : [],
    trades: Array.isArray(review.trades) ? review.trades : [],
    untaken: review.untaken || { cards: [], text: '' },
    notes: Array.isArray(review.notes) ? review.notes : [],
    source: review.source || null,
    score: review.score || null,
    stats: review.stats || null,
    account: review.account || null,
    orders: review.orders || null,
    focus: progress.focus || null,
    progress: {
      days: Array.isArray(progress.days) ? progress.days : [],
      patterns: Array.isArray(progress.patterns) ? progress.patterns : [],
      trades: progress.trades ?? 0,
      cleanTrades: progress.clean_trades ?? 0,
      cleanRate: progress.clean_rate ?? null,
      streak: progress.clean_streak_days ?? 0,
      pnl: progress.pnl ?? null,
      planPnl: progress.plan_pnl_on_traded_cards ?? null,
      stats: progress.stats || null,
    },
    noOrders: payload?.automatic_execution === false,
  };
}
