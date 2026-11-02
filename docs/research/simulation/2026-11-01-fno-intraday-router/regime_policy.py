"""Pure causal state/selection contracts for N01 research; no broker imports."""
from __future__ import annotations
import math
from collections import defaultdict
from datetime import date
import numpy as np

EXPERTS=('DONCHIAN','TPB','SHIPPED','OR20','EFF','BOLL_REENTRY')
TREND={'TREND_UP':1,'TREND_DOWN':-1}


def describe(t,trend):
    """Each output row reads only its completed prefix. No end-of-day label."""
    out={};committed='UNAVAILABLE';pending=None;count=0
    for i,(stamp,r) in enumerate(t.iterrows()):
        raw='UNAVAILABLE';er=adx=None;crosses=0
        window=t.iloc[max(0,i-11):i+1];mins=window['minute'].to_numpy()
        valid=(i>=5 and t['minute'].iloc[0]==555 and len(window)>=6 and
               np.all(np.diff(mins)==5) and
               np.isfinite(window[['open','high','low','close','volume','atr','vwap']].to_numpy()).all() and
               (t['volume'].iloc[:i+1]>=0).all() and r['atr']>0)
        if valid:
            d=trend.loc[stamp];adx=float(d['adx'])
            valid=np.isfinite([adx,d['pdi'],d['mdi']]).all()
        if valid:
            path=float(window['close'].diff().abs().sum());progress=float(window['close'].iloc[-1]-window['close'].iloc[0])
            er=abs(progress)/path if path>0 else 0.
            signs=np.sign((window['close']-window['vwap']).to_numpy());nz=signs[signs!=0]
            crosses=int(np.sum(nz[1:]!=nz[:-1]))
            prior=float(t['close'].iloc[i-1]);prior_atr=float(t['atr'].iloc[i-1])
            tr=max(r['high']-r['low'],abs(r['high']-prior),abs(r['low']-prior))
            side=1 if d['pdi']>d['mdi'] else -1
            if prior_atr>0 and tr>3*prior_atr:raw='SHOCK'
            elif adx>=25 and er>=.45 and side*progress>0 and side*(r['close']-r['vwap'])>=.25*r['atr']:
                raw='TREND_UP' if side>0 else 'TREND_DOWN'
            elif (er<=.25 and crosses>=2) or (adx<=20 and er<=.35):raw='RANGE'
            else:raw='TRANSITION'
        if raw in ('UNAVAILABLE','SHOCK'):
            committed=raw;pending=None;count=0
        elif raw==committed:pending=None;count=0
        else:
            if raw==pending:count+=1
            else:pending=raw;count=1
            if count>=2:committed=raw;pending=None;count=0
        out[str(stamp)[:19]]={'state':committed,'raw_state':raw,'adx':adx,'efficiency':er,'vwap_crossings':crosses}
    return out


def rule_experts(state):
    if state in TREND:return list(EXPERTS[:-1])
    if state=='RANGE':return ['BOLL_REENTRY']
    if state=='TRANSITION':return ['TPB']
    return []


def direction_allowed(state,direction):
    return state not in TREND or TREND[state]==(1 if direction=='LONG' else -1)


def invalidates(entry,states,direction):
    """Three confirmed bar states; unknown/shock never fabricates an exit."""
    if len(states)<3:return False
    sign=1 if direction=='LONG' else -1
    def adverse(s):
        if s in ('UNAVAILABLE','SHOCK'):return False
        if entry in TREND:return s=='RANGE' or (s in TREND and TREND[s]!=sign)
        if entry=='RANGE':return s in TREND and TREND[s]!=sign
        return False
    return all(adverse(s) for s in states[-3:])


def fit_model(records,asof,sessions):
    """Rolling past-only expert rewards; closed labels must precede as-of."""
    assert asof[8:10]=='01'
    prior=[d for d in sorted(sessions) if d<asof][-252:];days=set(prior)
    selected=[r for r in records if r['day'] in days and r['exit_time'][:10]<asof]
    global_={e:[] for e in EXPERTS};cells=defaultdict(list)
    for r in selected:
        assert r['entry_time']<=r['exit_time'] and r['exit_time'][:10]<asof
        global_[r['expert']].append(float(r['net']))
        cells[(r['cell'],r['expert'])].append(float(r['net']))
    choices={}
    for cell in sorted({r['cell'] for r in selected if isinstance(r['cell'],str)}):
        ranks=[]
        for e in EXPERTS:
            values=cells[(cell,e)];all_=global_[e]
            if len(values)<12 or len(all_)<30:continue
            estimate=(sum(values)+12*float(np.mean(all_)))/(len(values)+12)
            sd=float(np.std(values,ddof=1))
            score=estimate-.5*sd/math.sqrt(len(values)+12)
            if score>0:ranks.append({'expert':e,'score':score,'cell_trades':len(values),'global_trades':len(all_)})
        ranks.sort(key=lambda r:(-r['score'],EXPERTS.index(r['expert'])))
        choices[cell]=ranks
    return {'asof':asof,'window_start':prior[0] if prior else None,'past_sessions':len(prior),
            'labels':len(selected),'latest_label_exit':max((r['exit_time'] for r in selected),default=None),'choices':choices}
