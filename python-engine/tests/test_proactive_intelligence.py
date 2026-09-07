from datetime import datetime, timedelta, timezone

import json

import pytest

from proactive_intelligence import (
    ShadowProposal, ShadowSimulation, allocate_shadow_proposals, build_shadow_proposals, proactive_activity_report,
    proactive_shadow_comparison, proactive_shadow_research_report, run_shadow_research_comparison,
    size_shadow_allocations,
    record_opportunity_event,
    record_cash_flow, proactive_inactivity_diagnostics, proactive_session_diagnostics, record_scan_run,
    run_configured_shadow_workflow, run_shadow_workflow,
    simulate_shadow_trade,
    transition_watchlist,
    shadow_history_state,
)


@pytest.mark.asyncio
async def test_five_eligible_session_diagnostics_are_calendar_aware_and_scope_isolated(db_path):
    # 2026-09-01 through 2026-09-07 contains five NSE sessions (weekend
    # excluded). The last two successful sessions deliberately have no viable
    # candidate, while the whole window has one fill.
    base = datetime(2026, 9, 1, 10, tzinfo=timezone.utc)
    policy, account = "trend_pullback_v1", "diagnostic-account"
    for index, day in enumerate((1, 2, 3, 4, 7), start=1):
        at = base.replace(day=day)
        assert await record_scan_run(
            db_path, scan_id=f"five-session-{index}", policy_id=policy,
            account_id=account, mode="SHADOW", status="SUCCESS", observed_at=at,
        )
    assert await record_opportunity_event(
        db_path, opportunity_id="five-session-filled", policy_id=policy, policy_version="v1",
        account_id=account, mode="SHADOW", instrument="SYNTH:FILL", stage="FILLED",
        reason_code="NEXT_EXECUTABLE_OPEN", idempotency_key="five-session-filled",
        observed_at=base.replace(day=3),
    )
    # An unavailable second account must not contaminate the healthy scope.
    assert await record_scan_run(
        db_path, scan_id="other-account", policy_id=policy, account_id="other-account",
        mode="SHADOW", status="UNAVAILABLE", reason="FIXTURE_SOURCE_INVALID", observed_at=base.replace(day=7),
    )

    report = await proactive_session_diagnostics(
        db_path, now=base.replace(day=7, hour=15), session_count=5,
    )
    scoped = next(row for row in report["reports"] if row["scope"]["account_id"] == account)
    assert scoped["eligible_sessions"] == ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-07"]
    assert scoped["scan_health"]["successful_sessions"] == 5
    assert scoped["activity"]["fills"] == 1
    codes = {row["code"] for row in scoped["findings"]}
    assert codes == {"TWO_ELIGIBLE_SESSIONS_NO_VIABLE_CANDIDATES", "FIVE_ELIGIBLE_SESSIONS_SPARSE_FILLS"}
    other = next(row for row in report["reports"] if row["scope"]["account_id"] == "other-account")
    assert other["scan_health"]["unavailable_sessions"] == 1
    assert "ELIGIBLE_SESSION_SCAN_HEALTH_INCOMPLETE" in {row["code"] for row in other["findings"]}


@pytest.mark.asyncio
async def test_session_diagnostics_make_never_configured_explicit(db_path):
    report = await proactive_session_diagnostics(
        db_path, now=datetime(2026, 9, 7, 15, tzinfo=timezone.utc), session_count=5,
    )
    assert report["reports"] == []
    assert report["findings"] == [{"code": "SCANNER_NEVER_CONFIGURED_OR_RAN"}]
    assert report["can_place_orders"] is False


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


@pytest.mark.asyncio
async def test_invalid_or_insufficient_shadow_history_is_unavailable_not_a_success(db_path):
    import aiosqlite

    now = datetime.now(timezone.utc)
    malformed = [{"timestamp": now.isoformat(), "open": 100, "high": 99,
                  "low": 98, "close": 100, "volume": 10}]
    assert shadow_history_state(malformed, now=now) == "INSUFFICIENT_HISTORY"
    result = await run_shadow_workflow(
        db_path, account_id="history", now=now, scenario_capital=1_000,
        universe={"NSE:BAD": malformed}, future_bars={},
    )
    assert result["proposals"] == 0
    async with aiosqlite.connect(db_path) as db:
        row = await (await db.execute(
            "SELECT status,reason FROM proactive_scan_runs WHERE account_id='history'"
        )).fetchone()
    assert tuple(row) == ("UNAVAILABLE", "INSUFFICIENT_HISTORY")


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
    assert len(allocations) == 2 and all(reasons[item.opportunity_id] == "SELECTED" for item in allocations)
    assert sum(item.reserved_capital for item in allocations) <= 1_000
    assert sum(item.initial_risk for item in allocations) <= 1_000 * .05
    gap = [{"timestamp": (now + timedelta(minutes=1)).isoformat(), "open": 200, "high": 201, "low": 199, "close": 200}]
    assert simulate_shadow_trade(first, gap, cash=1_000, allocation=allocations[0]).reason == "ALLOCATION_NO_LONGER_FEASIBLE"


def test_risk_sized_shadow_allocator_bounds_stop_risk_and_does_not_rank_raw_scales_as_probabilities():
    now = datetime.now(timezone.utc)
    tight = ShadowProposal("tight", "trend_pullback_v1", "SYNTH:TIGHT", 100, 98, 106,
                           now + timedelta(minutes=10), 1.005, 100, "x", now, now,
                           now + timedelta(minutes=10), now + timedelta(hours=1))
    wide = ShadowProposal("wide", "contraction_breakout_v1", "SYNTH:WIDE", 100, 80, 140,
                          now + timedelta(minutes=10), 4.0, 100, "x", now, now,
                          now + timedelta(minutes=10), now + timedelta(hours=1))
    allocations, reasons = size_shadow_allocations([wide, tight], capital=10_000)
    quantities = {item.opportunity_id: item.quantity for item in allocations}
    assert quantities["wide"] < quantities["tight"], "a wider stop may not increase position size"
    assert sum(item.initial_risk for item in allocations) <= 500
    assert all(reason == "SELECTED" for reason in reasons.values())


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
    assert len(portfolio) == 1
    row = portfolio[0]
    assert (row["account_id"], row["run_id"], row["open_positions"], row["closed_positions"]) == ("demo", "legacy", 0, 1)
    assert row["reserved_capital"] == 0
    assert row["gross_pnl"] == pytest.approx(updates[0][1].gross_pnl)
    assert row["fees"] == pytest.approx(updates[0][1].fees)
    assert row["net_pnl"] == pytest.approx(updates[0][1].net_pnl)
    assert row["scenario_capital"] is row["free_cash"] is row["marked_unrealized_pnl"] is None
    assert row["unrealized_state"] == "UNAVAILABLE_NO_CURRENT_MARK"


@pytest.mark.asyncio
async def test_shadow_evidence_repair_does_not_change_a_persisted_fill(db_path):
    from proactive_intelligence import _persist_new_shadow_position, repair_shadow_evidence
    now = datetime.now(timezone.utc)
    proposal = ShadowProposal("repair", "trend_pullback_v1", "NSE:REPAIR", 100, 95, 110,
                              now + timedelta(minutes=15), 1, 100, "test", now, now,
                              now + timedelta(minutes=15), now + timedelta(hours=1))
    result = simulate_shadow_trade(proposal, [{"timestamp": (now + timedelta(minutes=1)).isoformat(),
                                                "open": 100, "high": 101, "low": 99, "close": 100}], cash=1_000)
    assert await _persist_new_shadow_position(db_path, proposal=proposal, account_id="repair", result=result)
    # New positions and their FILLED evidence are one transaction. Repair is
    # retained only for evidence created by older releases.
    assert await repair_shadow_evidence(db_path, account_id="repair") == 0
    assert await repair_shadow_evidence(db_path, account_id="repair") == 0


@pytest.mark.asyncio
async def test_shadow_position_lifecycle_and_events_commit_together(db_path):
    import aiosqlite
    from proactive_intelligence import _advance_open_shadow_positions, _persist_new_shadow_position

    now = datetime.now(timezone.utc)
    proposal = ShadowProposal("atomic", "trend_pullback_v1", "NSE:ATOMIC", 100, 95, 110,
                              now + timedelta(minutes=15), 1, 100, "test", now, now,
                              now + timedelta(minutes=15), now + timedelta(hours=1))
    entry = {"timestamp": (now + timedelta(minutes=1)).isoformat(), "open": 100, "high": 101, "low": 99, "close": 100}
    opened = simulate_shadow_trade(proposal, [entry], cash=1_000)
    assert await _persist_new_shadow_position(db_path, proposal=proposal, account_id="atomic", result=opened)
    async with aiosqlite.connect(db_path) as db:
        [filled] = await (await db.execute("SELECT stage FROM proactive_events WHERE opportunity_id='atomic'")).fetchall()
    assert filled[0] == "FILLED"

    stop = {"timestamp": (now + timedelta(minutes=2)).isoformat(), "open": 94, "high": 96, "low": 93, "close": 94}
    assert len(await _advance_open_shadow_positions(
        db_path, account_id="atomic", future_bars={"NSE:ATOMIC": [entry, stop]},
    )) == 1
    async with aiosqlite.connect(db_path) as db:
        events = await (await db.execute(
            "SELECT stage FROM proactive_events WHERE opportunity_id='atomic' ORDER BY event_id"
        )).fetchall()
        status = await (await db.execute(
            "SELECT status FROM proactive_shadow_positions WHERE opportunity_id='atomic'"
        )).fetchone()
        watchlist = await (await db.execute(
            "SELECT state FROM proactive_watchlist WHERE opportunity_id='atomic'"
        )).fetchone()
    assert [row[0] for row in events] == ["FILLED", "CLOSED"]
    assert status[0] == "CLOSED"
    assert watchlist is None, "legacy direct persistence does not fabricate a watchlist"


@pytest.mark.asyncio
async def test_shadow_step_lease_serializes_workers_and_recovers_only_after_expiry(db_path):
    import aiosqlite
    from proactive_intelligence import _claim_shadow_step, _ensure_shadow_run

    now = datetime.now(timezone.utc)
    run_key = await _ensure_shadow_run(
        db_path, account_id="lease", run_id="lease-v1", scenario_capital=1_000,
        fee_rate=.001, slippage_bps=5,
    )
    assert await _claim_shadow_step(db_path, run_key=run_key, as_of=now, input_digest="one", origin="SHADOW") is None
    with pytest.raises(RuntimeError, match="active evaluation"):
        await _claim_shadow_step(
            db_path, run_key=run_key, as_of=now + timedelta(minutes=1), input_digest="two", origin="SHADOW",
        )
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE proactive_shadow_run_steps SET claimed_at=? WHERE run_key=? AND as_of=?",
            ((now - timedelta(minutes=6)).isoformat(), run_key, now.isoformat()),
        )
        await db.commit()
    assert await _claim_shadow_step(
        db_path, run_key=run_key, as_of=now + timedelta(minutes=1), input_digest="two", origin="SHADOW",
    ) is None
    async with aiosqlite.connect(db_path) as db:
        prior = await (await db.execute(
            "SELECT status FROM proactive_shadow_run_steps WHERE run_key=? AND as_of=?",
            (run_key, now.isoformat()),
        )).fetchone()
    assert prior[0] == "ABANDONED"


@pytest.mark.asyncio
async def test_shadow_activity_reports_completed_bar_mark_without_changing_cash(db_path):
    from proactive_intelligence import _persist_new_shadow_position
    now = datetime.now(timezone.utc)
    proposal = ShadowProposal("marked", "trend_pullback_v1", "NSE:MARK", 100, 95, 110,
                              now + timedelta(minutes=15), 1, 100, "test", now, now,
                              now + timedelta(minutes=15), now + timedelta(hours=1))
    result = simulate_shadow_trade(proposal, [{"timestamp": (now + timedelta(minutes=1)).isoformat(),
                                                "open": 100, "high": 103, "low": 99, "close": 102}], cash=1_000)
    assert await _persist_new_shadow_position(db_path, proposal=proposal, account_id="mark", result=result,
                                              marked_price=102, marked_at=result.last_bar_at)
    [row] = (await proactive_activity_report(db_path))["shadow_positions"]
    assert row["unrealized_state"] == "MARKED_COMPLETED_BAR"
    assert row["marked_unrealized_gross_pnl"] > 0
    assert row["free_cash"] is None, "legacy records cannot fabricate scenario capital"


@pytest.mark.asyncio
async def test_shadow_comparison_uses_only_costed_closed_outcomes_and_never_claims_authority(db_path):
    from proactive_intelligence import _persist_new_shadow_position

    now = datetime.now(timezone.utc)
    first = ShadowProposal("comparison-one", "trend_pullback_v1", "NSE:ONE", 100, 95, 110,
                           now + timedelta(minutes=15), 1, 100, "test", now, now,
                           now + timedelta(minutes=15), now + timedelta(hours=1))
    second = ShadowProposal("comparison-two", "trend_pullback_v1", "NSE:TWO", 100, 95, 110,
                            now + timedelta(minutes=15), 1, 100, "test", now, now,
                            now + timedelta(minutes=15), now + timedelta(hours=1))
    first_close = ShadowSimulation("CLOSED", 1, 100, 110, 10, .2, 9.8, "TARGET", now,
                                   now + timedelta(minutes=5))
    second_close = ShadowSimulation("CLOSED", 1, 100, 75, -25, .2, -25.2, "STOP", now,
                                    now + timedelta(minutes=10))
    assert await _persist_new_shadow_position(db_path, proposal=first, account_id="comparison", result=first_close)
    assert await _persist_new_shadow_position(db_path, proposal=second, account_id="comparison", result=second_close)

    report = await proactive_shadow_comparison(db_path)
    assert report["mode"] == "SHADOW"
    assert report["research_only"] is True
    assert report["can_place_orders"] is False
    assert report["authorization_effect"] == "NONE"
    [row] = report["comparisons"]
    assert row["policy_id"] == "trend_pullback_v1"
    assert row["closed_records"] == row["closed_outcomes"] == 2
    assert row["gross_pnl"] == pytest.approx(-15)
    assert row["costs"] == pytest.approx(.4)
    assert row["net_pnl"] == pytest.approx(-15.4)
    assert row["net_expectancy"] == pytest.approx(-7.7)
    assert row["max_drawdown"] == pytest.approx(25.2)
    assert row["profit_factor"] == pytest.approx(9.8 / 25.2)
    assert row["evidence_state"] == "INSUFFICIENT_CLOSED_OUTCOMES"
    assert row["exit_policy_comparison_state"] == "UNAVAILABLE_NOT_EXPERIMENT_TAGGED"
    assert row["exit_reasons"] == [
        {"reason": "STOP", "closed_outcomes": 1},
        {"reason": "TARGET", "closed_outcomes": 1},
    ]


@pytest.mark.asyncio
async def test_frozen_shadow_research_trials_retain_matched_entry_exit_nonfills(db_path):
    base = datetime.now(timezone.utc)
    common = dict(entry=100, stop=95, target=110, valid_until=base + timedelta(minutes=30),
                  score=1, required_capital=100, reason="test", signal_at=base, data_cutoff=base,
                  entry_deadline=base + timedelta(minutes=30), holding_deadline=base + timedelta(hours=4))
    proposals = [
        ShadowProposal("trial-fill", "trend_pullback_v1", "SYNTH:FILL", **common),
        ShadowProposal("trial-no-pullback", "trend_pullback_v1", "SYNTH:NO_PULLBACK", **common),
    ]
    future_bars = {
        "SYNTH:FILL": [
            {"timestamp": (base + timedelta(minutes=5)).isoformat(), "open": 105, "high": 106, "low": 104, "close": 105},
            {"timestamp": (base + timedelta(minutes=10)).isoformat(), "open": 100, "high": 101, "low": 99, "close": 100},
            {"timestamp": (base + timedelta(minutes=61)).isoformat(), "open": 100, "high": 101, "low": 99, "close": 100},
        ],
        "SYNTH:NO_PULLBACK": [
            {"timestamp": (base + timedelta(minutes=5)).isoformat(), "open": 105, "high": 106, "low": 104, "close": 105},
            {"timestamp": (base + timedelta(minutes=10)).isoformat(), "open": 106, "high": 107, "low": 105, "close": 106},
        ],
    }
    first = await run_shadow_research_comparison(
        db_path, research_run_id="fixture-entry-exit-v1", proposals=proposals,
        future_bars=future_bars, cash_per_trial=1_000, fee_rate=0, slippage_bps=0,
    )
    assert first["mode"] == "SHADOW" and first["can_place_orders"] is False
    assert first["opportunities"] == 2 and first["profile_trials"] == first["inserted_trials"] == 12
    retry = await run_shadow_research_comparison(
        db_path, research_run_id="fixture-entry-exit-v1", proposals=proposals,
        future_bars=future_bars, cash_per_trial=1_000, fee_rate=0, slippage_bps=0,
    )
    assert retry["inserted_trials"] == 0
    with pytest.raises(ValueError, match="manifest conflicts"):
        await run_shadow_research_comparison(
            db_path, research_run_id="fixture-entry-exit-v1", proposals=proposals,
            future_bars=future_bars, cash_per_trial=1_001, fee_rate=0, slippage_bps=0,
        )
    report = await proactive_shadow_research_report(db_path, research_run_id="fixture-entry-exit-v1")
    assert report["research_only"] is True and report["authorization_effect"] == "NONE"
    assert len(report["comparisons"]) == 6
    pullback = next(row for row in report["comparisons"] if row["entry_profile_id"] == "BOUNDED_PULLBACK_LIMIT_V1" and row["exit_profile_id"] == "STOP_TARGET_TIME_V1")
    assert pullback["trials"] == 2 and pullback["no_fills"] == 1 and pullback["open_trials"] == 1
    bounded_time = next(row for row in report["comparisons"] if row["entry_profile_id"] == "NEXT_EXECUTABLE_OPEN_V1" and row["exit_profile_id"] == "BOUNDED_TIME_EXIT_60M_V1")
    assert bounded_time["closed_outcomes"] == 1
    assert bounded_time["evidence_state"] == "INSUFFICIENT_CLOSED_OUTCOMES"


@pytest.mark.asyncio
async def test_isolated_proactive_demo_rejects_historical_backfill_and_proves_full_shadow_path(tmp_path):
    from proactive_demo import run_proactive_shadow_demo

    result = await run_proactive_shadow_demo(str(tmp_path / "proactive_demo.db"))
    assert result["mode"] == "SHADOW" and result["can_place_orders"] is False
    assert result["assertions"] == {
        "pending_expired": True, "one_affordable_allocation": True, "completed_bar_exit": True,
        "nonnegative_synthetic_cash": True, "matched_trials_retained": True,
        "five_session_inactivity_explained": True,
    }
    assert result["workflow"]["expiry_sweep"]["expired_pending"] == 1
    assert "MISSED_ENTRY_WINDOW_NO_HISTORICAL_BACKFILL" in result["workflow"]["managed"]["reasons"].values()
    [position] = result["activity"]["shadow_positions"]
    assert position["closed_positions"] == 1 and position["free_cash"] > position["scenario_capital"]
    diagnostic_scope = next(
        row for row in result["five_session_diagnostics"]["reports"]
        if row["scope"]["account_id"] == "demo-sparse-activity"
    )
    assert {row["code"] for row in diagnostic_scope["findings"]} == {
        "TWO_ELIGIBLE_SESSIONS_NO_VIABLE_CANDIDATES", "FIVE_ELIGIBLE_SESSIONS_SPARSE_FILLS",
    }


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
async def test_pending_expiry_is_run_scoped_and_records_state_and_event_together(db_path):
    """A later replay clock must not mutate another account/run's watchlist."""
    import aiosqlite
    from proactive_intelligence import _expire_pending_shadow_watchlists

    now = datetime.now(timezone.utc)
    for account, suffix in (("run-a", "a"), ("run-b", "b")):
        for state in ("WATCHING", "ARMED", "TRIGGERED", "DEFERRED", "SELECTED"):
            opportunity_id = f"expiry-{suffix}-{state.lower()}"
            assert await record_opportunity_event(
                db_path, opportunity_id=opportunity_id, policy_id="trend_pullback_v1", policy_version="v1",
                account_id=account, mode="SHADOW", instrument=f"SYNTH:{suffix}", stage="SETUP",
                reason_code="COMPLETED_BAR", idempotency_key=f"{opportunity_id}:setup", observed_at=now,
                valid_until=now + timedelta(minutes=1),
            )
            assert await transition_watchlist(
                db_path, opportunity_id=opportunity_id, state="WATCHING", reason="SETUP", now=now,
                valid_until=now + timedelta(minutes=1),
            )
            async with aiosqlite.connect(db_path) as db:
                await db.execute("UPDATE proactive_watchlist SET state=? WHERE opportunity_id=?", (state, opportunity_id))
                await db.commit()

    assert await _expire_pending_shadow_watchlists(db_path, account_id="run-a", now=now + timedelta(minutes=2)) == 5
    async with aiosqlite.connect(db_path) as db:
        a_states = await (await db.execute(
            "SELECT DISTINCT state FROM proactive_watchlist WHERE opportunity_id LIKE 'expiry-a-%'"
        )).fetchall()
        b_states = await (await db.execute(
            "SELECT DISTINCT state FROM proactive_watchlist WHERE opportunity_id LIKE 'expiry-b-%'"
        )).fetchall()
        a_events = await (await db.execute(
            "SELECT COUNT(*) FROM proactive_events WHERE opportunity_id LIKE 'expiry-a-%' AND stage='EXPIRED'"
        )).fetchone()
        b_events = await (await db.execute(
            "SELECT COUNT(*) FROM proactive_events WHERE opportunity_id LIKE 'expiry-b-%' AND stage='EXPIRED'"
        )).fetchone()
    assert a_states == [("EXPIRED",)] and a_events[0] == 5
    assert {row[0] for row in b_states} == {"WATCHING", "ARMED", "TRIGGERED", "DEFERRED", "SELECTED"}
    assert b_events[0] == 0


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
        manifest_row = await (await db.execute(
            "SELECT manifest_json FROM proactive_shadow_runs WHERE account_id='account-A'"
        )).fetchone()
    assert count[0] == 2
    manifest = json.loads(manifest_row[0])
    assert manifest["schema_version"] == "shadow-evidence-v2"
    assert len(manifest["implementation_sha256"]) == 64
    assert manifest["policy_manifest"]["allocator"] == "risk-budget-v1"
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
