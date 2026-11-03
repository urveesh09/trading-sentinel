"""E03.1 is a separate disabled defensive experiment; stops are triggers."""
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
import json,sqlite3
import expiry_e02 as X
import expiry_paper as EP
from tests.test_expiry_e02 import add,bars,contract,quote,source,stamp

def position(lots=2,variant=X.E031):
    now=stamp()
    p=EP._new_position(now.date().isoformat(),'NIFTY',variant.play,'NFO',contract(),8.,lots,now)
    p.update(stop=round(8*(1-variant.initial_stop),2),direction=1,underlying_stop=9990.,e02_policy=X.policy_for(variant))
    return p

def test_defaults_off_separate_identity_and_no_db_when_disabled(tmp_path):
    from config import Settings
    assert Settings().EXPIRY_E031_SHADOW_ENABLED is False
    base=tmp_path/'app.db'
    assert X.run_tick(base,now=stamp(),variant=X.E031)=={'status':'DISABLED'}
    assert not list(tmp_path.iterdir())
    assert len({X.path_for(base,v) for v in X.VARIANTS})==3
    assert X.E031.version=='expiry-e031-v1' and X.E031.play=='E031'

def test_initial_stop_and_peak_lock_boundaries():
    p=position()
    assert p['stop']==5.2
    assert X.action(p,11.95,10018.,stamp()) is None
    assert p['stop']==7.17
    assert X.action(p,12.,10018.,stamp()) is None
    assert p['stop']==8.8
    assert X.action(p,8.8,10018.,stamp())==(2,'TRAIL')

def test_floor_never_lowers_existing_stop():
    p=position();p['stop']=9.5
    assert X.action(p,12.,10018.,stamp()) is None
    assert p['stop']==9.5

def test_entry_reserve_and_strike_selection_stay_e03():
    reading=X.signal(bars());now=stamp(13,11);book=SimpleNamespace(by_symbol={'X':contract()})
    a=X.plan(reading,{'X':quote(5.5,now)},book,now,1250.,25000.,X.E031)
    b=X.plan(reading,{'X':quote(5.5,now)},book,now,1250.,25000.,X.E03)
    assert a==b and a['lots']==3 and EP.worst_case_loss(a['limit'],a['lots'],65)<=1250

def test_e02_e03_frozen_policy_and_open_position_unchanged():
    for v in (X.E02,X.E03):
        p=position(variant=v)
        assert 'lock_arm' not in p['e02_policy'] and p['stop']==4.8
        X.action(p,12.,10018.,stamp())
        assert p['stop']==7.2
    p=position();frozen=dict(p['e02_policy'])
    newer=replace(X.E031,initial_stop=.1,lock_floor=2.)
    assert X.policy_for(newer)!=frozen and p['e02_policy']==frozen

def test_gap_can_fill_below_trigger_and_lose_money():
    p=position();X.action(p,12.,10018.,stamp())
    assert X.action(p,8.7,10018.,stamp())==(2,'TRAIL')
    q=EP.Quote(((4.,650),),((4.05,650),),4.,stamp())
    EP._try_exit(p,q,2,'TRAIL',stamp())
    assert p['status']=='CLOSED' and p['net_pnl']<0 and p['entry_price']==8.

def test_runner_rule_and_one_lot_target_remain_e03():
    assert X.action(position(1),16.,10018.,stamp())==(1,'TARGET')
    p=position(3);assert X.action(p,16.,10018.,stamp())==(2,'TARGET_BASE')
    X.sell_base(p,EP.Quote(((16.,650),),((16.05,650),),16.,stamp()),2,stamp())
    assert X.action(p,30.,9000.,stamp()+timedelta(minutes=40)) is None
    assert X.action(p,14.,9000.,stamp()+timedelta(minutes=40))==(1,'RUNNER_TRAIL')

def test_pending_fill_and_disabled_restart_keep_frozen_risk_and_exit(tmp_path):
    base=source(tmp_path);now=stamp();add(base,now)
    s=X._new_state(now-timedelta(minutes=10),X.E031)
    s['day']=dict(date=now.date().isoformat(),budget=2500.,spent=0.,trades=0)
    s['pending']=dict(symbol='X',limit=8.8,lots=2,at=now.isoformat(),expires=(now+timedelta(minutes=1)).isoformat(),direction=1,underlying_stop=9990.)
    with sqlite3.connect(X.path_for(base,X.E031)) as db:
        db.execute('CREATE TABLE e02_state(id INTEGER PRIMARY KEY,payload TEXT)')
        db.execute('CREATE TABLE e02_positions(id INTEGER PRIMARY KEY,day TEXT,status TEXT,payload TEXT)')
        db.execute('INSERT INTO e02_state VALUES(1,?)',(json.dumps(s),))
    out=X.run_tick(base,enabled=True,now=now,book=SimpleNamespace(by_symbol={'X':contract()}),variant=X.E031)
    assert out['status']=='OPEN'
    with sqlite3.connect(X.path_for(base,X.E031)) as db:
        s=json.loads(db.execute('SELECT payload FROM e02_state').fetchone()[0]);p=s['position']
        assert p['stop']==5.2 and p['lots']==2 and p['e02_policy']['lock_floor']==1.1
        p['exit_pending']='STOP'
        db.execute('UPDATE e02_state SET payload=?',(json.dumps(s),))
    assert X.held_contracts(base,SimpleNamespace(by_symbol={'X':contract()}))==[contract()]
    later=now+timedelta(seconds=10);add(base,later,price=5.)
    closed=X.run_tick(base,enabled=False,now=later,variant=X.E031)
    assert closed['status']=='OBSERVING' and closed['cash']<25000
    assert closed['day']['trades']==1 and closed['day']['spent']==out['day']['spent']
    assert not (tmp_path/'app.db.expiry-e03.db').exists() and not (tmp_path/'app.db.expiry-e02.db').exists()
