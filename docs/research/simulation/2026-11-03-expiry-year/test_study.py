from datetime import datetime,timedelta
import copy
import pytest
import study as S
from candidates import lock40


def toy(prices, volumes=None):
    x=S.Session.__new__(S.Session)
    x.day="2026-01-06";x.underlying="NIFTY";x.info={"window":"synthetic"}
    x.exchange="NFO";x.lot=65;x.schedule=S.EP.fee_schedule("NFO")
    x.p75=[.05,.05,.05,.1,.1,.2,1.05]
    x.names=["X"];x.kinds={"X":"CE"}
    x._contract={"X":S.L.Contract(1,"X","NIFTY",S.date(2026,1,6),25000,"CE",65)}
    x.now=[datetime(2026,1,6,14,0,tzinfo=S.EP.IST)+timedelta(seconds=10*i) for i in range(len(prices))]
    x.clock=[t.time() for t in x.now];x.n=len(prices);x.spot=[24900.]*x.n
    x._bars=[{"CE":dict(open=p,high=p,low=p,close=p,volume=(volumes or [10000]*x.n)[i])} for i,p in enumerate(prices)]
    x._signals={S.L.NATIVE_SIGNAL:({"box":None},[])}
    return x


def test_initial_stop_is_not_lost_for_research_play_name():
    x=toy([5,5,3,3,3])
    p=S.simulate(x,(0,"X","TEST"),S.FIXED["E011"])
    assert p["_events"][-1]["action"]=="STOP"
    assert p["_events"][-1]["ts"]==x.now[3].isoformat()
    S.audit_position(p)


def test_future_high_low_do_not_change_decision_quote_or_quantity():
    a=toy([5,5,5,5]);b=copy.deepcopy(a)
    b._bars[1]["CE"].update(high=50,low=.1)
    assert a.quote(0,"X")==b.quote(0,"X")
    # Ordinary price is next OPEN, no use of that bar's later high/low.
    p=S.simulate(a,(0,"X","TEST"),S.FIXED["E011"])
    q=S.simulate(b,(0,"X","TEST"),S.FIXED["E011"])
    assert (p["entry_price"],p["lots"])==(q["entry_price"],q["lots"])


def test_adverse_prices_are_execution_only_and_keep_full_premium_ceiling():
    x=toy([5,5,1,1,1]);x._bars[1]["CE"]["high"]=50
    p=S.simulate(x,(0,"X","TEST"),S.FIXED["E011"],True)
    assert p is None # cannot afford even one whole lot, never pre-choose a cheaper future entry


def test_thin_execution_bar_cannot_fill_the_decision_order():
    x=toy([5,5,5],volumes=[10000,0,10000])
    assert S.simulate(x,(0,"X","TEST"),S.FIXED["E011"]) is None


def test_exit_stays_pending_through_no_volume_then_fills_later():
    x=toy([5,5,3,2,1,1],volumes=[10000,10000,10000,0,10000,10000])
    p=S.simulate(x,(0,"X","TEST"),S.FIXED["E011"])
    assert p["missed_exit_bars"]==1
    assert p["_events"][-1]["ts"]==x.now[4].isoformat()
    assert p["_events"][-1]["price"]<1
    S.audit_position(p)


def test_missing_next_grid_point_does_not_become_a_fill():
    x=toy([5,5,5]);x.now[1]+=timedelta(seconds=10)
    assert S.simulate(x,(0,"X","TEST"),S.FIXED["E011"]) is None


def test_no_terminal_sale_is_invented():
    x=toy([5,5,5])
    p=S.simulate(x,(0,"X","TEST"),S.FIXED["E011"])
    assert p["status"]=="UNRESOLVED_AT_DATA_END"
    assert len(p["_events"])==1 and p["assumed_pnl"]<0
    S.audit_position(p)


def test_lock_is_causal_monotonic_and_native_floor_still_applies():
    x=toy([5,5,8,7,7])
    p=S.simulate(x,(0,"X","TEST"),S.FIXED["E011"],manager_override=lock40)
    assert p["stop"]>=6.4
    # Unseen future extension cannot affect the earlier stop decision.
    y=toy([5,5,8,7,100])
    q=S.simulate(y,(0,"X","TEST"),S.FIXED["E011"],manager_override=lock40)
    assert p["_events"][:1]==q["_events"][:1]


def test_stop_precedes_bank_on_a_gap():
    x=toy([5,5,20,1,1])
    p=S.simulate(x,(0,"X","TEST"),S.FIXED["E011"])
    assert p["_events"][-1]["action"]=="TRAIL"
    S.audit_position(p)


def test_exit_arms_have_identical_entries_and_fees_are_reconciled():
    x=toy([5,5,15,12,8,4,1,1])
    rows=[S.simulate(x,(0,"X","TEST"),S.FIXED[a]) for a in ("E01","E011","E011R","E011_S20")]
    assert len({(p["entry_ts"],p["lots"],p["entry_price"]) for p in rows})==1
    for p in rows:S.audit_position(p)


def test_pre2025_and_seen_windows_remain_separate():
    assert S.window("NIFTY","2026-09-22")=="seen"
    assert S.window("SENSEX","2026-09-24")=="validation"
    assert S.window("NIFTY","2025-11-04")=="test2025"


def test_minute_confirmation_is_explicit_and_restores_native_clock():
    import minutes as m
    x=toy([5]*33)
    x.now=[datetime(2026,1,6,13,0,tzinfo=S.EP.IST)+timedelta(minutes=i) for i in range(33)]
    x.clock=[t.time() for t in x.now]
    x.spot=[100.]*30+[102.]*3;x.fut=list(x.spot);x.anchor=list(x.spot)
    x._signals={}
    native=S.EP.CONFIRM_MAX_GAP_SEC
    state,fire=m.signals(x)
    assert fire==[(31,"UP")]
    assert state["box"]["n"]==30
    assert S.EP.CONFIRM_MAX_GAP_SEC==native==25.
