import ast
from datetime import datetime, timedelta
import inspect
import json
import sqlite3

import pytest

import momentum_paper_evidence_review as review


SOURCE_REF = "sha256:" + ("b" * 64)


def _db(path, *, key="entry:key-1", ticker="ACME", outcome="opened", closed=True):
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE momentum_paper_admission_outcomes (
            admission_key TEXT, signal_key TEXT, ticker TEXT, outcome TEXT, recorded_at TEXT
        );
        CREATE TABLE positions (
            paper_admission_key TEXT, ticker TEXT, entry_date TEXT, exit_date TEXT,
            status TEXT, entry_price REAL, shares INTEGER, initial_capital_at_risk REAL,
            realised_pnl REAL, r_multiple REAL, source TEXT
        );
        CREATE TABLE bankroll_ledger (
            origin_ref TEXT, event_type TEXT, pnl REAL, timestamp TEXT, source TEXT
        );
    """)
    con.execute("INSERT INTO momentum_paper_admission_outcomes VALUES (?,?,?,?,?)",
                (key, "signal-1", ticker, outcome, "2026-09-25T04:30:00+00:00"))
    if outcome == "opened":
        con.execute("INSERT INTO positions VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            key, ticker, "2026-09-25T10:00:00+05:30",
            "2026-09-25T15:15:00+05:30" if closed else None,
            "CLOSED" if closed else "OPEN", 100.0, 10, 20.0, 20.0, 1.0, "MOMENTUM_PAPER",
        ))
        if closed:
            con.execute("INSERT INTO bankroll_ledger VALUES (?,?,?,?,?)", (
                key, "TRADE_CLOSED", 20.0, "2026-09-25T15:15:00+05:30", "MOMENTUM_PAPER",
            ))
    con.commit()
    con.close()


def _input(tmp_path, entries):
    start = datetime.fromisoformat("2026-09-25T10:00:00+05:30")
    deadline = datetime.fromisoformat("2026-09-25T15:15:00+05:30")
    quotes = []
    clock = start
    while clock <= deadline:
        for entry in entries:
            quotes.append({"entry_id": entry["entry_id"], "observed_at": clock.isoformat(),
                           "ltp": 104.0 if clock >= start + timedelta(minutes=1) else 100.0})
        clock += timedelta(minutes=1)
    packet = {"schema": "momentum_exit_study_input_v1", "study_id": "evidence-review",
              "max_quote_gap_seconds": 60, "entries": entries, "quotes": quotes}
    path = tmp_path / "study-input.json"
    path.write_text(json.dumps(packet, separators=(",", ":")), encoding="utf-8")
    return path


def _entry(*, key="entry:key-1", ticker="ACME", entry_id="study-1"):
    row = {"entry_id": entry_id, "source_ref": SOURCE_REF, "ticker": ticker,
           "entry_at": "2026-09-25T10:00:00+05:30", "entry_price": 100.0,
           "stop_loss_initial": 98.0, "target_1": 104.0, "shares": 10}
    if key is not None:
        row["admission_key"] = key
    return row


def test_exact_key_binds_complete_path_to_matched_closed_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr("momentum_exit_study.settings.MOMENTUM_USE_SCALE_OUT", False)
    db = tmp_path / "paper.db"; _db(db)
    result = review.build_momentum_paper_evidence_review(str(db), str(_input(tmp_path, [_entry()])))

    assert result["status"] == "COMPLETE"
    assert result["qualification"] == "NOT_ASSESSED"
    assert result["authority"]["can_place_orders"] is False
    assert result["pairs"][0]["state"] == "COMPLETE"
    assert result["pairs"][0]["lifecycle"]["cash"]["state"] == "MATCH"
    assert result["summary"]["paired_delta_count"] == 1


def test_same_ticker_cannot_bind_when_opaque_admission_key_differs(tmp_path, monkeypatch):
    monkeypatch.setattr("momentum_exit_study.settings.MOMENTUM_USE_SCALE_OUT", False)
    db = tmp_path / "paper.db"; _db(db, key="entry:actual", ticker="ACME")
    result = review.build_momentum_paper_evidence_review(str(db), str(_input(tmp_path, [_entry(key="entry:wrong")])))
    assert result["status"] == "PARTIAL"
    assert result["pairs"][0]["state"] == "UNRESOLVED_ADMISSION_NOT_FOUND"
    assert result["summary"]["paired_delta_count"] == 0


def test_legacy_exit_packet_without_key_is_unavailable_not_guessed(tmp_path, monkeypatch):
    monkeypatch.setattr("momentum_exit_study.settings.MOMENTUM_USE_SCALE_OUT", False)
    db = tmp_path / "paper.db"; _db(db)
    result = review.build_momentum_paper_evidence_review(str(db), str(_input(tmp_path, [_entry(key=None)])))
    assert result["pairs"][0]["state"] == "UNAVAILABLE_ADMISSION_KEY_MISSING"


def test_duplicate_packet_key_and_ticker_mismatch_remain_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr("momentum_exit_study.settings.MOMENTUM_USE_SCALE_OUT", False)
    db = tmp_path / "paper.db"; _db(db)
    duplicate = review.build_momentum_paper_evidence_review(str(db), str(_input(tmp_path, [
        _entry(entry_id="one"), _entry(entry_id="two"),
    ])))
    assert {row["state"] for row in duplicate["pairs"]} == {"UNRESOLVED_DUPLICATE_ADMISSION_KEY"}

    mismatch = review.build_momentum_paper_evidence_review(str(db), str(_input(tmp_path, [
        _entry(ticker="OTHER"),
    ])))
    assert mismatch["pairs"][0]["state"] == "UNRESOLVED_TICKER_MISMATCH"


def test_missing_database_stays_read_only_and_cli_prints_json(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("momentum_exit_study.settings.MOMENTUM_USE_SCALE_OUT", False)
    missing = tmp_path / "does-not-exist.db"
    input_path = _input(tmp_path, [_entry()])
    result = review.build_momentum_paper_evidence_review(str(missing), str(input_path))
    assert not missing.exists()
    assert result["pairs"][0]["state"] == "UNAVAILABLE_LIFECYCLE_AUDIT"
    assert review._main(["--db", str(missing), "--input", str(input_path)]) == 0
    assert json.loads(capsys.readouterr().out)["schema"] == review.SCHEMA


def test_exit_study_rejects_invalid_optional_admission_key(tmp_path):
    entry = _entry(); entry["admission_key"] = "\n"
    with pytest.raises(review.MomentumPaperEvidenceReviewError, match="admission_key"):
        review.build_momentum_paper_evidence_review(str(tmp_path / "missing.db"), str(_input(tmp_path, [entry])))


def test_review_module_has_no_runtime_order_network_or_message_dependencies():
    tree = ast.parse(inspect.getsource(review))
    imports, names = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    assert not (imports & {"httpx", "requests", "aiosqlite", "kite", "fno_executor"})
    assert not (names & {"place_order", "modify_order", "cancel_order", "post", "put", "delete"})
