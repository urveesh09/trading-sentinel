"""Penny research v1: causal continuous Smart books and own-cash daily theses.

Research only. No scheduler, broker or notification imports. Candle prices are
declared execution proxies; unavailable rows never establish actual market fills.
Historical replay modules and runtime strategy bindings remain unchanged.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta
import math
from statistics import median

from adaptive_penny_policy import CompletedBar
from daily_portfolio import (BookConfig, DailySignal, RestingLevel, bars_by_ticker,
                             calendar_from, penny_cnc_costs, run_daily_book)
from penny_engine_breakout import _rsi_14_wilder
from penny_lifecycle_replay import (PennyLifecycleConfig, _Replay, _TickerDay,
                                    _aware, _summary)
from penny_profit_lock import decide as profit_lock
from penny_shadow import _costs_from_snapshot, _execution_snapshot
from penny_smart_book import new_book, step_book
from penny_smart_policy import SMART_PARAMS
from penny_smart_v2 import SMART_V2_PARAMS

VERSION = "PENNY_RESEARCH_20261104_V1"


def financial_summary(trades, curve, bankroll):
    closed = [t for t in trades if t.get('status') == 'CLOSED']
    profits = [t['net_pnl'] for t in closed]
    peak, dd = bankroll, 0.0
    for _, equity in curve:
        peak = max(peak, equity)
        dd = max(dd, peak - equity)
    gains, losses = sum(max(p, 0) for p in profits), -sum(min(p, 0) for p in profits)
    return {'closed': len(closed), 'net': round(sum(profits), 4),
            'ex_best': round(sum(profits) - max([0.0, *profits]), 4),
            'fees': round(sum(t.get('costs', 0) for t in closed), 4),
            'drawdown': round(dd, 4), 'wins': sum(p > 0 for p in profits),
            'profit_factor': round(gains / losses, 4) if losses else None,
            'final_equity': round(curve[-1][1] if curve else bankroll, 4),
            'unresolved': sum(t.get('status') != 'CLOSED' for t in trades),
            'exit_reasons': dict(Counter(t.get('exit_reason') for t in trades))}


def smart_rollover(state, day):
    """Same flat-book equity carry as the runtime; never refill a losing book."""
    if state['day'] != day and not state['positions']:
        equity = state['bankroll'] + state['realized']
        if equity > 0:
            return new_book(day, equity, state['execution'])
    return state


def run_smart(intraday, daily, tickers, *, start, end, params=SMART_V2_PARAMS,
              bankroll=2000.0, spread_bps=10.0, complete_only=False):
    """Continuous runtime pure book over causal minute quotes; no fake depth.

    Half the modeled spread is paid on each side. Quote exists only at an
    actually traded minute open. Gaps are neither filled nor perfect exits.
    Missing final exits carry to the next observed session, as pending risk.
    """
    execution = _execution_snapshot('PENNY_RESEARCH_CANDLE_PROXY')
    cost = lambda e, x, q: _costs_from_snapshot(e, x, q, execution)
    state = new_book(start, bankroll, execution)
    selected = defaultdict(list)
    exclusions = Counter()
    for row in intraday.coverage:
        day, ticker = row['trading_date'], row['ticker']
        if not start <= day <= end or ticker not in tickers:
            continue
        allowed = ('COMPLETE',) if complete_only else ('COMPLETE', 'PARTIAL')
        if row['status'] not in allowed or ticker in daily.invalid:
            exclusions[row['status']] += 1
            continue
        selected[day].append(ticker)
    trades, curve, daily_results, event_counts = [], [], [], Counter()
    half = spread_bps / 20000
    for day in sorted(selected):
        state = smart_rollover(state, day)
        names = sorted(set(selected[day]) | set(state['positions']))
        bars = {t: intraday.bars.get((t, day), ()) for t in names}
        tds = {t: _TickerDay(bs) for t, bs in bars.items() if bs}
        cbars = {t: [CompletedBar(f'{t}|{b.start.isoformat()}', b.start, b.available_at,
                                  b.open, b.high, b.low, b.close, b.volume) for b in bs]
                 for t, bs in bars.items()}
        medians = {}
        for t in names:
            prior = daily.known_before(t, date.fromisoformat(day),
                                       since=date.fromisoformat(day) - timedelta(days=35))
            medians[t] = median([b.volume for b in prior[-20:]]) if len(prior) >= 5 else 0
        recorded = len(state['trades'])
        for minute in range(556, 931):
            rolled = smart_rollover(state, day)
            if rolled is not state:
                state, recorded = rolled, 0
            now = _aware(date.fromisoformat(day), minute)
            observations, quotes = {}, {}
            for t, td in tds.items():
                n = td.completed_count(minute)
                if n:
                    observations[t] = {'bars': cbars[t][:n], 'median_volume': medians[t]}
                _, bar = td.bar_at(minute)
                if bar is not None and bar.executable:
                    quotes[t] = {'entry': bar.open * (1 + half),
                                 'exit': bar.open * (1 - half), 'executable': True}
            state, events = step_book(state, observations, quotes, now=now, cost=cost,
                                      params=params, allow_entries=minute < 855)
            event_counts.update(e['kind'] for e in events)
            for row in state['trades'][recorded:]:
                p = row['thesis']
                trades.append({'ticker': p['ticker'], 'entry_fill_ts': p['entry_at'],
                               'exit_fill_ts': row['exit_at'], 'entry_fill_price': p['entry_price'],
                               'exit_fill_price': row['exit_price'], 'shares': p['shares_initial'],
                               'net_pnl': row['net_pnl'], 'costs': row['costs'],
                               'exit_reason': row['exit_reason'], 'status': 'CLOSED'})
            recorded = len(state['trades'])
            if state.get('marked_pnl') is not None:
                equity = state['bankroll'] + state['marked_pnl']
                curve.append((now.isoformat(), equity))
        equity = state['bankroll'] + state['realized'] + sum(
            (p['mark'] - p['thesis']['entry_price']) * p['thesis']['shares_open']
            - cost(p['thesis']['entry_price'], p['mark'], p['thesis']['shares_open'])
            for p in state['positions'].values())
        daily_results.append({'date': day, 'equity': round(equity, 4),
                              'open': len(state['positions']),
                              'halted': state.get('daily_loss_latched', False)})
    for t, p in state['positions'].items():
        trades.append({'ticker': t, 'status': 'UNRESOLVED', 'exit_reason': 'MISSING_EXIT_EVIDENCE'})
    return {'version': VERSION, 'scope': 'BAR_LIFECYCLE_PARTIAL', 'params': asdict(params),
            'bankroll': bankroll, 'spread_bps': spread_bps, 'complete_only': complete_only,
            'summary': financial_summary(trades, curve, bankroll), 'trades': trades,
            'daily': daily_results, 'curve': curve, 'events': dict(event_counts),
            'exclusions': dict(exclusions), 'final_state': state}


class CurrentClassicReplay(_Replay):
    """Add current pure profit-lock monitor to the preserved old replay."""
    def _exit_via_market(self, trade, td, boundary, reason, day):
        # Historical adapter can book a future gap fill immediately. This
        # research reference refuses it rather than release future cash early.
        index, bar = td.bar_at(boundary)
        if bar is None or not bar.executable:
            trade.update(status='UNRESOLVED', exit_reason='MISSING_CURRENT_EXIT:'+reason)
            self.missing_exit = True
            return
        self._close(trade, td, index, bar.open, reason, _aware(day,boundary))

    def _admit(self, *args):
        if getattr(self, 'missing_exit', False):
            return 'UNRESOLVED_EXPOSURE_BLOCK'
        return super()._admit(*args)

    def _check_stop(self, trade, td, boundary, now, day):
        ltp, executable = td.ltp_at(boundary)
        if executable and ltp is not None:
            fees = _costs_from_snapshot(trade['entry_fill_price'], trade['entry_fill_price'],
                                        trade['shares'], self.execution)
            result = profit_lock(entry=trade['entry_fill_price'],
                                 initial_stop=trade['initial_stop_price'],
                                 target=trade['target_price'], stop=trade['stop_price'],
                                 peak=trade.get('_peak'), ltp=ltp,
                                 breakeven_per_share=fees / trade['shares'])
            trade['_peak'], trade['stop_price'] = result.peak, result.stop
            if result.exit_reason:
                return self._exit_via_market(trade, td, boundary, result.exit_reason, day)
        return super()._check_stop(trade, td, boundary, now, day)


def run_classic(intraday, daily, tickers, *, start, end, bankroll=2000):
    cfg = PennyLifecycleConfig(tuple(tickers), bankroll=bankroll, session_policy='allow_gaps')
    r = CurrentClassicReplay(intraday, daily, cfg, date.fromisoformat(start), date.fromisoformat(end))
    for day, names in r._select_days().items():
        r.run_day(day, names)
    for t in r.trades:
        for k in [k for k in t if k.startswith('_')]:
            t.pop(k)
    closed = sorted((t for t in r.trades if t['status'] == 'CLOSED'), key=lambda t: t['exit_fill_ts'])
    equity, curve = bankroll, []
    for t in closed:
        equity += t['net_pnl']; curve.append((t['exit_fill_ts'], equity))
    return {'scope': 'BAR_LIFECYCLE_PARTIAL', 'trades': r.trades,
            'summary': financial_summary(r.trades, curve, bankroll),
            'drawdown_basis': 'realised close curve; compare only on same basis',
            'exclusions': r.exclusions}


@dataclass(frozen=True)
class DailyGenome:
    name: str
    family: str = 'PULLBACK'
    hold: int = 3
    stop_atr: float = 1.5
    trail_atr: float = 2.0
    target_r: float = 2.5
    slots: int = 3
    risk_pct: float = 0.01
    volume_floor: float = 0.6
    score_floor: float = 0.45
    thesis_exit: bool = False


def daily_features(rows):
    """Precompute only backward-looking features; no future labels or outcomes."""
    grouped = defaultdict(list)
    for row in rows:
        t, d, o, h, l, c, v = row
        if all(isinstance(x, (int, float)) and math.isfinite(x) for x in (o,h,l,c,v)) and 0 < l <= min(o,c) <= max(o,c) <= h and v > 0:
            grouped[t].append((d,o,h,l,c,v))
    out = defaultdict(list)
    for ticker, history in grouped.items():
        history.sort()
        for i in range(60, len(history)):
            d,o,h,l,c,v = history[i]
            prior = history[i-20:i]
            prev = history[i-1][4]
            if not 1 <= c <= 55 or any(abs(history[j][4] / history[j-1][4] - 1) > .4 for j in range(i-20,i+1)):
                continue
            tv = median([x[4]*x[5] for x in prior])
            if tv < 500000:
                continue
            atr = sum(max(history[j][2]-history[j][3],abs(history[j][2]-history[j-1][4]),abs(history[j][3]-history[j-1][4])) for j in range(i-13,i+1))/14
            if atr <= 0:
                continue
            rvol = v / median([x[5] for x in prior])
            mean20 = sum(x[4] for x in prior)/20
            clv = (c-l)/(h-l) if h>l else .5
            trend = c/history[i-20][4]-1
            ret5 = c/history[i-5][4]-1
            drop = min(0, c/max(x[2] for x in history[i-5:i+1])-1)
            f={'ticker':ticker,'date':d,'close':c,'atr':atr,'rvol':rvol,'clv':clv,
               'trend':trend,'ret5':ret5,'drop':drop,'mean20':mean20,'low':l,
               'low5':min(x[3] for x in history[i-4:i+1]),'prev_close':prev}
            out[d].append(f)
    return dict(out)


def candidate_score(f, genome):
    """Two economic hypotheses: trend pullback resumption vs recovered panic."""
    if f['rvol'] < genome.volume_floor:
        return None
    if genome.family == 'PULLBACK':
        if f['trend'] <= 0 or f['close'] < f['mean20'] or not -.08 <= f['ret5'] <= .03:
            return None
        return .35*min(f['trend']/.15,1)+.35*f['clv']+.3*min(f['rvol']/2,1)
    if genome.family == 'FLUSH':
        if f['drop'] > -.04 or f['clv'] < .5:
            return None
        return .4*min(-f['drop']/.15,1)+.35*f['clv']+.25*min(f['rvol']/2,1)
    raise ValueError('unknown daily family')


def daily_signals(features, day, equity, genome):
    ranked=[]
    for f in features.get(day, ()):
        score=candidate_score(f,genome)
        if score is not None and score >= genome.score_floor:
            ranked.append((score,f))
    result=[]
    for score,f in sorted(ranked,key=lambda x:(-x[0],x[1]['ticker'])):
        entry=f['close'];distance=max(genome.stop_atr*f['atr'],.015*entry)
        if distance >= .15*entry:
            continue
        stop=entry-distance
        q=min(int(equity*genome.risk_pct/distance),int(equity/genome.slots/entry))
        if q < 1:
            continue
        result.append(DailySignal(f['ticker'],day,entry,stop,entry+genome.target_r*distance,
                                  q,genome.family,context={'atr':f['atr'],'anchor':f['low'],
                                                          'score':score,'genome':asdict(genome)}))
    return result


class DailyThesisPolicy:
    def __init__(self,genome): self.genome=genome
    def admit(self,signal,open_price): return None
    def resting_levels(self,p): return (RestingLevel(p.signal.target,1.,'TARGET'),)
    def on_partial(self,p,level): pass
    def at_close(self,p,bar,day,session_index):
        g=self.genome
        age=session_index-p.entry_session
        if g.thesis_exit and age >= 1 and bar['close'] < p.signal.context['anchor']:
            return 'THESIS_FAILED'
        if age >= g.hold: return 'TIME'
        peak=max(p.state.get('peak',p.entry_price),bar['close']);p.state['peak']=peak
        if peak-p.entry_price >= 1.5*p.initial_risk_per_share:
            p.stop=max(p.stop,peak-g.trail_atr*p.signal.context['atr'])
        return None


def run_daily(rows, features, genome, *, start, end, bankroll=100000, slippage_bps=10):
    bars=bars_by_ticker(rows)
    calendar=calendar_from(bars,'NIFTYBEES',start)
    result=run_daily_book(bars,calendar,end=end,
        signals_after_close=lambda d,e:daily_signals(features,d,e,genome),
        policy=DailyThesisPolicy(genome),costs=penny_cnc_costs,
        config=BookConfig(bankroll=bankroll,slippage_bps=slippage_bps,
                          entry_drift_pct=.02,max_entries_per_day=genome.slots,
                          max_open_positions=genome.slots))
    return {'version':VERSION,'scope':'PORTFOLIO_PROXY','genome':asdict(genome),
            'metrics':financial_summary(result['trades'],result['equity_curve'],bankroll),**result}


def accepts(candidate, baseline, bankroll, minimum_closes=20):
    return (candidate['closed'] >= minimum_closes and candidate['unresolved'] == 0
            and candidate['net'] > 0 and candidate['ex_best'] > 0
            and candidate['net'] > baseline['net']
            and candidate['drawdown'] <= max(1.5*baseline['drawdown'],bankroll*.025))
