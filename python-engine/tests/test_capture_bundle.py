"""[WORKFLOW-A.3 2026-09-17] Tests for the capture-bundle
binding.

Per Workstream A in NEXT_AGENT_PLAN.md:
> Carry the chosen clocks and source IDs into the
> captured bundle and frozen decision manifest. Bind
> candidate and public captures to the same
> decision/run/account/index.

These tests pin the canonical capture bundle:
  - ``build_capture_bundle`` -- low-level builder.
  - ``bundle_from_clock_and_card`` -- convenience wrapper
    that takes a DecisionClock directly.
  - ``validate_bundle`` -- returns ALL binding problems.
  - ``has_required_bundle_fields`` -- quick assertion.
  - Round-trip via JSON preserves the bundle.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from zoneinfo import ZoneInfo

PYTHON_ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ENGINE))

from capture_bundle import (  # noqa: E402  -- import path
    BUNDLE_VERSION_V1,
    BundleValidationCode,
    BundleValidationProblem,
    CaptureBundle,
    REQUIRED_BUNDLE_FIELDS,
    build_capture_bundle,
    bundle_from_clock_and_card,
    has_required_bundle_fields,
    validate_bundle,
)
from decision_clocks_extensions import (  # noqa: E402  -- import path
    build_clock_for_test,
)


IST = ZoneInfo("Asia/Kolkata")


def _tick() -> datetime:
    return datetime(2026, 9, 14, 9, 45, tzinfo=IST)


def _card() -> dict:
    return {
        "scope": "MARKET_SETUP",
        "underlying": "NIFTY",
        "exchange": "NSE",
        "thesis_id": "thesis-abc",
        "evidence": "QUALIFIED_FOR_ADVISORY",
        "policy_version": "v1",
        "quote_time": "2026-09-14T09:45:00+05:30",
        "valid_until": "2026-09-14T15:30:00+05:30",
        "why_now": ["ORB broke above opening range"],
        "uncertainty": "liquidity uncertain",
        "invalidation": "below opening low",
        "management": "exit at target",
        "holding_horizon": "INTRADAY",
        "management_deadline": "2026-09-14T15:15:00+05:30",
        "net_debit_rs": 150.0,
        "max_loss_rs": 150.0,
        "breakevens": [24150.0],
        "trigger_level": 24100.0,
        "invalidation_level": 24000.0,
        "target_level": 24300.0,
        "estimated_round_trip_cost_rs": 5.0,
        "legs": [
            {"side": "BUY", "ratio": 1, "lot_size": 75,
             "expiry": "2026-09-26", "option_type": "CE",
             "strike": 24100, "tradingsymbol": "NIFTY24100CE"},
        ],
    }


# -- 1. Required fields --------------------------------------


def test_required_bundle_fields_constant_includes_all_keys():
    """[WORKFLOW-A.3 2026-09-17] The plan's required fields:
    decision_id, run_id, account_id, underlying, policy,
    clock, source_ids, card."""
    expected = {
        "bundle_version", "decision_id", "run_id", "account_id",
        "underlying", "policy", "clock", "source_ids", "card",
    }
    assert set(REQUIRED_BUNDLE_FIELDS) == expected


def test_bundle_version_v1_constant():
    assert BUNDLE_VERSION_V1 == "BUNDLE_VERSION_V1"


# -- 2. build_capture_bundle --------------------------------


def test_build_capture_bundle_returns_capture_bundle_instance():
    bundle = build_capture_bundle(
        run_id="run-1", account_id="acct-1", underlying="NIFTY",
        policy="FROZEN_COMPLETED_BAR_CUTOFF_V1",
        clock_payload={"tick_started_at": "2026-09-14T09:45:00+05:30"},
        public_source_id="kite:NIFTY:1",
        chain_source_id="kite:NIFTY:2",
        card=_card(),
    )
    assert isinstance(bundle, CaptureBundle)


def test_build_capture_bundle_populates_all_fields():
    bundle = build_capture_bundle(
        run_id="run-1", account_id="acct-1", underlying="NIFTY",
        policy="FROZEN_COMPLETED_BAR_CUTOFF_V1",
        clock_payload={"tick_started_at": "2026-09-14T09:45:00+05:30"},
        public_source_id="kite:NIFTY:1",
        chain_source_id="kite:NIFTY:2",
        card=_card(),
    )
    assert bundle.run_id == "run-1"
    assert bundle.account_id == "acct-1"
    assert bundle.underlying == "NIFTY"
    assert bundle.policy == "FROZEN_COMPLETED_BAR_CUTOFF_V1"
    assert bundle.source_ids == {
        "public": "kite:NIFTY:1", "chain": "kite:NIFTY:2",
    }
    assert bundle.clock["tick_started_at"] == "2026-09-14T09:45:00+05:30"


def test_decision_id_is_deterministic_for_same_inputs():
    """[WORKFLOW-A.3 2026-09-17] decision_id is a hash that
    binds the bundle's identity. Same inputs = same
    decision_id; different inputs = different decision_id."""
    card = _card()
    a = build_capture_bundle(
        run_id="run-1", account_id="acct-1", underlying="NIFTY",
        policy="FROZEN_COMPLETED_BAR_CUTOFF_V1",
        clock_payload={"tick_started_at": "2026-09-14T09:45:00+05:30"},
        public_source_id="kite:NIFTY:1", chain_source_id="kite:NIFTY:2",
        card=card,
    )
    b = build_capture_bundle(
        run_id="run-1", account_id="acct-1", underlying="NIFTY",
        policy="FROZEN_COMPLETED_BAR_CUTOFF_V1",
        clock_payload={"tick_started_at": "2026-09-14T09:45:00+05:30"},
        public_source_id="kite:NIFTY:1", chain_source_id="kite:NIFTY:2",
        card=card,
    )
    assert a.decision_id == b.decision_id


def test_decision_id_changes_when_clock_payload_changes():
    card = _card()
    a = build_capture_bundle(
        run_id="run-1", account_id="acct-1", underlying="NIFTY",
        policy="FROZEN_COMPLETED_BAR_CUTOFF_V1",
        clock_payload={"tick_started_at": "2026-09-14T09:45:00+05:30"},
        public_source_id="kite:NIFTY:1", chain_source_id="kite:NIFTY:2",
        card=card,
    )
    b = build_capture_bundle(
        run_id="run-1", account_id="acct-1", underlying="NIFTY",
        policy="FROZEN_COMPLETED_BAR_CUTOFF_V1",
        clock_payload={"tick_started_at": "2026-09-14T09:46:00+05:30"},  # different tick
        public_source_id="kite:NIFTY:1", chain_source_id="kite:NIFTY:2",
        card=card,
    )
    assert a.decision_id != b.decision_id


def test_decision_id_changes_when_run_id_changes():
    """[WORKFLOW-A.3 2026-09-17] Same inputs but different
    run_id (different run) = different decision_id."""
    card = _card()
    kwargs = dict(
        account_id="acct-1", underlying="NIFTY",
        policy="FROZEN_COMPLETED_BAR_CUTOFF_V1",
        clock_payload={"tick_started_at": "2026-09-14T09:45:00+05:30"},
        public_source_id="kite:NIFTY:1", chain_source_id="kite:NIFTY:2",
        card=card,
    )
    a = build_capture_bundle(run_id="run-1", **kwargs)
    b = build_capture_bundle(run_id="run-2", **kwargs)
    assert a.decision_id != b.decision_id


# -- 3. bundle_from_clock_and_card ---------------------------


def test_bundle_from_clock_and_card_uses_clock_run_id():
    """[WORKFLOW-A.3 2026-09-17] The clock's run_id is the
    canonical run identity; the bundle carries it."""
    clock = build_clock_for_test(tick_started_at=_tick(), underlying="NIFTY")
    bundle = bundle_from_clock_and_card(clock=clock, card=_card())
    assert bundle.run_id == clock.run_id


def test_bundle_from_clock_and_card_includes_clock_payload():
    clock = build_clock_for_test(tick_started_at=_tick(), underlying="NIFTY")
    bundle = bundle_from_clock_and_card(clock=clock, card=_card())
    # The clock payload contains all the ISO timestamps.
    assert "tick_started_at" in bundle.clock
    assert "evaluation_cutoff_at" in bundle.clock
    assert "public_received_at" in bundle.clock
    assert "candidate_constructed_at" in bundle.clock


def test_bundle_from_clock_and_card_pulls_source_ids_from_clock():
    clock = build_clock_for_test(
        tick_started_at=_tick(), underlying="NIFTY",
        public_source_id="kite:NIFTY:1", chain_source_id="kite:NIFTY:2",
    )
    bundle = bundle_from_clock_and_card(clock=clock, card=_card())
    assert bundle.source_ids["public"] == "kite:NIFTY:1"
    assert bundle.source_ids["chain"] == "kite:NIFTY:2"


def test_bundle_from_clock_and_card_explicit_source_ids_override():
    """[WORKFLOW-A.3 2026-09-17] Explicit source IDs win
    over the clock's stored source IDs."""
    clock = build_clock_for_test(
        tick_started_at=_tick(), underlying="NIFTY",
        public_source_id="kite:NIFTY:old",
    )
    bundle = bundle_from_clock_and_card(
        clock=clock, card=_card(), public_source_id="kite:NIFTY:new",
    )
    assert bundle.source_ids["public"] == "kite:NIFTY:new"


# -- 4. CaptureBundle.to_dict -------------------------------


def test_to_dict_serializes_all_fields():
    clock = build_clock_for_test(tick_started_at=_tick(), underlying="NIFTY")
    bundle = bundle_from_clock_and_card(clock=clock, card=_card())
    d = bundle.to_dict()
    expected = {
        "bundle_version", "decision_id", "run_id", "account_id",
        "underlying", "policy", "clock", "source_ids", "card",
    }
    assert set(d.keys()) == expected


def test_to_dict_round_trips_through_json():
    """[WORKFLOW-A.3 2026-09-17] A captured bundle should
    survive a JSON round-trip without loss."""
    clock = build_clock_for_test(tick_started_at=_tick(), underlying="NIFTY")
    bundle = bundle_from_clock_and_card(clock=clock, card=_card())
    d = bundle.to_dict()
    rehydrated = json.loads(json.dumps(d))
    assert rehydrated == d


# -- 5. validate_bundle -------------------------------------


def test_validate_bundle_passes_for_complete_bundle():
    clock = build_clock_for_test(tick_started_at=_tick(), underlying="NIFTY")
    bundle = bundle_from_clock_and_card(clock=clock, card=_card())
    problems = validate_bundle(bundle.to_dict())
    assert problems == [], (
        f"expected no problems; got: {[(p.code, p.message) for p in problems]}"
    )


def test_validate_bundle_collects_all_missing_fields():
    """[WORKFLOW-A.3 2026-09-17] All missing fields are
    surfaced together."""
    problems = validate_bundle({})
    missing = [p for p in problems if p.code == BundleValidationCode.MISSING_FIELD]
    assert len(missing) >= len(REQUIRED_BUNDLE_FIELDS)


def test_validate_bundle_detects_missing_clock():
    clock = build_clock_for_test(tick_started_at=_tick(), underlying="NIFTY")
    bundle = bundle_from_clock_and_card(clock=clock, card=_card())
    d = bundle.to_dict()
    del d["clock"]
    problems = validate_bundle(d)
    assert any(
        p.field == "clock" and p.code == BundleValidationCode.MISSING_FIELD
        for p in problems
    )


def test_validate_bundle_detects_empty_card():
    clock = build_clock_for_test(tick_started_at=_tick(), underlying="NIFTY")
    bundle = bundle_from_clock_and_card(clock=clock, card={})
    problems = validate_bundle(bundle.to_dict())
    assert any(
        p.code == BundleValidationCode.EMPTY_CARD for p in problems
    )


def test_validate_bundle_detects_underlying_mismatch():
    """[WORKFLOW-A.3 2026-09-17] The plan says 'Bind
    candidate and public captures to the same
    decision/run/account/index'. card.underlying must
    match bundle.underlying."""
    clock = build_clock_for_test(tick_started_at=_tick(), underlying="NIFTY")
    bundle = bundle_from_clock_and_card(clock=clock, card=_card())
    d = bundle.to_dict()
    d["card"]["underlying"] = "SENSEX"
    problems = validate_bundle(d)
    assert any(
        p.code == BundleValidationCode.UNDERLYING_MISMATCH for p in problems
    )


def test_validate_bundle_detects_clock_missing_tick_started():
    clock = build_clock_for_test(tick_started_at=_tick(), underlying="NIFTY")
    bundle = bundle_from_clock_and_card(clock=clock, card=_card())
    d = bundle.to_dict()
    d["clock"] = {}  # no tick_started_at
    problems = validate_bundle(d)
    assert any(
        p.code == BundleValidationCode.CLOCK_NOT_READY for p in problems
    )


def test_validate_bundle_detects_bad_version():
    clock = build_clock_for_test(tick_started_at=_tick(), underlying="NIFTY")
    bundle = bundle_from_clock_and_card(clock=clock, card=_card())
    d = bundle.to_dict()
    d["bundle_version"] = "BUNDLE_VERSION_V99"
    problems = validate_bundle(d)
    assert any(
        p.code == BundleValidationCode.BAD_VERSION for p in problems
    )


def test_validate_bundle_detects_non_mapping():
    problems = validate_bundle("not a mapping")  # type: ignore[arg-type]
    assert any(
        p.code == BundleValidationCode.WRONG_TYPE for p in problems
    )


# -- 6. has_required_bundle_fields ---------------------------


def test_has_required_bundle_fields_true_for_complete_bundle():
    clock = build_clock_for_test(tick_started_at=_tick(), underlying="NIFTY")
    bundle = bundle_from_clock_and_card(clock=clock, card=_card())
    assert has_required_bundle_fields(bundle.to_dict()) is True


def test_has_required_bundle_fields_false_when_card_missing():
    clock = build_clock_for_test(tick_started_at=_tick(), underlying="NIFTY")
    bundle = bundle_from_clock_and_card(clock=clock, card=_card())
    d = bundle.to_dict()
    del d["card"]
    assert has_required_bundle_fields(d) is False


# -- 7. End-to-end: FROZEN and POST_ACQ bundles -----------


def test_frozen_policy_bundle_carries_policy_version():
    clock = build_clock_for_test(tick_started_at=_tick(), underlying="NIFTY")
    bundle = bundle_from_clock_and_card(clock=clock, card=_card())
    assert bundle.policy == "FROZEN_COMPLETED_BAR_CUTOFF_V1"


def test_post_acquisition_bundle_carries_policy_version():
    """[WORKFLOW-A.3 2026-09-17] The bundle carries the
    policy version so replays can re-evaluate under the
    right policy."""
    from decision_policy import start_clock_for_policy, DecisionPolicy
    tick = _tick()
    clock = start_clock_for_policy(
        policy=DecisionPolicy.POST_ACQUISITION_RECOMPUTE_V1.value,
        tick_started_at=tick, underlying="NIFTY",
        account_id="manual-profile:p1",
    ).with_stage(candidate_constructed_at=tick + timedelta(seconds=2))
    bundle = bundle_from_clock_and_card(clock=clock, card=_card())
    assert bundle.policy == "POST_ACQUISITION_RECOMPUTE_V1"
