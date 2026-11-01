"""Additional contract verification; no strategy/scoring changes."""
import sys
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace as NS
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core_lab as X

@pytest.mark.parametrize('clock,allowed',[('10:09:59',True),('10:10:00',False),('10:10:01',False)])
def test_latest_closed_bar_end_freshness_boundary(monkeypatch,clock,allowed):
    sig=NS(direction=NS(value='LONG'),bar_ts='2024-01-02 10:00:00')
    engine=NS(book={'n02_policy':'CORE_ADD'},table={'2024-01-02':{}},members=X.members(),_signal=lambda *a:sig)
    monkeypatch.setattr(X.Y.replay,'_last_closed_bar',lambda *a:sig.bar_ts)
    monkeypatch.setattr(X.Y.ROUTER,'allowed',lambda *a:True)
    monkeypatch.setattr(X.S,'stretch_at',lambda *a:0.)
    monkeypatch.setattr(X,'decisions',lambda:{'CORE_ADD':{'2024-01-02':{'profile':'MAIN','asof':'2024-01-02','latest_label_exit':None}}})
    got=X.route(engine,None,None,datetime.fromisoformat('2024-01-02T'+clock+'+05:30'))
    assert (got.direction is not None)==allowed

def test_successful_low_addition_restores_main_limits_and_keeps_exact_leg(monkeypatch):
    now=datetime.fromisoformat('2024-01-02T10:06:59+05:30');sig=NS(direction=NS(value='SHORT'),bar_ts='2024-01-02 10:00:00')
    engine=NS(book=X.book('contract','STATIC','TPB_ONE'),table={'2024-01-02':{}},members=X.members(),_signal=lambda *a:sig,decisions=[])
    monkeypatch.setattr(X.Y.replay,'_last_closed_bar',lambda *a:sig.bar_ts)
    monkeypatch.setattr(X.Y.ROUTER,'allowed',lambda gate,row:gate.endswith('LOW'))
    monkeypatch.setattr(X.S,'stretch_at',lambda *a:0.)
    monkeypatch.setattr(X.settings,'FNO_MAX_LOTS',2);monkeypatch.setattr(X.settings,'FNO_MAX_LOTS_PROVEN',3)
    cash=NS(next_id=1,open={})
    def accepted(self,book,*args):
        assert X.route(self,None,None,now) is sig
        assert (X.settings.FNO_MAX_LOTS,X.settings.FNO_MAX_LOTS_PROVEN)==(1,1)
        book.open[1]=NS(entry_time=now.isoformat(),entry_premium=100.,initial_qty=65,stop_underlying=21900.,target_underlying=21700.)
        book.next_id=2
    monkeypatch.setattr(X,'_old_entry',accepted);X.entry(engine,cash,None,None,None,now)
    assert (X.settings.FNO_MAX_LOTS,X.settings.FNO_MAX_LOTS_PROVEN)==(2,3)
    original=cash.open[1]._n02_metadata;engine._n02_decision['selected_profile']='NO_EFF'
    assert original['selected_profile']=='TPB_ONE' and original['initial_quantity']==65 and original['initial_entry_premium']==100.
    assert original['initial_stop_underlying']==21900. and original['initial_target_underlying']==21700.
    engine.book=X.book('contract-main','STATIC','MAIN');monkeypatch.setattr(X.Y.ROUTER,'allowed',lambda gate,row:gate.endswith('HIGH'))
    assert X.route(engine,None,None,now) is sig
    assert (X.settings.FNO_MAX_LOTS,X.settings.FNO_MAX_LOTS_PROVEN)==(2,3)
