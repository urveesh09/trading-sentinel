import pytest
import ledger_lab as K

def test_net_ledger_uses_only_realized_cash_and_full_loss_reserve():
    r=K.ARMS['NET_RISK_LEDGER']
    assert K.room_for(r,[],0,2500,25000)==1250
    p=[{'net':-1500.}]
    assert K.room_for(r,p,2400,2500,23500)==1000
    K.check_admission(r,p,2500,1000)
    with pytest.raises(AssertionError):K.check_admission(r,p,2500,1001)

def test_profit_reentry_cannot_risk_day_opening_principal():
    r=K.ARMS['PROFIT_REENTRY'];p=[{'net':800.},{'net':-300.}]
    assert K.room_for(r,p,2000,2500,25500)==500
    K.check_admission(r,p,2500,500)
    with pytest.raises(AssertionError):K.check_admission(r,p,2500,501)
    assert K.room_for(r,[{'net':-100.},{'net':50.}],2000,2500,24950)==0

def test_original_first_two_keep_original_gross_budget():
    r=K.ARMS['PROFIT_REENTRY']
    assert K.room_for(r,[{'net':1000.}],1100,1250,26000)==150

def test_braked_loss_allowance_and_own_cash_always_bind():
    r=K.ARMS['NET_RISK_LEDGER']
    assert K.room_for(r,[{'net':-200.}],1100,625,24800)==425
    assert K.room_for(r,[{'net':2000.}],1100,2500,300)==300
