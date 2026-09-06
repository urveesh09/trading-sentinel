from datetime import datetime, timedelta, timezone

import pytest

from proactive_intelligence import (
    ShadowProposal, allocate_shadow_proposals, build_shadow_proposals, proactive_activity_report,
    size_shadow_allocations,
    record_opportunity_event,
    record_cash_flow, proactive_inactivity_diagnostics, record_scan_run,
    run_configured_shadow_workflow, run_shadow_workflow,
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
    assert await record_scan_run(db_path, scan_id="scan-1", policy_id="trend_pullback_v1", account_id="dev", mode="SHADOW", status="SUCCESS", observed_at=now)
    report = await proactive_activity_report(db_path)
    shadow = report["modes"]["SHADOW"]
    assert shadow["scan_evaluations"] == 1
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
    bars[-3].update({"open": 102.1, "high": 102.4, "low": 101.8, "close": 102.0})
    bars[-2].update({"open": 102.0, "high": 102.4, "low": 101.8, "close": 102.1})
    bars[-1].update({"open": 103.8, "close": 104.0, "high": 104.2, "low": 103.4, "volume": 300})
    proposals = build_shadow_proposals("NSE:DEMO", bars, now=now + timedelta(minutes=1))
    assert proposals
    selected, reasons = allocate_shadow_proposals(proposals, capital=8_000, reserved=7_900)
    assert selected == []
    assert set(reasons.values()) == {"INSUFFICIENT_SHADOW_CASH_AFTER_COST_RESERVE"}
    assert build_shadow_proposals("NSE:DEMO", bars, now=now - timedelta(days=1)) == []


def test_shadow_simulator_is_costed_and_conservative_on_ambiguous_bar():
    now = datetime.now(timezone.utc)
    proposal = ShadowProposal("opp", "trend_pullback_v1", "NSE:DEMO", 100, 95, 110,
                              now + timedelta(minutes=15), 1, 100, "test", now, now,
                              now + timedelta(minutes=15), now + timedelta(hours=1))
    result = simulate_shadow_trade(proposal, [{"timestamp": (now + timedelta(minutes=5)).isoformat(),
                                                "open": 100, "high": 111, "low": 94, "close": 107}], cash=1_000)
    assert result.status == "CLOSED"
    assert result.reason == "AMBIGUOUS_BAR_STOP_FIRST"
    assert result.net_pnl < 0
    assert simulate_shadow_trade(proposal, [{"timestamp": (now + timedelta(minutes=5)).isoformat(), "open": 100, "high": 101, "low": 99, "close": 100}], cash=10).reason == "INSUFFICIENT_CASH_AFTER_FEES"


def test_shared_allocation_reserves_cash_once_and_rejects_gap_overspend():
    now = datetime.now(timezone.utc)
    first = ShadowProposal("one", "trend_pullback_v1", "NSE:ONE", 100, 95, 110, now + timedelta(minutes=10), 2, 100, "x", now, now, now + timedelta(minutes=10), now + timedelta(hours=1))
    second = ShadowProposal("two", "range_reversion_v1", "NSE:TWO", 100, 95, 110, now + timedelta(minutes=10), 1, 100, "x", now, now, now + timedelta(minutes=10), now + timedelta(hours=1))
    allocations, reasons = size_shadow_allocations([first, second], capital=1_000)
    assert len(allocations) == 1 and reasons["two"] == "INSUFFICIENT_SHADOW_CASH_AFTER_COST_RESERVE"
    gap = [{"timestamp": (now + timedelta(minutes=1)).isoformat(), "open": 200, "high": 201, "low": 199, "close": 200}]
    assert simulate_shadow_trade(first, gap, cash=1_000, allocation=allocations[0]).reason == "ALLOCATION_NO_LONGER_FEASIBLE"


@pytest.mark.asyncio
async def test_open_shadow_position_reserves_cash_and_closes_on_a_later_bar(db_path):
    from proactive_intelligence import _advance_open_shadow_positions, _persist_new_shadow_position, _shadow_account_state

    now = datetime.now(timezone.utc)
    proposal = ShadowProposal("durable", "trend_pullback_v1", "NSE:DURABLE", 100, 95, 110,
                              now + timedelta(minutes=15), 1, 100, "test", now, now,
                              now + timedelta(minutes=15), now + timedelta(hours=1))
    entry_bar = {"timestamp": (now + timedelta(minutes=5)).isoformat(), "open": 100, "high": 101, "low": 99, "close": 100}
    opened = simulate_shadow_trade(proposal, [entry_bar], cash=1_000)
    assert opened.status == "OPEN" and opened.entry_at is not None and opened.last_bar_at is not None
    assert await _persist_new_shadow_position(db_path, proposal=proposal, account_id="demo", result=opened)
    assert not await _persist_new_shadow_position(db_path, proposal=proposal, account_id="demo", result=opened)
    free_after_entry, instruments, identities = await _shadow_account_state(db_path, account_id="demo", scenario_capital=1_000)
    assert 0 < free_after_entry < 1_000
    assert instruments == {"NSE:DURABLE"} and identities == {"durable"}

    # The first bar is replayed with a later stop bar. It must be ignored, then
    # the later bar conservatively closes the durable position at the stop/gap.
    stop_bar = {"timestamp": (now + timedelta(minutes=10)).isoformat(), "open": 94, "high": 96, "low": 93, "close": 94}
    updates = await _advance_open_shadow_positions(db_path, account_id="demo", future_bars={"NSE:DURABLE": [entry_bar, stop_bar]})
    assert len(updates) == 1 and updates[0][1].status == "CLOSED"
    free_after_close, instruments, identities = await _shadow_account_state(db_path, account_id="demo", scenario_capital=1_000)
    assert instruments == set() and identities == {"durable"}
    assert free_after_close < 1_000, "loss and both-side costs must reduce synthetic cash"
    portfolio = (await proactive_activity_report(db_path))["shadow_positions"]
    assert portfolio == [pytest.approx({"account_id": "demo", "run_id": "legacy", "open_positions": 0, "closed_positions": 1,
                                        "reserved_capital": 0.0, "gross_pnl": updates[0][1].gross_pnl,
                                        "fees": updates[0][1].fees, "net_pnl": updates[0][1].net_pnl})]


def test_shadow_simulator_rejects_duplicate_or_malformed_future_timestamps():
    now = datetime.now(timezone.utc)
    proposal = ShadowProposal("ordered", "trend_pullback_v1", "NSE:ORDERED", 100, 95, 110,
                              now + timedelta(minutes=15), 1, 100, "test", now, now,
                              now + timedelta(minutes=15), now + timedelta(hours=1))
    duplicate = [{"timestamp": (now + timedelta(minutes=5)).isoformat(), "open": 100, "high": 101, "low": 99, "close": 100}] * 2
    assert simulate_shadow_trade(proposal, duplicate, cash=1_000).reason == "INVALID_OR_UNORDERED_FUTURE_BARS"


@pytest.mark.asyncio
async def test_workflow_clock_cannot_close_an_open_position_from_a_future_bar(db_path):
    from proactive_intelligence import _persist_new_shadow_position, _shadow_account_state

    base = datetime.now(timezone.utc)
    proposal = ShadowProposal("clocked", "trend_pullback_v1", "NSE:CLOCK", 100, 95, 110,
                              base + timedelta(minutes=15), 1, 100, "test", base, base,
                              base + timedelta(minutes=15), base + timedelta(hours=1))
    entry = {"timestamp": (base + timedelta(minutes=1)).isoformat(), "open": 100, "high": 101, "low": 99, "close": 100}
    stop = {"timestamp": (base + timedelta(minutes=10)).isoformat(), "open": 94, "high": 96, "low": 93, "close": 94}
    opened = simulate_shadow_trade(proposal, [entry], cash=1_000)
    assert await _persist_new_shadow_position(db_path, proposal=proposal, account_id="clock", result=opened)

    early = await run_shadow_workflow(db_path, account_id="clock", universe={}, now=base + timedelta(minutes=5), scenario_capital=1_000, future_bars={"NSE:CLOCK": [entry, stop]})
    early_cash, open_instruments, _ = await _shadow_account_state(db_path, account_id="clock", scenario_capital=1_000)
    assert early["managed_positions"] == 0 and open_instruments == {"NSE:CLOCK"}
    assert early["free_cash"] == pytest.approx(early_cash)

    later = await run_shadow_workflow(db_path, account_id="clock", universe={}, now=base + timedelta(minutes=10), scenario_capital=1_000, future_bars={"NSE:CLOCK": [entry, stop]})
    late_cash, open_instruments, _ = await _shadow_account_state(db_path, account_id="clock", scenario_capital=1_000)
    assert later["managed_positions"] == 1 and open_instruments == set()
    assert later["free_cash"] == pytest.approx(late_cash)
    assert early_cash < late_cash < 1_000


@pytest.mark.asyncio
async def test_workflow_expires_pending_watchlist_when_instrument_disappears(db_path):
    import aiosqlite

    now = datetime.now(timezone.utc)
    await record_opportunity_event(
        db_path, opportunity_id="pending-expiry", policy_id="trend_pullback_v1", policy_version="v1",
        account_id="pending", mode="SHADOW", instrument="NSE:MISSING", stage="SETUP",
        reason_code="COMPLETED_BAR", idempotency_key="pending-expiry:setup", observed_at=now,
        valid_until=now + timedelta(minutes=5),
    )
    assert await transition_watchlist(db_path, opportunity_id="pending-expiry", state="WATCHING", reason="SETUP", now=now, valid_until=now + timedelta(minutes=5))
    assert await transition_watchlist(db_path, opportunity_id="pending-expiry", state="ARMED", reason="READY", now=now + timedelta(minutes=1))
    result = await run_shadow_workflow(db_path, account_id="pending", universe={}, now=now + timedelta(minutes=6), scenario_capital=1_000)
    async with aiosqlite.connect(db_path) as db:
        state = await (await db.execute("SELECT state FROM proactive_watchlist WHERE opportunity_id='pending-expiry'")).fetchone()
        expiry_events = await (await db.execute("SELECT COUNT(*) FROM proactive_events WHERE idempotency_key='pending-expiry:expired'")).fetchone()
    assert result["expired_pending"] == 1 and state[0] == "EXPIRED" and expiry_events[0] == 1


@pytest.mark.asyncio
async def test_shadow_runs_isolate_identical_setups_by_account_and_manifest(db_path):
    import aiosqlite

    base = datetime.now(timezone.utc)
    bars = [{"timestamp": (base - timedelta(minutes=(20-index)*15)).isoformat(), "open": 100+index*.15-.2, "high": 100+index*.15+.3, "low": 100+index*.15-.4, "close": 100+index*.15, "volume": 100} for index in range(21)]
    bars[-3].update({"open": 102.1, "high": 102.4, "low": 101.8, "close": 102})
    bars[-2].update({"open": 102.0, "high": 102.4, "low": 101.8, "close": 102.1})
    bars[-1].update({"open": 103.8, "close": 104, "high": 104.2, "low": 103.4, "volume": 300})
    entry = {"timestamp": (base + timedelta(minutes=5)).isoformat(), "open": 104, "high": 105, "low": 103, "close": 104}
    kwargs = {"universe": {"NSE:IDENTITY": bars}, "now": base + timedelta(minutes=5),
              "future_bars": {"NSE:IDENTITY": [entry]}, "scenario_capital": 1_000, "run_id": "scenario-a"}
    await run_shadow_workflow(db_path, account_id="account-A", **kwargs)
    await run_shadow_workflow(db_path, account_id="account-B", **kwargs)
    await run_shadow_workflow(db_path, account_id="account-A", **kwargs)
    async with aiosqlite.connect(db_path) as db:
        count = await (await db.execute("SELECT COUNT(*) FROM proactive_shadow_positions")).fetchone()
    assert count[0] == 2
    with pytest.raises(ValueError, match="manifest conflicts"):
        await run_shadow_workflow(db_path, account_id="account-A", **{**kwargs, "scenario_capital": 1_200})


@pytest.mark.asyncio
async def test_watchlist_lifecycle_cannot_be_reset_by_repeated_scan(db_path):
    now = datetime.now(timezone.utc)
    assert await transition_watchlist(db_path, opportunity_id="watch-1", state="WATCHING", reason="NEW", now=now, valid_until=now + timedelta(minutes=10))
    assert await transition_watchlist(db_path, opportunity_id="watch-1", state="ARMED", reason="READY", now=now + timedelta(minutes=1))
    assert not await transition_watchlist(db_path, opportunity_id="watch-1", state="WATCHING", reason="REPEATED_SCAN", now=now + timedelta(minutes=2))


@pytest.mark.asyncio
async def test_funding_is_not_profit_and_dropped_workflow_is_visible(db_path):
    now = datetime.now(timezone.utc)
    assert await record_cash_flow(db_path, flow_id="deposit-1", mode="LIVE", flow_type="DEPOSIT", amount=8_000, occurred_at=now, note="owner funding")
    assert not await record_cash_flow(db_path, flow_id="deposit-1", mode="LIVE", flow_type="DEPOSIT", amount=8_000, occurred_at=now, note="owner funding")
    await record_opportunity_event(db_path, opportunity_id="dropped", policy_id="trend_pullback_v1", policy_version="1", account_id="dev", mode="SHADOW", instrument="NSE:DEMO", stage="RISK_APPROVED", reason_code="OK", idempotency_key="dropped-1", observed_at=now)
    await record_scan_run(db_path, scan_id="scan-dropped", policy_id="trend_pullback_v1", account_id="dev", mode="SHADOW", status="SUCCESS", observed_at=now)
    report = await proactive_activity_report(db_path)
    assert report["funding_flows"]["LIVE"]["DEPOSIT"] == 8_000
    assert "profit" in report["note"].lower()
    assert {row["code"] for row in await proactive_inactivity_diagnostics(db_path, now=now + timedelta(minutes=61))} >= {"MISSED_SCAN_INTERVALS", "DROPPED_RISK_APPROVED_WORKFLOW"}


@pytest.mark.asyncio
async def test_shadow_workflow_records_real_scan_setup_selection_and_outcome(db_path):
    now = datetime.now(timezone.utc)
    bars = [{"timestamp": (now - timedelta(minutes=(20-index)*15)).isoformat(), "open": 100+index*.15-.2, "high": 100+index*.15+.3, "low": 100+index*.15-.4, "close": 100+index*.15, "volume": 100} for index in range(21)]
    bars[-3].update({"open": 102.1, "high": 102.4, "low": 101.8, "close": 102})
    bars[-2].update({"open": 102.0, "high": 102.4, "low": 101.8, "close": 102.1})
    bars[-1].update({"open": 103.8, "close": 104, "high": 104.2, "low": 103.4, "volume": 300})
    result = await run_shadow_workflow(db_path, account_id="demo", universe={"NSE:DEMO": bars}, now=now + timedelta(minutes=1), future_bars={"NSE:DEMO": [{"timestamp": (now + timedelta(minutes=5)).isoformat(), "open": 104, "high": 105, "low": 103, "close": 104}]})
    assert result["mode"] == "SHADOW" and result["proposals"] >= 1
    report = await proactive_activity_report(db_path)
    assert report["modes"]["SHADOW"]["scan_evaluations"] >= 1
    assert report["modes"]["SHADOW"]["stages"]["SETUP"] >= 1


@pytest.mark.asyncio
async def test_identical_shadow_workflow_rerun_does_not_create_a_second_scan(db_path):
    import aiosqlite
    now = datetime.now(timezone.utc)
    bars = [{"timestamp": (now - timedelta(minutes=(20-index)*15)).isoformat(), "open": 100+index*.15-.2, "high": 100+index*.15+.3, "low": 100+index*.15-.4, "close": 100+index*.15, "volume": 100} for index in range(21)]
    bars[-3].update({"open": 102.1, "high": 102.4, "low": 101.8, "close": 102})
    bars[-2].update({"open": 102.0, "high": 102.4, "low": 101.8, "close": 102.1})
    bars[-1].update({"open": 103.8, "close": 104, "high": 104.2, "low": 103.4, "volume": 300})
    kwargs = {"account_id": "demo", "universe": {"NSE:DEMO": bars}, "future_bars": {"NSE:DEMO": []}}
    first = await run_shadow_workflow(db_path, now=now + timedelta(minutes=1), **kwargs)
    before = (await proactive_activity_report(db_path))["modes"]["SHADOW"]["scan_evaluations"]
    async with aiosqlite.connect(db_path) as db:
        before_events = await (await db.execute("SELECT COUNT(*) FROM proactive_events")).fetchone()
        before_positions = await (await db.execute("SELECT COUNT(*) FROM proactive_shadow_positions")).fetchone()
    retry = await run_shadow_workflow(db_path, now=now + timedelta(minutes=1), **kwargs)
    async with aiosqlite.connect(db_path) as db:
        event_count = await (await db.execute("SELECT COUNT(*) FROM proactive_events")).fetchone()
        position_count = await (await db.execute("SELECT COUNT(*) FROM proactive_shadow_positions")).fetchone()
    after = (await proactive_activity_report(db_path))["modes"]["SHADOW"]["scan_evaluations"]
    assert retry == first and before == after
    assert event_count == before_events and position_count == before_positions


@pytest.mark.asyncio
async def test_resumed_shadow_position_uses_persisted_zero_cost_manifest(db_path):
    import aiosqlite

    base = datetime.now(timezone.utc)
    bars = [{"timestamp": (base - timedelta(minutes=(20-index)*15)).isoformat(), "open": 100+index*.15-.2, "high": 100+index*.15+.3, "low": 100+index*.15-.4, "close": 100+index*.15, "volume": 100} for index in range(21)]
    bars[-3].update({"open": 102.1, "high": 102.4, "low": 101.8, "close": 102})
    bars[-2].update({"open": 102.0, "high": 102.4, "low": 101.8, "close": 102.1})
    bars[-1].update({"open": 103.8, "close": 104, "high": 104.2, "low": 103.4, "volume": 300})
    entry = {"timestamp": (base + timedelta(minutes=5)).isoformat(), "open": 104, "high": 105, "low": 103, "close": 104}
    stop = {"timestamp": (base + timedelta(minutes=10)).isoformat(), "open": 94, "high": 96, "low": 93, "close": 94}
    common = {"account_id": "cost-account", "run_id": "zero-cost", "universe": {"NSE:COST": bars},
              "scenario_capital": 1_000, "fee_rate": 0, "slippage_bps": 0,
              "future_bars": {"NSE:COST": [entry, stop]}}
    await run_shadow_workflow(db_path, now=base + timedelta(minutes=5), **common)
    await run_shadow_workflow(db_path, now=base + timedelta(minutes=10), **common)
    async with aiosqlite.connect(db_path) as db:
        row = await (await db.execute("SELECT status,entry_fees,exit_fees,net_pnl,gross_pnl FROM proactive_shadow_positions")).fetchone()
    assert row[0] == "CLOSED" and row[1] == row[2] == 0
    assert row[3] == pytest.approx(row[4])


@pytest.mark.asyncio
async def test_configured_shadow_runner_is_opt_in_and_records_unavailable_fixture_source(tmp_path, monkeypatch):
    from config import settings

    now = datetime.now(timezone.utc)
    monkeypatch.setattr(settings, "PROACTIVE_SHADOW_ENABLED", False)
    assert (await run_configured_shadow_workflow(now=now))["state"] == "DISABLED"

    monkeypatch.setattr(settings, "PROACTIVE_SHADOW_ENABLED", True)
    monkeypatch.setattr(settings, "PROACTIVE_SHADOW_FIXTURE_PATH", "")
    monkeypatch.setattr(settings, "PROACTIVE_SHADOW_ACCOUNT_ID", "dev-fixture")
    assert (await run_configured_shadow_workflow(now=now))["state"] == "FIXTURE_SOURCE_UNCONFIGURED"
    report = await proactive_activity_report(settings.DB_PATH)
    assert report["modes"]["SHADOW"]["scan_evaluations"] == 0
    diagnostics = await proactive_inactivity_diagnostics(settings.DB_PATH, now=now)
    assert any(row["code"] == "SCANNER_SOURCE_UNAVAILABLE" and row["reason"] == "FIXTURE_SOURCE_UNCONFIGURED" for row in diagnostics)

    fixture = tmp_path / "shadow_fixture.json"
    fixture.write_text('{"mode":"LIVE","universe":{}}', encoding="utf-8")
    monkeypatch.setattr(settings, "PROACTIVE_SHADOW_FIXTURE_PATH", str(fixture))
    assert (await run_configured_shadow_workflow(now=now + timedelta(minutes=1)))["state"] == "FIXTURE_SOURCE_INVALID"
