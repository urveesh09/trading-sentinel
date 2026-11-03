from dataclasses import replace
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import precursor as P

def toy():
    n=70;s=np.linspace(10000,10030,n);q=np.ones((n,2,5))*10
    q[:,:,4]=1000;q[:,0,3]=np.linspace(6,10,n);q[:,1,3]=np.linspace(10,6,n)
    f=np.zeros((n,4));f[:,3]=s+20
    return SimpleNamespace(n=n,close=s,f=f,q=q,strikes=np.array([10050,10050]),kinds=np.array([1,-1]),
        features={10:np.ones((n,8))*2},minute=np.arange(760,830),oi=np.ones((n,2))*10000)

def test_features_never_depend_on_future_bars_or_future_oi():
    t=toy();a=P.feature(t,40,0,1)
    t.close[41:]=1;t.f[41:]=99999;t.q[41:]=1e7;t.oi[41:]=0
    assert np.allclose(a,P.feature(t,40,0,1),equal_nan=True)

def test_feature_missing_inputs_are_not_invented_open_interest():
    t=toy();t.oi[:]=np.nan
    x=P.feature(t,40,0,1)
    assert np.isnan(x[P.NAMES.index('oi_fraction5')])

def test_fit_uses_only_supplied_training_rows_and_day_weight():
    x=np.array([[1.,np.nan],[2.,3.],[3.,4.],[4.,5.]])
    y=np.array([0,0,1,1]);days=np.array(['a','a','a','b'])
    m=P.fit(x,y,days);assert m['training_day_weight']==2.
    held=np.array([[999.,np.nan]])
    first=P.predict(m,held);held[:]=-999
    assert m==P.fit(x,y,days) and np.isfinite(first).all()
    assert m['impute'][1]==4.

def test_no_entry_label_is_not_a_removed_success(monkeypatch):
    t=toy();monkeypatch.setattr(P.E,'executable',lambda *a:(0,None))
    r=P.label(t,40,0,1,11.,5)
    assert r['hit']==0 and r['status']=='NO_ENTRY' and r['net']==0

def test_target_needs_future_executable_sale_not_high(monkeypatch):
    t=toy();t.q[:,:,1]=9999.;t.q[:,:,3]=10.
    t.q[42,0,3]=60. # target trigger; next open is worse, still recorded at actual fill
    def execute(t,i,j,side,scenario,lots):return 1,10. if side=='BUY' else 40.
    monkeypatch.setattr(P.E,'executable',execute)
    r=P.label(t,40,0,1,11.,5)
    assert r['hit']==1 and r['exit_i']==43 and r['net']<40.*65

def test_activation_compares_only_current_directions_not_future_best():
    rows=[dict(day='d',i=1,j=0,direction=1,fees2=.1),dict(day='d',i=1,j=1,direction=-1,fees2=.1),dict(day='d',i=2,j=2,direction=1,fees2=.1)]
    P.activate(rows,np.array([.6,.5,.99]),2)
    assert P.ACTIVE['d'][1][0]==0 and P.ACTIVE['d'][2][0]==2
