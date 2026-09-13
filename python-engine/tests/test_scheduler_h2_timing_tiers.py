"""[WORKFLOW-H H2 2026-09-13] Scheduler timing priority-tier acceptance.

Closes H2 of workstream H per
``docs/2026-09-13-workflow-f-state-of-codebase-audit.md`` section 13
future plan and ``docs/NEXT_AGENT_PLAN.md`` row H.

Acceptance coverage for the priority-tier breakdown added to
``python-engine/scheduler_telemetry.py``.

[WHY-THIS-EXISTS 2026-09-13]
  Pre-fix, ``scheduler_timing_report`` grouped by literal
  ``job_id`` but not by the §12 priority tier (exit, advice,
  scan, research). The operator could not see "the slowest stage
  across all exit-tier jobs" vs "the slowest scan-tier job"; the
  tail-latency signal was buried under a flat per-job roll-up.
  H2 ships ``JOB_TIER_MAP`` and ``by_tier`` roll-up so the
  operator can see p50/p95/max + per-stage aggregation per
  priority tier. A tier with zero jobs returns ``None`` (not 0)
  so the UI can distinguish "unavailable" from "instant", per
  the §12 acceptance *"UI fixture covers unavailable and zero
  distinctly."*
"""
from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime, timezone
from typing import Any, Dict

import pytest
import pytest_asyncio

from scheduler_telemetry import (
    JOB_TIER_MAP,
    TIER_ORDER,
    _aggregate_by_tier,
    _percentiles,
    _tier_for,
    init_scheduler_telemetry,
    record_scheduler_event,
    scheduler_timing_report,
)


# ---- helpers ---------------------------------------------------------------

@pytest_asyncio.fixture
async def telemetry_db(tmp_path):
    """A fresh telemetry DB per test."""
    db = str(tmp_path / "telemetry.db")
    await init_scheduler_telemetry(db)
    yield db


async def _record(
    db: str,
    *,
    job_id: str,
    elapsed: float = 1.0,
    result: str = "COMPLETED",
    stage_durations: Dict[str, float] = None,
    reason: str = None,
):
    """Insert one telemetry row with sensible defaults."""
    now = datetime.now(timezone.utc)
    await record_scheduler_event(
        db,
        job_id=job_id,
        event_kind="EXECUTION",
        result=result,
        started_at=now,
        ended_at=now,
        elapsed_seconds=elapsed,
        reason=reason,
        stage_durations=stage_durations or {},
        retention=100,
    )


# ---- JOB_TIER_MAP ----------------------------------------------------------

class TestJobTierMap:
    def test_every_registered_penny_job_maps_to_a_known_tier(self) -> None:
        """Every penny subsystem job_id in scheduler_setup must be in
        JOB_TIER_MAP. A future agent who adds a new penny job must
        add it to the map -- this test catches the silent drop.
        """
        penny_jobs = {
            "penny_premarket_report",
            "penny_regime_compute",
            "penny_regime_refresh",
            "penny_scan_interval",
            "penny_connors_scan",
            "penny_edge_scan",
            "penny_edge_exit",
            "penny_eod_check",
            "penny_force_close_mis",
            "penny_daily_attribution",
            "penny_heatmap",
            "penny_eod_digest",
            "penny_hourly_report",
            "penny_accept_watchdog",
        }
        for job in penny_jobs:
            assert job in JOB_TIER_MAP, (
                f"penny job {job!r} missing from JOB_TIER_MAP; "
                f"add it explicitly per plan §12 taxonomy"
            )

    def test_every_registered_fno_job_maps_to_a_known_tier(self) -> None:
        fno_jobs = {"fno_tick", "fno_hourly_report", "fno_accept_watchdog"}
        for job in fno_jobs:
            assert job in JOB_TIER_MAP

    def test_every_registered_partner_job_maps_to_a_known_tier(self) -> None:
        partner_jobs = {
            "partner_scan_tick",
            "partner_manual_advisory_tick",
            "partner_manual_advisory_lifecycle_tick",
            "partner_analytics_tick",
            "partner_morning_brief",
            "partner_eod_wrap",
            "partner_rv_refresh",
            "partner_input_refresh",
            "partner_hedge_tick",
            "partner_hedge_delivery_recovery",
            "partner_hedge_morning_summary",
            "partner_hedge_eod_summary",
            "partner_hedge_phase2_tick",
            "partner_hedge_phase3_tick",
        }
        for job in partner_jobs:
            assert job in JOB_TIER_MAP

    def test_every_registered_system_job_maps_to_a_known_tier(self) -> None:
        system_jobs = {
            "premarket_login_nudge",
            "daily_bootstrap_tick",
            "circuit_breaker_enforce",
        }
        for job in system_jobs:
            assert job in JOB_TIER_MAP

    def test_unrecognised_job_id_lands_in_other(self) -> None:
        assert _tier_for("future_unknown_job_xyz") == "other"
        assert _tier_for("") == "other"
        assert _tier_for("definitely_not_a_real_job") == "other"

    def test_tier_order_lists_priority_order(self) -> None:
        """§12 specifies the priority order: exit > advice > scan > research.
        TIER_ORDER must reflect that. ``system`` and ``other`` come
        last because they are meta-buckets.
        """
        assert TIER_ORDER.index("exit") < TIER_ORDER.index("advice")
        assert TIER_ORDER.index("advice") < TIER_ORDER.index("scan")
        assert TIER_ORDER.index("scan") < TIER_ORDER.index("research")

    def test_every_tier_value_in_map_is_in_tier_order_or_other(self) -> None:
        for tier in JOB_TIER_MAP.values():
            assert tier in TIER_ORDER or tier == "other", (
                f"unknown tier {tier!r} in JOB_TIER_MAP"
            )


# ---- by_tier output shape --------------------------------------------------

class TestByTierShape:
    @pytest.mark.asyncio
    async def test_by_tier_key_present(self, telemetry_db: str) -> None:
        await _record(telemetry_db, job_id="penny_edge_exit")
        rep = await scheduler_timing_report(telemetry_db, limit=100)
        assert "by_tier" in rep
        assert isinstance(rep["by_tier"], dict)

    @pytest.mark.asyncio
    async def test_by_tier_contains_all_five_tiers_plus_other(
        self, telemetry_db: str,
    ) -> None:
        """Even with no data, all six tiers (exit, advice, scan,
        research, system, other) must be present so the dashboard
        can iterate without checking for missing keys.
        """
        rep = await scheduler_timing_report(telemetry_db, limit=100)
        for tier in ("exit", "advice", "scan", "research", "system", "other"):
            assert tier in rep["by_tier"], (
                f"tier {tier!r} missing from by_tier; "
                f"the §12 dashboard iterates over all six"
            )

    @pytest.mark.asyncio
    async def test_empty_tier_returns_none_not_zero(self, telemetry_db: str) -> None:
        """A tier with zero jobs returns None (not 0) for all
        numeric fields, per §12 acceptance: "UI fixture covers
        unavailable and zero distinctly."
        """
        await _record(telemetry_db, job_id="penny_edge_exit")
        rep = await scheduler_timing_report(telemetry_db, limit=100)
        # ``advice`` and ``scan`` etc. have no jobs.
        for empty_tier in ("advice", "scan", "research", "system"):
            t = rep["by_tier"][empty_tier]
            assert t["job_count"] == 0
            assert t["elapsed_seconds"]["p50"] is None
            assert t["elapsed_seconds"]["p95"] is None
            assert t["elapsed_seconds"]["max"] is None
            assert t["runs"] == 0
            assert t["executed_runs"] == 0
            assert t["rejected"] == 0
            assert t["in_flight"] == 0
            assert t["results"] == {}
            assert t["stage_durations"] == {}
            # The note is the operator-visible signal.
            assert "unavailable" in t["note"].lower(), (
                f"empty tier {empty_tier!r} must carry a note "
                f"telling the UI to render as 'unavailable'"
            )

    @pytest.mark.asyncio
    async def test_populated_tier_computes_percentiles(
        self, telemetry_db: str,
    ) -> None:
        """A populated tier's elapsed_seconds is computed from the
        UNION of samples across jobs (NOT the median of per-job
        medians).
        """
        # Three runs of penny_edge_exit (exit tier) at 1s, 2s, 3s.
        # The union percentiles: sorted [1, 2, 3] -> p50=2.0, max=3.0.
        for elapsed in (1.0, 2.0, 3.0):
            await _record(telemetry_db, job_id="penny_edge_exit", elapsed=elapsed)
        rep = await scheduler_timing_report(telemetry_db, limit=100)
        exit_t = rep["by_tier"]["exit"]
        assert exit_t["job_count"] == 1
        assert exit_t["jobs"] == ["penny_edge_exit"]
        assert exit_t["runs"] == 3
        assert exit_t["executed_runs"] == 3
        # Per-tier percentiles from the union of three samples [1, 2, 3].
        assert exit_t["elapsed_seconds"]["p50"] == pytest.approx(2.0, rel=0, abs=1e-6)
        assert exit_t["elapsed_seconds"]["max"] == pytest.approx(3.0, rel=0, abs=1e-6)

    @pytest.mark.asyncio
    async def test_populated_tier_aggregates_multiple_jobs(
        self, telemetry_db: str,
    ) -> None:
        """A populated tier with multiple jobs aggregates ALL
        samples across jobs.
        """
        # penny_edge_exit (exit) at 4.0; penny_force_close_mis (exit) at 6.0.
        # Union percentiles: [4, 6] -> p50 = either 4 or 6 depending
        # on indexing; max = 6.
        await _record(telemetry_db, job_id="penny_edge_exit", elapsed=4.0)
        await _record(telemetry_db, job_id="penny_force_close_mis", elapsed=6.0)
        rep = await scheduler_timing_report(telemetry_db, limit=100)
        exit_t = rep["by_tier"]["exit"]
        assert exit_t["job_count"] == 2
        assert sorted(exit_t["jobs"]) == ["penny_edge_exit", "penny_force_close_mis"]
        assert exit_t["runs"] == 2
        assert exit_t["executed_runs"] == 2
        assert exit_t["elapsed_seconds"]["max"] == pytest.approx(6.0, rel=0, abs=1e-6)

    @pytest.mark.asyncio
    async def test_single_sample_returns_that_sample_unchanged(
        self, telemetry_db: str,
    ) -> None:
        await _record(telemetry_db, job_id="penny_hourly_report", elapsed=2.5)
        rep = await scheduler_timing_report(telemetry_db, limit=100)
        advice_t = rep["by_tier"]["advice"]
        # Single sample: p50 = p95 = max = that sample.
        assert advice_t["elapsed_seconds"]["p50"] == 2.5
        assert advice_t["elapsed_seconds"]["p95"] == 2.5
        assert advice_t["elapsed_seconds"]["max"] == 2.5

    @pytest.mark.asyncio
    async def test_stage_durations_aggregate_across_tier(
        self, telemetry_db: str,
    ) -> None:
        """Stage durations from every job in the tier are merged
        into per-stage percentiles. The slowest stage in the tier
        is the most actionable single signal.
        """
        # penny_edge_exit: kite_quote_fetch = 4.0, order_send = 1.0.
        # penny_force_close_mis: kite_quote_fetch = 6.0, order_send = 0.5.
        await _record(
            telemetry_db,
            job_id="penny_edge_exit",
            elapsed=5.0,
            stage_durations={"kite_quote_fetch": 4.0, "order_send": 1.0},
        )
        await _record(
            telemetry_db,
            job_id="penny_force_close_mis",
            elapsed=6.5,
            stage_durations={"kite_quote_fetch": 6.0, "order_send": 0.5},
        )
        rep = await scheduler_timing_report(telemetry_db, limit=100)
        exit_t = rep["by_tier"]["exit"]
        # Per-stage union: kite_quote_fetch [4.0, 6.0] -> max 6.0
        # order_send [1.0, 0.5] -> max 1.0
        assert exit_t["stage_durations"]["kite_quote_fetch"]["max"] == pytest.approx(6.0, rel=0, abs=1e-6)
        assert exit_t["stage_durations"]["order_send"]["max"] == pytest.approx(1.0, rel=0, abs=1e-6)

    @pytest.mark.asyncio
    async def test_rejected_runs_counted(self, telemetry_db: str) -> None:
        """The ``rejected`` counter is incremented when the
        event_kind is SCHEDULER_REJECTED (not when the result
        is REJECTED). This is the documented contract from the
        listener path; the per-tier roll-up inherits it.
        """
        # Insert directly via the DB to bypass record_scheduler_event's
        # event_kind=EXECUTION default; we want to simulate the
        # SCHEDULER_REJECTED event_kind that ``attach_scheduler_listener``
        # writes when APScheduler rejects an instance.
        import aiosqlite
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(telemetry_db) as db:
            await db.execute(
                "INSERT INTO scheduler_run_telemetry "
                "(run_id, boot_id, job_id, event_kind, scheduled_at, started_at, ended_at, "
                " elapsed_seconds, result, reason, stage_durations_json, created_at) "
                "VALUES (?, ?, ?, ?, NULL, NULL, NULL, NULL, ?, ?, ?, ?)",
                (
                    "test-reject-1",
                    "test-boot",
                    "penny_edge_exit",
                    "SCHEDULER_REJECTED",
                    "REJECTED",
                    "max_instances",
                    "{}",
                    now,
                ),
            )
            await db.commit()
        rep = await scheduler_timing_report(telemetry_db, limit=100)
        exit_t = rep["by_tier"]["exit"]
        assert exit_t["rejected"] == 1
        assert exit_t["results"]["REJECTED"] == 1
        # ``executed_runs`` does NOT increment on SCHEDULER_REJECTED.
        assert exit_t["executed_runs"] == 0

    @pytest.mark.asyncio
    async def test_results_merged_across_jobs(self, telemetry_db: str) -> None:
        """The ``results`` field is merged across jobs in a tier.
        """
        await _record(telemetry_db, job_id="penny_edge_exit", result="COMPLETED")
        await _record(telemetry_db, job_id="penny_force_close_mis", result="REJECTED")
        await _record(telemetry_db, job_id="penny_eod_digest", result="COMPLETED")
        rep = await scheduler_timing_report(telemetry_db, limit=100)
        exit_t = rep["by_tier"]["exit"]
        assert exit_t["results"]["COMPLETED"] == 2
        assert exit_t["results"]["REJECTED"] == 1

    @pytest.mark.asyncio
    async def test_unknown_job_lands_in_other_tier(self, telemetry_db: str) -> None:
        await _record(telemetry_db, job_id="future_unknown_xyz", elapsed=1.0)
        rep = await scheduler_timing_report(telemetry_db, limit=100)
        other_t = rep["by_tier"]["other"]
        assert other_t["job_count"] == 1
        assert other_t["jobs"] == ["future_unknown_xyz"]


# ---- operational_coverage integration -------------------------------------

class TestOperationalCoverageTierEntry:
    @pytest.mark.asyncio
    async def test_coverage_includes_tier_entries(
        self, telemetry_db, monkeypatch,
    ) -> None:
        """operational_coverage_report emits one entry per tier."""
        from operational_coverage import operational_coverage_report
        # Patch settings to use the test DB.
        from config import settings
        monkeypatch.setattr(settings, "DB_PATH", telemetry_db)
        await _record(telemetry_db, job_id="penny_edge_exit", elapsed=1.0)
        rep = await operational_coverage_report(telemetry_db)
        for tier in ("exit", "advice", "scan", "research", "system", "other"):
            assert f"scheduler_tier:{tier}" in rep["producers"], (
                f"tier entry scheduler_tier:{tier} missing from coverage"
            )
        exit_entry = rep["producers"]["scheduler_tier:exit"]
        assert exit_entry["counts"]["runs"] == 1
        assert exit_entry["counts"]["job_count"] == 1
        assert exit_entry["state"] == "OBSERVED"
        empty_entry = rep["producers"]["scheduler_tier:scan"]
        assert empty_entry["state"] == "UNCONFIGURED"
        assert empty_entry["reason"] == "no_jobs_in_tier"
        assert empty_entry["counts"]["job_count"] == 0


# ---- _percentiles invariants -----------------------------------------------

class TestPercentilesInvariants:
    def test_empty_returns_three_nones(self) -> None:
        out = _percentiles([])
        assert out == {"p50": None, "p95": None, "max": None}

    def test_single_sample(self) -> None:
        out = _percentiles([5.0])
        assert out == {"p50": 5.0, "p95": 5.0, "max": 5.0}

    def test_sorted_ascending(self) -> None:
        out = _percentiles([3.0, 1.0, 2.0])
        # Internal sort. p50 of [1,2,3] -> index 1 = 2.0. max = 3.0.
        assert out["max"] == 3.0
        assert out["p50"] == pytest.approx(2.0, rel=0, abs=1e-6)

    @pytest.mark.asyncio
    async def test_inf_rejected_at_rollup_layer(self) -> None:
        """Non-finite samples must not contaminate per-tier percentiles.

        The per-tier roll-up filters with ``math.isfinite`` BEFORE
        accumulating into the sample list; ``_percentiles`` itself
        is a low-level helper that does not enforce finite-input
        (it would be a behaviour change for existing callers).
        We exercise the roll-up-layer guard here.

        We insert TWO rows: one with a valid elapsed_seconds, one
        with elapsed_seconds=Inf. The defence must drop the Inf row
        so the percentile is computed from the valid sample only --
        not from {valid, Inf} (which would yield Inf max).
        """
        # Build a one-off DB inside this test.
        import tempfile
        import aiosqlite
        d = tempfile.mkdtemp()
        db = str(d) + "/inf.db"
        await init_scheduler_telemetry(db)
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(db) as conn:
            # Row 1: VALID elapsed_seconds = 2.0.
            await conn.execute(
                "INSERT INTO scheduler_run_telemetry "
                "(run_id, boot_id, job_id, event_kind, scheduled_at, started_at, ended_at, "
                " elapsed_seconds, result, reason, stage_durations_json, created_at) "
                "VALUES (?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?, ?, ?)",
                (
                    "valid-1", "boot", "penny_edge_exit", "EXECUTION",
                    2.0, "COMPLETED", None, "{}", now,
                ),
            )
            # Row 2: NON-FINITE elapsed_seconds = Inf.
            await conn.execute(
                "INSERT INTO scheduler_run_telemetry "
                "(run_id, boot_id, job_id, event_kind, scheduled_at, started_at, ended_at, "
                " elapsed_seconds, result, reason, stage_durations_json, created_at) "
                "VALUES (?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?, ?, ?)",
                (
                    "inf-1", "boot", "penny_edge_exit", "EXECUTION",
                    float("inf"), "COMPLETED", None, "{}", now,
                ),
            )
            await conn.commit()
        rep = await scheduler_timing_report(db, limit=100)
        exit_t = rep["by_tier"]["exit"]
        # Both rows are EXECUTION; executed_runs counts both.
        assert exit_t["executed_runs"] == 2
        # The percentile layer filters the Inf sample BEFORE
        # computing percentiles. With only the valid sample [2.0],
        # max == 2.0 -- NOT Inf.
        assert exit_t["elapsed_seconds"]["max"] == 2.0
        assert math.isfinite(exit_t["elapsed_seconds"]["max"])
        assert exit_t["elapsed_seconds"]["p50"] == 2.0
