from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import payoff as P

def tape():
    return SimpleNamespace(close=np.array([10010.]),strikes=np.repeat([10050.,10100.,10150.],2),
        kinds=np.tile([1,-1],3),q=np.tile([10.,12.,8.,10.,1000.],(1,6,1)))

def test_shapes_are_terminal_bounded_everywhere():
    t=tape()
    for shape in ('vertical','butterfly'):
        legs=P.contracts(t,0,1,replace(P.BASE,shape=shape))
        for s in np.linspace(9800,10400,1201):
            payoff=sum(w*max(0,s-t.strikes[j]) for j,w in legs)
            assert -.0001<=payoff<=50.0001

def test_missing_or_far_strike_cannot_be_substituted():
    t=tape();t.strikes[4:]=10500
    assert P.contracts(t,0,1,replace(P.BASE,shape='butterfly')) is None
    assert P.contracts(t,0,-1,P.BASE) is None

def test_pack_capacity_respects_double_short_and_costs():
    t=tape();legs=P.contracts(t,0,1,replace(P.BASE,shape='butterfly'))
    q=P.quote(t,0,legs,True,packs=3,close=True)
    assert q['packs']==1 # 200 units available at 20%, 130 for two middle shorts
    assert q['fees']>P.E.ORDER*3
    assert q['value']>0 # crossing all legs cannot earn a stale-price credit
    assert q['gross_long']>0

def test_negative_liquidation_is_charged_not_clipped():
    t=tape();legs=P.contracts(t,0,1,replace(P.BASE,shape='butterfly'))
    q=P.quote(t,0,legs,False,packs=1,close=True)
    assert q['value']<0
