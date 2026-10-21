import React, { useState } from 'react';
import useSWR from 'swr';
import { ArrowLeft, GraduationCap } from 'lucide-react';
import { fetcher, postClient } from '../api/client';
import {
  STATUS_LABEL, buildCoachModel, buildReportBody, coachUrl, fillLabel, fillSource, formatPrice, formatRs, pnlTone,
  zerodhaLine,
} from '../utils/partnerCoach';

// [O21-PC] What the partner did with each card, what the card said, and the
// difference with a reason. Coaching only: nothing here places an order or
// changes a card.
// [O21-PK] `partnerView`: the partner's own coach-only session (opened by
// their Zerodha login). Read-only: no report form, no remove, no navigation.

const WINDOWS = [1, 7, 30, 90];

function Tile({ label, value, tone = 'text-white', hint }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900/80 p-3">
      <p className="text-[10px] uppercase tracking-wide text-gray-500">{label}</p>
      <p className={`mt-1 text-lg font-bold ${tone}`}>{value}</p>
      {hint && <p className="mt-1 text-[11px] text-gray-500">{hint}</p>}
    </div>
  );
}

function Flag({ flag }) {
  return (
    <li className="rounded border border-amber-800/70 bg-amber-950/20 p-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-xs font-bold text-amber-200">{flag.title}</span>
        {flag.impact_rs != null && <span className={`font-mono text-xs ${pnlTone(flag.impact_rs)}`}>{formatRs(flag.impact_rs)}</span>}
      </div>
      <p className="mt-1 text-xs text-gray-300">{flag.reason}</p>
      {flag.why && <p className="mt-1 text-xs text-gray-400">{flag.why}</p>}
      {flag.better && <p className="mt-1 text-xs text-emerald-200">{flag.better}</p>}
      <p className="mt-1 text-[11px] text-gray-500">Next time: {flag.advice}</p>
    </li>
  );
}

function Fills({ title, fills, onVoid }) {
  if (!fills?.length) return null;
  return (
    <div>
      <p className="text-[10px] uppercase text-gray-500">{title}</p>
      <ul className="mt-1 space-y-1">
        {fills.map((fill) => (
          <li key={fill.report_id} className="flex flex-wrap items-center gap-2 text-xs text-gray-200">
            <span className="font-mono">{fillLabel(fill)}</span>
            <span className="text-[10px] text-gray-500">{fillSource(fill)}</span>
            {onVoid && fill.source !== 'ZERODHA' && <button onClick={() => onVoid(fill.report_id)} className="text-[10px] text-red-300 hover:text-red-200">remove</button>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function CardRow({ item, onVoid, who = 'Partner' }) {
  const card = item.card || {};
  const partner = item.partner || {};
  const plan = item.plan || {};
  return (
    <article className="rounded-lg border border-gray-800 bg-gray-950 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h4 className="font-mono text-sm font-bold text-white">{item.time} · {item.option}</h4>
          {item.card ? (
            <p className="mt-1 text-[11px] text-gray-400">
              Card: buy up to {formatPrice(card.buy_limit)} (ask {formatPrice(card.ask)}) · SL {formatPrice(card.sl_premium)} ·
              target ≈{formatPrice(card.target_low)}–{formatPrice(card.target_premium)} · skip after {card.fill_by} · exit by {card.exit_by}
            </p>
          ) : <p className="mt-1 text-[11px] text-gray-400">No card for this option</p>}
        </div>
        <span className="rounded-full border border-gray-700 px-2 py-0.5 text-[10px] text-gray-300">
          {STATUS_LABEL[partner.status] || 'Off-card'}
        </span>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div className="space-y-2">
          <Fills title="Bought" fills={partner.buys} onVoid={onVoid} />
          <Fills title="Sold" fills={partner.sells} onVoid={onVoid} />
          {partner.pnl != null && <p className={`text-sm font-bold ${pnlTone(partner.pnl)}`}>{who}: {formatRs(partner.pnl)} after charges{partner.estimated ? ' (≈ prices)' : ''}</p>}
        </div>
        <div className="space-y-1 text-xs text-gray-300">
          {item.card_messages?.length > 0 && <p className="text-[11px] text-gray-500">Card messages: {item.card_messages.map((m) => `${m.type.replaceAll('_', ' ').toLowerCase()} ${m.at}`).join(' · ')}</p>}
          {plan.note && <p>Card plan: {plan.note}</p>}
          {plan.pnl != null && <p className={`font-bold ${pnlTone(plan.pnl)}`}>Card plan: {formatRs(plan.pnl)}{plan.qty ? ` on ${plan.qty} qty` : ''}</p>}
          {item.same_entry?.pnl != null && plan.pnl === 0 && <p className="text-[11px] text-gray-400">Card exits on your entry: {formatRs(item.same_entry.pnl)} ({item.same_entry.note})</p>}
          {item.prices_available === false && <p className="text-[11px] text-amber-300">No option prices were stored for this strike.</p>}
        </div>
      </div>
      {item.flags?.length > 0 && <ul className="mt-3 space-y-2">{item.flags.map((flag, index) => <Flag key={`${flag.code}-${index}`} flag={flag} />)}</ul>}
      {item.positives?.length > 0 && (
        <ul className="mt-2 space-y-1">
          {item.positives.map((good, index) => <li key={`${good.code}-${index}`} className="text-xs text-emerald-300">✅ {good.title}: {good.reason}</li>)}
        </ul>
      )}
      {item.verdict && <p className="mt-3 border-t border-gray-800 pt-2 text-xs text-gray-400">{item.verdict}</p>}
    </article>
  );
}

function ReportForm({ cards, onSaved }) {
  const empty = { advisoryId: '', action: 'BUY', lots: '1', price: '', time: '', underlying: 'NIFTY', strike: '', optType: 'CE', note: '' };
  const [form, setForm] = useState(empty);
  const [notice, setNotice] = useState('');
  const set = (key) => (event) => setForm({ ...form, [key]: event.target.value });
  const submit = async (event) => {
    event.preventDefault();
    const { body, errors } = buildReportBody(form);
    if (errors.length) { setNotice(errors.join(' ')); return; }
    try {
      await postClient('/api/proxy/partner/coach/reports', body);
      setNotice('Saved.');
      setForm({ ...empty, advisoryId: form.advisoryId });
      onSaved();
    } catch (error) {
      setNotice(error.info?.detail || error.message);
    }
  };
  const input = 'mt-1 w-full rounded border border-gray-700 bg-gray-950 p-2 text-gray-100';
  return (
    <form onSubmit={submit} className="grid gap-3 rounded-lg border border-gray-800 bg-gray-900/60 p-4 sm:grid-cols-4">
      <p className="text-sm font-bold text-white sm:col-span-4">Add what the partner told you</p>
      <label className="text-xs text-gray-400 sm:col-span-2">Card
        <select value={form.advisoryId} onChange={set('advisoryId')} className={input}>
          <option value="">No card (off-card trade)</option>
          {cards.map((card) => <option key={card.value} value={card.value}>{card.label}</option>)}
        </select>
      </label>
      <label className="text-xs text-gray-400">Action
        <select value={form.action} onChange={set('action')} className={input}>
          <option value="BUY">Bought</option><option value="SELL">Sold</option><option value="SKIP">Skipped</option>
        </select>
      </label>
      <label className="text-xs text-gray-400">Time (IST)<input type="datetime-local" value={form.time} onChange={set('time')} className={input} /></label>
      {!form.advisoryId && <>
        <label className="text-xs text-gray-400">Index
          <select value={form.underlying} onChange={set('underlying')} className={input}><option>NIFTY</option><option>SENSEX</option><option>BANKNIFTY</option></select>
        </label>
        <label className="text-xs text-gray-400">Strike<input value={form.strike} onChange={set('strike')} inputMode="numeric" className={input} /></label>
        <label className="text-xs text-gray-400">Type
          <select value={form.optType} onChange={set('optType')} className={input}><option>CE</option><option>PE</option></select>
        </label>
      </>}
      {form.action !== 'SKIP' && <>
        <label className="text-xs text-gray-400">Price ₹<input value={form.price} onChange={set('price')} inputMode="decimal" className={input} /></label>
        <label className="text-xs text-gray-400">Lots<input value={form.lots} onChange={set('lots')} inputMode="numeric" className={input} /></label>
      </>}
      <label className="text-xs text-gray-400 sm:col-span-2">Note<input value={form.note} onChange={set('note')} maxLength={200} className={input} /></label>
      <div className="flex items-center gap-3 sm:col-span-4">
        <button className="rounded border border-teal-600 bg-teal-950 px-3 py-2 text-xs font-bold text-teal-100">Save report</button>
        {notice && <span className="text-xs text-gray-400">{notice}</span>}
      </div>
    </form>
  );
}

export default function PartnerCoach({ navigateToDashboard, navigateToReview, partnerView = false }) {
  const [days, setDays] = useState(partnerView ? 1 : 30);
  const [syncNote, setSyncNote] = useState('');
  const { data, error, isLoading, mutate } = useSWR(coachUrl(partnerView, days), fetcher,
    { refreshInterval: 60000, dedupingInterval: 20000 });
  const model = buildCoachModel(data);
  const s = model.summary;
  const today = String(data?.as_of || '').slice(0, 10);
  const voidReport = partnerView ? null : async (reportId) => {
    if (!window.confirm('Remove this report?')) return;
    await postClient(`/api/proxy/partner/coach/reports/${reportId}/void`, { note: 'removed from dashboard' });
    mutate();
  };
  const rereadZerodha = async () => {
    setSyncNote('Reading…');
    try {
      await postClient('/api/proxy/partner/broker/sync');
      setSyncNote('Read.');
      mutate();
    } catch (err) {
      setSyncNote(err.info?.detail?.code === 'not_connected' ? 'No partner login held now.' : err.message);
    }
  };
  return (
    <div className="min-h-screen bg-gray-950 p-4 text-gray-100 sm:p-6">
      <div className="mx-auto max-w-6xl space-y-5">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            {navigateToDashboard && <button onClick={navigateToDashboard} className="rounded border border-gray-700 p-2 text-gray-300 hover:bg-gray-800" aria-label="Back"><ArrowLeft size={16} /></button>}
            <div>
              <h1 className="flex items-center gap-2 text-2xl font-bold text-white"><GraduationCap size={22} /> {partnerView ? 'Your trading review' : 'Partner Coach'}</h1>
              <p className="text-sm text-gray-400">{partnerView
                ? 'Your Zerodha trades against each card: what went well, what cost money, and what to do next time.'
                : 'What the partner did with each card, what the card said, and why the difference matters.'}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {WINDOWS.map((value) => (
              <button key={value} onClick={() => setDays(value)} className={`rounded border px-3 py-1.5 text-xs font-bold ${days === value ? 'border-teal-500 bg-teal-950 text-teal-100' : 'border-gray-700 text-gray-300'}`}>{value === 1 ? 'Today' : `${value}d`}</button>
            ))}
            {navigateToReview && <button onClick={navigateToReview} className="rounded border border-teal-700 px-3 py-1.5 text-xs font-bold text-teal-100">Partner's view</button>}
            <span className="rounded border border-red-700 bg-red-950 px-2 py-1 text-[10px] font-black text-red-100">COACHING ONLY · NO ORDERS</span>
          </div>
        </header>

        {error && <div className="rounded border border-red-800 bg-red-950/40 p-3 text-sm text-red-200">Coach data unavailable: {error.message}</div>}
        {isLoading && !data && <p className="text-sm text-gray-500">Loading…</p>}
        {data && !partnerView && (
          <div className="flex flex-wrap items-center gap-3 rounded border border-gray-800 bg-gray-900/60 p-3 text-xs text-gray-300">
            <span>{zerodhaLine(model.zerodha, today)}</span>
            {model.zerodha?.connected && <button onClick={rereadZerodha} className="rounded border border-teal-700 px-2 py-1 font-bold text-teal-100">Re-read Zerodha</button>}
            {syncNote && <span className="text-gray-500">{syncNote}</span>}
          </div>
        )}
        {data && !partnerView && !model.captureEnabled && <div className="rounded border border-amber-700 bg-amber-950/30 p-3 text-sm text-amber-200">Fill capture is off (PARTNER_FILL_CAPTURE_ENABLED): cards carry no buttons and only reports entered here are scored.</div>}

        {data && <>
          <section className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
            <Tile label="Cards sent" value={s.cards_delivered ?? 0} />
            <Tile label="Bought / skipped" value={`${s.cards_bought ?? 0} / ${(s.cards_skipped ?? 0) + (s.cards_not_traded ?? 0)}`} hint={`${s.cards_not_reported ?? 0} not reported`} />
            <Tile label="Off-card trades" value={s.off_card_trades ?? 0} />
            <Tile label={partnerView ? 'Your P&L' : 'Partner P&L'} value={formatRs(s.actual_pnl)} tone={pnlTone(s.actual_pnl)} hint={`${s.trades_scored ?? 0} trades with prices`} />
            <Tile label="Card plan, same cards" value={formatRs(s.plan_pnl_on_same_cards)} tone={pnlTone(s.plan_pnl_on_same_cards)} />
            <Tile label="Gap vs plan" value={formatRs(s.gap_vs_plan)} tone={pnlTone(s.gap_vs_plan)} />
            <Tile label="Cards followed" value={s.followed_cards ?? 0} hint={`unbought cards' plan: ${formatRs(s.unreported_cards_plan_pnl)}`} />
          </section>

          <section className="rounded-lg border border-gray-800 bg-gray-900/60 p-4">
            <h2 className="text-lg font-bold text-white">Patterns, costliest first</h2>
            {model.leaks.length === 0 ? <p className="mt-2 text-sm text-gray-400">No behaviour flags in this window.</p> : (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="text-gray-500"><tr><th className="p-2">Pattern</th><th className="p-2">Times</th><th className="p-2">Rupee effect</th><th className="p-2">What to do</th></tr></thead>
                  <tbody>{model.leaks.map((leak) => (
                    <tr key={leak.code} className="border-t border-gray-800">
                      <td className="p-2 font-bold text-amber-200">{leak.title}</td>
                      <td className="p-2 font-mono">{leak.count}</td>
                      <td className={`p-2 font-mono ${pnlTone(leak.impact_rs)}`}>{leak.priced ? formatRs(leak.impact_rs) : 'not priced'}</td>
                      <td className="p-2 text-gray-400">{leak.advice}</td>
                    </tr>))}</tbody>
                </table>
                <p className="mt-2 text-[11px] text-gray-500">A trade can carry several patterns, so the rupee effects overlap and do not add up to the total gap.</p>
              </div>
            )}
          </section>

          {model.days.map((day) => (
            <section key={day.day} className="space-y-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-gray-800 pb-2">
                <h2 className="text-lg font-bold text-white">{day.day}</h2>
                <p className="text-xs text-gray-400">Partner <span className={pnlTone(day.actual_pnl)}>{formatRs(day.actual_pnl)}</span> · card plan on the same cards <span className={pnlTone(day.plan_pnl_on_traded_cards)}>{formatRs(day.plan_pnl_on_traded_cards)}</span></p>
              </div>
              {day.day_flags?.length > 0 && <ul className="space-y-2">{day.day_flags.map((flag, index) => <Flag key={`${flag.code}-${index}`} flag={flag} />)}</ul>}
              {day.cards.map((item) => <CardRow key={item.advisory_id} item={item} onVoid={voidReport} who={partnerView ? 'You' : 'Partner'} />)}
              {day.off_card.map((item) => <CardRow key={item.key} item={item} onVoid={voidReport} who={partnerView ? 'You' : 'Partner'} />)}
            </section>
          ))}

          {!partnerView && <ReportForm cards={model.cardOptions} onSaved={() => mutate()} />}

          <section className="grid gap-3 text-xs text-gray-400 sm:grid-cols-2">
            <div className="rounded border border-gray-800 p-3">
              <p className="font-bold text-gray-300">How this is worked out</p>
              <p className="mt-1">Each card instruction is priced {model.assumptions.reaction_sec ?? 120} s after the message reached the partner, because a manual trader needs time to read and place the order. Card prices are {model.assumptions.card_prices}. Partner prices are {model.assumptions.partner_prices}.</p>
            </div>
            <div className="rounded border border-gray-800 p-3">
              <p className="font-bold text-gray-300">Data gaps</p>
              <p className="mt-1">{model.quality.superseded_by_zerodha ? `${model.quality.superseded_by_zerodha} Telegram report(s) replaced by Zerodha fills · ` : ''}{model.quality.estimated_prices ?? 0} estimated price(s) from taps · {model.quality.missing_prices ?? 0} missing · {model.quality.exits_without_buy ?? 0} exit(s) without a buy · {model.quality.open_without_exit ?? 0} open without an exit · {model.quality.cards_without_prices ?? 0} card(s) without option prices.</p>
            </div>
          </section>
        </>}
      </div>
    </div>
  );
}
