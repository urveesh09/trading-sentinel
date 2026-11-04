from copy import deepcopy
from datetime import date,timedelta

import pytest

from overnight_enrichment import Policy,choose,legacy_lab,pair_risk,risk_history,route_fraction,simulate


def tape(n=70):
    lab=legacy_lab();days=[];d=date(2023,1,2)
    for i in range(n):
        while d.weekday()>4:d+=timedelta(days=1)
        close=20+i*.03
        bar={t:{'open':close+.15,'high':close+.3,'low':close-.3,'close':close,'volume':1000000.} for t in ['AAA','BBB','CCC']}
        cands=[lab.Cand(t,'MO_strong','MO',.8,.8,close,close-.5,close+1,{'night_mean':.005}) for t in bar]
        days.append(lab.Day(d.isoformat(),(0.,.5,'BOTH'),cands,bar,{t:close-.03 for t in bar},{}));d+=timedelta(days=1)
    return days


def test_v2_control_reproduces_legacy_full_fill(monkeypatch):
    lab=legacy_lab();days=tape()
    monkeypatch.setitem(lab.SELECTORS,'enrichment_test',lambda d,cs,p:[c for c in cs if c.f['night_mean']>=.001])
    a=lab.Arm('control',slots=2,entry_bps=0,exit_bps=5,sizing='equal',select='enrichment_test',compound=False)
    old=lab.run_book(days,a,start=days[0].date,end=days[-2].date)
    new=simulate(days,Policy('control',screen_before_depth=True),start=days[0].date,end=days[-2].date)
    assert old['summary']=={k:new['summary'][k] for k in old['summary']}
    assert len(old['curve'])==len(new['curve'])
    for (_,x),(_,y) in zip(old['curve'],new['curve']):assert x==pytest.approx(y,abs=1e-7)
    assert [t['shares'] for t in old['trades']]==[t['shares'] for t in new['trades']]


def test_nonfills_release_reserved_cash_and_charge_no_dp():
    days=tape(4)
    r=simulate(days,Policy('nonfill'),start=days[0].date,end=days[-2].date,winning_close_fill=0.)
    assert r['trades']==[] and r['summary']['final']==25000
    assert r['open_at_end']==0 and r['outcomes']['POSTCLOSE_WINNER_NONFILL']==6


def test_hybrid_keeps_regular_sleeve_if_winning_postclose_orders_fail():
    days=tape(4)
    r=simulate(days,Policy('mixed',regular_fraction=.5),start=days[0].date,end=days[-2].date,winning_close_fill=0.)
    assert r['trades'] and all(t['regular_qty']>0 and t['postclose_qty']==0 for t in r['trades'])
    for t in r['trades']:
        assert (t['exit']-t['entry'])*t['shares']-t['cost']==pytest.approx(t['net'],abs=1e-7)


def test_fixed_risk_capital_never_reinvests_accumulated_profits():
    days=tape();r=simulate(days,Policy('fixed'),start=days[0].date,end=days[-2].date)
    by_day={}
    for i in r['intents']:by_day[i['date']]=by_day.get(i['date'],0)+i['reserved']
    assert r['summary']['net']>0 and max(by_day.values())<=25000


def test_selection_and_risk_have_no_next_session_leak():
    days=tape();before=risk_history(days[:45]);changed=deepcopy(days)
    for d in changed:
        d.nxt={'AAA':{'open':999999}}
    for d in changed[45:]:
        for b in d.bar.values():b['open']*=3
    after=risk_history(changed)
    assert all(before[d]==after[d] for d in before)
    p=Policy('risk',portfolio='downside',inverse_risk_weights=True)
    assert [c.ticker for c in choose(days[44],p,before[days[44].date])[0]]==[c.ticker for c in choose(changed[44],p,after[days[44].date])[0]]


def test_pair_weights_capped_and_missing_history_is_not_zero_risk():
    p=Policy('risk',portfolio='downside',inverse_risk_weights=True)
    assert pair_risk('A','B',{},p) is None
    h={'A':tuple((str(i),-.001) for i in range(30)),'B':tuple((str(i),-.2) for i in range(30))}
    score,w=pair_risk('A','B',h,p)
    assert score>0 and .35<=w<=.65


def test_native_depth_is_taken_before_night_screen():
    days=tape(2);d=days[0]
    lab=legacy_lab();d.cands=[lab.Cand(str(i),'MO_strong','MO',.8,.8,20,19,22,{'night_mean':-.01 if i<10 else .01}) for i in range(12)]
    for c in d.cands:d.bar[c.ticker]={'open':20,'high':21,'low':19,'close':20,'volume':100000};d.prev_close[c.ticker]=20
    assert not choose(d,Policy('native'),{})[0]
    assert len(choose(d,Policy('legacy',screen_before_depth=True),{})[0])==2


def test_anchored_pair_preserves_first_pick_and_requires_material_improvement():
    d=tape(2)[0]
    h={t:tuple((str(i),v) for i in range(30)) for t,v in [('AAA',-.02),('BBB',-.02),('CCC',-.001)]}
    p=Policy('anchor',portfolio='downside',anchor_first=True)
    cs,_,status=choose(d,p,h)
    assert [c.ticker for c in cs[:2]]==['AAA','CCC']
    assert status=='DOWNSIDE_PAIR'
    cs,_,status=choose(d,Policy('strict',portfolio='downside',anchor_first=True,min_risk_improvement=.99),h)
    assert [c.ticker for c in cs[:2]]==['AAA','BBB'] and status=='ANCHOR_RETAINED_PAIR'


def test_cost_hurdle_routes_only_positive_estimated_net_without_future_return():
    c=tape(2)[0].cands[0];p=Policy('route',regular_fraction=.5,route_rule='positive_net')
    c.f['night_mean']=.001
    assert route_fraction(c,p,25000,36,5)==0
    c.f['night_mean']=.03
    assert route_fraction(c,p,25000,36,5)==.5
    assert route_fraction(c,p,25000,400,5)==0
