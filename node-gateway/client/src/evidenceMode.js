// Browser-evidence mode is deliberately unavailable in normal builds.  It is
// a local Dev rendering fixture for visual verification of the real Dashboard
// components, never a replacement for authenticated service evidence.
export const evidenceModeEnabled = import.meta.env.DEV && import.meta.env.VITE_EVIDENCE_DEMO === 'true';

export const evidenceFixtures = {
  health: { token_status: 'active', market_open: false, circuit_breaker_halted: false },
  proactiveActivity: {
    modes: {
      SHADOW: { unique_opportunities: 4, scan_evaluations: 5, stages: { SETUP: 4, DEFERRED: 1, FILLED: 1, CLOSED: 1 } },
      LIVE: { unique_opportunities: 0, scan_evaluations: 0, stages: {} },
      PAPER: { unique_opportunities: 0, scan_evaluations: 0, stages: {} },
      REPLAY: { unique_opportunities: 0, scan_evaluations: 0, stages: {} },
    },
    shadow_positions: [{
      account_id: 'demo-synthetic-account', run_id: 'demo-multisession-v1', open_positions: 1,
      closed_positions: 1, scenario_capital: 150, free_cash: 42.5, reserved_capital: 104,
      gross_pnl: 8, fees: 0.62, net_pnl: 7.38, marked_unrealized_pnl: 1.5,
      unrealized_state: 'MARKED_COMPLETED_BAR',
    }],
    note: 'DEV EVIDENCE FIXTURE — synthetic scenario only; not broker-reconciled profit.',
  },
  partnerCards: {
    mode: 'SHADOW',
    cards: [{
      evaluation_id: 'demo-superseded-card', phase: 'phase2', kind: 'covered_call_recommendation',
      underlying: 'NIFTY', contracts: ['NIFTY-DEMO-CE'], rendered_text: 'Synthetic hedge review: NIFTY coverage.',
      evaluated_at: '2026-09-07T09:30:00+05:30', valid_until: null, portfolio_revision: 1,
      current_portfolio_revision: 3, portfolio_state: 'SUPERSEDED', is_superseded: true,
      delivery_state: 'NOT_SENT_SHADOW_EVIDENCE', can_send: false, can_trade: false,
    }],
    note: 'DEV EVIDENCE FIXTURE — persisted-card layout only; no delivery is available.',
  },
  optionalAi: {
    mode: 'OPTIONAL_ANNOTATION', state: 'OUTAGE_CIRCUIT_OPEN', stale: false,
    reported_at: '2026-09-07T09:32:00+05:30', execution_authority: 'NONE', can_place_orders: false,
    detail: { queue: { pending: 0, cached: 0, daily_requests: 3, daily_budget: 40, max_pending: 16, circuit_state: 'OPEN' } },
    note: 'DEV EVIDENCE FIXTURE — provider outage leaves deterministic processing independent.',
  },
  sessionDiagnostics: {
    mode: 'OBSERVATION_ONLY', session_count: 5, can_place_orders: false, authorization_effect: 'NONE', findings: [],
    reports: [{
      scope: { policy_id: 'trend_pullback_v1', account_id: 'demo-sparse-activity', mode: 'SHADOW' },
      eligible_sessions: ['2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04', '2026-09-07'],
      scan_health: { expected_sessions: 5, successful_sessions: 5, unavailable_sessions: 0, missing_sessions: 0 },
      activity: { viable_events: 1, fills: 1 },
      findings: [{ code: 'TWO_ELIGIBLE_SESSIONS_NO_VIABLE_CANDIDATES' }, { code: 'FIVE_ELIGIBLE_SESSIONS_SPARSE_FILLS' }],
    }],
  },
};
