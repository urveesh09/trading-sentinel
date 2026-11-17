"""EN06 (auditor's brief, Nov 17): the paper execution contract.

1. One archived packet, or a newer packet repeating the same bids, never sells the same displayed depth twice,
   across callbacks and restarts (the consumed depth is saved with the fill).
2. The day line splits filled sales, the assumed residual of unsold lots and open tickets.
3. The main ticket's notices are stored with the fill / settlement and drained idempotently.
4. CAS 2.0 (2026-12-07): fill labels and the legacy settlement sample follow the dated schedule.
5. A real 13:00 route: recorder ticks from 12:47 -> twelve bars -> signal -> plan -> fill on a later packet;
   a late start or a missing minute refuses instead.
"""
from datetime import date,datetime,time,timedelta
from types import SimpleNamespace
import json,sqlite3
import expiry_e02 as X
import expiry_paper as EP
from tests.test_expiry_e02 import add,contract,source,stamp
from tests.test_expiry_en01 import _book,_position,_saved


def _tick(base,now,legs,spot=10018.,fut=None):
    with sqlite3.connect(str(base)+'.expiry-paper.db') as c:
        c.execute('INSERT INTO expiry_paper_ticks VALUES(?,?,?,?,?,?)',(now.date().isoformat(),'NIFTY',now.isoformat(),spot,spot if fut is None else fut,json.dumps(dict(legs=legs))))


def _q(bids,now,ask=None):
    return dict(b=bids,a=[[ask or bids[0][0]+.05,650]],ltp=bids[0][0],ts=now.isoformat())


def test_two_callbacks_on_one_archived_packet_sell_its_depth_once(tmp_path):
    # Auditor's reproduction: one displayed lot, two open lots, a pending stop, callbacks 10 s apart, no new row.
    base=source(tmp_path);now=stamp(14,30,5);_tick(base,now,{'X':_q([[5.,65]],now)})
    p=_position(X.E032,stamp(14,20));p['exit_pending']='STOP';_book(base,X.E032,now,p)
    X.run_tick(base,enabled=False,now=now,variant=X.E032)
    out=X.run_tick(base,enabled=False,now=now+timedelta(seconds=10),variant=X.E032)          # a fresh callback, no new packet
    saved=_saved(base,X.E032)
    assert saved['lots_open']==1 and [e['action'] for e in saved['_events']].count('STOP')==1 and out['notices']==[]
    with sqlite3.connect(X.path_for(base,X.E032)) as db:
        s=json.loads(db.execute('SELECT payload FROM e02_state').fetchone()[0])
    assert s['consumed']['X']['taken']==[[5.0,65]] and s['decision_counts']['exit']['same_packet']>=1


def test_deeper_book_sells_the_rest_and_a_changed_book_is_fresh(tmp_path):
    base=source(tmp_path);now=stamp(14,30,5);_tick(base,now,{'X':_q([[5.,65],[4.9,65]],now)})
    p=_position(X.E032,stamp(14,20),lots=3);p['exit_pending']='STOP';_book(base,X.E032,now,p)
    X.run_tick(base,enabled=False,now=now,variant=X.E032)
    assert _saved(base,X.E032)['lots_open']==1                       # two lots across two levels
    later=now+timedelta(seconds=10);_tick(base,later,{'X':_q([[5.,65],[4.9,65]],later)})
    X.run_tick(base,enabled=False,now=later,variant=X.E032)
    assert _saved(base,X.E032)['lots_open']==1                       # same bids: nothing left to sell
    third=later+timedelta(seconds=10);_tick(base,third,{'X':_q([[4.85,130]],third)})
    X.run_tick(base,enabled=False,now=third,variant=X.E032)
    assert _saved(base,X.E032)['status']=='CLOSED'


def test_partial_sale_then_settlement_splits_filled_and_assumed(tmp_path):
    # Auditor's reproduction: a partial sale's filled profit was shown as filled 0 and folded into "assumed".
    base=source(tmp_path);now=stamp(14,30,5);_tick(base,now,{'X':_q([[12.,65]],now)})
    p=_position(X.E032,stamp(14,20),lots=3,entry=8.);p['exit_pending']='TIME';_book(base,X.E032,now,p)
    X.run_tick(base,enabled=False,now=now,variant=X.E032)
    filled=_saved(base,X.E032)['net_pnl'];assert filled>0
    X.reconcile(base,X.E032,stamp(15,45))                            # no settlement sample: worst case for 2 lots
    saved=_saved(base,X.E032)
    assert saved['status']=='UNRESOLVED' and saved['net_pnl']==filled and saved['assumed_pnl']<0
    line=[x for x in X.summary_lines(base,'2026-11-03','NIFTY') if x.startswith('  main day:')][0]
    assert f"filled net Rs {filled:+,.2f}" in line and f"assumed residual Rs {saved['assumed_pnl']:+,.2f} (not a fill)" in line
    assert f"= Rs {filled+saved['assumed_pnl']:+,.2f}" in line


def test_open_tickets_are_counted_not_valued_in_the_day_line(tmp_path):
    base=source(tmp_path);p=_position(X.E032,stamp(14,20));_book(base,X.E032,stamp(14,25),p)   # saved as OPEN
    line=[x for x in X.summary_lines(base,'2026-11-03','NIFTY') if x.startswith('  main day:')][0]
    assert 'filled net Rs +0.00' in line and '1 ticket still open' in line


def test_main_notices_are_stored_with_the_fill_and_drained_once(tmp_path):
    base=source(tmp_path);now=stamp(14,30,5);_tick(base,now,{'X':_q([[9.,650]],now)})
    p=_position(X.E032,stamp(14,20));p['exit_pending']='TIME';_book(base,X.E032,now,p)
    X.run_tick(base,enabled=False,now=now,variant=X.E032,keep_notices=True)
    sent=[]
    def broken(notes):raise RuntimeError('outbox down')
    try:X.drain_notices(base,X.E032,broken,now)
    except RuntimeError:pass
    assert X.drain_notices(base,X.E032,sent.extend,now)==1 and X.drain_notices(base,X.E032,sent.extend,now)==0
    assert len(sent)==1 and sent[0][0].endswith(':TIME')
    # Re-queueing the same key into the expiry outbox is ignored, so a crash after queueing cannot duplicate it.
    import expiry_paper as xp
    xp.queue_notices(str(base),sent,now);xp.queue_notices(str(base),sent,now)
    with sqlite3.connect(xp.expiry_db_path(str(base))) as db:
        assert db.execute('SELECT COUNT(*) FROM expiry_paper_notices').fetchone()[0]==1
    # A shadow (keep_notices off) stores nothing to drain.
    assert X.drain_notices(base,X.E031,sent.extend,now)==0


def test_cas2_labels_and_no_guessed_settlement():
    assert EP.fill_model(time(15,20))=='AUCTION_WINDOW' and EP.fill_model(time(15,20),date(2026,12,3))=='AUCTION_WINDOW'
    assert EP.fill_model(time(15,20),date(2026,12,8))=='CONTINUOUS' and EP.fill_model(time(15,30),date(2026,12,8))=='AUCTION_WINDOW'
    c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
    c.execute('CREATE TABLE expiry_paper_ticks(day TEXT,underlying TEXT,ts TEXT,spot REAL,fut REAL,quotes TEXT)')
    for d in ('2026-12-03','2026-12-08'):c.execute('INSERT INTO expiry_paper_ticks VALUES(?,?,?,?,?,?)',(d,'NIFTY',d+'T15:37:00+05:30',26000.,26000.,'{}'))
    assert EP._settlement_spot(c,'2026-12-03','NIFTY')==26000. and EP._settlement_spot(c,'2026-12-08','NIFTY') is None


def _route(tmp_path,skip=()):
    """Recorder rows every 10 s from 12:47 (minutes in ``skip`` missing: no login yet, or a dropped minute), each
    followed by the scheduler's run_tick, as Production sees them. One close a minute: an efficient rise
    12:47-12:56, a two-bar pullback, and the resumption in the bar that ends at 13:00."""
    closes=[10000.+2*i for i in range(10)]+[10017.,10016.,10019.,10020.,10021.]
    tmp_path.mkdir(parents=True,exist_ok=True);base=source(tmp_path);book=SimpleNamespace(by_symbol={'X':contract()});out=None
    t=stamp(12,47)
    while t<=stamp(13,1,10):
        m=int((t-stamp(12,47)).total_seconds()//60)
        if m not in skip:_tick(base,t,{'X':_q([[7.95,650]],t,8.)},spot=closes[m])
        r=X.run_tick(base,enabled=True,now=t,book=book,variant=X.E032)
        out=r if 'decision_counts' in r else out
        t+=timedelta(seconds=10)
    return out,X.positions(base,X.E032)


def test_1300_route_from_a_1247_start_plans_at_1300_and_fills_on_the_next_packet(tmp_path):
    out,pos=_route(tmp_path)
    assert len(pos)==1 and pos[0]['entry_ts'].startswith('2026-11-03T13:00') and pos[0]['lots']==2 and pos[0]['direction']==1
    assert out['decision_counts']['signal']['passed']>=1 and out['decision_counts']['pending']['filled']==1


def test_late_login_or_a_missing_warmup_minute_refuses_at_1300(tmp_path):
    out,pos=_route(tmp_path/'late',skip=range(0,8))              # no recorder rows before 12:55 (late login)
    assert pos==[] and out['decision_counts']['signal'].get('warmup',0)>=1
    out,pos=_route(tmp_path/'gap',skip=(5,))                     # the 12:52 minute missing: a gap in the bar run
    assert pos==[] and out['decision_counts']['signal'].get('bar_gap',0)>=1
