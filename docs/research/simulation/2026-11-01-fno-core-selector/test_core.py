import copy,json,sys
from collections import Counter
from datetime import date,datetime,timedelta
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import core_lab as X
P=X.P


def histories(n=80):
    days=[(date(2024,1,1)+timedelta(days=i)).isoformat() for i in range(n)]
    rows=lambda net:[{'entry_time':d+'T10:00:00+05:30','exit_time':d+'T11:00:00+05:30','net_pnl':net} for d in days]
    return days,{'MAIN':rows(10.),'TPB_ONE':rows(110.),'NO_EFF':rows(-20.)}


def test_empty_or_weak_evidence_defaults_main():
    d,r=histories(4);m=P.evidence(r,'2024-03-01',d)
    assert not m['profiles']['TPB_ONE']['eligible']
    assert P.choose({'2024-03-01':m},P.ORDER)['2024-03-01']['profile']=='MAIN'


def test_positive_paired_evidence_and_future_outcomes_do_not_change_choice():
    d,r=histories();m=P.evidence(r,'2024-04-01',d)
    assert m['profiles']['TPB_ONE']['eligible'] and not m['profiles']['NO_EFF']['eligible']
    changed=copy.deepcopy(r)
    for rows in changed.values():rows.append({'entry_time':'2024-04-01T10:00:00+05:30','exit_time':'2024-04-01T11:00:00+05:30','net_pnl':1e8})
    assert P.evidence(changed,'2024-04-01',d+['2024-04-01'])==m
    changed['TPB_ONE'].append({'entry_time':'2024-03-30T10:00:00+05:30','exit_time':'2024-04-02T10:00:00+05:30','net_pnl':1e9})
    assert P.evidence(changed,'2024-04-01',d+['2024-04-01'])==m


def test_paired_increment_not_absolute_profit():
    d,r=histories()
    for row in r['MAIN']:row['net_pnl']=200.
    m=P.evidence(r,'2024-04-01',d)
    assert m['profiles']['TPB_ONE']['paired_net']<0 and not m['profiles']['TPB_ONE']['eligible']


def test_two_day_confirmation_and_immediate_main_fallback():
    d,r=histories();m=P.evidence(r,'2024-04-01',d);m2=copy.deepcopy(m);m2['asof']='2024-04-02'
    m3=copy.deepcopy(m);m3['asof']='2024-04-03';m3['profiles']['TPB_ONE']['eligible']=False
    out=P.choose({'2024-04-01':m,'2024-04-02':m2,'2024-04-03':m3},('TPB_ONE',))
    assert [v['profile'] for v in out.values()]==['MAIN','TPB_ONE','MAIN']


def test_one_big_lucky_day_cannot_qualify():
    d,r=histories()
    for row in r['TPB_ONE']:row['net_pnl']=0.
    r['TPB_ONE'][0]['net_pnl']=100000.
    m=P.evidence(r,'2024-04-01',d)
    assert not m['profiles']['TPB_ONE']['checks']['without_best'] and not m['profiles']['TPB_ONE']['eligible']


def fixture(monkeypatch,profile='MAIN',direction='LONG',stretch=0.):
    sig=NS(direction=NS(value=direction),bar_ts='2024-01-02 10:00:00')
    self=NS(book={'n02_policy':'STATIC','n02_profile':profile},table={'2024-01-02':{}},members=X.members(),calls=[])
    def signal(i,*args):self.calls.append(i);return sig
    self._signal=signal
    monkeypatch.setattr(X.Y.replay,'_last_closed_bar',lambda *a:sig.bar_ts)
    monkeypatch.setattr(X.Y.ROUTER,'allowed',lambda gate,row:gate.endswith('HIGH'))
    monkeypatch.setattr(X.S,'stretch_at',lambda *a:stretch)
    now=datetime.fromisoformat('2024-01-02T10:06:59+05:30')
    return self,sig,now


def test_main_order_and_stretched_first_signal_are_preserved(monkeypatch):
    self,sig,now=fixture(monkeypatch,stretch=.6)
    got=X.route(self,None,None,now)
    assert got.direction is None and self.calls==[0]


def test_low_put_addition_cap_and_entry_restoration(monkeypatch):
    self,sig,now=fixture(monkeypatch,profile='TPB_ONE',direction='SHORT')
    monkeypatch.setattr(X.Y.ROUTER,'allowed',lambda gate,row:gate.endswith('LOW'))
    before=(X.settings.FNO_MAX_LOTS,X.settings.FNO_MAX_LOTS_PROVEN)
    book=NS(next_id=1,open={})
    def base(self,*args):
        assert X.route(self,None,None,now).direction.value=='SHORT'
        assert X.settings.FNO_MAX_LOTS<=1 and X.settings.FNO_MAX_LOTS_PROVEN<=1
        raise RuntimeError('simulated admission failure')
    monkeypatch.setattr(X,'_old_entry',base)
    with pytest.raises(RuntimeError):X.entry(self,book,None,None,None,now)
    assert (X.settings.FNO_MAX_LOTS,X.settings.FNO_MAX_LOTS_PROVEN)==before


def test_low_day_call_refused_without_changing_core_limits(monkeypatch):
    self,sig,now=fixture(monkeypatch,profile='TPB_ONE',direction='LONG')
    monkeypatch.setattr(X.Y.ROUTER,'allowed',lambda gate,row:gate.endswith('LOW'))
    before=(X.settings.FNO_MAX_LOTS,X.settings.FNO_MAX_LOTS_PROVEN)
    assert X.route(self,None,None,now).direction is None
    assert (X.settings.FNO_MAX_LOTS,X.settings.FNO_MAX_LOTS_PROVEN)==before


def test_selector_missing_bar_does_not_enter(monkeypatch):
    self,sig,now=fixture(monkeypatch);self.book={'n02_policy':'CORE_ADD'}
    monkeypatch.setattr(X.Y.replay,'_last_closed_bar',lambda *a:None)
    assert X.route(self,None,None,now).direction is None


def test_main_remains_available_after_any_signal_with_no_challenger(monkeypatch):
    self,sig,now=fixture(monkeypatch);self.book={'n02_policy':'CORE_ADD'}
    monkeypatch.setattr(X,'decisions',lambda:{'CORE_ADD':{'2024-01-02':{'profile':'MAIN','asof':'2024-01-02','latest_label_exit':None}}})
    assert X.route(self,None,None,now) is sig and self._fired==0


def test_admission_metadata_is_copied_from_exact_leg(monkeypatch):
    leg=NS(_n02_metadata={'admission_id':'exact/1','initial_quantity':65})
    monkeypatch.setattr(X,'_old_close',lambda *a:({'net_pnl':1.},1.))
    row,_=X.close_record(leg,None);leg._n02_metadata['initial_quantity']=999
    assert row['initial_quantity']==65 and row['admission_id']=='exact/1'


def test_book_matrix_does_not_mutate_member_policy_when_selection_changes():
    refs=X.books('reference');children=X.books('candidate')
    assert len(refs)==4 and len(children)==2
    assert all(b['members']==X.members() for b in [*refs.values(),*children.values()])
    assert X.INDEX['MAIN']==(0,1,2,3) and X.INDEX['NO_EFF']==(0,1,3)
