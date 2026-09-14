"""[WORKFLOW-F 2026-09-13] Discrepancy framework acceptance.

Closes F4 (sub-slices F4.a, F4.b, F4.c) of workstream F per
``docs/2026-09-13-workflow-f-state-of-codebase-audit.md`` section 6
future plan and ``docs/NEXT_AGENT_PLAN.md`` section 10.2.

Acceptance coverage for ``python-engine/discrepancies.py``.

[WHY-THIS-EXISTS 2026-09-13]
  Pre-fix, the five DISC-A1..A5 reconciliation warnings in the F
  audit doc were docs-only placeholders with no source evidence.
  ``broker_reconciliation.broker_statement_report`` returned
  MATCH/UNRESOLVED/UNAVAILABLE but did not persist anything.
  ``reconciliation_evidence.reconciliation_evidence_report`` returned
  per-row reasons (origin_ref_pnl_difference, etc.) but did not
  persist them. Re-running the report produced the same findings
  with no operator-visible history. F4 ships the durable record
  layer with append-only DB triggers, idempotent recording, and a
  forward-only state machine.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest
import pytest_asyncio

from discrepancies import (
    DISCREPANCY_SCHEMA_VERSION,
    DiscrepancyCategory,
    DiscrepancyRecord,
    DiscrepancyStatus,
    DiscrepancyTransitionError,
    init_discrepancies_db,
    list_discrepancies,
    record_current_state,
    record_discrepancy,
    record_from_broker_statement,
    record_from_evidence_report,
    update_discrepancy_status,
)


# ---- fixtures ---------------------------------------------------------------

@pytest_asyncio.fixture
async def discrepancies_db(tmp_path):
    """A fresh ``discrepancies.db`` per test, with the schema applied."""
    path = str(tmp_path / "discrepancies.db")
    await init_discrepancies_db(path)
    yield path


# ---- schema version --------------------------------------------------------

class TestSchemaVersion:
    def test_version_constant_is_a_positive_int(self) -> None:
        assert isinstance(DISCREPANCY_SCHEMA_VERSION, int)
        assert DISCREPANCY_SCHEMA_VERSION >= 1


# ---- record_discrepancy ----------------------------------------------------

class TestRecordDiscrepancy:
    @pytest.mark.asyncio
    async def test_first_record_returns_id(self, discrepancies_db: str) -> None:
        did = await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.ORIGIN_REF_PNL_DIFFERENCE,
            evidence_key="CAT|ledger:1",
            account_id="owner",
            source="PENNY_PAPER",
            severity="HIGH",
            amount_inr=-100.0,
            evidence_refs=[("bankroll_ledger", "1")],
        )
        assert isinstance(did, int) and did >= 1

    @pytest.mark.asyncio
    async def test_idempotent_returns_same_id_and_ignores_new_values(
        self, discrepancies_db: str,
    ) -> None:
        did1 = await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.ORIGIN_REF_PNL_DIFFERENCE,
            evidence_key="CAT|ledger:1",
            account_id="owner", source="PENNY_PAPER",
            severity="HIGH", amount_inr=-100.0,
            evidence_refs=[("bankroll_ledger", "1")],
        )
        # Re-record with different severity / amount / refs.
        did2 = await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.ORIGIN_REF_PNL_DIFFERENCE,
            evidence_key="CAT|ledger:1",
            account_id="owner", source="PENNY_PAPER",
            severity="LOW", amount_inr=-999.0,
            evidence_refs=[("bankroll_ledger", "999")],
        )
        assert did1 == did2
        rows = await list_discrepancies(discrepancies_db)
        assert len(rows) == 1
        assert rows[0].severity == "HIGH"  # first record wins
        assert rows[0].amount_inr == -100.0
        assert rows[0].evidence_refs == [("bankroll_ledger", "1")]

    @pytest.mark.asyncio
    async def test_record_with_no_amount_is_allowed(
        self, discrepancies_db: str,
    ) -> None:
        did = await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.BROKER_STATEMENT_UNAVAILABLE,
            evidence_key="X|owner|NO_BROKER_STATEMENT",
            account_id="owner", source="BROKER",
            severity="LOW", amount_inr=None,
            evidence_refs=[],
        )
        rows = await list_discrepancies(discrepancies_db)
        assert rows[0].id == did
        assert rows[0].amount_inr is None

    @pytest.mark.asyncio
    async def test_legacy_internal_account_attribution_is_unverified(
        self, discrepancies_db: str,
    ) -> None:
        await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.ORIGIN_REF_PNL_DIFFERENCE,
            evidence_key="legacy|ledger:1", account_id="old-account",
            source="PENNY_PAPER", severity="HIGH",
        )
        [row] = await list_discrepancies(discrepancies_db)
        assert row.account_attribution == "UNVERIFIED_LEGACY_ACCOUNT_ATTRIBUTION"

    @pytest.mark.asyncio
    async def test_invalid_severity_rejected(
        self, discrepancies_db: str,
    ) -> None:
        with pytest.raises(ValueError, match="severity"):
            await record_discrepancy(
                discrepancies_db,
                category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
                evidence_key="X",
                account_id="owner", source="BROKER",
                severity="BOGUS",
            )

    @pytest.mark.asyncio
    async def test_empty_evidence_key_rejected(
        self, discrepancies_db: str,
    ) -> None:
        with pytest.raises(ValueError, match="evidence_key"):
            await record_discrepancy(
                discrepancies_db,
                category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
                evidence_key="",
                account_id="owner", source="BROKER",
                severity="HIGH",
            )

    @pytest.mark.asyncio
    async def test_nan_amount_rejected(
        self, discrepancies_db: str,
    ) -> None:
        with pytest.raises(ValueError, match="amount_inr"):
            await record_discrepancy(
                discrepancies_db,
                category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
                evidence_key="X",
                account_id="owner", source="BROKER",
                severity="HIGH", amount_inr=float("nan"),
            )

    @pytest.mark.asyncio
    async def test_malformed_evidence_ref_rejected(
        self, discrepancies_db: str,
    ) -> None:
        with pytest.raises(ValueError, match="evidence_ref"):
            await record_discrepancy(
                discrepancies_db,
                category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
                evidence_key="X",
                account_id="owner", source="BROKER",
                severity="HIGH",
                evidence_refs=[("bankroll_ledger",)],  # 1-tuple, invalid
            )

    @pytest.mark.asyncio
    async def test_evidence_refs_deduplicated(
        self, discrepancies_db: str,
    ) -> None:
        await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.ORIGIN_REF_PNL_DIFFERENCE,
            evidence_key="X",
            account_id="owner", source="X",
            severity="HIGH",
            evidence_refs=[
                ("bankroll_ledger", "1"),
                ("bankroll_ledger", "1"),  # duplicate
                ("bankroll_ledger", "2"),
            ],
        )
        rows = await list_discrepancies(discrepancies_db)
        assert rows[0].evidence_refs == [
            ("bankroll_ledger", "1"),
            ("bankroll_ledger", "2"),
        ]


# ---- update_discrepancy_status ---------------------------------------------

class TestUpdateStatus:
    @pytest.mark.asyncio
    async def test_open_to_investigating(
        self, discrepancies_db: str,
    ) -> None:
        did = await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
            evidence_key="X", account_id="o", source="X", severity="HIGH",
        )
        await update_discrepancy_status(
            discrepancies_db,
            discrepancy_id=did,
            new_status=DiscrepancyStatus.INVESTIGATING,
            actor="op", note="reviewing",
        )
        rows = await list_discrepancies(discrepancies_db)
        assert rows[0].current_status == DiscrepancyStatus.INVESTIGATING
        assert rows[0].status_note == "reviewing"

    @pytest.mark.asyncio
    async def test_open_to_withdrawn(
        self, discrepancies_db: str,
    ) -> None:
        did = await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
            evidence_key="X", account_id="o", source="X", severity="LOW",
        )
        await update_discrepancy_status(
            discrepancies_db, discrepancy_id=did,
            new_status=DiscrepancyStatus.WITHDRAWN, actor="op",
            note="not a real discrepancy",
        )
        rows = await list_discrepancies(discrepancies_db)
        assert rows[0].current_status == DiscrepancyStatus.WITHDRAWN

    @pytest.mark.asyncio
    async def test_investigating_to_resolved(
        self, discrepancies_db: str,
    ) -> None:
        did = await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
            evidence_key="X", account_id="o", source="X", severity="HIGH",
        )
        await update_discrepancy_status(
            discrepancies_db, discrepancy_id=did,
            new_status=DiscrepancyStatus.INVESTIGATING, actor="op",
        )
        await update_discrepancy_status(
            discrepancies_db, discrepancy_id=did,
            new_status=DiscrepancyStatus.RESOLVED_EXPLAINED, actor="op",
            note="explained by FX timing",
        )
        rows = await list_discrepancies(discrepancies_db)
        assert rows[0].current_status == DiscrepancyStatus.RESOLVED_EXPLAINED
        assert rows[0].status_note == "explained by FX timing"

    @pytest.mark.asyncio
    async def test_skip_investigating_rejected(
        self, discrepancies_db: str,
    ) -> None:
        did = await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
            evidence_key="X", account_id="o", source="X", severity="HIGH",
        )
        with pytest.raises(DiscrepancyTransitionError, match="OPEN -> RESOLVED_EXPLAINED"):
            await update_discrepancy_status(
                discrepancies_db, discrepancy_id=did,
                new_status=DiscrepancyStatus.RESOLVED_EXPLAINED, actor="op",
            )

    @pytest.mark.asyncio
    async def test_resolved_to_open_rejected(
        self, discrepancies_db: str,
    ) -> None:
        did = await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
            evidence_key="X", account_id="o", source="X", severity="HIGH",
        )
        await update_discrepancy_status(
            discrepancies_db, discrepancy_id=did,
            new_status=DiscrepancyStatus.INVESTIGATING, actor="op",
        )
        await update_discrepancy_status(
            discrepancies_db, discrepancy_id=did,
            new_status=DiscrepancyStatus.RESOLVED_EXPLAINED, actor="op",
        )
        with pytest.raises(DiscrepancyTransitionError):
            await update_discrepancy_status(
                discrepancies_db, discrepancy_id=did,
                new_status=DiscrepancyStatus.OPEN, actor="op",
            )

    @pytest.mark.asyncio
    async def test_same_state_is_idempotent_no_log_row(
        self, discrepancies_db: str,
    ) -> None:
        did = await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
            evidence_key="X", account_id="o", source="X", severity="HIGH",
        )
        # First transition creates a log row.
        await update_discrepancy_status(
            discrepancies_db, discrepancy_id=did,
            new_status=DiscrepancyStatus.INVESTIGATING, actor="op",
        )
        # Re-issuing same state must NOT add a log row.
        await update_discrepancy_status(
            discrepancies_db, discrepancy_id=did,
            new_status=DiscrepancyStatus.INVESTIGATING, actor="op",
            note="second call",
        )
        sync = sqlite3.connect(discrepancies_db)
        try:
            count = sync.execute(
                "SELECT COUNT(*) FROM discrepancy_status_log "
                "WHERE discrepancy_id=? AND to_status='INVESTIGATING'",
                (did,),
            ).fetchone()[0]
        finally:
            sync.close()
        assert count == 1, "same-state must not append a duplicate log row"

    @pytest.mark.asyncio
    async def test_unknown_discrepancy_id_raises(
        self, discrepancies_db: str,
    ) -> None:
        with pytest.raises(ValueError, match="no discrepancy_status_log"):
            await update_discrepancy_status(
                discrepancies_db, discrepancy_id=99999,
                new_status=DiscrepancyStatus.INVESTIGATING, actor="op",
            )

    @pytest.mark.asyncio
    async def test_empty_actor_rejected(
        self, discrepancies_db: str,
    ) -> None:
        did = await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
            evidence_key="X", account_id="o", source="X", severity="HIGH",
        )
        with pytest.raises(ValueError, match="actor"):
            await update_discrepancy_status(
                discrepancies_db, discrepancy_id=did,
                new_status=DiscrepancyStatus.INVESTIGATING, actor="",
            )


# ---- append-only DB triggers -----------------------------------------------

class TestAppendOnlyTriggers:
    @pytest.mark.asyncio
    async def test_discrepancies_update_blocked(
        self, discrepancies_db: str,
    ) -> None:
        did = await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
            evidence_key="X", account_id="o", source="X", severity="HIGH",
        )
        sync = sqlite3.connect(discrepancies_db)
        try:
            with pytest.raises(sqlite3.IntegrityError, match="discrepancies_immutable"):
                sync.execute(
                    "UPDATE discrepancies SET severity='LOW' WHERE id=?",
                    (did,),
                )
        finally:
            sync.close()

    @pytest.mark.asyncio
    async def test_discrepancies_delete_blocked(
        self, discrepancies_db: str,
    ) -> None:
        did = await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
            evidence_key="X", account_id="o", source="X", severity="HIGH",
        )
        sync = sqlite3.connect(discrepancies_db)
        try:
            with pytest.raises(sqlite3.IntegrityError, match="discrepancies_immutable"):
                sync.execute("DELETE FROM discrepancies WHERE id=?", (did,))
        finally:
            sync.close()

    @pytest.mark.asyncio
    async def test_status_log_update_blocked(
        self, discrepancies_db: str,
    ) -> None:
        did = await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
            evidence_key="X", account_id="o", source="X", severity="HIGH",
        )
        sync = sqlite3.connect(discrepancies_db)
        try:
            with pytest.raises(sqlite3.IntegrityError, match="discrepancy_status_log_immutable"):
                sync.execute(
                    "UPDATE discrepancy_status_log SET note='x' WHERE discrepancy_id=?",
                    (did,),
                )
        finally:
            sync.close()

    @pytest.mark.asyncio
    async def test_status_log_delete_blocked(
        self, discrepancies_db: str,
    ) -> None:
        did = await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
            evidence_key="X", account_id="o", source="X", severity="HIGH",
        )
        sync = sqlite3.connect(discrepancies_db)
        try:
            with pytest.raises(sqlite3.IntegrityError, match="discrepancy_status_log_immutable"):
                sync.execute(
                    "DELETE FROM discrepancy_status_log WHERE discrepancy_id=?",
                    (did,),
                )
        finally:
            sync.close()


# ---- list_discrepancies ----------------------------------------------------

class TestListDiscrepancies:
    @pytest.mark.asyncio
    async def test_filter_by_account(self, discrepancies_db: str) -> None:
        await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
            evidence_key="X1", account_id="alpha", source="X", severity="HIGH",
        )
        await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
            evidence_key="X2", account_id="beta", source="X", severity="HIGH",
        )
        rows = await list_discrepancies(discrepancies_db, account_id="alpha")
        assert len(rows) == 1
        assert rows[0].account_id == "alpha"

    @pytest.mark.asyncio
    async def test_filter_by_category(self, discrepancies_db: str) -> None:
        await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
            evidence_key="X1", account_id="o", source="X", severity="HIGH",
        )
        await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.ORIGIN_REF_PNL_DIFFERENCE,
            evidence_key="X2", account_id="o", source="X", severity="HIGH",
        )
        rows = await list_discrepancies(
            discrepancies_db,
            category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
        )
        assert len(rows) == 1
        assert rows[0].category == DiscrepancyCategory.BROKER_RESIDUAL_NONZERO

    @pytest.mark.asyncio
    async def test_filter_by_source(self, discrepancies_db: str) -> None:
        await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
            evidence_key="X1", account_id="o", source="PENNY", severity="HIGH",
        )
        await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
            evidence_key="X2", account_id="o", source="MOMENTUM", severity="HIGH",
        )
        rows = await list_discrepancies(discrepancies_db, source="PENNY")
        assert len(rows) == 1 and rows[0].source == "PENNY"

    @pytest.mark.asyncio
    async def test_filter_by_status(self, discrepancies_db: str) -> None:
        d1 = await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
            evidence_key="X1", account_id="o", source="X", severity="HIGH",
        )
        d2 = await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.ORIGIN_REF_PNL_DIFFERENCE,
            evidence_key="X2", account_id="o", source="X", severity="HIGH",
        )
        await update_discrepancy_status(
            discrepancies_db, discrepancy_id=d1,
            new_status=DiscrepancyStatus.INVESTIGATING, actor="op",
        )
        open_rows = await list_discrepancies(
            discrepancies_db, status=DiscrepancyStatus.OPEN,
        )
        assert {r.id for r in open_rows} == {d2}
        inv_rows = await list_discrepancies(
            discrepancies_db, status=DiscrepancyStatus.INVESTIGATING,
        )
        assert {r.id for r in inv_rows} == {d1}

    @pytest.mark.asyncio
    async def test_filter_by_date_range(self, discrepancies_db: str) -> None:
        # Two rows; the filter on recorded_at should isolate them.
        await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
            evidence_key="X1", account_id="o", source="X", severity="HIGH",
        )
        future = datetime.now(timezone.utc).replace(year=2099)
        rows = await list_discrepancies(
            discrepancies_db,
            since=future,
        )
        assert rows == []

    @pytest.mark.asyncio
    async def test_limit_enforced(self, discrepancies_db: str) -> None:
        for i in range(5):
            await record_discrepancy(
                discrepancies_db,
                category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
                evidence_key=f"X{i}", account_id="o", source="X", severity="HIGH",
            )
        rows = await list_discrepancies(discrepancies_db, limit=3)
        assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_invalid_limit_rejected(self, discrepancies_db: str) -> None:
        with pytest.raises(ValueError, match="limit"):
            await list_discrepancies(discrepancies_db, limit=0)
        with pytest.raises(ValueError, match="limit"):
            await list_discrepancies(discrepancies_db, limit=2000)

    @pytest.mark.asyncio
    async def test_empty_result(self, discrepancies_db: str) -> None:
        rows = await list_discrepancies(discrepancies_db)
        assert rows == []

    @pytest.mark.asyncio
    async def test_to_dict_round_trip(self, discrepancies_db: str) -> None:
        await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.ORIGIN_REF_PNL_DIFFERENCE,
            evidence_key="X", account_id="o", source="X", severity="HIGH",
            amount_inr=-12.5,
            evidence_refs=[("bankroll_ledger", "1")],
        )
        rows = await list_discrepancies(discrepancies_db)
        d = rows[0].to_dict()
        assert d["category"] == "ORIGIN_REF_PNL_DIFFERENCE"
        assert d["severity"] == "HIGH"
        assert d["amount_inr"] == -12.5
        assert d["evidence_refs"] == [{"table": "bankroll_ledger", "key": "1"}]
        assert d["current_status"] == "OPEN"


# ---- bridges ----------------------------------------------------------------

class TestBridgeFromBrokerStatement:
    @pytest.mark.asyncio
    async def test_match_returns_none(self, discrepancies_db: str) -> None:
        out = await record_from_broker_statement(
            discrepancies_db,
            broker_report={"status": "MATCH", "residual": 0.0},
            account_id="o",
        )
        assert out is None
        rows = await list_discrepancies(discrepancies_db)
        assert rows == []

    @pytest.mark.asyncio
    async def test_unresolved_records_residual(
        self, discrepancies_db: str,
    ) -> None:
        out = await record_from_broker_statement(
            discrepancies_db,
            broker_report={
                "status": "UNRESOLVED",
                "statement_id": "2026-09-07",
                "residual": 12.5,
            },
            account_id="o",
        )
        assert isinstance(out, int)
        rows = await list_discrepancies(discrepancies_db)
        assert len(rows) == 1
        assert rows[0].category == DiscrepancyCategory.BROKER_RESIDUAL_NONZERO
        assert rows[0].amount_inr == 12.5
        assert rows[0].severity == "HIGH"
        assert rows[0].evidence_refs == [
            ("broker_statement_imports", "o:2026-09-07"),
        ]

    @pytest.mark.asyncio
    async def test_unavailable_records_no_statement(
        self, discrepancies_db: str,
    ) -> None:
        out = await record_from_broker_statement(
            discrepancies_db,
            broker_report={
                "status": "UNAVAILABLE",
                "reason": "NO_BROKER_STATEMENT",
            },
            account_id="o",
        )
        assert isinstance(out, int)
        rows = await list_discrepancies(discrepancies_db)
        assert rows[0].category == DiscrepancyCategory.BROKER_STATEMENT_UNAVAILABLE
        assert rows[0].amount_inr is None
        assert rows[0].severity == "LOW"

    @pytest.mark.asyncio
    async def test_unknown_status_rejected(
        self, discrepancies_db: str,
    ) -> None:
        with pytest.raises(ValueError, match="unknown broker report status"):
            await record_from_broker_statement(
                discrepancies_db,
                broker_report={"status": "BOGUS"},
                account_id="o",
            )

    @pytest.mark.asyncio
    async def test_nan_residual_rejected(
        self, discrepancies_db: str,
    ) -> None:
        with pytest.raises(ValueError, match="residual"):
            await record_from_broker_statement(
                discrepancies_db,
                broker_report={
                    "status": "UNRESOLVED",
                    "statement_id": "X",
                    "residual": float("nan"),
                },
                account_id="o",
            )


class TestBridgeFromEvidenceReport:
    @pytest.mark.asyncio
    async def test_unresolved_row_records_pnl_difference(
        self, discrepancies_db: str,
    ) -> None:
        eids = await record_from_evidence_report(
            discrepancies_db,
            evidence_report={
                "sheets": [
                    {"ledger_id": 100, "ticker": "TCS",
                     "source": "PENNY_PAPER",
                     "ledger_pnl": -10.0, "state": "UNRESOLVED",
                     "reason": "origin_ref_pnl_difference",
                     "position": None},
                ],
                "source_sheets": [
                    {"source": "PENNY_PAPER",
                     "status": "INTERNAL_EVIDENCE_AVAILABLE"},
                ],
            },
            account_id="o",
        )
        assert eids == [1]
        rows = await list_discrepancies(discrepancies_db)
        assert rows[0].category == DiscrepancyCategory.ORIGIN_REF_PNL_DIFFERENCE
        assert rows[0].severity == "HIGH"
        assert rows[0].amount_inr == -10.0
        assert rows[0].account_id == "INTERNAL_UNSCOPED"
        assert rows[0].account_attribution == "INTERNAL_UNSCOPED"

    @pytest.mark.asyncio
    async def test_same_internal_fact_is_not_attached_to_each_broker_account(
        self, discrepancies_db: str,
    ) -> None:
        payload = {
            "sheets": [{
                "ledger_id": 777, "ticker": "TCS", "source": "PENNY_PAPER",
                "ledger_pnl": -10.0, "state": "UNRESOLVED",
                "reason": "origin_ref_pnl_difference", "position": None,
            }],
            "source_sheets": [],
        }
        first = await record_from_evidence_report(
            discrepancies_db, evidence_report=payload, account_id="broker-a",
        )
        second = await record_from_evidence_report(
            discrepancies_db, evidence_report=payload, account_id="broker-b",
        )
        assert first == second
        assert await list_discrepancies(discrepancies_db, account_id="broker-a") == []
        assert await list_discrepancies(discrepancies_db, account_id="broker-b") == []

    @pytest.mark.asyncio
    async def test_matched_internal_skipped(
        self, discrepancies_db: str,
    ) -> None:
        eids = await record_from_evidence_report(
            discrepancies_db,
            evidence_report={
                "sheets": [
                    {"ledger_id": 101, "ticker": "INFY",
                     "source": "PENNY_PAPER",
                     "ledger_pnl": 5.0, "state": "MATCHED_INTERNAL",
                     "reason": "stable_origin_ref_and_pnl_match",
                     "position": None},
                ],
                "source_sheets": [],
            },
            account_id="o",
        )
        assert eids == []
        rows = await list_discrepancies(discrepancies_db)
        assert rows == []

    @pytest.mark.asyncio
    async def test_unknown_reason_skipped_silently(
        self, discrepancies_db: str,
    ) -> None:
        # An unknown reason string is silently skipped -- not raised.
        eids = await record_from_evidence_report(
            discrepancies_db,
            evidence_report={
                "sheets": [
                    {"ledger_id": 200, "ticker": "X",
                     "source": "PENNY_PAPER",
                     "ledger_pnl": 0.0, "state": "UNRESOLVED",
                     "reason": "future_reason_string_not_yet_categorised",
                     "position": None},
                ],
                "source_sheets": [],
            },
            account_id="o",
        )
        assert eids == []
        rows = await list_discrepancies(discrepancies_db)
        assert rows == []

    @pytest.mark.asyncio
    async def test_invalid_amounts_sheet_flag(
        self, discrepancies_db: str,
    ) -> None:
        eids = await record_from_evidence_report(
            discrepancies_db,
            evidence_report={
                "sheets": [],
                "source_sheets": [
                    {"source": "PENNY_PAPER",
                     "status": "INTERNAL_EVIDENCE_HAS_INVALID_AMOUNTS"},
                ],
            },
            account_id="o",
        )
        assert len(eids) == 1
        rows = await list_discrepancies(discrepancies_db)
        assert rows[0].category == DiscrepancyCategory.INTERNAL_EVIDENCE_INVALID_AMOUNTS
        assert rows[0].amount_inr is None
        assert rows[0].evidence_refs == [("bankroll_ledger", "source:PENNY_PAPER")]

    @pytest.mark.asyncio
    async def test_multiple_unresolved_details_all_recorded(
        self, discrepancies_db: str,
    ) -> None:
        eids = await record_from_evidence_report(
            discrepancies_db,
            evidence_report={
                "sheets": [
                    {"ledger_id": 1, "ticker": "TCS", "source": "PENNY_PAPER",
                     "ledger_pnl": -1, "state": "UNRESOLVED",
                     "reason": "origin_ref_pnl_difference",
                     "position": None},
                    {"ledger_id": 2, "ticker": "INFY", "source": "PENNY_PAPER",
                     "ledger_pnl": -2, "state": "UNRESOLVED",
                     "reason": "origin_ref_source_mismatch",
                     "position": {"source": "MOMENTUM", "status": "CLOSED"}},
                    {"ledger_id": 3, "ticker": "HDFC", "source": "PENNY_PAPER",
                     "ledger_pnl": -3, "state": "UNRESOLVED",
                     "reason": "multiple_ledger_rows_share_origin_ref",
                     "position": None},
                ],
                "source_sheets": [],
            },
            account_id="o",
        )
        assert len(eids) == 3
        rows = await list_discrepancies(discrepancies_db)
        cats = {r.category for r in rows}
        assert cats == {
            DiscrepancyCategory.ORIGIN_REF_PNL_DIFFERENCE,
            DiscrepancyCategory.ORIGIN_REF_SOURCE_MISMATCH,
            DiscrepancyCategory.MULTIPLE_LEDGER_ROWS_SHARE_ORIGIN_REF,
        }
        # The source-mismatch row should include the position_status ref.
        sm = next(
            r for r in rows
            if r.category == DiscrepancyCategory.ORIGIN_REF_SOURCE_MISMATCH
        )
        assert ("position_status", "MOMENTUM:CLOSED") in sm.evidence_refs


# ---- record_current_state end-to-end --------------------------------------

class TestRecordCurrentStateEndToEnd:
    @pytest.mark.asyncio
    async def test_records_both_broker_and_evidence(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """End-to-end: run both reports via real DBs, no mocks."""
        from broker_reconciliation import import_broker_statement
        from performance import init_ledger, record_trade_close
        db = str(tmp_path / "end2end.db")
        # 1. Seed bankroll_ledger so the evidence report has a sheet.
        # Use a non-empty origin_ref that doesn't match any position
        # in fno_positions / fno_dr_positions. The evidence report
        # will tag this row as `origin_ref_has_no_matching_position`
        # (mapped to DiscrepancyCategory.ORIGIN_REF_HAS_NO_MATCHING_POSITION).
        await init_ledger(db)
        await record_trade_close(
            db, ticker="TCS", pnl=-50.0, source="PENNY_PAPER",
            origin_ref="fno_position:99999",
        )
        # 2. Import a broker statement that is UNRESOLVED (residual
        #    != 0). The expected cash with closing=1100 should be
        #    1000+200-40-8-15 = 1137, but we set closing=1100 -> 37 rupee
        #    gap, so status=UNRESOLVED.
        await import_broker_statement(
            db, account_id="owner", statement_id="2026-09-08",
            as_of=datetime(2026, 9, 8, tzinfo=timezone.utc),
            opening_cash=1137.0, closing_cash=1100.0,
            entries=[
                {"entry_id": "d", "entry_type": "DEPOSIT", "amount": 200},
                {"entry_id": "t", "entry_type": "TRADE_REALIZED", "amount": -40},
                {"entry_id": "c", "entry_type": "CHARGE", "amount": 8},
                {"entry_id": "o", "entry_type": "OPERATING_EXPENSE", "amount": 15},
            ],
            fills=[],
        )
        # 3. Run the bridge.
        result = await record_current_state(
            db, account_id="owner", actor="test",
        )
        # Broker side: 1 record (UNRESOLVED residual).
        assert len(result["broker"]) == 1
        # Evidence side: at least one record (the empty origin_ref row).
        assert len(result["evidence"]) >= 1
        # Verify both categories are in the recorded rows.
        rows = await list_discrepancies(db)
        cats = {r.category for r in rows}
        assert DiscrepancyCategory.BROKER_RESIDUAL_NONZERO in cats
        assert (
            DiscrepancyCategory.ORIGIN_REF_HAS_NO_MATCHING_POSITION in cats
        )


# ---- reproduction / determinism --------------------------------------------

class TestReproducibility:
    @pytest.mark.asyncio
    async def test_same_record_twice_no_extra_log_rows(
        self, discrepancies_db: str,
    ) -> None:
        await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
            evidence_key="X", account_id="o", source="X", severity="HIGH",
        )
        await record_discrepancy(
            discrepancies_db,
            category=DiscrepancyCategory.BROKER_RESIDUAL_NONZERO,
            evidence_key="X", account_id="o", source="X", severity="HIGH",
        )
        sync = sqlite3.connect(discrepancies_db)
        try:
            count = sync.execute(
                "SELECT COUNT(*) FROM discrepancies"
            ).fetchone()[0]
            log_count = sync.execute(
                "SELECT COUNT(*) FROM discrepancy_status_log"
            ).fetchone()[0]
        finally:
            sync.close()
        assert count == 1
        assert log_count == 1
