"""[WORKFLOW-G 2026-09-13] Trailing-stop exit profile acceptance.

Closes gap #6 of 6 from
``docs/2026-09-13-workflow-g-state-of-codebase-audit.md`` §6.

The trailing-stop profile is the third orthogonal axis to the existing
two exit profiles:

  - ``STOP_TARGET_TIME_V1`` (fixed stop + target + time-stop)
  - ``BOUNDED_TIME_EXIT_60M_V1`` (60-minute holding deadline)
  - ``TRAILING_STOP_V1`` (Chandelier-style trailing stop, this commit)

Hypothesis #5 (§11 'Exit profile comparison') needs a third point on the
matrix to do a meaningful comparison; this closure supplies that point.

This file proves:

  1. The constant is shipped in ``_SHADOW_EXIT_PROFILES``.
  2. The dispatcher's enum-check accepts ``TRAILING_STOP_V1`` and rejects
     unknown exit ids (negative control preserved).
  3. The trailing simulator exits with ``TRAILING_STOP`` when the price
     breaches the (ratcheting) trailing level.
  4. The trailing simulator exits with ``HOLDING_DEADLINE`` when the bar
     falls past the configured holding deadline (matches the
     limit-pullback simulator's semantics).
  5. The trailing level is recomputed from the *previous* bar's high,
     never from the bar that triggered the exit (look-ahead safety).
  6. ``persist_exit_policy_comparison`` emits three rows instead of two
     after the change (deterministic count via the shipped constants).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from proactive_intelligence import (
    ShadowProposal,
    ShadowSimulation,
    _SHADOW_ENTRY_PROFILES,
    _SHADOW_EXIT_PROFILES,
    _simulate_shadow_trailing_stop,
    simulate_shadow_research_trial,
)


def _make_proposal(**overrides):
    """A valid proposal priced 100/95/110 with the typical timing."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    common = dict(
        entry=100.0, stop=95.0, target=110.0,
        valid_until=base + timedelta(minutes=30),
        score=1.0, required_capital=100.0, reason="trailing-stop-fixture",
        signal_at=base, data_cutoff=base,
        entry_deadline=base + timedelta(minutes=30),
        holding_deadline=base + timedelta(hours=4),
    )
    return ShadowProposal(
        opportunity_id="trailing-fixture",
        policy_id=overrides.pop("policy_id", "trend_pullback_v1"),
        instrument="NSE:TRAIL",
        **common,
        **overrides,
    )


def _bars(at, opens, highs, lows, closes):
    return [
        {
            "timestamp": (at + timedelta(minutes=index + 1)).isoformat(),
            "open": opens[index], "high": highs[index],
            "low": lows[index], "close": closes[index],
        }
        for index in range(len(opens))
    ]


# ---- 1: constant shipped ----------------------------------------------

def test_trailing_stop_is_in_shipped_exit_profiles() -> None:
    assert "TRAILING_STOP_V1" in _SHADOW_EXIT_PROFILES


# ---- 2: dispatcher acceptance + negative control ----------------------

class TestDispatcherAcceptance:
    def test_dispatcher_returns_simulation_for_trailing_stop(self) -> None:
        proposal = _make_proposal()
        at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        bars = _bars(at, [100] * 4, [100] * 4, [99] * 4, [100] * 4)
        sim = simulate_shadow_research_trial(
            proposal, bars, cash=1000,
            entry_profile_id="NEXT_EXECUTABLE_OPEN_V1",
            exit_profile_id="TRAILING_STOP_V1",
            fee_rate=0, slippage_bps=0,
        )
        assert sim is not None
        assert hasattr(sim, "status")
        assert sim.status in {"FILLED", "NO_FILL", "INVALID", "OPEN", "DEFERRED", "REJECTED"}

    def test_unknown_exit_profile_still_rejected(self) -> None:
        proposal = _make_proposal()
        at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        bars = _bars(at, [100] * 4, [100] * 4, [99] * 4, [100] * 4)
        with pytest.raises(ValueError, match="unsupported shadow research profile"):
            simulate_shadow_research_trial(
                proposal, bars, cash=1000,
                entry_profile_id="NEXT_EXECUTABLE_OPEN_V1",
                exit_profile_id="NOT_A_REAL_EXIT_V0",
                fee_rate=0, slippage_bps=0,
            )


# ---- 3: trailing-stop semantics ---------------------------------------

class TestTrailingStopSemantics:
    def test_trailing_stop_exits_when_low_breaches_trail(self) -> None:
        """After a small rally that raises the trail, a pullback closes the trade.

        Setup: entry at 100 (open + 0 slip = 100). Stop = 95 (entry_risk = 5).
        Bar 1: high 102 -> next-bar trail rises to 102 - 5 = 97.
        Bar 2: low 96 -> 96 < 97, exit TRAILING_STOP at min(100, 97) = 97.
        Fees are 0 in this test so we can read gross = exit - entry cleanly.
        """
        proposal = _make_proposal()
        at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        bars = _bars(
            at,
            opens=[100, 100, 100],
            highs=[101, 102, 100],
            lows=[99.5, 99.5, 96],   # bar 3 dips below 97 trail
            closes=[100, 101, 100],
        )
        sim = _simulate_shadow_trailing_stop(
            proposal, bars, cash=1000, fee_rate=0, slippage_bps=0,
        )
        assert sim.status == "CLOSED"
        assert sim.reason == "TRAILING_STOP"
        # exit price = min(open, trail) * (1 - slip) = min(100, 97) = 97
        assert sim.exit_price == 97.0
        # entry at 100; trail raised to 97 from bar 2's high of 102; bar 3 low 96 < 97
        # proves look-ahead avoidance: bar 3's high (100) would not raise trail further
        # (100 - 5 = 95 < 97 = prev trail) so it stays at 97.

    def test_holding_deadline_closes_when_time_runs_out(self) -> None:
        """If the bar is past holding_deadline, exit at open less slippage."""
        at = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        # Holding deadline is one minute after the entry bar at 10:01.
        proposal = ShadowProposal(
            "trailing-hold", "trend_pullback_v1", "NSE:HOLD",
            entry=100.0, stop=95.0, target=110.0,
            valid_until=at + timedelta(hours=4),
            score=1.0, required_capital=100.0, reason="hold-test",
            signal_at=at, data_cutoff=at,
            entry_deadline=at + timedelta(minutes=4),
            holding_deadline=at + timedelta(minutes=2),
        )
        bars = _bars(
            at,
            opens=[100, 100, 100, 100],
            highs=[100.5, 100.5, 100.5, 100.5],
            lows=[99.5, 99.5, 99.5, 99.5],
            closes=[100, 100, 100, 100],
        )
        sim = _simulate_shadow_trailing_stop(
            proposal, bars, cash=1000, fee_rate=0, slippage_bps=0,
        )
        # Bar at 10:02 is past holding_deadline 10:01; close at open = 100
        assert sim.status == "CLOSED"
        assert sim.reason == "HOLDING_DEADLINE"
        assert sim.exit_price == 100.0

    def test_initial_stop_only_when_no_favorable_extension(self) -> None:
        """If price immediately retraces without ever raising the trail,
        exit at the *initial* stop level (min(open, initial_stop) * 1-slip).

        Entry at 100, initial_stop = 95, no highs above entry; bar 2 low = 94 < 95.
        """
        proposal = _make_proposal()
        at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        bars = _bars(
            at,
            opens=[100, 100],
            highs=[100, 100.1],   # never raises the trail above 95
            lows=[99, 94],
            closes=[100, 99],
        )
        sim = _simulate_shadow_trailing_stop(
            proposal, bars, cash=1000, fee_rate=0, slippage_bps=0,
        )
        assert sim.status == "CLOSED"
        assert sim.reason == "TRAILING_STOP"
        # min(open=100, trail=95) = 95
        assert sim.exit_price == 95.0


# ---- 4: look-ahead safety ---------------------------------------------

class TestLookAheadSafety:
    def test_entry_bar_high_does_not_raise_trailing_above_initial_stop(self) -> None:
        """The bar that *opens* the position (entry bar) must NOT raise the
        trailing level above the initial stop on its own.

        Construct an unambiguous look-ahead scenario: a single bar opens
        the trade AND would otherwise exit it by the initial stop, AND
        carries an artificially large high. If the trailing level were
        raised using this bar's high *before* the exit-check fired, the
        exit would be at ``min(open, high - entry_risk)`` which is above
        the initial stop — a fabricated favourable intrabar sequence.

        Initial stop = 95. Entry at 100 (open). Bar low 94 (would trigger
        an exit at 95). High 110 (would raise trail to 105 if used). With
        the look-ahead fix, the trail stays at 95 and exit price is 95.

        To produce this scenario we need no prior bar: ``data_cutoff=at``
        means entry fires on the very first bar.
        """
        at = datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc)
        proposal = ShadowProposal(
            opportunity_id="lookahead-fixture",
            policy_id="trend_pullback_v1",
            instrument="NSE:LOOKAHEAD",
            entry=100.0, stop=95.0, target=110.0,
            valid_until=at + timedelta(minutes=15),
            score=1.0, required_capital=100.0,
            reason="lookahead-test",
            signal_at=at, data_cutoff=at,           # cut off exactly at bar 0
            entry_deadline=at + timedelta(minutes=1),
            holding_deadline=at + timedelta(hours=1),
        )
        # Single bar: opens the position, dips below the initial stop, with
        # an artificially high high that would raise the trailing level
        # above the initial stop if used in the same bar as the exit.
        bars = _bars(
            at,
            opens=[100],
            highs=[110],   # would raise trail to 110 - 5 = 105 if used
            lows=[94],     # breaches initial stop 95 -> exit at 95
            closes=[99],
        )
        sim = _simulate_shadow_trailing_stop(
            proposal, bars, cash=1000, fee_rate=0, slippage_bps=0,
        )
        assert sim.status == "CLOSED"
        assert sim.reason == "TRAILING_STOP"
        assert sim.exit_price == 95.0, (
            f"trail advanced to {sim.exit_price}; expected 95.0 "
            f"(look-ahead bug: entry bar's high raised trailing above initial stop)"
        )


# ---- 5: persist_exit_policy_comparison now emits three rows ------------

@pytest.mark.asyncio
async def test_persist_exit_policy_comparison_emits_three_rows(db_path) -> None:
    from proactive_exit_research import persist_exit_policy_comparison
    at = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    proposal = _make_proposal()
    future_bars = {
        proposal.instrument: _bars(at, [100] * 5, [100.5] * 5, [99.5] * 5, [100] * 5),
    }
    rows = await persist_exit_policy_comparison(
        db_path,
        research_run_id="trailing-stop-fixture-v1",
        proposals=[proposal],
        future_bars=future_bars,
        cash=1000, fee_rate=0, slippage_bps=0,
    )
    exit_ids = sorted(row["exit_profile_id"] for row in rows)
    assert exit_ids == sorted(["STOP_TARGET_TIME_V1", "PARTIAL_TARGET_TRAIL_V1", "TRAILING_STOP_V1"])
    trailing_row = next(row for row in rows if row["exit_profile_id"] == "TRAILING_STOP_V1")
    assert trailing_row["cost_model_version"] == "EQUITY_CASH_ESTIMATE_V1"
    assert trailing_row["trials"] == 1


@pytest.mark.parametrize("entry_profile, entry_minute", [
    ("NEXT_EXECUTABLE_OPEN_V1", 1), ("COMPLETED_BAR_CONFIRMATION_V1", 2),
])
def test_dispatch_selected_trailing_exit_preserves_entry_clock(entry_profile, entry_minute):
    proposal = _make_proposal()
    at = proposal.data_cutoff
    bars = _bars(at, [100, 100, 100], [102, 102, 100], [99, 99, 96], [100, 100, 99])
    result = simulate_shadow_research_trial(proposal, bars, cash=1000,
        entry_profile_id=entry_profile, exit_profile_id="TRAILING_STOP_V1", fee_rate=0, slippage_bps=0)
    assert (result.status, result.reason, result.exit_price) == ("CLOSED", "TRAILING_STOP", 97)
    assert result.entry_at == at + timedelta(minutes=entry_minute)
    assert result.last_bar_at == at + timedelta(minutes=3)


def test_limit_trailing_waits_for_touch_and_preserves_bound():
    proposal = _make_proposal()
    at = proposal.data_cutoff
    bars = _bars(at, [103, 102, 101, 100], [104, 103, 104, 101],
                 [101, 99, 99, 98], [103, 101, 102, 100])
    result = simulate_shadow_research_trial(proposal, bars, cash=1000,
        entry_profile_id="BOUNDED_PULLBACK_LIMIT_V1", exit_profile_id="TRAILING_STOP_V1",
        fee_rate=0, slippage_bps=0)
    assert result.entry_at == at + timedelta(minutes=2)
    assert result.entry_price == 100 and result.quantity == 10
    assert result.exit_price == 99 and result.last_bar_at == at + timedelta(minutes=4)
    assert result.reason == "TRAILING_STOP" and result.net_pnl == -10


def test_limit_trailing_does_not_ratchet_from_unproven_pre_fill_high():
    proposal = _make_proposal()
    bars = _bars(proposal.data_cutoff, [105, 100], [109, 100], [99, 96], [100, 99])
    result = simulate_shadow_research_trial(proposal, bars, cash=1000,
        entry_profile_id="BOUNDED_PULLBACK_LIMIT_V1", exit_profile_id="TRAILING_STOP_V1",
        fee_rate=0, slippage_bps=0)
    assert result.entry_price == 100
    assert result.status == "OPEN" and result.reason == "DATA_END_OPEN_POSITION"


@pytest.mark.parametrize("open_, high, low, close, reason", [
    (103, 104, 101, 103, "PULLBACK_LIMIT_NOT_REACHED"),
    (94, 96, 93, 94, "GAP_INVALIDATES_ENTRY_GEOMETRY"),
])
def test_limit_trailing_missing_touch_and_invalid_gap_are_no_fill(open_, high, low, close, reason):
    proposal = _make_proposal()
    bars = _bars(proposal.data_cutoff, [open_], [high], [low], [close])
    result = simulate_shadow_research_trial(proposal, bars, cash=1000,
        entry_profile_id="BOUNDED_PULLBACK_LIMIT_V1", exit_profile_id="TRAILING_STOP_V1",
        fee_rate=0, slippage_bps=0)
    assert result.status == "NO_FILL" and result.reason == reason
    assert result.quantity == 0 and result.entry_price is None


def test_confirmation_trailing_cannot_fill_the_confirmation_bar():
    proposal = _make_proposal()
    bars = _bars(proposal.data_cutoff, [100], [109], [94], [100])
    result = simulate_shadow_research_trial(proposal, bars, cash=1000,
        entry_profile_id="COMPLETED_BAR_CONFIRMATION_V1", exit_profile_id="TRAILING_STOP_V1",
        fee_rate=0, slippage_bps=0)
    assert result.status == "NO_FILL" and result.reason == "NO_EXECUTABLE_BAR_AFTER_CONFIRMATION"


def test_confirmation_trailing_does_not_use_confirmation_extremes():
    proposal = _make_proposal()
    bars = _bars(proposal.data_cutoff, [100, 100, 100], [109, 102, 100], [94, 99, 96], [100, 100, 99])
    result = simulate_shadow_research_trial(proposal, bars, cash=1000,
        entry_profile_id="COMPLETED_BAR_CONFIRMATION_V1", exit_profile_id="TRAILING_STOP_V1",
        fee_rate=.001, slippage_bps=5)
    assert result.entry_at == proposal.data_cutoff + timedelta(minutes=2)
    assert result.reason == "TRAILING_STOP"
    assert result.fees > 0 and result.net_pnl < result.gross_pnl


@pytest.mark.parametrize("field", ["fee_rate", "slippage_bps"])
@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_nonfinite_trial_cost_assumptions_fail_closed(field, value):
    with pytest.raises(ValueError, match="invalid research simulation assumptions"):
        simulate_shadow_research_trial(_make_proposal(), [], cash=1000,
            entry_profile_id="NEXT_EXECUTABLE_OPEN_V1", exit_profile_id="TRAILING_STOP_V1", **{field: value})
