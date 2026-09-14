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
    """[WORKFLOW-G 2026-09-13 → WORKFLOW-J.4 2026-09-13] Pre-J.4
    this class pinned ``"UNKNOWN"`` for every input. J.4 wires
    the helper to ``classify_session_phase`` so a real datetime
    resolves to a bounded phase; only ``None`` keeps
    ``"UNKNOWN"``. The class is renamed-and-repurposed to assert
    that bounded behaviour.
    """

    def test_returns_real_phase_for_aware_datetime(self) -> None:
        # Aware datetime: 12:00 UTC = 17:30 IST, AFTER the
        # 16:00 close on any weekday -> CLOSED. The classifier
        # resolves this exactly -- pinning CLOSED proves the
        # wire is active without ambiguity.
        out = stamp_session_phase(
            observation_at=datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
        )
        assert out == "CLOSED"
        assert out != "UNKNOWN"

    def test_returns_real_phase_for_naive_datetime(self) -> None:
        # Naive datetime is interpreted as UTC.
        # 04:00 UTC = 09:30 IST = mid-session.
        out = stamp_session_phase(
            observation_at=datetime(2026, 9, 14, 4, 0),
        )
        assert out == "CONTINUOUS_TRADING"
        assert out != "UNKNOWN"

    def test_returns_unknown_for_none(self) -> None:
        out = stamp_session_phase(observation_at=None)
        assert out == "UNKNOWN"

    def test_returns_string_type(self) -> None:
        assert isinstance(stamp_session_phase(observation_at=None), str)


# ---- 3: helper signature ----------------------------------------------

def test_helper_signature_uses_keyword_only_observation_at() -> None:
    """J.4 keeps the keyword-only shape on every parameter. The
    helper still has ``observation_at`` as the first / only
    required parameter; the new ``symbol``, ``is_derivative``,
    ``cas_eligible`` are appended with keyword-only kind so
    callers cannot accidentally pass them positionally.
    """
    sig = inspect.signature(stamp_session_phase)
    params = list(sig.parameters.values())
    # Pre-J.4 had 1 keyword-only parameter; J.4 keeps that
    # one as required and adds three more, all keyword-only
    # and all optional. The exact identity of the augmented
    # set is intentionally pinned: any further change is a
    # contract revision.
    names = [p.name for p in params]
    assert names == [
        "observation_at", "symbol", "is_derivative", "cas_eligible",
    ], f"signature drift; got {names}"
    assert all(
        p.kind == inspect.Parameter.KEYWORD_ONLY for p in params
    ), "every parameter must be keyword-only"
    # observation_at is required (no default); the rest are
    # optional so legacy single-kwarg callers keep working.
    assert params[0].default is inspect.Parameter.empty


def test_helper_source_does_not_call_io_or_clock() -> None:
    """The helper is pure; no DB, no clock, no random, no settings.

    We strip the docstring before checking so the test does
    not false-fail on docstring prose like ``datetime.now``
    and ``time.time`` that simply describe the constraint.
    Only real call-sites count.
    """
    import ast
    import re
    src = inspect.getsource(stamp_session_phase)
    # Drop the leading docstring block; what remains is the
    # implementation body. Tests are about the implementation,
    # not the documentation that names the constraint.
    stripped = re.sub(r'^\s*"""[\s\S]*?"""\s*\n', "", src, count=1)
    tree = ast.parse(stripped)
    forbidden_call_names = {"open", "connect", "datetime.now",
                            "time.time", "time.clock", "settings"}
    leaks: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        target_name: str | None = None
        if isinstance(func, ast.Attribute) and isinstance(
            func.value, ast.Name,
        ):
            target_name = f"{func.value.id}.{func.attr}"
        elif isinstance(func, ast.Name):
            target_name = func.id
        if target_name in forbidden_call_names:
            leaks.append(target_name)
    assert leaks == [], f"helper uses forbidden tokens: {leaks}"


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
    """The ``proactive_shadow_runs.manifest_json`` carries ``session_phase = "UNKNOWN"``
    because the ``_ensure_shadow_run`` call site in
    ``proactive_intelligence.py`` passes ``observation_at=None``
    (no timestamp in scope). J.4 preserves this None-branch
    contract: ``session_phase = "UNKNOWN"``.
    """
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
async def test_run_research_comparison_manifest_records_session_phase_classified(db_setup):
    """[WORKFLOW-J.4 2026-09-13] The
    ``proactive_shadow_research_runs.manifest_json`` carries the
    REAL classified phase (was ``"UNKNOWN"`` pre-J.4).
    ``run_shadow_research_comparison`` passes
    ``proposals[0].signal_at`` as the observation
    timestamp. J.4 wires ``stamp_session_phase`` so the
    manifest now records the bounded phase.

    09:30 UTC = 15:00 IST = ``CONTINUOUS_TRADING`` on a Monday
    trading day. We pick a Monday (``2026-09-14``) explicitly
    because Sundays / Saturdays return CLOSED regardless of
    time-of-day -- the classifier's bounded contract.
    A regression to ``"UNKNOWN"`` here is a hard fail -- it
    would mean J.4 silently re-broke the forward-compat seam.
    """
    db_path = db_setup
    # 2026-09-14 is a Monday (per market_calendar test
    # fixtures). Use a Monday so the classifier returns a
    # bounded phase relevant to trading.
    epoch = datetime(2026, 9, 14, 9, 30, tzinfo=timezone.utc)
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
    # J.4: real classification, not the placeholder.
    assert manifest.get("session_phase") == "CONTINUOUS_TRADING", (
        f"research manifest must carry the real J.4 phase, "
        f"keys: {list(manifest)}, value: {manifest.get('session_phase')!r}"
    )
