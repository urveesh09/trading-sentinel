"""[WORKFLOW-G 2026-09-13] Promotion-bridge persistence and state-machine tests.

Implements the contract at ``docs/2026-09-13-workflow-g-promotion-bridge.md``
sections 3 (states), 4 (required fields), 5 (refusal template), 6 (gating
chain). The module under test is ``promotion_bridge.py``; *no other G
artefact and no F/D/Python runtime is touched*.

Test design notes:

* These tests target the contract, not the implementation. If the contract
  changes (e.g. an additional authorisation state is added), the tests
  must be revisited; a passing test suite is the proof that the
  contract is honoured today, not that it is correct tomorrow.
* Forward-only state transitions are verified with an explicit allowlist
  matrix; we do not derive from the state enum so that a future addition
  would have to opt in.
* The DB used is a per-test temp file via ``db_path`` from conftest; no
  production cache.db is touched (sanity: ``default_db_path`` would
  resolve to ``promotion_bridges.db`` next to cache.db; we never call it).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from promotion_bridge import (
    AuthorisationState,
    BridgeAlreadyExistsError,
    BridgeDecision,
    BridgeInvalidStateError,
    BridgeMissingFieldError,
    BridgeSignerError,
    BridgeVersionMismatchError,
    compute_evidence_identity,
    init_promotion_bridges,
    persist_bridge,
    read_bridge,
    transition_bridge,
)
from proactive_intelligence import _SHADOW_SCHEMA_VERSION
from cost_schedules import EQUITY_INTRADAY_SCHEDULE_VERSION


# Convenience constants at module level so tests don't carry full paths.
UNSIGNED = AuthorisationState.UNSIGNED.value
REFUSED = AuthorisationState.REFUSED.value
APPROVED_WITH_BUDGET = AuthorisationState.APPROVED_WITH_BUDGET.value
APPROVED_LIVE_BUDGET = AuthorisationState.APPROVED_LIVE_BUDGET.value


def _make_decision(**overrides):
    """Build a valid BridgeDecision with the seven required fields.

    The dict-spread mirrors the dataclass shape; this helper is the
    single point where defaults live.
    """
    base = {
        "proposal_run_id": "shadow-run-v1-2026-09-13",
        "evidence_identity_sha256": "0" * 64,
        "schema_version": _SHADOW_SCHEMA_VERSION,
        "cost_schedule_version": EQUITY_INTRADAY_SCHEDULE_VERSION,
        "code_revision": "deadbeef" * 5,  # 40 chars, not validated beyond non-empty
        "decided_at_utc": datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc),
        "decided_by": "operator-dev",
        "authorisation_state": UNSIGNED,
        "notes": "fixture",
        # Explicit fixture predeclaration, not inferred owner risk tolerance.
        "research_budget_inr": 100.0,
        "live_bankroll_delta": 100.0,
        "max_drawdown_pct": .10,
        "expiry_seconds": 86400,
    }
    base.update(overrides)
    return BridgeDecision(**base)


def test_decision_factory_is_a_valid_decision() -> None:
    """The test factory itself produces a decision that passes construction."""
    decision = _make_decision()
    assert decision.authorisation_state == UNSIGNED
    assert len(decision.evidence_identity_sha256) == 64


# ---- 1: field-level enforcement ----------------------------------------

class TestRequiredFields:
    def test_empty_proposal_run_id_rejected(self) -> None:
        with pytest.raises(BridgeMissingFieldError, match="proposal_run_id"):
            _make_decision(proposal_run_id="")

    def test_whitespace_evidence_identity_rejected(self) -> None:
        with pytest.raises(BridgeMissingFieldError, match="evidence_identity_sha256"):
            _make_decision(evidence_identity_sha256="   ")

    def test_evidence_identity_must_be_64_hex(self) -> None:
        # Non-hex characters
        with pytest.raises(BridgeMissingFieldError, match="64-char lowercase hex"):
            _make_decision(evidence_identity_sha256="g" * 64)
        # Wrong length
        with pytest.raises(BridgeMissingFieldError, match="64-char lowercase hex"):
            _make_decision(evidence_identity_sha256="a" * 60)
        # Uppercase hex is rejected to keep the contract literal
        with pytest.raises(BridgeMissingFieldError, match="64-char lowercase hex"):
            _make_decision(evidence_identity_sha256="A" * 64)

    def test_decided_at_utc_must_be_tz_aware(self) -> None:
        with pytest.raises(BridgeMissingFieldError, match="decided_at_utc"):
            _make_decision(decided_at_utc=datetime(2026, 9, 13))

    def test_decided_by_must_match_signer_pattern(self) -> None:
        # Empty
        with pytest.raises(BridgeSignerError, match="operator identifier"):
            _make_decision(decided_by="")
        # Whitespace only
        with pytest.raises(BridgeSignerError, match="operator identifier"):
            _make_decision(decided_by="   ")
        # Forbidden punctuation: angle brackets / ampersand could be an XSS vector
        # on a downstream renderer; refuse.
        with pytest.raises(BridgeSignerError):
            _make_decision(decided_by="<script>")
        # Too long
        with pytest.raises(BridgeSignerError):
            _make_decision(decided_by="a" * 65)

    def test_accepted_signer_examples_do_not_raise(self) -> None:
        # Operators can use initials, emails, or github handles.
        for signer in ("UV", "urveesh09", "urveesh@dev.local", "ops-team-1"):
            _make_decision(decided_by=signer)


# ---- 2: version guards -------------------------------------------------

class TestVersionGuards:
    def test_stale_schema_version_rejected(self) -> None:
        with pytest.raises(BridgeVersionMismatchError, match="schema_version"):
            _make_decision(schema_version="shadow-evidence-v1")

    def test_stale_cost_schedule_version_rejected(self) -> None:
        with pytest.raises(BridgeVersionMismatchError, match="cost_schedule_version"):
            _make_decision(cost_schedule_version="ZERODHA_NSE_EQUITY_INTRADAY_AS_OF_2025-01-01")

    def test_current_versions_accepted(self) -> None:
        # No raise
        _make_decision(
            schema_version=_SHADOW_SCHEMA_VERSION,
            cost_schedule_version=EQUITY_INTRADAY_SCHEDULE_VERSION,
        )


# ---- 3: state machine --------------------------------------------------

class TestAuthorisationStateRejection:
    def test_unknown_state_rejected(self) -> None:
        with pytest.raises(BridgeInvalidStateError, match="authorisation_state"):
            _make_decision(authorisation_state="MAYBE")


# ---- 4: persistence + append-only --------------------------------------

@pytest.mark.asyncio
async def test_persistence_creates_record_and_appends_unsigned_transition(db_path) -> None:
    """First persistence writes the bridge row and a NULL -> UNSIGNED transition."""
    decision = _make_decision()
    bridge_id = await persist_bridge(db_path, decision)
    assert bridge_id == decision.bridge_id
    record = await read_bridge(db_path, bridge_id)
    assert record is not None
    assert record["bridge"]["bridge_id"] == bridge_id
    assert record["bridge"]["authorisation_state"] == UNSIGNED
    assert record["current_state"] == UNSIGNED
    assert len(record["transitions"]) == 1
    assert record["transitions"][0]["previous_state"] is None
    assert record["transitions"][0]["new_state"] == UNSIGNED


@pytest.mark.asyncio
async def test_persistence_is_append_only_by_default(db_path) -> None:
    """Re-persisting an existing bridge_id raises BridgeAlreadyExistsError."""
    decision = _make_decision()
    await persist_bridge(db_path, decision)
    with pytest.raises(BridgeAlreadyExistsError, match="already exists"):
        await persist_bridge(db_path, decision)


@pytest.mark.asyncio
async def test_different_bridge_ids_each_get_a_record(db_path) -> None:
    """Two distinct decisions at different bridge_ids coexist."""
    a = await persist_bridge(db_path, _make_decision())
    b = await persist_bridge(db_path, _make_decision())
    assert a != b
    rec_a = await read_bridge(db_path, a)
    rec_b = await read_bridge(db_path, b)
    assert rec_a is not None and rec_b is not None
    assert rec_a["bridge"]["bridge_id"] == a
    assert rec_b["bridge"]["bridge_id"] == b


# ---- 5: read fail-closed ------------------------------------------------

@pytest.mark.asyncio
async def test_read_unknown_bridge_returns_none(db_path) -> None:
    assert await read_bridge(db_path, "no-such-bridge") is None


# ---- 6: read carries the G invariant triple ------------------------------

@pytest.mark.asyncio
async def test_read_carries_research_only_invariant(db_path) -> None:
    decision = _make_decision(authorisation_state=REFUSED)
    bridge_id = await persist_bridge(db_path, decision)
    record = await read_bridge(db_path, bridge_id)
    assert record["research_only"] is True
    assert record["can_place_orders"] is False
    assert record["authorization_effect"] == "NONE"


# ---- 7: forward-only transitions ----------------------------------------

@pytest.mark.asyncio
async def test_unsigned_to_refused_is_the_only_recognised_first_refusal_path(db_path) -> None:
    decision = _make_decision(authorisation_state=UNSIGNED)
    bridge_id = await persist_bridge(db_path, decision)
    later = datetime(2026, 9, 13, 11, 0, tzinfo=timezone.utc)
    await transition_bridge(
        db_path, bridge_id, new_state=REFUSED, decided_by="operator-dev",
        decided_at_utc=later, notes="gates unsatisfied: live capital not yet reconciled",
    )
    record = await read_bridge(db_path, bridge_id)
    assert record["current_state"] == REFUSED
    assert len(record["transitions"]) == 2
    assert record["transitions"][1]["previous_state"] == UNSIGNED
    assert record["transitions"][1]["new_state"] == REFUSED


@pytest.mark.asyncio
async def test_unsigned_to_approved_with_budget_is_allowed(db_path) -> None:
    decision = _make_decision(
        authorisation_state=APPROVED_WITH_BUDGET,
        research_budget_inr=100.0,  # minimum accepted
        max_drawdown_pct=0.10,
        expiry_seconds=86400,
    )
    bridge_id = await persist_bridge(db_path, decision)
    record = await read_bridge(db_path, bridge_id)
    assert record["current_state"] == APPROVED_WITH_BUDGET
    assert record["bridge"]["research_budget_inr"] == 100.0
    assert record["bridge"]["max_drawdown_pct"] == 0.10
    assert record["bridge"]["expiry_seconds"] == 86400


@pytest.mark.asyncio
async def test_refused_to_approved_is_forbidden(db_path) -> None:
    """Bridge contract section 6: transitions are forward-only from UNSIGNED."""
    decision = _make_decision(authorisation_state=REFUSED)
    bridge_id = await persist_bridge(db_path, decision)
    later = datetime(2026, 9, 13, 11, 0, tzinfo=timezone.utc)
    with pytest.raises(BridgeInvalidStateError, match="forward-only"):
        await transition_bridge(
            db_path, bridge_id, new_state=APPROVED_WITH_BUDGET,
            decided_by="operator-dev", decided_at_utc=later,
        )


@pytest.mark.asyncio
async def test_approved_to_refused_is_forbidden(db_path) -> None:
    """Even APPROVED -> REFUSED is forbidden; supersede with a new bridge."""
    decision = _make_decision(authorisation_state=APPROVED_WITH_BUDGET, research_budget_inr=100.0)
    bridge_id = await persist_bridge(db_path, decision)
    later = datetime(2026, 9, 13, 11, 0, tzinfo=timezone.utc)
    with pytest.raises(BridgeInvalidStateError, match="forward-only"):
        await transition_bridge(
            db_path, bridge_id, new_state=REFUSED,
            decided_by="operator-dev", decided_at_utc=later,
        )


@pytest.mark.asyncio
async def test_transition_on_unknown_bridge_rejected(db_path) -> None:
    later = datetime(2026, 9, 13, 11, 0, tzinfo=timezone.utc)
    with pytest.raises(BridgeInvalidStateError, match="does not exist"):
        await transition_bridge(
            db_path, "no-such-bridge", new_state=REFUSED,
            decided_by="operator-dev", decided_at_utc=later,
        )


@pytest.mark.asyncio
async def test_transition_validates_tz_aware_timestamp(db_path) -> None:
    decision = _make_decision()
    bridge_id = await persist_bridge(db_path, decision)
    with pytest.raises(BridgeMissingFieldError, match="decided_at_utc"):
        await transition_bridge(
            db_path, bridge_id, new_state=REFUSED, decided_by="operator-dev",
            decided_at_utc=datetime(2026, 9, 13, 11, 0),  # naive!
        )


@pytest.mark.asyncio
async def test_transition_validates_signer_format(db_path) -> None:
    decision = _make_decision()
    bridge_id = await persist_bridge(db_path, decision)
    later = datetime(2026, 9, 13, 11, 0, tzinfo=timezone.utc)
    with pytest.raises(BridgeSignerError):
        await transition_bridge(
            db_path, bridge_id, new_state=REFUSED,
            decided_by="<script>", decided_at_utc=later,
        )


# ---- 8: schema bring-up is idempotent -----------------------------------

@pytest.mark.asyncio
async def test_init_promotion_bridges_is_idempotent(db_path) -> None:
    await init_promotion_bridges(db_path)
    # second call must not raise, and must not destroy existing data
    decision = _make_decision()
    bridge_id = await persist_bridge(db_path, decision)
    await init_promotion_bridges(db_path)
    record = await read_bridge(db_path, bridge_id)
    assert record is not None
    assert record["bridge"]["bridge_id"] == bridge_id


# ---- 9: budget field bounds --------------------------------------------

class TestBudgetBounds:
    def test_research_budget_below_minimum_rejected(self) -> None:
        with pytest.raises(BridgeMissingFieldError, match="research_budget_inr"):
            _make_decision(
                authorisation_state=APPROVED_WITH_BUDGET,
                research_budget_inr=0.0,
            )

    def test_live_bankroll_delta_above_max_rejected(self) -> None:
        with pytest.raises(BridgeMissingFieldError, match="live_bankroll_delta"):
            _make_decision(
                authorisation_state=APPROVED_LIVE_BUDGET,
                live_bankroll_delta=1e9,
            )

    def test_max_drawdown_pct_zero_rejected(self) -> None:
        with pytest.raises(BridgeMissingFieldError, match="max_drawdown_pct"):
            _make_decision(
                authorisation_state=APPROVED_WITH_BUDGET,
                research_budget_inr=100.0,
                max_drawdown_pct=0.0,
            )

    def test_expiry_seconds_negative_rejected(self) -> None:
        with pytest.raises(BridgeMissingFieldError, match="expiry_seconds"):
            _make_decision(
                authorisation_state=APPROVED_WITH_BUDGET,
                research_budget_inr=100.0,
                expiry_seconds=-1,
            )


# ---- 10: identity helper ------------------------------------------------

def test_compute_evidence_identity_is_deterministic() -> None:
    payload = {"opportunities": 12, "trials": 24, "policy": "trend_pullback_v1"}
    a = compute_evidence_identity(payload)
    b = compute_evidence_identity(payload)
    assert a == b
    assert len(a) == 64
    payload2 = dict(payload, trials=25)
    assert compute_evidence_identity(payload2) != a


def test_compute_evidence_identity_treats_keys_as_unordered() -> None:
    a = compute_evidence_identity({"a": 1, "b": 2})
    b = compute_evidence_identity({"b": 2, "a": 1})
    assert a == b


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", [REFUSED, APPROVED_WITH_BUDGET, APPROVED_LIVE_BUDGET])
async def test_latest_terminal_transition_cannot_be_amended(db_path, terminal):
    bridge_id = await persist_bridge(db_path, _make_decision())
    at = datetime(2026, 9, 13, 11, tzinfo=timezone.utc)
    await transition_bridge(db_path, bridge_id, new_state=terminal,
                            decided_by="operator-dev", decided_at_utc=at)
    for attempted in (UNSIGNED, REFUSED, APPROVED_WITH_BUDGET, APPROVED_LIVE_BUDGET):
        with pytest.raises(BridgeInvalidStateError, match="forward-only"):
            await transition_bridge(db_path, bridge_id, new_state=attempted,
                                    decided_by="operator-dev", decided_at_utc=at)
    record = await read_bridge(db_path, bridge_id)
    assert record["current_state"] == terminal
    assert len(record["transitions"]) == 2
    assert record["can_place_orders"] is False


@pytest.mark.asyncio
async def test_initial_approval_cannot_transition_back_to_unsigned(db_path):
    bridge_id = await persist_bridge(db_path, _make_decision(
        authorisation_state=APPROVED_WITH_BUDGET, research_budget_inr=100.0))
    with pytest.raises(BridgeInvalidStateError, match="forward-only"):
        await transition_bridge(db_path, bridge_id, new_state=UNSIGNED,
                                decided_by="operator-dev",
                                decided_at_utc=datetime(2026, 9, 13, 11, tzinfo=timezone.utc))


@pytest.mark.asyncio
async def test_concurrent_first_transitions_have_exactly_one_winner(db_path):
    import asyncio
    bridge_id = await persist_bridge(db_path, _make_decision())
    at = datetime(2026, 9, 13, 11, tzinfo=timezone.utc)
    results = await asyncio.gather(*[
        transition_bridge(db_path, bridge_id, new_state=state,
                          decided_by="operator-dev", decided_at_utc=at)
        for state in (REFUSED, APPROVED_WITH_BUDGET)
    ], return_exceptions=True)
    assert sum(result == bridge_id for result in results) == 1
    assert sum(isinstance(result, BridgeInvalidStateError) for result in results) == 1
    record = await read_bridge(db_path, bridge_id)
    assert len(record["transitions"]) == 2
    assert record["current_state"] in {REFUSED, APPROVED_WITH_BUDGET}


@pytest.mark.asyncio
async def test_committed_append_order_not_signature_clock_defines_state(db_path):
    bridge_id = await persist_bridge(db_path, _make_decision())
    # A historical operator timestamp cannot reorder the committed transition
    # ahead of creation and make the initial UNSIGNED row look current again.
    await transition_bridge(db_path, bridge_id, new_state=REFUSED,
                            decided_by="operator-dev",
                            decided_at_utc=datetime(2025, 1, 1, tzinfo=timezone.utc))
    record = await read_bridge(db_path, bridge_id)
    assert record["current_state"] == REFUSED
    assert [row["new_state"] for row in record["transitions"]] == [UNSIGNED, REFUSED]


@pytest.mark.parametrize("state, amount", [(APPROVED_WITH_BUDGET, "research_budget_inr"), (APPROVED_LIVE_BUDGET, "live_bankroll_delta")])
@pytest.mark.parametrize("missing", ["amount", "max_drawdown_pct", "expiry_seconds"])
def test_approved_decision_requires_explicit_budget_drawdown_and_expiry(state, amount, missing):
    field = amount if missing == "amount" else missing
    with pytest.raises(BridgeMissingFieldError, match=field):
        _make_decision(authorisation_state=state, **{field: None})


@pytest.mark.parametrize("field, value", [("research_budget_inr", True), ("research_budget_inr", float("nan")),
    ("max_drawdown_pct", float("inf")), ("expiry_seconds", 60.5), ("expiry_seconds", True), ("expiry_seconds", "3600")])
@pytest.mark.parametrize("state", [UNSIGNED, APPROVED_WITH_BUDGET])
def test_malformed_budget_is_rejected_before_sqlite_type_coercion(field, value, state):
    with pytest.raises(BridgeMissingFieldError, match=field):
        _make_decision(authorisation_state=state, **{field: value})


@pytest.mark.asyncio
async def test_unbudgeted_unsigned_record_cannot_be_approved(db_path):
    decision = _make_decision(research_budget_inr=None, live_bankroll_delta=None, max_drawdown_pct=None, expiry_seconds=None)
    await persist_bridge(db_path, decision)
    with pytest.raises(BridgeMissingFieldError, match="research_budget_inr"):
        await transition_bridge(db_path, decision.bridge_id, new_state=APPROVED_WITH_BUDGET,
                                decided_by="operator-dev", decided_at_utc=decision.decided_at_utc)
    record = await read_bridge(db_path, decision.bridge_id)
    assert record["current_state"] == UNSIGNED and len(record["transitions"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("delta, expected", [(-1, "NOT_YET_VALID"), (0, "VALID_BUDGET_ONLY"), (59, "VALID_BUDGET_ONLY"), (60, "EXPIRED")])
async def test_budget_status_at_exact_original_window_boundaries(db_path, delta, expected):
    decision = _make_decision(authorisation_state=APPROVED_WITH_BUDGET, expiry_seconds=60)
    await persist_bridge(db_path, decision)
    record = await read_bridge(db_path, decision.bridge_id, now=decision.decided_at_utc + timedelta(seconds=delta))
    assert record["budget_status"] == expected
    assert record["current_state"] == APPROVED_WITH_BUDGET
    assert record["approval_usable"] is False and record["can_place_orders"] is False
    assert record["approval_blockers"] == ["FROZEN_HELDOUT_ACCOUNT_AND_F_D_EVIDENCE_NOT_VALIDATED"]


@pytest.mark.asyncio
async def test_later_approval_cannot_extend_predeclared_budget_window(db_path):
    decision = _make_decision(expiry_seconds=60)
    await persist_bridge(db_path, decision)
    at = decision.decided_at_utc + timedelta(seconds=30)
    await transition_bridge(db_path, decision.bridge_id, new_state=APPROVED_WITH_BUDGET,
                            decided_by="operator-dev", decided_at_utc=at)
    before = await read_bridge(db_path, decision.bridge_id, now=at - timedelta(seconds=1))
    expired = await read_bridge(db_path, decision.bridge_id, now=decision.decided_at_utc + timedelta(seconds=60))
    assert before["budget_status"] == "NOT_YET_VALID"
    assert expired["budget_status"] == "EXPIRED"


@pytest.mark.asyncio
async def test_approval_at_original_expiry_is_rejected_without_appending(db_path):
    decision = _make_decision(expiry_seconds=60)
    await persist_bridge(db_path, decision)
    with pytest.raises(BridgeMissingFieldError, match="validity window"):
        await transition_bridge(db_path, decision.bridge_id, new_state=APPROVED_WITH_BUDGET,
            decided_by="operator-dev", decided_at_utc=decision.decided_at_utc + timedelta(seconds=60))
    assert (await read_bridge(db_path, decision.bridge_id))["current_state"] == UNSIGNED


@pytest.mark.asyncio
async def test_historical_unbudgeted_approval_is_retained_but_not_usable(db_path):
    import aiosqlite
    decision = _make_decision()
    await persist_bridge(db_path, decision)
    # Model historical pre-hardening rows on a fixture; don't repair live books.
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE promotion_bridges SET authorisation_state=?,research_budget_inr=NULL,max_drawdown_pct=NULL,expiry_seconds=NULL WHERE bridge_id=?", (APPROVED_WITH_BUDGET, decision.bridge_id))
        await db.execute("UPDATE promotion_bridge_transitions SET new_state=? WHERE bridge_id=?", (APPROVED_WITH_BUDGET, decision.bridge_id))
        await db.commit()
    record = await read_bridge(db_path, decision.bridge_id, now=decision.decided_at_utc)
    assert record["budget_status"] == "INVALID_OR_MISSING_BUDGET"
    assert record["current_state"] == APPROVED_WITH_BUDGET and record["approval_usable"] is False


@pytest.mark.asyncio
async def test_stale_approved_record_is_visible_and_new_approval_fails(db_path, monkeypatch):
    import promotion_bridge
    decision = _make_decision()
    approved = _make_decision(authorisation_state=APPROVED_WITH_BUDGET)
    await persist_bridge(db_path, decision)
    await persist_bridge(db_path, approved)
    monkeypatch.setattr(promotion_bridge, "EQUITY_INTRADAY_SCHEDULE_VERSION", "new-version")
    with pytest.raises(BridgeVersionMismatchError, match="stale"):
        await transition_bridge(db_path, decision.bridge_id, new_state=APPROVED_WITH_BUDGET,
                                decided_by="operator-dev", decided_at_utc=decision.decided_at_utc)
    record = await read_bridge(db_path, approved.bridge_id, now=approved.decided_at_utc)
    assert record["budget_status"] == "STALE_VERSION" and record["approval_usable"] is False


@pytest.mark.asyncio
async def test_whitespace_transition_signer_is_not_a_signature(db_path):
    decision = _make_decision()
    await persist_bridge(db_path, decision)
    with pytest.raises(BridgeSignerError):
        await transition_bridge(db_path, decision.bridge_id, new_state=REFUSED,
                                decided_by="   ", decided_at_utc=decision.decided_at_utc)


@pytest.mark.asyncio
async def test_historical_out_of_window_signature_is_not_valid_budget_evidence(db_path):
    import aiosqlite
    decision = _make_decision(authorisation_state=APPROVED_WITH_BUDGET, expiry_seconds=60)
    await persist_bridge(db_path, decision)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE promotion_bridge_transitions SET decided_at_utc=? WHERE bridge_id=?",
                         ((decision.decided_at_utc + timedelta(seconds=60)).isoformat(), decision.bridge_id))
        await db.commit()
    record = await read_bridge(db_path, decision.bridge_id, now=decision.decided_at_utc)
    assert record["budget_status"] == "INVALID_OR_MISSING_BUDGET" and record["approval_usable"] is False
