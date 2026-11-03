"""E03: E02's signal with up to three lots and a free runner after the 2x sale; separate, disabled."""
from datetime import timedelta
from types import SimpleNamespace
import json,sqlite3
import expiry_e02 as X
import expiry_paper as EP
from tests.test_expiry_e02 import add,bars,contract,quote,source,stamp


def e03_state(now):
    s=X._new_state(now,X.E03)
    s['day']=dict(date=now.date().isoformat(),budget=2500.,spent=0.,trades=0)
    return s


def position(lots=3,entry=8.,variant=X.E03,now=None):
    now=now or stamp()
    p=EP._new_position(now.date().isoformat(),'NIFTY',variant.play,'NFO',contract(),entry,lots,now-timedelta(minutes=2))
    p.update(stop=round(entry*.6,2),direction=1,underlying_stop=9990.,e02_version=variant.version,e02_policy=X.policy_for(variant))
    return p


def test_e03_defaults_off_and_never_touches_e02_cash(tmp_path):
    from config import Settings
    assert Settings().EXPIRY_E03_SHADOW_ENABLED is False
    base=tmp_path/'app.db'
    assert X.run_tick(base,now=stamp(),variant=X.E03)['status']=='DISABLED'
    assert not (tmp_path/'app.db.expiry-e03.db').exists() and not (tmp_path/'app.db.expiry-e02.db').exists()
    assert X.path_for(base,X.E03)!=X.path_for(base) and X.E02.version=='expiry-e02-r3-v1'


def test_e03_buys_up_to_three_lots_inside_the_same_ticket_reserve():
    reading=X.signal(bars());book=SimpleNamespace(by_symbol={'X':contract()});now=stamp(13,11)
    p=X.plan(reading,{'X':quote(5.5,now)},book,now,1250,25000,X.E03)
    assert p['lots']==3 and EP.worst_case_loss(p['limit'],3,65)<=1250
    assert X.plan(reading,{'X':quote(5.5,now)},book,now,1250,25000)['lots']==1      # E02 stays one lot
    # A dearer ticket fits fewer lots; never more than the reserve.
    assert X.plan(reading,{'X':quote(9.,now)},book,now,1250,25000,X.E03)['lots']==2
    assert X.plan(reading,{'X':quote(15.,now)},book,now,1250,25000,X.E03)['lots']==1
    assert X.plan(reading,{'X':quote(19.,now)},book,now,1250,25000,X.E03) is None        # one lot plus fees is over Rs 1,250
    # Visible depth caps the lots: one lot shown buys one lot.
    assert X.plan(reading,{'X':quote(5.5,now,qty=65)},book,now,1250,25000,X.E03)['lots']==1


def test_e03_never_picks_beyond_four_strikes():
    reading=X.Reading(1,10018.,30.,791,.9);now=stamp(13,11)
    far=SimpleNamespace(underlying='NIFTY',expiry=now.date(),lot_size=65,instrument_type='CE',strike=10250.,tradingsymbol='X',token=1)
    book=SimpleNamespace(by_symbol={'X':far})
    assert X.plan(reading,{'X':quote(8.,now)},book,now,1250,25000) is not None           # E02's 400-point allowance
    assert X.plan(reading,{'X':quote(8.,now)},book,now,1250,25000,X.E03) is None


def test_the_2x_sale_keeps_half_the_lots_as_a_runner_and_one_lot_sells_whole():
    now=stamp()
    assert X.action(position(3),16.05,10018.,now)==(2,'TARGET_BASE')
    assert X.action(position(2),16.05,10018.,now)==(1,'TARGET_BASE')
    assert X.action(position(1),16.05,10018.,now)==(1,'TARGET')
    assert X.action(position(3,variant=X.E02),16.05,10018.,now)==(3,'TARGET')           # E02 unchanged


def test_partial_sale_latches_nothing_and_puts_the_runner_on_a_floor_at_cost():
    now=stamp();p=position(3)
    X.action(p,16.05,10018.,now)
    event=X.sell_base(p,EP.Quote(((16.,650),),((16.05,650),),16.,now),2,now)
    assert event['action']=='TARGET_BASE' and event['lots']==2
    assert p['lots_open']==1 and p['status']=='OPEN' and p['exit_pending'] is None and p['runner']
    assert p['stop']==8.03                                        # half of the 16.05 peak, just above the 8.00 cost
    assert X.sell_base(position(3),None,2,now) is None            # no fresh bid: nothing sold, no runner


def test_runner_ignores_the_idle_clock_and_the_index_stop_but_keeps_its_floor():
    now=stamp();p=position(3);X.action(p,16.05,10018.,now)
    X.sell_base(p,EP.Quote(((16.,650),),((16.05,650),),16.,now),2,now)
    late=now+timedelta(minutes=30)
    assert X.action(p,30.,9000.,late) is None                     # far past 8 minutes, index far below its stop
    assert p['stop']==15.0
    assert X.action(p,14.95,10018.,late)==(1,'RUNNER_TRAIL')
    q=position(3);X.action(q,16.05,10018.,now);X.sell_base(q,EP.Quote(((16.,650),),((16.05,650),),16.,now),2,now)
    assert X.action(q,80.,10018.,late)==(1,'HERO_TARGET')        # 10x entry


def test_held_contracts_keep_each_variants_open_leg(tmp_path):
    base=source(tmp_path);now=stamp()
    s=e03_state(now);s['position']={'symbol':'X','status':'OPEN'}
    with sqlite3.connect(X.path_for(base,X.E03)) as c:
        c.execute('CREATE TABLE e02_state(id INTEGER PRIMARY KEY,payload TEXT)')
        c.execute('INSERT INTO e02_state VALUES(1,?)',(json.dumps(s),))
    book=SimpleNamespace(by_symbol={'X':contract()})
    assert X.held_contracts(base,book)==[book.by_symbol['X']]
    assert X.has_open_book(base,X.E03) and not X.has_open_book(base)


def test_archive_stream_banks_two_lots_at_2x_and_the_runner_trails_after_the_idle_clock(tmp_path):
    base=source(tmp_path);book=SimpleNamespace(by_symbol={'X':contract()})
    closes=[10000+i*2 for i in range(9)]+[10015.,10014.,10018.]+[10018.]*16
    price={**{m:5.5 for m in range(15)},15:12.,16:12.,17:30.,**{m:30. for m in range(18,26)},26:14.,27:14.}
    out=None
    for minute,c in enumerate(closes):
        for second in (0,10,20,30,40,50):
            now=stamp(13,0)+timedelta(minutes=minute,seconds=second)
            add(base,now,spot=c+{0:-1,10:1,20:-1,30:.2,40:0,50:0}[second],price=price[minute])
            out=X.run_tick(base,enabled=True,now=now,book=book,variant=X.E03)
    assert not (tmp_path/'app.db.expiry-e02.db').exists()
    with sqlite3.connect(X.path_for(base,X.E03)) as db:
        rows=[json.loads(r[0]) for r in db.execute('SELECT payload FROM e02_positions')]
    assert len(rows)==1
    p=rows[0];events=[(e['action'],e['lots']) for e in p['_events']]
    assert p['play']=='E03' and p['lots']==3 and p['status']=='CLOSED'
    assert events==[('BUY',3),('TARGET_BASE',2),('RUNNER_TRAIL',1)]
    assert abs(p['gross']-p['costs']-p['net_pnl'])<.02 and p['net_pnl']>0
    assert out['cash']==round(25000+p['net_pnl'],2) and out['version']=='expiry-e03-v1'
