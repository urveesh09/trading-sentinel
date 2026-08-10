import test from 'node:test';
import assert from 'node:assert/strict';
import {
  READINESS_STATES,
  evidenceLabel,
  normalizePromotionReadiness,
} from '../src/utils/promotionReadiness.js';

test('normalizes research families without inventing missing evidence', () => {
  const model = normalizePromotionReadiness({
    as_of: '2026-08-10T12:00:00+00:00', research_only: true,
    can_place_orders: false, authorization_effect: 'NONE',
    families: [{ strategy: 'MOMENTUM', reconciliation_division: 'momentum_paper',
      source_errors: ['backtest unavailable'], variants: [{
        strategy: 'MOMENTUM', variant: 'MOM_BASE', state: 'COLLECTING',
        research_only: true, can_place_orders: false,
        evidence: { distinct_candidates: 0, closed_trades: null, oos_scored_folds: 2,
          provenance_status: 'VALID', reconciliation_status: 'MATCH' },
        blockers: [{ gate: 'closed_trades', status: 'COLLECTING', observed: null,
          required: '>=20', reason: 'still collecting' }],
        sources: { backtest_run_id: 'run-1', backtest_status: 'SUCCEEDED' },
        source_timestamps: { backtest_completed_at: '2026-08-10T11:00:00+00:00' },
      }] }],
  });
  const item = model.families[0].variants[0];
  assert.equal(item.evidence.distinctCandidates, 0);
  assert.equal(item.evidence.closedTrades, null);
  assert.equal(item.gates[0].observed, null);
  assert.equal(evidenceLabel(item.gates[0].observed), 'Insufficient evidence');
  assert.equal(item.sources.backtest_run_id, 'run-1');
  assert.deepEqual(model.families[0].sourceErrors, ['backtest unavailable']);
});

test('only declared research states survive and none imply execution', () => {
  assert.deepEqual(READINESS_STATES, [
    'COLLECTING', 'INELIGIBLE', 'CANDIDATE_FOR_PAPER_REVIEW',
  ]);
  const model = normalizePromotionReadiness({ families: [{ strategy: 'PENNY', variants: [
    { variant: 'PEN_BASE', state: 'LIVE_READY', research_only: false, can_place_orders: true },
  ] }] });
  const item = model.families[0].variants[0];
  assert.equal(item.state, 'COLLECTING');
  assert.match(item.stateWarning, /readiness state was rejected/);
  assert.equal(item.canPlaceOrders, true);
  assert.equal(item.researchOnly, false);
});

test('malformed and failed payloads degrade to an empty evidence model', () => {
  const model = normalizePromotionReadiness(null, new Error('offline'));
  assert.deepEqual(model.families, []);
  assert.deepEqual(model.sourceErrors, ['offline']);
  assert.equal(model.canPlaceOrders, false);
  assert.equal(evidenceLabel({ status: 'MATCH' }), '{"status":"MATCH"}');
});

test('missing safety flags fail closed instead of receiving safe defaults', () => {
  const model = normalizePromotionReadiness({
    families: [{ strategy: 'FNO', variants: [{ variant: 'FNO_BASE', state: 'COLLECTING' }] }],
  });
  assert.equal(model.researchOnly, false);
  assert.equal(model.canPlaceOrders, false);
  assert.equal(model.authorizationEffect, null);
  assert.equal(model.families[0].variants[0].researchOnly, false);
});
