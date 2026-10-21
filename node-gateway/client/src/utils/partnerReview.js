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
    progress: {
      days: Array.isArray(progress.days) ? progress.days : [],
      patterns: Array.isArray(progress.patterns) ? progress.patterns : [],
      trades: progress.trades ?? 0,
      cleanTrades: progress.clean_trades ?? 0,
      cleanRate: progress.clean_rate ?? null,
      streak: progress.clean_streak_days ?? 0,
      pnl: progress.pnl ?? null,
      planPnl: progress.plan_pnl_on_traded_cards ?? null,
    },
    noOrders: payload?.automatic_execution === false,
  };
}
