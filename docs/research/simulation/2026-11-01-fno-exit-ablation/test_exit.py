import json,sys
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace as NS
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import exit_lab as L

@pytest.mark.parametrize('age,trail,net,progress,fresh,combined',[(29.99,False,-1.,0.,True,60.),(30.,False,0.,.49,True,30.),(31.,True,-1.,0.,True,60.),(60.,False,1.,1.,True,90.),(60.,False,0.,1.,True,60.),(61.,False,1.,1.,False,60.),(90.,False,1.,1.,True,60.)])
def test_exact_parent_cases_separate_only_intended_behavior(age,trail,net,progress,fresh,combined):
    ctx={'fresh':fresh,'valid_volume':True,'close':102.,'previous_close':101.,'vwap':100.}
    got=L.E.R.horizon(age,trail,net,progress,ctx,'LONG')[0];assert got==combined
    assert L.R.choose('STALL_ONLY',got)[0]==(30. if combined==30. else 60.)
    assert L.R.choose('CONTINUE_ONLY',got)[0]==(90. if combined==90. else 60.)
    assert L.R.choose('BASE',got)==(60.,'BASE60')

def test_unknown_modes_or_parent_clocks_fail():
    with pytest.raises(ValueError):L.R.choose('unknown',30.)
    with pytest.raises(ValueError):L.R.choose('STALL_ONLY',999.)

@pytest.mark.parametrize('mode,expected',[('STALL_ONLY',[30.,60.]),('CONTINUE_ONLY',[60.,90.])])
def test_concurrent_eff_legs_and_exception_restoration(monkeypatch,mode,expected):
    policy=L.Y.member_policy(L.Y.named('EFF'));policies=[policy];full={1:NS(mark=30.),2:NS(mark=90.)};book=NS(open=full)
    engine=NS(book={'n04_mode':mode,'n03_variant':'BASE'},members=[{'name':'EFF'}],leg_member={1:0,2:0},policies=policies,_frame=None);seen=[]
    monkeypatch.setattr(L.E,'liquidation',lambda leg,*a:(leg.mark,{'action':'STALL30' if leg.mark==30. else 'CONTINUE90'}))
    def original(self,book,*a):
        seen.append(dict(self.policies[0].exit_overrides)['FNO_TIME_STOP_MIN'])
        if next(iter(book.open))==2:raise RuntimeError('report-only simulated failure')
    monkeypatch.setattr(L,'_manage',original)
    with pytest.raises(RuntimeError):L.manage(engine,book,None,None)
    assert seen==expected and engine.policies is policies and book.open is full
    assert not full[1]._n04_ever_extended
    assert full[2]._n04_ever_extended==(mode=='CONTINUE_ONLY')

def test_base_delegates_original_management_once(monkeypatch):
    engine=NS(book={'n04_mode':'BASE'});book=object();calls=[]
    monkeypatch.setattr(L,'_manage',lambda *a:calls.append(a) or 17)
    assert L.manage(engine,book,None,None)==17 and calls==[(engine,book,None,None)]

@pytest.mark.parametrize('mode,reason,clock,future',[('CONTINUE_ONLY','hard_flat_1510','15:10:00',1025.),('STALL_ONLY','underlying_stop','10:31:00',980.)])
def test_urgent_native_exit_wins_over_ablation(monkeypatch,mode,reason,clock,future):
    now=datetime.fromisoformat('2024-01-02T'+clock+'+05:30');entered='2024-01-02T14:00:00+05:30' if reason.startswith('hard') else '2024-01-02T10:00:00+05:30'
    leg=L.Y.replay.OpenLeg(id=1,tradingsymbol='NIFTY2401041000CE',token=1,direction='LONG',lots=1,lot_size=65,entry_time=entered,entry_premium=100.,entry_underlying=1000.,stop_underlying=980.,target_underlying=1100.,premium_stop=70.,atr_at_entry=10.,delta_at_entry=.5,bar_ts=entered[:10]+' 09:55:00',initial_qty=65,best_underlying=1000.)
    engine=L.Y.BookReplay(None,L.books()['NORMAL|MAIN|'+mode],{},'year');engine.leg_member={1:2};book=L.Y.replay.Book(equity=250000.,open={1:leg});obs=NS(options={1:NS(bid=90.,ltp=90.)},future=NS(ltp=future))
    monkeypatch.setattr(L.X.settings,'FNO_HARD_FLAT_MIN',910)
    monkeypatch.setattr(L.E,'liquidation',lambda *a:(90. if mode=='CONTINUE_ONLY' else 30.,{'action':'CONTINUE90' if mode=='CONTINUE_ONLY' else 'STALL30'}))
    L.manage(engine,book,obs,now);assert not book.open and book.trades[0]['exit_reason']==reason
    assert book.equity==pytest.approx(250000.+book.trades[0]['net_pnl'],abs=.0001)

def test_retest_is_unchanged_and_matrix_only_has_two_exit_hypotheses():
    books=L.books();assert len(books)==18 and L.Y.BookReplay._signal is L.E.signal
    assert {b['n04_mode'] for b in books.values()}=={'BASE','STALL_ONLY','CONTINUE_ONLY'}
    for n,b in books.items():
        assert b['n03_variant']==('RETEST' if b['n04_context']=='BALANCED_RETEST' else 'BASE')
        if n.startswith('ONE|'):assert b['cfg']=={'FNO_MAX_LOTS':1,'FNO_MAX_LOTS_PROVEN':1}

def test_durable_preferred_reference_is_exact_and_unqualified():
    p=L.ROOT/'docs/FNO_RESEARCH_REFERENCE.json';r=json.loads(p.read_text())
    assert r['preferred_id']=='BALANCED_RETEST_N03' and r['book_key']=='NORMAL|TPB_ONE|RETEST' and not r['qualified'] and not r['deployed']
    assert r['freeze_sha256']==L.B.P.sha(L.PARENT/'freeze.json') and r['results_sha256']==L.B.P.sha(L.PARENT/'results.json')
    for y,v in r['years'].items():assert v['evaluation_sha256']==L.B.P.sha(L.ROOT/v['evaluation'])
