"""E01 exact copying, bounded exits, durable parent binding and rollout safety."""
from dataclasses import replace
import json
import sqlite3

import pytest

import expiry_paper as xp
from tests.test_expiry_paper import _at, _book, _quote, TUESDAY


@pytest.fixture
def saved_c(tmp_path,monkeypatch):
    monkeypatch.setattr(xp.settings,"EXPIRY_E01_SHADOW_ENABLED",True)
    book=_book();contract=next(c for c in book.by_symbol.values() if c.instrument_type=="CE")
    at=_at(TUESDAY,13,40);state=xp.new_day_state()
    with xp._store(str(tmp_path/"expiry.db")) as conn:
        main=xp._new_position(TUESDAY.isoformat(),"NIFTY","C","NFO",contract,10.,2,at)
        xp._save_position(conn,main);state["trades"]["C"]=1
        yield conn,state,main,contract,at


def test_e01_policy_is_fixed_on_the_old_c():
    assert xp.E01_PREMIUM_STOP==.30 and xp.POLICIES[xp.E01_PLAY].hard_stop==.30
    assert xp.C_V3_POLICY.hard_stop is None
    assert replace(xp.POLICIES[xp.E01_PLAY],hard_stop=None)==xp.C_V3_POLICY
    assert xp.STRUCTURE_BACK[xp.E01_PLAY]==xp.STRUCTURE_BACK["C"]
    assert xp.PAIRED_WITH[xp.E01_PLAY]=="C" and xp.E01_PLAY not in xp.MAIN_PLAYS


def test_copy_binds_exact_saved_entry_and_cannot_duplicate(saved_c):
    conn,state,main,contract,at=saved_c
    shadow=xp.copy_e01_entry(conn,state,main,contract,at)
    for name in ("day","underlying","exchange","symbol","token","lot_size","lots","entry_ts","entry_price","max_loss","fee_snapshot"):
        assert shadow[name]==main[name]
    assert shadow["stop"]==7 and main["stop"]==7.5
    events=json.loads(conn.execute("select events from expiry_paper_positions where id=?",(shadow["id"],)).fetchone()[0])
    assert events[0]["paired_primary_id"]==main["id"] and events[0]["e01_version"]==xp.E01_VERSION
    assert xp.copy_e01_entry(conn,state,main,contract,at) is None
    assert conn.execute("select count(*) from expiry_paper_positions").fetchone()[0]==2


def test_wrong_contract_and_late_copy_are_refused(saved_c):
    conn,state,main,contract,at=saved_c
    assert xp.copy_e01_entry(conn,state,main,replace(contract,token=contract.token+1),at) is None
    assert xp.copy_e01_entry(conn,state,main,contract,_at(TUESDAY,13,40,10)) is None
    assert conn.execute("select count(*) from expiry_paper_positions").fetchone()[0]==1


def test_correct_id_cannot_hide_changed_saved_economics(saved_c):
    conn,state,main,contract,at=saved_c
    changed={**main,"entry_price":20.0}  # would exceed the full-ticket ceiling at two lots
    assert xp.copy_e01_entry(conn,state,changed,contract,at) is None
    assert xp.copy_e01_entry(conn,state,{**main,"id":main["id"]+1000},contract,at) is None
    assert conn.execute("select count(*) from expiry_paper_positions").fetchone()[0]==1


@pytest.mark.parametrize("parent",[True,False,0,-1,"1",None,{},[]])
def test_malformed_parent_identity_is_not_an_integer_admission(parent):
    assert xp._e01_parent_id(json.dumps([dict(action="BUY",paired_primary_id=parent,e01_version=xp.E01_VERSION)])) is None


def test_old_version_is_not_paired_into_the_new_version():
    assert xp._e01_parent_id(json.dumps([dict(action="BUY",paired_primary_id=1,e01_version="expiry-e01-v0")])) is None


def test_disable_blocks_new_entries_and_never_changes_main(saved_c,monkeypatch):
    conn,state,main,contract,at=saved_c
    monkeypatch.setattr(xp.settings,"EXPIRY_E01_SHADOW_ENABLED",False)
    assert xp.copy_e01_entry(conn,state,main,contract,at) is None
    assert main["stop"]==7.5 and state["trades"]["C"]==1


def test_old_day_is_not_enrolled_by_loading_new_code(saved_c):
    conn,state,main,contract,at=saved_c
    state.pop("e01")
    xp._save_state(conn,TUESDAY.isoformat(),"NIFTY",state,at)
    loaded=xp._load_state(conn,TUESDAY.isoformat(),"NIFTY")
    assert loaded["e01"]==dict(version=None,enabled=False)
    assert not xp.e01_entry_enabled(loaded)
    assert xp.copy_e01_entry(conn,loaded,main,contract,at) is None


def test_mid_session_enable_does_not_enroll_an_opted_out_day(monkeypatch):
    monkeypatch.setattr(xp.settings,"EXPIRY_E01_SHADOW_ENABLED",False)
    old=xp.new_day_state()
    monkeypatch.setattr(xp.settings,"EXPIRY_E01_SHADOW_ENABLED",True)
    assert not xp.e01_entry_enabled(old)
    assert xp.e01_entry_enabled(xp.new_day_state())


def test_open_shadow_still_exits_with_toggle_off_and_a_gap_is_not_breakeven(saved_c,monkeypatch):
    conn,state,main,contract,at=saved_c
    shadow=xp.copy_e01_entry(conn,state,main,contract,at)
    monkeypatch.setattr(xp.settings,"EXPIRY_E01_SHADOW_ENABLED",False)
    later=_at(TUESDAY,13,41)
    action=xp.manage_position(shadow,xp.POLICIES[xp.E01_PLAY],5,later)
    assert action==(2,"STOP")
    first=xp._try_exit(shadow,_quote([(5,65)],"bids",later),*action,later)
    assert first["lots"]==1 and first["price"]==5 and shadow["exit_pending"]=="STOP"
    # Latched exit persists even when the remaining lot's price rebounds.
    end=_at(TUESDAY,13,41,10)
    second=xp._try_exit(shadow,_quote([(9,65)],"bids",end),1,shadow["exit_pending"],end)
    assert second["price"]==9 and shadow["status"]=="CLOSED"
    assert shadow["net_pnl"]<0 and shadow["net_pnl"]>=-shadow["max_loss"]
    assert main["status"]=="OPEN" and main["stop"]==7.5


def test_missing_exit_depth_latches_without_inventing_a_fill(saved_c):
    conn,state,main,contract,at=saved_c
    shadow=xp.copy_e01_entry(conn,state,main,contract,at)
    assert xp._try_exit(shadow,None,2,"STOP",_at(TUESDAY,13,41)) is None
    assert shadow["lots_open"]==2 and shadow["exit_pending"]=="STOP"


def test_shadow_insert_failure_preserves_main_ticket(saved_c,monkeypatch):
    conn,state,main,contract,at=saved_c
    original=xp._save_position
    def fail(conn,pos):
        if pos["play"]==xp.E01_PLAY:raise sqlite3.OperationalError("injected optional shadow failure")
        return original(conn,pos)
    monkeypatch.setattr(xp,"_save_position",fail)
    assert xp.copy_e01_entry(conn,state,main,contract,at) is None
    assert conn.execute("select count(*) from expiry_paper_positions").fetchone()[0]==1
    assert state["trades"][xp.E01_PLAY]==0 and state["refusals"]["CE01:SAVE_FAILED"]==1


def test_pairing_requires_durable_parent_id_as_well_as_identical_economics(saved_c):
    conn,state,main,contract,at=saved_c
    shadow=xp.copy_e01_entry(conn,state,main,contract,at)
    later=_at(TUESDAY,13,41)
    xp._sell(main,2,6,"FAILED_BREAK",later);xp._save_position(conn,main)
    xp._sell(shadow,2,7,"STOP",later);xp._save_position(conn,shadow)
    xp._save_state(conn,TUESDAY.isoformat(),"NIFTY",state,at)
    assert "CE01-C today Rs +" in "\n".join(xp.paired_lines(conn,TUESDAY.isoformat(),"NIFTY"))
    raw=json.loads(conn.execute("select events from expiry_paper_positions where id=?",(shadow["id"],)).fetchone()[0])
    raw[0]["paired_primary_id"]=main["id"]+1000
    conn.execute("update expiry_paper_positions set events=? where id=?",(json.dumps(raw),shadow["id"]))
    assert "1 not the same entry" in "\n".join(xp.paired_lines(conn,TUESDAY.isoformat(),"NIFTY"))


@pytest.mark.parametrize("column,value",[("lot_size",999),("max_loss",1.0),("fee_snapshot","{}"),("token",999)])
def test_correct_parent_id_does_not_hide_mismatched_paired_terms(saved_c,column,value):
    conn,state,main,contract,at=saved_c
    shadow=xp.copy_e01_entry(conn,state,main,contract,at)
    later=_at(TUESDAY,13,41)
    xp._sell(main,2,6,"FAILED_BREAK",later);xp._save_position(conn,main)
    xp._sell(shadow,2,7,"STOP",later);xp._save_position(conn,shadow)
    xp._save_state(conn,TUESDAY.isoformat(),"NIFTY",state,at)
    assert "CE01-C today Rs +" in "\n".join(xp.paired_lines(conn,TUESDAY.isoformat(),"NIFTY"))
    conn.execute(f"UPDATE expiry_paper_positions SET {column}=? WHERE id=?",(value,shadow["id"]))
    assert "1 not the same entry" in "\n".join(xp.paired_lines(conn,TUESDAY.isoformat(),"NIFTY"))
