"""Causal order/signal contracts; no historical outcome is an assertion target."""
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import mechanisms as M

def test_patient_expiry_and_previous_bar_cancel():
    t=SimpleNamespace(close=np.array([100.,101.,99.,50.,103.]),minute=np.arange(780,785))
    r=replace(M.BASE,mechanism='patient')
    assert not M.patient_cancel(t,2,0,1,2.,r) # current low is not observed at its open
    assert not M.patient_cancel(t,3,0,1,2.,r)
    assert M.patient_cancel(t,4,0,1,2.,r)

def test_patient_limit_does_not_invent_spread_capture(monkeypatch):
    t=SimpleNamespace(q=np.array([[[5.,5.,5.,5.,1000.]]]))
    monkeypatch.setattr(M.L,'choose',lambda *a:(0,2,5.5))
    assert M.choose(t,0,1,replace(M.BASE,mechanism='patient'),1250,25000)==(0,2,5.)
    assert M.choose(t,0,1,M.BASE,1250,25000)==(0,2,5.5)

def toy():
    n=65;ks=np.array([9950,9950,10000,10000,10050,10050]);kinds=np.tile([1,-1],3)
    t=SimpleNamespace(n=n,strikes=ks,kinds=kinds,minute=np.arange(770,770+n),
       close=np.linspace(9990,10010,n),f=np.zeros((n,4)),q=np.ones((n,6,5))*10)
    t.f[:,3]=t.close
    for i in range(n):
        t.q[i,0::2,3]=10*np.exp(.0005*i*i)
        t.q[i,1::2,3]=10*np.exp(-.0005*i*i)
        t.q[i,:,4]=1000
    return t

def test_option_signal_future_poisoning_cannot_change_past():
    t=toy();r=replace(M.BASE,mechanism='option_led')
    before=M.option_signal(t,r);assert before.any()
    t.q[45:]*=99;t.close[45:]=50000;t.f[45:,3]=1
    assert np.array_equal(before[:45],M.option_signal(t,r)[:45])

def test_option_signal_requires_both_sides_and_independent_future():
    t=toy();r=replace(M.BASE,mechanism='option_led')
    t.q[:,1::2,3]=np.nan
    assert not M.option_signal(t,r).any()
    t=toy();t.f[:,3]=-t.close
    assert not M.option_signal(t,r).any()

def order_tape():
    return SimpleNamespace(day='2025-01-02',n=6,minute=np.arange(780,786),
        close=np.full(6,100.),q=np.tile([11.,12.,8.,10.,1000.],(6,1,1)),
        symbols=['TEST'],features={10:np.ones((6,8))})

def test_patient_does_not_fill_intrabar_touch_and_expires(monkeypatch):
    import mechanism_day as day
    monkeypatch.setattr(day,'directions',lambda *a:np.array([1,0,0,0,0,0]))
    monkeypatch.setattr(day,'choose',lambda *a:(0,1,10.))
    r=day.run_day(order_tape(),replace(M.BASE,mechanism='patient'),details=True)
    assert r['trades']==0 and r['net']==0 and r['unresolved']==0
    assert r['rejected']==3

def test_patient_fill_clock_cash_and_fees(monkeypatch):
    import mechanism_day as day
    monkeypatch.setattr(day,'directions',lambda *a:np.array([1,0,0,0,0,0]))
    monkeypatch.setattr(day,'choose',lambda *a:(0,1,10.))
    t=order_tape();t.q[2,0,0]=9.
    r=day.run_day(t,replace(M.BASE,mechanism='patient',hold=1),details=True)
    p=r['positions'][0]
    assert p['decision_i']==0 and p['entry_i']==2 and p['exit_i']==4
    assert p['entry']==9.05 and p['events'][-1]['reason']=='TIME'
    assert p['reserve']<=1250 and r['spent']<=2500 and r['unresolved']==0
    assert p['net']==round((p['events'][-1]['price']-p['entry'])*M.LOT-p['fees'],2)
