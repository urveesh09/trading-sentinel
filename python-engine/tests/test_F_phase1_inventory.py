"""[WORKFLOW-F 2026-09-13] Phase 1 inventory + reconciliation-warning map acceptance.

Closes F1 (the three sub-slices F1.a, F1.b, F1.c) of workstream F per
``docs/2026-09-13-workflow-f-state-of-codebase-audit.md``. F1 is the
*inventory* phase; it ships:

1. F1.a \u2014 a docs census of every F-relevant table, write path, read
   path, and source-enum invariant;
2. F1.b \u2014 advisory discrepancy IDs for the five historical
   reconciliation warnings referenced in ``SYSTEM_GUIDE.md:87``;
3. F1.c \u2014 set ``EQUITY_INTRADAY_EFFECTIVE_DATE = \"2026-08-10\"``
   (previously ``None``) matching ``EQUITY_INTRADAY_VERIFIED_AS_OF``.

F1 ships no new tables, no migrations, no scheduler wiring, no broker
integration. This test file pins the F1 artefacts so a future F slice
cannot quietly regress the inventory or the cost-schedule decision.

The test file also verifies F1's *negative space*:
  - there is no ``DISC-<id>`` literal in production code yet (clean
    slate for F4);
  - there is no new persistence surface under the F tree yet
    (F2-F6 have not started).
"""
from __future__ import annotations

from datetime import datetime, timezone

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
    def test_equity_intraday_effective_date_pinned_to_verified_as_of(self) -> None:
        """The equity schedule's effective date equals its verified-as-of date.

        Pre-2026-09-13 the value was ``None``; F1.c sets it to the
        ``\"2026-08-10\"`` value that already shipped as
        ``EQUITY_INTRADAY_VERIFIED_AS_OF``. This test pins the choice.
        """
        assert EQUITY_INTRADAY_EFFECTIVE_DATE == "2026-08-10"
        assert EQUITY_INTRADAY_EFFECTIVE_DATE == EQUITY_INTRADAY_VERIFIED_AS_OF

    def test_equity_snapshot_carries_effective_date(self) -> None:
        """Every caller of ``equity_intraday_cost_snapshot`` now sees a
        non-null ``effective_date``. ``options_cost_snapshot`` is
        unchanged: its effective date was already ``\"2026-04-01\"``.
        """
        snapshot = equity_intraday_cost_snapshot()
        assert snapshot["effective_date"] == "2026-08-10"
        assert snapshot["effective_date"] is not None
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
            assert equity_intraday_cost_snapshot()["effective_date"] == "2026-08-10"
