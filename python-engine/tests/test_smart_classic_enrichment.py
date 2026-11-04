from copy import deepcopy
from types import SimpleNamespace

import pytest
from smart_classic_enrichment import (Order,Policy,auction_orders,bar5,intraday_orders,
                                      run_book,snapshots,wilder_rsi,cnc_orders)
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
    a=run_book(orders,rows,[d],entry_bps=0,exit_bps=0,max_new_day=4,max_positions=4)
    changed=deepcopy(orders)
    for o in changed:o.entry=17.
    b=run_book(changed,rows,[d],entry_bps=0,exit_bps=0,max_new_day=4,max_positions=4)
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


def test_partial_carry_reserves_position_slot_even_with_spare_cash():
    dates=['2026-02-02','2026-02-03','2026-02-04']
    a=Order(dates[0],550,'A',20.,1,(0,),25,25,(dates[2],555,21.,'carry'),{'slot_fraction':1.})
    b=Order(dates[1],550,'B',20.,1,(0,),9999,9999,(dates[1],970,30.,'unfunded'),{'slot_fraction':1.})
    rows={t:[(d,20.,21.,19.,20.,100000.) for d in dates] for t in 'AB'}
    r=run_book([a,b],rows,dates,entry_bps=0,exit_bps=0)
    assert [t['ticker'] for t in r['trades']]==['A']
    assert r['outcomes']['POSITIONS_RESERVED_BY_CARRY']==1


def test_short_fees_and_cash_identity_are_direction_correct():
    d='2026-02-02';o=Order(d,650,'A',20.,-1,(0,),9999,9999,(d,900,19.,'cover'),{'slot_fraction':1.})
    r=run_book([o],{'A':[(d,20.,21.,19.,19.,100000.)]},[d],entry_bps=25,exit_bps=25)
    t=r['trades'][0]
    assert t['entry']<20 and t['exit']>19
    assert t['net']==pytest.approx((t['entry']-t['exit'])*t['qty']-t['fees'])
    assert r['cash']==pytest.approx(2000+t['net'])


def test_no_winner_does_not_remove_a_loss_from_ex_best_winner_metric():
    d='2026-02-02';o=Order(d,550,'A',20.,1,(0,),9999,9999,(d,900,19.,'loss'),{'slot_fraction':1.})
    r=run_book([o],{'A':[(d,20.,21.,19.,19.,100000.)]},[d],entry_bps=0,exit_bps=0)
    assert r['summary']['ex_best']==r['summary']['net']


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


def test_native_reference_thinness_uses_clearing_price_not_preauction_limit():
    rows=daily_rows(tickers=('A','B'));day=rows['A'][-1][0]
    rows['A']=[(*r[:5],50000.) for r in rows['A']]
    ds=[SimpleNamespace(ticker=t,date=day,day_open=price,day_close=price+.2,day_low=price-.2,
        bars=[(555,price,price+.3,price-.2,price+.2,100000.)]) for t,price in [('A',10.),('B',19.)]]
    orders,_=auction_orders(ds,rows,[day],Policy('reference','auction_ref',exit_minute=970),2000)
    assert orders[0].ticker=='B' # A needs50 shares of normal capacity; only40 available
    assert orders[0].cap_known>1000000 # history is an admission gate, not realised capacity


def test_cnc_pending_deadline_can_wait_beyond_seven_bars_without_fake_exit():
    from datetime import date,timedelta
    rows=[]
    for i in range(272):
        day=(date(2025,1,1)+timedelta(days=i)).isoformat();c=10+.04*i
        if 256<=i<260:c=20.-.2*(i-256)
        if 260<=i<270:
            c=19.2-.4*(i-260);rows.append((day,c,c,c,c,1000000.));continue
        if i>=270:rows.append((day,16.,16.5,15.9,16.3,1000000.));continue
        rows.append((day,c,c+.1,c-.1,c,1000000.))
    orders,_=cnc_orders({'A':rows},[rows[260][0]],Policy('cnc','cnc_wilder'))
    assert orders and orders[0].outcome[:2]==(rows[270][0],555)
    assert orders[0].outcome[3]=='PENDING_CNC_SALE_FIRST_TRADABLE_OPEN'


def test_night_cost_gate_uses_known_quantity_and_rejects_fee_negative_ticket():
    d='2026-02-02';o=Order(d,970,'A',20.,1,(0,),9999,9999,('2026-02-03',555,21.,'night'),
        {'slot_fraction':1.,'night_cost_gate':True,'night_mean':.001})
    daily={'A':[(d,20,21,19,20,100000),('2026-02-03',21,22,20,21,100000)]}
    r=run_book([o],daily,list(x[0] for x in daily['A']),entry_bps=0,exit_bps=0)
    assert not r['intents'] and r['outcomes']['NIGHT_ESTIMATE_BELOW_FEES']==1
