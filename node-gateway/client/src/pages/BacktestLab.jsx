import React, { useEffect, useMemo, useState } from 'react';
import useSWR from 'swr';
import { fetcher, postClient } from '../api/client';
import {
  INSUFFICIENT_EVIDENCE,
  backtestStrategyKind,
  buildIntradayReplayConfig,
  evidenceValue,
  isTrueIntradayStrategy,
  PENNY_WALK_FORWARD_ID,
  replayEvidence,
  buildPennyWalkForwardConfig,
  walkForwardFolds,
  walkForwardVerdict,
} from '../utils/backtestLab';

const money = (value) => value == null ? INSUFFICIENT_EVIDENCE : `INR ${Number(value).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
const metric = (value, suffix = '') => value == null ? INSUFFICIENT_EVIDENCE : `${Number(value).toFixed(2)}${suffix}`;

const strategyPrefix = (strategy) => ({
  penny_1m: '[TRUE 1m]', momentum_15m: '[TRUE 15m]', daily_proxy: '[DAILY PROXY]', other: '[RESEARCH]',
}[backtestStrategyKind(strategy)]);

function ReplayEvidence({ run }) {
  const evidence = replayEvidence(run);
  const coverageEntries = Object.entries(evidence.coverage || {}).filter(([, value]) => typeof value !== 'object');
  const coverageDetails = Object.fromEntries(Object.entries(evidence.coverage || {}).filter(([, value]) => typeof value === 'object' && value !== null));
  const funnelEntries = Object.entries(evidence.funnel || {});
  const variantMetrics = Array.isArray(run?.result?.variants) ? run.result.variants : (run?.summary?.variant_summaries || []);
  return <div className="mt-4 space-y-4 rounded border border-violet-800 bg-violet-950/20 p-4">
    <div><h3 className="font-semibold text-violet-200">True-intraday replay evidence</h3><p className="mt-1 text-xs text-slate-400">Historical cache evidence only. These are simulated outcomes, never live fills or profit claims.</p></div>
    <div><h4 className="text-xs font-bold uppercase tracking-wide text-slate-400">Provenance and coverage</h4>{coverageEntries.length ? <dl className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">{coverageEntries.map(([key, value]) => <div key={key} className="rounded bg-slate-950 p-2"><dt className="text-[10px] uppercase text-slate-500">{key.replaceAll('_', ' ')}</dt><dd className="mt-1 break-all font-mono text-xs">{String(evidenceValue(value))}</dd></div>)}</dl> : <p className="mt-2 text-sm text-amber-300">{INSUFFICIENT_EVIDENCE}: no coverage snapshot was returned.</p>}{Object.keys(coverageDetails).length > 0 && <pre className="mt-2 max-h-48 overflow-auto rounded bg-slate-950 p-2 text-[11px] text-slate-300">{JSON.stringify(coverageDetails, null, 2)}</pre>}</div>
    <div><h4 className="text-xs font-bold uppercase tracking-wide text-slate-400">Evaluation funnel</h4>{funnelEntries.length ? <div className="mt-2 overflow-x-auto"><table className="w-full text-left text-xs"><thead className="text-slate-500"><tr><th className="p-2">Variant</th><th className="p-2">Evaluations</th><th className="p-2">Accepted prefixes</th><th className="p-2">Distinct candidates</th><th className="p-2">Top blockers</th></tr></thead><tbody>{funnelEntries.map(([name, row]) => <tr key={name} className="border-t border-slate-800"><td className="p-2 font-mono">{name}</td><td className="p-2">{evidenceValue(row?.evaluations)}</td><td className="p-2">{evidenceValue(row?.accepted_prefixes ?? row?.raw_accepts)}</td><td className="p-2">{evidenceValue(row?.distinct_candidates)}</td><td className="p-2 font-mono">{row?.rejects ? JSON.stringify(row.rejects) : INSUFFICIENT_EVIDENCE}</td></tr>)}</tbody></table></div> : <p className="mt-2 text-sm text-amber-300">{INSUFFICIENT_EVIDENCE}: no evaluator funnel was returned.</p>}</div>
    {!!variantMetrics.length && <div><h4 className="text-xs font-bold uppercase tracking-wide text-slate-400">Variant outcome metrics</h4><div className="mt-2 overflow-x-auto"><table className="w-full text-left text-xs"><thead className="text-slate-500"><tr><th className="p-2">Variant</th><th className="p-2">Entries</th><th className="p-2">Closed</th><th className="p-2">Net</th><th className="p-2">PF</th><th className="p-2">Avg R</th><th className="p-2">Drawdown</th></tr></thead><tbody>{variantMetrics.map((row, index) => <tr key={row.variant || index} className="border-t border-slate-800"><td className="p-2 font-mono">{row.variant || 'Aggregate replay'}</td><td className="p-2">{evidenceValue(row.paper_entries ?? row.entries)}</td><td className="p-2">{evidenceValue(row.closed_trades)}</td><td className="p-2">{evidenceValue(row.net_pnl)}</td><td className="p-2">{evidenceValue(row.profit_factor)}</td><td className="p-2">{evidenceValue(row.avg_r)}</td><td className="p-2">{evidenceValue(row.max_drawdown)}</td></tr>)}</tbody></table></div></div>}
    <div><h4 className="text-xs font-bold uppercase tracking-wide text-slate-400">Chronological OOS folds</h4><p className={`mt-1 text-sm ${evidence.oosAvailable ? 'text-emerald-300' : 'text-amber-300'}`}>{evidence.oosAvailable ? `${evidence.scoredFolds} genuinely scored fold(s)` : `${INSUFFICIENT_EVIDENCE}: ${evidence.scoredFolds}/${evidence.requiredFolds} genuinely scored folds`}</p>{evidence.folds.length > 0 && <div className="mt-2 overflow-x-auto"><table className="w-full text-left text-xs"><thead className="text-slate-500"><tr><th className="p-2">Train</th><th className="p-2">Test</th><th className="p-2">Train selection</th><th className="p-2">Scored</th><th className="p-2">OOS evidence</th></tr></thead><tbody>{evidence.folds.map((fold, index) => <tr key={`${fold.fold ?? index}`} className="border-t border-slate-800"><td className="p-2 font-mono">{fold.train?.join(' to ') || [fold.train_start, fold.train_end].filter(Boolean).join(' to ') || INSUFFICIENT_EVIDENCE}</td><td className="p-2 font-mono">{fold.test?.join(' to ') || [fold.test_start, fold.test_end].filter(Boolean).join(' to ') || INSUFFICIENT_EVIDENCE}</td><td className="p-2">{fold.selected_variant || fold.chosen_config || INSUFFICIENT_EVIDENCE}</td><td className="p-2">{fold.scored === false ? 'No' : 'Yes'}</td><td className="p-2 font-mono">{fold.oos_expectancy ?? (fold.oos_scores ? JSON.stringify(fold.oos_scores) : fold.reason || INSUFFICIENT_EVIDENCE)}</td></tr>)}</tbody></table></div>}</div>
  </div>;
}

function IntradayControls({ strategy, values, onChange }) {
  const defaults = strategy?.default_config || {};
  const kind = backtestStrategyKind(strategy);
  const regimeOptions = strategy?.parameter_schema?.regime?.enum || [defaults.regime].filter(Boolean);
  const variantOptions = strategy?.parameter_schema?.variants?.items?.enum || defaults.variants || [];
  const selectedVariants = Array.isArray(values.variants) ? values.variants : (defaults.variants || []);
  const numeric = [
    ['minimum_daily_bars', 'Minimum daily bars', 5, 1], ['train_days', 'Train days', 1, 1],
    ['test_days', 'Test days', 1, 1], ['step_days', 'Step days', 1, 1],
    ['bankroll', 'Simulated bankroll', 1, 1], ['momentum_pool', 'Momentum pool', 1, 1],
    ['min_candles', 'Minimum 15m candles', 2, 1], ['daily_lookback_rows', 'Prior daily rows', 14, 1],
    ['normal_volume_threshold', 'Normal volume threshold', 0.01, 0.01],
    ['lunchtime_volume_threshold', 'Lunch volume threshold', 0.01, 0.01],
    ['oos_folds', 'Required OOS folds', 3, 1],
  ].filter(([key]) => key in defaults);
  return <div className="space-y-3 rounded border border-violet-700/60 bg-violet-950/25 p-3">
    <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-bold text-violet-200">{kind === 'penny_1m' ? 'True one-minute Penny replay' : 'True 15-minute Momentum replay'}</p><span className="rounded border border-violet-600 px-2 py-1 text-[10px] font-bold text-violet-200">CACHE REPLAY - NO ORDERS</span></div>
    <p className="text-xs text-slate-400">Distinct from every daily proxy. Results require explicit interval provenance and sufficient historical coverage.</p>
    {('tickers' in defaults || 'ticker' in defaults) && <label className="block text-xs text-slate-300">Ticker filter (comma-separated; blank uses available cache scope)<input value={values.tickers ?? ''} onChange={(event) => onChange('tickers', event.target.value)} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 p-2 uppercase" placeholder="RELIANCE, TCS" /></label>}
    {!!numeric.length && <div className="grid grid-cols-2 gap-2">{numeric.map(([key, label, min, step]) => <label key={key} className="text-xs text-slate-300">{label}<input aria-label={label} type="number" min={min} step={step} value={values[key] ?? defaults[key]} onChange={(event) => onChange(key, event.target.value)} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 p-2" /></label>)}</div>}
    {'regime' in defaults && <label className="block text-xs text-slate-300">Historical regime assumption<select value={values.regime ?? defaults.regime} onChange={(event) => onChange('regime', event.target.value)} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 p-2">{regimeOptions.map((option) => <option key={option}>{option}</option>)}</select></label>}
    {'market_regime' in defaults && <label className="block text-xs text-slate-300">Legacy market regime<input value={values.market_regime ?? defaults.market_regime} onChange={(event) => onChange('market_regime', event.target.value)} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 p-2" /></label>}
    {('lunchtime_start' in defaults || 'lunchtime_end' in defaults) && <div className="grid grid-cols-2 gap-2">{[['lunchtime_start', 'Lunch window start'], ['lunchtime_end', 'Lunch window end']].filter(([key]) => key in defaults).map(([key, label]) => <label key={key} className="text-xs text-slate-300">{label}<input type="time" value={values[key] ?? defaults[key]} onChange={(event) => onChange(key, event.target.value)} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 p-2" /></label>)}</div>}
    {['walk_forward', 'anchored'].filter((key) => key in defaults).map((key) => <label key={key} className="flex items-center gap-2 text-xs text-slate-300"><input type="checkbox" checked={Boolean(values[key] ?? defaults[key])} onChange={(event) => onChange(key, event.target.checked)} />{key === 'walk_forward' ? 'Run chronological walk-forward evidence' : 'Anchored expanding train window'}</label>)}
    {!!variantOptions.length && <div><p className="text-xs text-slate-400">Replay variants</p><div className="mt-1 flex flex-wrap gap-2">{variantOptions.map((variant) => <label key={variant} className="flex items-center gap-1 rounded bg-slate-950 px-2 py-1 text-xs"><input type="checkbox" checked={selectedVariants.includes(variant)} onChange={(event) => { const next = event.target.checked ? [...selectedVariants, variant] : selectedVariants.filter((item) => item !== variant); if (next.length) onChange('variants', next); }} />{variant}</label>)}</div></div>}
    <p className="text-xs text-amber-300">OOS metrics remain insufficient evidence until the backend reports the required genuinely scored folds.</p>
  </div>;
}

function StatusPill({ status }) {
  const tone = status === 'SUCCEEDED' ? 'bg-emerald-950 text-emerald-300 border-emerald-700'
    : status === 'FAILED' || status === 'UNAVAILABLE' ? 'bg-red-950 text-red-300 border-red-700'
      : 'bg-amber-950 text-amber-300 border-amber-700';
  return <span className={`rounded-full border px-2 py-1 text-xs font-bold ${tone}`}>{status}</span>;
}

export default function BacktestLab({ navigateToDashboard }) {
  const { data: strategyData } = useSWR('/api/proxy/backtests/strategies', fetcher);
  const { data: runData, mutate: refreshRuns } = useSWR('/api/proxy/backtests/runs?limit=50', fetcher, { refreshInterval: 3000 });
  const strategies = strategyData?.strategies || [];
  const runs = runData?.runs || [];
  const available = strategies.filter((item) => item.available);
  const [strategyId, setStrategyId] = useState('');
  const [startDate, setStartDate] = useState('2025-01-01');
  const [endDate, setEndDate] = useState(new Date().toISOString().slice(0, 10));
  const [bankroll, setBankroll] = useState('100000');
  const [ticker, setTicker] = useState('RELIANCE');
  const [preset, setPreset] = useState('baseline');
  const [trainDays, setTrainDays] = useState('60');
  const [testDays, setTestDays] = useState('20');
  const [stepDays, setStepDays] = useState('20');
  const [anchored, setAnchored] = useState(true);
  const [replayControls, setReplayControls] = useState({});
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!strategyId && available.length) {
      setStrategyId(available[0].strategy_id);
      setBankroll(String(available[0].default_config.initial_bankroll));
    }
  }, [strategyId, available]);

  const selectedStrategy = useMemo(
    () => strategies.find((item) => item.strategy_id === strategyId),
    [strategies, strategyId],
  );
  const activeId = selectedRunId || runs[0]?.run_id;
  const { data: detailData } = useSWR(activeId ? `/api/proxy/backtests/runs/${activeId}` : null, fetcher, {
    refreshInterval: (data) => ['QUEUED', 'RUNNING'].includes(data?.run?.status) ? 1500 : 0,
  });
  const activeRun = detailData?.run || runs.find((item) => item.run_id === activeId);

  const chooseStrategy = (id) => {
    const item = strategies.find((entry) => entry.strategy_id === id);
    setStrategyId(id);
    if (item?.default_config?.initial_bankroll) setBankroll(String(item.default_config.initial_bankroll));
    if (id === PENNY_WALK_FORWARD_ID && item?.default_config) {
      setTrainDays(String(item.default_config.train_days));
      setTestDays(String(item.default_config.test_days));
      setStepDays(String(item.default_config.step_days));
      setAnchored(Boolean(item.default_config.anchored));
    }
    if (isTrueIntradayStrategy(item)) {
      const defaults = item.default_config || {};
      setReplayControls(Object.fromEntries(Object.entries(defaults).map(([key, value]) => [
        key,
        key === 'tickers' ? (Array.isArray(value) ? value.join(', ') : '')
          : typeof value === 'number' ? String(value) : value,
      ])));
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    setSubmitting(true); setError('');
    const config = isTrueIntradayStrategy(selectedStrategy) ? {} : { initial_bankroll: Number(bankroll) };
    if (strategyId === 'swing_regime_daily') config.ticker = ticker.trim().toUpperCase();
    if (strategyId === 'penny_breakout_daily_proxy') config.preset = preset;
    if (strategyId === PENNY_WALK_FORWARD_ID) Object.assign(config, buildPennyWalkForwardConfig({
      initialBankroll: bankroll, trainDays, testDays, stepDays, anchored,
    }));
    if (isTrueIntradayStrategy(selectedStrategy)) Object.assign(config, buildIntradayReplayConfig(selectedStrategy, {
      ...replayControls, initialBankroll: bankroll,
    }));
    try {
      const created = await postClient('/api/proxy/backtests/runs', {
        strategy_id: strategyId, start_date: startDate, end_date: endDate, config,
        assumptions: selectedStrategy?.default_assumptions || {},
      });
      setSelectedRunId(created.run_id);
      await refreshRuns();
    } catch (err) {
      setError(err.info?.detail || err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-900/90 px-5 py-4">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.22em] text-cyan-400">Research only - no broker orders</p>
            <h1 className="text-2xl font-bold">Backtest Lab</h1>
          </div>
          <button onClick={navigateToDashboard} className="rounded border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800">Back to dashboard</button>
        </div>
      </header>

      <main className="mx-auto grid max-w-7xl gap-6 p-5 xl:grid-cols-[380px_1fr]">
        <section className="space-y-5">
          <div className="rounded-lg border border-amber-700/60 bg-amber-950/30 p-4 text-sm text-amber-100">
            Results are experiments, not forecasts. This Lab has no order-placement capability and cannot enable live trading.
          </div>
          <form onSubmit={submit} className="space-y-4 rounded-lg border border-slate-800 bg-slate-900 p-5">
            <h2 className="font-semibold">New immutable experiment</h2>
            <label className="block text-sm text-slate-300">Strategy
              <select value={strategyId} onChange={(e) => chooseStrategy(e.target.value)} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 p-2">
                {strategies.map((item) => <option key={item.strategy_id} value={item.strategy_id} disabled={!item.available}>{strategyPrefix(item)} {item.name}{item.available ? '' : ' -- unavailable'}</option>)}
              </select>
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="text-sm text-slate-300">Start<input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 p-2" required /></label>
              <label className="text-sm text-slate-300">End<input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 p-2" required /></label>
            </div>
            {(!isTrueIntradayStrategy(selectedStrategy) || 'initial_bankroll' in (selectedStrategy?.default_config || {})) && <label className="block text-sm text-slate-300">Research bankroll<input type="number" min="1" value={bankroll} onChange={(e) => setBankroll(e.target.value)} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 p-2" required /></label>}
            {strategyId === 'swing_regime_daily' && <label className="block text-sm text-slate-300">Ticker<input value={ticker} onChange={(e) => setTicker(e.target.value)} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 p-2 uppercase" required /></label>}
            {strategyId === 'penny_breakout_daily_proxy' && <label className="block text-sm text-slate-300">Preset<select value={preset} onChange={(e) => setPreset(e.target.value)} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 p-2"><option>baseline</option><option>relaxed</option><option>phase3</option></select></label>}
            {strategyId === PENNY_WALK_FORWARD_ID && <div className="space-y-3 rounded border border-amber-700/60 bg-amber-950/30 p-3">
              <p className="text-sm font-bold text-amber-200">Daily proxy and zero-fee model — never live-equivalent</p>
              <p className="text-xs text-amber-300">Each fold selects baseline, relaxed, or phase3 using TRAIN only, then scores that one selection on a strictly later TEST window.</p>
              <div className="grid grid-cols-3 gap-2">
                <label className="text-xs text-slate-300">Train days<input aria-label="Train days" type="number" min="1" value={trainDays} onChange={(e) => setTrainDays(e.target.value)} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 p-2" /></label>
                <label className="text-xs text-slate-300">Test days<input aria-label="Test days" type="number" min="1" value={testDays} onChange={(e) => setTestDays(e.target.value)} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 p-2" /></label>
                <label className="text-xs text-slate-300">Step days<input aria-label="Step days" type="number" min="1" value={stepDays} onChange={(e) => setStepDays(e.target.value)} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 p-2" /></label>
              </div>
              <label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" checked={anchored} onChange={(e) => setAnchored(e.target.checked)} />Anchored expanding train window</label>
              <p className="text-xs text-slate-400">Step must be at least the test length. At least three scored folds are required before aggregate edge metrics appear.</p>
            </div>}
            {isTrueIntradayStrategy(selectedStrategy) && <IntradayControls strategy={selectedStrategy} values={replayControls} onChange={(key, value) => setReplayControls((current) => ({ ...current, [key]: value }))} />}
            {selectedStrategy && <div className="space-y-2 rounded bg-slate-950 p-3 text-xs text-slate-400">
              <p>{selectedStrategy.description}</p>
              <p><span className="text-slate-200">Mode:</span> {backtestStrategyKind(selectedStrategy).replaceAll('_', ' ')}</p>
              <p><span className="text-slate-200">Data:</span> {(selectedStrategy.data_requirements || []).join('; ') || 'Not published'}</p>
              <p><span className="text-slate-200">Assumptions:</span> {JSON.stringify(selectedStrategy.default_assumptions)}</p>
              {(selectedStrategy.limitations || []).map((item) => <p key={item} className="text-amber-300">- {item}</p>)}
            </div>}
            {error && <p className="text-sm text-red-400">{error}</p>}
            <button disabled={submitting || !selectedStrategy?.available} className="w-full rounded bg-cyan-700 px-4 py-2 font-bold hover:bg-cyan-600 disabled:cursor-not-allowed disabled:opacity-40">{submitting ? 'Queuing...' : 'Run research backtest'}</button>
          </form>
        </section>

        <section className="space-y-6">
          <div className="rounded-lg border border-slate-800 bg-slate-900 p-5">
            <div className="mb-4 flex items-center justify-between"><h2 className="font-semibold">Run evidence</h2>{activeRun && <StatusPill status={activeRun.status} />}</div>
            {!activeRun ? <p className="text-slate-500">No experiments yet.</p> : <>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {[['Net P&L', money(activeRun.summary?.net_pnl)], ['Net return', metric(activeRun.summary?.net_return_pct, '%')], ['Max drawdown', metric(activeRun.summary?.max_drawdown_pct, '%')], ['OOS', activeRun.summary?.oos?.available ? 'Available' : INSUFFICIENT_EVIDENCE], ['Trades', activeRun.summary?.trade_count ?? INSUFFICIENT_EVIDENCE], ['Win rate', metric(activeRun.summary?.win_rate_pct, '%')], ['Profit factor', metric(activeRun.summary?.profit_factor)], ['Average R', metric(activeRun.summary?.avg_r)]].map(([label, value]) => <div key={label} className="rounded border border-slate-800 bg-slate-950 p-3"><p className="text-xs uppercase tracking-wide text-slate-500">{label}</p><p className="mt-1 font-mono text-lg">{value}</p></div>)}
              </div>
              {activeRun.error && <p className="mt-4 rounded bg-red-950/50 p-3 text-sm text-red-300">{activeRun.error}</p>}
              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                <div><h3 className="mb-2 text-sm font-semibold text-slate-300">Frozen assumptions</h3><pre className="overflow-x-auto rounded bg-slate-950 p-3 text-xs text-cyan-200">{JSON.stringify(activeRun.assumptions, null, 2)}</pre></div>
                <div><h3 className="mb-2 text-sm font-semibold text-slate-300">Dataset evidence</h3><div className="rounded bg-slate-950 p-3 text-xs text-slate-300"><p className="break-all font-mono">{activeRun.dataset_fingerprint || 'Pending fingerprint'}</p><p className="mt-2">{activeRun.dataset ? JSON.stringify(activeRun.dataset) : 'Dataset snapshot pending.'}</p></div></div>
              </div>
              {!!activeRun.warnings?.length && <div className="mt-4 rounded border border-amber-800 bg-amber-950/30 p-3"><h3 className="text-sm font-semibold text-amber-200">Limitations and warnings</h3>{activeRun.warnings.map((warning) => <p key={warning} className="mt-1 text-sm text-amber-300">- {warning}</p>)}</div>}
              {isTrueIntradayStrategy(strategies.find((item) => item.strategy_id === activeRun.strategy_id) || { strategy_id: activeRun.strategy_id }) && <ReplayEvidence run={activeRun} />}
              {activeRun.strategy_id === PENNY_WALK_FORWARD_ID && <div className="mt-4 rounded border border-cyan-900 bg-slate-950 p-4">
                <h3 className="font-semibold text-cyan-200">Chronological walk-forward evidence</h3>
                <p className="mt-1 text-sm text-slate-300">Verdict: <span className="font-semibold">{walkForwardVerdict(activeRun)}</span></p>
                <p className="mt-1 text-xs text-amber-300">Daily-bar proxy, zero fees and zero slippage. This is not evidence of live one-minute execution performance.</p>
                <div className="mt-3 grid gap-2 sm:grid-cols-3">
                  {[['Overfit gap', activeRun.summary?.oos?.overfit_gap], ['Selection stability', activeRun.summary?.oos?.selection_stability], ['Positive OOS fraction', activeRun.summary?.oos?.positive_oos_fraction]].map(([label, value]) => <div key={label} className="rounded border border-slate-800 p-2"><p className="text-xs text-slate-500">{label}</p><p className="font-mono">{value == null ? INSUFFICIENT_EVIDENCE : Number(value).toFixed(4)}</p></div>)}
                </div>
                <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-xs"><thead className="text-slate-500"><tr><th className="p-2">Train</th><th className="p-2">Test</th><th className="p-2">Selected on train</th><th className="p-2">Train scores</th><th className="p-2">OOS scores</th></tr></thead><tbody>{walkForwardFolds(activeRun).map((fold, index) => <tr key={`${fold.test?.[0]}-${index}`} className="border-t border-slate-800"><td className="p-2 font-mono">{fold.train?.join(' → ')}</td><td className="p-2 font-mono">{fold.test?.join(' → ')}</td><td className="p-2">{fold.chosen_config || 'No train winner'}</td><td className="p-2 font-mono">{JSON.stringify(fold.train_scores)}</td><td className="p-2 font-mono">{fold.oos_scores ? JSON.stringify(fold.oos_scores) : INSUFFICIENT_EVIDENCE}</td></tr>)}</tbody></table></div>
              </div>}
            </>}
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900 p-5">
            <h2 className="mb-4 font-semibold">Run history</h2>
            <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-slate-500"><tr><th className="p-2">Created</th><th className="p-2">Strategy</th><th className="p-2">Status</th><th className="p-2">Net P&L</th><th className="p-2">Trades</th></tr></thead><tbody>{runs.map((run) => <tr key={run.run_id} onClick={() => setSelectedRunId(run.run_id)} className="cursor-pointer border-t border-slate-800 hover:bg-slate-800/60"><td className="p-2">{new Date(run.created_at).toLocaleString()}</td><td className="p-2">{run.strategy_id}</td><td className="p-2"><StatusPill status={run.status} /></td><td className="p-2 font-mono">{money(run.summary?.net_pnl)}</td><td className="p-2">{run.summary?.trade_count ?? '--'}</td></tr>)}</tbody></table></div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900 p-5"><h2 className="mb-3 font-semibold">Registered but unavailable</h2>{strategies.filter((item) => !item.available).map((item) => <div key={item.strategy_id} className="mb-2 rounded bg-slate-950 p-3"><p className="font-medium">{item.name}</p><p className="text-sm text-red-300">{item.availability_reason}</p></div>)}</div>
        </section>
      </main>
    </div>
  );
}
