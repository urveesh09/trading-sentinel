from types import SimpleNamespace
import numpy as np
import smart_lab as S

def tape():return SimpleNamespace(day='2025-01-02',q=np.array([[[10.,10.,10.,10.,1000.]]]))

def test_missing_or_negative_prediction_never_adds_risk(monkeypatch):
    monkeypatch.setattr(S.L,'choose',lambda *a:(0,1,11.))
    S.ELIGIBLE_DAYS={'2025-01-02'};S.FORECAST={}
    assert S.choose(tape(),0,1,S.ARMS['SMART_RUNNER25'],1562.5,25000)==(0,1,11.)
    S.FORECAST={('2025-01-02',0,0,1):-.1}
    assert S.choose(tape(),0,1,S.ARMS['SMART_RUNNER25'],1562.5,25000)==(0,1,11.)

def test_positive_prediction_only_changes_exact_contract_one_lot(monkeypatch):
    monkeypatch.setattr(S.L,'choose',lambda *a:(0,1,11.))
    S.ELIGIBLE_DAYS={'2025-01-02'};S.FORECAST={('2025-01-02',0,0,1):.1}
    pick=S.choose(tape(),0,1,S.ARMS['SMART_RUNNER25'],1562.5,25000)
    assert pick[0]==0 and pick[1]==2
    monkeypatch.setattr(S.L,'choose',lambda *a:(0,2,7.))
    assert S.choose(tape(),0,1,S.ARMS['SMART_RUNNER25'],1562.5,25000)==(0,2,7.)

def test_warmup_runs_unchanged_even_with_future_prediction(monkeypatch):
    monkeypatch.setattr(S.L,'choose',lambda *a:(0,1,11.))
    S.ELIGIBLE_DAYS=set();S.FORECAST={('2025-01-02',0,0,1):1.}
    assert S.choose(tape(),0,1,S.ARMS['SMART_RUNNER25'],1562.5,25000)==(0,1,11.)
