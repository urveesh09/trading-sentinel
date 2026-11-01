import copy
from collections import Counter
from datetime import date, datetime, timedelta
import sys
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import variant_lab as L
R = L.R


def labels():
    ds = [(date(2024,1,1)+timedelta(days=i)).isoformat() for i in range(115) if (date(2024,1,1)+timedelta(days=i)).weekday()<5]
    rows = {}
    for p in R.ORDER:
        rows[p] = [dict(entry_time=d+'T10:00:00+05:30',exit_time=d+'T11:00:00+05:30',net_pnl=100. if p=='MAIN' else 200.) for d in ds]
    return ds,rows


def test_future_and_same_day_labels_cannot_change_decision():
    ds, rows = labels();asof=ds[-1];before=R.evidence(rows,asof,ds,'MAIN')
    for p in R.ORDER:
        rows[p][-1]['net_pnl']=float('nan')
        rows[p].append(dict(entry_time='2024-12-01',exit_time='2024-12-02',net_pnl=-999999.))
    assert R.evidence(rows,asof,ds+['2024-12-02'],'MAIN')==before
    assert before['latest_label_exit'][:10]<asof and before['profiles']['BASE']['eligible']


def test_persistence_and_immediate_missing_support_fallback():
    ds, rows=labels();models={d:R.evidence(rows,d,ds,'MAIN') for d in ds};a=R.choose(models,'MAIN')
    eligible=[d for d in ds if models[d]['profiles']['BASE']['eligible']]
    assert a[eligible[0]]['variant']=='MAIN' and a[eligible[1]]['variant']=='BASE'
    m=copy.deepcopy(models[eligible[1]])
    for v in m['profiles'].values():v['eligible']=False
    models[eligible[1]]=m
    assert R.choose(models,'MAIN')[eligible[1]]['variant']=='MAIN'


def test_same_year_window_and_deterministic_tie_order():
    ds,rows=labels();m=R.evidence(rows,'2025-01-02',ds+['2025-01-01'],'MAIN')
    assert m['sessions']==1 and m['latest_label_exit'] is None
    models={d:R.evidence(rows,d,ds,'MAIN') for d in ds}
    assert R.choose(models,'MAIN')[ds[-1]]['variant']=='BASE'


@pytest.mark.parametrize('reason',['weeks','paired_days','challenger_trades','anchor_trades','score','without_best','drawdown'])
def test_each_failed_gate_refuses_challenger(reason):
    ds,rows=labels();m=R.evidence(rows,ds[-1],ds,'MAIN');assert m['profiles']['BASE']['eligible']
    # Test composition directly via histories with an independently failing guard.
    check=m['profiles']['BASE']['checks'];check[reason]=False
    for p,v in m['profiles'].items():v['eligible']=all(check.values())
    assert R.choose({ds[-1]:m},'MAIN')[ds[-1]]['variant']=='MAIN'


@pytest.mark.parametrize('value',[float('nan'),float('inf'),-float('inf')])
def test_invalid_past_economics_refused(value):
    ds,rows=labels();rows['BASE'][0]['net_pnl']=value
    with pytest.raises(ValueError):R.evidence(rows,ds[-1],ds,'MAIN')


def test_invalid_past_entry_exit_order_and_unknown_inventory():
    ds,rows=labels();rows['BASE'][0]['entry_time']='2024-12-31'
    with pytest.raises(ValueError):R.evidence(rows,ds[-1],ds,'MAIN')
    with pytest.raises(ValueError):R.evidence({},ds[-1],ds,'MAIN')


def test_noncausal_model_refused():
    ds,rows=labels();m=R.evidence(rows,ds[-1],ds,'MAIN');m['latest_label_exit']=ds[-1]
    with pytest.raises(ValueError):R.choose({ds[-1]:m},'MAIN')


def test_entry_restores_configuration_and_binds_immutable_policy(monkeypatch):
    original=L.books('candidate')['MAIN_ANCHOR'];self=NS(book=original,notes=Counter(),decisions=[]);book=NS(next_id=1,open={})
    d=dict(variant='STALL30',asof='2024-01-02',latest_label_exit='2024-01-01T11:00:00+05:30')
    monkeypatch.setattr(L,'decision',lambda *a:copy.deepcopy(d))
    def underlying(engine,book,*a):
        assert engine.book['n03_variant']=='RETEST' and engine.book['n02_profile']=='TPB_ONE'
        book.open[1]=NS(_n02_metadata={});book.next_id+=1;engine.decisions.append({})
    monkeypatch.setattr(L,'_entry',underlying)
    L.entry(self,book,None,None,None,datetime.fromisoformat('2024-01-02T10:00:00+05:30'))
    assert self.book is original and original['n03_variant']=='BASE'
    m=book.open[1]._n02_metadata
    assert m['n06_variant']=='STALL30' and m['admission_id']==f'N06/{L.B.YEAR}/{L.Y.digest(original)}/1'
    d['variant']='MAIN';assert m['n06_decision']['variant']=='STALL30'
    assert self.decisions[0]['n06_variant']=='STALL30'


def test_entry_error_restores_original_and_retest_resets_only_on_scope_change(monkeypatch):
    original=L.books('candidate')['MAIN_ANCHOR'];self=NS(book=original,notes=Counter(),decisions=[]);book=NS(next_id=1)
    d=dict(variant='BASE',asof='2024-01-02',latest_label_exit=None)
    monkeypatch.setattr(L,'decision',lambda *a:d)
    def fail(*a):raise RuntimeError('simulated')
    monkeypatch.setattr(L,'_entry',fail)
    now=datetime.fromisoformat('2024-01-02T10:00:00+05:30')
    with pytest.raises(RuntimeError):L.entry(self,book,None,None,None,now)
    state=self._n03_retest;assert self.book is original
    with pytest.raises(RuntimeError):L.entry(self,book,None,None,None,now)
    assert self._n03_retest is state
    d['variant']='MAIN'
    with pytest.raises(RuntimeError):L.entry(self,book,None,None,None,now)
    assert self._n03_retest is not state


def test_missing_decision_does_not_call_entry(monkeypatch):
    self=NS(book=L.books('candidate')['MAIN_ANCHOR'],notes=Counter())
    def missing(*a):raise KeyError('missing')
    monkeypatch.setattr(L,'decision',missing);monkeypatch.setattr(L,'_entry',lambda *a:pytest.fail('entry called'))
    L.entry(self,None,None,None,None,datetime.now());assert self.notes['n06_decision_unavailable']==1


def test_held_leg_retains_admitted_policy_and_restores_on_exception(monkeypatch):
    policies=[L.Y.member_policy(L.Y.named('EFF'))]
    full={1:NS(_n02_metadata={'n06_variant':'STALL30'}),2:NS(_n02_metadata={'n06_variant':'STRUCT30'})}
    self=NS(book=L.books('candidate')['MAIN_ANCHOR'],policies=policies,members=[{'name':'EFF'}],leg_member={1:0,2:0},_frame=None)
    book=NS(open=full);seen=[]
    monkeypatch.setattr(L.P,'review',lambda leg,obs,now,frame,mode:(30. if mode=='STALL30' else 60.,{'mode':mode}))
    def native(engine,book,*a):
        seen.append(dict(engine.policies[0].exit_overrides)['FNO_TIME_STOP_MIN'])
        if next(iter(book.open))==2:raise RuntimeError('simulated')
    monkeypatch.setattr(L,'_manage',native)
    with pytest.raises(RuntimeError):L.manage(self,book,None,None)
    assert seen==[30.,60.] and book.open is full and self.policies is policies


@pytest.mark.parametrize('reason,clock,future',[('hard_flat_1510','15:10:00',1025.),('underlying_stop','10:31:00',980.)])
def test_selector_preserves_urgent_exit_priority(monkeypatch,reason,clock,future):
    now=datetime.fromisoformat('2024-01-02T'+clock+'+05:30');entered='2024-01-02T14:00:00+05:30' if reason.startswith('hard') else '2024-01-02T10:00:00+05:30'
    leg=L.Y.replay.OpenLeg(id=1,tradingsymbol='NIFTY2401041000CE',token=1,direction='LONG',lots=1,lot_size=65,entry_time=entered,entry_premium=100.,entry_underlying=1000.,stop_underlying=980.,target_underlying=1100.,premium_stop=70.,atr_at_entry=10.,delta_at_entry=.5,bar_ts=entered[:10]+' 09:55:00',initial_qty=65,best_underlying=1000.)
    leg._n02_metadata={'n06_variant':'STALL30'}
    engine=L.Y.BookReplay(None,L.books('candidate')['MAIN_ANCHOR'],{},'year');engine.leg_member={1:2};book=L.Y.replay.Book(equity=250000.,open={1:leg});obs=NS(options={1:NS(bid=90.,ltp=90.)},future=NS(ltp=future))
    monkeypatch.setattr(L.X.settings,'FNO_HARD_FLAT_MIN',910);monkeypatch.setattr(L.P,'review',lambda *a:(30.,{'action':'STALL30'}))
    L.manage(engine,book,obs,now);assert not book.open and book.trades[0]['exit_reason']==reason


def test_stale_adaptive_bar_refused_and_caps_unchanged(monkeypatch):
    monkeypatch.setattr(L.Y.replay,'_last_closed_bar',lambda *a:'2024-01-02 09:50:00')
    monkeypatch.setattr(L,'_route',lambda *a:pytest.fail('stale routed'))
    self=NS(book=L.books('candidate')['MAIN_ANCHOR'])
    assert L.route(self,None,None,datetime.fromisoformat('2024-01-02T10:00:00+05:30')).direction is None
    for phase,n in [('reference',4),('candidate',2)]:
        bs=L.books(phase);assert len(bs)==n
        for b in bs.values():assert not b['cfg'] and b['n05_mode']=='BASE' and b['n02_policy']=='STATIC'
