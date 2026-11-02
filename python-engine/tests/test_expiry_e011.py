"""E01.1's paper shadows: exact copies of C's ticket, the frozen exits, and what must not change."""
from dataclasses import replace
import json
import sqlite3

import pytest

import expiry_paper as xp
from tests.test_expiry_paper import TUESDAY, _at, _book, _quote


@pytest.fixture
def saved_c(tmp_path, monkeypatch):
    monkeypatch.setattr(xp.settings, "EXPIRY_E01_SHADOW_ENABLED", True)
    monkeypatch.setattr(xp.settings, "EXPIRY_E011_SHADOW_ENABLED", True)
    book = _book()
    contract = next(c for c in book.by_symbol.values() if c.instrument_type == "CE")
    at = _at(TUESDAY, 13, 40)
    state = xp.new_day_state()
    with xp._store(str(tmp_path / "expiry.db")) as conn:
        main = xp._new_position(TUESDAY.isoformat(), "NIFTY", "C", "NFO", contract, 3.0, 10, at)
        xp._save_position(conn, main)
        state["trades"]["C"] = 1
        yield conn, state, main, contract, at


def _ticket(saved, play=xp.E011_PLAY):
    conn, state, main, contract, at = saved
    return {p["play"]: p for p in xp.copy_e011_entries(conn, state, main, contract, at)}[play]


def test_the_frozen_rules():
    c = xp.POLICIES["C"]
    e, r = xp.POLICIES[xp.E011_PLAY], xp.POLICIES[xp.E011R_PLAY]
    assert e.hard_stop == r.hard_stop == .25
    assert e.trails == r.trails == ((2.0, .60), (4.0, .60))
    assert e.bank_at == 2.0 and e.bank_mode == "recover"
    assert r.bank_at is None
    # Nothing else differs from C.
    assert replace(e, hard_stop=None, trails=c.trails, bank_mode="half") == c
    assert replace(r, hard_stop=None, trails=c.trails, bank_at=c.bank_at) == c
    assert xp.STRUCTURE_BACK[xp.E011_PLAY] == xp.STRUCTURE_BACK[xp.E011R_PLAY] == xp.STRUCTURE_BACK["C"]
    assert xp.PAIRED_WITH[xp.E011_PLAY] == xp.PAIRED_WITH[xp.E011R_PLAY] == "C"


def test_main_c_and_e01_keep_their_rules():
    assert xp.POLICIES["C"].hard_stop is None and xp.POLICIES["C"].bank_mode == "half"
    assert xp.POLICIES["C"].trails == ((4.0, .60),)
    assert xp.POLICIES[xp.E01_PLAY].hard_stop == .30 and xp.POLICIES[xp.E01_PLAY].bank_mode == "half"
    assert not set(xp.E011_PLAYS) & set(xp.MAIN_PLAYS)


def test_both_copy_the_saved_ticket_exactly(saved_c):
    conn, state, main, contract, at = saved_c
    copies = xp.copy_e011_entries(conn, state, main, contract, at)
    assert [c["play"] for c in copies] == [xp.E011_PLAY, xp.E011R_PLAY]
    for shadow in copies:
        for name in ("day", "underlying", "exchange", "symbol", "token", "lot_size", "lots", "entry_ts", "entry_price", "max_loss", "fee_snapshot"):
            assert shadow[name] == main[name]
        assert shadow["stop"] == 2.25
        events = json.loads(conn.execute("select events from expiry_paper_positions where id=?", (shadow["id"],)).fetchone()[0])
        assert events[0]["paired_primary_id"] == main["id"] and events[0]["e011_version"] == xp.E011_VERSION
    assert main["stop"] == 0


def test_a_second_copy_is_refused(saved_c):
    conn, state, main, contract, at = saved_c
    assert len(xp.copy_e011_entries(conn, state, main, contract, at)) == 2
    assert xp.copy_e011_entries(conn, state, main, contract, at) == []
    assert conn.execute("select count(*) from expiry_paper_positions").fetchone()[0] == 3


def test_a_wrong_contract_or_late_copy_is_refused(saved_c):
    conn, state, main, contract, at = saved_c
    assert xp.copy_e011_entries(conn, state, main, replace(contract, token=contract.token + 1), at) == []
    assert xp.copy_e011_entries(conn, state, main, contract, _at(TUESDAY, 13, 40, 10)) == []
    assert xp.copy_e011_entries(conn, state, {**main, "entry_price": 20.0}, contract, at) == []
    assert conn.execute("select count(*) from expiry_paper_positions").fetchone()[0] == 1
    assert state["refusals"][f"{xp.E011_PLAY}:TWIN_MISMATCH"] == 3


def test_off_blocks_copies_and_old_days_are_not_enrolled(saved_c, monkeypatch):
    conn, state, main, contract, at = saved_c
    monkeypatch.setattr(xp.settings, "EXPIRY_E011_SHADOW_ENABLED", False)
    assert xp.copy_e011_entries(conn, state, main, contract, at) == []
    monkeypatch.setattr(xp.settings, "EXPIRY_E011_SHADOW_ENABLED", True)
    state.pop("e011")
    xp._save_state(conn, TUESDAY.isoformat(), "NIFTY", state, at)
    loaded = xp._load_state(conn, TUESDAY.isoformat(), "NIFTY")
    assert loaded["e011"] == dict(version=None, enabled=False)
    assert xp.copy_e011_entries(conn, loaded, main, contract, at) == []


def test_mid_session_on_does_not_enroll_a_day_begun_off(monkeypatch):
    monkeypatch.setattr(xp.settings, "EXPIRY_E011_SHADOW_ENABLED", False)
    old = xp.new_day_state()
    monkeypatch.setattr(xp.settings, "EXPIRY_E011_SHADOW_ENABLED", True)
    assert not xp.e011_entry_enabled(old, xp.E011_PLAY)
    assert xp.e011_entry_enabled(xp.new_day_state(), xp.E011_PLAY)


def test_off_still_manages_an_open_leg(saved_c, monkeypatch):
    shadow = _ticket(saved_c)
    monkeypatch.setattr(xp.settings, "EXPIRY_E011_SHADOW_ENABLED", False)
    assert xp.manage_position(shadow, xp.POLICIES[xp.E011_PLAY], 2.2, _at(TUESDAY, 13, 41)) == (10, "STOP")


def test_a_failed_shadow_save_keeps_the_main_ticket(saved_c, monkeypatch):
    conn, state, main, contract, at = saved_c
    original = xp._save_position

    def fail(conn, pos):
        if pos["play"] == xp.E011_PLAY:
            raise sqlite3.OperationalError("injected")
        return original(conn, pos)
    monkeypatch.setattr(xp, "_save_position", fail)
    copies = xp.copy_e011_entries(conn, state, main, contract, at)
    assert [c["play"] for c in copies] == [xp.E011R_PLAY]             # the other shadow is unaffected
    assert state["trades"][xp.E011_PLAY] == 0 and state["refusals"][f"{xp.E011_PLAY}:SAVE_FAILED"] == 1
    assert conn.execute("select count(*) from expiry_paper_positions where play='C'").fetchone()[0] == 1


# --- the bank ------------------------------------------------------------------------------------------------------

def test_bank_sells_just_enough_to_take_the_cost_back(saved_c):
    shadow = _ticket(saved_c)
    at = _at(TUESDAY, 14, 0)
    assert xp.manage_position(shadow, xp.POLICIES[xp.E011_PLAY], 9.0, at) == (4, "BANK_HALF")
    assert shadow["banked"] == 1 and shadow["bank_pending"] == 4
    schedule = xp._position_schedule(shadow)
    paid = 3.0 * 650 + xp.buy_charges(3.0, 650, schedule)
    # Four lots cover it with every remaining lot's fee reserved. Three don't.
    assert 9.0 * 260 - xp.sell_charges(9.0, 260, schedule) - 6 * xp.order_fee(schedule) >= paid
    assert 9.0 * 195 - xp.sell_charges(9.0, 195, schedule) - 7 * xp.order_fee(schedule) < paid


def test_a_higher_price_sells_fewer_lots(saved_c):
    shadow = _ticket(saved_c)
    assert xp.cost_recovery_lots(shadow, 9.0) == 4
    assert xp.cost_recovery_lots(shadow, 20.0) == 2
    assert xp.cost_recovery_lots(shadow, 50.0) == 1


@pytest.mark.parametrize("lots,expected", [(1, 0), (2, 1), (3, 1)])
def test_small_tickets_fall_back_to_half(saved_c, lots, expected):
    shadow = {**_ticket(saved_c), "lots": lots, "lots_open": lots}
    assert xp.cost_recovery_lots(shadow, 3.1) == expected


def test_a_bank_on_a_one_lot_ticket_sells_nothing(saved_c):
    shadow = {**_ticket(saved_c), "lots": 1, "lots_open": 1}
    assert xp.manage_position(shadow, xp.POLICIES[xp.E011_PLAY], 9.0, _at(TUESDAY, 14, 0)) is None
    assert shadow["banked"] == 1 and shadow["bank_pending"] == 0


def test_unfilled_bank_lots_stay_pending_and_only_while_the_bid_holds(saved_c):
    shadow = _ticket(saved_c)
    at = _at(TUESDAY, 14, 0)
    action = xp.manage_position(shadow, xp.POLICIES[xp.E011_PLAY], 9.0, at)
    event = xp._try_exit(shadow, _quote([(9.0, 130)], "bids", at), *action, at)    # two of the four lots fill
    assert event["lots"] == 2 and shadow["bank_pending"] == 2 and shadow["lots_open"] == 8
    later = _at(TUESDAY, 14, 0, 10)
    assert xp.manage_position(shadow, xp.POLICIES[xp.E011_PLAY], 9.5, later) == (2, "BANK_HALF")
    # Under the bank level nothing more sells, and the floor still protects what's open.
    assert xp.manage_position(shadow, xp.POLICIES[xp.E011_PLAY], 8.5, _at(TUESDAY, 14, 0, 20)) is None


def test_the_no_bank_arm_never_sells_at_3x(saved_c):
    shadow = _ticket(saved_c, xp.E011R_PLAY)
    assert xp.manage_position(shadow, xp.POLICIES[xp.E011R_PLAY], 9.0, _at(TUESDAY, 14, 0)) is None
    assert shadow["banked"] == 0 and shadow["lots_open"] == 10


# --- the floor -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("play", xp.E011_PLAYS)
def test_the_floor_starts_at_3x(saved_c, play):
    shadow = _ticket(saved_c, play)
    policy = xp.POLICIES[play]
    assert xp.manage_position(shadow, policy, 8.9, _at(TUESDAY, 14, 0)) is None     # under 3x: only the 25% stop
    assert shadow["stop"] == 2.25
    xp.manage_position(shadow, policy, 9.0, _at(TUESDAY, 14, 1))
    assert shadow["stop"] == 5.4
    xp.manage_position(shadow, policy, 20.0, _at(TUESDAY, 14, 2))
    assert shadow["stop"] == 12.0


def test_c_itself_has_no_floor_there(saved_c):
    conn, state, main, contract, at = saved_c
    xp.manage_position(main, xp.POLICIES["C"], 14.0, _at(TUESDAY, 14, 0))           # 4.67x: under C's 5x trail
    assert main["stop"] == 0
    assert xp.manage_position(main, xp.POLICIES["C"], 3.0, _at(TUESDAY, 14, 1)) is None


@pytest.mark.parametrize("play", xp.E011_PLAYS)
def test_the_floor_sells_every_open_lot_and_a_gap_is_not_a_promise(saved_c, play):
    shadow = _ticket(saved_c, play)
    policy = xp.POLICIES[play]
    at = _at(TUESDAY, 14, 0)
    action = xp.manage_position(shadow, policy, 20.0, at)
    if action:
        xp._try_exit(shadow, _quote([(20.0, 6500)], "bids", at), *action, at)
    later = _at(TUESDAY, 14, 1)
    lots = shadow["lots_open"]
    assert xp.manage_position(shadow, policy, 11.0, later) == (lots, "TRAIL")       # stop 12, bid gapped to 11
    event = xp._try_exit(shadow, _quote([(11.0, 6500)], "bids", later), lots, "TRAIL", later)
    assert event["price"] == 11.0 and shadow["status"] == "CLOSED"


@pytest.mark.parametrize("play", xp.E011_PLAYS)
def test_a_failed_break_still_comes_before_the_bank(saved_c, play):
    shadow = _ticket(saved_c, play)
    assert xp.manage_position(shadow, xp.POLICIES[play], 9.0, _at(TUESDAY, 14, 0), structure_broken=True) == (10, "FAILED_BREAK")


@pytest.mark.parametrize("play", xp.E011_PLAYS)
def test_flat_time_sells_everything(saved_c, play):
    shadow = _ticket(saved_c, play)
    assert xp.manage_position(shadow, xp.POLICIES[play], 9.0, _at(TUESDAY, 15, 38)) == (10, "FLAT_TIME")


# --- pairing and the day's summary ---------------------------------------------------------------------------------

def _closed_pair(saved):
    conn, state, main, contract, at = saved
    copies = xp.copy_e011_entries(conn, state, main, contract, at)
    later = _at(TUESDAY, 13, 41)
    xp._sell(main, 10, 2.0, "FAILED_BREAK", later)
    xp._save_position(conn, main)
    for shadow in copies:
        xp._sell(shadow, 10, 2.2, "STOP", later)
        xp._save_position(conn, shadow)
    xp._save_state(conn, TUESDAY.isoformat(), "NIFTY", state, at)
    return conn, state, copies


def test_pairing_needs_the_parent_id_and_the_same_terms(saved_c):
    conn, state, copies = _closed_pair(saved_c)
    text = "\n".join(xp.paired_lines(conn, TUESDAY.isoformat(), "NIFTY"))
    assert "CE011-C today Rs +" in text and "CE011R-C today Rs +" in text
    raw = json.loads(conn.execute("select events from expiry_paper_positions where id=?", (copies[0]["id"],)).fetchone()[0])
    raw[0]["paired_primary_id"] += 1000
    conn.execute("update expiry_paper_positions set events=? where id=?", (json.dumps(raw), copies[0]["id"]))
    assert "1 not the same entry" in "\n".join(xp.paired_lines(conn, TUESDAY.isoformat(), "NIFTY"))


@pytest.mark.parametrize("parent", [True, False, 0, -1, "1", None, {}, []])
def test_a_malformed_parent_is_not_an_admission(parent):
    assert xp._e011_parent_id(json.dumps([dict(action="BUY", paired_primary_id=parent, e011_version=xp.E011_VERSION)])) is None


def test_another_versions_link_is_not_this_ones():
    assert xp._e011_parent_id(json.dumps([dict(action="BUY", paired_primary_id=1, e01_version=xp.E01_VERSION)])) is None
    assert xp._e01_parent_id(json.dumps([dict(action="BUY", paired_primary_id=1, e011_version=xp.E011_VERSION)])) is None


def test_the_summary_names_them_and_reports_an_unenrolled_day(saved_c):
    conn, state, _ = _closed_pair(saved_c)
    state["box"], state["box_status"] = dict(hi=23000.0, lo=22954.0, fut_hi=23010.0, fut_lo=22964.0, n=180), "READY"
    text = xp.format_day_summary(conn, TUESDAY.isoformat(), "NIFTY", state)
    assert "E01.1 shadows" in text and "box 20 bp, reading only" in text
    assert f"{xp.E011_PLAY}: filled net" in text and f"{xp.E011R_PLAY}: filled net" in text
    old = {**xp.new_day_state(), "e011": dict(version=None, enabled=False)}
    conn.execute("delete from expiry_paper_positions")
    text = xp.format_day_summary(conn, TUESDAY.isoformat(), "NIFTY", old)
    assert f"{xp.E011_PLAY}: not enrolled for this expiry" in text and f"{xp.E011R_PLAY}: not enrolled for this expiry" in text
    assert "E01.1 shadows" not in text
