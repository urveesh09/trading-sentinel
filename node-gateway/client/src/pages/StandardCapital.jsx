import React, { useState } from 'react';
import useSWR from 'swr';
import { ArrowLeft, Scale } from 'lucide-react';
import { fetcher } from '../api/client';
import { formatRs, pnlTone } from '../utils/partnerCoach';
import {
  CAPITAL_PRESETS, formatCapital, formatPct, rowsByReturn, sincePresets, standardCapitalUrl,
} from '../utils/standardCapital';

// [O21-SC] Every paper book replayed on one standard capital, so books with
// different notionals can be compared. Paper only; not a forecast.

export default function StandardCapital({ navigateToDashboard }) {
  const [capital, setCapital] = useState(200000);
  const [custom, setCustom] = useState('');
  const [since, setSince] = useState('');
  const { data, error, isLoading } = useSWR(standardCapitalUrl(capital, since), fetcher,
    { refreshInterval: 300000, dedupingInterval: 60000 });
  const books = rowsByReturn(data?.books);
  const split = data?.equal_split;
  const button = (active) => `rounded border px-3 py-1.5 text-xs font-bold ${active ? 'border-teal-500 bg-teal-950 text-teal-100' : 'border-gray-700 text-gray-300'}`;
  return (
    <div className="min-h-screen bg-gray-950 p-4 text-gray-100 sm:p-6">
      <div className="mx-auto max-w-6xl space-y-5">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <button onClick={navigateToDashboard} className="rounded border border-gray-700 p-2 text-gray-300 hover:bg-gray-800" aria-label="Back"><ArrowLeft size={16} /></button>
            <div>
              <h1 className="flex items-center gap-2 text-2xl font-bold text-white"><Scale size={22} /> Standard Capital</h1>
              <p className="text-sm text-gray-400">Each book's own closed paper trades replayed on {formatCapital(capital)}: whole lots and shares, own cash only, charges at the new size.</p>
            </div>
          </div>
          <span className="rounded border border-amber-700 bg-amber-950 px-2 py-1 text-[10px] font-black text-amber-100">PAPER · NOT A FORECAST</span>
        </header>

        <section className="flex flex-wrap items-center gap-2">
          {CAPITAL_PRESETS.map((preset) => <button key={preset.value} onClick={() => setCapital(preset.value)} className={button(capital === preset.value)}>{preset.label}</button>)}
          <form onSubmit={(event) => { event.preventDefault(); const value = Number(custom); if (value >= 1000) setCapital(value); }} className="flex items-center gap-2">
            <input value={custom} onChange={(event) => setCustom(event.target.value)} inputMode="numeric" placeholder="Other ₹" className="w-28 rounded border border-gray-700 bg-gray-950 p-1.5 text-xs" />
            <button className={button(false)}>Use</button>
          </form>
          <span className="mx-2 h-5 w-px bg-gray-800" />
          {sincePresets().map((preset) => <button key={preset.label} onClick={() => setSince(preset.value)} className={button(since === preset.value)}>{preset.label}</button>)}
          <input type="date" value={since} onChange={(event) => setSince(event.target.value)} className="rounded border border-gray-700 bg-gray-950 p-1.5 text-xs" />
        </section>
        <p className="text-xs text-gray-500">Rules change often, so "since" scores the current version of a book apart from its history.</p>

        {error && <div className="rounded border border-red-800 bg-red-950/40 p-3 text-sm text-red-200">Unavailable: {error.info?.detail || error.message}</div>}
        {isLoading && !data && <p className="text-sm text-gray-500">Loading…</p>}

        {data && <>
          <div className="overflow-x-auto rounded-lg border border-gray-800">
            <table className="w-full text-left text-xs">
              <thead className="bg-gray-900 text-gray-500">
                <tr>
                  <th className="p-2">Book</th><th className="p-2">Net at {formatCapital(capital)}</th><th className="p-2">Return</th>
                  <th className="p-2">Worst drawdown</th><th className="p-2">PF</th><th className="p-2">Win %</th>
                  <th className="p-2">Trades taken</th><th className="p-2">Cash used (peak)</th><th className="p-2">Last 30d</th>
                  <th className="p-2">Reference · scale</th><th className="p-2">Real orders</th>
                </tr>
              </thead>
              <tbody>{books.map((book) => (
                <React.Fragment key={book.key}>
                  <tr className="border-t border-gray-800 align-top">
                    <td className="p-2 font-bold text-white">{book.label}<div className="text-[10px] font-normal text-gray-500">{book.first_trade ? `${book.first_trade} → ${book.last_trade}` : 'no closed trades'}</div></td>
                    <td className={`p-2 font-mono ${pnlTone(book.net_pnl)}`}>{formatRs(book.net_pnl)}</td>
                    <td className={`p-2 font-mono ${pnlTone(book.return_pct)}`}>{formatPct(book.return_pct, 2)}</td>
                    <td className="p-2 font-mono">{book.max_drawdown != null ? `${formatRs(-book.max_drawdown)} (${formatPct(-book.max_drawdown_pct)})` : 'n/a'}</td>
                    <td className="p-2 font-mono">{book.profit_factor ?? 'n/a'}</td>
                    <td className="p-2 font-mono">{book.win_rate_pct ?? 'n/a'}</td>
                    <td className="p-2 font-mono">{book.trades_taken ?? 0}/{book.trades_in_book ?? 0}{book.skipped_too_small ? ` · ${book.skipped_too_small} too small` : ''}{book.skipped_no_cash ? ` · ${book.skipped_no_cash} no cash` : ''}</td>
                    <td className="p-2 font-mono">{book.peak_deployed_pct != null ? `${book.peak_deployed_pct}%` : 'n/a'}</td>
                    <td className={`p-2 font-mono ${pnlTone(book.last_30d_pnl)}`}>{formatRs(book.last_30d_pnl)}</td>
                    <td className="p-2 font-mono">{formatCapital(book.reference_capital)} · ×{book.scale ?? 'n/a'}</td>
                    <td className="p-2 text-gray-400">{book.live_path}</td>
                  </tr>
                  {(book.flags?.length > 0 || book.note) && (
                    <tr><td colSpan={11} className="px-2 pb-2 text-[11px] text-amber-300">{[book.note, ...(book.flags || [])].filter(Boolean).join(' · ')}</td></tr>
                  )}
                </React.Fragment>
              ))}</tbody>
            </table>
          </div>

          {split && (
            <section className="rounded-lg border border-gray-800 bg-gray-900/60 p-4 text-sm">
              <p className="font-bold text-white">{formatCapital(capital)} split equally across {split.books} books ({formatCapital(split.per_book)} each)</p>
              <p className="mt-1 text-gray-300">Net <span className={pnlTone(split.net_pnl)}>{formatRs(split.net_pnl)}</span> ({formatPct(split.return_pct, 2)}) · worst drawdown {formatRs(-split.max_drawdown)} ({formatPct(-split.max_drawdown_pct)}) · {split.closes} closes</p>
            </section>
          )}

          <section className="rounded border border-gray-800 p-3 text-xs text-gray-400">
            <p className="font-bold text-gray-300">Method</p>
            <ul className="mt-1 list-disc space-y-1 pl-4">
              {Object.entries(data.method || {}).map(([key, text]) => <li key={key}>{text}</li>)}
              <li>At a book's own reference capital the replay equals the book's own P&L unless the book held more than its pool at once (flagged).</li>
            </ul>
          </section>
        </>}
      </div>
    </div>
  );
}
