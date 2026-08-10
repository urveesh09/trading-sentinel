import React from 'react';
import { AlertTriangle, BarChart3, FlaskConical, Microscope } from 'lucide-react';
import StatusBar from '../components/StatusBar';
import SignalCard from '../components/SignalCard';
import PositionRow from '../components/PositionRow';
import CircuitBreaker from '../components/CircuitBreaker';
import { useSignals } from '../hooks/useSignals';
import { usePositions } from '../hooks/usePositions';
import { useDivisionPerformance } from '../hooks/useDivisionPerformance';
import { isActivePosition } from '../utils/positions';
import {
  INSUFFICIENT_DATA,
  buildDivisionViewModel,
  formatMoney,
  formatNumber,
  formatPercent,
  hasReconciliationMismatch,
} from '../utils/divisionPerformance';

const metric = (label, value, className = 'text-gray-100') => (
  <div className="min-w-0">
    <dt className="text-[11px] uppercase tracking-wide text-gray-500">{label}</dt>
    <dd className={`mt-1 truncate text-sm font-semibold ${className}`}>{value}</dd>
  </div>
);

function pnlColour(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'text-gray-400';
  return Number(value) >= 0 ? 'text-emerald-400' : 'text-red-400';
}

function DivisionCard({ division }) {
  const mode = division.mode;
  const ledger = division.ledger || {};
  const positions = division.positions || {};
  const mismatch = hasReconciliationMismatch(division);
  return (
    <article className={`rounded-lg border bg-gray-900/80 p-4 ${mismatch ? 'border-amber-500/70' : 'border-gray-800'}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h4 className="font-semibold text-white">{division.label}</h4>
          <p className="mt-0.5 text-xs text-gray-500">{division.pool} / {division.source}</p>
        </div>
        <span className={`rounded-full border px-2.5 py-1 text-[10px] font-bold tracking-widest ${
          mode === 'paper'
            ? 'border-violet-500/50 bg-violet-950 text-violet-200'
            : 'border-emerald-500/50 bg-emerald-950 text-emerald-200'
        }`}>
          {mode === 'paper' ? 'PAPER - SIMULATION' : 'LIVE'}
        </span>
      </div>

      {mismatch && (
        <div className="mt-3 flex gap-2 rounded border border-amber-600/50 bg-amber-950/50 p-2 text-xs text-amber-200">
          <AlertTriangle className="mt-0.5 shrink-0" size={14} />
          <span>Reconciliation mismatch: ledger and position closes disagree. Ledger remains cash truth.</span>
        </div>
      )}

      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-4 sm:grid-cols-3 lg:grid-cols-2 xl:grid-cols-3">
        {metric('Allocation', formatMoney(division.allocation, mode))}
        {metric('Equity', formatMoney(ledger.equity, mode))}
        {metric('Cash P&L', formatMoney(ledger.cash_pnl, mode, { signed: true }), pnlColour(ledger.cash_pnl))}
        {metric('Closed trades', ledger.trade_close_count ?? INSUFFICIENT_DATA)}
        {metric('Profit factor', formatNumber(ledger.profit_factor))}
        {metric('Expectancy', formatMoney(ledger.net_expectancy, mode, { signed: true }), pnlColour(ledger.net_expectancy))}
        {metric('Max drawdown', formatPercent(ledger.max_drawdown_pct))}
        {metric('Open risk', formatMoney(positions.open_risk, mode))}
        {metric('Open positions', positions.open_count ?? INSUFFICIENT_DATA)}
      </dl>

      {Array.isArray(division.warnings) && division.warnings.length > 0 && (
        <ul className="mt-4 space-y-1 border-t border-gray-800 pt-3 text-xs text-amber-300/90">
          {division.warnings.slice(0, 3).map((warning) => <li key={warning}>- {warning}</li>)}
        </ul>
      )}
    </article>
  );
}

function ModeSection({ group }) {
  const paper = group.mode === 'paper';
  return (
    <section className={`rounded-xl border p-4 ${paper ? 'border-violet-800/70 bg-violet-950/10' : 'border-emerald-900/70 bg-emerald-950/10'}`}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className={`text-lg font-bold tracking-wide ${paper ? 'text-violet-200' : 'text-emerald-200'}`}>{group.label}</h3>
          <p className="mt-1 text-xs text-gray-500">
            {paper ? 'Simulation only - these balances are not real funds.' : 'Broker-facing capital and realised cash ledger.'}
          </p>
        </div>
        <div className="grid grid-cols-3 gap-4 rounded-lg border border-gray-800 bg-gray-950/70 px-4 py-2 text-right">
          <div><div className="text-[10px] uppercase text-gray-500">Allocation</div><div className="text-xs font-semibold text-white">{formatMoney(group.total?.allocation, group.mode)}</div></div>
          <div><div className="text-[10px] uppercase text-gray-500">Equity</div><div className="text-xs font-semibold text-white">{formatMoney(group.total?.equity, group.mode)}</div></div>
          <div><div className="text-[10px] uppercase text-gray-500">Cash P&L</div><div className={`text-xs font-semibold ${pnlColour(group.total?.cash_pnl)}`}>{formatMoney(group.total?.cash_pnl, group.mode, { signed: true })}</div></div>
        </div>
      </div>
      {group.divisions.length ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-3">
          {group.divisions.map((division) => <DivisionCard key={division.key || division.source} division={division} />)}
        </div>
      ) : <div className="rounded border border-gray-800 p-5 text-sm text-gray-500">No divisions registered for this mode.</div>}
    </section>
  );
}

export default function Dashboard({ healthData, navigateToPositions, navigateToBacktests, navigateToResearch }) {
  const { signals, mutate: refreshSignals } = useSignals();
  const { positions } = usePositions();
  const { divisionPerformance, isLoading, isError } = useDivisionPerformance();
  const viewModel = buildDivisionViewModel(divisionPerformance);
  const cbHalted = healthData?.circuit_breaker_halted || false;
  const cbReasons = healthData?.circuit_breaker_reasons || [];
  const isMarketOpen = healthData?.market_open || false;
  const activePositions = Array.isArray(positions) ? positions.filter(isActivePosition).slice(0, 5) : [];

  return (
    <div className="min-h-screen bg-gray-950 text-gray-200">
      <StatusBar cbHalted={cbHalted} />
      <main className="mx-auto max-w-[1600px] space-y-6 p-4 sm:p-6">
        {cbHalted && <CircuitBreaker haltReasons={cbReasons} onResetSuccess={() => window.location.reload()} />}

        <header className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2"><BarChart3 className="text-cyan-400" size={22} /><h1 className="text-2xl font-bold text-white">Trading Operations</h1></div>
            <p className="mt-1 text-sm text-gray-500">Ledger-backed performance by strategy module and execution mode.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={navigateToResearch} className="flex items-center gap-2 rounded-lg border border-violet-600 bg-violet-950 px-4 py-2.5 text-sm font-bold text-violet-100 hover:bg-violet-900"><Microscope size={17} /> Experiment Center <span className="rounded bg-violet-900 px-1.5 py-0.5 text-[9px] tracking-wider">PAPER</span></button>
            <button onClick={navigateToBacktests} className="flex items-center gap-2 rounded-lg border border-cyan-600 bg-cyan-950 px-4 py-2.5 text-sm font-bold text-cyan-100 hover:bg-cyan-900"><FlaskConical size={17} /> Backtest Lab <span className="rounded bg-cyan-900 px-1.5 py-0.5 text-[9px] tracking-wider">RESEARCH ONLY</span></button>
          </div>
        </header>

        <section aria-labelledby="division-performance-heading">
          <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
            <div><h2 id="division-performance-heading" className="text-xl font-bold text-white">Module Performance</h2><p className="text-xs text-gray-500">Accounting truth: {viewModel.accountingTruth || 'Unavailable'}</p></div>
            {viewModel.mismatchCount > 0 && <div className="flex items-center gap-1 text-sm font-semibold text-amber-300"><AlertTriangle size={16} /> {viewModel.mismatchCount} reconciliation warning{viewModel.mismatchCount === 1 ? '' : 's'}</div>}
          </div>
          {isLoading && !divisionPerformance ? <div className="rounded border border-gray-800 bg-gray-900 p-6 text-gray-500">Loading division performance...</div>
            : isError ? <div className="rounded border border-red-900 bg-red-950/30 p-6 text-red-300">Division performance is currently unavailable. Live and paper totals are intentionally not estimated.</div>
              : <div className="space-y-5">{viewModel.groups.map((group) => <ModeSection key={group.mode} group={group} />)}</div>}
        </section>

        <section className="grid grid-cols-1 gap-6 xl:grid-cols-3">
          <div className="space-y-4 xl:col-span-1">
            <h2 className="border-b border-gray-800 pb-2 text-xl font-bold text-white">Active Signals</h2>
            {!signals?.length ? <div className="rounded border border-gray-800 bg-gray-900 p-4 text-sm italic text-gray-500">No pending signals.</div>
              : signals.map((signal) => <SignalCard key={signal.signal_id} signal={signal} isMarketOpen={isMarketOpen} cbHalted={cbHalted} onActionComplete={refreshSignals} />)}
          </div>
          <div className="xl:col-span-2">
            <div className="mb-4 flex items-end justify-between border-b border-gray-800 pb-2"><h2 className="text-xl font-bold text-white">Open Positions</h2><button onClick={navigateToPositions} className="text-sm text-blue-400 hover:text-blue-300">View All -&gt;</button></div>
            <div className="overflow-x-auto rounded border border-gray-800 bg-gray-900">
              <table className="w-full whitespace-nowrap text-left text-sm">
                <thead className="bg-gray-800 text-gray-400"><tr>{['Ticker', 'Entry', 'Stop', 'T1', 'T2', 'Unrealised P&L', 'R-Mult', 'Days', 'Source'].map((heading) => <th key={heading} className="p-3 font-medium">{heading}</th>)}</tr></thead>
                <tbody>{activePositions.length ? activePositions.map((position) => <PositionRow key={position.order_id} position={position} />) : <tr><td colSpan="9" className="p-6 text-center italic text-gray-500">No open positions.</td></tr>}</tbody>
              </table>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
