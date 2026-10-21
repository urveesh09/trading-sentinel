import React, { useState } from 'react';
import useSWR from 'swr';
import { ArrowLeft, BookOpen, GraduationCap, Lightbulb, ListChecks, Minus, ShieldAlert, TrendingDown, TrendingUp } from 'lucide-react';
import { fetcher } from '../api/client';
import { formatRs, pnlTone } from '../utils/partnerCoach';
import { buildReviewModel, formatDay, percent, reviewUrl, trendOf } from '../utils/partnerReview';
import PartnerCoach from './PartnerCoach';

// [O21-PL] The partner's own dashboard: today's learnings first. The lesson
// of the day (what happened, why it matters, what would have been better, the
// rule), what went well, each trade as a story and the cards not taken.
// "Progress" and "All details" are there for more. Read-only: nothing here
// places an order or changes a card.

const TABS = [['today', 'Today'], ['progress', 'Progress'], ['details', 'All details']];

function Section({ title, icon: Icon, children }) {
  return (
    <section className="rounded-lg border border-gray-800 bg-gray-900/70 p-4">
      <h2 className="flex items-center gap-2 text-base font-bold text-white">{Icon && <Icon size={18} />} {title}</h2>
      <div className="mt-3 space-y-3">{children}</div>
    </section>
  );
}

function Labeled({ label, children, tone = 'text-gray-200' }) {
  if (!children) return null;
  return (
    <div>
      <p className="text-[10px] font-bold uppercase tracking-wide text-gray-500">{label}</p>
      <p className={`mt-0.5 text-sm ${tone}`}>{children}</p>
    </div>
  );
}

function Example({ example, showOption }) {
  return (
    <div className="space-y-2">
      {showOption && example.option && <p className="font-mono text-xs text-gray-400">{example.time} · {example.option}</p>}
      <Labeled label="What happened">{example.what}</Labeled>
      <Labeled label="Why it matters">{example.why}</Labeled>
      <Labeled label="What would have been better" tone="text-emerald-200">{example.better}</Labeled>
    </div>
  );
}

function Lesson({ lesson }) {
  const [first, ...others] = lesson.examples;
  return (
    <article className="rounded-lg border border-amber-700 bg-amber-950/20 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-lg font-bold text-amber-100">{lesson.title}{lesson.count > 1 ? ` · ${lesson.count} times` : ''}</h3>
        {lesson.impact_rs != null && <span className={`font-mono text-sm ${pnlTone(lesson.impact_rs)}`}>{formatRs(lesson.impact_rs)}</span>}
      </div>
      <div className="mt-3 space-y-4">
        <Example example={first} showOption />
        {others.map((example, index) => (
          <div key={index} className="border-t border-amber-900/60 pt-3"><Example example={example} showOption /></div>
        ))}
        {lesson.also?.length > 0 && (
          <div className="border-t border-amber-900/60 pt-3">
            <p className="text-[10px] font-bold uppercase tracking-wide text-gray-500">Also on this trade</p>
            <ul className="mt-1 space-y-2">
              {lesson.also.map((also, index) => (
                <li key={`${also.code}-${index}`} className="text-sm text-gray-200">
                  <span className="font-bold text-amber-200">{also.title}.</span> {also.what} <span className="text-emerald-200">{also.better}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        <p className="rounded border border-teal-700 bg-teal-950/40 p-3 text-sm font-bold text-teal-100">Next time: {lesson.rule}</p>
      </div>
    </article>
  );
}

function SmallLesson({ lesson }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="rounded border border-gray-800 bg-gray-950 p-3">
      <button onClick={() => setOpen(!open)} className="flex w-full flex-wrap items-baseline justify-between gap-2 text-left">
        <span className="text-sm font-bold text-amber-200">{lesson.title}{lesson.count > 1 ? ` · ${lesson.count} times` : ''}</span>
        <span className={`font-mono text-xs ${pnlTone(lesson.impact_rs)}`}>{lesson.impact_rs != null ? formatRs(lesson.impact_rs) : ''}</span>
      </button>
      <p className="mt-1 text-xs text-gray-300">{lesson.examples[0]?.what}</p>
      {open && <div className="mt-3 space-y-3">{lesson.examples.map((example, index) => <Example key={index} example={example} showOption />)}</div>}
      <p className="mt-2 text-xs text-teal-200">Next time: {lesson.rule}</p>
      {!open && <button onClick={() => setOpen(true)} className="mt-1 text-[11px] text-gray-500 underline">Why, and what would have been better</button>}
    </li>
  );
}

function Story({ story }) {
  return (
    <article className="rounded-lg border border-gray-800 bg-gray-950 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-mono text-sm font-bold text-white">{story.time} · {story.option}{story.on_card ? '' : ' · no card'}</h3>
        {story.pnl != null && <span className={`font-mono text-sm font-bold ${pnlTone(story.pnl)}`}>{formatRs(story.pnl)}</span>}
      </div>
      <ol className="mt-2 space-y-1 border-l border-gray-800 pl-3">
        {story.timeline.map((event, index) => (
          <li key={index} className={`text-xs ${event.who === 'card' ? 'text-sky-200' : 'text-gray-200'}`}>
            <span className="mr-2 font-mono text-gray-500">{event.at}</span>{event.text}
          </li>
        ))}
      </ol>
      <p className="mt-2 text-xs text-gray-400">{story.result}</p>
      {(story.mistakes.length > 0 || story.good.length > 0) && (
        <p className="mt-1 text-[11px]">
          {story.mistakes.map((title) => <span key={title} className="mr-2 text-amber-300">• {title}</span>)}
          {story.good.map((title) => <span key={title} className="mr-2 text-emerald-300">✓ {title}</span>)}
        </p>
      )}
    </article>
  );
}

export function Today({ model }) {
  const { headline, lesson } = model;
  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-gray-800 bg-gray-900/70 p-4">
        <p className="text-xs text-gray-400">{formatDay(model.day)}{model.source === 'ZERODHA' ? ' · from your Zerodha orders' : ''}</p>
        {headline.pnl != null && <p className={`mt-1 text-3xl font-black ${pnlTone(headline.pnl)}`}>{formatRs(headline.pnl)}</p>}
        <p className="mt-1 text-sm text-gray-200">{headline.text}</p>
      </section>

      {lesson && (
        <Section title="Your lesson for today" icon={Lightbulb}>
          <Lesson lesson={lesson} />
        </Section>
      )}

      {model.wellDone.length > 0 && (
        <Section title="What you did well" icon={ListChecks}>
          <ul className="space-y-1">
            {model.wellDone.map((good, index) => (
              <li key={`${good.code}-${index}`} className="text-sm text-emerald-200">
                ✓ <span className="font-bold">{good.title}</span>{good.option ? ` (${good.option})` : ''}: <span className="text-gray-300">{good.reason}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {model.moreLessons.length > 0 && (
        <Section title="More to learn from today" icon={ShieldAlert}>
          <ul className="space-y-2">{model.moreLessons.map((item) => <SmallLesson key={item.code} lesson={item} />)}</ul>
        </Section>
      )}

      {model.trades.length > 0 && (
        <Section title="Your trades, step by step" icon={BookOpen}>
          {model.trades.map((story, index) => <Story key={`${story.option}-${index}`} story={story} />)}
        </Section>
      )}

      {model.untaken.cards?.length > 0 && (
        <Section title="Cards you did not take">
          <p className="text-xs text-gray-400">{model.untaken.text}</p>
          <ul className="space-y-1">
            {model.untaken.cards.map((card, index) => (
              <li key={index} className="text-xs text-gray-300">
                <span className="font-mono text-gray-500">{card.time}</span> {card.option} · {card.status}
                {card.plan_pnl != null && <span className={`ml-2 font-mono ${pnlTone(card.plan_pnl)}`}>{formatRs(card.plan_pnl)} on 1 lot</span>}
                {card.note && <span className="ml-2 text-gray-500">— {card.note}</span>}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {model.notes.length > 0 && <ul className="space-y-1 text-[11px] text-gray-500">{model.notes.map((note) => <li key={note}>{note}</li>)}</ul>}
    </div>
  );
}

function TrendIcon({ trend }) {
  if (trend === 'fewer') return <TrendingDown size={14} className="text-emerald-300" />;
  if (trend === 'more') return <TrendingUp size={14} className="text-red-300" />;
  return <Minus size={14} className="text-gray-500" />;
}

export function Progress({ progress }) {
  return (
    <div className="space-y-4">
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ['Trades', progress.trades, 'text-white'],
          ['Followed the card', `${percent(progress.cleanRate)} (${progress.cleanTrades})`, 'text-emerald-200'],
          ['Clean days in a row', progress.streak, 'text-emerald-200'],
          ['Your P&L', formatRs(progress.pnl), pnlTone(progress.pnl)],
        ].map(([label, value, tone]) => (
          <div key={label} className="rounded-lg border border-gray-800 bg-gray-900/80 p-3">
            <p className="text-[10px] uppercase tracking-wide text-gray-500">{label}</p>
            <p className={`mt-1 text-lg font-bold ${tone}`}>{value}</p>
          </div>
        ))}
      </section>
      <Section title="Your patterns: this week against last week" icon={ShieldAlert}>
        {progress.patterns.length === 0 ? <p className="text-sm text-gray-400">No mistakes flagged in this window.</p> : (
          <ul className="space-y-2">
            {progress.patterns.map((pattern) => {
              const trend = trendOf(pattern);
              return (
                <li key={pattern.code} className="rounded border border-gray-800 bg-gray-950 p-3">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="text-sm font-bold text-amber-200">{pattern.title}</span>
                    <span className="flex items-center gap-1 text-xs"><TrendIcon trend={pattern.trend} />
                      <span className={trend.tone}>{pattern.last_7_days} this week, {pattern.previous_7_days} last week ({trend.label})</span>
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-gray-400">{pattern.total} time{pattern.total === 1 ? '' : 's'} in the window{pattern.priced ? ` · ${formatRs(pattern.impact_rs)}` : ''}</p>
                  <p className="mt-1 text-xs text-teal-200">Next time: {pattern.rule}</p>
                </li>
              );
            })}
          </ul>
        )}
      </Section>
      <Section title="Day by day">
        <ul className="space-y-1">
          {progress.days.map((day) => (
            <li key={day.day} className="flex flex-wrap items-baseline gap-3 text-xs text-gray-300">
              <span className="w-24 font-mono text-gray-500">{formatDay(day.day)}</span>
              <span>{day.trades} trade{day.trades === 1 ? '' : 's'}</span>
              <span className={`font-mono ${pnlTone(day.pnl)}`}>{formatRs(day.pnl)}</span>
              <span className={day.clean ? 'text-emerald-300' : 'text-amber-300'}>{day.trades ? (day.clean ? '✓ clean' : `${day.mistakes} mistake${day.mistakes === 1 ? '' : 's'}`) : 'no trades'}</span>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}

export default function PartnerReview({ navigateBack }) {
  const [day, setDay] = useState('');
  const [tab, setTab] = useState('today');
  const { data, error, isLoading } = useSWR(reviewUrl(day), fetcher, { revalidateOnFocus: false });
  const model = buildReviewModel(data);
  if (tab === 'details') {
    return <PartnerCoach partnerView navigateToDashboard={() => setTab('today')} />;
  }
  return (
    <div className="min-h-screen bg-gray-950 p-4 text-gray-100 sm:p-6">
      <div className="mx-auto max-w-3xl space-y-4">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            {navigateBack && <button onClick={navigateBack} className="rounded border border-gray-700 p-2 text-gray-300 hover:bg-gray-800" aria-label="Back"><ArrowLeft size={16} /></button>}
            <h1 className="flex items-center gap-2 text-2xl font-bold text-white"><GraduationCap size={22} /> Your trading review</h1>
          </div>
          {model.days.length > 0 && (
            <select value={model.day} onChange={(event) => setDay(event.target.value)} className="rounded border border-gray-700 bg-gray-900 p-2 text-sm text-gray-100" aria-label="Day">
              {model.days.map((value) => <option key={value} value={value}>{formatDay(value)}</option>)}
            </select>
          )}
        </header>
        <nav className="flex gap-2">
          {TABS.map(([key, label]) => (
            <button key={key} onClick={() => setTab(key)} className={`rounded border px-3 py-1.5 text-xs font-bold ${tab === key ? 'border-teal-500 bg-teal-950 text-teal-100' : 'border-gray-700 text-gray-300'}`}>{label}</button>
          ))}
        </nav>
        {error && <div className="rounded border border-red-800 bg-red-950/40 p-3 text-sm text-red-200">Your review is unavailable: {error.message}</div>}
        {isLoading && !data && <p className="text-sm text-gray-500">Loading your review…</p>}
        {data && tab === 'today' && <Today model={model} />}
        {data && tab === 'progress' && <Progress progress={model.progress} />}
        <p className="text-center text-[10px] text-gray-600">Coaching only. Nothing here places an order.</p>
      </div>
    </div>
  );
}
