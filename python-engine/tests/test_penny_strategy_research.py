from dataclasses import replace

import pytest

from penny_strategy_research import (DailyGenome, DailyThesisPolicy, accepts,
    candidate_score, daily_features, daily_signals, financial_summary, smart_rollover)
from penny_smart_book import new_book


def test_rollover_preserves_losses_and_pending_exposure():
    state=new_book('2026-10-01',2000,{})
    state['realized']=-25
    assert smart_rollover(state,'2026-10-02')['bankroll']==1975
    state['positions']['X']={'pending':True}
    assert smart_rollover(state,'2026-10-02') is state


def test_drawdown_uses_marks_and_excludes_best_winner():
    trades=[{'status':'CLOSED','net_pnl':10,'costs':1},
            {'status':'CLOSED','net_pnl':-3,'costs':2}]
    result=financial_summary(trades,[('a',2000),('b',1980),('c',2007)],2000)
    assert result['net']==7 and result['ex_best']==-3
    assert result['drawdown']==20 and result['fees']==3


def test_no_hindsight_in_daily_features():
    from datetime import date,timedelta
    rows=[('X',(date(2025,1,1)+timedelta(days=i)).isoformat(),20+i*.01,21+i*.01,19+i*.01,20+i*.01,100000) for i in range(100)]
    before=daily_features(rows[:80])
    changed=rows[:80]+[(t,d,o,h,l,c*2,v) for t,d,o,h,l,c,v in rows[80:]]
    assert {d:v for d,v in daily_features(changed).items() if d<=rows[79][1]}==before


def test_genome_rejects_future_family_and_sizes_own_cash():
    f={'ticker':'X','date':'2025-01-01','close':20,'atr':.5,'rvol':2,'clv':.8,
       'trend':.1,'ret5':-.02,'drop':-.05,'mean20':19,'low':19.5}
    g=DailyGenome('test')
    signal=daily_signals({f['date']:[f]},f['date'],2000,g)[0]
    assert signal.planned_shares*signal.reference_price <= 2000/g.slots
    assert signal.planned_shares*(signal.reference_price-signal.stop) <= 20
    with pytest.raises(ValueError):candidate_score(f,replace(g,family='FUTURE'))


def test_acceptance_needs_positive_exhero_and_no_unresolved():
    baseline={'net':-5,'drawdown':10}
    c={'closed':30,'unresolved':0,'net':10,'ex_best':2,'drawdown':30}
    assert accepts(c,baseline,2000)
    assert not accepts({**c,'unresolved':1},baseline,2000)
    assert not accepts({**c,'ex_best':-1},baseline,2000)


def test_trail_changes_future_stop_without_invented_same_bar_fill():
    from daily_portfolio import DailySignal,OpenPosition
    signal=DailySignal('X','2025-01-01',20,19,23,10,'PULLBACK',context={'atr':.3,'anchor':19})
    p=OpenPosition(signal,'2025-01-02',0,20,10,19)
    policy=DailyThesisPolicy(DailyGenome('test'))
    assert policy.at_close(p,{'close':22},'2025-01-02',0) is None
    assert p.stop==pytest.approx(21.4)


def test_classic_gap_cannot_release_future_cash():
    from penny_strategy_research import CurrentClassicReplay
    r=object.__new__(CurrentClassicReplay)
    class MissingCurrent:
        def bar_at(self,minute):return None,None
        def first_traded_from(self,minute):raise AssertionError('future fill inspected')
    trade={'status':'OPEN'}
    r._exit_via_market(trade,MissingCurrent(),900,'DEADLINE',None)
    assert trade['status']=='UNRESOLVED'
    assert r._admit()=='UNRESOLVED_EXPOSURE_BLOCK'


def test_cash_and_fee_identity_of_shared_daily_book():
    from daily_portfolio import BookConfig,DailySignal,run_daily_book
    bars={'X':{f'2025-01-0{i}':{'open':20,'high':20.1,'low':19.9,'close':20,'volume':10000} for i in range(1,6)}}
    policy=DailyThesisPolicy(DailyGenome('test',hold=1))
    result=run_daily_book(bars,list(bars['X']),end='2025-01-03',
        signals_after_close=lambda d,e:[DailySignal('X',d,20,19,23,20,'PULLBACK',context={'atr':.2,'anchor':19})],
        policy=policy,costs=lambda *a:5,
        config=BookConfig(1000,max_open_positions=1,max_entries_per_day=1))
    closed=[t for t in result['trades'] if t['status']=='CLOSED']
    assert closed
    assert result['equity_curve'][-1][1]==pytest.approx(1000+sum(t['net_pnl'] for t in closed),abs=.001)
    for t in closed: assert t['gross_pnl']-t['costs']==pytest.approx(t['net_pnl'])


def test_carry_close_rolls_equity_before_next_observation(monkeypatch):
    import penny_strategy_research as lab
    from types import SimpleNamespace
    from datetime import datetime,timedelta,timezone
    now=datetime(2026,9,2,9,15,tzinfo=timezone(timedelta(hours=5,minutes=30)))
    day=now.date().isoformat()
    bar=SimpleNamespace(start=now,available_at=now+timedelta(minutes=1),open=10.,high=10.1,
                        low=9.9,close=10.,volume=1000.,executable=True)
    tape=SimpleNamespace(coverage=[{'ticker':'X','trading_date':day,'status':'COMPLETE'}],
                         bars={('X',day):(bar,)})
    daily=SimpleNamespace(invalid={},known_before=lambda *a,**k:[])
    original=lab.new_book;calls=[]
    def fresh(d,b,e):
        state=original(d,b,e)
        if not calls and d==day and b==2000:
            state['day']='2026-09-01';state['positions']={'X':{}}
        return state
    def observe(state,*args,**kwargs):
        calls.append((state['day'],state['bankroll']))
        if len(calls)==1:
            state['positions']={};state['realized']=-5
        state['marked_pnl']=state['realized']
        return state,[]
    monkeypatch.setattr(lab,'new_book',fresh);monkeypatch.setattr(lab,'step_book',observe)
    lab.run_smart(tape,daily,['X'],start=day,end=day)
    assert calls[0]==('2026-09-01',2000)
    assert calls[1]==(day,1995)
