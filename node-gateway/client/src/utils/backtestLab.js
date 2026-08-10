export const PENNY_WALK_FORWARD_ID = 'penny_breakout_daily_proxy_walk_forward';
export const PENNY_INTRADAY_ID = 'penny_breakout_intraday_1m_replay';
export const MOMENTUM_INTRADAY_ID = 'momentum_intraday_15m_replay';
export const INSUFFICIENT_EVIDENCE = 'Insufficient evidence';

const numberOrDefault = (value, fallback) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

export function backtestStrategyKind(strategy) {
  const id = strategy?.strategy_id || '';
  const capabilities = Array.isArray(strategy?.capabilities) ? strategy.capabilities : [];
  const requirements = Array.isArray(strategy?.data_requirements) ? strategy.data_requirements.join(' ').toLowerCase() : '';
  if (id === PENNY_INTRADAY_ID || (id.includes('penny') && (capabilities.includes('true_intraday') || requirements.includes('1-minute') || requirements.includes('1m')))) return 'penny_1m';
  if (id === MOMENTUM_INTRADAY_ID || (id.includes('momentum') && (capabilities.includes('true_intraday') || requirements.includes('15-minute') || requirements.includes('15m')))) return 'momentum_15m';
  if (id.includes('daily_proxy')) return 'daily_proxy';
  return 'other';
}

export function isTrueIntradayStrategy(strategy) {
  return ['penny_1m', 'momentum_15m'].includes(backtestStrategyKind(strategy));
}

export function buildIntradayReplayConfig(strategy, controls = {}) {
  const defaults = strategy?.default_config && typeof strategy.default_config === 'object'
    ? strategy.default_config : {};
  const config = { ...defaults };
  if ('initial_bankroll' in defaults) config.initial_bankroll = numberOrDefault(controls.initialBankroll, defaults.initial_bankroll);
  if ('ticker' in defaults) config.ticker = String(controls.tickers || defaults.ticker || '').split(',')[0].trim().toUpperCase();
  if ('tickers' in defaults) config.tickers = String(controls.tickers || '').split(',').map((item) => item.trim().toUpperCase()).filter(Boolean);
  if (Array.isArray(defaults.variants) && Array.isArray(controls.variants) && controls.variants.length) config.variants = [...controls.variants];
  for (const key of [
    'minimum_daily_bars', 'daily_lookback_rows', 'min_candles', 'oos_folds',
    'train_days', 'test_days', 'step_days', 'bankroll', 'momentum_pool',
    'normal_volume_threshold', 'lunchtime_volume_threshold',
  ]) {
    if (key in defaults) config[key] = numberOrDefault(controls[key], defaults[key]);
  }
  for (const key of ['regime', 'market_regime', 'lunchtime_start', 'lunchtime_end']) {
    if (key in defaults && controls[key]) config[key] = controls[key];
  }
  for (const key of ['walk_forward', 'anchored']) {
    if (key in defaults) config[key] = controls[key] === undefined ? Boolean(defaults[key]) : Boolean(controls[key]);
  }
  return config;
}

export function replayEvidence(run) {
  const result = run?.result && typeof run.result === 'object' ? run.result : {};
  const coverage = result.coverage || result.diagnostics || run?.dataset?.coverage || run?.dataset || {};
  const funnel = result.funnel || {};
  const oos = result.oos || run?.summary?.oos || {};
  const folds = Array.isArray(oos.folds) ? oos.folds : Array.isArray(result.folds) ? result.folds : [];
  const scoredFolds = oos.scored_folds ?? oos.n_scored_folds ?? folds.filter((fold) => fold.scored !== false).length;
  const requiredFolds = oos.required_folds ?? oos.minimum_scored_folds ?? 3;
  const oosAvailable = oos.status === 'scored' || oos.available === true || scoredFolds >= requiredFolds;
  return { coverage, funnel, oos, folds, scoredFolds, requiredFolds, oosAvailable };
}

export function evidenceValue(value) {
  return value === null || value === undefined || value === '' ? INSUFFICIENT_EVIDENCE : value;
}

export function buildPennyWalkForwardConfig({
  initialBankroll, trainDays, testDays, stepDays, anchored,
}) {
  return {
    initial_bankroll: Number(initialBankroll),
    train_days: Number(trainDays),
    test_days: Number(testDays),
    step_days: Number(stepDays),
    anchored: Boolean(anchored),
  };
}

export function walkForwardFolds(run) {
  return Array.isArray(run?.result?.folds) ? run.result.folds : [];
}

export function walkForwardVerdict(run) {
  const oos = run?.summary?.oos;
  if (!oos) return INSUFFICIENT_EVIDENCE;
  if (!oos.available) {
    return `Insufficient OOS evidence (${oos.n_scored_folds ?? 0}/${oos.minimum_scored_folds ?? 3} scored folds)`;
  }
  return String(oos.verdict || INSUFFICIENT_EVIDENCE).replaceAll('_', ' ');
}
