"""expiry-v5: E03.2 is the expiry book's main paper ticket, on NIFTY and SENSEX (owner order, Nov 3 2026)."""
from datetime import date,datetime,time,timedelta
from types import SimpleNamespace
import json,sqlite3
import expiry_e02 as X
import expiry_paper as xp
import expiry_paper as EP
from tests.test_expiry_e02 import add,bars,contract,quote,source,stamp
from tests.test_expiry_paper import TUESDAY,_at,_insert_legs

THURSDAY=date(2026,11,5)


def sensex_put(strike=79900.,expiry=THURSDAY):
    return SimpleNamespace(underlying='SENSEX',expiry=expiry,lot_size=20,instrument_type='PE',strike=strike,tradingsymbol='S',token=7)


def test_sensex_ticket_keeps_the_rupees_a_lot_four_strikes_and_twice_the_put_reserve():
    now=datetime(2026,11,5,13,11,tzinfo=EP.IST);book=SimpleNamespace(by_symbol={'S':sensex_put()})
    reading=X.Reading(-1,80000.,15.,791,-.9)
    p=X.plan(reading,{'S':quote(20.,now)},book,now,2500.,25000.,X.E032,'SENSEX')
    assert p and 1<=p['lots']<=6 and EP.worst_case_loss(p['limit'],p['lots'],20,EP.fee_schedule('BFO'))<=2500
    assert p['limit']==21.6                                                              # the 8% limit
    assert X.plan(reading,{'S':quote(10.,now)},book,now,2500.,25000.,X.E032,'SENSEX') is None   # under Rs 16.25: too far out
    assert X.plan(reading,{'S':quote(70.,now)},book,now,2500.,25000.,X.E032,'SENSEX') is None   # over Rs 65
    far=SimpleNamespace(**{**vars(sensex_put()),'strike':79500.})                         # five 100-point steps
    assert X.plan(X.Reading(-1,80000.,60.,791,-.9),{'S':quote(20.,now)},SimpleNamespace(by_symbol={'S':far}),now,2500.,25000.,X.E032,'SENSEX') is None
    # A NIFTY plan never takes a SENSEX contract, and NIFTY-only variants never see SENSEX.
    assert X.plan(reading,{'S':quote(20.,now)},book,now,2500.,25000.,X.E032) is None
    assert X.E031.underlyings==('NIFTY',) and X.E032.underlyings==('NIFTY','SENSEX')


def test_run_tick_follows_the_index_that_expires_today(tmp_path):
    base=source(tmp_path);now=datetime(2026,11,5,13,5,tzinfo=EP.IST);add(base,now,spot=80000.,underlying='SENSEX')
    out=X.run_tick(base,enabled=True,now=now,book=SimpleNamespace(by_symbol={}),variant=X.E032)
    assert out['status']=='OBSERVING' and out['underlying']=='SENSEX' and out['notices']==[]
    assert X.run_tick(base,enabled=True,now=now,variant=X.E031)['status']=='NO_NIFTY_SOURCE'


def test_buy_and_sell_produce_owner_notices(tmp_path):
    base=source(tmp_path);now=stamp(13,15);add(base,now)
    s=X._new_state(now-timedelta(minutes=10),X.E032)
    s['day']=dict(date=now.date().isoformat(),budget=5000.,spent=0.,trades=0)
    s['pending']=dict(symbol='X',limit=8.6,lots=2,at=now.isoformat(),expires=(now+timedelta(minutes=1)).isoformat(),direction=1,underlying_stop=9990.)
    with sqlite3.connect(X.path_for(base,X.E032)) as db:
        db.execute('CREATE TABLE e02_state(id INTEGER PRIMARY KEY,payload TEXT)')
        db.execute('CREATE TABLE e02_positions(id INTEGER PRIMARY KEY,day TEXT,status TEXT,payload TEXT)')
        db.execute('INSERT INTO e02_state VALUES(1,?)',(json.dumps(s),))
    out=X.run_tick(base,enabled=True,now=now,book=SimpleNamespace(by_symbol={'X':contract()}),variant=X.E032)
    (key,text),=out['notices']
    assert out['status']=='OPEN' and key.endswith(':BUY') and 'E03.2 (main): bought 2 lots X at Rs 8.00 (call ticket' in text
    assert 'everything is sold from 15:14' in text and 'Paper only' in text
    later=stamp(15,14,5);add(base,later,price=9.)
    out=X.run_tick(base,enabled=True,now=later,variant=X.E032)
    (key,text),=out['notices']
    assert out['status']=='OBSERVING' and 'FLAT_TIME' in key and 'sold 2 lots X at Rs 8.95 (FLAT_TIME); ticket closed, net Rs' in text
    assert X.day_results(base)=={('2026-11-03','NIFTY'):X.positions(base)[0]['net_pnl']}
    # The scheduler queues them in the expiry outbox; the usual flush sends them.
    assert xp.queue_notices(str(base),out['notices'],later)==1
    with sqlite3.connect(xp.expiry_db_path(str(base))) as db:
        assert db.execute('SELECT COUNT(*) FROM expiry_paper_notices').fetchone()[0]==1


def test_a_new_day_records_the_main_and_silences_a_b_c(monkeypatch):
    monkeypatch.setattr(xp.settings,'EXPIRY_MAIN_STRATEGY','E032')
    state=xp.new_day_state()
    assert state['main']=='E032' and xp.e032_main(state)
    monkeypatch.setattr(xp.settings,'EXPIRY_MAIN_STRATEGY','ABC')
    assert xp.new_day_state()['main']=='ABC' and not xp.e032_main(xp.new_day_state())
    assert not xp.e032_main({})                                    # a day begun before expiry-v5


def test_summary_and_owner_rule_read_e032_on_its_days_and_a_b_c_before(tmp_path,monkeypatch):
    base=source(tmp_path);monkeypatch.setattr(xp.settings,'DB_PATH',str(base))
    p=EP._new_position('2026-11-05','SENSEX','E032','BFO',sensex_put(),20.,2,datetime(2026,11,5,13,20,tzinfo=EP.IST))
    p.update(status='CLOSED',net_pnl=-180.5,costs=40.5,gross=-140.,e02_policy=X.policy_for(X.E032),direction=-1,underlying_stop=80100.)
    with sqlite3.connect(X.path_for(base,X.E032)) as db:
        db.execute('CREATE TABLE e02_positions(id INTEGER PRIMARY KEY,day TEXT,status TEXT,payload TEXT)')
        db.execute('INSERT INTO e02_positions VALUES(1,?,?,?)',(p['day'],p['status'],json.dumps(p)))
    with xp._store(xp.expiry_db_path(str(base))) as conn:
        _insert_legs(conn,(('2026-10-06','C','13:40','X1',6,-500.,'CLOSED'),))
        old=xp.new_day_state();old.pop('main')
        xp._save_state(conn,'2026-10-06','NIFTY',old,_at(TUESDAY,15,45))
        monkeypatch.setattr(xp.settings,'EXPIRY_MAIN_STRATEGY','E032')
        new=xp.new_day_state()
        xp._save_state(conn,'2026-11-05','SENSEX',new,datetime(2026,11,5,15,45,tzinfo=EP.IST))
        summary=xp.format_day_summary(conn,'2026-11-05','SENSEX',new)
        owner=xp.owner_rule_lines(conn,'2026-11-05')
    assert 'MAIN E03.2 (expiry-v5)' in summary and 'untested on SENSEX' in summary
    assert 'E03.2: 2 lots S bought 20.00, CLOSED, net Rs -180.50 after fees Rs 40.50' in summary
    assert 'A, B and C, the main book until expiry-v5, now shadows (no Telegram trades):' in summary and 'A+B+C day:' in summary
    assert 'main book lost 2 of 2' in owner[0]                    # Oct 6 by A+B+C (-500), Nov 5 by E03.2 (-180.50)
    assert owner[1].split(': ',1)[1].startswith('E032 (main) 1/1 (Rs -180)')
