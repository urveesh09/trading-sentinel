"""[WORKFLOW-G 2026-09-13] Session-phase placeholder acceptance (forward-compat for J).

Closes gap #6 of 6 from
``docs/2026-09-13-workflow-g-state-of-codebase-audit.md`` §6.

Plan §14 puts workstream J (CAS and market-session correctness) ahead
of any session-aware G rollout: J owns the canonical NSE/BSE/SEBI phase
inventory that G will eventually consume. Today G does not have the
ground truth, so this slice commits a *typed placeholder* that:

1. declares ``_SESSION_PHASE_UNKNOWN = "UNKNOWN"``;
2. exposes a single helper ``stamp_session_phase(observation_at=...)``
   with a signature already shaped for J's eventual classifier;
3. threads the placeholder through two run-manifest sites so J's
   eventual real classifier only has to replace one function body,
   not every call site.

The schema on disk is unchanged: the placeholder lives only inside the
``manifest_json`` JSON column of ``proactive_shadow_runs`` and
``proactive_shadow_research_runs``. J's real session classifier will
later add an additive ``session_phase TEXT NULL`` column on the trial
rows; this slice preserves that optionality without predetermining the
shape.

This file proves:

1. The constant ships at the named value.
2. ``stamp_session_phase`` is **pure** (no I/O, no clock) and **total**
   (returns a known string for any input, including None).
3. The helper's signature is keyword-only so callers can't accidentally
   pass it positionally and break the J migration contract.
4. The manifests emitted by ``run_shadow_workflow`` and
   ``run_shadow_research_comparison`` carry the placeholder key with
   the expected ``"UNKNOWN"`` value.
"""
from __future__ import annotations

import inspect
import json
from datetime import datetime, timedelta, timezone

import aiosqlite
import pytest
import pytest_asyncio

from proactive_intelligence import (
    LEGACY_DEFAULT_V1_RUN_ID,  # noqa: F401 -- import-shape smoke
    ShadowProposal,
    _SESSION_PHASE_UNKNOWN,
    _proposal_id,
    init_proactive_intelligence,
    run_shadow_research_comparison,
    run_shadow_workflow,
    stamp_session_phase,
)


# ---- 1: constant shape and value ---------------------------------------

def test_session_phase_unknown_constant_value() -> None:
    """A rename would orphan every prior manifest carrying the literal."""
    assert _SESSION_PHASE_UNKNOWN == "UNKNOWN"
    assert isinstance(_SESSION_PHASE_UNKNOWN, str)


# ---- 2: helper purity and totality ------------------------------------

class TestStampSessionPhase:
    def test_returns_unknown_for_arbitrary_datetime(self) -> None:
        out = stamp_session_phase(observation_at=datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc))
        assert out == "UNKNOWN"

    def test_returns_unknown_for_naive_datetime(self) -> None:
        out = stamp_session_phase(observation_at=datetime(2026, 9, 13, 10, 0))
        assert out == "UNKNOWN"

    def test_returns_unknown_for_none(self) -> None:
        out = stamp_session_phase(observation_at=None)
        assert out == "UNKNOWN"

    def test_returns_string_type(self) -> None:
        assert isinstance(stamp_session_phase(observation_at=None), str)


# ---- 3: helper signature ----------------------------------------------

def test_helper_signature_uses_keyword_only_observation_at() -> None:
    """J's replacement must be a drop-in; preserve the keyword-only shape."""
    sig = inspect.signature(stamp_session_phase)
    params = list(sig.parameters.values())
    assert len(params) == 1
    assert params[0].name == "observation_at"
    assert params[0].kind == inspect.Parameter.KEYWORD_ONLY


def test_helper_source_does_not_call_io_or_clock() -> None:
    """The helper is pure; no DB, no clock, no random, no settings."""
    src = inspect.getsource(stamp_session_phase)
    forbidden = ("open(", "connect(", "datetime.now", "time.", "random.", "settings.")
    leaks = [tok for tok in forbidden if tok in src]
    assert leaks == [], f"placeholder uses forbidden tokens: {leaks}"


# ---- 4: integration via run manifests ---------------------------------

def _bars(epoch: datetime, count: int = 21, instrument: str = "SYNTH:PHASE") -> list:
    return [{
        "timestamp": (epoch + i * timedelta(minutes=15)).isoformat(),
        "open": 100 + i * 0.1, "high": 101 + i * 0.1,
        "low": 99 + i * 0.1, "close": 100 + i * 0.1,
        "volume": 100,
    } for i in range(count)]


def _proposal(epoch: datetime, instrument: str = "SYNTH:PHASE") -> ShadowProposal:
    common = dict(entry=100.0, stop=95.0, target=110.0,
                  valid_until=epoch + timedelta(minutes=30),
                  score=1.0, required_capital=100.0, reason="phase-fixture",
                  signal_at=epoch, data_cutoff=epoch,
                  entry_deadline=epoch + timedelta(minutes=30),
                  holding_deadline=epoch + timedelta(hours=4))
    return ShadowProposal(_proposal_id("trend_pullback_v1", instrument, epoch),
                          "trend_pullback_v1", instrument, **common)


@pytest_asyncio.fixture
async def db_setup(db_path):
    await init_proactive_intelligence(db_path)
    return db_path


@pytest.mark.asyncio
async def test_run_workflow_manifest_records_session_phase_unknown(db_setup):
    """The ``proactive_shadow_runs.manifest_json`` carries ``session_phase = \"UNKNOWN\"``."""
    db_path = db_setup
    epoch = datetime(2026, 9, 13, 9, 30, tzinfo=timezone.utc)
    result = await run_shadow_workflow(
        db_path,
        account_id="phase-account",
        run_id="phase-run-v1",
        universe={_proposal(epoch).instrument: _bars(epoch)},
        now=epoch,
    )
    # The manifest persists under the storage_account_id (= run_key) the
    # runner resolved; it appears in the manifest dict as ``account_id``
    # and ``run_id`` columns on the row.
    run_key = result["manifest"]["account_id"] if "manifest" in result else None
    # The manifest columns are read by row; the dict shape varies across
    # path versions, so just READ the only row whose run_id matches.
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT manifest_json FROM proactive_shadow_runs "
            "WHERE run_id = ? ORDER BY created_at DESC LIMIT 1",
            ("phase-run-v1",),
        ) as cursor:
            row = await cursor.fetchone()
    assert row is not None, "run manifest must persist"
    manifest = json.loads(row[0])
    assert manifest.get("session_phase") == "UNKNOWN", (
        f"run_workflow manifest missing session_phase, keys: {list(manifest)}"
    )


@pytest.mark.asyncio
async def test_run_research_comparison_manifest_records_session_phase_unknown(db_setup):
    """The ``proactive_shadow_research_runs.manifest_json`` carries ``session_phase = \"UNKNOWN\"``."""
    db_path = db_setup
    epoch = datetime(2026, 9, 13, 9, 30, tzinfo=timezone.utc)
    proposal = _proposal(epoch, instrument="SYNTH:PHASE2")
    await run_shadow_research_comparison(
        db_path,
        research_run_id="phase-research-v1",
        proposals=[proposal],
        future_bars={proposal.instrument: _bars(epoch, instrument="SYNTH:PHASE2")},
        cash_per_trial=1000.0,
    )
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT manifest_json FROM proactive_shadow_research_runs WHERE research_run_id=?",
            ("phase-research-v1",),
        ) as cursor:
            row = await cursor.fetchone()
    assert row is not None, "research manifest must persist"
    manifest = json.loads(row[0])
    assert manifest.get("session_phase") == "UNKNOWN", (
        f"research manifest missing session_phase, keys: {list(manifest)}"
    )
