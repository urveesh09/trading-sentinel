export const INSUFFICIENT_DATA = 'Insufficient data';

const hasNumber = (value) => value !== null && value !== undefined && Number.isFinite(Number(value));
const firstNumber = (...values) => values.find(hasNumber);

export function formatCount(value) {
  return hasNumber(value) ? Number(value).toLocaleString('en-IN') : INSUFFICIENT_DATA;
}

export function formatRate(value, digits = 1) {
  return hasNumber(value) ? `${(Number(value) * 100).toFixed(digits)}%` : INSUFFICIENT_DATA;
}

export function formatScenarioMoney(value) {
  return hasNumber(value)
    ? `Estimated INR ${Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : INSUFFICIENT_DATA;
}

export function formatSimulatedMoney(value) {
  return hasNumber(value)
    ? `Simulated INR ${Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : INSUFFICIENT_DATA;
}

export function formatPaperMoney(value) {
  return hasNumber(value)
    ? `INR ${Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : INSUFFICIENT_DATA;
}

const DEFINITIONS = {
  momentum: { id: 'momentum', title: 'Momentum Recency', subtitle: 'VWAP crossover recency and distance filters' },
  penny: { id: 'penny', title: 'Penny Breakout', subtitle: 'Time-window and volume-threshold candidates' },
  fno: { id: 'fno', title: 'F&O Opening Range', subtitle: 'Opening-range freshness and confirmation variants' },
};

function normalizeVariant(experimentId, name, config, row = {}) {
  const evaluations = firstNumber(row.evaluations);
  const rawCandidates = firstNumber(row.raw_accepts, row.accepts, row.accepted_evaluations);
  const distinctCandidates = firstNumber(row.distinct_candidates);
  const repeats = hasNumber(row.repeat_accepts)
    ? Number(row.repeat_accepts)
    : hasNumber(rawCandidates) && hasNumber(distinctCandidates)
      ? Math.max(Number(rawCandidates) - Number(distinctCandidates), 0)
      : null;
  const acceptRate = hasNumber(row.accept_rate)
    ? Number(row.accept_rate)
    : hasNumber(evaluations) && Number(evaluations) > 0 && hasNumber(rawCandidates)
      ? Number(rawCandidates) / Number(evaluations)
      : null;
  const repeatRate = hasNumber(rawCandidates) && Number(rawCandidates) > 0 && hasNumber(repeats)
    ? Number(repeats) / Number(rawCandidates)
    : null;
  return {
    name,
    config: config || {},
    evaluations,
    rawCandidates,
    distinctCandidates,
    repeats,
    acceptRate,
    repeatRate,
    blockers: Array.isArray(row.top_rejects) ? row.top_rejects : [],
    warnings: Array.isArray(row.warnings) ? row.warnings : [],
    estimatedPostCost: experimentId === 'fno' ? (row.estimated_post_cost || null) : null,
    virtualOutcome: experimentId === 'penny' ? {
      entries: firstNumber(row.paper_entries) ?? null,
      open: firstNumber(row.open_trades) ?? null,
      closed: firstNumber(row.closed_trades) ?? null,
      wins: firstNumber(row.winning_trades) ?? null,
      losses: firstNumber(row.losing_trades) ?? null,
      breakevens: firstNumber(row.breakeven_trades) ?? null,
      winRate: firstNumber(row.win_rate) ?? null,
      avgR: firstNumber(row.avg_r) ?? null,
      netPnl: firstNumber(row.net_pnl) ?? null,
      expectancy: firstNumber(row.expectancy) ?? null,
      profitFactor: firstNumber(row.profit_factor) ?? null,
      maxDrawdown: firstNumber(row.max_drawdown) ?? null,
    } : null,
    simulatedOutcomes: experimentId === 'momentum' ? {
      entries: firstNumber(row.paper_entries),
      open: firstNumber(row.open_trades),
      closed: firstNumber(row.closed_trades),
      gross: firstNumber(row.gross_pnl),
      costs: firstNumber(row.costs),
      net: firstNumber(row.net_pnl),
      expectancy: firstNumber(row.net_expectancy),
      profitFactor: firstNumber(row.profit_factor),
      breakevens: firstNumber(row.breakevens),
      winRate: firstNumber(row.win_rate),
      averageR: firstNumber(row.avg_r),
      maxDrawdown: firstNumber(row.max_drawdown),
      currentDrawdown: firstNumber(row.current_drawdown),
    } : null,
  };
}

export function normalizeExperiment(experimentId, payload, error = null) {
  const definition = DEFINITIONS[experimentId];
  if (!definition) throw new Error(`Unknown experiment: ${experimentId}`);
  const registry = payload?.registry && typeof payload.registry === 'object' ? payload.registry : {};
  const comparisonRows = Array.isArray(payload?.comparison?.variants) ? payload.comparison.variants : [];
  const byName = new Map(comparisonRows.map((row) => [row.variant, row]));
  const names = [...new Set([...Object.keys(registry), ...comparisonRows.map((row) => row.variant).filter(Boolean)])];
  return {
    ...definition,
    enabled: payload?.enabled ?? null,
    status: error ? 'unavailable' : (payload?.status || 'unavailable'),
    warning: error?.message || payload?.warning || null,
    researchOnly: payload?.research_only !== false,
    canPlaceOrders: payload?.can_place_orders === true,
    variants: names.map((name) => normalizeVariant(experimentId, name, registry[name], byName.get(name))),
  };
}

export function buildResearchCenterModel(payloads = {}, errors = {}) {
  return ['momentum', 'penny', 'fno'].map((id) => normalizeExperiment(id, payloads[id], errors[id]));
}
