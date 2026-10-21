// [O21-PC] Formatting and form helpers for the Partner Coach page.
// The engine computes every number; this module only labels them.

const hasValue = (value) => value !== null && value !== undefined && Number.isFinite(Number(value));

export const ESTIMATE_BASES = new Set(['ASK_AT_TAP', 'BID_AT_TAP', 'LTP_AT_TAP']);

export function formatRs(value, { signed = true } = {}) {
  if (!hasValue(value)) return 'n/a';
  const amount = Number(value);
  const body = `₹${Math.abs(amount).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
  if (!signed) return amount < 0 ? `−${body}` : body;
  if (amount === 0) return body;
  return amount < 0 ? `−${body}` : `+${body}`;
}

export function formatPrice(value) {
  if (!hasValue(value)) return '?';
  return `₹${Number(value).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
}

export function fillLabel(fill) {
  const price = fill?.price;
  const prefix = ESTIMATE_BASES.has(fill?.price_basis) ? '≈' : '';
  const lots = fill?.lots ? `${fill.lots} lot${fill.lots === 1 ? '' : 's'} ` : '';
  const at = String(fill?.at || '').slice(11, 16) || '?';
  return `${lots}${price == null ? 'price not reported' : prefix + formatPrice(price)} at ${at}`;
}

export function pnlTone(value) {
  if (!hasValue(value) || Number(value) === 0) return 'text-gray-300';
  return Number(value) > 0 ? 'text-emerald-300' : 'text-red-300';
}

export const STATUS_LABEL = {
  BOUGHT: 'Bought',
  EXIT_ONLY: 'Exit reported, buy missing',
  SKIPPED: 'Skipped',
  NOT_TRADED: 'Not traded',
  NOT_REPORTED: 'Not reported',
};

// [O21-PK] Where a fill came from; Zerodha fills are exact and cannot be removed.
export function fillSource(fill) {
  if (fill?.source === 'ZERODHA') return 'from Zerodha';
  if (fill?.source === 'DASHBOARD') return 'entered here';
  return 'from Telegram';
}

// The partner's coach-only session reads through /api/partner-kite; the owner's through /api/proxy.
export function coachUrl(partnerView, days) {
  const base = partnerView ? '/api/partner-kite/coach' : '/api/proxy/partner/coach';
  return `${base}?days=${days}`;
}

// One line on the partner's Zerodha link for the owner.
export function zerodhaLine(zerodha, today) {
  if (!zerodha?.configured) return 'Zerodha not set up: fills come from Telegram replies and this page.';
  const read = zerodha.days?.[today];
  const when = read ? String(read.synced_at || '').slice(11, 16) : null;
  const parts = [zerodha.connected ? `Zerodha connected (${zerodha.account})` : 'Zerodha not connected now'];
  if (read) parts.push(`today read at ${when}${read.complete ? ', whole day' : ', before the close'} · ${read.option_orders} option order(s)`);
  else parts.push('today not read yet: the partner taps “Open today’s review” in Telegram after 15:40');
  return parts.join(' · ');
}

// A datetime-local value ("2026-10-21T12:09") read as IST wall-clock time.
export function istIsoFromLocal(value) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(String(value || ''))) return null;
  return `${value}:00+05:30`;
}

export function buildReportBody(form) {
  const errors = [];
  const action = String(form.action || '').toUpperCase();
  if (!['BUY', 'SELL', 'SKIP'].includes(action)) errors.push('Choose bought, sold or skipped.');
  const tradeAt = istIsoFromLocal(form.time);
  if (!tradeAt) errors.push('Enter the time of the trade.');
  const body = { action, trade_at: tradeAt };
  if (form.note) body.note = String(form.note).slice(0, 200);
  if (form.advisoryId) {
    body.advisory_id = form.advisoryId;
  } else {
    const strike = Number(form.strike);
    if (!form.underlying || !Number.isFinite(strike) || strike <= 0 || !['CE', 'PE'].includes(form.optType)) {
      errors.push('An off-card trade needs the index, strike and CE/PE.');
    }
    Object.assign(body, { underlying: form.underlying, strike, opt_type: form.optType });
  }
  if (action !== 'SKIP') {
    if (form.price !== '' && form.price !== undefined) {
      const price = Number(form.price);
      if (!Number.isFinite(price) || price <= 0) errors.push('Price must be a positive number.');
      body.price = price;
    }
    const lots = Number(form.lots || 1);
    if (!Number.isInteger(lots) || lots < 1 || lots > 50) errors.push('Lots must be 1 to 50.');
    body.lots = lots;
  }
  return { body, errors };
}

export function buildCoachModel(payload) {
  const summary = payload?.summary || {};
  const days = Array.isArray(payload?.days) ? payload.days : [];
  const cards = days.flatMap((day) => (day.cards || []).map((card) => ({ ...card, day: day.day })));
  return {
    summary,
    leaks: Array.isArray(payload?.leaks) ? payload.leaks : [],
    days,
    cardOptions: cards.map((card) => ({ value: card.advisory_id, label: `${card.day} ${card.time} ${card.option}` })),
    quality: payload?.data_quality || {},
    assumptions: payload?.assumptions || {},
    captureEnabled: payload?.capture_enabled !== false,
    zerodha: payload?.zerodha || null,
    noOrders: payload?.automatic_execution === false && payload?.blocks_cards === false,
  };
}
