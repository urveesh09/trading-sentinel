const hasValue = (value) => value !== null && value !== undefined && Number.isFinite(Number(value));

export const INSUFFICIENT_DATA = 'Insufficient data';

export function formatMoney(value, mode = 'live', options = {}) {
  if (!hasValue(value)) return INSUFFICIENT_DATA;
  const amount = Number(value);
  const sign = options.signed && amount > 0 ? '+' : '';
  const label = mode === 'paper' ? 'Simulated INR' : 'INR';
  return `${sign}${label} ${amount.toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function formatNumber(value, digits = 2) {
  if (!hasValue(value)) return INSUFFICIENT_DATA;
  return Number(value).toFixed(digits);
}

export function formatPercent(value, digits = 1) {
  if (!hasValue(value)) return INSUFFICIENT_DATA;
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

export function hasReconciliationMismatch(division) {
  return division?.reconciliation?.status === 'MISMATCH';
}

export function buildDivisionViewModel(payload) {
  const divisions = Array.isArray(payload?.divisions) ? payload.divisions : [];
  const makeGroup = (mode) => ({
    mode,
    label: mode === 'paper' ? 'PAPER / SIMULATED' : 'LIVE CAPITAL',
    moneyLabel: mode === 'paper' ? 'Simulated INR' : 'INR',
    total: payload?.totals?.[mode] || null,
    divisions: divisions.filter((division) => division?.mode === mode),
  });
  return {
    asOf: payload?.as_of || null,
    accountingTruth: payload?.accounting_truth || null,
    groups: [makeGroup('live'), makeGroup('paper')],
    mismatchCount: divisions.filter(hasReconciliationMismatch).length,
  };
}
