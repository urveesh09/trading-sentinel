"""Frozen shadow FNO_SPREAD_TILT_V1: the naked option's risk budget spent on spread lots."""
import json
import sqlite3
from datetime import datetime, timedelta

import fno_spread_tilt as tilt
from fno_spread_tilt import Single, Spread


def _t(day, hh, mm, ss=0):
    return datetime(2026, 10, day, hh, mm, ss)


def test_paired_signal_spends_the_naked_budget_on_spread_lots_capped_at_max():
    # Oct 9 shape: naked call max loss 7,475 and net -22.75; 1-lot spread max loss 2,811, net +565.84.
    single = Single(41, _t(9, 9, 50, 21), "CE", 7475.0, -22.75)
    spread = Spread(31, _t(9, 9, 50, 21), "CE", 1, 2811.0, 565.84)
    [o] = tilt.pair_and_score([single], [spread], max_lots=3)
    assert (o.single_id, o.spread_id, o.variant_lots) == (41, 31, 3)       # 1 + floor(7475/2811)=2 -> 3
    assert o.actual == -22.75 + 565.84 and abs(o.variant - 3 * 565.84) < 1e-9


def test_unpaired_vehicles_keep_their_actual_result_and_type_must_match():
    single = Single(1, _t(12, 10, 0), "PE", 13000.0, 4710.0)               # no spread that tick
    other = Single(2, _t(12, 11, 0), "CE", 9000.0, -500.0)
    spread = Spread(9, _t(12, 11, 0, 30), "PE", 1, 3000.0, 200.0)          # PE spread, CE naked: not a pair
    outcomes = tilt.pair_and_score([single, other], [spread], max_lots=3)
    assert all(o.actual == o.variant for o in outcomes) and len(outcomes) == 3
    assert not any(o.single_id and o.spread_id for o in outcomes)


def test_pair_window_and_lot_cap_respect_existing_limits():
    single = Single(1, _t(12, 10, 0), "CE", 1000.0, -100.0)                 # budget buys no extra lot
    spread = Spread(2, _t(12, 10, 0) + timedelta(seconds=90), "CE", 2, 6000.0, 300.0)
    [o] = tilt.pair_and_score([single], [spread], max_lots=3)
    assert o.variant_lots == 2 and o.variant == 300.0                       # never below actual lots
    late = Spread(3, _t(12, 10, 0) + timedelta(seconds=200), "CE", 1, 3000.0, 50.0)
    assert not any(o.single_id and o.spread_id for o in tilt.pair_and_score([single], [late], 3))


def test_report_scores_forward_only_and_reads_the_real_tables(tmp_path):
    db = str(tmp_path / "cache.db")
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE fno_positions (id INTEGER, source TEXT, entry_time TEXT, opt_type TEXT, "
                     "max_loss_rupees REAL, initial_max_loss_rupees REAL, pnl REAL, status TEXT)")
        conn.execute("CREATE TABLE fno_dr_positions (id INTEGER, source TEXT, kind TEXT, legs_json TEXT, "
                     "lots INTEGER, max_loss_rs REAL, pnl REAL, cash_pnl REAL, status TEXT, opened_at TEXT)")
        legs = json.dumps([{"opt_type": "CE", "strike": 22500, "quantity": 1, "premium": 114.95},
                           {"opt_type": "CE", "strike": 22600, "quantity": -1, "premium": 71.70}])
        for i, day in ((1, "2026-10-09"), (2, "2026-10-13")):               # one seen, one forward
            conn.execute("INSERT INTO fno_positions VALUES (?,?,?,?,?,?,?,?)",
                         (i, "FNO_PAPER", f"{day}T09:50:21+05:30", "CE", 7475.0, None, -22.75, "CLOSED"))
            conn.execute("INSERT INTO fno_dr_positions VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (i, "FNO_PAPER", "DEBIT_SPREAD", legs, 1, 2811.0, 585.34, 565.84, "CLOSED",
                          f"{day}T09:50:21+05:30"))
    report = tilt.spread_tilt_report(db)
    assert report["forward"]["paired"] == 1 and report["in_sample_context"]["paired"] == 1
    assert report["forward"]["paired_variant_net"] == round(3 * 565.84, 2)    # cash net, not model net
    assert report["can_place_orders"] is False
    assert "actual Rs +543 vs variant Rs +1,698" in tilt.report_line(report)
