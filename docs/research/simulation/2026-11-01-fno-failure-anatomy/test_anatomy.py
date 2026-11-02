from pathlib import Path
from datetime import datetime
from types import SimpleNamespace as NS
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import anatomy_lab as L
R=L.R


@pytest.mark.parametrize('mode',['PREMIUM_STALL','STRUCT_OR_PREMIUM'])
@pytest.mark.parametrize('bid,clock',[(99.,30.),(100.,30.),(100.01,60.)])
def test_actual_price_break_even_boundary(mode,bid,clock):assert R.choose(mode,True,30.,bid,100.)[0]==clock


@pytest.mark.parametrize('age,eligible',[(29.99,True),(60.,True),(30.,False),(float('nan'),True)])
def test_original_stall_eligibility_and_clock_remain_required(age,eligible):assert R.choose('STRUCT_OR_PREMIUM',eligible,age,99.,100.,{'fresh':True,'close':99.},100.)[0]==60.


@pytest.mark.parametrize('bid,entry',[(None,100.),(0.,100.),(float('nan'),100.),(99.,0.),(99.,float('inf'))])
def test_missing_or_invalid_price_cannot_create_exit(bid,entry):assert R.choose('STRUCT_OR_PREMIUM',True,31.,bid,entry,{'fresh':True,'close':99.},100.)[0]==60.


@pytest.mark.parametrize('direction,close,clock',[('LONG',99.,30.),('LONG',100.,60.),('SHORT',101.,30.),('SHORT',100.,60.)])
def test_structure_alternative_does_not_require_premium_loss(direction,close,clock):
    assert R.choose('STRUCT_OR_PREMIUM',True,31.,101.,100.,{'fresh':True,'close':close},100.,direction)[0]==clock
    assert R.choose('PREMIUM_STALL',True,31.,101.,100.,{'fresh':True,'close':close},100.,direction)[0]==60.


def test_stale_or_missing_structure_still_allows_observed_premium_weakness():
    for structure in (None,{'fresh':False,'close':99.},{'fresh':True,'close':float('nan')}):
        assert R.choose('STRUCT_OR_PREMIUM',True,31.,99.,100.,structure,100.)[0]==30.
        assert R.choose('STRUCT_OR_PREMIUM',True,31.,101.,100.,structure,100.)[0]==60.


def test_unknown_mode_and_direction_refused():
    with pytest.raises(ValueError):R.choose('invalid',True,31.,99.,100.)
    assert R.choose('PREMIUM_STALL',True,31.,99.,100.,direction='invalid')[0]==60.


def test_review_uses_immutable_entry_price_and_level_current_bid(monkeypatch):
    leg=NS(entry_premium=100.,qty=130,direction='LONG',_n02_metadata={'n03_entry_context':{'broken_level':1000.}})
    monkeypatch.setattr(L.P.P.E,'liquidation',lambda *a:(30.,{'age_minutes':31.,'bid':101.,'progress_r':.1,'net_at_bid_after_cost':-300.}))
    monkeypatch.setattr(L.P.P.E,'context',lambda *a:{'fresh':True,'close':1001.})
    minute,c=L.review(leg,None,None,None,'STRUCT_OR_PREMIUM');assert minute==60 and c['gross_at_bid']==130. and c['original_retest_level']==1000.
    leg._n02_metadata['n03_entry_context']['broken_level']=0.;assert c['original_retest_level']==1000.


def test_per_leg_policies_and_open_map_restore_on_exception(monkeypatch):
    policies=[L.Y.member_policy(L.Y.named('EFF'))];full={1:NS(clock=30.),2:NS(clock=60.)};book=NS(open=full);engine=NS(book={'n07_mode':'PREMIUM_STALL'},members=[{'name':'EFF'}],leg_member={1:0,2:0},policies=policies,_frame=None);seen=[]
    monkeypatch.setattr(L,'review',lambda leg,*a:(leg.clock,{'action':'test'}))
    def native(self,book,*a):
        seen.append(dict(self.policies[0].exit_overrides)['FNO_TIME_STOP_MIN'])
        if next(iter(book.open))==2:raise RuntimeError('simulated')
    monkeypatch.setattr(L,'_manage',native)
    with pytest.raises(RuntimeError):L.manage(engine,book,None,None)
    assert seen==[30.,60.] and engine.policies is policies and book.open is full


@pytest.mark.parametrize('mode',['PREMIUM_STALL','STRUCT_OR_PREMIUM'])
@pytest.mark.parametrize('reason,clock,future',[('hard_flat_1510','15:10:00',1025.),('underlying_stop','10:31:00',980.)])
def test_native_urgent_exits_take_priority(monkeypatch,mode,reason,clock,future):
    now=datetime.fromisoformat('2024-01-02T'+clock+'+05:30');entered='2024-01-02T14:00:00+05:30' if reason.startswith('hard') else '2024-01-02T10:00:00+05:30'
    leg=L.Y.replay.OpenLeg(id=1,tradingsymbol='NIFTY2401041000CE',token=1,direction='LONG',lots=1,lot_size=65,entry_time=entered,entry_premium=100.,entry_underlying=1000.,stop_underlying=980.,target_underlying=1100.,premium_stop=70.,atr_at_entry=10.,delta_at_entry=.5,bar_ts=entered[:10]+' 09:55:00',initial_qty=65,best_underlying=1000.)
    engine=L.Y.BookReplay(None,L.books()['NORMAL|'+mode],{},'year');engine.leg_member={1:2};book=L.Y.replay.Book(equity=250000.,open={1:leg});obs=NS(options={1:NS(bid=90.,ltp=90.)},future=NS(ltp=future))
    monkeypatch.setattr(L.X.settings,'FNO_HARD_FLAT_MIN',910);monkeypatch.setattr(L,'review',lambda *a:(60.,{'action':'NATIVE60'}))
    L.manage(engine,book,obs,now);assert not book.open and book.trades[0]['exit_reason']==reason


def test_matrix_inherits_original_caps_and_priority():
    b=L.books();assert len(b)==15
    for n,v in b.items():
        assert [m['name'] for m in v['members']]==['SHIPPED','OR20','EFF','TPB','TPB']
        assert v['n03_variant']=='RETEST'
        if n.startswith('ONE|'):assert v['cfg']=={'FNO_MAX_LOTS':1,'FNO_MAX_LOTS_PROVEN':1}
        else:assert not v['cfg']
        if n.startswith('NO_EXTRA_STRESS|'):assert v['cost']==[0.,0.]
        else:assert v['cost']==[200.,5.]


def test_real_cli_control_preflight_does_not_double_import_replay_graph():
    import subprocess
    result=subprocess.run([sys.executable,str(L.HERE/'anatomy_lab.py'),'check-controls'],cwd=L.ROOT,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert 'PRE_CANDIDATE_CONTROLS_VERIFIED 18' in result.stdout
