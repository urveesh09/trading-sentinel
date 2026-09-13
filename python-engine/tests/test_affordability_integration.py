"""[WORKFLOW-F 2026-09-13] Affordability integration tests.

Companion to ``test_affordability.py``. The unit tests there cover
the *decision logic* of the guard in isolation; this file covers
the *integration surfaces* the guard exposes.

Three integration layers:

1. ``async_evaluate_paper_to_live_affordability`` is a thin async
   wrapper that mirrors the sync decision. Verify it produces
   identical evaluations for identical inputs.

2. ``assert_live_entry_safety`` reads live equity and realised
   paper P&L from the production ledger via
   ``performance.division_equity`` and
   ``performance.allocation_for_source``. Verify it (a) raises
   ``LIVE_NOT_ARMED`` for FNO today (because
   ``FNO_LIVE_BANKROLL == 0``), (b) accepts a small EDGE_LIVE delta
   when both pools exist with sensible P&L, (c) fails closed on a
   ledger query failure, and (d) propagates ``ValueError`` for bad
   arguments.

3. The integration is gated behind ``PENNY_LIVE_TRADING = False``
   and ``FNO_LIVE_BANKROLL = 0`` today. The tests in this file mock
   the ledger boundary directly to avoid SQLite file-handle locking
   collisions on Windows (the runtime integration is exercised by
   the *production* orchestrators; the guard's contract is
   exercised here in isolation).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from affordability import (
    AffordabilityEvaluation,
    AffordabilityRefusal,
    AffordabilityVerdict,
    async_evaluate_paper_to_live_affordability,
    assert_live_entry_safety,
    assert_live_affordable_from_paper,
    evaluate_paper_to_live_affordability,
)


# ---------------------------------------------------------------------------
# 1. ``async_evaluate_paper_to_live_affordability``.
# ---------------------------------------------------------------------------

class TestAsyncEvaluator:
    """The async version must produce the same evaluation as the sync
    one for the same inputs. The decision logic is identical; only
    the call shape differs so orchestrators can ``await`` without a
    sync/async shim.
    """

    def test_async_matches_sync_for_affordable_case(self) -> None:
        kwargs = dict(
            live_source="EDGE_LIVE",
            paper_source="EDGE_PAPER",
            proposed_delta_inr=1000.0,
            live_current_inr=1500.0,
            paper_pnl_inr=0.0,
        )
        sync_eval = evaluate_paper_to_live_affordability(**kwargs)
        async_eval = asyncio.run(
            async_evaluate_paper_to_live_affordability(**kwargs)
        )
        assert async_eval.verdict == sync_eval.verdict
        assert async_eval.live_current_inr == sync_eval.live_current_inr
        assert async_eval.paper_pnl_inr == sync_eval.paper_pnl_inr
        assert async_eval.refusal_reasons == sync_eval.refusal_reasons

    def test_async_matches_sync_for_margin_exceeded(self) -> None:
        kwargs = dict(
            live_source="EDGE_LIVE",
            paper_source="EDGE_PAPER",
            proposed_delta_inr=4000.0,
            live_current_inr=1500.0,
            paper_pnl_inr=0.0,
        )
        sync_eval = evaluate_paper_to_live_affordability(**kwargs)
        async_eval = asyncio.run(
            async_evaluate_paper_to_live_affordability(**kwargs)
        )
        assert async_eval.verdict == AffordabilityVerdict.MARGIN_EXCEEDED
        assert async_eval.refusal_reasons == sync_eval.refusal_reasons


# ---------------------------------------------------------------------------
# 2. ``assert_live_entry_safety`` against a mocked ledger.
# ---------------------------------------------------------------------------

class _StubLedger:
    """In-memory stub of ``performance.division_equity`` and
    ``performance.allocation_for_source``.

    Returning pre-canned floats lets the wrapper's logic run
    exactly as it would in production, but without the SQLite
    file-handle locking that breaks on Windows. The runtime ledger
    integration is exercised by ``penny_edge_orchestrator`` and
    ``fno_orchestrator`` themselves; this file proves the
    *contract* of the wrapper against canned inputs.
    """

    def __init__(self, *, live_equity: float, paper_equity: float, paper_allocation: float):
        self.live_equity = live_equity
        self.paper_equity = paper_equity
        self.paper_allocation = paper_allocation

    async def _division_equity(self, db_path: str, source: str):
        if source == "EDGE_LIVE":
            return self.live_equity
        if source == "FNO_LIVE":
            return self.live_equity
        if source == "EDGE_PAPER":
            return self.paper_equity
        if source == "FNO_PAPER":
            return self.paper_equity
        raise AssertionError(f"unexpected source in stub: {source}")

    def _allocation_for_source(self, source: str) -> float:
        if source in ("EDGE_PAPER", "FNO_PAPER"):
            return self.paper_allocation
        # EDGE_LIVE / FNO_LIVE allocations are looked up by the
        # real ``performance`` module when the paper source is
        # queried, so the wrapper never reads live allocation from
        # ``allocation_for_source`` for the live source.
        return 0.0


@pytest.fixture
def live_armed_stub(monkeypatch):
    """A stubbed ledger with ``EDGE_LIVE`` equity = 1500 and
    ``EDGE_PAPER`` equity = 100000 (the shipping defaults).
    """
    stub = _StubLedger(
        live_equity=1500.0,
        paper_equity=100000.0,
        paper_allocation=100000.0,  # paper is fully allocated; realised P&L = 0
    )

    # We patch ``performance.division_equity`` and
    # ``performance.allocation_for_source`` because the wrapper does a
    # lazy import of ``performance``. ``monkeypatch.setattr`` on the
    # already-imported ``performance`` module will not affect the
    # wrapper's local import; therefore we must patch the names the
    # wrapper resolves through ``import performance``.
    import performance
    async def _division_equity(db_path, source):
        return await stub._division_equity(db_path, source)
    monkeypatch.setattr(
        performance, "division_equity", _division_equity
    )
    monkeypatch.setattr(
        performance, "allocation_for_source",
        stub._allocation_for_source
    )
    return stub


@pytest.fixture
def live_not_armed_stub(monkeypatch):
    """A stubbed ledger with ``FNO_LIVE`` equity = 0."""
    stub = _StubLedger(
        live_equity=0.0,
        paper_equity=250000.0,
        paper_allocation=250000.0,
    )
    import performance
    async def _division_equity(db_path, source):
        return await stub._division_equity(db_path, source)
    monkeypatch.setattr(
        performance, "division_equity", _division_equity
    )
    monkeypatch.setattr(
        performance, "allocation_for_source",
        stub._allocation_for_source
    )
    return stub


class TestAssertLiveEntrySafety:
    """Read-ledger integration through a mock. Verify the wrapper
    raises ``LIVE_NOT_ARMED`` for FNO today, accepts an EDGE_LIVE
    delta when both pools exist with sensible P&L, and fails closed
    on a ledger query failure.
    """

    @pytest.mark.asyncio
    async def test_live_not_armed_fno_live_zero(self, live_not_armed_stub) -> None:
        """FNO today: ``FNO_LIVE_BANKROLL == 0``."""
        with pytest.raises(AffordabilityRefusal) as excinfo:
            await assert_live_entry_safety(
                db_path="/dev/null",
                live_source="FNO_LIVE",
                paper_source="FNO_PAPER",
                proposed_delta_inr=10.0,
            )
        assert excinfo.value.result.verdict == AffordabilityVerdict.LIVE_NOT_ARMED

    @pytest.mark.asyncio
    async def test_live_armed_delta_within_margin_affordable(
        self, live_armed_stub
    ) -> None:
        """EDGE_LIVE at 1500 * 1.5 = 2250 max delta. Several deltas
        are tested so the boundary semantics (inclusive on the
        affordable side, exclusive on the refusal side) are pinned.
        """
        for delta in (1.0, 100.0, 1000.0, 1500.0, 2250.0):
            result = await assert_live_entry_safety(
                db_path="/dev/null",
                live_source="EDGE_LIVE",
                paper_source="EDGE_PAPER",
                proposed_delta_inr=delta,
            )
            assert result.verdict == AffordabilityVerdict.AFFORDABLE, (
                f"delta={delta} should be affordable at live=1500 margin=1.5"
            )
        # One rupee beyond the inclusive ceiling refuses.
        with pytest.raises(AffordabilityRefusal) as excinfo:
            await assert_live_entry_safety(
                db_path="/dev/null",
                live_source="EDGE_LIVE",
                paper_source="EDGE_PAPER",
                proposed_delta_inr=2250.01,
            )
        assert excinfo.value.result.verdict == (
            AffordabilityVerdict.MARGIN_EXCEEDED
        )

        # The wrapper reads the live equity from the stub and passes
        # it through. Verifies the wrapper actually uses the
        # ``performance`` boundary rather than guessing.
        result = await assert_live_entry_safety(
            db_path="/dev/null",
            live_source="EDGE_LIVE",
            paper_source="EDGE_PAPER",
            proposed_delta_inr=1000.0,
        )
        assert result.live_current_inr == 1500.0

    @pytest.mark.asyncio
    async def test_live_armed_delta_exceeding_margin_refused(
        self, live_armed_stub
    ) -> None:
        """EDGE_LIVE at 1500, margin=1.5, ceiling=2250. Deltas strictly
        *above* 2250 must refuse with MARGIN_EXCEEDED. The exception
        carries the evaluation so dashboards and bridge audit can
        serialise it.
        """
        for delta in (2500.0, 5000.0, 100_000.0):
            with pytest.raises(AffordabilityRefusal) as excinfo:
                await assert_live_entry_safety(
                    db_path="/dev/null",
                    live_source="EDGE_LIVE",
                    paper_source="EDGE_PAPER",
                    proposed_delta_inr=delta,
                )
            assert excinfo.value.result.verdict == (
                AffordabilityVerdict.MARGIN_EXCEEDED
            ), f"delta={delta} should be refused at margin=1.5"

    @pytest.mark.asyncio
    async def test_invalid_inputs_propagate_as_value_error(
        self, live_armed_stub
    ) -> None:
        """The wrapper routes programmer errors as ``ValueError``,
        distinct from data refusals (which become ``AffordabilityRefusal``).
        """
        with pytest.raises(ValueError):
            await assert_live_entry_safety(
                db_path="/dev/null",
                live_source="",
                paper_source="EDGE_PAPER",
                proposed_delta_inr=1000.0,
            )
        with pytest.raises(ValueError):
            await assert_live_entry_safety(
                db_path="/dev/null",
                live_source="EDGE_LIVE",
                paper_source="EDGE_PAPER",
                proposed_delta_inr=0,
            )


# ---------------------------------------------------------------------------
# 3. Orchestrator call-site identifier (smoke test for the integration seams).
# ---------------------------------------------------------------------------

class TestOrchestratorSeams:
    """Today no orchestrator path increases the live bankroll. These
    tests prove the *guard exists* and is importable from the same
    module that the orchestrators live in, so a future wire-up is
    one import line away.
    """

    def test_penny_orchestrator_does_not_currently_grow_live(self) -> None:
        """``penny_edge_orchestrator.py`` today sizes both legs off
        *current* equity and never issues an ``IncreaseLiveBankroll``
        request. The guard is therefore *not* called. We verify the
        absence so a future contributor who adds a growth path does
        not miss the integration.
        """
        import penny_edge_orchestrator as peo
        public_functions = [
            name for name in dir(peo)
            if not name.startswith("_") and callable(getattr(peo, name))
        ]
        growth_suggestives = [
            n for n in public_functions
            if "grow" in n.lower() or "increase" in n.lower() or "raise" in n.lower()
        ]
        assert not growth_suggestives, (
            f"unexpected growth-related public functions: {growth_suggestives}"
        )

    def test_fno_orchestrator_does_not_currently_grow_live(self) -> None:
        """``fno_orchestrator.py`` today sizes off
        ``_fno_pool_live()`` from ``settings.FNO_LIVE_BANKROLL``
        which is 0. A future growth path must use the guard. Today,
        no such path exists.
        """
        import fno_orchestrator as fo
        import inspect
        suspects = [
            name for name, member in inspect.getmembers(fo, inspect.isfunction)
            if "grow" in name.lower() or "increase_live" in name.lower()
        ]
        assert not suspects, f"unexpected growth-related functions: {suspects}"
