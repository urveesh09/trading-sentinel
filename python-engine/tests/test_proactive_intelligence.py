from datetime import datetime, timedelta, timezone

import pytest

from proactive_intelligence import (
    ShadowProposal, allocate_shadow_proposals, build_shadow_proposals, proactive_activity_report,
    record_opportunity_event,
    simulate_shadow_trade,
    transition_watchlist,
)


@pytest.mark.asyncio
async def test_activity_events_are_idempotent_and_mode_separated(db_path):
    now = datetime.now(timezone.utc)
    common = dict(opportunity_id="trend:NSE:DEMO:1", policy_id="trend_pullback_v1",
                  policy_version="1", account_id="dev", mode="SHADOW", instrument="NSE:DEMO",
                  stage="SETUP", reason_code="COMPLETED_BAR", observed_at=now,
                  valid_until=now + timedelta(minutes=15), idempotency_key="setup-1")
    assert await record_opportunity_event(db_path, **common)
    assert not await record_opportunity_event(db_path, **common)
    assert await record_opportunity_event(
        db_path, **{**common, "stage": "DEFERRED", "reason_code": "CAPITAL_RESERVED",
                     "idempotency_key": "deferred-1"},
    )
    report = await proactive_activity_report(db_path)
    shadow = report["modes"]["SHADOW"]
    assert shadow["scan_evaluations"] == 2
    assert shadow["unique_opportunities"] == 1
    assert shadow["stages"]["SETUP"] == 1
    assert report["modes"]["LIVE"]["scan_evaluations"] == 0


def test_three_shadow_sleeves_use_completed_bars_and_allocator_preserves_cash():
    now = datetime.now(timezone.utc)
    bars = []
    for index in range(21):
        close = 100 + index * .15
        bars.append({"timestamp": (now - timedelta(minutes=(20-index)*15)).isoformat(),
                     "open": close-.2, "high": close+.3, "low": close-.4,
                     "close": close, "volume": 100})
    bars[-3]["close"] = 102.0
    bars[-2]["close"] = 102.1
    bars[-1].update({"close": 104.0, "high": 104.2, "low": 103.4, "volume": 300})
    proposals = build_shadow_proposals("NSE:DEMO", bars, now=now + timedelta(minutes=1))
    assert proposals
    selected, reasons = allocate_shadow_proposals(proposals, capital=8_000, reserved=7_900)
    assert selected == []
    assert set(reasons.values()) == {"INSUFFICIENT_SHADOW_CASH_AFTER_COST_RESERVE"}
    assert build_shadow_proposals("NSE:DEMO", bars, now=now - timedelta(days=1)) == []


def test_shadow_simulator_is_costed_and_conservative_on_ambiguous_bar():
    now = datetime.now(timezone.utc)
    proposal = ShadowProposal("opp", "trend_pullback_v1", "NSE:DEMO", 100, 95, 110,
                              now + timedelta(minutes=15), 1, 100, "test")
    result = simulate_shadow_trade(proposal, [{"timestamp": (now + timedelta(minutes=5)).isoformat(),
                                                "open": 100, "high": 111, "low": 94, "close": 107}], cash=1_000)
    assert result.status == "CLOSED"
    assert result.reason == "AMBIGUOUS_BAR_STOP_FIRST"
    assert result.net_pnl < 0
    assert simulate_shadow_trade(proposal, [], cash=10).reason == "INSUFFICIENT_CASH_AFTER_FEES"


@pytest.mark.asyncio
async def test_watchlist_lifecycle_cannot_be_reset_by_repeated_scan(db_path):
    now = datetime.now(timezone.utc)
    assert await transition_watchlist(db_path, opportunity_id="watch-1", state="WATCHING", reason="NEW", now=now, valid_until=now + timedelta(minutes=10))
    assert await transition_watchlist(db_path, opportunity_id="watch-1", state="ARMED", reason="READY", now=now + timedelta(minutes=1))
    assert not await transition_watchlist(db_path, opportunity_id="watch-1", state="WATCHING", reason="REPEATED_SCAN", now=now + timedelta(minutes=2))
