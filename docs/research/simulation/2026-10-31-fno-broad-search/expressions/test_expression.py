import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import expression_lab as E


def leg(credit,gross,fees):
    return {'status':'AVAILABLE','entry_cashflow':credit,'gross':gross,'fees':fees}


def test_iron_has_eight_order_fees_and_stress_charged_once():
    r=E.combine_credits(leg(500,100,60),leg(400,50,70),50,400)
    assert r['net']==150-130-400 and r['fees']==130 and r['entry_cashflow']==900
    assert r['reserved_own_cash']==2*50*65+400+400
    assert r['planned_risk']==50*65-900+400+400


def test_unknown_or_arbitrage_credit_not_zero_profit():
    assert E.combine_credits({'status':'UNAVAILABLE','reason':'missing'},leg(100,0,60),50,400)['status']=='UNAVAILABLE'
    assert E.combine_credits(leg(2000,100,60),leg(2000,100,60),50,400)['status']=='UNAVAILABLE'


def test_planned_risk_does_not_use_future_profit():
    a=E.combine_credits(leg(500,100,60),leg(400,50,70),50,400)
    b=E.combine_credits(leg(500,-2000,90),leg(400,500,80),50,400)
    assert a['planned_risk']==b['planned_risk'] and a['reserved_own_cash']==b['reserved_own_cash']


def test_expression_list_frozen_and_covers_two_and_four_legs():
    s=E.spec();assert len(s)==9
    assert sum(x['kind']=='SAME_DIRECTION_CREDIT' for x in s)==3
    assert {(x['width'],x['offset']) for x in s if x['kind']=='NEUTRAL_IRON'}=={(w,o) for w in (50,100) for o in (0,50,100)}


def test_exact_parent_key_does_not_allow_changed_economics():
    import json,hashlib
    t={'key':'same','entry_qty':65,'entry_premium':100.,'stop_underlying':24000.}
    evidence={'file_sha256':'fixed','record_sha256':[hashlib.sha256(json.dumps(t,sort_keys=True).encode()).hexdigest()]}
    E.validate_parent([t],'fixed',evidence)
    for field,value in [('entry_qty',999),('entry_premium',101.),('stop_underlying',23900.)]:
        with pytest.raises(AssertionError):E.validate_parent([{**t,field:value}],'fixed',evidence)
    with pytest.raises(AssertionError):E.validate_parent([t],'changed',evidence)
