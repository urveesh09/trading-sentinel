"""E02 is an isolated disabled research shadow; no broker execution path."""
from datetime import date,datetime,timedelta
from types import SimpleNamespace
import json,sqlite3
import pytest
import expiry_e02 as X
import expiry_paper as EP


def stamp(h=13,m=15,s=0):return datetime(2026,11,3,h,m,s,tzinfo=EP.IST)


def bars():
    # Efficient rise, then a small two-bar pullback and a turn back up.
    closes=[10000+i*2 for i in range(9)]+[10015.,10014.,10018.]
    return [dict(end=(stamp(13,0)+timedelta(minutes=i)).isoformat(),s=[c-1,c+1,c-1,c],f=[c-1,c+1,c-1,c]) for i,c in enumerate(closes)]


def quote(price,now,qty=650):
    return dict(b=[[price-.05,qty]],a=[[price,qty]],ltp=price,ts=now.isoformat())


def contract(expiry=date(2026,11,3),lot=65):
    return SimpleNamespace(underlying='NIFTY',expiry=expiry,lot_size=lot,instrument_type='CE',strike=10025.,tradingsymbol='X',token=1)


def source(tmp_path):
    base=tmp_path/'app.db'
    c=sqlite3.connect(str(base)+'.expiry-paper.db')
    c.execute('CREATE TABLE expiry_paper_ticks(day TEXT,underlying TEXT,ts TEXT,spot REAL,fut REAL,quotes TEXT,PRIMARY KEY(day,underlying,ts))')
    c.commit();c.close();return base


def add(base,now,spot=10018.,price=8.,underlying='NIFTY'):
    with sqlite3.connect(str(base)+'.expiry-paper.db') as c:
        c.execute('INSERT INTO expiry_paper_ticks VALUES(?,?,?,?,?,?)',(now.date().isoformat(),underlying,now.isoformat(),spot,spot,json.dumps(dict(legs={'X':quote(price,now)}))))


def put_state(base,state,position=None):
    with sqlite3.connect(X.path_for(base)) as c:
        c.execute('CREATE TABLE IF NOT EXISTS e02_state(id INTEGER PRIMARY KEY,payload TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS e02_positions(id INTEGER PRIMARY KEY,day TEXT,status TEXT,payload TEXT)')
        if position:
            position['id']=1
            c.execute('INSERT INTO e02_positions VALUES(?,?,?,?)',(1,position['day'],position['status'],json.dumps(position)))
        c.execute('INSERT OR REPLACE INTO e02_state VALUES(1,?)',(json.dumps(state),))


def state(now):
    s=X._new_state(now)
    s['day']=dict(date=now.date().isoformat(),budget=2500.,spent=0.,trades=0)
    return s


def test_shadow_defaults_off_without_creating_a_database(tmp_path):
    from config import Settings
    assert Settings().EXPIRY_E02_SHADOW_ENABLED is False
    base=tmp_path/'app.db'
    assert X.run_tick(base,now=stamp())['status']=='DISABLED'
    assert not (tmp_path/'app.db.expiry-e02.db').exists()


def test_signal_refuses_gaps_invalid_bars_and_unknown_future():
    b=bars();assert X.signal(b)
    b[1]['end']=(stamp(13,0)+timedelta(seconds=90)).isoformat();assert X.signal(b) is None
    b=bars();b[-1]['f'][3]=None;assert X.signal(b) is None
    b=bars();b[-1]['s'][1]=1.;assert X.signal(b) is None


def test_future_extension_does_not_enter_a_signal():
    b=bars();first=X.signal(b)
    assert first and first.direction==1
    extended=b+[dict(end=stamp(13,12).isoformat(),s=[1,1,1,1],f=[1,1,1,1])]
    assert X.signal(extended[:12])==first


def test_entry_is_one_lot_capped_before_submission():
    reading=X.signal(bars());book=SimpleNamespace(by_symbol={'X':contract()});now=stamp(13,11)
    p=X.plan(reading,{'X':quote(8.,now)},book,now,1250,25000)
    assert p and p['limit']<=8.8
    assert EP.worst_case_loss(p['limit'],1,65)<=1250
    assert X.plan(reading,{'X':quote(8.,now)},book,now,100,25000) is None


@pytest.mark.parametrize('expiry,lot',[(date(2026,11,10),65),(date(2026,11,3),75)])
def test_wrong_expiry_or_unvalidated_lot_refuses_entry(expiry,lot):
    r=X.signal(bars());now=stamp(13,11);b=SimpleNamespace(by_symbol={'X':contract(expiry,lot)})
    assert X.plan(r,{'X':quote(8.,now)},b,now,1250,25000) is None


def test_stale_and_missing_bids_are_not_entry_prices():
    r=X.signal(bars());now=stamp(13,11);book=SimpleNamespace(by_symbol={'X':contract()})
    assert X.plan(r,{'X':quote(8.,now-timedelta(seconds=30))},book,now,1250,25000) is None
    q=quote(8.,now);q['b']=[]
    assert X.plan(r,{'X':q},book,now,1250,25000) is None


def test_stale_source_does_not_create_or_fill_shadow(tmp_path):
    b=source(tmp_path);add(b,stamp())
    assert X.run_tick(b,enabled=True,now=stamp()+timedelta(seconds=21))['status']=='STALE_SOURCE'
    assert not (tmp_path/'app.db.expiry-e02.db').exists()


def test_sensex_evidence_does_not_qualify_nifty(tmp_path):
    b=source(tmp_path);add(b,stamp(),underlying='SENSEX')
    assert X.run_tick(b,enabled=True,now=stamp())['status']=='NO_NIFTY_SOURCE'


def test_corrupt_cash_fails_closed(tmp_path):
    b=source(tmp_path);now=stamp();add(b,now)
    s=state(now);s['cash']=99999.;put_state(b,s)
    with pytest.raises(ValueError,match='cash journal'):X.run_tick(b,enabled=True,now=now)


def test_pending_entry_reloads_contracts_and_preserves_daily_reserve(tmp_path,monkeypatch):
    b=source(tmp_path);now=stamp();add(b,now)
    s=state(now);s['pending']=dict(symbol='X',limit=8.8,at=now.isoformat(),expires=(now+timedelta(minutes=1)).isoformat(),direction=1,underlying_stop=9990.)
    put_state(b,s)
    import fno_underlyings
    monkeypatch.setattr(fno_underlyings,'get_instruments_for',lambda u:SimpleNamespace(by_symbol={'X':contract()}))
    out=X.run_tick(b,enabled=True,now=now)
    assert out['status']=='OPEN' and out['day']['trades']==1 and out['day']['spent']<=1250
    again=X.run_tick(b,enabled=True,now=now)
    assert again['day']==out['day']
    with sqlite3.connect(X.path_for(b)) as c:
        p=json.loads(c.execute('SELECT payload FROM e02_positions').fetchone()[0])
        assert p['lots']==1 and p['stop']==4.8 and p['e02_policy']['hold']==480


def test_disabled_flag_still_closes_an_open_pending_exit(tmp_path):
    b=source(tmp_path);now=stamp();add(b,now,price=6.)
    pos=EP._new_position(now.date().isoformat(),'NIFTY','E02R3','NFO',contract(),8.,1,now-timedelta(minutes=5))
    pos.update(exit_pending='STOP',direction=1,underlying_stop=9990.)
    s=state(now-timedelta(minutes=10));s['position']=pos;s['day']['spent']=pos['max_loss'];s['day']['trades']=1
    put_state(b,s,pos)
    result=X.run_tick(b,enabled=False,now=now)
    assert result['status']=='OBSERVING' and result['cash']<25000
    with sqlite3.connect(X.path_for(b)) as c:assert c.execute('SELECT status FROM e02_positions').fetchone()[0]=='CLOSED'


def test_restart_cannot_refill_cash_or_the_days_allowance(tmp_path):
    b=source(tmp_path);now=stamp();add(b,now)
    s=state(now);s['day'].update(spent=2500.,trades=2)
    s['pending']=dict(symbol='X',limit=8.8,expires=(now+timedelta(minutes=1)).isoformat(),direction=1,underlying_stop=9990.)
    put_state(b,s)
    result=X.run_tick(b,enabled=True,now=now,book=SimpleNamespace(by_symbol={'X':contract()}))
    assert result['day']['spent']==2500 and result['day']['trades']==2 and result['status']=='OBSERVING'


def test_old_open_position_is_unresolved_and_blocks_new_day(tmp_path):
    b=source(tmp_path);now=stamp();add(b,now)
    s=state(now-timedelta(days=1));s['position']={'status':'OPEN'};put_state(b,s)
    assert X.run_tick(b,enabled=True,now=now)['status']=='UNRESOLVED_PRIOR_DAY'


def test_partial_sample_minute_is_not_filled_forward():
    s=state(stamp(13,0))
    for sec in (0,10,20):X._sample(s,dict(ts=stamp(13,0,sec).isoformat(),spot=10000.,fut=10000.,quotes='{}'))
    assert X._sample(s,dict(ts=stamp(13,1).isoformat(),spot=10000.,fut=10000.,quotes='{}')) is None
    assert not s['bars']


def test_open_leg_stays_in_the_existing_quote_batch_when_disabled(tmp_path):
    b=source(tmp_path);now=stamp();s=state(now)
    s['position']={'symbol':'X','status':'OPEN'};put_state(b,s)
    book=SimpleNamespace(by_symbol={'X':contract()})
    assert X.held_contracts(b,book)==[book.by_symbol['X']]
    assert X.held_contracts(b,SimpleNamespace(by_symbol={}))==[]


def test_archive_stream_opens_once_then_disabled_shadow_keeps_its_time_exit(tmp_path):
    base=source(tmp_path);book=SimpleNamespace(by_symbol={'X':contract()})
    closes=[10000+i*2 for i in range(9)]+[10015.,10014.,10018.]+[10018.]*10
    opened=None
    for minute,c in enumerate(closes):
        for second in (0,10,20,30,40,50):
            now=stamp(13,0)+timedelta(minutes=minute,seconds=second)
            add(base,now,spot=c+{0:-1,10:1,20:-1,30:.2,40:0,50:0}[second])
            out=X.run_tick(base,enabled=minute<14,now=now,book=book)
            if out['status']=='OPEN':opened=out
    assert opened and opened['day']['trades']==1
    assert out['status']=='OBSERVING' and out['day']['trades']==1
    with sqlite3.connect(X.path_for(base)) as db:
        rows=db.execute('SELECT payload FROM e02_positions').fetchall()
        assert len(rows)==1
        p=json.loads(rows[0][0]);assert p['status']=='CLOSED' and p['_events'][-1]['action']=='TIME'


def test_late_activation_does_not_backfill_earlier_forward_trades(tmp_path):
    base=source(tmp_path);book=SimpleNamespace(by_symbol={'X':contract()})
    for i,c in enumerate([10000+j*2 for j in range(9)]+[10015.,10014.,10018.]+[10018.]):
        for second in (0,10,20,30,40,50):add(base,stamp(13,0)+timedelta(minutes=i,seconds=second),spot=c+{0:-1,10:1,20:-1,30:.2,40:0,50:0}[second])
    out=X.run_tick(base,enabled=True,now=stamp(13,12,50),book=book)
    assert out['day']['trades']==0 and out['status']=='OBSERVING'


def test_missing_bid_never_becomes_a_terminal_sale(tmp_path):
    base=source(tmp_path);now=stamp();add(base,now)
    with sqlite3.connect(str(base)+'.expiry-paper.db') as db:
        raw=json.loads(db.execute('SELECT quotes FROM expiry_paper_ticks').fetchone()[0]);raw['legs']['X']['b']=[]
        db.execute('UPDATE expiry_paper_ticks SET quotes=?',(json.dumps(raw),))
    p=EP._new_position(now.date().isoformat(),'NIFTY','E02R3','NFO',contract(),8.,1,now-timedelta(minutes=5))
    p.update(exit_pending='STOP',direction=1,underlying_stop=9990.)
    s=state(now);s['position']=p;s['day'].update(spent=p['max_loss'],trades=1);put_state(base,s,p)
    result=X.run_tick(base,enabled=False,now=now)
    assert result['status']=='OPEN' and result['cash']==25000
    with sqlite3.connect(X.path_for(base)) as db:
        p=json.loads(db.execute('SELECT payload FROM e02_positions').fetchone()[0])
        assert p['lots_open']==1 and len(p['_events'])==1 and p['assumed_pnl'] is None


def test_entry_cannot_pay_through_its_precommitted_limit(tmp_path):
    base=source(tmp_path);now=stamp();add(base,now,price=10.)
    s=state(now);s['pending']=dict(symbol='X',limit=8.8,at=now.isoformat(),expires=(now+timedelta(minutes=1)).isoformat(),direction=1,underlying_stop=9990.)
    put_state(base,s)
    out=X.run_tick(base,enabled=True,now=now,book=SimpleNamespace(by_symbol={'X':contract()}))
    assert out['day']['spent']==0 and out['day']['trades']==0


def test_source_database_is_read_only(tmp_path):
    import hashlib
    base=source(tmp_path);now=stamp();add(base,now)
    p=tmp_path/'app.db.expiry-paper.db';before=hashlib.sha256(p.read_bytes()).hexdigest()
    X.run_tick(base,enabled=True,now=now,book=SimpleNamespace(by_symbol={'X':contract()}))
    assert hashlib.sha256(p.read_bytes()).hexdigest()==before
