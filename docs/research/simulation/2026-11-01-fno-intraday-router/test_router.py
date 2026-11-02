from datetime import date,datetime,timedelta
from pathlib import Path
from types import SimpleNamespace
from collections import Counter
import copy,json,sys
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import router_lab as X
R=X.R


def bars(kind='trend'):
    idx=pd.date_range('2026-01-02 09:15',periods=60,freq='5min')
    c=100+np.arange(60)*.5 if kind=='trend' else 100+np.sin(np.arange(60)*2)
    t=pd.DataFrame({'open':c-.1,'high':c+.2,'low':c-.2,'close':c,'volume':1000.,'atr':1.,'vwap':100.,'minute':idx.hour*60+idx.minute},index=idx)
    d=pd.DataFrame({'adx':35. if kind=='trend' else 15.,'pdi':40.,'mdi':10.},index=idx)
    return t,d


@pytest.mark.parametrize('kind',['trend','range'])
def test_every_prefix_and_future_mutation(kind):
    t,d=bars(kind);full=R.describe(t,d)
    for i in range(1,len(t)+1):
        prefix=R.describe(t.iloc[:i],d.iloc[:i]);assert prefix=={k:v for k,v in full.items() if k<=str(t.index[i-1])}
        changed=t.copy();changed.iloc[i:,changed.columns.get_indexer(['open','high','low','close'])]*=3
        mutated=R.describe(changed,d)
        assert prefix=={k:v for k,v in mutated.items() if k<=str(t.index[i-1])}


def test_trend_range_and_hysteresis():
    t,d=bars();s=R.describe(t,d)
    assert s[str(t.index[5])]['state']=='UNAVAILABLE'
    assert s[str(t.index[6])]['state']=='TREND_UP'
    t,d=bars('range');assert 'RANGE' in {v['state'] for v in R.describe(t,d).values()}


@pytest.mark.parametrize('fault',['negative','nan','gap'])
def test_missing_or_bad_observations_reset_fail_closed(fault):
    t,d=bars()
    if fault=='negative':t.loc[t.index[20],'volume']=-1
    elif fault=='nan':t.loc[t.index[20],'close']=np.nan
    else:t=t.drop(t.index[19])
    assert R.describe(t,d)[str(pd.Timestamp('2026-01-02 10:55'))]['state']=='UNAVAILABLE'


def test_shock_not_smoothed_over():
    t,d=bars();t.loc[t.index[20],'high']+=10
    assert R.describe(t,d)[str(t.index[20])]['state']=='SHOCK'


def test_rule_really_selects_different_experts():
    assert R.rule_experts('TREND_UP')[0]=='DONCHIAN'
    assert R.rule_experts('RANGE')==['BOLL_REENTRY']
    assert R.rule_experts('TRANSITION')==['TPB']
    assert not R.rule_experts('SHOCK') and not R.direction_allowed('TREND_UP','SHORT')


def test_exit_invalidation_requires_three_confirmed_states():
    assert not R.invalidates('TREND_UP',['RANGE']*2,'LONG')
    assert R.invalidates('TREND_UP',['RANGE']*3,'LONG')
    assert not R.invalidates('TREND_UP',['RANGE','SHOCK','RANGE'],'LONG')
    assert R.invalidates('RANGE',['TREND_DOWN']*3,'LONG')
    assert not R.invalidates('RANGE',['TREND_UP']*3,'LONG')


def record(day,net=1000,exit=None):
    return {'day':day,'entry_time':day+'T10:00:00+05:30','exit_time':(exit or day)+'T11:00:00+05:30','expert':'DONCHIAN','cell':'TREND_UP|LOW','net':net}


def test_models_never_use_unclosed_or_future_labels():
    days=[(date(2024,1,1)+timedelta(days=i)).isoformat() for i in range(365)]
    records=[record(d) for d in days]
    a=R.fit_model(records,'2024-06-01',days)
    assert a['latest_label_exit'][:10]<'2024-06-01'
    changed=[{**r,'net':-1e6} if r['exit_time'][:10]>='2024-06-01' else r for r in records]
    assert a==R.fit_model(changed,'2024-06-01',days)
    assert a==R.fit_model(records+[record('2024-05-31',1e8,exit='2024-06-02')],'2024-06-01',days)
    assert a['choices']['TREND_UP|LOW'][0]['expert']=='DONCHIAN'


def test_insufficient_or_negative_training_does_not_invent_an_expert():
    days=[f'2024-01-{i:02d}' for i in range(1,31)]
    assert not R.fit_model([record(d) for d in days[:10]],'2024-02-01',days)['choices']['TREND_UP|LOW']
    assert not R.fit_model([record(d,-100) for d in days],'2024-02-01',days)['choices']['TREND_UP|LOW']


def test_numpy_result_types_are_native_json():
    v=X.native({'flag':np.bool_(False),'n':np.int64(3),'p':np.float64(.2),'a':np.array([1.,2.])})
    back=json.loads(json.dumps(v,allow_nan=False))
    assert back=={'flag':False,'n':3,'p':.2,'a':[1.,2.]} and type(back['flag']) is bool


def test_all_trigger_breakout_can_reenter_after_an_earlier_ineligible_signal():
    t,_=bars();t['high']=t['close']+.01
    f={'t':t,'stamps':list(t.index.strftime('%Y-%m-%d %H:%M:%S'))}
    m=X.experts()['DONCHIAN'];hits=X.all_triggers(m,f)
    assert len(hits)>2 and all(v[0]==1 for v in hits.values())


def test_book_matrix_and_controls_preserve_contract():
    base=X.books('base');child=X.books('candidate')
    assert len(base)==9 and len(child)==6
    assert 'n01_policy' not in base['MAIN'] and 'n01_policy' not in base['OLD_BREAKOUT_LOW']
    assert base['LIB|DONCHIAN']['members'][0]['n01_all_triggers'] is True
    assert not base['OLD_BREAKOUT_LOW']['members'][0].get('n01_all_triggers')
    assert child['EX|RULE']['members']==child['EX|RULE_EXIT']['members']


def test_close_metadata_bound_to_actual_leg_not_ticker_date(monkeypatch):
    monkeypatch.setattr(X,'_previous_close',lambda leg,*a,**k:({'net_pnl':1.},1.))
    leg=SimpleNamespace(_n01_metadata={'router_admission_id':'exact/17','initial_quantity':65,'initial_entry_premium':100.})
    r,_=X.close_record(leg,None);assert r['router_admission_id']=='exact/17' and r['initial_quantity']==65
    leg._n01_metadata['initial_quantity']=999
    assert r['initial_quantity']==65,'closed evidence must not alias mutable admission metadata'


def test_new_routing_leaves_baseline_route_untouched(monkeypatch):
    sentinel=object();monkeypatch.setattr(X,'_previous_route',lambda *a:sentinel)
    assert X.route(SimpleNamespace(book={}),None,None,None) is sentinel


@pytest.mark.parametrize('family',['DONCHIAN','BOLL_REENTRY'])
def test_new_expert_every_prefix_and_original_first_trigger_parity(family):
    t,_=bars('range');t['high']=t['close']+.05;t['low']=t['close']-.05
    if family=='DONCHIAN':t['close']=100+np.arange(len(t))*.3;t['high']=t['close']+.01;t['low']=t['close']-.1
    f={'t':t,'stamps':list(t.index.strftime('%Y-%m-%d %H:%M:%S'))};m=X.experts()[family]
    full=X.all_triggers(m,f)
    first={}
    for stamp,hit in full.items():first.setdefault(hit[0],(stamp,hit))
    old=X.B.entries(m,f)
    assert old=={stamp:hit for stamp,hit in first.values()}
    for i in range(2,len(t)+1):
        short={**f,'t':t.iloc[:i],'stamps':f['stamps'][:i]}
        assert X.all_triggers(m,short)=={k:v for k,v in full.items() if k<=str(t.index[i-1])}


def test_real_feature_pipeline_future_prices_do_not_change_states():
    rows=[]
    for day in pd.date_range('2026-01-01',periods=5):
        t,_=bars();t.index=pd.date_range(day.strftime('%Y-%m-%d')+' 09:15',periods=len(t),freq='5min');rows.append(t[['open','high','low','close','volume']])
    frame=pd.concat(rows);d=frame.index[-1].date()
    X._STATES.clear();X.B.O27F._FEATURES.clear();original=X.states(frame,d)[0]
    cut=pd.Timestamp(str(d)+' 11:00:00');changed=frame.copy();changed.loc[changed.index>cut,['open','high','low','close']]*=5
    X._STATES.clear();X.B.O27F._FEATURES.clear();mutated=X.states(changed,d)[0]
    assert {k:v for k,v in original.items() if k<=str(cut)}=={k:v for k,v in mutated.items() if k<=str(cut)}


@pytest.mark.parametrize('mode',['unpriced','too_early','normal_closed','switch'])
def test_management_always_first_and_no_unpriced_or_early_switch(monkeypatch,mode):
    calls=[]
    def original(self,book,obs,now):
        calls.append('normal')
        if mode=='normal_closed':book.open.clear()
    monkeypatch.setattr(X,'_previous_manage',original)
    history={f'2026-01-02 10:{i:02d}:00':{'state':'RANGE'} for i in (0,5,10)}
    monkeypatch.setattr(X,'state_at',lambda *a:({'state':'RANGE'},'2026-01-02 10:10:00',history))
    monkeypatch.setattr(X.Y.replay,'_close_record',lambda *a:({'net_pnl':1.},1.))
    now=datetime.fromisoformat('2026-01-02T10:16:00+05:30')
    leg=SimpleNamespace(entry_time=(now-timedelta(minutes=14 if mode=='too_early' else 20)).isoformat(),direction='LONG',token=7,initial_qty=65)
    book=SimpleNamespace(open={1:leg},trades=[],equity=100.,closes=[],completed=[])
    self=SimpleNamespace(book={'n01_policy':'RULE_EXIT'},_frame=object(),_n01_admissions={1:{'router_state':'TREND_UP'}},notes=Counter(),leg_member={1:0})
    obs=SimpleNamespace(options={} if mode=='unpriced' else {7:SimpleNamespace(bid=2.)},future=SimpleNamespace(ltp=100.))
    X.manage(self,book,obs,now)
    assert calls==['normal']
    if mode=='switch':assert not book.open and len(book.trades)==1 and book.equity==101.
    elif mode=='normal_closed':assert not book.open and not book.trades
    else:assert book.open and not book.trades
