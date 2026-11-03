"""E03.2: E03.1 with put tickets at twice the reserve, an 8% buy limit and every leg sold from 15:14; disabled."""
from datetime import date,time,timedelta
from types import SimpleNamespace
import json,sqlite3
import expiry_e02 as X
import expiry_paper as EP
from tests.test_expiry_e02 import add,bars,contract,quote,source,stamp


def put_contract(strike=9975.):
    return SimpleNamespace(underlying='NIFTY',expiry=date(2026,11,3),lot_size=65,instrument_type='PE',strike=strike,tradingsymbol='P',token=2)


def put_reading():return X.Reading(-1,10000.,5.,791,-.9)


def position(variant,entry_at,lots=2,entry=8.):
    p=EP._new_position(entry_at.date().isoformat(),'NIFTY',variant.play,'NFO',contract(),entry,lots,entry_at)
    p.update(stop=round(entry*(1-variant.initial_stop),2),direction=1,underlying_stop=9990.,e02_version=variant.version,e02_policy=X.policy_for(variant))
    return p


def test_defaults_off_separate_identity_and_older_variants_keep_their_settings(tmp_path):
    from config import Settings
    assert Settings().EXPIRY_E032_SHADOW_ENABLED is True and Settings().EXPIRY_MAIN_STRATEGY=='E032'          # the main expiry ticket since expiry-v5
    base=tmp_path/'app.db'
    assert X.run_tick(base,now=stamp(),variant=X.E032)=={'status':'DISABLED'}
    assert not list(tmp_path.iterdir())
    assert X.E032.version=='expiry-e032-v1' and X.E032.play=='E032' and X.E032 in X.VARIANTS
    assert len({X.path_for(base,v) for v in X.VARIANTS})==len(X.VARIANTS)
    for v in (X.E02,X.E03,X.E031):
        assert (v.put_mult,v.chase,v.flat)==(1.,.10,time(15,28))
        assert X.ticket_scale(v,-1)==X.ticket_scale(v,1)==1. and X.day_scale(v)==1.
        assert 'flat' not in X.policy_for(v)
    assert X.ticket_scale(X.E032,-1)==2. and X.ticket_scale(X.E032,1)==1. and X.day_scale(X.E032)==2.


def test_a_put_ticket_buys_up_to_six_lots_inside_twice_the_reserve():
    now=stamp(13,11);book=SimpleNamespace(by_symbol={'P':put_contract()})
    p=X.plan(put_reading(),{'P':quote(5.5,now)},book,now,2500.,25000.,X.E032)
    assert p['lots']==6 and EP.worst_case_loss(p['limit'],6,65)<=2500
    # E03.1 with the same room still stops at three lots; a call ticket of E03.2 stays E03.1's.
    assert X.plan(put_reading(),{'P':quote(5.5,now)},book,now,2500.,25000.,X.E031)['lots']==3
    call=X.plan(X.signal(bars()),{'X':quote(5.5,now)},SimpleNamespace(by_symbol={'X':contract()}),now,1250.,25000.,X.E032)
    assert call['lots']==3 and EP.worst_case_loss(call['limit'],3,65)<=1250


def test_buy_limit_is_eight_percent_above_the_decision_ask():
    now=stamp(13,11);book=SimpleNamespace(by_symbol={'X':contract()});reading=X.signal(bars())
    assert X.plan(reading,{'X':quote(10.,now)},book,now,1250.,25000.,X.E032)['limit']==10.8
    assert X.plan(reading,{'X':quote(10.,now)},book,now,1250.,25000.,X.E031)['limit']==11.0


def test_policy_frozen_on_the_ticket_sells_from_1514():
    frozen=X.policy_for(X.E032)
    assert frozen['flat']=='15:14' and frozen['stop']==.35 and frozen['lock_floor']==1.1 and frozen['split']
    e032=position(X.E032,stamp(15,12));e031=position(X.E031,stamp(15,12))
    assert X.flat_time(e032)==time(15,14) and X.flat_time(e031)==time(15,28) and X.flat_time({})==time(15,28)
    assert X.action(e032,8.5,10018.,stamp(15,14))==(2,'FLAT_TIME')
    assert X.action(e031,8.5,10018.,stamp(15,14)) is None


def _open_book(base,variant,now,p):
    s=X._new_state(now-timedelta(hours=2),variant)
    s['day']=dict(date=now.date().isoformat(),budget=2500.*X.day_scale(variant),spent=1100.,trades=1);s['position']=p
    with sqlite3.connect(X.path_for(base,variant)) as db:
        db.execute('CREATE TABLE e02_state(id INTEGER PRIMARY KEY,payload TEXT)')
        db.execute('CREATE TABLE e02_positions(id INTEGER PRIMARY KEY,day TEXT,status TEXT,payload TEXT)')
        db.execute('INSERT INTO e02_state VALUES(1,?)',(json.dumps(s),))


def test_an_open_runner_is_sold_from_1514_end_to_end_while_e031_holds(tmp_path):
    base=source(tmp_path);now=stamp(15,14,5);add(base,now,price=9.)
    for variant in (X.E032,X.E031):
        p=position(variant,stamp(14,40));p.update(runner=True,stop=8.)
        _open_book(base,variant,now,p)
        out=X.run_tick(base,enabled=False,now=now,variant=variant)
        with sqlite3.connect(X.path_for(base,variant)) as db:
            saved=json.loads(db.execute('SELECT payload FROM e02_positions').fetchone()[0])
        if variant is X.E032:
            assert out['status']=='OBSERVING' and saved['status']=='CLOSED' and saved['_events'][-1]['action']=='FLAT_TIME'
        else:
            assert out['status']=='OPEN' and saved['status']=='OPEN'


def test_a_new_day_reserves_twice_the_ceiling_for_e032_only(tmp_path):
    base=source(tmp_path);now=stamp(13,5);add(base,now)
    book=SimpleNamespace(by_symbol={'X':contract()})
    assert X.run_tick(base,enabled=True,now=now,book=book,variant=X.E032)['day']['budget']==5000.
    assert X.run_tick(base,enabled=True,now=now,book=book,variant=X.E031)['day']['budget']==2500.
