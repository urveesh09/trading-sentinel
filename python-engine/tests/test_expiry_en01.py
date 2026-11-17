"""EN01 (Nov 17 audit): expiry exits are honest.

1. One displayed bid is used once: a latched exit and the 15:14 flat sale never both fill on one snapshot.
2. Every sale gets its owner notice.
3. A leg still open after its session is valued at settlement (assumed, never a fill) and no longer blocks
   the next expiry; the hourly reconcile does it the same evening.
4. From NSE CAS 2.0 (2026-12-07) no paper fill is booked at or after the expiring contracts' 15:30 close and
   the old book's 15:38 flat becomes 15:28. Nothing changes before then.
"""
from datetime import date,datetime,time,timedelta
import json,sqlite3
import expiry_e02 as X
import expiry_paper as EP
from tests.test_expiry_e02 import add,contract,quote,source,stamp,put_state,state


def _book(base,variant,now,position,spent=1100.):
    s=X._new_state(now-timedelta(hours=2),variant)
    s['day']=dict(date=now.date().isoformat(),budget=2500.*X.day_scale(variant),spent=spent,trades=1);s['position']=position
    with sqlite3.connect(X.path_for(base,variant)) as db:
        db.execute('CREATE TABLE IF NOT EXISTS e02_state(id INTEGER PRIMARY KEY,payload TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS e02_positions(id INTEGER PRIMARY KEY,day TEXT,status TEXT,payload TEXT)')
        if position.get('id'):
            db.execute('INSERT INTO e02_positions VALUES(?,?,?,?)',(position['id'],position['day'],position['status'],json.dumps(position)))
        db.execute('INSERT OR REPLACE INTO e02_state VALUES(1,?)',(json.dumps(s),))


def _position(variant,at,lots=2,entry=8.,day=None):
    p=EP._new_position((day or at.date()).isoformat(),'NIFTY',variant.play,'NFO',contract(expiry=day or at.date()),entry,lots,at)
    p.update(id=1,stop=round(entry*(1-variant.initial_stop),2),direction=1,underlying_stop=9990.,e02_version=variant.version,e02_policy=X.policy_for(variant))
    return p


def _saved(base,variant):
    with sqlite3.connect(X.path_for(base,variant)) as db:
        return json.loads(db.execute('SELECT payload FROM e02_positions').fetchone()[0])


def _one_lot_quote(price,now):return dict(b=[[price,65]],a=[[price+.05,65]],ltp=price,ts=now.isoformat())


def test_a_latched_exit_and_the_flat_sale_never_share_one_displayed_bid(tmp_path):
    # Audit reproduction: at 15:14 a pending STOP sold the one displayed lot and FLAT_TIME sold the second lot
    # into the same snapshot. Now the second lot waits for the next snapshot.
    base=source(tmp_path);now=stamp(15,14,5)
    with sqlite3.connect(str(base)+'.expiry-paper.db') as c:
        c.execute('INSERT INTO expiry_paper_ticks VALUES(?,?,?,?,?,?)',(now.date().isoformat(),'NIFTY',now.isoformat(),10018.,10018.,json.dumps(dict(legs={'X':_one_lot_quote(5.,now)}))))
    p=_position(X.E032,stamp(14,40));p['exit_pending']='STOP'
    _book(base,X.E032,now,p)
    out=X.run_tick(base,enabled=False,now=now,variant=X.E032)
    saved=_saved(base,X.E032)
    sold=[e for e in saved['_events'] if e['action']!='BUY']
    assert [(e['action'],e['lots']) for e in sold]==[('STOP',1)] and saved['lots_open']==1 and saved['status']=='OPEN'
    assert [k.rsplit(':',1)[1] for k,_ in out['notices']]==['STOP']
    later=now+timedelta(seconds=10)
    with sqlite3.connect(str(base)+'.expiry-paper.db') as c:
        c.execute('INSERT INTO expiry_paper_ticks VALUES(?,?,?,?,?,?)',(later.date().isoformat(),'NIFTY',later.isoformat(),10018.,10018.,json.dumps(dict(legs={'X':_one_lot_quote(5.,later)}))))
    out=X.run_tick(base,enabled=False,now=later,variant=X.E032)
    assert _saved(base,X.E032)['status']=='CLOSED' and [k.rsplit(':',1)[1] for k,_ in out['notices']]==['STOP']


def test_the_flat_sale_still_fires_when_nothing_else_used_the_snapshot(tmp_path):
    base=source(tmp_path);now=stamp(15,14,5);add(base,now,price=9.)
    p=_position(X.E032,stamp(14,40));p.update(runner=True,stop=8.)
    _book(base,X.E032,now,p)
    out=X.run_tick(base,enabled=False,now=now,variant=X.E032)
    assert _saved(base,X.E032)['status']=='CLOSED' and out['notices'][0][0].endswith(':FLAT_TIME')


def test_a_prior_day_open_leg_is_settled_and_the_new_expiry_trades(tmp_path):
    base=source(tmp_path);now=stamp(13,5);add(base,now)
    old=date(2026,10,27);p=_position(X.E032,datetime(2026,10,27,14,40,tzinfo=EP.IST),lots=2,entry=8.,day=old);p['exit_pending']='FLAT_TIME'
    with sqlite3.connect(str(base)+'.expiry-paper.db') as c:      # our post-auction index sample that day
        c.execute('INSERT INTO expiry_paper_ticks VALUES(?,?,?,?,?,?)',('2026-10-27','NIFTY','2026-10-27T15:37:00+05:30',10030.,10030.,'{}'))
    _book(base,X.E032,datetime(2026,10,27,15,0,tzinfo=EP.IST),p)
    out=X.run_tick(base,enabled=True,now=now,variant=X.E032)
    assert out['status']=='OBSERVING' and out['day']['date']=='2026-11-03' and out['day']['budget']==5000.
    saved=_saved(base,X.E032)
    # Strike 10025 CE, index 10030: intrinsic 5 less 0.15% exercise STT, against the Rs 8 paid, on 130 units.
    assert saved['status']=='SETTLED_ASSUMED' and saved['assumed_pnl']==round((5*(1-EP.EXERCISE_STT_PCT)-8.)*130,2)
    assert out['cash']==round(25000+saved['net_pnl']+saved['assumed_pnl'],2)
    (key,text),=out['notices']
    assert key.endswith(':SETTLED_ASSUMED') and 'could not be sold before the close' in text and 'not a fill' in text
    assert X.day_results(base)=={('2026-10-27','NIFTY'):X.booked(saved)}


def test_without_a_settlement_price_the_leg_is_unresolved_at_its_worst_case(tmp_path):
    base=source(tmp_path);now=stamp(13,5);add(base,now)
    old=date(2026,10,27);p=_position(X.E032,datetime(2026,10,27,14,40,tzinfo=EP.IST),day=old)
    _book(base,X.E032,datetime(2026,10,27,15,0,tzinfo=EP.IST),p)
    out=X.run_tick(base,enabled=True,now=now,variant=X.E032)
    saved=_saved(base,X.E032)
    assert saved['status']=='UNRESOLVED' and saved['assumed_pnl']==-round(8.*130+2*EP.order_fee(EP.fee_schedule('NFO')),2)
    assert out['status']=='OBSERVING' and out['cash']==round(25000+X.booked(saved),2)


def test_the_hourly_reconcile_settles_the_same_evening_and_only_after_the_session(tmp_path):
    base=source(tmp_path);p=_position(X.E032,stamp(14,40))
    _book(base,X.E032,stamp(15,0),p)
    assert X.reconcile(base,X.E032,stamp(15,30))==[]                       # still trading
    (key,text),=X.reconcile(base,X.E032,stamp(15,45))
    assert key.endswith(':UNRESOLVED') and _saved(base,X.E032)['status']=='UNRESOLVED'
    with sqlite3.connect(X.path_for(base,X.E032)) as db:
        s=json.loads(db.execute('SELECT payload FROM e02_state').fetchone()[0])
    assert s['position'] is None and s['cash']==round(25000+X.booked(_saved(base,X.E032)),2)
    assert X.reconcile(base,X.E032,stamp(15,46))==[]                       # once


def test_old_unresolved_test_now_settles_instead_of_blocking(tmp_path):
    # Was test_old_open_position_is_unresolved_and_blocks_new_day: the stuck leg returned UNRESOLVED_PRIOR_DAY
    # on every later tick. The book now values it and carries on.
    b=source(tmp_path);now=stamp();add(b,now)
    prior=now-timedelta(days=7);p=EP._new_position(prior.date().isoformat(),'NIFTY','E02R3','NFO',contract(expiry=prior.date()),8.,1,prior)
    p.update(id=1,direction=1,underlying_stop=9990.)
    s=state(prior);s['position']=p;put_state(b,s,p)
    out=X.run_tick(b,enabled=True,now=now)
    assert out['status']=='OBSERVING' and out['cash']<25000


def test_cas2_no_fill_at_or_after_the_expiring_close_and_flat_capped_at_1528():
    before=datetime(2026,12,3,15,35,tzinfo=EP.IST);after=datetime(2026,12,8,15,30,tzinfo=EP.IST)
    assert EP.can_fill(before) and not EP.can_fill(after) and EP.can_fill(after.replace(minute=29,second=59))
    assert EP.last_flat(before.date(),EP.FINAL_FLAT)==time(15,38) and EP.last_flat(after.date(),EP.FINAL_FLAT)==time(15,28)
    assert EP.last_flat(after.date(),time(15,14))==time(15,14)
    c=contract(expiry=after.date())
    p=EP._new_position(after.date().isoformat(),'NIFTY','C','NFO',c,8.,2,after.replace(minute=0))
    q=EP.Quote(((9.,650),),((9.05,650),),9.,after)
    assert EP._try_exit(p,q,2,'FLAT_TIME',after) is None and p['exit_pending']=='FLAT_TIME' and p['lots_open']==2
    assert EP.manage_position(p,EP.POLICIES['C'],9.,after.replace(minute=28)) is not None      # 15:28: flat now
    assert EP.manage_position(dict(p,exit_pending=None),EP.POLICIES['C'],9.,after.replace(minute=27))!=(2,'FLAT_TIME')


def test_en02_recording_starts_1247_so_e032_has_twelve_bars_by_1300(tmp_path):
    """EN02: the lab's 13:00 decisions need bars from 12:48; with ticks from 12:59 the first was ~13:11."""
    from tests.test_expiry_e02 import bars as rising
    assert EP.TICK_START==time(12,47) and EP.EXPECTED_SLOTS==1038
    base=source(tmp_path);closes=[b['s'][3] for b in rising()]+[10019.]    # twelve bars 12:48-12:59, then 13:00
    s=state(stamp(12,47));s['bars']=[];last=None
    for k,c in enumerate(closes):
        start=stamp(12,48)+timedelta(minutes=k)
        for sec in range(0,60,10):
            done=X._sample(s,dict(ts=(start+timedelta(seconds=sec)).isoformat(),spot=c,fut=c,quotes='{}'))
            last=done or last
    done=X._sample(s,dict(ts=stamp(13,1).isoformat(),spot=10019.,fut=10019.,quotes='{}'))
    assert len(s['bars'])>=12 and s['bars'][-1]['end']==stamp(13,1).isoformat()
    # With the full warm-up the 13:00 window is open from its first minute (outside_window only before 13:00).
    diag={};X.signal(s['bars'][:-1],diag)
    assert 'warmup' not in diag.get('signal',{})
