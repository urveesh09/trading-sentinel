"""[WORKFLOW-F 2026-09-13] Reconciliation CLI acceptance.

Closes F5 (CLI portion) of workstream F per
``docs/2026-09-13-workflow-f-state-of-codebase-audit.md`` section 6
future plan and ``docs/NEXT_AGENT_PLAN.md`` section 10.

Acceptance coverage for ``python-engine/reconciliation_cli.py``.

[WHY-THIS-EXISTS 2026-09-13]
  Pre-fix, ``broker_reconciliation.import_broker_statement`` was a
  Python async function with no CLI surface and no FastAPI route.
  The operator had no way to ingest a real broker statement without
  writing Python. The F4 framework's ``record_current_state`` was
  never wired to the import path, so discrepancies never flowed in
  from real statements. F5 ships the offline CLI skeleton that
  imports a JSON payload, runs ``record_current_state`` as a side
  effect, and lists discrepancies via filtered queries.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict

import pytest
import pytest_asyncio

import reconciliation_cli
from reconciliation_cli import (
    _import_statement,
    _list_discrepancies,
    _parse_iso,
    _payload_to_import_kwargs,
    _run_report,
    _write_output_atomic,
    main,
)


# ---- fixtures ---------------------------------------------------------------

@pytest_asyncio.fixture
async def cli_db(tmp_path):
    """A fresh DB with bankroll_ledger + discrepancies tables."""
    from performance import init_ledger, record_trade_close
    from discrepancies import init_discrepancies_db
    db = str(tmp_path / "cli.db")
    await init_ledger(db)
    await init_discrepancies_db(db)
    # Seed a ledger row that will produce an evidence-report
    # discrepancy (origin_ref has no matching position).
    await record_trade_close(
        db, ticker="TCS", pnl=-50.0, source="PENNY_PAPER",
        origin_ref="fno_position:99999",
    )
    yield db


def _write_payload(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def _good_payload(account: str = "owner", statement: str = "2026-09-08") -> Dict[str, Any]:
    return {
        "account_id": account, "statement_id": statement,
        "as_of": "2026-09-08T00:00:00+00:00",
        "opening_cash": 1137.0, "closing_cash": 1100.0,
        "entries": [
            {"entry_id": "d", "entry_type": "DEPOSIT", "amount": 200},
            {"entry_id": "t", "entry_type": "TRADE_REALIZED", "amount": -40},
            {"entry_id": "c", "entry_type": "CHARGE", "amount": 8},
            {"entry_id": "o", "entry_type": "OPERATING_EXPENSE", "amount": 15},
        ],
        "fills": [],
    }


# ---- _parse_iso ------------------------------------------------------------

class TestParseIso:
    def test_accepts_zulu(self) -> None:
        dt = _parse_iso("2026-09-08T00:00:00Z", "as_of")
        assert dt.tzinfo is not None
        assert dt.year == 2026 and dt.month == 9 and dt.day == 8

    def test_accepts_offset(self) -> None:
        dt = _parse_iso("2026-09-08T05:30:00+05:30", "as_of")
        assert dt.tzinfo is not None

    def test_rejects_naive(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            _parse_iso("2026-09-08T00:00:00", "as_of")

    def test_rejects_garbage(self) -> None:
        with pytest.raises(ValueError, match="not ISO-8601"):
            _parse_iso("yesterday", "as_of")


# ---- _payload_to_import_kwargs ---------------------------------------------

class TestPayloadToImportKwargs:
    def test_good_payload(self) -> None:
        kw = _payload_to_import_kwargs(_good_payload())
        assert kw["account_id"] == "owner"
        assert kw["statement_id"] == "2026-09-08"
        assert isinstance(kw["as_of"], datetime)
        assert kw["as_of"].tzinfo is not None
        assert kw["opening_cash"] == 1137.0
        assert kw["closing_cash"] == 1100.0
        assert isinstance(kw["entries"], list)
        assert isinstance(kw["fills"], list)

    def test_missing_required_keys_rejected(self) -> None:
        bad = _good_payload()
        bad.pop("statement_id")
        with pytest.raises(ValueError, match="missing required keys"):
            _payload_to_import_kwargs(bad)

    def test_non_dict_payload_rejected(self) -> None:
        with pytest.raises(ValueError, match="JSON object"):
            _payload_to_import_kwargs([1, 2, 3])

    def test_non_list_entries_rejected(self) -> None:
        bad = _good_payload()
        bad["entries"] = "not a list"
        with pytest.raises(ValueError, match="entries must be a list"):
            _payload_to_import_kwargs(bad)

    def test_non_list_fills_rejected(self) -> None:
        bad = _good_payload()
        bad["fills"] = "not a list"
        with pytest.raises(ValueError, match="fills must be a list"):
            _payload_to_import_kwargs(bad)

    def test_naive_as_of_rejected(self) -> None:
        bad = _good_payload()
        bad["as_of"] = "2026-09-08T00:00:00"
        with pytest.raises(ValueError, match="timezone-aware"):
            _payload_to_import_kwargs(bad)

    @pytest.mark.parametrize("field,value", [
        ("account_id", None), ("account_id", "  "),
        ("statement_id", None), ("statement_id", "  "),
    ])
    def test_null_or_blank_identity_rejected(self, field, value) -> None:
        bad = _good_payload()
        bad[field] = value
        with pytest.raises(ValueError, match=field):
            _payload_to_import_kwargs(bad)


# ---- _write_output_atomic --------------------------------------------------

class TestWriteOutputAtomic:
    def test_writes_atomically(self, tmp_path) -> None:
        path = str(tmp_path / "out.json")
        _write_output_atomic(path, {"a": 1, "b": [2, 3]})
        with open(path, "rb") as f:
            data = json.loads(f.read())
        assert data == {"a": 1, "b": [2, 3]}

    def test_byte_identical_retry_succeeds(self, tmp_path) -> None:
        path = str(tmp_path / "out.json")
        v = {"a": 1, "b": "x"}
        _write_output_atomic(path, v)
        # Re-write with the same value: succeeds, no exception.
        _write_output_atomic(path, v)
        with open(path, "rb") as f:
            assert json.loads(f.read()) == v

    def test_different_value_retry_raises(self, tmp_path) -> None:
        path = str(tmp_path / "out.json")
        _write_output_atomic(path, {"a": 1})
        with pytest.raises(ValueError, match="different content"):
            _write_output_atomic(path, {"a": 2})

    def test_nan_value_rejected(self, tmp_path) -> None:
        path = str(tmp_path / "out.json")
        with pytest.raises(ValueError):
            _write_output_atomic(path, {"a": float("nan")})

    def test_creates_parent_directory(self, tmp_path) -> None:
        path = str(tmp_path / "deep" / "nested" / "out.json")
        _write_output_atomic(path, {"ok": True})
        assert os.path.exists(path)


# ---- _import_statement -----------------------------------------------------

class TestImportStatement:
    @pytest.mark.asyncio
    async def test_imports_and_records(self, cli_db: str, tmp_path) -> None:
        payload = _good_payload()
        p_path = str(tmp_path / "p.json")
        _write_payload(p_path, payload)
        o_path = str(tmp_path / "o.json")
        args = argparse.Namespace(
            db=cli_db, payload=p_path, output=o_path, command="import-statement",
        )
        out = await _import_statement(args)
        assert out["ok"] is True
        assert out["broker_status"] == "UNRESOLVED"
        assert out["account_id"] == "owner"
        assert out["statement_id"] == "2026-09-08"
        assert len(out["discrepancy_ids"]["broker"]) >= 1
        assert len(out["discrepancy_ids"]["evidence"]) >= 1
        assert "broker_internal" in out["discrepancy_ids"]
        assert out["broker_internal"]["status"] == "INSUFFICIENT_SCOPE"

    @pytest.mark.asyncio
    async def test_idempotent_reimport_no_new_discrepancies(
        self, cli_db: str, tmp_path,
    ) -> None:
        payload = _good_payload()
        p_path = str(tmp_path / "p.json")
        _write_payload(p_path, payload)
        o_path = str(tmp_path / "o.json")
        args = argparse.Namespace(
            db=cli_db, payload=p_path, output=o_path, command="import-statement",
        )
        first = await _import_statement(args)
        second = await _import_statement(args)
        assert first["ok"] and second["ok"]
        # The recorded discrepancy IDs must be byte-identical.
        assert (
            first["discrepancy_ids"]["broker"]
            == second["discrepancy_ids"]["broker"]
        )
        assert (
            first["discrepancy_ids"]["evidence"]
            == second["discrepancy_ids"]["evidence"]
        )

    @pytest.mark.asyncio
    async def test_import_reports_unique_live_reference_without_reconciliation_claim(
        self, cli_db: str, tmp_path, monkeypatch,
    ) -> None:
        from config import settings
        from fno_positions import init_fno_positions_db
        from position_tracker import init_positions_db
        monkeypatch.setattr(settings, "BROKER_RECONCILIATION_ACCOUNT_ID", "owner")
        await init_positions_db(cli_db)
        await init_fno_positions_db(cli_db)
        with sqlite3.connect(cli_db) as db:
            db.execute(
                "INSERT INTO positions "
                "(ticker,exchange,entry_date,entry_price,shares,status,source,broker_entry_order_id) "
                "VALUES ('TCS','NSE','2026-09-19',100,1,'OPEN','PENNY','order-1')")
        payload = _good_payload(statement="matched-reference")
        payload["fills"] = [{
            "fill_id": "fill-1", "order_id": "order-1", "status": "FILLED",
            "quantity": 1, "price": 100, "fees": 1,
        }]
        path = str(tmp_path / "matched.json")
        _write_payload(path, payload)
        out = await _import_statement(argparse.Namespace(
            db=cli_db, payload=path, output=str(tmp_path / "out.json"),
            command="import-statement"))
        assert out["ok"] is True
        assert out["broker_internal"]["status"] == "MATCHED_REFERENCE"
        assert out["broker_internal"]["broker_reconciled"] is False
        assert out["discrepancy_ids"]["broker_internal"] == []

    def test_main_retry_writes_identical_immutable_output(self, cli_db: str, tmp_path) -> None:
        payload_path = str(tmp_path / "statement.json")
        output_path = str(tmp_path / "out.json")
        _write_payload(payload_path, _good_payload())
        argv = ["--db", cli_db, "import-statement", "--payload", payload_path,
                "--output", output_path]
        assert main(argv) == 0
        with open(output_path, "rb") as stream:
            first = stream.read()
        assert main(argv) == 0
        with open(output_path, "rb") as stream:
            assert stream.read() == first

    @pytest.mark.asyncio
    async def test_bad_payload_records_error(
        self, cli_db: str, tmp_path,
    ) -> None:
        bad = _good_payload()
        bad.pop("statement_id")
        p_path = str(tmp_path / "p.json")
        _write_payload(p_path, bad)
        o_path = str(tmp_path / "o.json")
        args = argparse.Namespace(
            db=cli_db, payload=p_path, output=o_path, command="import-statement",
        )
        out = await _import_statement(args)
        assert out["ok"] is False
        assert out["error"] is not None
        assert "missing required keys" in out["error"]

    @pytest.mark.asyncio
    async def test_missing_payload_file(self, cli_db: str, tmp_path) -> None:
        o_path = str(tmp_path / "o.json")
        args = argparse.Namespace(
            db=cli_db,
            payload=str(tmp_path / "no_such.json"),
            output=o_path,
            command="import-statement",
        )
        out = await _import_statement(args)
        assert out["ok"] is False
        assert "unreadable input file" in (out["error"] or "")


# ---- _run_report -----------------------------------------------------------

class TestRunReport:
    @pytest.mark.asyncio
    async def test_runs_both_reports(self, cli_db: str, tmp_path) -> None:
        # First import a statement so the broker report has data.
        await _import_statement(argparse.Namespace(
            db=cli_db, payload=str(tmp_path / "_x.json"),
            output=str(tmp_path / "_y.json"), command="import-statement",
        ))
        # We need a real payload file for the import side effect to
        # work; create one.
        _write_payload(
            str(tmp_path / "_x.json"),
            _good_payload(statement="2026-09-09"),
        )
        o_path = str(tmp_path / "report.json")
        args = argparse.Namespace(
            db=cli_db, account="owner", source=None, limit=200,
            record=False, output=o_path, command="run-report",
        )
        out = await _run_report(args)
        assert out["ok"] is True
        assert out["broker"]["status"] in {"MATCH", "UNRESOLVED", "UNAVAILABLE"}
        assert "sheets" in out["evidence"]

    @pytest.mark.asyncio
    async def test_record_flag_records_discrepancies(
        self, cli_db: str, tmp_path,
    ) -> None:
        _write_payload(
            str(tmp_path / "_x.json"),
            _good_payload(statement="2026-09-10"),
        )
        await _import_statement(argparse.Namespace(
            db=cli_db, payload=str(tmp_path / "_x.json"),
            output=str(tmp_path / "_y.json"), command="import-statement",
        ))
        o_path = str(tmp_path / "report.json")
        args = argparse.Namespace(
            db=cli_db, account="owner", source=None, limit=200,
            record=True, output=o_path, command="run-report",
        )
        out = await _run_report(args)
        assert out["ok"] is True
        # The recorded list may be empty (idempotent re-record) but
        # the keys must exist.
        assert "broker" in out["discrepancy_ids"]
        assert "evidence" in out["discrepancy_ids"]
        assert "broker_internal" in out["discrepancy_ids"]
        assert out["broker_internal"]["broker_reconciled"] is False


# ---- _list_discrepancies ---------------------------------------------------

class TestListDiscrepancies:
    @pytest.mark.asyncio
    async def test_lists_empty(self, cli_db: str, tmp_path) -> None:
        args = argparse.Namespace(
            db=cli_db, account=None, source=None,
            category=None, status=None, since=None, until=None,
            limit=200, output=str(tmp_path / "out.json"),
            command="list-discrepancies",
        )
        out = await _list_discrepancies(args)
        assert out["ok"] is True
        assert out["rows"] == []

    @pytest.mark.asyncio
    async def test_lists_after_import(
        self, cli_db: str, tmp_path,
    ) -> None:
        _write_payload(
            str(tmp_path / "_x.json"),
            _good_payload(statement="2026-09-11"),
        )
        await _import_statement(argparse.Namespace(
            db=cli_db, payload=str(tmp_path / "_x.json"),
            output=str(tmp_path / "_y.json"), command="import-statement",
        ))
        args = argparse.Namespace(
            db=cli_db, account="owner", source=None,
            category=None, status=None, since=None, until=None,
            limit=200, output=str(tmp_path / "out.json"),
            command="list-discrepancies",
        )
        out = await _list_discrepancies(args)
        assert out["ok"] is True
        assert len(out["rows"]) >= 1

    @pytest.mark.asyncio
    async def test_invalid_category_rejected(
        self, cli_db: str, tmp_path,
    ) -> None:
        args = argparse.Namespace(
            db=cli_db, account=None, source=None,
            category="NOT_A_CATEGORY", status=None, since=None, until=None,
            limit=200, output=str(tmp_path / "out.json"),
            command="list-discrepancies",
        )
        out = await _list_discrepancies(args)
        assert out["ok"] is False
        assert "category" in (out["error"] or "")

    @pytest.mark.asyncio
    async def test_invalid_status_rejected(
        self, cli_db: str, tmp_path,
    ) -> None:
        args = argparse.Namespace(
            db=cli_db, account=None, source=None,
            category=None, status="NOT_A_STATUS", since=None, until=None,
            limit=200, output=str(tmp_path / "out.json"),
            command="list-discrepancies",
        )
        out = await _list_discrepancies(args)
        assert out["ok"] is False
        assert "status" in (out["error"] or "")


# ---- main() integration ----------------------------------------------------

class TestMainIntegration:
    def test_import_statement_subcommand_runs(self, cli_db, tmp_path) -> None:
        payload_path = str(tmp_path / "p.json")
        output_path = str(tmp_path / "o.json")
        _write_payload(payload_path, _good_payload())
        rc = main([
            "--db", cli_db,
            "import-statement",
            "--payload", payload_path,
            "--output", output_path,
        ])
        assert rc == 0
        with open(output_path, "rb") as f:
            out = json.loads(f.read())
        assert out["ok"] is True

    def test_list_discrepancies_subcommand_runs(
        self, cli_db, tmp_path,
    ) -> None:
        output_path = str(tmp_path / "o.json")
        rc = main([
            "--db", cli_db,
            "list-discrepancies",
            "--output", output_path,
        ])
        assert rc == 0
        with open(output_path, "rb") as f:
            out = json.loads(f.read())
        assert out["ok"] is True

    def test_validation_error_returns_nonzero(
        self, cli_db, tmp_path,
    ) -> None:
        payload_path = str(tmp_path / "bad.json")
        output_path = str(tmp_path / "o.json")
        bad = _good_payload()
        bad.pop("statement_id")
        _write_payload(payload_path, bad)
        rc = main([
            "--db", cli_db,
            "import-statement",
            "--payload", payload_path,
            "--output", output_path,
        ])
        assert rc == 1
        # Output is still written so the operator can see why.
        with open(output_path, "rb") as f:
            out = json.loads(f.read())
        assert out["ok"] is False

    def test_run_report_subcommand_runs(self, cli_db, tmp_path) -> None:
        # First import so the broker report has data.
        _write_payload(
            str(tmp_path / "p.json"),
            _good_payload(statement="2026-09-12"),
        )
        main([
            "--db", cli_db,
            "import-statement",
            "--payload", str(tmp_path / "p.json"),
            "--output", str(tmp_path / "i.json"),
        ])
        output_path = str(tmp_path / "o.json")
        rc = main([
            "--db", cli_db,
            "run-report",
            "--account", "owner",
            "--output", output_path,
        ])
        assert rc == 0
        with open(output_path, "rb") as f:
            out = json.loads(f.read())
        assert out["ok"] is True
        assert out["broker"]["status"] in {"MATCH", "UNRESOLVED", "UNAVAILABLE"}
