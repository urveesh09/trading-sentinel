import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))

from iterate_penny_strategy_search import NightGenome,night_features,night_signals


def test_night_features_do_not_read_next_open():
    from datetime import date,timedelta
    rows=[]
    for i in range(120):
        d=(date(2020,1,1)+timedelta(days=i)).isoformat()
        close=20+i*.01
        rows.append(('X',d,close-.01,close+.1,close-.1,close,100000))
    before=night_features(rows[:90])
    mutated=rows[:90]+[(t,d,o*2,h*2,l*2,c*2,v) for t,d,o,h,l,c,v in rows[90:]]
    assert {d:v for d,v in night_features(mutated).items() if d<=rows[89][1]}==before


def test_night_cash_size_does_not_claim_stop_guarantee():
    f={'ticker':'X','date':'2020-01-01','close':20,'nights':[.01]*60,
       'days':[-.002]*60,'momentum':.1}
    g=NightGenome('test')
    signal=night_signals({f['date']:[f]},f['date'],2000,g)[0]
    assert signal.planned_shares*signal.reference_price <= 2000/3
    assert signal.target is None
