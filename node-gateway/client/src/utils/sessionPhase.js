// [WORKFLOW-J.8 2026-09-13] Pure session-phase utility.
//
// Single source of truth for the bounded session phase
// visualisation and execution-allowed derivation on the
// React client. Mirrors the Node `isExecutionAllowed`
// contract bit-perfect; the translation table lives
// here (not in the consumers) so a future phase-set
// change surfaces as a single-file review.
//
// The phase string comes from `health.session_phase`
// (the Node `/` GET response, exposed by the J.6
// sessionPhase mirror). When the field is missing
// (e.g. health fetch failing) we treat it as
// ``UNKNOWN`` -- never throws, never returns
// undefined -- the UI contract is "always show a
// coloured phase label".
//
// This module is intentionally framework-agnostic
// (no React imports). Tests can import it directly;
// components import it via the standard import.

export const VALID_SESSION_PHASES = Object.freeze([
  'CLOSED',
  'PRE_MARKET',
  'CONTINUOUS_TRADING',
  'CAS_REFERENCE_PRICE_WINDOW',
  'CAS_ORDER_ENTRY',
  'CAS_LIMIT_ENTRY_ONLY',
  'CAS_MATCHING',
  'CAS_POST',
  'DERIVATIVES_CAS_ALIGNED',
  'UNKNOWN',
]);

// Phases that block broker orders (J.7 contract).
// PRE_MARKET blocks by default but becomes allowed
// when ``allow_pre_market=true``; that branch lives
// in the Node side. The client only displays the
// current phase.
const BLOCKING_PHASES = new Set([
  'CLOSED',
  'PRE_MARKET',
  'CAS_REFERENCE_PRICE_WINDOW',
  'CAS_ORDER_ENTRY',
  'CAS_LIMIT_ENTRY_ONLY',
  'CAS_MATCHING',
  'CAS_POST',
  'UNKNOWN',
]);

// Human-readable display labels for each bounded phase.
// Keep them short -- they go in a small badge.
export const PHASE_DISPLAY_LABEL = Object.freeze({
  CLOSED: 'Market Closed',
  PRE_MARKET: 'Pre-Market',
  CONTINUOUS_TRADING: 'Continuous Trading',
  CAS_REFERENCE_PRICE_WINDOW: 'CAS: Reference Price',
  CAS_ORDER_ENTRY: 'CAS: Order Entry',
  CAS_LIMIT_ENTRY_ONLY: 'CAS: Limit Entry',
  CAS_MATCHING: 'CAS: Matching',
  CAS_POST: 'CAS: Post-Close',
  DERIVATIVES_CAS_ALIGNED: 'Derivatives: CAS Aligned',
  UNKNOWN: 'Unknown',
});

// Tailwind class set for each phase. Three buckets:
//   - green   -> execution allowed (CONTINUOUS_TRADING,
//                DERIVATIVES_CAS_ALIGNED)
//   - yellow  -> execution blocked but expected
//                (PRE_MARKET, CAS_POST cash-only, CAS
//                sub-windows during the closing auction)
//   - red     -> execution blocked, unexpected or
//                outside-trading-hours (CLOSED, UNKNOWN)
//
// CAS_POST is technically a CAS sub-window so we colour
// it yellow (in-block but expected), not red.
export const PHASE_COLOR_CLASS = Object.freeze({
  CLOSED: 'bg-red-900 text-red-200 border-red-700',
  PRE_MARKET: 'bg-yellow-900 text-yellow-100 border-yellow-700',
  CONTINUOUS_TRADING: 'bg-green-900 text-green-200 border-green-700',
  CAS_REFERENCE_PRICE_WINDOW: 'bg-yellow-900 text-yellow-100 border-yellow-700',
  CAS_ORDER_ENTRY: 'bg-yellow-900 text-yellow-100 border-yellow-700',
  CAS_LIMIT_ENTRY_ONLY: 'bg-yellow-900 text-yellow-100 border-yellow-700',
  CAS_MATCHING: 'bg-yellow-900 text-yellow-100 border-yellow-700',
  CAS_POST: 'bg-yellow-900 text-yellow-100 border-yellow-700',
  DERIVATIVES_CAS_ALIGNED: 'bg-green-900 text-green-200 border-green-700',
  UNKNOWN: 'bg-red-900 text-red-200 border-red-700',
});

// Returns whether the bounded phase blocks broker
// orders. Mirrors ``isExecutionAllowed`` on the Node
// side; PRE_MARKET is always reported as blocking here
// because the operator override (``allow_pre_market``)
// is not exposed to the dashboard.
//
// The contract: any input that is not a documented
// phase string -- null, undefined, numbers, objects,
// arbitrary strings -- blocks execution. This matches
// the "fail closed for safety" pattern: a misconfigured
// health payload (or a network blip that returns
// ``undefined``) must NOT silently allow an order that
// the server would reject.
export function isExecutionBlockedByPhase(phase) {
  if (typeof phase !== 'string') return true;
  if (VALID_SESSION_PHASES.indexOf(phase) < 0) return true;
  return BLOCKING_PHASES.has(phase);
}

// Coerce an unknown input (null, undefined, anything
// not in VALID_SESSION_PHASES) to UNKNOWN. Never
// throws. The UI contract is "always show a coloured
// phase label" -- never an unstyled string.
export function coercePhase(phase) {
  if (typeof phase !== 'string') return 'UNKNOWN';
  if (VALID_SESSION_PHASES.indexOf(phase) >= 0) return phase;
  return 'UNKNOWN';
}

// Bundle everything for components that need it.
export function describePhase(phase) {
  const safe = coercePhase(phase);
  return {
    phase: safe,
    label: PHASE_DISPLAY_LABEL[safe],
    colorClass: PHASE_COLOR_CLASS[safe],
    executionBlocked: isExecutionBlockedByPhase(safe),
  };
}
