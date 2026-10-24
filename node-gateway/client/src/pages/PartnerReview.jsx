import React, { useState } from 'react';
import useSWR from 'swr';
import { ArrowLeft, BarChart3, BookOpen, ChevronLeft, ChevronRight, ClipboardList, Crosshair, Download, GraduationCap, Lightbulb, ListChecks, Minus, ShieldAlert, TrendingDown, TrendingUp } from 'lucide-react';
import { fetcher } from '../api/client';
import { formatRs, pnlTone } from '../utils/partnerCoach';
import {
  LEVEL_STYLE, LEVEL_TEXT, REVIEW_DAYS_URL, buildReviewModel, chartGeometry, dayList, dayNeighbours, dayWords, formatDay,
  formatPrice, minutesLabel, percent, reviewPdfUrl, reviewUrl, rulesAsOf, scoreTone, signedPercent, syncNote, syncRefreshMs,
  trendOf, watchNote,
} from '../utils/partnerReview';
import PartnerCoach from './PartnerCoach';

// [O21-PL] The partner's own dashboard: today's learnings first. The lesson
// of the day (what happened, why it matters, what would have been better, the
// rule), what went well, each trade as a story and the cards not taken.
// "Progress" and "All details" are there for more. Read-only: nothing here
// places an order or changes a card.
// [O21-PX] Also: the one rule to focus on tomorrow, rules kept today (process,
// not money), each trade's price chart with the buys, sells and stops, what
// the option did before, during and after the trade, the day's orders, and
// the window's statistics with a plain line for each pattern they show.
// [O23-PH] Earlier days: step back and forward a day or pick one (the last
// 120 days), or open one from Progress; an earlier day reads "that day".
// [O23-PD] "Download PDF" saves the open day's review as a PDF.
// [O23-PM] Each rule kept says in a line what it means.

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

function Stat({ label, value, tone = 'text-white', note }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900/80 p-3">
      <p className="text-[10px] uppercase tracking-wide text-gray-500">{label}</p>
      <p className={`mt-1 text-lg font-bold ${tone}`}>{value}</p>
      {note && <p className="text-[10px] text-gray-500">{note}</p>}
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

// [O21-PX] The option's price around the trade: the line, your buys (green)
// and sells (red), and the card's and your own levels as dashed lines.
export function PriceChart({ chart }) {
  const geo = chartGeometry(chart);
  if (!geo) return null;
  return (
    <figure className="mt-2 rounded border border-gray-800 bg-gray-950/60 p-2">
      <svg viewBox={`0 0 ${geo.width} ${geo.height}`} className="h-40 w-full" role="img"
        aria-label={`Option price from ${geo.start} to ${geo.end}, with your buys and sells`}>
        {geo.levels.map((level) => (
          <g key={`${level.label}-${level.price}`}>
            <line x1="0" x2={geo.width} y1={level.y} y2={level.y} className={LEVEL_STYLE[level.kind] || 'stroke-gray-500'} strokeDasharray="4 3" strokeWidth="1" />
            <text x={geo.width - 2} y={level.y - 2} textAnchor="end" fontSize="8" className={LEVEL_TEXT[level.kind] || 'fill-gray-400'}>{level.label} {formatPrice(level.price)}</text>
          </g>
        ))}
        <path d={geo.path} fill="none" className="stroke-gray-200" strokeWidth="1.5" strokeLinejoin="round" />
        {geo.marks.map((mark, index) => (
          <g key={`${mark.kind}-${index}`}>
            <circle cx={mark.x} cy={mark.y} r="4" className={mark.kind === 'buy' ? 'fill-emerald-400' : 'fill-red-400'} />
            <title>{`${mark.kind === 'buy' ? 'You bought' : 'You sold'} at ${formatPrice(mark.price)} (${mark.at})`}</title>
          </g>
        ))}
      </svg>
      <figcaption className="mt-1 flex flex-wrap justify-between gap-2 text-[10px] text-gray-500">
        <span>{geo.start}</span>
        <span><span className="text-emerald-300">●</span> your buy · <span className="text-red-300">●</span> your sell{geo.hiddenLevels.length ? ` · off the chart: ${geo.hiddenLevels.map((l) => `${l.label} ${formatPrice(l.price)}`).join(', ')}` : ''}</span>
        <span>{geo.end}</span>
      </figcaption>
    </figure>
  );
}

function Checks({ checks }) {
  if (!checks?.length) return null;
  return (
    <p className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
      {checks.map((check) => (
        <span key={check.key} className={`rounded border px-1.5 py-0.5 ${check.kept ? 'border-emerald-800 text-emerald-200' : 'border-red-800 text-red-200'}`}>
          {check.kept ? '✓' : '✗'} {check.name}
        </span>
      ))}
    </p>
  );
}

function Story({ story }) {
  const label = story.reentry ? ' · bought again on the card' : (story.on_card ? '' : ' · no card');
  return (
    <article className="rounded-lg border border-gray-800 bg-gray-950 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-mono text-sm font-bold text-white">{story.time} · {story.option}{label}</h3>
        {story.pnl != null && <span className={`font-mono text-sm font-bold ${pnlTone(story.pnl)}`}>{formatRs(story.pnl)}</span>}
      </div>
      <Checks checks={story.checks} />
      {story.chart && <PriceChart chart={story.chart} />}
      {story.option_lines?.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-xs text-gray-300">
          {story.option_lines.map((line) => <li key={line}>{line}</li>)}
        </ul>
      )}
      <ol className="mt-2 space-y-1 border-l border-gray-800 pl-3">
        {story.timeline.map((event, index) => (
          <li key={index} className={`text-xs ${event.who === 'card' ? 'text-sky-200' : event.who === 'assistant' ? 'text-teal-200' : 'text-gray-200'}`}>
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

function Focus({ focus }) {
  if (!focus) return null;
  return (
    <section className="rounded-lg border border-teal-600 bg-teal-950/40 p-4">
      <p className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-wide text-teal-300"><Crosshair size={14} /> Tomorrow, focus on one thing</p>
      <p className="mt-1 text-base font-bold text-teal-50">{focus.rule}</p>
      <p className="mt-1 text-xs text-teal-200/80">{focus.text}</p>
    </section>
  );
}

function Headline({ model }) {
  const { headline, score, stats, account } = model;
  return (
    <section className="rounded-lg border border-gray-800 bg-gray-900/70 p-4">
      <p className="text-xs text-gray-400">{formatDay(model.day)}{model.source === 'ZERODHA' ? ' · from your Zerodha orders' : ''}</p>
      <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
        {headline.pnl != null && <p className={`text-3xl font-black ${pnlTone(headline.pnl)}`}>{formatRs(headline.pnl)}</p>}
        {score && (
          <div className="text-right">
            <p className={`text-2xl font-black ${scoreTone(score.pct)}`}>{score.kept}/{score.of}</p>
            <p className="text-[10px] uppercase tracking-wide text-gray-500">rules kept</p>
          </div>
        )}
      </div>
      <p className="mt-1 text-sm text-gray-200">{headline.text}</p>
      {(stats || account) && (
        <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400">
          {stats && <span>{stats.wins} win{stats.wins === 1 ? '' : 's'} · {stats.losses} loss{stats.losses === 1 ? '' : 'es'}</span>}
          {stats?.charges != null && <span>Charges {formatRs(stats.charges, { signed: false })}</span>}
          {stats?.time_in_market_min != null && <span>In the market {minutesLabel(stats.time_in_market_min)}</span>}
          {account?.pnl_pct != null && <span className={pnlTone(account.pnl_pct)}>{signedPercent(account.pnl_pct)} of your account</span>}
        </p>
      )}
    </section>
  );
}

function RulesKept({ score, title }) {
  if (!score) return null;
  return (
    <Section title={title} icon={ListChecks}>
      <p className="text-xs text-gray-400">Each trade is checked against the same rules. This counts how you traded, not whether it made money.{rulesAsOf(score)}</p>
      <ul className="grid gap-1 sm:grid-cols-2">
        {score.rules.map((rule) => (
          <li key={rule.key} className="rounded border border-gray-800 bg-gray-950 px-2 py-1">
            <div className="flex items-baseline justify-between gap-2 text-sm">
              <span className={rule.kept === rule.of ? 'text-emerald-200' : 'text-amber-200'}>{rule.kept === rule.of ? '✓' : '✗'} {rule.name}</span>
              <span className="font-mono text-xs text-gray-400">{rule.kept}/{rule.of}</span>
            </div>
            {rule.means && <p className="mt-0.5 text-[11px] leading-snug text-gray-500">{rule.means}</p>}
          </li>
        ))}
      </ul>
    </Section>
  );
}

function Orders({ orders, title }) {
  if (!orders) return null;
  return (
    <Section title={title} icon={ClipboardList}>
      <p className="text-sm text-gray-300">
        {orders.placed} placed · {orders.filled} filled · {orders.rejected.length} refused · {orders.cancelled_unfilled} cancelled unfilled
        {orders.modified ? ` · ${orders.modified} changed after placing` : ''}{orders.market ? ` · ${orders.market} at market price` : ''}
      </p>
      {orders.rejected.length > 0 && (
        <ul className="space-y-1">
          {orders.rejected.map((order, index) => (
            <li key={index} className="text-xs text-red-200">
              <span className="mr-2 font-mono text-gray-500">{order.at}</span>{order.side === 'BUY' ? 'Buy' : 'Sell'} {order.quantity} {order.tradingsymbol} refused{order.plain || order.reason ? `: ${order.plain || order.reason}` : ''}
              {order.plain && order.reason && <span className="block text-gray-500">Zerodha: {order.reason}</span>}
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

export function Today({ model }) {
  const { lesson } = model;
  const words = dayWords(model.past);
  return (
    <div className="space-y-4">
      <Headline model={model} />

      {model.newest && <Focus focus={model.focus} />}

      {lesson && (
        <Section title={words.lesson} icon={Lightbulb}>
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
        <Section title={words.more} icon={ShieldAlert}>
          <ul className="space-y-2">{model.moreLessons.map((item) => <SmallLesson key={item.code} lesson={item} />)}</ul>
        </Section>
      )}

      <RulesKept score={model.score} title={words.rules} />

      {model.trades.length > 0 && (
        <Section title="Your trades, step by step" icon={BookOpen}>
          {model.trades.map((story, index) => <Story key={`${story.option}-${index}`} story={story} />)}
        </Section>
      )}

      <Orders orders={model.orders} title={words.orders} />

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

function Split({ label, bucket }) {
  return (
    <li className="flex items-baseline justify-between gap-2 text-sm">
      <span className="text-gray-300">{label}</span>
      <span className="font-mono text-xs text-gray-400">{bucket?.trades ?? 0} trade{bucket?.trades === 1 ? '' : 's'} · <span className={pnlTone(bucket?.pnl)}>{formatRs(bucket?.pnl)}</span></span>
    </li>
  );
}

function WindowStats({ stats }) {
  if (!stats || !stats.trades) return null;
  return (
    <>
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Win rate" value={percent(stats.win_rate)} note={`${stats.wins} won · ${stats.losses} lost`} />
        <Stat label="Average win" value={formatRs(stats.avg_win)} tone={pnlTone(stats.avg_win)} />
        <Stat label="Average loss" value={formatRs(stats.avg_loss)} tone={pnlTone(stats.avg_loss)} />
        <Stat label="Per trade" value={formatRs(stats.per_trade)} tone={pnlTone(stats.per_trade)} note={stats.charges != null ? `after ${formatRs(stats.charges, { signed: false })} charges` : undefined} />
      </section>
      {stats.insights?.length > 0 && (
        <Section title="What your numbers say" icon={BarChart3}>
          <ul className="space-y-2">
            {stats.insights.map((line) => <li key={line} className="rounded border border-gray-800 bg-gray-950 p-2 text-sm text-gray-200">{line}</li>)}
          </ul>
        </Section>
      )}
      <Section title="Where the results came from">
        <ul className="space-y-1">
          <Split label="With a card" bucket={stats.on_card} />
          <Split label="Without a card" bucket={stats.off_card} />
          <Split label="Within 30 min of a loss" bucket={stats.after_loss} />
          <Split label="All other trades" bucket={stats.other} />
        </ul>
        <ul className="space-y-1 border-t border-gray-800 pt-2">
          {stats.by_time.map((bucket) => <Split key={bucket.label} label={bucket.label} bucket={bucket} />)}
        </ul>
        {(stats.hold_min?.wins != null || stats.hold_min?.losses != null) && (
          <p className="border-t border-gray-800 pt-2 text-xs text-gray-400">
            Typical hold: winners {minutesLabel(stats.hold_min.wins)} · losers {minutesLabel(stats.hold_min.losses)}
          </p>
        )}
      </Section>
    </>
  );
}

export function Progress({ progress, focus, onOpenDay }) {
  return (
    <div className="space-y-4">
      <Focus focus={focus} />
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Trades" value={progress.trades} />
        <Stat label="Followed the card" value={`${percent(progress.cleanRate)} (${progress.cleanTrades})`} tone="text-emerald-200" />
        <Stat label="Clean days in a row" value={progress.streak} tone="text-emerald-200" />
        <Stat label="Your P&L" value={formatRs(progress.pnl)} tone={pnlTone(progress.pnl)} />
      </section>
      <WindowStats stats={progress.stats} />
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
        {onOpenDay && progress.days.length > 0 && <p className="text-xs text-gray-400">Tap a day to open its review.</p>}
        <ul className="space-y-1">
          {progress.days.map((day) => (
            <li key={day.day}>
              <button type="button" onClick={onOpenDay ? () => onOpenDay(day.day) : undefined} disabled={!onOpenDay}
                className="flex w-full flex-wrap items-baseline gap-3 rounded px-1 py-0.5 text-left text-xs text-gray-300 enabled:hover:bg-gray-800">
                <span className="w-24 font-mono text-gray-500">{formatDay(day.day)}</span>
                <span>{day.trades} trade{day.trades === 1 ? '' : 's'}</span>
                <span className={`font-mono ${pnlTone(day.pnl)}`}>{formatRs(day.pnl)}</span>
                <span className={day.clean ? 'text-emerald-300' : 'text-amber-300'}>{day.trades ? (day.clean ? '✓ clean' : `${day.mistakes} mistake${day.mistakes === 1 ? '' : 's'}`) : 'no trades'}</span>
                {day.rules_kept_pct != null && <span className={scoreTone(day.rules_kept_pct)}>rules kept {day.rules_kept_pct}%</span>}
                {onOpenDay && <ChevronRight size={12} className="ml-auto self-center text-gray-600" />}
              </button>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}

// [O23-PH] Step a day back or forward, or pick any day with a review.
function DayBar({ days, day, onPick }) {
  if (!days.length || !day) return null;
  const { older, newer } = dayNeighbours(days, day);
  const step = 'flex items-center gap-1 rounded border border-gray-700 px-2 py-2 text-xs text-gray-200 enabled:hover:bg-gray-800 disabled:opacity-40';
  return (
    <div className="flex items-center gap-2" role="group" aria-label="Choose a day">
      <button type="button" className={step} disabled={!older} onClick={() => onPick(older)} aria-label="Earlier day">
        <ChevronLeft size={14} /><span className="hidden sm:inline">Earlier</span>
      </button>
      <select value={day} onChange={(event) => onPick(event.target.value)} aria-label="Day"
        className="min-w-0 flex-1 rounded border border-gray-700 bg-gray-900 p-2 text-sm text-gray-100">
        {days.map((value) => <option key={value} value={value}>{formatDay(value)}</option>)}
      </select>
      <button type="button" className={step} disabled={!newer} onClick={() => onPick(newer)} aria-label="Later day">
        <span className="hidden sm:inline">Later</span><ChevronRight size={14} />
      </button>
    </div>
  );
}

// [O23-PD] The open day's review as a PDF. While today's orders are still
// being read the file would be partial, so it waits.
function PdfButton({ model }) {
  if (!model.day) return null;
  const busy = model.day === model.today && syncRefreshMs(model.sync) > 0;
  const look = 'flex items-center gap-1.5 rounded border px-3 py-2 text-xs font-bold';
  if (busy) {
    return <span className={`${look} border-gray-800 text-gray-500`} title="Your orders are still loading">
      <Download size={14} /> PDF after the update</span>;
  }
  return (
    <a href={reviewPdfUrl(model.day)} download className={`${look} border-teal-700 text-teal-100 hover:bg-teal-950`}>
      <Download size={14} /> Download PDF
    </a>
  );
}

export default function PartnerReview({ navigateBack }) {
  const [day, setDay] = useState('');
  const [tab, setTab] = useState('today');
  // [A22-P4] While the login's background read runs, refresh every few seconds.
  const { data, error, isLoading } = useSWR(reviewUrl(day), fetcher, {
    revalidateOnFocus: false, refreshInterval: (latest) => syncRefreshMs(latest?.sync),
  });
  // [O23-PH] The 120-day list, read once; the review's own days fill in until it arrives.
  const { data: history } = useSWR(REVIEW_DAYS_URL, fetcher, { revalidateOnFocus: false });
  const model = buildReviewModel(data);
  const days = dayList(model.days, history?.days, model.day);
  const syncText = syncNote(model.sync);
  const openDay = (value) => { setDay(value); setTab('today'); };
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
          {data && <PdfButton model={model} />}
        </header>
        <DayBar days={days} day={model.day} onPick={openDay} />
        <nav className="flex gap-2">
          {TABS.map(([key, label]) => (
            <button key={key} onClick={() => setTab(key)} className={`rounded border px-3 py-1.5 text-xs font-bold ${tab === key ? 'border-teal-500 bg-teal-950 text-teal-100' : 'border-gray-700 text-gray-300'}`}>
              {key === 'today' && model.past ? formatDay(model.day) : label}
            </button>
          ))}
        </nav>
        {error && <div className="rounded border border-red-800 bg-red-950/40 p-3 text-sm text-red-200">Your review is unavailable: {error.message}</div>}
        {isLoading && !data && <p className="text-sm text-gray-500">Loading your review…</p>}
        {syncText && <p className="rounded border border-sky-900 bg-sky-950/40 p-2 text-xs text-sky-200" role="status">{syncText}</p>}
        {model.watch && !model.past && <p className="rounded border border-teal-900 bg-teal-950/40 p-2 text-xs text-teal-200" role="status">{watchNote(model.watch)}</p>}
        {data && tab === 'today' && <Today model={model} />}
        {data && tab === 'progress' && <Progress progress={model.progress} focus={model.focus} onOpenDay={openDay} />}
        <p className="text-center text-[10px] text-gray-600">Coaching only. Nothing here places an order.</p>
      </div>
    </div>
  );
}
