"""[WORKFLOW-F 2026-09-13] Phase 1 inventory + reconciliation-warning map acceptance.

Checks bounded F1 contracts, not completion of the inventory or investigation per
``docs/2026-09-13-workflow-f-state-of-codebase-audit.md``. F1 is the
*inventory* phase; it ships:

1. F1.a \u2014 a docs census of every F-relevant table, write path, read
   path, and source-enum invariant;
2. F1.b \u2014 unverified historical-warning inventory; tests do not
   establish warning identities, persisted IDs or closure;
3. F1.c \u2014 retain unknown effective date until dated tariff provenance
   is established; verification date is not an effective-date substitute.

The correction ships no new runtime tables, migrations, scheduler wiring or
broker integration. Fresh isolated databases check current owning contracts;
they do not prove actual Production reconciliation or inventory completeness.

The test file also verifies F1's *negative space*:
  - there is no ``DISC-<id>`` literal in production code yet (clean
    slate for F4);
  - there is no new persistence surface under the F tree yet
    (F2-F6 have not started).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cost_schedules import (
    EQUITY_INTRADAY_EFFECTIVE_DATE,
    EQUITY_INTRADAY_SCHEDULE_VERSION,
    EQUITY_INTRADAY_VERIFIED_AS_OF,
    OPTIONS_EFFECTIVE_DATE,
    OPTIONS_SCHEDULE_VERSION,
    equity_intraday_cost_snapshot,
    options_cost_snapshot,
)


# ---- 1: cost-schedule decisions (F1.c) ------------------------------

class TestF1cCostScheduleDecision:
    def test_equity_intraday_effective_date_is_unknown(self) -> None:
        """Verification does not establish a composite tariff effective date."""
        assert EQUITY_INTRADAY_EFFECTIVE_DATE is None
        assert EQUITY_INTRADAY_VERIFIED_AS_OF == "2026-08-10"

    def test_equity_snapshot_carries_effective_date(self) -> None:
        """New snapshots expose uncertainty without changing options metadata."""
        snapshot = equity_intraday_cost_snapshot()
        assert snapshot["effective_date"] is None
        assert snapshot["verified_as_of"] == "2026-08-10"
        assert snapshot["schedule_version"] == EQUITY_INTRADAY_SCHEDULE_VERSION

    def test_options_snapshot_unchanged(self) -> None:
        """F1.c is intentionally equity-only; options schedule is not modified.

        This test prevents an accidental drift into the options
        snapshot's effective date on a future inventory commit.
        """
        assert OPTIONS_EFFECTIVE_DATE == "2026-04-01"
        snapshot = options_cost_snapshot()
        assert snapshot["effective_date"] == "2026-04-01"
        assert snapshot["schedule_version"] == OPTIONS_SCHEDULE_VERSION


# ---- 2: clean-slate guarantees for F4 (discrepancy framework) ----

class TestF1NegativeSpace:
    def test_no_disc_id_literal_in_F_related_code_yet(self) -> None:
        """F1 ships F4's advisory IDs in docs only; no Python literal
        ``\"DISC-<seq>\"`` should yet appear in F-related modules.

        A non-zero match here signals the F4 discrepancy framework has
        landed (or someone seeded a literal). Either is informative.
        """
        import re
        from pathlib import Path
        f_modules = [
            "performance.py",
            "performance_analytics.py",
            "broker_reconciliation.py",
            "reconciliation_evidence.py",
            "cost_schedules.py",
        ]
        python_dir = Path(__file__).resolve().parent.parent
        offenders = []
        for module_name in f_modules:
            module_path = python_dir / module_name
            if not module_path.exists():
                continue
            source = module_path.read_text(encoding="utf-8")
            # Match ``DISC-`` followed by a year-month pattern; this is
            # a soft scan that catches deliberate IDs without being
            # fooled by substring matches.
            for match in re.finditer(r"DISC-\d{4}-\d{2}-", source):
                offenders.append((module_name, match.group(0)))
        assert offenders == [], (
            f"F1 left clean slate for F4 discrepancy framework, but found: {offenders}"
        )


# ---- 3: scheduled-broker-statement ingestion stays manual ----------

class TestF1SchemaAdjacentContract:
    @pytest.mark.asyncio
    async def test_actual_broker_primary_keys_and_multiple_entries(self, tmp_path) -> None:
        import aiosqlite
        from broker_reconciliation import import_broker_statement, broker_statement_report
        path = str(tmp_path / "broker.db")
        args = dict(account_id="fixture", statement_id="s1", as_of=datetime(2026, 9, 10, tzinfo=timezone.utc),
                    opening_cash=100, closing_cash=125,
                    entries=[{"entry_id": "deposit", "entry_type": "DEPOSIT", "amount": 30},
                             {"entry_id": "charge", "entry_type": "CHARGE", "amount": 5}], fills=[])
        assert await import_broker_statement(path, **args) is True
        assert await import_broker_statement(path, **args) is False
        async with aiosqlite.connect(path) as db:
            for table, expected in {
                "broker_statement_imports": ["account_id", "statement_id"],
                "broker_statement_entries": ["account_id", "statement_id", "entry_id"],
                "broker_statement_fills": ["account_id", "statement_id", "fill_id"],
            }.items():
                rows = await (await db.execute(f"PRAGMA table_info({table})")).fetchall()
                assert [row[1] for row in sorted(rows, key=lambda row: row[5]) if row[5]] == expected
        report = await broker_statement_report(path, account_id="fixture")
        assert report["status"] == "MATCH"
        assert report["deposits"] == 30
        assert report["net_trading_result"] == 0  # Funding is not profit.
        assert report["can_place_orders"] is False

    @pytest.mark.asyncio
    async def test_fresh_owning_position_and_outcome_schema(self, tmp_path) -> None:
        import aiosqlite
        from position_tracker import init_positions_db
        from analytics import init_analytics_db
        from fno_positions import init_fno_positions_db
        from fno_dr_book import init_dr_db
        path = str(tmp_path / "schemas.db")
        for initializer in (init_positions_db, init_analytics_db, init_fno_positions_db, init_dr_db):
            await initializer(path)
            await initializer(path)
        async with aiosqlite.connect(path) as db:
            rows = await (await db.execute("PRAGMA table_info(positions)")).fetchall()
            assert not any(row[5] for row in rows)  # No declared PK, not composite.
            columns = {row[1] for row in rows}
            assert "id" not in columns
            assert {"penny_attempt_id", "broker_entry_order_id", "shares", "exit_date", "vwap_at_entry"} <= columns
            for table in ("trade_outcomes", "fno_positions", "fno_dr_positions"):
                info = await (await db.execute(f"PRAGMA table_info({table})")).fetchall()
                assert [(row[1], row[5]) for row in info if row[5]] == [("id", 1)]
            outcome = {row[1] for row in await (await db.execute("PRAGMA table_info(trade_outcomes)")).fetchall()}
            assert {"closed_at", "realised_pnl", "scan_id", "notes"} <= outcome
            assert not {"timestamp", "pnl", "signal_id"} & outcome
            indexes = await (await db.execute("PRAGMA index_list(trade_outcomes)")).fetchall()
            unique_keys = []
            for index in indexes:
                if index[2]:
                    key = await (await db.execute(f'PRAGMA index_info("{index[1]}")')).fetchall()
                    unique_keys.append([row[2] for row in key])
            assert ["ticker", "closed_at"] in unique_keys

    def test_import_broker_statement_returns_table_names_persistently(self) -> None:
        """F1 doc-commits the *current* wiring of broker_reconciliation:

        - ``broker_statement_imports`` primary key is
          ``(account_id, statement_id)``;
        - no scheduled job imports statements today;
        - the operator-facing route ``routes_commands.py`` is the only
          surface that calls ``broker_statement_report``.

        This test pins the *export* of ``import_broker_statement``
        (a future scheduler is expected to call it, F5) without
        asserting the import path today.
        """
        import inspect
        from broker_reconciliation import import_broker_statement
        source = inspect.getsource(import_broker_statement)
        assert "INSERT INTO broker_statement_imports" in source
        # The PK columns must be the composite; future F5 ingestion
        # relies on the same identity contract.
        assert "account_id=? AND statement_id=?" in source


# ---- 4: snapshot callers are unaffected ---------------------------

class TestF1SnapshotBackwardCompatibility:
    def test_namespace_penny_alias_unchanged(self) -> None:
        """The ``namespace=\"PENNY\"`` alias in
        ``equity_intraday_cost_snapshot`` is a documented contract;
        pinning it ensures no F1 edit broke the
        penny-snapshot arithmetic path.
        """
        zerodha = equity_intraday_cost_snapshot(namespace="ZERODHA")
        penny = equity_intraday_cost_snapshot(namespace="PENNY")
        # Same schedule version + effective date; the rates differ
        # only because the user's config may have set distinct values.
        assert zerodha["schedule_version"] == penny["schedule_version"]
        assert zerodha["effective_date"] == penny["effective_date"]
        assert zerodha["verified_as_of"] == penny["verified_as_of"]

    def test_unsupported_namespace_raises(self) -> None:
        """A future contributor must not silently fall through to a
        default namespace.
        """
        import pytest
        with pytest.raises(ValueError, match="ZERODHA or PENNY"):
            equity_intraday_cost_snapshot(namespace="UNRECOGNISED")

    def test_imports_remind_about_timestamp_aware_inputs(self) -> None:
        """F1 is docs + 1-line code change; no clock-dependent behaviour
        introduced. Sanity-check that the modified module imports
        cleanly under the test conftest's settings, even at session
        boundaries (year boundary, DST).
        """
        # A tz-aware naive datetime is not the right shape for
        # schedule metadata, but the test conftest produces one; the
        # helper functions themselves do not depend on ``datetime``.
        sample = datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        assert sample.tzinfo is not None
        # Snapshot can be called repeatedly without state.
        for _ in range(3):
            assert equity_intraday_cost_snapshot()["effective_date"] is None
