// [O21-SC] Presets and labels for the Standard Capital page.

const hasValue = (value) => value !== null && value !== undefined && Number.isFinite(Number(value));

export const CAPITAL_PRESETS = [
  { label: '₹10k', value: 10000 },
  { label: '₹12.5k', value: 12500 },
  { label: '₹2L', value: 200000 },
  { label: '₹5L', value: 500000 },
];

export function sincePresets(now = new Date()) {
  const thirty = new Date(now.getTime() - 30 * 24 * 3600 * 1000);
  return [
    { label: 'All history', value: '' },
    { label: 'Since Sep 1', value: '2026-09-01' },
    { label: 'Last 30 days', value: thirty.toISOString().slice(0, 10) },
  ];
}

export function formatCapital(value) {
  if (!hasValue(value)) return 'n/a';
  const amount = Number(value);
  if (amount >= 100000) return `₹${(amount / 100000).toLocaleString('en-IN', { maximumFractionDigits: 2 })}L`;
  return `₹${amount.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
}

export function formatPct(value, digits = 1) {
  if (!hasValue(value)) return 'n/a';
  const amount = Number(value);
  return `${amount > 0 ? '+' : ''}${amount.toFixed(digits)}%`;
}

export function standardCapitalUrl(capital, since) {
  const params = new URLSearchParams();
  if (hasValue(capital)) params.set('capital', String(capital));
  if (since) params.set('since', since);
  return `/api/proxy/performance/standard-capital?${params.toString()}`;
}

export function rowsByReturn(books) {
  return [...(books || [])].sort((a, b) => {
    const left = hasValue(a.return_pct) ? Number(a.return_pct) : -Infinity;
    const right = hasValue(b.return_pct) ? Number(b.return_pct) : -Infinity;
    return right - left;
  });
}
