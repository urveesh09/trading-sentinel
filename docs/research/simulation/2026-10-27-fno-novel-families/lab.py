"""O27e research-only entry-family evolution. No runtime module imports this file."""
from __future__ import annotations

import argparse
from collections import Counter, OrderedDict, defaultdict
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import random
import socket
import statistics
import subprocess
import sys
import weakref

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'python-engine/fno_policy_replay.py').is_file())
sys.path[:0] = [str(ROOT / 'python-engine'), str(ROOT / 'scripts')]
import pandas as pd
import run_fno_consistency_grid as grid
import fno_policy_replay as replay
import fno_shadow
from config import settings
from fno_engine_mom import MomSignal
from fno_models import FnoDirection

DATA = ROOT / 'docs/research/fno/2026-10-27-consistency-grid/_local/dataset'
OLD_CONTROL = ROOT / 'docs/research/fno/2026-10-27-consistency-grid/_local/arms/OR30__LOCK_LIVE__T45__TR1.0.json'
A = ('2026-09-10', '2026-10-09')
FULL = ('2026-09-10', '2026-10-26')
B = ('2026-10-12', '2026-10-26')
FAMILIES = ('EFFICIENCY_BREAK', 'COMPRESSION_RELEASE', 'FAILED_AUCTION')
GENES = {
    'lookback': (4, 6, 12), 'efficiency': (0.15, 0.35, 0.55),
    'buffer': (0.0, 0.1, 0.2), 'body': (0.35, 0.55), 'vwap': (False, True),
    'compression': (2.0, 3.0, 4.0), 'rvol': (0.8, 1.0, 1.2),
    'stop': (1.0, 1.5, 2.0), 'target': (1.2, 1.8, 2.4),
    'exit': ('LIVE', 'PATIENT', 'LOOSE'),
}
GA = {'seed': 2026102705, 'population_per_family': 8, 'generations': 5,
      'elites': 2, 'immigrants': 1, 'mutation_probability': 0.18, 'finalists': 2}
RULE = {
    'all_dates_seen': True, 'min_A_trades': 8, 'min_trades_each_A_third': 2,
    'A_eligibility': 'no unresolved; net > 0; net without best day > 0; stressed net > 0',
    'fitness': '(net-best positive day)/max(closed-trade drawdown,1000) - .75*losing thirds - .75*empty thirds; fewer than 8 trades: -10+trades/8',
    'plateau': 'median of family leader and all one-step numeric/boolean/exit neighbours; family fixed',
    'selection': 'two family leaders by (eligible, plateau, fitness, digest), frozen before B; ineligible arms remain diagnostics only',
    'B_diagnostic': '>=3 trades; zero unresolved; net>0; net excluding best day>0; net>control; DD<=max(1.5*control,5000); stressed net>0',
    'fixed_trade_stress': 'net - 1 rupee per option unit per side - 25% extra recorded charges; not a resimulation of sizing/brakes',
    'verdict': 'EXPLORATORY_ONLY_NO_UNTOUCHED_DATA regardless of apparent profit',
}
_FEATURES = OrderedDict()


def write_new(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, allow_nan=False, default=str)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


def features(frame):
    """All rolling features are causal; later rows cannot alter an earlier row."""
    key = id(frame)
    cached = _FEATURES.get(key)
    if cached and cached[0]() is frame:
        return cached[1]
    x = frame.copy(); by_day = x.groupby(x.index.date, sort=False)
    previous = x.close.shift(1)
    tr = pd.concat([x.high-x.low, (x.high-previous).abs(), (x.low-previous).abs()], axis=1).max(axis=1)
    x['atr'] = tr.ewm(alpha=1/settings.FNO_ATR_LEN, adjust=False).mean()
    x['vwap'] = ((x.high+x.low+x.close)/3*x.volume).groupby(x.index.date).cumsum() / x.volume.groupby(x.index.date).cumsum().replace(0, float('nan'))
    x['rvol'] = float('nan')
    # Same calendar-day window and slot policy as the shipped RVOL helper.
    for _, slots in x.groupby([x.index.hour, x.index.minute]):
        base = slots.volume.rolling(f'{int(settings.FNO_RVOL_LOOKBACK_DAYS)}D', closed='left', min_periods=3).mean()
        x.loc[slots.index, 'rvol'] = slots.volume / base.replace(0, float('nan'))
    for n in GENES['lookback']:
        x[f'hi{n}'] = by_day.high.transform(lambda s: s.shift(1).rolling(n).max())
        x[f'lo{n}'] = by_day.low.transform(lambda s: s.shift(1).rolling(n).min())
        changes = by_day.close.transform(lambda s: s.diff().abs().rolling(n).sum())
        displacement = by_day.close.transform(lambda s: (s-s.shift(n)).abs())
        x[f'er{n}'] = displacement / changes.replace(0, float('nan'))
    _FEATURES[key] = (weakref.ref(frame), x)
    while len(_FEATURES) > 3:
        _FEATURES.popitem(last=False)
    return x


@dataclass(frozen=True)
class NovelSignal:
    name: str
    genome: dict


def signal(frame, regime, now, variant):
    """Futures-only closed-bar predicates. Exits, options and risk stay shipped."""
    g = variant.genome; out = MomSignal()
    if frame.empty or not frame.index.is_monotonic_increasing or not frame.index.is_unique:
        out.reject_reason = 'novel:invalid_frame'; return out
    naive = now.replace(tzinfo=None)
    end = int(frame.index.searchsorted(pd.Timestamp(naive-timedelta(minutes=5)), side='right'))
    if end < settings.FNO_ATR_LEN+1:
        out.reject_reason = 'novel:warmup'; return out
    rows = features(frame).iloc[:end]; today = rows[rows.index.date == naive.date()]
    if len(today) < max(g['lookback']+2, 7):
        out.reject_reason = 'novel:session_warmup'; return out
    # Exact 09:15–09:40 range and a contiguous lookback; no bars manufactured across gaps.
    opening = today[(today.index.hour*60+today.index.minute >= 555) & (today.index.hour*60+today.index.minute < 585)]
    expected = pd.date_range(pd.Timestamp(naive.date())+pd.Timedelta(minutes=555), periods=6, freq='5min')
    if not opening.index.equals(expected) or today.index[-1] < expected[-1]+pd.Timedelta(minutes=5):
        out.reject_reason = 'novel:opening_range'; return out
    tail = today.iloc[-(g['lookback']+2):]
    if not (tail.index.to_series().diff().dropna() == pd.Timedelta(minutes=5)).all():
        out.reject_reason = 'novel:bar_gap'; return out
    r, p, pp = today.iloc[-1], today.iloc[-2], today.iloc[-3]
    out.bar_ts = today.index[-1].strftime('%Y-%m-%d %H:%M:%S')
    out.close, out.atr = float(r.close), float(r.atr)
    out.or_high, out.or_low = float(opening.high.max()), float(opening.low.min())
    out.rvol = float(r.rvol) if pd.notna(r.rvol) else 0.0
    if regime == 'REGIME_3_CRISIS':
        out.reject_reason = 'novel:crisis'; return out
    if pd.isna(r.rvol) or r.rvol < g['rvol']:
        out.reject_reason = 'novel:rvol'; return out
    n = g['lookback']; hi, lo, er = float(r[f'hi{n}']), float(r[f'lo{n}']), float(r[f'er{n}'])
    body = abs(r.close-r.open) / max(float(r.high-r.low), 1e-9)
    if not all(pd.notna(v) for v in (hi, lo, er, r.vwap)) or out.atr <= 0 or body < g['body']:
        out.reject_reason = 'novel:shape'; return out
    long = short = False
    if g['family'] in FAMILIES[:2]:
        long = r.close > hi+g['buffer']*r.atr and p.close <= p[f'hi{n}']+g['buffer']*p.atr
        short = r.close < lo-g['buffer']*r.atr and p.close >= p[f'lo{n}']-g['buffer']*p.atr
        if er < g['efficiency']:
            out.reject_reason = 'novel:efficiency'; return out
        if g['family'] == 'COMPRESSION_RELEASE' and (hi-lo) > g['compression']*p.atr:
            out.reject_reason = 'novel:not_compressed'; return out
    else:
        # A completed outside close, followed by a close back inside the OR; first reclaim only.
        long = p.close < out.or_low-g['buffer']*p.atr and r.close > out.or_low and r.close < out.or_high and r.close > r.open
        short = p.close > out.or_high+g['buffer']*p.atr and r.close < out.or_high and r.close > out.or_low and r.close < r.open
        if er > g['efficiency'] or abs(p.close-p.vwap) < 0.5*p.atr:
            out.reject_reason = 'novel:not_exhausted'; return out
    if not (long or short):
        out.reject_reason = 'novel:no_trigger'; return out
    if g['vwap']:
        if g['family'] == 'FAILED_AUCTION':
            okay = r.close < r.vwap if long else r.close > r.vwap
        else:
            okay = (r.close > r.vwap and r.vwap >= p.vwap) if long else (r.close < r.vwap and r.vwap <= p.vwap)
        if not okay:
            out.reject_reason = 'novel:vwap'; return out
    distance = g['stop']*out.atr
    if g['family'] == 'FAILED_AUCTION':
        stop = min(p.low-0.05, r.close-distance) if long else max(p.high+0.05, r.close+distance)
    else:
        stop = max(lo, r.close-distance) if long else min(hi, r.close+distance)
    risk = (r.close-stop) if long else (stop-r.close)
    if risk <= 0:
        out.reject_reason = 'novel:degenerate_stop'; return out
    out.direction = FnoDirection.LONG if long else FnoDirection.SHORT
    out.stop_underlying = float(stop)
    out.target_underlying = float(r.close + (1 if long else -1)*g['target']*risk)
    return out


def policy(g):
    exits = {}
    if g['exit'] == 'PATIENT':
        exits = {'FNO_TIME_STOP_MIN':75., 'FNO_TRAIL_ATR_MULT':1.5, 'FNO_PROFIT_LOCK_ARM_R':0.8}
    elif g['exit'] == 'LOOSE':
        exits = {'FNO_TIME_STOP_MIN':60., 'FNO_TRAIL_ATR_MULT':1.5, 'FNO_PROFIT_LOCK_ENABLED':False}
    return replay.ReplayPolicy(name='O27E_'+digest(g), manage_every_observation=True,
                               signal_variant=NovelSignal('O27E_'+digest(g), g), exit_overrides=tuple(sorted(exits.items())))


@contextmanager
def research_dispatch():
    original = fno_shadow._variant_signal
    def dispatch(frame, regime, now, variant):
        return signal(frame, regime, now, variant) if isinstance(variant, NovelSignal) else original(frame, regime, now, variant)
    fno_shadow._variant_signal = dispatch
    try:
        yield
    finally:
        fno_shadow._variant_signal = original


def deny_network():
    def denied(*args, **kwargs):
        raise RuntimeError('O27e offline research: network prohibited')
    socket.socket.connect = denied; socket.socket.connect_ex = denied
    socket.create_connection = denied; socket.getaddrinfo = denied


class AuditedReplay(replay.SingleLegReplay):
    def __init__(self, data, arm, strict=False):
        super().__init__(data, arm); self.strict = strict; self.execution = Counter(); self.entries = {}

    def _entry(self, book, obs, frame, day, now):
        before = book.next_id
        if self.strict:
            # Whole-position displayed depth, both sides, no phantom liquidity.
            filtered = {k:q for k,q in obs.options.items() if q.bid>0 and q.ask>0
                        and min(q.bid_quantity,q.ask_quantity)>=int(settings.FNO_MAX_LOTS)*q.contract.lot_size}
            obs = replace(obs, options=filtered)
        super()._entry(book, obs, frame, day, now)
        for leg in book.open.values():
            if leg.id >= before:
                q = obs.options[leg.token]; self.entries[leg.id] = {'qty':leg.initial_qty, 'ask_quantity':q.ask_quantity}
                self.execution['entries'] += 1
                self.execution['entry_depth_insufficient'] += q.ask_quantity < leg.initial_qty

    def _manage(self, book, obs, now):
        before = len(book.trades); held = {leg.tradingsymbol:leg for leg in book.open.values()}
        if self.strict:
            adjusted = {}
            for k,q in obs.options.items():
                qty = next((leg.qty for leg in book.open.values() if leg.token == k), 0)
                adjusted[k] = q if q.bid>0 and q.bid_quantity>=qty else replace(q,bid=0.,ltp=0.)
            obs = replace(obs, options=adjusted)
        super()._manage(book, obs, now)
        for trade in book.trades[before:]:
            leg = held[trade['tradingsymbol']]; q = obs.options.get(leg.token)
            trade['entry_qty'] = leg.initial_qty
            trade['fill_basis'] = 'BID' if q and q.bid>0 else 'LTP_PROXY'
            self.execution['ltp_exits'] += trade['fill_basis'] != 'BID'
            self.execution['exit_depth_insufficient'] += not q or q.bid_quantity < leg.qty


def metrics(trades, days):
    closed = sorted([t for t in trades if 'net_pnl' in t and t['entry_time'][:10] in days], key=lambda t:t['exit_time'])
    unresolved = [t for t in trades if 'net_pnl' not in t and t['entry_time'][:10] in days]
    daily = {d:0. for d in days}; running = peak = dd = 0.; charges = stress = 0.
    for t in closed:
        net = float(t['net_pnl']); daily[t['entry_time'][:10]] += net; running += net
        peak = max(peak,running); dd = max(dd,peak-running)
        fee = float(t['gross_pnl'])-net; charges += fee
        stress += net-2*int(t['entry_qty'])-0.25*fee
    vals = [t['net_pnl'] for t in closed]; wins = sum(x for x in vals if x>0); losses = -sum(x for x in vals if x<0)
    third_days = [days[i*len(days)//3:(i+1)*len(days)//3] for i in range(3)]
    thirds = [{'net':round(sum(daily[d] for d in block),4), 'trades':sum(t['entry_time'][:10] in block for t in closed)} for block in third_days]
    return {'trades':len(closed), 'unresolved':len(unresolved), 'net':round(running,4), 'charges':round(charges,4),
            'net_without_best_trade':round(running-max([0.,*vals]),4), 'net_without_best_day':round(running-max([0.,*daily.values()]),4),
            'drawdown_closed_trades':round(dd,4), 'win_rate':sum(x>0 for x in vals)/len(vals) if vals else None,
            'profit_factor':wins/losses if losses else None, 'stressed_net_fixed_trades':round(stress,4),
            'active_days':sum(any(t['entry_time'][:10]==d for t in closed) for d in days),
            'green_days':sum(v>0 for v in daily.values()), 'red_days':sum(v<0 for v in daily.values()),
            'sessions':len(days), 'daily':{k:round(v,4) for k,v in daily.items()}, 'thirds':thirds,
            'exit_reasons':dict(Counter(t['exit_reason'] for t in closed))}


def score(m):
    if m['trades'] < 8:
        return -10+m['trades']/8
    return m['net_without_best_day']/max(m['drawdown_closed_trades'],1000)-.75*sum(x['net']<0 for x in m['thirds'])-.75*sum(x['trades']==0 for x in m['thirds'])


def eligible(m):
    return m['trades']>=8 and m['unresolved']==0 and m['net']>0 and m['net_without_best_day']>0 and m['stressed_net_fixed_trades']>0 and all(x['trades']>=2 for x in m['thirds'])


def bindings():
    calendar=json.loads((HERE/'calendar.json').read_text())
    manifest=json.loads((DATA/'manifest.json').read_text())
    assert sorted(e for e in manifest['option_expiries']['NIFTY'] if FULL[0]<=e<=FULL[1])==calendar['nifty_expiries_in_window'], 'expiry calendar differs from independent NSE cross-check'
    files = {p.relative_to(ROOT).as_posix():grid._sha(p) for p in (ROOT/'python-engine').glob('*.py')}
    for p in [Path(grid.__file__), HERE/'lab.py', HERE/'test_lab.py']:
        files[p.relative_to(ROOT).as_posix()] = grid._sha(p)
    return {'sources':files, 'dataset':grid._verify_dataset(DATA), 'settings':grid._settings_check(), 'calendar_sha256':grid._sha(HERE/'calendar.json'),
            'prior_control_sha256':grid._sha(OLD_CONTROL), 'prior_genomes_sha256':grid._sha(ROOT/'docs/research/fno/2026-10-27-evolution/results.json')}


def evaluate(task):
    g, window, strict, out_dir = task; out = Path(out_dir); deny_network()
    data = grid.CachedReplayData(DATA, HERE/'_local/cache')
    arm = replay.resolve_policy('CURRENT') if g is None else policy(g)
    with research_dispatch():
        runner = AuditedReplay(data, arm, strict); result = runner.run(*window)
    days = [d for d in data.days if window[0]<=d<=window[1]]
    result['execution'] = dict(runner.execution); result['metrics'] = metrics(result['trades'],days)
    result['genome'] = g; result['strict_bid_depth_diagnostic'] = strict
    target = out/f'{"CURRENT" if g is None else digest(g)}.json'
    write_new(target,result); return str(target)


def warm(day):
    # Deliberately rebuild from raw archive, never reuse a preceding experiment's pickle.
    deny_network(); import pickle
    data = replay.ReplayData(DATA); parsed = data.observations(day)
    path = HERE/'_local/cache'/f'{day}.pkl'
    with path.open('xb') as f: pickle.dump(parsed,f,protocol=pickle.HIGHEST_PROTOCOL)
    return day


def random_genome(family,rng):
    return canonical({'family':family, **{k:rng.choice(v) for k,v in GENES.items()}})


def canonical(g):
    # Do not count an inactive compression knob as another tested strategy.
    return {**g,'compression':g['compression'] if g['family']=='COMPRESSION_RELEASE' else 3.0}


def breed(a,b,rng):
    g = {'family':a['family']}
    for k,alleles in GENES.items():
        v = rng.choice([a[k],b[k]])
        if rng.random()<GA['mutation_probability']:
            alternatives = [x for x in alleles if x!=v]; v=rng.choice(alternatives)
        g[k]=v
    return canonical(g)


def neighbours(g):
    rows=[]
    for k,alleles in GENES.items():
        if k=='compression' and g['family']!='COMPRESSION_RELEASE': continue
        i=alleles.index(g[k])
        for j in (i-1,i+1):
            if 0<=j<len(alleles): rows.append({**g,k:alleles[j]})
    return rows


def signature(trades):
    keys=('bar_ts','tradingsymbol','entry_time','entry_premium','exit_time','exit_premium','exit_reason','gross_pnl','net_pnl','lots_at_exit')
    return [{k:t.get(k) for k in keys} for t in trades]


def run(jobs):
    frozen=json.loads((HERE/'freeze.json').read_text()); assert frozen['bindings']==bindings(), 'bound inputs changed'
    assert 1<=jobs<=6, 'One to six research workers'
    # A committed freeze, not just a mutable working file, is mandatory.
    rel=(HERE/'freeze.json').relative_to(ROOT).as_posix()
    committed=subprocess.check_output(['git','show',f'HEAD:{rel}'],cwd=ROOT)
    assert json.loads(committed)==frozen, 'freeze not committed'
    local=HERE/'_local'; (local/'cache').mkdir(parents=True,exist_ok=False)
    for name in ('A','FULL','STRICT'): (local/name).mkdir()
    days=frozen['bindings']['dataset']['quote_days']
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        list(pool.map(warm,days))
        control_path=evaluate((None,FULL,False,str(local/'FULL')))
        control=json.loads(Path(control_path).read_text()); old=json.loads(OLD_CONTROL.read_text())
        assert signature(control['trades'])==signature(old['trades']), 'CURRENT differs from prior control; abort search'
        write_new(HERE/'parity.json',{'prior_control_sha256':grid._sha(OLD_CONTROL),'exact_trade_financial_parity':True,
                                    'metrics':control['metrics'],'archive_exclusions':control['archive_exclusions'],'notes':control['notes']})
        print('PARITY PASS',control['metrics']['trades'],control['metrics']['net'],flush=True)
        rng=random.Random(GA['seed']); evaluated={}; history=[]
        def batch(genomes):
            fresh={digest(g):g for g in genomes if digest(g) not in evaluated}
            tasks=[(g,A,False,str(local/'A')) for g in fresh.values()]
            for file in pool.map(evaluate,tasks):
                report=json.loads(Path(file).read_text()); g=report['genome']; m=report['metrics']
                evaluated[digest(g)]={'genome':g,'metrics':m,'fitness':score(m),'eligible':eligible(m)}
        leaders=[]
        for family in FAMILIES:
            pop=[random_genome(family,rng) for _ in range(GA['population_per_family'])]
            for generation in range(GA['generations']):
                batch(pop); ranked=sorted(pop,key=lambda g:(evaluated[digest(g)]['eligible'],evaluated[digest(g)]['fitness'],digest(g)),reverse=True)
                best=evaluated[digest(ranked[0])]
                history.append({'family':family,'generation':generation,'evaluated':len(evaluated),'leader':digest(ranked[0]),'fitness':best['fitness'],'metrics':best['metrics']})
                print(f'{family} generation {generation}: {len(evaluated)} genomes; best net={best["metrics"]["net"]:.2f}, trades={best["metrics"]["trades"]}, eligible={best["eligible"]}',flush=True)
                new=ranked[:GA['elites']]+[random_genome(family,rng)]
                def tournament():
                    return max(rng.sample(ranked,3),key=lambda g:(evaluated[digest(g)]['eligible'],evaluated[digest(g)]['fitness']))
                while len(new)<GA['population_per_family']: new.append(breed(tournament(),tournament(),rng))
                pop=new
            family_rows=[r for r in evaluated.values() if r['genome']['family']==family]
            leader=max(family_rows,key=lambda r:(r['eligible'],r['fitness'],digest(r['genome'])))
            nearby=neighbours(leader['genome']); batch(nearby)
            leader['plateau']=statistics.median([leader['fitness'],*[evaluated[digest(g)]['fitness'] for g in nearby]])
            leaders.append(leader)
        chosen=sorted(leaders,key=lambda r:(r['eligible'],r['plateau'],r['fitness'],digest(r['genome'])),reverse=True)[:2]
        write_new(HERE/'selection.json',{'rule':RULE,'candidates':chosen,'control_metrics':control['metrics'],
                                       'evaluated':len(evaluated),'selected_before_B':True})
        full=list(pool.map(evaluate,[(r['genome'],FULL,False,str(local/'FULL')) for r in chosen]))
        strict=list(pool.map(evaluate,[(g,FULL,True,str(local/'STRICT')) for g in [None,*[r['genome'] for r in chosen]]]))
    full_reports=[json.loads(Path(p).read_text()) for p in full]
    strict_reports=[json.loads(Path(p).read_text()) for p in strict]
    days_b=[d for d in days if B[0]<=d<=B[1]]; base_b=metrics(control['trades'],days_b)
    for r in full_reports:
        m=metrics(r['trades'],days_b); r['B_seen_diagnostic']=m
        r['B_checks']={'trades':m['trades']>=3,'priced':m['unresolved']==0,'positive':m['net']>0,
            'best_day_removed':m['net_without_best_day']>0,'beats_control':m['net']>base_b['net'],
            'drawdown':m['drawdown_closed_trades']<=max(1.5*base_b['drawdown_closed_trades'],5000),
            'stress':m['stressed_net_fixed_trades']>0}
    assert frozen['bindings']==bindings(), 'bound inputs changed during scoring'
    write_new(HERE/'results.json',{'freeze_sha256':grid._sha(HERE/'freeze.json'),'verdict':RULE['verdict'],
        'control':control,'control_B_seen':base_b,'candidates':full_reports,'strict_diagnostics':strict_reports,
        'evaluations':evaluated,'generations':history,'source_and_dataset_reverified':True,'can_place_orders':False})
    print('DONE',len(evaluated),'genomes;',RULE['verdict'],flush=True)


def freeze():
    deny_network()
    value={'schema':'o27e_novel_families_v1','bindings':bindings(),'genes':GENES,'families':FAMILIES,
           'ga':GA,'rule':RULE,'windows':{'search_seen':A,'diagnostic_seen':B,'full_seen':FULL},
           'qualification':'NOT_ASSESSED','can_place_orders':False}
    write_new(HERE/'freeze.json',value)
    write_new(HERE/'configuration.json',{'source':'existing read-only Production export','dataset':str(DATA.relative_to(ROOT)),
        'dataset_binding':value['bindings']['dataset'],'settings':value['bindings']['settings'],
        'source_binding':value['bindings']['sources'],'opening_state':'shipped replay: historical prior closes; shared-risk spread closes exogenous',
        'fills':'primary ask entry / bid else LTP exit, inherited for parity; separate no-LTP/depth diagnostic',
        'clock':'closed 5-minute futures bars, live-aligned 90-second entry grid, ~60-second archived management',
        'limits':'6 workers after hours; no network; no live book or scheduler; 29 seen sessions only','rule':RULE})
    print('FROZEN',value['bindings']['dataset']['manifest_sha256'],flush=True)


if __name__=='__main__':
    cli=argparse.ArgumentParser(); cli.add_argument('action',choices=['freeze','run']); cli.add_argument('--jobs',type=int,default=6)
    args=cli.parse_args()
    if args.action=='freeze': freeze()
    else: run(args.jobs)
