from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import risk_lab as R

def t(price):return SimpleNamespace(q=np.array([[[price,price,price,price,10000.]]]))

def test_runner_only_increases_original_one_lot_same_contract(monkeypatch):
    monkeypatch.setattr(R.L,'choose',lambda *a:(0,1,12.))
    pick=R.choose(t(10.),0,1,R.ARMS['RUNNER25'],1562.5,25000)
    assert pick[0]==0 and pick[1]==2 and R.E.reserve(pick[2],pick[1])<=1562.51
    monkeypatch.setattr(R.L,'choose',lambda *a:(0,2,8.))
    assert R.choose(t(6.),0,1,R.ARMS['RUNNER25'],1562.5,25000)==(0,2,8.)

def test_extra_reserve_does_not_admit_missing_baseline_strike(monkeypatch):
    monkeypatch.setattr(R.L,'choose',lambda *a:None)
    assert R.choose(t(20.),0,1,R.ARMS['SCALE25'],1562.5,25000) is None

def test_original_selection_always_uses_old_ticket_limit(monkeypatch):
    rooms=[]
    def choose(*a):rooms.append(a[-2]);return (0,1,10.)
    monkeypatch.setattr(R.L,'choose',choose)
    R.choose(t(10.),0,1,R.ARMS['SCALE25'],1562.5,25000)
    assert rooms==[1250.]

def test_resize_obeys_capacity_cash_fees_and_integer_lots():
    p=R.resize(t(10.),0,0,3,1562.5,25000,.1)
    assert p[1]==2
    assert R.resize(t(10.),0,0,3,1562.5,600,.1) is None or R.resize(t(10.),0,0,3,1562.5,600,.1)[1]<=1
    tt=t(10.);tt.q[0,0,4]=100
    assert R.resize(tt,0,0,3,1562.5,25000,.1) is None
