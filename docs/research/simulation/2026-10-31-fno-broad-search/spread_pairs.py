"""Matched vertical-expression diagnostics, NOT a spread lifecycle/backtest.

Replayed strategy entries/exits are a declared control. No counterfactual
entry selection or combined account return is inferred from the pairs.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'python-engine/fno_policy_replay.py').is_file())
sys.path.insert(0,str(ROOT/'python-engine'))
from fno_costs import calc_fno_costs  # noqa:E402

LOT=65
WIDTHS=(50,100,150)
COSTS=(200.,400.)


def vertical(e,x,wing_e,wing_x,width,mode,extra):
    """Known entry risk/cash uses entry values only; actual exit fees separate."""
    if any(q is None for q in (e,x,wing_e,wing_x)):return {'status':'UNAVAILABLE','reason':'missing_exact_minute_leg'}
    if any(not q['volume']>0 for q in (e,x,wing_e,wing_x)):return {'status':'UNAVAILABLE','reason':'no_positive_same_minute_volume'}
    if any(q['bid']<=0 or q['ask']<q['bid'] for q in (e,x,wing_e,wing_x)):return {'status':'UNAVAILABLE','reason':'invalid_quote'}
    for a,b in ((e,wing_e),(x,wing_x)):
        if not -.05<=a['close']-b['close']<=width+.05:return {'status':'UNAVAILABLE','reason':'incoherent_vertical_midpoints'}
    if mode=='DEBIT':
        entry=e['ask']-wing_e['bid'];end=x['bid']-wing_x['ask']
        if not 0<entry<width:return {'status':'UNAVAILABLE','reason':'invalid_entry_debit'}
        gross=(end-entry)*LOT
        fees=calc_fno_costs(e['ask'],x['bid'],LOT)+calc_fno_costs(wing_x['ask'],wing_e['bid'],LOT)
        planned=entry*LOT+200+extra
    elif mode=='INVERSE_CREDIT':
        credit=e['bid']-wing_e['ask'];liability=x['ask']-wing_x['bid']
        if not 0<credit<width:return {'status':'UNAVAILABLE','reason':'invalid_entry_credit'}
        gross=(credit-liability)*LOT
        fees=calc_fno_costs(x['ask'],e['bid'],LOT)+calc_fno_costs(wing_e['ask'],wing_x['bid'],LOT)
        entry=-credit;planned=(width-credit)*LOT+200+extra
    else:raise ValueError(mode)
    single_gross=(x['bid']-e['ask'])*LOT
    single_net=single_gross-calc_fno_costs(e['ask'],x['bid'],LOT)-extra
    reserve=width*LOT+200+extra  # deliberately full width for BOTH structures
    return {'status':'AVAILABLE','mode':mode,'gross':gross,'fees':fees,'extra':extra,'net':gross-fees-extra,
            'same_clock_single_net':single_net,'delta_vs_single':gross-fees-extra-single_net,
            'entry_cashflow':-entry*LOT,'reserved_own_cash':reserve,'planned_risk':planned,
            'cash_feasible':reserve<=250000,'risk_compatible':planned<=5000,
            'note':'Entry-only planned risk includes fixedRs200 fee buffer; not a guaranteed loss or broker margin requirement'}


def summarize(rows):
    available=[r for r in rows if r['status']=='AVAILABLE']
    risk=[r for r in available if r['risk_compatible'] and r['cash_feasible']]
    def agg(part):
        if not part:return {'trades':0,'net':None,'single_same_cohort_net':None,'delta':None,'wins':0,'without_best_day':None,'worst_trade':None}
        days=defaultdict(float)
        for r in part:days[r['day']]+=r['net']
        net=sum(r['net'] for r in part)
        return {'trades':len(part),'net':round(net,2),'single_same_cohort_net':round(sum(r['same_clock_single_net'] for r in part),2),
                'delta':round(sum(r['delta_vs_single'] for r in part),2),'wins':sum(r['net']>0 for r in part),
                'without_best_day':round(net-max([0.,*days.values()]),2),'worst_trade':round(min([0.,*[r['net'] for r in part]]),2)}
    return {'requested':len(rows),'available':len(available),'unavailable':dict(Counter(r['reason'] for r in rows if r['status']!='AVAILABLE')),
            'all_priced_diagnostic':agg(available),'entry_risk_compatible_subset':agg(risk),
            'coverage_pct':round(100*len(available)/len(rows),1) if rows else None,
            'money_if_no_available':None if not available else 'priced_subset_only'}


def main():
    import lab_broad as B
    B.O27F.deny_network()
    f=json.loads((HERE/'freeze.json').read_text());results={};rows=[];parity=0
    for y in ('2024','2025','2026'):
        con=sqlite3.connect((ROOT/f['bindings'][y]['dataset']/'breeze.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
        keys=json.loads((HERE/f'_local/keys-screen-{y}.json').read_text());memo={}
        def quote(expiry,strike,opt,stamp):
            key=(expiry,strike,opt,stamp)
            if key not in memo:
                q=con.execute("SELECT close,volume FROM candles WHERE kind='option' AND expiry=? AND strike=? AND opt=? AND datetime=?",key).fetchone()
                if q:
                    bid,ask=B.Y.yeardata.bid_ask(float(q[0]));memo[key]={'close':float(q[0]),'bid':bid,'ask':ask,'volume':float(q[1] or 0)}
                else:memo[key]=None
            return memo[key]
        for control in ('RAW|MAIN','RAW|E|tpb_puts'):
            data=json.loads((HERE/'_local/evals'/f'{keys[control]}.json').read_text())
            for t in data['trades']:
                if t.get('net_pnl') is None:continue
                assert t['entry_qty']==LOT and t['lots_at_exit']==1 and not t.get('adds'), 'paired controls require one lot/no adds'
                token=re.fullmatch(r'NIFTY(\d{6})(\d+)(CE|PE)',t['tradingsymbol']);assert token,t['tradingsymbol']
                exp=datetime.strptime(token[1],'%y%m%d').date().isoformat();strike=int(token[2]);opt=token[3]
                def stamp(s):return datetime.fromisoformat(s).strftime('%Y-%m-%d %H:%M:00')
                e,x=quote(exp,strike,opt,stamp(t['entry_time'])),quote(exp,strike,opt,stamp(t['exit_time']))
                valid=e is not None and x is not None and e['volume']>0 and x['volume']>0
                if valid:
                    assert abs(e['ask']-t['entry_premium'])<.001 and abs(x['bid']-t['exit_premium'])<.001,'single-leg quote parity'
                    expected=(x['bid']-e['ask'])*LOT-calc_fno_costs(e['ask'],x['bid'],LOT)
                    assert abs(expected-t['net_pnl'])<.011,'single-leg fee parity'
                    parity+=1
                for width in WIDTHS:
                    wing=strike+(width if opt=='CE' else -width)
                    we,wx=quote(exp,wing,opt,stamp(t['entry_time'])),quote(exp,wing,opt,stamp(t['exit_time']))
                    for mode in ('DEBIT','INVERSE_CREDIT'):
                        for cost in COSTS:
                            r=vertical(e,x,we,wx,width,mode,cost)
                            r.update(year=y,day=t['entry_time'][:10],control=control,direction=t['direction'],width=width,mode=mode,extra=cost)
                            rows.append(r)
        con.close()
    for control in ('RAW|MAIN','RAW|E|tpb_puts'):
        for d in ('LONG','SHORT'):
            for width in WIDTHS:
                for mode in ('DEBIT','INVERSE_CREDIT'):
                    for cost in COSTS:
                        part=[r for r in rows if r['control']==control and r['direction']==d and r['width']==width and r['mode']==mode and r['extra']==cost]
                        if not part:continue
                        name=f'{control}|{d}|{width}|{mode}|{int(cost)}'
                        results[name]={y:summarize([r for r in part if r['year']==y]) for y in ('2024','2025','2026')}
    leads=[]
    for name,ys in results.items():
        if not name.endswith('|400'):continue
        part=[ys[y]['entry_risk_compatible_subset'] for y in ('2024','2025','2026')]
        coverage=all(ys[y]['requested']>0 and ys[y]['entry_risk_compatible_subset']['trades']/ys[y]['requested']>=.95 for y in ('2024','2025','2026'))
        passes=coverage and min(p['trades'] for p in part)>=12 and sum(p['trades'] for p in part)>=40 and all(p['net'] is not None and p['net']>0 and p['without_best_day']>0 and p['delta']>0 for p in part)
        if passes:leads.append(name)
    B.P.write(HERE/'spread-results.json',{'schema':'o31i_spread_pairs_v1','results':results,'single_quote_fee_parity_trades':parity,'exploratory_leads':leads,
        'scope':'MATCHED_EXPRESSION_DIAGNOSTIC_NOT_SPREAD_LIFECYCLE_OR_PORTFOLIO','qualified':False,'can_place_orders':False})
    B.P.write(HERE/'_local/spread-pairs.json',rows)
    print('Spread diagnostic cells',len(results),'single-leg parity',parity,'paired observations',len(rows),flush=True)


if __name__=='__main__':main()
