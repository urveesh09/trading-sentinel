"""Independent unmocked acceptance checks for the predeclared G/C workflow."""
from datetime import datetime, timedelta, timezone

import pytest

from proactive_comparison_protocol import freeze_comparison_protocol, evaluate_comparison_protocol, _summarise
from proactive_intelligence import ShadowProposal


def _manifest():
    return {"protocol_id": "independent", "account_id": "fixture", "code_revision": "a" * 40,
            "frozen_at": "2026-09-10T00:00:00Z", "training_sessions": ["2026-09-09"],
            "holdout_sessions": ["2026-09-11", "2026-09-14"], "cash": 8000,
            "alternatives": [{"name": "baseline", "entry": "NEXT_EXECUTABLE_OPEN_V1", "exit": "STOP_TARGET_TIME_V1"}],
            "baseline": "baseline", "cost_snapshot": {"fee_rate": 0, "slippage_bps": 0,
                                                        "schedule_version": "FIXTURE_ONLY", "effective_date": None},
            "cost_stress": {"fee_multiplier": 2, "additional_slippage_bps": 0},
            "thresholds": {"minimum_closed_outcomes": 1, "minimum_complete_sessions": 1,
                           "maximum_drawdown_pct": .5, "minimum_net_expectancy": 0,
                           "minimum_paired_delta": 0, "confidence_level": .95, "bootstrap_samples": 200}}


def _at(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _proposal():
    return ShadowProposal("opportunity", "fixture-orb", "fixture", 100, 99, 102,
                          _at("2026-09-11T10:00:00Z"), 1, 100, "fixture",
                          signal_at=_at("2026-09-11T04:00:00Z"), data_cutoff=_at("2026-09-11T04:00:00Z"))


@pytest.mark.asyncio
async def test_any_missing_declared_session_prevents_support_even_if_minimum_met(tmp_path):
    path = str(tmp_path / "offline.db")
    await freeze_comparison_protocol(path, _manifest(), now=_at("2026-09-10T01:00:00Z"))
    report = await evaluate_comparison_protocol(path, protocol_id="independent", report_id="r1",
        proposals=[_proposal()], future_bars={"fixture": [
            {"timestamp": "2026-09-11T04:05:00Z", "open": 100, "high": 103, "low": 99.5, "close": 102}]},
        session_coverage={"baseline": {"2026-09-11": "COMPLETE", "2026-09-14": "MISSING"}},
        now=_at("2026-09-15T00:00:00Z"))
    assert report["profiles"][0]["baseline"]["closed"] == 1
    assert report["profiles"][0]["disposition"] == "UNCERTAIN"
    assert report["approval_usable"] is False


@pytest.mark.asyncio
async def test_exact_freeze_retry_after_holdout_preserves_original_recorded_clock(tmp_path):
    path = str(tmp_path / "offline.db")
    first = await freeze_comparison_protocol(path, _manifest(), now=_at("2026-09-10T01:00:00Z"))
    retry = await freeze_comparison_protocol(path, _manifest(), now=_at("2026-09-15T00:00:00Z"))
    assert retry == first
    changed = _manifest()
    changed["protocol_id"] = "backdated-new"
    with pytest.raises(ValueError):
        await freeze_comparison_protocol(path, changed, now=_at("2026-09-15T00:00:00Z"))


@pytest.mark.asyncio
async def test_full_cost_provenance_is_frozen_and_not_discarded(tmp_path):
    manifest = _manifest()
    path = str(tmp_path / "offline.db")
    retained = await freeze_comparison_protocol(path, manifest, now=_at("2026-09-10T01:00:00Z"))
    assert retained["cost_snapshot"]["schedule_version"] == "FIXTURE_ONLY"
    assert retained["cost_snapshot"]["effective_date"] is None
    manifest["cost_snapshot"]["schedule_version"] = "DIFFERENT"
    with pytest.raises(ValueError, match="conflict"):
        await freeze_comparison_protocol(path, manifest, now=_at("2026-09-10T02:00:00Z"))


def test_cluster_bootstrap_matches_opportunity_weighted_estimand_and_is_not_point_interval():
    base, challenger = [], []
    for i, delta in enumerate([-10] * 9 + [100]):
        row = {"opportunity_id": str(i), "session": "2026-09-11" if i < 9 else "2026-09-14",
               "status": "CLOSED", "net_pnl": 0, "quantity": 1, "entry_price": 100,
               "exit_price": 100, "exit_at": "2026-09-14T10:00:00Z"}
        base.append(row)
        challenger.append({**row, "net_pnl": delta})
    summary = _summarise(challenger, base, cash=8000, confidence=.95, samples=500)
    assert summary["paired_baseline_delta"] == 1  # Not session-mean45.
    low, high = summary["paired_session_cluster_bootstrap_ci"]
    assert low < 1 < high
    assert summary["bootstrap_cluster_count"] == 2
    assert _summarise(challenger, base, cash=8000, confidence=.95, samples=500) == summary
    assert summary["turnover_notional"] == 2000


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["overlap", "reversed", "boolean", "optimistic_stress", "revision"])
async def test_protocol_rejects_invalid_declared_contracts(tmp_path, mutation):
    manifest = _manifest()
    if mutation == "overlap": manifest["training_sessions"] = ["2026-09-11"]
    if mutation == "reversed": manifest["training_sessions"] = ["2026-09-15"]
    if mutation == "boolean": manifest["thresholds"]["minimum_closed_outcomes"] = True
    if mutation == "optimistic_stress": manifest["cost_stress"]["fee_multiplier"] = .5
    if mutation == "revision": manifest["code_revision"] = "latest"
    with pytest.raises(ValueError):
        await freeze_comparison_protocol(str(tmp_path / "offline.db"), manifest, now=_at("2026-09-10T01:00:00Z"))


@pytest.mark.asyncio
async def test_actual_two_profile_two_session_report_retains_all_gates_and_retries(tmp_path):
    from dataclasses import replace
    import hashlib
    import json
    manifest = _manifest()
    manifest["alternatives"].append({"name": "bounded", "entry": "NEXT_EXECUTABLE_OPEN_V1",
                                      "exit": "BOUNDED_TIME_EXIT_60M_V1"})
    path = str(tmp_path / "offline.db")
    await freeze_comparison_protocol(path, manifest, now=_at("2026-09-10T01:00:00Z"))
    first = replace(_proposal(), entry_deadline=_at("2026-09-11T04:20:00Z"))
    second = replace(first, opportunity_id="second", signal_at=_at("2026-09-14T04:00:00Z"),
                     data_cutoff=_at("2026-09-14T04:00:00Z"), valid_until=_at("2026-09-14T10:00:00Z"),
                     entry_deadline=_at("2026-09-14T04:20:00Z"))
    bars = {p.opportunity_id: [{"timestamp": p.signal_at.replace(minute=5).isoformat(),
                               "open": 100, "high": 103, "low": 99.5, "close": 102}]
            for p in (first, second)}
    args = dict(protocol_id="independent", report_id="two-profile", proposals=[first, second],
                future_bars=bars, session_coverage={name: {day: "COMPLETE" for day in manifest["holdout_sessions"]}
                                                   for name in ("baseline", "bounded")},
                now=_at("2026-09-15T00:00:00Z"))
    report = await evaluate_comparison_protocol(path, **args)
    assert len(report["profiles"]) == 2
    assert all(profile["baseline"]["closed"] == 2 for profile in report["profiles"])
    assert all(profile["stress"]["closed"] == 2 for profile in report["profiles"])
    assert all(profile["disposition"] == "SUPPORTS_FURTHER_RESEARCH" for profile in report["profiles"])
    assert report["disposition"] == "SUPPORTS_FURTHER_RESEARCH"
    assert report["can_qualify"] is False and report["can_place_orders"] is False
    body = {key: value for key, value in report.items() if key != "report_sha256"}
    assert hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest() == report["report_sha256"]
    assert await evaluate_comparison_protocol(path, **{**args, "now": _at("2026-09-16T00:00:00Z")}) == report


@pytest.mark.asyncio
async def test_causal_range_profile_uses_ordinary_predeclared_gates(tmp_path):
    """A dedicated range profile is no longer mislabeled as a confirmation alias."""
    from dataclasses import replace

    manifest = _manifest()
    manifest["holdout_sessions"] = ["2026-09-11"]
    manifest["alternatives"] = [{
        "name": "range", "entry": "RANGE_REVERSION_V1",
        "exit": "STOP_TARGET_TIME_V1",
    }]
    manifest["baseline"] = "range"
    path = str(tmp_path / "range.db")
    await freeze_comparison_protocol(
        path, manifest, now=_at("2026-09-10T01:00:00Z"),
    )
    proposal = replace(
        _proposal(), entry_deadline=_at("2026-09-11T04:20:00Z"),
    )
    cutoff = _at("2026-09-11T04:00:00Z")
    bars = []
    for index in range(14):
        close = 100.0 + (index % 4 - 1.5) * .03
        bars.append({
            "timestamp": (cutoff - timedelta(
                minutes=(14 - index) * 5,
            )).isoformat(),
            "open": close, "high": close + .5, "low": close - .5,
            "close": close,
        })
    bars.extend([
        {"timestamp": "2026-09-11T04:05:00+00:00", "open": 100,
         "high": 100.2, "low": 99.4, "close": 99.8},
        {"timestamp": "2026-09-11T04:10:00+00:00", "open": 99.9,
         "high": 100.2, "low": 99.8, "close": 100.1},
    ])
    report = await evaluate_comparison_protocol(
        path, protocol_id="independent", report_id="range-causal",
        proposals=[proposal], future_bars={proposal.opportunity_id: bars},
        session_coverage={"range": {"2026-09-11": "COMPLETE"}},
        now=_at("2026-09-12T00:00:00Z"),
    )
    profile = report["profiles"][0]
    assert profile["semantic_limitation"] is None
    assert profile["baseline"]["closed"] == 1, profile["outcomes"]["baseline"][0]["reason"]
    assert profile["stress"]["closed"] == 1
    assert profile["disposition"] == "SUPPORTS_FURTHER_RESEARCH"
    assert report["approval_usable"] is False
