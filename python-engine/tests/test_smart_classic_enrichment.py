from copy import deepcopy
from types import SimpleNamespace

import pytest
from smart_classic_enrichment import (Order,Policy,auction_orders,bar5,intraday_orders,
                                      run_book,snapshots,wilder_rsi)
from penny_engine_connors import _rsi_2


def daily_rows(tickers=('A','B','C','D'),n=30):
    from datetime import date,timedelta
    dates=[(date(2026,1,1)+timedelta(days=i)).isoformat() for i in range(n)]
    return {t:[(d,20.,21.,19.,20.,1000000.) for d in dates] for t in tickers}


def test_wilder_uses_history_and_matches_hand_calculation():
    x=[10.,11.,10.,11.,10.]
    assert wilder_rsi(x)[2:]==pytest.approx([50,75,37.5])
    assert _rsi_2(x)==50
    assert wilder_rsi(x+[200.])[:len(x)]==wilder_rsi(x)


def test_snapshots_ignore_today_and_future_bars():
    rows=daily_rows();day=rows['A'][25][0];before=snapshots(rows,[day])
    changed=deepcopy(rows)
    for t in changed:
        changed[t][25]=(day,999.,1000.,998.,999.,10.)
    assert snapshots(changed,[day])==before


def test_preselected_limit_not_final_price_determines_quantity():
    d='2026-02-02';orders=[]
    for i,t in enumerate('ABCD'):
        orders.append(Order(d,550,t,18.,1,(i,),9999,9999,(d,970,20.,'proxy'),{'slot_fraction':.25},19.6))
    rows={t:[(d,18.,21.,17.,20.,100000.)] for t in 'ABCD'}
    a=run_book(orders,rows,[d],entry_bps=0,exit_bps=0,max_new_day=4)
    changed=deepcopy(orders)
    for o in changed:o.entry=17.
    b=run_book(changed,rows,[d],entry_bps=0,exit_bps=0,max_new_day=4)
    assert [x['qty'] for x in a['intents']]==[x['qty'] for x in b['intents']]
    assert sum(x['reserved'] for x in a['intents'])<=2000


def test_locked_carry_reserves_cash_until_actual_future_exit():
    days=['2026-02-02','2026-02-03','2026-02-04']
    first=Order(days[0],550,'A',20.,1,(0,),9999,9999,(days[2],555,19.,'carry'),{'slot_fraction':1.})
    second=Order(days[1],550,'B',20.,1,(0,),9999,9999,(days[1],970,30.,'not_funded'),{'slot_fraction':1.})
    rows={t:[(d,20.,21.,19.,20.,100000.) for d in days] for t in ['A','B']}
    r=run_book([first,second],rows,days,entry_bps=0,exit_bps=0)
    # Residual dust cannot open another full risk ticket.
    assert [t['ticker'] for t in r['trades']]==['A']
    assert r['trades'][0]['exit_day']==days[2] and r['open']==0


def test_missing_exit_remains_open_without_fabricated_haircut():
    d='2026-02-02';o=Order(d,550,'A',20.,1,(0,),9999,9999,None,{'slot_fraction':1.})
    r=run_book([o],{'A':[(d,20.,21.,19.,19.,100000.)]},[d],entry_bps=0,exit_bps=0)
    assert r['summary']['net']==0 and r['open']==1 and not r['trades']


def test_short_fees_and_cash_identity_are_direction_correct():
    d='2026-02-02';o=Order(d,650,'A',20.,-1,(0,),9999,9999,(d,900,19.,'cover'),{'slot_fraction':1.})
    r=run_book([o],{'A':[(d,20.,21.,19.,19.,100000.)]},[d],entry_bps=25,exit_bps=25)
    t=r['trades'][0]
    assert t['entry']<20 and t['exit']>19
    assert t['net']==pytest.approx((t['entry']-t['exit'])*t['qty']-t['fees'])
    assert r['cash']==pytest.approx(2000+t['net'])


def test_postopen_confirmation_enters_next_completed_bar():
    d=SimpleNamespace(ticker='A',date='2026-02-02',prev_close=20.,median_value20=1000000.,
        median_vol20=100000.,day_open=19.,bars=[(555,19.,19.4,18.9,19.3,10000.),
        (560,19.3,19.5,19.2,19.4,10000.),(585,19.4,19.6,19.3,19.5,10000.)])
    os,_=intraday_orders([d],Policy('confirm','confirm',exit_minute=585))
    assert os[0].minute==560 and os[0].entry==19.3
    assert os[0].cap_known==100 and os[0].cap_actual==100


def test_missing_today_does_not_change_preselected_auction_pool():
    rows=daily_rows();day=rows['A'][-1][0]
    _,counts=auction_orders([],rows,[day],Policy('basket','basket',slots=4),2000)
    assert counts['PRESELECTED_LIMIT']==4 and counts['MISSING_AUCTION_OUTCOME']==4
