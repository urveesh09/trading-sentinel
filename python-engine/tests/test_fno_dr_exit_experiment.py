"""R1: evidence-bound defined-risk exit experiment.

Economics come from a real ``build_debit_spread`` structure persisted as a
bound ``fno_dr_positions`` row; quotes are genuine collector events built by
``research_quote_collector.normalise_quote``.
"""
from __future__ import annotations

import ast
import json
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import fno_dr_exit_experiment as dr
from fno_defined_risk import build_debit_spread, structure_round_trip_cost
from fno_models import Contract, FnoDirection, OptionType
from research_quote_collector import normalise_quote

IST = ZoneInfo("Asia/Kolkata")
OPENED = datetime(2026, 10, 1, 10, 0, tzinfo=IST)
LONG_TOKEN, SHORT_TOKEN = 501, 502
SYMBOLS = {LONG_TOKEN: "NIFTY26OCT25000CE", SHORT_TOKEN: "NIFTY26OCT25100CE"}
EARLY, LATE = datetime(2026, 9, 1, tzinfo=timezone.utc), datetime(2026, 10, 5, tzinfo=timezone.utc)


def _structure():
    prices = {25000.0: 120.0, 25100.0: 60.0}
    return build_debit_spread(FnoDirection.LONG, 25000.0, 50.0, 2,
                              lambda _opt, strike: prices.get(float(strike)), 65)


def _row(**changes):
    s = _structure()
    legs = []
    for leg, token in zip(s.legs, (LONG_TOKEN, SHORT_TOKEN)):
        legs.append({"opt_type": leg.opt_type.value, "strike": leg.strike, "quantity": leg.quantity,
                     "premium": leg.premium, "contract": {
                         "underlying": "NIFTY", "expiry": "2026-10-08", "exchange": "NFO", "token": token,
                         "tradingsymbol": SYMBOLS[token], "lot_size": 65, "instrument_type": "CE"}})
    row = {"id": 7, "source": "FNO_PAPER", "kind": "DEBIT_SPREAD",
           "legs_json": json.dumps(legs, separators=(",", ":"), sort_keys=True), "lot_size": 65, "lots": 1,
           "net_premium_rs": round(s.net_premium * 65, 2), "max_profit_rs": s.max_profit_rs,
           "max_loss_rs": s.max_loss_rs, "entry_cost_rs": structure_round_trip_cost(s),
           "opened_at": OPENED.isoformat()}
    row.update(changes)
    return row


def _entry(settlement=None, **changes):
    return dr.verify_entry(dr.entry_envelope(_row(**changes)), settlement)


def _event(token, minute, mid, *, lag=0, symbol=None, bid=True):
    at = OPENED + timedelta(minutes=minute)
    contract = Contract(token, symbol or SYMBOLS[token], "NIFTY", date(2026, 10, 8),
                        25000.0 if token == LONG_TOKEN else 25100.0, "CE", 65)
    raw = {"instrument_token": token, "last_price": mid, "timestamp": (at - timedelta(seconds=lag)).isoformat(),
           "depth": {"buy": [{"price": round(mid - 0.5, 2), "quantity": 650, "orders": 3}] if bid else [],
                     "sell": [{"price": round(mid + 0.5, 2), "quantity": 650, "orders": 3}]}}
    return normalise_quote(contract, raw, source="KITE", mode="KITE_REST_FULL_LOWER_FREQUENCY",
                           received_at=at, selection_reason="fixture", exchange="NFO")


def _events(long_mid, short_mid, *, end_minute=311, **kwargs):
    rows = []
    for minute in range(1, end_minute + 1):
        rows.append(_event(LONG_TOKEN, minute, long_mid(minute), **kwargs))
        rows.append(_event(SHORT_TOKEN, minute, short_mid(minute), **kwargs))
    return rows


def _rally(minute):   # spread value rises to ~95 (target 50% of max profit) by minute 30, then fades
    if minute <= 30:
        return 120.0 + minute * 1.5, 60.0 + minute * 0.3
    return 165.0 - (minute - 30) * 0.4 if minute < 120 else 129.0, 69.0


def _observations(entry, events, gap=180):
    return dr.observations_from_archive(events, entry, max_age_seconds=gap)


def test_entry_economics_rederive_from_bound_legs():
    entry = _entry()
    assert entry.leg_tokens == (LONG_TOKEN, SHORT_TOKEN) and entry.max_loss > 0
    for change, message in (({"max_loss_rs": 999.0}, "max_loss_rs"), ({"max_profit_rs": 1.0}, "max_profit_rs"),
                            ({"net_premium_rs": -1.0}, "net_premium_rs"), ({"entry_cost_rs": 1.0}, "entry_cost_rs")):
        with pytest.raises(dr.DrStudyError, match=message):
            _entry(**change)


def test_single_leg_duplicate_token_and_non_finite_rows_are_rejected():
    row = _row()
    legs = json.loads(row["legs_json"])
    with pytest.raises(dr.DrStudyError, match="two legs"):
        dr.verify_entry(dr.entry_envelope({**row, "legs_json": json.dumps(legs[:1])}))
    duplicate = [legs[0], {**legs[1], "contract": {**legs[1]["contract"], "token": LONG_TOKEN}}]
    with pytest.raises(dr.DrStudyError):
        dr.verify_entry(dr.entry_envelope({**row, "legs_json": json.dumps(duplicate)}))
    with pytest.raises(dr.DrStudyError, match="non-finite"):
        dr.entry_envelope({**row, "max_loss_rs": math.nan})
    with pytest.raises(dr.DrStudyError, match="legacy or invalid"):
        dr.entry_envelope({**row, "legs_json": json.dumps([{k: v for k, v in leg.items() if k != "contract"} for leg in legs])})


def test_baseline_replays_live_target_and_candidate_holds_then_gives_back():
    entry = _entry()
    observations, excluded = _observations(entry, _events(lambda m: _rally(m)[0], lambda m: _rally(m)[1]))
    assert excluded == {}
    base = dr.simulate(entry, observations, dr.BASELINE, max_gap_seconds=180)
    cand = dr.simulate(entry, observations, dr.TRAIL, max_gap_seconds=180)
    assert base["status"] == "CLOSED" and base["reason"] == "target"
    # Settlement uses executable prices: sell the long at bid, buy back the short at ask.
    exit_minute = int((datetime.fromisoformat(base["exit_at"]) - OPENED).total_seconds() // 60)
    long_mid, short_mid = _rally(exit_minute)
    assert base["gross_pnl"] == pytest.approx(((long_mid - 0.5 - 120.0) - (short_mid + 0.5 - 60.0)) * 65)
    assert base["costs"] == entry.entry_cost
    assert cand["reason"] == "trail_giveback" and cand["target_hold_activated"] is True


def test_unpriced_squareoff_is_unresolved_not_invented():
    entry = _entry()
    events = _events(lambda m: 121.0, lambda m: 60.5, end_minute=309)
    # At square-off the long leg has no bid: executable cash cannot be priced.
    events += [_event(LONG_TOKEN, 310, 121.0, bid=False), _event(SHORT_TOKEN, 310, 60.5)]
    observations, _ = _observations(entry, events)
    result = dr.simulate(entry, observations, dr.BASELINE, max_gap_seconds=180)
    assert (result["status"], result["reason"]) == ("UNRESOLVED", "squareoff_unpriced")
    assert datetime.fromisoformat(result["at"]) == OPENED + timedelta(minutes=310)
    assert "net_pnl" not in result


def test_stale_foreign_and_partial_receipts_are_never_used():
    entry = _entry()
    stale = _events(lambda m: 121.0, lambda m: 60.5, end_minute=3, lag=600)
    observations, excluded = _observations(entry, stale)
    assert observations == [] and excluded == {"provider_quote_older_than_declared_maximum": 3}
    from momentum_exit_study import ExitStudyError
    with pytest.raises(ExitStudyError, match="identity"):
        _observations(entry, [_event(LONG_TOKEN, 1, 121.0, symbol="NIFTY26OCT25050CE"), _event(SHORT_TOKEN, 1, 60.5)])
    only_long = [_event(LONG_TOKEN, 1, 121.0)]
    assert _observations(entry, only_long)[0] == []


def test_paired_deltas_use_only_baselines_reconciled_to_ledger_cash():
    events = _events(lambda m: _rally(m)[0], lambda m: _rally(m)[1])
    probe = _entry()
    replay = dr.simulate(probe, _observations(probe, events)[0], dr.BASELINE, max_gap_seconds=180)
    settled = {"status": "CLOSED", "settlement_state": "SETTLED", "exit_reason": "target",
               "position_net_pnl": replay["net_pnl"], "ledger_net_pnl": replay["net_pnl"]}
    good = _entry(settled)
    bad = _entry({**settled, "ledger_net_pnl": replay["net_pnl"] + 500.0}, id=8)
    manifest = dr.freeze_manifest(experiment_id="r1", frozen_at=EARLY)
    report = dr.build_report([(good, _observations(good, events)[0], {}),
                              (bad, _observations(bad, events)[0], {})], manifest)
    states = {pair["position_ref"]: pair["reconciliation"]["state"] for pair in report["pairs"]}
    assert states == {"fno_dr_positions:7": "RECONCILED", "fno_dr_positions:8": "LEDGER_MISMATCH_OR_MISSING"}
    assert report["holdout"]["reconciled_usable"] == 1 and report["holdout"]["paired"]["complete_pairs"] == 1


def test_manifest_drift_duplicates_and_development_are_refused_or_labelled(monkeypatch):
    from config import settings
    entry = _entry()
    observations = _observations(entry, _events(lambda m: 121.0, lambda m: 60.5))[0]
    manifest = dr.freeze_manifest(experiment_id="r1", frozen_at=LATE)
    report = dr.build_report([(entry, observations, {})], manifest)
    assert report["pairs"][0]["sample_class"] == "DEVELOPMENT"
    with pytest.raises(dr.DrStudyError, match="duplicate entry"):
        dr.build_report([(entry, observations, {}), (entry, observations, {})], manifest)
    tampered = json.loads(json.dumps(manifest))
    tampered["candidate_parameters"]["trail_giveback_fraction_of_max_profit"] = 0.9
    with pytest.raises(dr.DrStudyError, match="candidate_parameters"):
        dr.build_report([], tampered)
    monkeypatch.setattr(settings, "FNO_BROKERAGE_FLAT", float(settings.FNO_BROKERAGE_FLAT) + 1)
    with pytest.raises(dr.DrStudyError, match="cost_schedule"):
        dr.build_report([], manifest)


def test_entries_are_read_from_persisted_rows_and_ledger(tmp_path):
    db = tmp_path / "engine.db"
    with sqlite3.connect(db) as con:
        from fno_dr_book import _DDL
        con.executescript(_DDL)
        con.execute("CREATE TABLE bankroll_ledger (origin_ref TEXT, pnl REAL)")
        row = _row()
        con.execute("INSERT INTO fno_dr_positions (id,source,kind,legs_json,lot_size,lots,net_premium_rs,max_profit_rs,"
                    "max_loss_rs,entry_cost_rs,status,opened_at,exit_reason,pnl,settlement_state) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,'CLOSED',?,'target',123.0,'SETTLED')",
                    (row["id"], row["source"], row["kind"], row["legs_json"], 65, 1, row["net_premium_rs"],
                     row["max_profit_rs"], row["max_loss_rs"], row["entry_cost_rs"], row["opened_at"]))
        con.execute("INSERT INTO fno_dr_positions (id,source,kind,legs_json,lot_size,status,opened_at) "
                    "VALUES (9,'FNO_PAPER','DEBIT_SPREAD','[{\"opt_type\":\"CE\",\"strike\":1,\"quantity\":1,\"premium\":1}]',65,'CLOSED',?)",
                    (row["opened_at"],))
        con.execute("INSERT INTO bankroll_ledger VALUES ('fno_dr_structure:7', 123.0)")
    before = db.read_bytes()
    entries, unavailable = dr.entries_from_db(str(db))
    assert db.read_bytes() == before
    assert [e.position_ref for e in entries] == ["fno_dr_positions:7"]
    assert entries[0].settlement["ledger_net_pnl"] == 123.0
    assert unavailable[0]["position_ref"] == "fno_dr_positions:9"


def test_no_runtime_caller_and_read_only_sqlite():
    root = Path(dr.__file__).resolve().parent
    source = (root / "fno_dr_exit_experiment.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert not imported & {"aiosqlite", "httpx", "kite_client", "main", "fno_executor", "fno_orchestrator"}
    assert source.count("sqlite3.connect(") == source.count('?mode=ro", uri=True)')
    callers = []
    for path in root.glob("*.py"):
        if path.name == "fno_dr_exit_experiment.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        names = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        if "fno_dr_exit_experiment" in names:
            callers.append(path.name)
    assert callers == []
