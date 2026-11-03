"""Causal, clock and risk regressions for new E03.1 research mechanisms."""
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import lab as L

def pos():return dict(entry=10.,entry_i=10,direction=1)

def test_stall_waits_and_uses_current_bid():
    r=replace(L.BASE,stall_minutes=3,stall_gain=.1)
    assert not L.stalled(r,12,pos(),5.)
    assert L.stalled(r,13,pos(),10.9)
    assert not L.stalled(r,13,pos(),11.)

def test_extension_requires_profit_both_markets_and_expires():
    r=replace(L.BASE,extend_minutes=4,extend_gain=.1)
    t=SimpleNamespace(close=np.arange(40,dtype=float),f=np.tile(np.arange(40.)[:,None],(1,4)))
    assert not L.timed_out(t,r,18,pos(),11.,.1)
    assert L.timed_out(t,r,22,pos(),11.,.1)
    assert L.timed_out(t,r,18,pos(),10.9,.1)
    t.f[18,3]=0.
    assert L.timed_out(t,r,18,pos(),11.,.1)

def test_future_data_never_changes_extension():
    r=replace(L.BASE,extend_minutes=4,extend_gain=.1)
    t=SimpleNamespace(close=np.arange(40,dtype=float),f=np.tile(np.arange(40.)[:,None],(1,4)))
    a=L.timed_out(t,r,18,pos(),11.,.1)
    t.close[19:]=np.nan;t.f[19:]=np.nan
    assert L.timed_out(t,r,18,pos(),11.,.1)==a

def test_missing_confirmation_exits():
    t=SimpleNamespace(close=np.arange(40,dtype=float),f=np.tile(np.arange(40.)[:,None],(1,4)))
    t.close[15]=np.nan
    assert L.timed_out(t,replace(L.BASE,extend_minutes=4),18,pos(),15.,.5)

def test_baseline_no_early_stall_or_extension():
    assert not L.stalled(L.BASE,100,pos(),.1)
    assert L.timed_out(None,L.BASE,18,pos(),20.,1.)

def test_new_entry_cap_does_not_look_at_next_bar(monkeypatch):
    monkeypatch.setattr(L.X,'choose',lambda *args:(0,2,11.))
    t=SimpleNamespace(q=np.array([[[10.,99.,1.,10.,10000.]]]))
    r=replace(L.BASE,chase=.025)
    a=L.choose(t,0,1,r,1250.,25000.)
    assert a==(0,2,10.3)
    t.q[0,0,1:3]=[1e9,.001]
    assert L.choose(t,0,1,r,1250.,25000.)==a
