import test from 'node:test';
import assert from 'node:assert/strict';
import {
  INSUFFICIENT_EVIDENCE,
  MOMENTUM_INTRADAY_ID,
  PENNY_INTRADAY_ID,
  backtestStrategyKind,
  buildIntradayReplayConfig,
  buildPennyWalkForwardConfig,
  evidenceValue,
  replayEvidence,
  walkForwardFolds,
  walkForwardVerdict,
} from '../src/utils/backtestLab.js';

test('true intraday choices remain distinct from daily proxies', () => {
  assert.equal(backtestStrategyKind({ strategy_id: PENNY_INTRADAY_ID }), 'penny_1m');
  assert.equal(backtestStrategyKind({ strategy_id: MOMENTUM_INTRADAY_ID }), 'momentum_15m');
  assert.equal(backtestStrategyKind({ strategy_id: 'penny_breakout_daily_proxy' }), 'daily_proxy');
  assert.equal(backtestStrategyKind({ strategy_id: 'future_momentum', capabilities: ['true_intraday'], data_requirements: ['15-minute cache'] }), 'momentum_15m');
});

test('intraday request config is typed and restricted to published defaults', () => {
  const strategy = { default_config: {
    initial_bankroll: 2500, tickers: [], minimum_daily_bars: 5,
    oos_folds: 3, variants: ['PEN_BASE'], frozen_server_key: true,
  } };
  assert.deepEqual(buildIntradayReplayConfig(strategy, {
    initialBankroll: '5000', tickers: ' abc, xyz ', minimum_daily_bars: '14',
    oos_folds: '4', variants: ['PEN_BASE'], unregistered: 'ignored',
  }), {
    initial_bankroll: 5000, tickers: ['ABC', 'XYZ'], minimum_daily_bars: 14,
    oos_folds: 4, variants: ['PEN_BASE'], frozen_server_key: true,
  });
});

test('replay evidence preserves provenance and refuses to imply OOS from empty folds', () => {
  const evidence = replayEvidence({ result: {
    coverage: { selected_interval: '15minute', bars: 80 },
    funnel: { MOM_BASE: { evaluations: 20 } },
    oos: { status: 'insufficient_data', required_folds: 3, scored_folds: 2, folds: [{ scored: true }, { scored: false }] },
  } });
  assert.equal(evidence.coverage.selected_interval, '15minute');
  assert.equal(evidence.scoredFolds, 2);
  assert.equal(evidence.oosAvailable, false);
  assert.equal(evidenceValue(null), INSUFFICIENT_EVIDENCE);
  assert.equal(evidenceValue(0), 0);
});

test('walk-forward controls produce typed API config', () => {
  assert.deepEqual(buildPennyWalkForwardConfig({
    initialBankroll: '100000', trainDays: '60', testDays: '20',
    stepDays: '20', anchored: true,
  }), {
    initial_bankroll: 100000, train_days: 60, test_days: 20,
    step_days: 20, anchored: true,
  });
});

test('insufficient folds never render as a positive aggregate verdict', () => {
  const run = { summary: { oos: {
    available: false, n_scored_folds: 2, minimum_scored_folds: 3,
    verdict: 'insufficient_data',
  } } };
  assert.equal(walkForwardVerdict(run), 'Insufficient OOS evidence (2/3 scored folds)');
});

test('missing OOS summary is labelled insufficient evidence', () => {
  assert.equal(walkForwardVerdict({ summary: null }), INSUFFICIENT_EVIDENCE);
});

test('fold rendering reads immutable result evidence and tolerates missing data', () => {
  const folds = [{ train: ['2026-01-01', '2026-02-01'], test: ['2026-02-02', '2026-02-20'] }];
  assert.deepEqual(walkForwardFolds({ result: { folds } }), folds);
  assert.deepEqual(walkForwardFolds({ summary: null }), []);
});
