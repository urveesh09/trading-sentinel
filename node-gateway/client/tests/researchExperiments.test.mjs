import test from 'node:test';
import assert from 'node:assert/strict';
import {
  INSUFFICIENT_DATA,
  buildResearchCenterModel,
  formatCount,
  formatPaperMoney,
  formatRate,
  formatScenarioMoney,
  formatSimulatedMoney,
  normalizeExperiment,
} from '../src/utils/researchExperiments.js';

test('normalizes all three backend count dialects without mixing experiments', () => {
  const model = buildResearchCenterModel({
    momentum: { enabled: true, status: 'ready', registry: { MOM_BASE: {} }, comparison: { variants: [{ variant: 'MOM_BASE', evaluations: 10, accepts: 5, distinct_candidates: 3 }] } },
    penny: { enabled: true, status: 'ready', registry: { PEN_BASE: {} }, comparison: { variants: [{ variant: 'PEN_BASE', evaluations: 20, raw_accepts: 8, distinct_candidates: 2, repeat_accepts: 6 }] } },
    fno: { enabled: true, status: 'ready', registry: { FNO_BASE: {} }, comparison: { variants: [{ variant: 'FNO_BASE', evaluations: 4, accepted_evaluations: 2, distinct_candidates: 1 }] } },
  });
  assert.deepEqual(model.map((experiment) => experiment.id), ['momentum', 'penny', 'fno']);
  assert.deepEqual(model.map((experiment) => experiment.variants[0].rawCandidates), [5, 8, 2]);
  assert.deepEqual(model.map((experiment) => experiment.variants[0].repeats), [2, 6, 1]);
});

test('null metrics remain insufficient data rather than zero', () => {
  assert.equal(formatCount(null), INSUFFICIENT_DATA);
  assert.equal(formatRate(undefined), INSUFFICIENT_DATA);
  assert.equal(formatScenarioMoney(Number.NaN), INSUFFICIENT_DATA);
  const variant = normalizeExperiment('momentum', { registry: { MOM_BASE: {} }, comparison: { variants: [] } }).variants[0];
  assert.equal(variant.evaluations, undefined);
  assert.equal(variant.rawCandidates, undefined);
});

test('repeat inflation and accept conversion are derived without treating repeats as samples', () => {
  const variant = normalizeExperiment('penny', {
    registry: { PEN_BASE: {} },
    comparison: { variants: [{ variant: 'PEN_BASE', evaluations: 100, raw_accepts: 25, distinct_candidates: 10 }] },
  }).variants[0];
  assert.equal(variant.acceptRate, 0.25);
  assert.equal(variant.repeats, 15);
  assert.equal(variant.repeatRate, 0.6);
});

test('post-cost scenarios appear only on F&O and remain explicitly estimated', () => {
  const outcome = { available_samples: 2, gross_pnl: 500, estimated_costs: 75, estimated_net_pnl: 425 };
  const fno = normalizeExperiment('fno', { registry: { FNO_BASE: {} }, comparison: { variants: [{ variant: 'FNO_BASE', estimated_post_cost: outcome }] } });
  const momentum = normalizeExperiment('momentum', { registry: { MOM_BASE: {} }, comparison: { variants: [{ variant: 'MOM_BASE', estimated_post_cost: outcome }] } });
  assert.deepEqual(fno.variants[0].estimatedPostCost, outcome);
  assert.equal(momentum.variants[0].estimatedPostCost, null);
  assert.equal(formatScenarioMoney(425), 'Estimated INR 425.00');
});

test('disabled and unavailable states are preserved', () => {
  assert.equal(normalizeExperiment('penny', { enabled: false, status: 'disabled' }).status, 'disabled');
  const failed = normalizeExperiment('fno', undefined, new Error('offline'));
  assert.equal(failed.status, 'unavailable');
  assert.equal(failed.warning, 'offline');
});

test('momentum virtual outcomes remain explicitly simulated and preserve nulls', () => {
  const variant = normalizeExperiment('momentum', {
    registry: { MOM_BASE: {} },
    comparison: { variants: [{
      variant: 'MOM_BASE', paper_entries: 2, open_trades: 1, closed_trades: 1,
      gross_pnl: 120, costs: 20, net_pnl: 100, net_expectancy: 100,
      profit_factor: null, breakevens: 0, win_rate: 1, avg_r: 0.8, max_drawdown: 0,
      current_drawdown: 0,
    }] },
  }).variants[0];
  assert.equal(variant.simulatedOutcomes.entries, 2);
  assert.equal(variant.simulatedOutcomes.net, 100);
  assert.equal(variant.simulatedOutcomes.profitFactor, undefined);
  assert.equal(variant.simulatedOutcomes.breakevens, 0);
  assert.equal(formatSimulatedMoney(100), 'Simulated INR 100.00');
  assert.equal(formatSimulatedMoney(null), INSUFFICIENT_DATA);
});

test('Penny virtual outcomes preserve mode, costs and null semantics', () => {
  const penny = normalizeExperiment('penny', {
    registry: { PEN_BASE: {} },
    comparison: { variants: [{
      variant: 'PEN_BASE', paper_entries: 3, open_trades: 1, closed_trades: 2,
      winning_trades: 1, losing_trades: 0, breakeven_trades: 1,
      win_rate: 0.5, avg_r: 0.125,
      net_pnl: -1.25, expectancy: -0.625, profit_factor: null, max_drawdown: 1.25,
    }] },
  }).variants[0];
  assert.deepEqual(penny.virtualOutcome, {
    entries: 3, open: 1, closed: 2, wins: 1, losses: 0, breakevens: 1,
    winRate: 0.5, avgR: 0.125, netPnl: -1.25,
    expectancy: -0.625, profitFactor: null, maxDrawdown: 1.25,
  });
  assert.equal(formatPaperMoney(-1.25), 'INR -1.25');
  assert.equal(formatPaperMoney(null), INSUFFICIENT_DATA);
  assert.equal(normalizeExperiment('momentum', {
    registry: { MOM_BASE: {} },
  }).variants[0].virtualOutcome, null);
});
