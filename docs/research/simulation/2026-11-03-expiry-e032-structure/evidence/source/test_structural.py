from dataclasses import replace
from types import SimpleNamespace
import math
import numpy as np
import structural as S

def test_normal_model_symmetry_parity_and_inversion():
    for sd in (1.,10.,100.):
        c=S.normal_option(101,100,sd,1);p=S.normal_option(101,100,sd,-1)
        assert math.isclose(c-p,1,abs_tol=1e-10)
        assert math.isclose(S.implied_sd(c,101,100,1),sd,abs_tol=1e-8)
    assert S.implied_sd(.5,102,100,1) is None
    assert S.normal_option(90,100,0.,1)==0.

def test_expiry_forward_uses_both_pairs_and_missing_stays_missing():
    t=SimpleNamespace(strikes=np.repeat([9950,10000,10050],2),kinds=np.tile([1,-1],3),
        close=np.array([10000.]),q=np.ones((1,6,5))*100)
    t.q[0,:,3]=[75,25,25,25,25,75]
    assert S.expiry_forward(t,0)==10000.
    t.q[0,1,3]=np.nan
    assert S.expiry_forward(t,0) is None

def test_reclaim_uses_prior_range_not_current_and_no_future():
    n=30;x=np.tile([100.,102.,98.,100.],(n,1));f=x.copy()
    x[22]=[98.,101.,97.,100.];f[22]=[98.,101.,97.,100.]
    t=SimpleNamespace(n=n,x=x,f=f,close=x[:,3],minute=np.arange(770,800))
    r=replace(S.BASE,mechanism='reclaim');a=S.reclaim(t,r)
    assert a[22]==1 and a.sum()==1
    t.x[23:]=1;t.f[23:]=1
    assert np.array_equal(a[:23],S.reclaim(t,r)[:23])

def test_reclaim_needs_independent_confirmation():
    n=30;x=np.tile([100.,102.,98.,100.],(n,1));f=x.copy();x[22]=[98.,101.,97.,100.]
    t=SimpleNamespace(n=n,x=x,f=f,close=x[:,3],minute=np.arange(770,800))
    assert not S.reclaim(t,replace(S.BASE,mechanism='reclaim')).any()
