from types import SimpleNamespace
import numpy as np
import credit_lab as C

def tape():
    return SimpleNamespace(close=np.array([10010.]),strikes=np.repeat([9900.,9950.,10000.,10050.,10100.],2),
        kinds=np.tile([1,-1],5),q=np.tile([10.,12.,8.,10.,1000.],(1,10,1)))

def test_signal_sells_only_protected_opposite_side_and_causal_range():
    t=tape();up=C.contracts(t,0,1,C.ARMS['CREDIT_8M']);down=C.contracts(t,0,-1,C.ARMS['CREDIT_8M'])
    assert list(t.strikes[list(up)])==[10000.,9950.] and (t.kinds[list(up)]==-1).all()
    assert list(t.strikes[list(down)])==[10050.,10100.] and (t.kinds[list(down)]==1).all()
    for legs,kind in ((up,-1),(down,1)):
        for spot in np.linspace(9700,10300,301):
            liability=max(0,kind*(spot-t.strikes[legs[0]]))-max(0,kind*(spot-t.strikes[legs[1]]))
            assert -.001<=liability<=50.001

def position():
    return dict(credit=20.,entry_fees=50.,hedge_entry=10.,reserve=2515.,width=50.)

def test_missing_hedge_is_long_asset_writeoff_not_fake_fill():
    p=position();q=dict(short=5.,hedge=None,cost=5.,fees=25.)
    assert C.close_position(p,q,3,2,'TAKE_HALF_CREDIT')
    assert p['exit_hedge'] is None and p['residual_long']==1 and p['unresolved_short']==0
    assert p['assumed']==-650 and p['filled_fee']+p['assumed']==p['net']
    assert p['net']==(20.-5.)*65-50-25

def test_unsafe_close_is_not_clipped_to_width_or_filled():
    p=position();q=dict(short=80.,hedge=10.,cost=70.,fees=60.)
    assert not C.close_position(p,q,3,2,'STOP') and 'net' not in p

def test_zero_bid_is_unfillable_never_clamped():
    t=tape();t.q[0,0,:4]=.05
    assert C.leg_price(t,0,0,False,'ordinary',mark=True) is None

def test_missing_short_cannot_be_abandoned_as_paid_long():
    t=tape();t.q[0,0]=np.nan
    assert C.close_quote(t,0,(0,2),'ordinary') is None
