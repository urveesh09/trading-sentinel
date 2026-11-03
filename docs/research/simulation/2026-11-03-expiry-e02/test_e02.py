from dataclasses import replace
from datetime import datetime,timedelta
import random
import numpy as np
import pytest
import data as D
import e02_lab as E


def toy(n=100):
    close=10000+np.arange(n)*.4
    x=np.column_stack([close-.1,close+.1,close-.15,close])
    q=np.empty((n,2,5));q[:]=[10.,10.2,9.8,10.,100000.]
    now=[datetime(2025,1,2,13,0,tzinfo=D.EP.IST)+timedelta(minutes=i+1) for i in range(n)]
    return D.Tape('2025-01-02',x,x.copy(),q,np.array([10100.,9900.]),np.array([1,-1]),['CE','PE'],now,np.arange(781,781+n),0)


def test_money_formula_matches_native_schedule():
    rng=random.Random(1)
    for _ in range(1000):
        price=rng.uniform(.05,250);lots=rng.randint(1,10)
        assert E.fee(price,lots*65,True)==round(D.EP.buy_charges(price,lots*65,E.FEE),2)
        assert E.fee(price,lots*65,False)==round(D.EP.sell_charges(price,lots*65,E.FEE),2)
        assert abs(E.reserve(price,lots)-D.EP.worst_case_loss(price,lots,65,E.FEE))<.006


def test_2024_requires_committed_final_exam():
    with pytest.raises(AssertionError,match='Reserved'):D.load_year(2024)


@pytest.mark.parametrize('setup',['BOX','BREAK','RETEST','PULLBACK','FADE'])
def test_truncating_future_cannot_change_signal(setup):
    t=toy();short=toy(55);rule=E.Rule(setup=setup,look=5,efficiency=0.,stretch=20.)
    assert np.array_equal(E.directions(t,rule)[:55],E.directions(short,rule))
    t.x[60:,3]+=1000
    assert np.array_equal(E.directions(t,rule)[:55],E.directions(short,rule))


def test_entry_plan_is_based_on_observed_quote_not_future_range():
    t=toy();r=E.Rule(look=5,stretch=20.)
    plan=E.choose(t,10,1,r,2500,25000)
    t.q[11,0,1]=1000
    assert E.choose(t,10,1,r,2500,25000)==plan


def test_limit_and_dust_prevent_oversized_or_illusory_fill():
    t=toy();r=E.Rule(look=5,stretch=20.,hold=8)
    t.q[:,:,0]=1000
    out=E.run_day(t,r)
    assert out['trades']==0 and out['rejected']>0
    t=toy();t.q[:,:,4]=0
    assert E.run_day(t,r)['trades']==0


def test_daily_reserve_is_never_recycled_after_a_trade():
    t=toy();r=E.Rule(look=5,stretch=20.,hold=8,slots=2)
    out=E.run_day(t,r,details=True)
    assert out['trades']==2 and out['spent']<=2500
    assert abs(out['spent']-sum(p['reserve'] for p in out['positions']))<.03
    assert all(p['reserve']<=1250 for p in out['positions'])


def test_next_bar_orders_and_raw_cash_identity():
    out=E.run_day(toy(),E.Rule(look=5,stretch=20.,hold=8),details=True)
    assert out['trades']
    for p in out['positions']:
        cash=0
        for e in p['events']:
            assert e['i']>e['decision_i']
            cash+=(1 if e['side']=='SELL' else -1)*e['price']*e['lots']*65-e['fees']
        assert abs(round(cash,2)-p['net'])<.03


def test_stop_does_not_fill_at_a_better_price_than_next_bar_open():
    t=toy();t.q[12:,0,:4]=1.
    out=E.run_day(t,E.Rule(look=5,stretch=20.,hold=60),details=True)
    p=out['positions'][0]
    assert p['events'][-1]['reason']=='STOP'
    assert p['events'][-1]['price']<1.
    assert p['net']>=-p['reserve']-.02


def test_missing_exit_volume_stays_pending_until_executable():
    t=toy();t.q[12:,0,:4]=1.;t.q[13,0,4]=0
    out=E.run_day(t,E.Rule(look=5,stretch=20.,hold=60),details=True)
    events=out['positions'][0]['events']
    assert events[-1]['i']==14 and events[-1]['decision_i']==12


def test_book_brake_cannot_create_negative_cash():
    tapes=[toy() for _ in range(53)]
    for i,t in enumerate(tapes):t.day=f'2025-{i//5+1:02d}-{i%5+1:02d}'
    result=E.run_year(tapes,E.Rule(look=5,stretch=20.,hold=8))
    assert all(d['cash_after']>=0 for d in result['days'])
    assert any(d['scale']<1 for d in result['days'])


def test_native_controller_and_cashflow_match_the_fast_replay():
    from audit import native_audit
    t=toy();t.q[20:,0,:4]=25.
    r=E.Rule(look=5,stretch=20.,hold=15)
    for scenario in ('ordinary','adverse','catastrophe'):
        row=E.run_day(t,r,scenario,details=True)
        assert native_audit(t,r,row,scenario)==row['trades']


def test_reach_gate_uses_current_atr_and_time_remaining_only():
    t=toy();r=E.Rule(look=5,stretch=20.,reach=.1)
    assert E.choose(t,10,1,r,2500,25000) is None
    t.q[11:,:,1]*=100
    assert E.choose(t,10,1,r,2500,25000) is None
    assert E.choose(t,10,1,replace(r,reach=0.),2500,25000) is not None


def test_lot_size_sensitivity_changes_actual_reserve_and_quantity_consistently():
    original=E.LOT
    try:
        E.LOT=25
        assert E.reserve(10.,2)==10*50+E.fee(10.,50,True)+2*E.ORDER
        out=E.run_day(toy(),E.Rule(look=5,stretch=20.,hold=8),details=True)
        for p in out['positions']:
            assert abs(p['reserve']-D.EP.worst_case_loss(p['entry'],p['lots'],25,E.FEE))<.01
    finally:E.LOT=original


def test_flat_days_do_not_hide_a_losing_streak():
    rows=[dict(day=f'2025-01-{i+1:02d}',net=v,trades=int(v!=0),fees=0,unresolved=0) for i,v in enumerate([-1,0,-1,0,-1,2])]
    assert E.summary(rows)['losing_streak']==3
