import React from 'react';
import { AlertTriangle, BarChart3, FlaskConical, Microscope } from 'lucide-react';
import StatusBar from '../components/StatusBar';
import SignalCard from '../components/SignalCard';
import PositionRow from '../components/PositionRow';
import CircuitBreaker from '../components/CircuitBreaker';
import { useSignals } from '../hooks/useSignals';
import { usePositions } from '../hooks/usePositions';
import { useDivisionPerformance } from '../hooks/useDivisionPerformance';
import { useProactiveActivity } from '../hooks/useProactiveActivity';
import { usePartnerHedgeCards } from '../hooks/usePartnerHedgeCards';
import { usePartnerDeliveryBacklog } from '../hooks/usePartnerDeliveryBacklog';
import { useOptionalAiStatus } from '../hooks/useOptionalAiStatus';
import { useProactiveSessionDiagnostics } from '../hooks/useProactiveSessionDiagnostics';
import { evidenceModeEnabled } from '../evidenceMode';
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

function ActivityFunnel({ activity, isLoading, isError }) {
  if (isLoading) return <div className="rounded border border-gray-800 bg-gray-900 p-4 text-sm text-gray-500">Loading proactive activity…</div>;
  if (isError || !activity) return <div className="rounded border border-amber-800 bg-amber-950/30 p-4 text-sm text-amber-200">Proactive activity is unavailable; unknown data is not treated as healthy inactivity.</div>;
  const shadowPositions = Array.isArray(activity.shadow_positions) ? activity.shadow_positions : [];
  const marketData = Array.isArray(activity.market_data?.latest) ? activity.market_data.latest : [];
  const brokerStatement = activity.broker_statement;
  return (
    <section className="rounded-xl border border-cyan-900/70 bg-cyan-950/10 p-4">
      <h2 className="text-xl font-bold text-white">Why we traded — or did not</h2>
      <p className="mt-1 text-xs text-gray-500">Unique opportunities vs repeated evaluations. Shadow/replay evidence is never live P&amp;L.</p>
      <div className="mt-4 grid gap-3 md:grid-cols-4">
        {Object.entries(activity.modes || {}).map(([mode, row]) => (
          <div key={mode} className="rounded border border-gray-800 bg-gray-950/70 p-3">
            <div className="text-xs font-bold text-cyan-200">{mode}</div>
            <div className="mt-2 text-sm">Opportunities: <b>{row.unique_opportunities}</b></div>
            <div className="text-sm">Evaluations: <b>{row.scan_evaluations}</b></div>
            <div className="mt-2 text-[11px] text-gray-500">{Object.entries(row.stages || {}).map(([stage, count]) => `${stage}: ${count}`).join(' · ') || 'No evidence recorded'}</div>
          </div>
        ))}
      </div>
      <div className="mt-4 border-t border-cyan-900/60 pt-3">
        <h3 className="text-sm font-semibold text-cyan-100">Broker statement reconciliation</h3>
        <p className="mt-1 text-[11px] text-gray-500">Imported statement evidence only. A broker acknowledgement or this card never authorises an order.</p>
        {brokerStatement ? <div className={`mt-2 rounded border p-3 text-xs ${brokerStatement.status === 'MATCH' ? 'border-emerald-900/70 bg-emerald-950/10' : 'border-amber-800 bg-amber-950/20'}`}><div className="flex justify-between gap-3"><b>{brokerStatement.status}</b><span>{brokerStatement.statement_id || brokerStatement.reason}</span></div>{brokerStatement.status !== 'UNAVAILABLE' && <div className="mt-2 grid grid-cols-2 gap-2 text-gray-300 sm:grid-cols-4"><span>Net after costs: <b className={pnlColour(brokerStatement.net_trading_result)}>{formatMoney(brokerStatement.net_trading_result, 'live', { signed: true })}</b></span><span>Charges: <b>{formatMoney(brokerStatement.charges, 'live')}</b></span><span>Expenses: <b>{formatMoney(brokerStatement.operating_expenses, 'live')}</b></span><span>Residual: <b>{formatMoney(brokerStatement.residual, 'live', { signed: true })}</b></span></div>}</div> : <div className="mt-2 text-xs text-gray-500">Broker statement reconciliation is unavailable.</div>}
      </div>
      <div className="mt-4 border-t border-cyan-900/60 pt-3">
        <h3 className="text-sm font-semibold text-cyan-100">Completed-bar market-data evidence</h3>
        <p className="mt-1 text-[11px] text-gray-500">Provider freshness is separate from scheduler activity. This read-only SHADOW source cannot place orders.</p>
        {marketData.length ? <div className="mt-3 grid gap-3 md:grid-cols-3">{marketData.map((row) => (
          <div key={`${row.account_id}:${row.run_id}`} className="rounded border border-gray-800 bg-gray-950/70 p-3 text-xs">
            <div className="flex items-start justify-between gap-2"><div className="font-semibold text-cyan-200">{row.account_id}</div><span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${row.state === 'AVAILABLE' ? 'bg-emerald-950 text-emerald-200' : 'bg-amber-950 text-amber-200'}`}>{row.state}</span></div>
            <div className="mt-1 text-[10px] text-gray-500">Run: {row.run_id} · {row.provider || 'Provider unavailable'}</div>
            <div className="mt-2 grid grid-cols-2 gap-2 text-gray-300"><span>Bars: <b>{row.bar_count}</b></span><span>Instruments: <b>{row.instrument_count}</b></span><span>Frame: <b>{row.timeframe || '—'}</b></span><span>Age: <b>{row.freshness_seconds == null ? '—' : `${Math.round(row.freshness_seconds)}s`}</b></span></div>
            <p className="mt-2 break-words text-[10px] text-gray-500">{row.reason} · adjustment {row.adjustment_version || 'unavailable'}</p>
          </div>
        ))}</div> : <div className="mt-2 text-xs text-gray-500">No completed-bar provider observation has been recorded for this dashboard scope.</div>}
      </div>
      <div className="mt-4 border-t border-cyan-900/60 pt-3">
        <h3 className="text-sm font-semibold text-cyan-100">Synthetic SHADOW positions and outcomes</h3>
        <p className="mt-1 text-[11px] text-gray-500">Fixture simulation only. Gross, fees and net are not broker-reconciled profit.</p>
        {shadowPositions.length ? <div className="mt-3 grid gap-3 md:grid-cols-3">{shadowPositions.map((row) => (
          <div key={`${row.account_id}:${row.run_id || 'legacy'}`} className="rounded border border-gray-800 bg-gray-950/70 p-3 text-sm">
            <div className="font-semibold text-violet-200">{row.account_id}</div><div className="text-[10px] text-gray-500">Run: {row.run_id || 'legacy'}</div>
            <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-gray-300">
              <span>Open: <b>{row.open_positions}</b></span><span>Closed: <b>{row.closed_positions}</b></span>
              <span>Scenario cash: <b>{row.scenario_capital == null ? 'Unavailable' : formatMoney(row.scenario_capital, 'paper')}</b></span><span>Free cash: <b>{row.free_cash == null ? 'Unavailable' : formatMoney(row.free_cash, 'paper')}</b></span>
              <span>Reserved: <b>{formatMoney(row.reserved_capital, 'paper')}</b></span><span>Gross: <b className={pnlColour(row.gross_pnl)}>{formatMoney(row.gross_pnl, 'paper', { signed: true })}</b></span>
              <span>Fees: <b>{formatMoney(row.fees, 'paper')}</b></span><span>Net: <b className={pnlColour(row.net_pnl)}>{formatMoney(row.net_pnl, 'paper', { signed: true })}</b></span>
              <span className="col-span-2 text-[10px] text-amber-200">Unrealized: {row.unrealized_state === 'UNAVAILABLE_NO_CURRENT_MARK' ? 'Unavailable — no current fixture mark' : formatMoney(row.marked_unrealized_pnl, 'paper', { signed: true })}</span>
            </div>
          </div>
        ))}</div> : <div className="mt-2 text-xs text-gray-500">No persisted synthetic fills or closed outcomes in this reporting window.</div>}
      </div>
      <p className="mt-3 text-xs text-gray-500">{activity.note}</p>
    </section>
  );
}

function PartnerHedgeCards({ cards, isLoading, isError }) {
  if (isLoading) return <div className="rounded border border-gray-800 bg-gray-900 p-4 text-sm text-gray-500">Loading partner hedge review evidence…</div>;
  if (isError || !cards) return <div className="rounded border border-amber-800 bg-amber-950/30 p-4 text-sm text-amber-200">Partner hedge review evidence is unavailable. Unavailable data is never shown as a current recommendation.</div>;
  const rows = Array.isArray(cards.cards) ? cards.cards : [];
  return (
    <section className="rounded-xl border border-fuchsia-900/70 bg-fuchsia-950/10 p-4" aria-labelledby="partner-hedge-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="partner-hedge-heading" className="text-xl font-bold text-white">Partner hedge review cards</h2>
          <p className="mt-1 text-xs text-gray-500">Persisted review evidence only. No card can send a message, place an order, or confirm a partner holding.</p>
        </div>
        <span className="rounded border border-fuchsia-500/50 bg-fuchsia-950 px-2 py-1 text-[10px] font-bold tracking-widest text-fuchsia-200">{cards.mode || 'SHADOW'} · NO DELIVERY</span>
      </div>
      {rows.length ? <div className="mt-4 grid gap-3 lg:grid-cols-2">{rows.map((card) => (
        <article key={card.evaluation_id} className={`rounded border bg-gray-950/70 p-3 ${card.is_superseded ? 'border-amber-700/80' : 'border-gray-800'}`}>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div><h3 className="font-semibold text-fuchsia-100">{card.underlying || 'Unknown underlying'} · {card.kind || 'review'}</h3><p className="mt-0.5 text-[11px] text-gray-500">{card.phase || 'phase unavailable'} · {card.evaluated_at || 'time unavailable'}</p></div>
            <span className={`rounded px-2 py-1 text-[10px] font-bold ${card.is_superseded ? 'bg-amber-950 text-amber-200' : 'bg-slate-800 text-slate-300'}`}>{card.portfolio_state || 'REVISION UNAVAILABLE'}</span>
          </div>
          <p className="mt-3 whitespace-pre-wrap text-sm text-gray-300">{card.rendered_text || card.reason || 'No rendered review text.'}</p>
          <dl className="mt-3 grid grid-cols-2 gap-2 border-t border-gray-800 pt-3 text-xs">
            <div><dt className="text-gray-500">Contracts</dt><dd className="mt-0.5 text-gray-200">{card.contracts?.length ? card.contracts.join(', ') : 'Unavailable'}</dd></div>
            <div><dt className="text-gray-500">Valid until</dt><dd className="mt-0.5 text-gray-200">{card.valid_until || 'Unavailable'}</dd></div>
            <div><dt className="text-gray-500">Recorded revision</dt><dd className="mt-0.5 text-gray-200">{card.portfolio_revision ?? 'Unavailable'}</dd></div>
            <div><dt className="text-gray-500">Current revision</dt><dd className="mt-0.5 text-gray-200">{card.current_portfolio_revision ?? 'Unavailable'}</dd></div>
          </dl>
          <p className="mt-3 text-[10px] font-semibold tracking-wide text-gray-500">{card.delivery_state || 'NOT SENT'} · SEND: NO · TRADE: NO</p>
        </article>
      ))}</div> : <div className="mt-4 rounded border border-gray-800 bg-gray-950/70 p-4 text-sm text-gray-500">No persisted partner hedge review evidence yet.</div>}
      <p className="mt-3 text-xs text-gray-500">{cards.note}</p>
    </section>
  );
}

function PartnerDeliveryBacklog({ backlog, isLoading, isError }) {
  if (isLoading) return <div className="rounded border border-gray-800 bg-gray-900 p-4 text-sm text-gray-500">Loading partner delivery recovery evidence…</div>;
  if (isError || !backlog) return <div className="rounded border border-amber-800 bg-amber-950/30 p-4 text-sm text-amber-200">Partner delivery recovery evidence is unavailable. No delivery conclusion is inferred.</div>;
  const manual = Array.isArray(backlog.manual_recovery) ? backlog.manual_recovery : [];
  const quarantine = Array.isArray(backlog.quarantine) ? backlog.quarantine : [];
  return (
    <section className="rounded-xl border border-amber-900/70 bg-amber-950/10 p-4" aria-labelledby="partner-delivery-heading">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 id="partner-delivery-heading" className="text-xl font-bold text-white">Partner delivery recovery</h2><p className="mt-1 text-xs text-gray-500">Read-only operator evidence. Ambiguous deliveries require recorded manual resolution; this dashboard cannot resend or release them.</p></div><span className="rounded border border-amber-600/60 bg-amber-950 px-2 py-1 text-[10px] font-bold tracking-widest text-amber-200">NO RESEND ACTION</span></div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2"><div className="rounded border border-gray-800 bg-gray-950/70 p-3"><div className="text-xs font-semibold text-amber-100">Manual recovery required: {manual.length}</div>{manual.length ? <ul className="mt-2 space-y-1 text-[11px] text-gray-400">{manual.slice(0, 4).map((item) => <li key={`${item.kind}:${item.dedup_key}`}>{item.kind} · {item.dedup_key} · {item.state}</li>)}</ul> : <p className="mt-2 text-xs text-emerald-300">No unresolved delivery evidence.</p>}</div><div className="rounded border border-gray-800 bg-gray-950/70 p-3"><div className="text-xs font-semibold text-amber-100">Quarantined legacy records: {quarantine.length}</div>{quarantine.length ? <ul className="mt-2 space-y-1 text-[11px] text-gray-400">{quarantine.slice(0, 4).map((item) => <li key={`${item.kind}:${item.dedup_key}`}>{item.kind} · {item.reason}</li>)}</ul> : <p className="mt-2 text-xs text-emerald-300">No quarantined records.</p>}</div></div>
    </section>
  );
}

function OptionalAiEvidence({ optionalAi, isLoading, isError }) {
  if (isLoading) return <div className="rounded border border-gray-800 bg-gray-900 p-4 text-sm text-gray-500">Loading optional-AI health evidence…</div>;
  if (isError || !optionalAi) return <div className="rounded border border-amber-800 bg-amber-950/30 p-4 text-sm text-amber-200">Optional-AI health is unavailable. Deterministic trading paths do not depend on this display.</div>;
  const unavailable = ['NOT_REPORTED', 'STALE', 'OUTAGE_CIRCUIT_OPEN', 'UNAVAILABLE', 'CORRUPT_REPORT'].includes(optionalAi.state);
  const queue = optionalAi.detail?.queue || {};
  return (
    <section className={`rounded-xl border p-4 ${unavailable ? 'border-amber-800 bg-amber-950/20' : 'border-blue-900/70 bg-blue-950/10'}`} aria-labelledby="optional-ai-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h2 id="optional-ai-heading" className="text-xl font-bold text-white">Optional AI annotation</h2><p className="mt-1 text-xs text-gray-500">A status/outage evidence surface, not a trade permission or risk override.</p></div>
        <span className={`rounded px-2 py-1 text-[10px] font-bold tracking-widest ${unavailable ? 'bg-amber-950 text-amber-200' : 'bg-blue-950 text-blue-200'}`}>{optionalAi.state}</span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
        <div><div className="text-gray-500">Pending</div><div className="mt-1 font-semibold text-gray-200">{queue.pending ?? 'Unavailable'}</div></div>
        <div><div className="text-gray-500">Circuit</div><div className="mt-1 font-semibold text-gray-200">{queue.circuit_state ?? 'Unavailable'}</div></div>
        <div><div className="text-gray-500">Daily budget</div><div className="mt-1 font-semibold text-gray-200">{queue.daily_requests ?? '—'} / {queue.daily_budget ?? '—'}</div></div>
        <div><div className="text-gray-500">Reported at</div><div className="mt-1 break-all font-semibold text-gray-200">{optionalAi.reported_at || 'Never'}</div></div>
      </div>
      <p className="mt-3 text-xs text-gray-400">{optionalAi.note}</p>
      <p className="mt-2 text-[10px] font-semibold tracking-wide text-gray-500">EXECUTION AUTHORITY: NONE · CAN PLACE ORDERS: NO</p>
    </section>
  );
}

function SessionDiagnostics({ sessionDiagnostics, isLoading, isError }) {
  if (isLoading) return <div className="rounded border border-gray-800 bg-gray-900 p-4 text-sm text-gray-500">Loading calendar-aware session diagnostics…</div>;
  if (isError || !sessionDiagnostics) return <div className="rounded border border-amber-800 bg-amber-950/30 p-4 text-sm text-amber-200">Five-session diagnostic evidence is unavailable; no inactivity conclusion is inferred.</div>;
  const reports = Array.isArray(sessionDiagnostics.reports) ? sessionDiagnostics.reports : [];
  const rootFindings = Array.isArray(sessionDiagnostics.findings) ? sessionDiagnostics.findings : [];
  return (
    <section className="rounded-xl border border-indigo-900/70 bg-indigo-950/10 p-4" aria-labelledby="session-diagnostics-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h2 id="session-diagnostics-heading" className="text-xl font-bold text-white">Five-session activity explanation</h2><p className="mt-1 text-xs text-gray-500">Calendar-aware operational evidence by policy, account and mode. It explains inactivity; it never loosens a gate.</p></div>
        <span className="rounded border border-indigo-500/50 bg-indigo-950 px-2 py-1 text-[10px] font-bold tracking-widest text-indigo-200">OBSERVATION ONLY</span>
      </div>
      {reports.length ? <div className="mt-4 space-y-3">{reports.map((report) => {
        const scope = report.scope || {};
        const health = report.scan_health || {};
        const activity = report.activity || {};
        const findings = Array.isArray(report.findings) ? report.findings : [];
        return <article key={`${scope.policy_id}:${scope.account_id}:${scope.mode}`} className="rounded border border-gray-800 bg-gray-950/70 p-3">
          <div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="font-semibold text-indigo-100">{scope.policy_id || 'Unknown policy'} · {scope.account_id || 'Unknown account'}</h3><p className="mt-0.5 text-[11px] text-gray-500">{scope.mode || 'Unknown mode'} · sessions: {(report.eligible_sessions || []).join(', ') || 'Unavailable'}</p></div><span className="rounded bg-slate-800 px-2 py-1 text-[10px] font-bold text-slate-300">SCANS {health.successful_sessions ?? 0}/{health.expected_sessions ?? '—'}</span></div>
          <div className="mt-3 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4"><div><div className="text-gray-500">Missing scans</div><div className="mt-1 font-semibold text-gray-200">{health.missing_sessions ?? '—'}</div></div><div><div className="text-gray-500">Unavailable scans</div><div className="mt-1 font-semibold text-gray-200">{health.unavailable_sessions ?? '—'}</div></div><div><div className="text-gray-500">Viable events</div><div className="mt-1 font-semibold text-gray-200">{activity.viable_events ?? '—'}</div></div><div><div className="text-gray-500">Fills</div><div className="mt-1 font-semibold text-gray-200">{activity.fills ?? '—'}</div></div></div>
          {findings.length ? <ul className="mt-3 space-y-1 border-t border-gray-800 pt-3 text-xs text-amber-200">{findings.map((finding, index) => <li key={`${finding.code}:${index}`}>{finding.code}</li>)}</ul> : <p className="mt-3 border-t border-gray-800 pt-3 text-xs text-emerald-300">No two/five-session activity concern is evidenced for this scope.</p>}
        </article>;
      })}</div> : <div className="mt-4 rounded border border-gray-800 bg-gray-950/70 p-4 text-sm text-gray-500">{rootFindings.map((finding) => finding.code).join(' · ') || 'No scanner scope has reported evidence yet.'}</div>}
    </section>
  );
}

export default function Dashboard({ healthData, navigateToPositions, navigateToBacktests, navigateToResearch }) {
  const { signals, mutate: refreshSignals } = useSignals();
  const { positions } = usePositions();
  const { divisionPerformance, isLoading, isError } = useDivisionPerformance();
  const proactive = useProactiveActivity();
  const partnerHedgeCards = usePartnerHedgeCards();
  const partnerDeliveryBacklog = usePartnerDeliveryBacklog();
  const optionalAi = useOptionalAiStatus();
  const sessionDiagnostics = useProactiveSessionDiagnostics();
  const viewModel = buildDivisionViewModel(divisionPerformance);
  const cbHalted = healthData?.circuit_breaker_halted || false;
  const cbReasons = healthData?.circuit_breaker_reasons || [];
  const isMarketOpen = healthData?.market_open || false;
  const activePositions = Array.isArray(positions) ? positions.filter(isActivePosition).slice(0, 5) : [];

  return (
    <div className="min-h-screen bg-gray-950 text-gray-200">
      <StatusBar cbHalted={cbHalted} />
      <main className="mx-auto max-w-[1600px] space-y-6 p-4 sm:p-6">
        {evidenceModeEnabled && <div className="rounded border border-amber-500/80 bg-amber-950/70 p-3 text-sm font-semibold text-amber-100">DEV EVIDENCE FIXTURE — synthetic browser-rendering scenario. It does not contact authenticated services and cannot represent live balances, orders, partner delivery or profit.</div>}
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

        <ActivityFunnel {...proactive} />

        <div className="grid gap-6 2xl:grid-cols-2">
          <PartnerHedgeCards {...partnerHedgeCards} />
          <PartnerDeliveryBacklog {...partnerDeliveryBacklog} />
          <OptionalAiEvidence {...optionalAi} />
        </div>

        <SessionDiagnostics {...sessionDiagnostics} />

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
