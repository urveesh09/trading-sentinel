import sys
from datetime import date,timedelta
from pathlib import Path
import sqlite3

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from validate_penny_finalists import edge_cache,edge_signals
from penny_edge_live import scan_today
from edge_overnight_paper import RANK_DEPTH
from daily_portfolio import bars_by_ticker


def test_cached_shipped_scan_has_identical_candidates_and_sizing(tmp_path):
    rows=[];days=[];d=date(2021,1,1);price=20
    while len(days)<85:
        if d.weekday()<5:days.append(d.isoformat())
        d+=timedelta(days=1)
    for i,day in enumerate(days):
        previous=price
        price=price*(1.08 if i>=80 else 1.001)
        rows.append(('RELIANCE',day,previous,price*1.01,previous*.99,price,500000 if i>=80 else 100000))
        rows.append(('NIFTYBEES',day,200,202,198,200+i*.1,1000000))
    path=tmp_path/'daily.sqlite'
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE ohlcv_cache(ticker,date,open,high,low,close,volume)')
        c.executemany('INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?)',rows)
    cache,regimes=edge_cache(rows,days[80],days[-1]);bars=bars_by_ticker(rows);seen=0
    for day in days[80:]:
        original=scan_today(bankroll=100000,max_positions=RANK_DEPTH,min_strength=.45,db_path=str(path),as_of_date=day,nifty_ticker='NIFTYBEES')['positions']
        actual=edge_signals(cache,regimes,bars,day,100000)
        expected=[(p.ticker,p.entry_price,p.stop_loss,p.target,p.shares,p.signal_subtype) for p in original]
        assert [(p.ticker,p.reference_price,p.stop,p.target,p.planned_shares,p.kind) for p in actual]==expected
        seen+=len(actual)
    assert seen>0
    from validate_penny_finalists import cached_edge
    from iterate_penny_strategy_search import NightGenome,night_features,run_night
    control=NightGenome('CONTROL',use_shipped_candidates=True,strength_weight=1.,min_edge=-1.)
    actual=run_night(rows,night_features(rows),control,start=days[80],end=days[-2],
                     shipped=(cache,regimes))
    baseline=cached_edge(rows,cache,regimes,start=days[80],end=days[-2],bankroll=100000,
                         entry_slip=25,exit_slip=10)
    assert actual['metrics']==baseline['metrics']
    assert actual['equity_curve']==baseline['equity_curve']
