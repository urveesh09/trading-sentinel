export const READINESS_STATES = Object.freeze([
  'COLLECTING',
  'INELIGIBLE',
  'CANDIDATE_FOR_PAPER_REVIEW',
]);

const mapping = (value) => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
const list = (value) => Array.isArray(value) ? value : [];
const text = (value) => value === null || value === undefined || value === '' ? null : String(value);

export function evidenceLabel(value) {
  if (value === null || value === undefined || value === '') return 'Insufficient evidence';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export function normalizePromotionReadiness(payload, error = null) {
  const root = mapping(payload);
  const rootErrors = list(root.source_errors).map(String);
  if (error) rootErrors.unshift(error.message || String(error));
  const families = list(root.families).filter((row) => row && typeof row === 'object').map((row) => ({
    strategy: text(row.strategy) || 'UNKNOWN',
    reconciliationDivision: text(row.reconciliation_division),
    sourceErrors: list(row.source_errors).map(String),
    variants: list(row.variants).filter((variant) => variant && typeof variant === 'object').map((variant) => {
      const suppliedState = text(variant.state);
      const validState = READINESS_STATES.includes(suppliedState);
      const evidence = mapping(variant.evidence);
      return {
        strategy: text(variant.strategy) || text(row.strategy) || 'UNKNOWN',
        variant: text(variant.variant) || 'UNKNOWN_VARIANT',
        state: validState ? suppliedState : 'COLLECTING',
        stateWarning: validState ? null : 'Unsupported or missing readiness state was rejected',
        researchOnly: variant.research_only === true,
        canPlaceOrders: variant.can_place_orders === true,
        evidence: {
          distinctCandidates: evidence.distinct_candidates ?? null,
          closedTrades: evidence.closed_trades ?? null,
          netExpectancy: evidence.net_expectancy_after_costs ?? null,
          profitFactor: evidence.profit_factor ?? null,
          maxDrawdown: evidence.max_drawdown ?? null,
          repeatInflation: evidence.repeat_inflation ?? null,
          oosScoredFolds: evidence.oos_scored_folds ?? null,
          provenanceStatus: evidence.provenance_status ?? null,
          reconciliationStatus: evidence.reconciliation_status ?? null,
        },
        gates: list(variant.blockers).filter((gate) => gate && typeof gate === 'object').map((gate) => ({
          gate: text(gate.gate) || 'unknown_gate',
          status: text(gate.status) || 'COLLECTING',
          observed: gate.observed ?? null,
          required: gate.required ?? null,
          reason: text(gate.reason) || 'No reason supplied',
        })),
        thresholds: mapping(variant.thresholds),
        sources: mapping(variant.sources),
        timestamps: mapping(variant.source_timestamps),
        explanation: text(variant.explanation),
      };
    }),
  }));
  return {
    asOf: text(root.as_of),
    researchOnly: root.research_only === true,
    canPlaceOrders: root.can_place_orders === true,
    authorizationEffect: text(root.authorization_effect),
    warning: text(root.warning),
    sourceErrors: rootErrors,
    families,
  };
}
