"""S6b step 2: frozen read-only single-leg F&O exit experiments."""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

import fno_exit_experiment as fx
from config import settings
from fno_costs import calc_fno_costs
from momentum_exit_study import ExitStudyError

ENTRY = datetime.fromisoformat("2026-09-25T10:00:00+05:30")
HARD_FLAT = datetime.fromisoformat("2026-09-25T15:10:00+05:30")
BEFORE = datetime(2026, 9, 1, tzinfo=timezone.utc)
AFTER = datetime(2026, 9, 30, tzinfo=timezone.utc)
SOURCE_REF = "sha256:" + "c" * 64


def _entry(**changes):
    entry = {
        "entry_id": "pos-1", "position_ref": "1", "source_ref": SOURCE_REF,
        "tradingsymbol": "NIFTY26SEP25000CE", "option_token": 501, "direction": "LONG",
        "quantity": 150, "lot_size": 75, "entry_time": ENTRY.isoformat(),
        "entry_premium": 100.0, "entry_underlying": 25000.0, "stop_underlying": 24970.0,
        "target_underlying": 25054.0, "premium_stop": 75.0, "atr_at_entry": 20.0,
    }
    entry.update(changes)
    return entry


def _observations(fut_at, basis_at, *, end=HARD_FLAT, step=60, entry_id="pos-1"):
    rows, current = [], ENTRY + timedelta(seconds=step)
    while current <= end:
        minute = (current - ENTRY).total_seconds() / 60.0
        rows.append({"entry_id": entry_id, "observed_at": current.isoformat(),
                     "fut_price": fut_at(minute), "exit_basis": basis_at(minute)})
        current += timedelta(seconds=step)
    return rows


def _run(tmp_path, observations, *, candidate=fx.PARTIAL_POLICY, frozen_at=BEFORE, **entry_changes):
    packet = {"schema": fx.INPUT_SCHEMA, "study_id": "s6b", "max_observation_gap_seconds": 120,
              "entries": [_entry(**entry_changes)], "observations": observations}
    path = tmp_path / f"packet-{len(list(tmp_path.iterdir()))}.json"
    path.write_text(json.dumps(packet), encoding="utf-8")
    manifest = fx.freeze_manifest(experiment_id="s6b", candidate_policy=candidate, frozen_at=frozen_at)
    return fx.build_fno_exit_experiment(path, manifest)


def _runner(minute):
    """Target (25054) reached at minute 18; best 25080 by 30; retrace to 25055."""
    if minute <= 30:
        return 25000.0 + minute * 3.0 * (80 / 90)
    return 25080.0 if minute <= 40 else 25055.0


def _runner_basis(minute):
    return 100.0 + (_runner(minute) - 25000.0) * 0.5


def test_baseline_replays_live_ladder_with_paper_fill_costs_and_live_r(tmp_path):
    pair = _run(tmp_path, _observations(_runner, _runner_basis))["pairs"][0]
    baseline = pair["baseline"]
    assert baseline["reason"] == "trail_stop"
    # Trail = best (25080) - FNO_TRAIL_ATR_MULT x ATR = 25060; 25055 breaches it.
    leg = baseline["legs"][0]
    assert leg["quantity"] == 150 and leg["exit_price"] == pytest.approx(_runner_basis(41))
    expected_net = (leg["exit_price"] - 100.0) * 150 - calc_fno_costs(100.0, leg["exit_price"], 150)
    assert baseline["net_pnl"] == pytest.approx(expected_net, abs=1e-5)
    risk = 100.0 * settings.FNO_STOP_PREMIUM_PCT * 150
    assert baseline["r_multiple"] == pytest.approx(expected_net / risk, abs=1e-6)


def test_partial_at_target_banks_half_the_lots_then_follows_live_ladder(tmp_path):
    pair = _run(tmp_path, _observations(_runner, _runner_basis))["pairs"][0]
    candidate = pair["candidate"]
    assert [leg["reason"] for leg in candidate["legs"]] == ["partial_at_target", "trail_stop"]
    assert [leg["quantity"] for leg in candidate["legs"]] == [75, 75]
    assert candidate["exit_at"] == pair["baseline"]["exit_at"]


def test_partial_is_identical_to_baseline_for_a_single_lot(tmp_path):
    pair = _run(tmp_path, _observations(_runner, _runner_basis), quantity=75)["pairs"][0]
    assert pair["candidate"]["legs"] == pair["baseline"]["legs"]
    assert pair["candidate"]["net_pnl"] == pair["baseline"]["net_pnl"]


def _flat_then(after):
    """Flat underlying through the 45-minute time stop with a losing premium."""
    return lambda minute: 25001.0 if minute <= 50 else after(minute)


def test_confirmed_time_extension_reaches_the_later_continuation(tmp_path):
    fut = _flat_then(lambda minute: min(25001.0 + (minute - 50) * 2.0, 25120.0))
    basis = lambda minute: 95.0 if minute <= 50 else 95.0 + (fut(minute) - 25001.0) * 0.5
    pair = _run(tmp_path, _observations(fut, basis), candidate=fx.EXTENSION_POLICY)["pairs"][0]
    assert pair["baseline"]["reason"] == "time_stop"
    assert pair["candidate"]["exits_replaced"][0]["exit_replaced"] == "time_stop"
    assert pair["candidate"]["net_pnl"] > pair["baseline"]["net_pnl"]


def test_extension_exits_when_confirmation_fails_and_is_reported_worse(tmp_path):
    fut = _flat_then(lambda minute: 25001.0 if minute < 60 else 24990.0)
    basis = lambda minute: 95.0 if minute < 60 else 88.0
    report = _run(tmp_path, _observations(fut, basis), candidate=fx.EXTENSION_POLICY)
    pair = report["pairs"][0]
    assert pair["candidate"]["reason"] == "time_stop"
    assert pair["candidate"]["exit_at"] == (ENTRY + timedelta(minutes=60)).isoformat()
    assert pair["candidate"]["net_pnl"] < pair["baseline"]["net_pnl"]
    assert report["summary"]["all"]["paired"]["candidate_worse"] == 1


def test_exit_without_a_positive_basis_is_unresolved_not_priced(tmp_path):
    fut = lambda minute: 25000.0 if minute < 10 else 24960.0   # underlying stop
    basis = lambda minute: 100.0 if minute < 10 else 0.0
    pair = _run(tmp_path, _observations(fut, basis))["pairs"][0]
    assert pair["baseline"]["status"] == "UNRESOLVED"
    assert pair["baseline"]["reason"] == "exit_basis_unavailable"
    assert pair["baseline"]["attempted_exit"] == "underlying_stop"


@pytest.mark.parametrize("mutate, reason", [
    (lambda rows: [r for i, r in enumerate(rows) if i not in (20, 21)], "observation_gap_exceeds_declared_maximum"),
    (lambda rows: rows[:100], "no_observation_at_or_after_hard_flat"),
    (lambda rows: rows[3:], "initial_observation_gap_exceeds_declared_maximum"),
])
def test_incomplete_paths_are_insufficient_evidence(tmp_path, mutate, reason):
    rows = mutate(_observations(lambda m: 25001.0, lambda m: 101.0))
    pair = _run(tmp_path, rows)["pairs"][0]
    assert pair["status"] == "INSUFFICIENT_EVIDENCE" and pair["reason"] == reason


def test_later_observations_cannot_change_an_earlier_exit(tmp_path):
    first = _run(tmp_path, _observations(_runner, _runner_basis))["pairs"][0]
    altered = _observations(lambda m: _runner(m) if m <= 41 else 26000.0,
                            lambda m: _runner_basis(m) if m <= 41 else 400.0)
    second = _run(tmp_path, altered)["pairs"][0]
    for side in ("baseline", "candidate"):
        assert first[side]["legs"] == second[side]["legs"]


def test_manifest_tamper_and_setting_drift_are_refused(tmp_path, monkeypatch):
    packet = tmp_path / "p.json"
    packet.write_text(json.dumps({"schema": fx.INPUT_SCHEMA, "study_id": "s", "max_observation_gap_seconds": 120,
                                  "entries": [_entry()], "observations": _observations(_runner, _runner_basis)}),
                      encoding="utf-8")
    manifest = fx.freeze_manifest(experiment_id="s6b", candidate_policy=fx.EXTENSION_POLICY, frozen_at=BEFORE)
    tampered = json.loads(json.dumps(manifest))
    tampered["candidate_parameters"]["max_pullback_from_best_r"] = 9.0
    with pytest.raises(ExitStudyError, match="candidate_parameters"):
        fx.build_fno_exit_experiment(packet, tampered)
    monkeypatch.setattr(settings, "FNO_TIME_STOP_MIN", 60)
    with pytest.raises(ExitStudyError, match="live_settings"):
        fx.build_fno_exit_experiment(packet, manifest)


def test_entries_before_freeze_are_development(tmp_path):
    report = _run(tmp_path, _observations(_runner, _runner_basis), frozen_at=AFTER)
    assert report["pairs"][0]["sample_class"] == "DEVELOPMENT"
    assert report["summary"]["holdout"]["pairs"] == 0


def test_freeze_parameters_do_not_alias_policy_and_cost_drift_is_refused(monkeypatch):
    manifest = fx.freeze_manifest(experiment_id="immutable", candidate_policy=fx.EXTENSION_POLICY)
    manifest["candidate_parameters"]["max_pullback_from_best_r"] = 99
    assert fx.CANDIDATE_POLICIES[fx.EXTENSION_POLICY]["max_pullback_from_best_r"] == 0.5
    with pytest.raises(ExitStudyError, match="candidate_parameters"):
        fx.verify_manifest(manifest)
    fresh = fx.freeze_manifest(experiment_id="rates", candidate_policy=fx.EXTENSION_POLICY)
    monkeypatch.setattr(settings, "FNO_BROKERAGE_FLAT", settings.FNO_BROKERAGE_FLAT + 1)
    with pytest.raises(ExitStudyError, match="cost_schedule"):
        fx.verify_manifest(fresh)


def _event(token, received, ltp, bid=None, *, symbol=None, provider_lag_sec=0):
    """A genuine archive event produced by the collector's own normaliser."""
    from datetime import date
    from fno_models import Contract
    from research_quote_collector import normalise_quote

    if isinstance(received, str):
        received = datetime.fromisoformat(received.replace("Z", "+00:00"))
    is_future = token == 999
    contract = Contract(token, symbol or ("NIFTYFUT" if is_future else "NIFTY26SEP25000CE"), "NIFTY",
                        date(2026, 9, 30), 0.0 if is_future else 25000.0, "FUT" if is_future else "CE", 75)
    raw = {"instrument_token": token, "last_price": ltp,
           "timestamp": (received - timedelta(seconds=provider_lag_sec)).isoformat(),
           "depth": {"buy": [{"price": bid, "quantity": 75, "orders": 1}] if bid else [],
                     "sell": [{"price": (bid or ltp) + 0.5, "quantity": 75, "orders": 1}]}}
    return normalise_quote(contract, raw, source="KITE", mode="KITE_REST_FULL_LOWER_FREQUENCY",
                           received_at=received, selection_reason="fixture", exchange="NFO")


T1, T2, T3 = (datetime(2026, 9, 25, 4, minute, tzinfo=timezone.utc) for minute in (31, 32, 33))


def test_archive_adapter_pairs_only_identical_receipts_and_uses_bid_then_ltp():
    events = [
        _event(999, T1, 25010.0), _event(501, T1, 102.0, bid=101.5),
        _event(999, T2, 25012.0), _event(501, T2, 103.0),
        _event(999, T3, 25013.0),                     # option missing: not paired
        _event(777, T3, 50.0),                        # foreign contract: ignored
    ]
    packet = fx.build_packet_from_archive_events(events, entry=_entry(), future_token=999, study_id="adapter")
    rows = packet["observations"]
    assert [(r["observed_at"], r["fut_price"], r["exit_basis"]) for r in rows] == [
        (events[0]["received_at_utc"], 25010.0, 101.5), (events[2]["received_at_utc"], 25012.0, 103.0)]
    again = fx.build_packet_from_archive_events(events, entry=_entry(), future_token=999, study_id="adapter")
    assert packet["entries"][0]["source_ref"] == again["entries"][0]["source_ref"]
    assert packet["provenance"]["verified_external_provenance"] is False


def test_archive_adapter_accepts_exact_duplicates_and_rejects_conflicts():
    base = [_event(999, T1, 25010.0), _event(501, T1, 102.0, bid=101.5)]
    duplicated = base + [dict(base[1])]
    assert len(fx.build_packet_from_archive_events(duplicated, entry=_entry(), future_token=999,
                                                   study_id="dup")["observations"]) == 1
    with pytest.raises(ExitStudyError, match="conflicting archive events"):
        fx.build_packet_from_archive_events(base + [_event(501, T1, 140.0, bid=139.5)], entry=_entry(),
                                            future_token=999, study_id="conflict")


@pytest.mark.parametrize("tamper, message", [
    (lambda e: e.update(ltp=999.0), "ltp column"),
    (lambda e: e["buy_depth"][0].update(price=150.0), "bid column"),
    (lambda e: e["raw_packet"].update(last_price=150.0), "raw_sha256"),
    (lambda e: e.pop("raw_packet"), "raw provider packet"),
])
def test_archive_adapter_rejects_columns_that_disagree_with_raw_bytes(tamper, message):
    option = _event(501, T1, 102.0, bid=101.5)
    tamper(option)
    with pytest.raises(ExitStudyError, match=message):
        fx.build_packet_from_archive_events([_event(999, T1, 25010.0), option], entry=_entry(),
                                            future_token=999, study_id="tamper")


def test_archive_adapter_rejects_foreign_option_identity():
    with pytest.raises(ExitStudyError, match="identity"):
        fx.build_packet_from_archive_events(
            [_event(999, T1, 25010.0), _event(501, T1, 102.0, bid=101.5, symbol="NIFTY26SEP25100CE")],
            entry=_entry(), future_token=999, study_id="identity")


def test_archive_adapter_excludes_stale_provider_quotes_and_counts_them():
    packet = fx.build_packet_from_archive_events(
        [_event(999, T1, 25010.0), _event(501, T1, 102.0, bid=101.5, provider_lag_sec=600),
         _event(999, T2, 25012.0), _event(501, T2, 103.0, bid=102.5)],
        entry=_entry(), future_token=999, study_id="stale", max_observation_gap_seconds=120)
    assert [row["exit_basis"] for row in packet["observations"]] == [102.5]
    assert packet["provenance"]["excluded_observations"] == {"provider_quote_older_than_declared_maximum": 1}


def test_split_cost_model_equals_round_trip_for_a_single_full_exit():
    import random
    rng = random.Random(7)
    for _ in range(500):
        premium, exit_price = rng.uniform(5, 400), rng.uniform(1, 600)
        qty = 75 * rng.randint(1, 6)
        entry = fx._entry(_entry(entry_premium=premium, premium_stop=premium * 0.75, quantity=qty))
        leg = fx._leg(entry, qty, exit_price, "x", ENTRY, include_entry_order=True)
        assert leg["costs"] == pytest.approx(calc_fno_costs(premium, exit_price, qty), abs=1e-6)


def test_partial_candidate_charges_the_entry_order_once(tmp_path):
    pair = _run(tmp_path, _observations(_runner, _runner_basis))["pairs"][0]
    legs = pair["candidate"]["legs"]
    entry = fx._entry(_entry())
    expected = (fx._side_cost(100.0, 150, side="BUY")
                + fx._side_cost(legs[0]["exit_price"], 75, side="SELL")
                + fx._side_cost(legs[1]["exit_price"], 75, side="SELL"))
    assert pair["candidate"]["costs"] == pytest.approx(expected, abs=1e-5)
    double_counted = (calc_fno_costs(100.0, legs[0]["exit_price"], 75)
                      + calc_fno_costs(100.0, legs[1]["exit_price"], 75))
    assert pair["candidate"]["costs"] < double_counted
    assert entry.quantity == 150


def test_cli_builds_packet_from_archive_and_evaluates_without_overwrite(tmp_path):
    day_dir = tmp_path / "archive" / "quotes" / "2026-09-25"
    day_dir.mkdir(parents=True)
    events = []
    current = ENTRY + timedelta(minutes=1)
    while current <= HARD_FLAT:
        stamp = current.astimezone(timezone.utc).isoformat()
        events += [_event(999, stamp, 25001.0), _event(501, stamp, 101.0, bid=100.5)]
        current += timedelta(minutes=1)
    (day_dir / "quotes.jsonl.open").write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    entry_file = tmp_path / "entry.json"
    entry_file.write_text(json.dumps(_entry()), encoding="utf-8")
    packet, manifest, report = tmp_path / "packet.json", tmp_path / "manifest.json", tmp_path / "report.json"
    assert fx._main(["build-packet", "--archive-root", str(tmp_path / "archive"), "--day", "2026-09-25",
                     "--entry", str(entry_file), "--future-token", "999", "--study-id", "cli",
                     "--output", str(packet)]) == 0
    assert fx._main(["freeze", "--experiment-id", "cli", "--candidate", fx.EXTENSION_POLICY,
                     "--output", str(manifest)]) == 0
    assert fx._main(["evaluate", "--manifest", str(manifest), "--input", str(packet),
                     "--output", str(report)]) == 0
    result = json.loads(report.read_text(encoding="utf-8"))
    assert result["pairs"][0]["status"] == "COMPLETE"
    with pytest.raises(SystemExit):
        fx._main(["evaluate", "--manifest", str(manifest), "--input", str(packet), "--output", str(report)])


def test_no_runtime_caller_or_side_effect_imports():
    root = Path(fx.__file__).resolve().parent
    tree = ast.parse((root / "fno_exit_experiment.py").read_text(encoding="utf-8"))
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert not imported & {"aiosqlite", "httpx", "kite_client", "main", "fno_executor",
                           "fno_orchestrator", "scheduler_setup", "fno_positions"}
    # sqlite3 is permitted only for read-only evidence binding.
    source = (root / "fno_exit_experiment.py").read_text(encoding="utf-8")
    assert source.count("sqlite3.connect(") == source.count("?mode=ro\", uri=True)")
    # Only inert research (the defined-risk experiment and the full-policy
    # replay) reuses the verified archive reader.
    assert _importers(root, "fno_exit_experiment") == ["fno_dr_exit_experiment.py", "fno_policy_replay.py"]
    # The shared metrics and pure ladder are imported only by research and the
    # (unchanged-behaviour) orchestrator, never the other way round.
    assert _importers(root, "exit_experiment_metrics") == ["fno_dr_exit_experiment.py", "fno_exit_experiment.py",
                                                          "momentum_exit_experiment.py"]


def _importers(root, module):
    """Engine modules that actually import ``module`` (AST, not text)."""
    found = []
    for path in sorted(root.glob("*.py")):
        if path.stem == module:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        names = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {
            alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        if module in names:
            found.append(path.name)
    return found


# [R1 2026-10-02] Both packets verified; entries bound to persisted evidence.
def test_stale_futures_packet_next_to_fresh_option_is_excluded():
    packet = fx.build_packet_from_archive_events(
        [_event(999, T1, 25010.0, provider_lag_sec=600), _event(501, T1, 102.0, bid=101.5),
         _event(999, T2, 25012.0), _event(501, T2, 103.0, bid=102.5)],
        entry=_entry(), future_token=999, study_id="stale-future", max_observation_gap_seconds=120)
    assert [row["exit_basis"] for row in packet["observations"]] == [102.5]
    assert packet["provenance"]["excluded_observations"] == {"provider_quote_older_than_declared_maximum": 1}


def test_clock_column_must_be_rederived_from_raw_and_must_exist():
    option = _event(501, T1, 102.0, bid=101.5, provider_lag_sec=600)
    option["provider_timestamp_utc"] = option["received_at_utc"]  # a "fresh" column over stale bytes
    with pytest.raises(ExitStudyError, match="provider clock column"):
        fx.build_packet_from_archive_events([_event(999, T1, 25010.0), option], entry=_entry(),
                                            future_token=999, study_id="clock")
    future = _event(999, T1, 25010.0)
    del future["raw_packet"]["timestamp"]
    future["raw_sha256"] = fx._raw_digest(future["raw_packet"])
    future["provider_timestamp_utc"] = None
    packet = fx.build_packet_from_archive_events([future, _event(501, T1, 102.0, bid=101.5)], entry=_entry(),
                                                 future_token=999, study_id="no-clock")
    assert packet["observations"] == []
    assert packet["provenance"]["excluded_observations"] == {"provider_clock_unavailable": 1}


def _position_db(tmp_path, *, pnl, ledger_pnl, exit_reason="trail_stop"):
    import sqlite3
    from fno_positions import _DDL
    db = tmp_path / "positions.db"
    with sqlite3.connect(db) as con:
        con.executescript(_DDL)
        con.execute("CREATE TABLE IF NOT EXISTS bankroll_ledger (origin_ref TEXT, event_type TEXT, pnl REAL)")
        e = _entry()
        con.execute(
            "INSERT INTO fno_positions (id,source,tradingsymbol,token,direction,qty,lot_size,entry_time,entry_premium,"
            "entry_underlying,stop_underlying,target_underlying,premium_stop,atr_at_entry,status,exit_reason,pnl) "
            "VALUES (4,'FNO_PAPER',?,?,?,?,?,?,?,?,?,?,?,?,'CLOSED',?,?)",
            (e["tradingsymbol"], e["option_token"], e["direction"], e["quantity"], e["lot_size"], e["entry_time"],
             e["entry_premium"], e["entry_underlying"], e["stop_underlying"], e["target_underlying"],
             e["premium_stop"], e["atr_at_entry"], exit_reason, pnl))
        if ledger_pnl is not None:
            con.execute("INSERT INTO bankroll_ledger VALUES ('fno_position:4','TRADE_CLOSED',?)", (ledger_pnl,))
    return db


def test_entry_binds_to_position_row_and_baseline_reconciles_to_ledger(tmp_path):
    probe = _run(tmp_path, _observations(_runner, _runner_basis))["pairs"][0]["baseline"]
    db = _position_db(tmp_path, pnl=probe["net_pnl"], ledger_pnl=probe["net_pnl"])
    before = db.read_bytes()
    entry = fx.entry_from_position_row(str(db), 4)
    assert db.read_bytes() == before
    assert entry["evidence_kind"] == "FNO_POSITIONS_ROW" and entry["settlement"]["ledger_events"] == 1
    assert fx.reconcile_single_leg(entry, probe)["state"] == "RECONCILED"
    assert fx.reconcile_single_leg({**entry, "settlement": {**entry["settlement"], "ledger_net_pnl": 0.0}},
                                   probe)["state"] == "LEDGER_MISMATCH_OR_MISSING"
    assert fx.reconcile_single_leg(_entry(), probe) == {"state": "UNBOUND_CALLER_ENTRY", "usable": False}


def test_report_paired_reconciled_counts_only_bound_matching_entries(tmp_path):
    probe = _run(tmp_path, _observations(_runner, _runner_basis))["pairs"][0]["baseline"]
    db = _position_db(tmp_path, pnl=probe["net_pnl"], ledger_pnl=probe["net_pnl"])
    entry = fx.entry_from_position_row(str(db), 4)
    rows = _observations(_runner, _runner_basis, entry_id=entry["entry_id"])
    packet = {"schema": fx.INPUT_SCHEMA, "study_id": "bound", "max_observation_gap_seconds": 120,
              "entries": [{**entry, "source_ref": SOURCE_REF}], "observations": rows}
    path = tmp_path / "bound.json"
    path.write_text(json.dumps(packet), encoding="utf-8")
    manifest = fx.freeze_manifest(experiment_id="bound", candidate_policy=fx.PARTIAL_POLICY, frozen_at=BEFORE)
    report = fx.build_fno_exit_experiment(path, manifest)
    assert report["pairs"][0]["reconciliation"]["state"] == "RECONCILED"
    assert report["summary"]["holdout"]["reconciled_usable"] == 1
    unbound = _run(tmp_path, _observations(_runner, _runner_basis))
    assert unbound["summary"]["holdout"]["reconciled_usable"] == 0
    assert unbound["summary"]["holdout"]["paired_reconciled"] == {"complete_pairs": 0}
