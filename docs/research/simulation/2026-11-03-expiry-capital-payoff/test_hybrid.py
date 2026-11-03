from types import SimpleNamespace
import numpy as np
import hybrid_lab as H
import credit_lab as C

def test_single_direction_is_not_day_best_future_selection():
    x=H.single_dirs(30,7,-1)
    assert list(np.flatnonzero(x))==[7] and x[7]==-1

def test_credit_plan_must_fit_cash_and_reserved_risk(monkeypatch):
    monkeypatch.setattr(C,'contracts',lambda *a:(0,1))
    monkeypatch.setattr(C,'entry',lambda *a,**k:dict(credit=20.,fees=50.))
    rule=C.ARMS['CREDIT_8M']
    assert H.credit_plan(None,0,1,rule,5000,25000)
    assert not H.credit_plan(None,0,1,rule,1000,25000)
    assert not H.credit_plan(None,0,1,rule,5000,3000)

def test_no_negative_or_unpriced_credit_can_replace_original(monkeypatch):
    monkeypatch.setattr(C,'contracts',lambda *a:(0,1))
    monkeypatch.setattr(C,'entry',lambda *a,**k:dict(credit=-.1,fees=50.))
    assert not H.credit_plan(None,0,1,C.ARMS['CREDIT_8M'],5000,25000)
