import React from 'react';
import { AlertTriangle, ArrowLeft, FlaskConical, ShieldCheck } from 'lucide-react';
import { useResearchExperiments } from '../hooks/useResearchExperiments';
import {
  INSUFFICIENT_DATA,
  buildResearchCenterModel,
  formatCount,
  formatPaperMoney,
  formatRate,
  formatScenarioMoney,
  formatSimulatedMoney,
} from '../utils/researchExperiments';
import { evidenceLabel, normalizePromotionReadiness } from '../utils/promotionReadiness';

const readinessStyle = {
  COLLECTING: 'border-blue-700 bg-blue-950 text-blue-200',
  INELIGIBLE: 'border-red-700 bg-red-950 text-red-200',
  CANDIDATE_FOR_PAPER_REVIEW: 'border-violet-700 bg-violet-950 text-violet-200',
};

function ReadinessVariant({ item }) {
  const evidence = item.evidence;
  const timestamps = Object.entries(item.timestamps);
  return (
    <article className="rounded-lg border border-gray-800 bg-gray-900/80 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div><h4 className="font-mono font-bold text-white">{item.variant}</h4><p className="mt-1 text-xs text-gray-500">{item.explanation || 'Research evidence assessment only.'}</p></div>
        <span className={`rounded-full border px-2.5 py-1 text-[10px] font-bold ${readinessStyle[item.state]}`}>{item.state.replaceAll('_', ' ')}</span>
      </div>
      {(item.canPlaceOrders || !item.researchOnly || item.stateWarning) && <div className="mt-3 rounded border border-red-700 bg-red-950/40 p-2 text-xs font-bold text-red-200">Contract integrity warning: {item.stateWarning || 'backend research safety flags are invalid'}; no authorization is inferred.</div>}
      <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Metric label="Distinct candidates" value={evidenceLabel(evidence.distinctCandidates)} />
        <Metric label="Closed paper trades" value={evidenceLabel(evidence.closedTrades)} />
        <Metric label="Net expectancy after costs" value={evidenceLabel(evidence.netExpectancy)} />
        <Metric label="Profit factor" value={evidenceLabel(evidence.profitFactor)} />
        <Metric label="Max drawdown" value={evidenceLabel(evidence.maxDrawdown)} />
        <Metric label="Repeat inflation" value={evidence.repeatInflation == null ? 'Insufficient evidence' : formatRate(evidence.repeatInflation)} />
      </dl>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <div className="rounded border border-gray-800 bg-gray-950 p-3"><p className="text-[10px] uppercase text-gray-500">Chronological OOS</p><p className="mt-1 text-sm font-bold">{evidenceLabel(evidence.oosScoredFolds)} scored folds</p></div>
        <div className="rounded border border-gray-800 bg-gray-950 p-3"><p className="text-[10px] uppercase text-gray-500">Data provenance</p><p className="mt-1 text-sm font-bold">{evidenceLabel(evidence.provenanceStatus)}</p></div>
        <div className="rounded border border-gray-800 bg-gray-950 p-3"><p className="text-[10px] uppercase text-gray-500">Ledger reconciliation</p><p className="mt-1 text-sm font-bold">{evidenceLabel(evidence.reconciliationStatus)}</p></div>
      </div>
      <div className="mt-4 border-t border-gray-800 pt-3">
        <h5 className="text-[10px] font-bold uppercase tracking-wide text-gray-500">Blocking or collecting gates</h5>
        {item.gates.length ? <div className="mt-2 overflow-x-auto"><table className="w-full text-left text-xs"><thead className="text-gray-500"><tr><th className="p-2">Gate</th><th className="p-2">Status</th><th className="p-2">Observed</th><th className="p-2">Required</th><th className="p-2">Reason</th></tr></thead><tbody>{item.gates.map((gate, index) => <tr key={`${gate.gate}-${index}`} className="border-t border-gray-800"><td className="p-2 font-mono">{gate.gate}</td><td className="p-2">{gate.status}</td><td className="p-2 font-mono">{evidenceLabel(gate.observed)}</td><td className="p-2 font-mono">{evidenceLabel(gate.required)}</td><td className="p-2 text-gray-400">{gate.reason}</td></tr>)}</tbody></table></div> : <p className="mt-2 text-xs text-violet-200">Static gates are satisfied for human paper review only.</p>}
      </div>
      <div className="mt-3 text-[11px] text-gray-500"><span>Replay: {evidenceLabel(item.sources.backtest_run_id)} ({evidenceLabel(item.sources.backtest_status)})</span>{timestamps.map(([key, value]) => <span key={key} className="ml-3">{key.replaceAll('_', ' ')}: {evidenceLabel(value)}</span>)}</div>
    </article>
  );
}

function ReadinessSection({ model }) {
  const contractUnsafe = !model.researchOnly || model.canPlaceOrders || model.authorizationEffect !== 'NONE';
  return (
    <section className="rounded-xl border-2 border-amber-700 bg-amber-950/10 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-xl font-bold text-white">Paper-review readiness</h2><p className="mt-1 text-sm text-gray-400">Static research gates across shadow outcomes, chronological replay, provenance, and ledger reconciliation.</p></div><span className="rounded border border-red-600 bg-red-950 px-3 py-2 text-xs font-black text-red-100">NO LIVE AUTHORIZATION</span></div>
      <div className="mt-3 rounded border border-red-800 bg-red-950/30 p-3 text-sm font-semibold text-red-100">These states cannot authorize live trading, order placement, sizing, configuration changes, or deployment. A paper-review candidate is evidence for human review only.</div>
      {contractUnsafe && <div className="mt-3 rounded border-2 border-red-500 bg-red-950 p-3 text-sm font-black text-red-100">CONTRACT INTEGRITY WARNING: research-only safety flags are missing or invalid. All evidence is treated as non-authorizing.</div>}
      {(model.warning || model.sourceErrors.length) && <div className="mt-3 space-y-1 rounded border border-amber-800 bg-amber-950/30 p-3 text-xs text-amber-200">{model.warning && <p>{model.warning}</p>}{model.sourceErrors.map((error, index) => <p key={`${error}-${index}`}>Source error: {error}</p>)}</div>}
      <p className="mt-3 text-[11px] text-gray-500">Evidence snapshot: {evidenceLabel(model.asOf)} / Authorization effect: {model.authorizationEffect || 'missing'}</p>
      <div className="mt-4 space-y-5">{model.families.length ? model.families.map((family) => <div key={family.strategy}><div className="mb-2 flex flex-wrap items-center gap-2"><h3 className="text-lg font-bold text-white">{family.strategy}</h3><span className="text-xs text-gray-500">Paper book: {evidenceLabel(family.reconciliationDivision)}</span></div>{family.sourceErrors.map((error, index) => <p key={`${error}-${index}`} className="mb-2 rounded border border-amber-900 bg-amber-950/20 p-2 text-xs text-amber-300">Source error: {error}</p>)}<div className="space-y-3">{family.variants.map((item) => <ReadinessVariant key={item.variant} item={item} />)}</div></div>) : <div className="rounded border border-gray-800 bg-gray-900 p-5 text-sm text-gray-500">Insufficient evidence: no readiness families were returned.</div>}</div>
    </section>
  );
}

function StatusBadge({ experiment }) {
  const style = experiment.status === 'ready'
    ? 'border-emerald-600 bg-emerald-950 text-emerald-200'
    : experiment.status === 'disabled'
      ? 'border-gray-600 bg-gray-900 text-gray-300'
      : experiment.status === 'empty'
        ? 'border-blue-700 bg-blue-950 text-blue-200'
        : 'border-red-700 bg-red-950 text-red-200';
  return <span className={`rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider ${style}`}>{experiment.status}</span>;
}

function ConfigSnapshot({ config }) {
  const entries = Object.entries(config || {}).filter(([key]) => key !== 'name');
  if (!entries.length) return <span className="text-gray-500">No parameters published</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {entries.map(([key, value]) => (
        <span key={key} className="rounded bg-gray-950 px-2 py-1 text-[11px] text-gray-400">
          {key.replaceAll('_', ' ')}: <strong className="text-gray-200">{value === null ? 'none' : String(value)}</strong>
        </span>
      ))}
    </div>
  );
}

function Metric({ label, value, accent = '' }) {
  return <div><dt className="text-[10px] uppercase tracking-wide text-gray-500">{label}</dt><dd className={`mt-1 text-sm font-bold ${accent || 'text-gray-100'}`}>{value}</dd></div>;
}

function CostScenario({ outcome }) {
  if (!outcome) return null;
  const hasSamples = Number(outcome.available_samples || 0) > 0;
  return (
    <div className="mt-4 rounded-lg border border-cyan-900 bg-cyan-950/20 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h5 className="text-xs font-bold uppercase tracking-wide text-cyan-200">Estimated target scenario</h5>
        <span className="rounded bg-cyan-950 px-2 py-1 text-[10px] font-bold text-cyan-300">NOT REALISED P&amp;L</span>
      </div>
      <p className="mt-1 text-[11px] text-gray-500">One-lot target scenario using an already-resolved chain. It is not a fill, closed trade, or profitability claim.</p>
      <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric label="Samples" value={formatCount(outcome.available_samples)} />
        <Metric label="Gross" value={hasSamples ? formatScenarioMoney(outcome.gross_pnl) : INSUFFICIENT_DATA} />
        <Metric label="Costs" value={hasSamples ? formatScenarioMoney(outcome.estimated_costs) : INSUFFICIENT_DATA} accent="text-amber-300" />
        <Metric label="Net" value={hasSamples ? formatScenarioMoney(outcome.estimated_net_pnl) : INSUFFICIENT_DATA} />
      </dl>
      {Number(outcome.unavailable_candidates || 0) > 0 && <p className="mt-2 text-xs text-amber-300">{formatCount(outcome.unavailable_candidates)} distinct candidate(s) lack defensible option-cost evidence.</p>}
    </div>
  );
}

function PennyVirtualOutcome({ outcome }) {
  if (!outcome) return null;
  return (
    <div className="mt-4 rounded-lg border border-emerald-900 bg-emerald-950/20 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h5 className="text-xs font-bold uppercase tracking-wide text-emerald-200">Broker-free virtual outcome book</h5>
        <span className="rounded bg-emerald-950 px-2 py-1 text-[10px] font-bold text-emerald-300">ONE SHARE - AFTER MIS COSTS</span>
      </div>
      <p className="mt-1 text-[11px] text-gray-500">Bar-based paper fills only. This is not live money, an order record, or a claim about scalable returns.</p>
      <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
        <Metric label="Paper entries" value={formatCount(outcome.entries)} />
        <Metric label="Open" value={formatCount(outcome.open)} />
        <Metric label="Closed" value={formatCount(outcome.closed)} />
        <Metric label="Wins / losses / flat" value={outcome.wins === null ? INSUFFICIENT_DATA : `${formatCount(outcome.wins)} / ${formatCount(outcome.losses)} / ${formatCount(outcome.breakevens)}`} />
        <Metric label="Win rate" value={formatRate(outcome.winRate)} />
        <Metric label="Average R" value={outcome.avgR === null ? INSUFFICIENT_DATA : Number(outcome.avgR).toFixed(3)} />
        <Metric label="Net P&amp;L" value={formatPaperMoney(outcome.netPnl)} />
        <Metric label="Net expectancy" value={formatPaperMoney(outcome.expectancy)} />
        <Metric label="Profit factor" value={outcome.profitFactor === null ? INSUFFICIENT_DATA : Number(outcome.profitFactor).toFixed(2)} />
        <Metric label="Max drawdown" value={formatPaperMoney(outcome.maxDrawdown)} />
      </dl>
    </div>
  );
}

function MomentumVirtualOutcome({ outcome }) {
  if (!outcome) return null;
  return (
    <div className="mt-4 rounded-lg border border-emerald-900 bg-emerald-950/20 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h5 className="text-xs font-bold uppercase tracking-wide text-emerald-200">Virtual paper outcome book</h5>
        <span className="rounded bg-emerald-950 px-2 py-1 text-[10px] font-bold text-emerald-300">SIMULATED - NO BROKER FILLS</span>
      </div>
      <p className="mt-1 text-[11px] text-gray-500">Bar-derived outcomes use declared slippage, equity MIS costs, conservative same-bar ordering, and only scanner-fetched bars.</p>
      <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
        <Metric label="Paper entries" value={formatCount(outcome.entries)} />
        <Metric label="Open" value={formatCount(outcome.open)} />
        <Metric label="Closed" value={formatCount(outcome.closed)} />
        <Metric label="Gross" value={formatSimulatedMoney(outcome.gross)} />
        <Metric label="Costs" value={formatSimulatedMoney(outcome.costs)} accent="text-amber-300" />
        <Metric label="Net" value={formatSimulatedMoney(outcome.net)} />
        <Metric label="Net expectancy" value={formatSimulatedMoney(outcome.expectancy)} />
        <Metric label="Profit factor" value={outcome.profitFactor === undefined ? INSUFFICIENT_DATA : Number(outcome.profitFactor).toFixed(2)} />
        <Metric label="Breakevens" value={formatCount(outcome.breakevens)} />
        <Metric label="Win rate" value={formatRate(outcome.winRate)} />
        <Metric label="Average R" value={formatCount(outcome.averageR)} />
        <Metric label="Max drawdown" value={formatSimulatedMoney(outcome.maxDrawdown)} />
        <Metric label="Current drawdown" value={formatSimulatedMoney(outcome.currentDrawdown)} />
      </dl>
    </div>
  );
}

function VariantCard({ experiment, variant }) {
  return (
    <article className="rounded-lg border border-gray-800 bg-gray-900/80 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div><h4 className="font-mono font-bold text-white">{variant.name}</h4><div className="mt-2"><ConfigSnapshot config={variant.config} /></div></div>
        <span className="rounded border border-violet-700 bg-violet-950 px-2 py-1 text-[10px] font-bold text-violet-200">IMMUTABLE VARIANT</span>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <Metric label="Evaluations" value={formatCount(variant.evaluations)} />
        <Metric label="Raw candidates" value={formatCount(variant.rawCandidates)} />
        <Metric label="Distinct candidates" value={formatCount(variant.distinctCandidates)} accent="text-cyan-300" />
        <Metric label="Accept conversion" value={formatRate(variant.acceptRate)} />
        <Metric label="Repeated accepts" value={formatCount(variant.repeats)} accent={Number(variant.repeats) > 0 ? 'text-amber-300' : ''} />
        <Metric label="Repeat inflation" value={formatRate(variant.repeatRate)} />
      </dl>

      <div className="mt-4 border-t border-gray-800 pt-3">
        <h5 className="text-[10px] font-bold uppercase tracking-wide text-gray-500">Top blockers</h5>
        {variant.blockers.length ? <div className="mt-2 flex flex-wrap gap-2">{variant.blockers.map((blocker) => <span key={`${blocker.reason}-${blocker.count}`} className="rounded bg-gray-950 px-2 py-1 text-xs text-gray-300">{String(blocker.reason).replaceAll('_', ' ')} <strong className="text-amber-300">{formatCount(blocker.count)}</strong></span>)}</div>
          : <p className="mt-2 text-xs text-gray-500">Insufficient data</p>}
      </div>
      {variant.warnings.map((warning) => <p key={warning} className="mt-2 text-xs text-amber-300">- {warning}</p>)}
      {experiment.id === 'momentum' && <MomentumVirtualOutcome outcome={variant.simulatedOutcomes} />}
      {experiment.id === 'penny' && <PennyVirtualOutcome outcome={variant.virtualOutcome} />}
      {experiment.id === 'fno' && <CostScenario outcome={variant.estimatedPostCost} />}
    </article>
  );
}

function ExperimentSection({ experiment }) {
  return (
    <section className="rounded-xl border border-gray-800 bg-gray-950/50 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h2 className="text-xl font-bold text-white">{experiment.title}</h2><p className="mt-1 text-sm text-gray-500">{experiment.subtitle}</p></div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-violet-600 bg-violet-950 px-2.5 py-1 text-[10px] font-bold text-violet-200">PAPER SHADOW</span>
          <span className={`rounded-full border px-2.5 py-1 text-[10px] font-bold ${experiment.enabled === true ? 'border-emerald-700 bg-emerald-950 text-emerald-200' : experiment.enabled === false ? 'border-gray-700 bg-gray-900 text-gray-300' : 'border-amber-700 bg-amber-950 text-amber-200'}`}>{experiment.enabled === true ? 'COLLECTOR ON' : experiment.enabled === false ? 'COLLECTOR OFF' : 'ENABLED: INSUFFICIENT DATA'}</span>
          <StatusBadge experiment={experiment} />
        </div>
      </div>
      {experiment.warning && <div className="mt-3 flex gap-2 rounded border border-red-800 bg-red-950/30 p-3 text-sm text-red-200"><AlertTriangle className="shrink-0" size={17} />{experiment.warning}</div>}
      {experiment.status === 'disabled' && <div className="mt-3 rounded border border-gray-700 bg-gray-900 p-3 text-sm text-gray-400">Evidence collection is disabled. Existing immutable history remains read-only.</div>}
      <div className="mt-4 space-y-4">
        {experiment.variants.length ? experiment.variants.map((variant) => <VariantCard key={variant.name} experiment={experiment} variant={variant} />)
          : <div className="rounded border border-gray-800 bg-gray-900 p-5 text-sm text-gray-500">No registered evidence is available.</div>}
      </div>
    </section>
  );
}

export default function ResearchCenter({ navigateToDashboard, navigateToBacktests }) {
  const { payloads, errors, readiness, readinessError, isLoading } = useResearchExperiments();
  const experiments = buildResearchCenterModel(payloads, errors);
  const readinessModel = normalizePromotionReadiness(readiness, readinessError);
  return (
    <div className="min-h-screen bg-gray-950 text-gray-200">
      <header className="border-b border-gray-800 bg-gray-900 px-4 py-4">
        <div className="mx-auto flex max-w-[1500px] flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3"><button onClick={navigateToDashboard} className="rounded border border-gray-700 p-2 text-gray-300 hover:bg-gray-800" aria-label="Back to dashboard"><ArrowLeft size={18} /></button><div><div className="flex items-center gap-2"><FlaskConical className="text-violet-400" size={21} /><h1 className="text-xl font-bold text-white">Research / Experiment Center</h1></div><p className="text-xs text-gray-500">Candidate evidence only. No broker orders, sizing, or live influence.</p></div></div>
          <div className="flex items-center gap-2"><span className="flex items-center gap-1 rounded-full border border-emerald-700 bg-emerald-950 px-3 py-1.5 text-[10px] font-bold text-emerald-200"><ShieldCheck size={13} /> RESEARCH ONLY - NO ORDERS</span><button onClick={navigateToBacktests} className="rounded border border-cyan-700 bg-cyan-950 px-3 py-2 text-sm font-semibold text-cyan-200 hover:bg-cyan-900">Open Backtest Lab</button></div>
        </div>
      </header>
      <main className="mx-auto max-w-[1500px] space-y-5 p-4 sm:p-6">
        <div className="rounded-lg border border-violet-800/70 bg-violet-950/20 p-4 text-sm text-violet-100">
          Raw candidates include repeated accepted evaluations. Distinct candidates are the sample-size view. Virtual outcomes are bar-derived simulations with declared costs—not broker fills or live-equivalent returns.
        </div>
        <ReadinessSection model={readinessModel} />
        {isLoading && experiments.every((item) => !item.variants.length) ? <div className="rounded border border-gray-800 bg-gray-900 p-8 text-center text-gray-500">Loading experiment evidence...</div>
          : experiments.map((experiment) => <ExperimentSection key={experiment.id} experiment={experiment} />)}
      </main>
    </div>
  );
}
