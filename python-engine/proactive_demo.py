"""Deterministic, isolated SHADOW workflow demonstration for Dev review.

It intentionally exercises the same workflow and reports consumed by the
application.  The symbols, account and prices are synthetic; this module has
no broker, transport, scheduler or production configuration dependency.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from proactive_intelligence import (
    build_shadow_proposals,
    proactive_activity_report,
    proactive_shadow_comparison,
    proactive_shadow_research_report,
    run_shadow_research_comparison,
    run_shadow_workflow,
)


def _trend_bars(end: datetime) -> list[dict]:
    bars = []
    for index in range(21):
        close = 100 + index * .15
        bars.append({"timestamp": (end - timedelta(minutes=(20 - index) * 15)).isoformat(),
                     "open": close - .2, "high": close + .3, "low": close - .4,
                     "close": close, "volume": 100})
    bars[-3].update({"open": 102.1, "high": 102.4, "low": 101.8, "close": 102})
    bars[-2].update({"open": 102, "high": 102.4, "low": 101.8, "close": 102.1})
    bars[-1].update({"open": 103.8, "high": 104.2, "low": 103.4, "close": 104, "volume": 300})
    return bars


def _range_bars(end: datetime) -> list[dict]:
    bars = []
    for index in range(21):
        close = 100 + (index % 3 - 1) * .2
        bars.append({"timestamp": (end - timedelta(minutes=(20 - index) * 15)).isoformat(),
                     "open": close - .1, "high": close + .3, "low": close - .3,
                     "close": close, "volume": 100})
    bars[-2].update({"open": 98.2, "high": 98.4, "low": 97.8, "close": 98})
    bars[-1].update({"open": 98.6, "high": 99.2, "low": 98.4, "close": 99})
    return bars


async def run_proactive_shadow_demo(db_path: str) -> dict:
    """Create one deterministic evidence-only scenario in a new SQLite file."""
    target = Path(db_path)
    if target.exists():
        raise FileExistsError("demo database already exists; choose a new path")
    target.parent.mkdir(parents=True, exist_ok=True)
    base = datetime(2026, 9, 1, 9, 30, tzinfo=timezone.utc)
    account_id, run_id, capital = "demo-synthetic-account", "demo-multisession-v1", 150.0

    # Session 1: an eligible range setup is selected but no executable bar is
    # available.  The later empty-universe session proves persistent expiry.
    expiry_history = _range_bars(base)
    pending = await run_shadow_workflow(
        db_path, account_id=account_id, run_id=run_id, scenario_capital=capital,
        universe={"SYNTH:EXPIRY": expiry_history}, future_bars={}, now=base + timedelta(minutes=1),
    )
    expiry_sweep = await run_shadow_workflow(
        db_path, account_id=account_id, run_id=run_id, scenario_capital=capital,
        universe={}, future_bars={}, now=base + timedelta(minutes=31),
    )

    # Session 2: one breakout sleeve has the top rank, its sibling shares an
    # instrument and is clustered, and an independent range candidate is
    # unaffordable after the first reservation.  The selected fill closes on
    # the next completed target bar.
    trade_base = base + timedelta(hours=2)
    trend = _trend_bars(trade_base)
    range_ = _range_bars(trade_base)
    entry_bar = {"timestamp": (trade_base + timedelta(minutes=5)).isoformat(),
                 "open": 104, "high": 105, "low": 103, "close": 104}
    target_bar = {"timestamp": (trade_base + timedelta(minutes=10)).isoformat(),
                  "open": 104, "high": 109, "low": 103, "close": 108.5}
    universe = {"SYNTH:ALPHA": trend, "SYNTH:UNAFFORDABLE": range_}
    future = {"SYNTH:ALPHA": [entry_bar, target_bar], "SYNTH:UNAFFORDABLE": []}
    selected = await run_shadow_workflow(
        db_path, account_id=account_id, run_id=run_id, scenario_capital=capital,
        universe=universe, future_bars=future, now=trade_base + timedelta(minutes=5),
    )
    managed = await run_shadow_workflow(
        db_path, account_id=account_id, run_id=run_id, scenario_capital=capital,
        universe=universe, future_bars=future, now=trade_base + timedelta(minutes=10),
    )

    # A frozen P4 experiment consumes the same deterministic opportunity bars
    # but is separate from the operational shadow position and cannot modify it.
    research_proposals = build_shadow_proposals("SYNTH:ALPHA", trend, now=trade_base + timedelta(minutes=1))
    research = await run_shadow_research_comparison(
        db_path, research_run_id="demo-entry-exit-v1", proposals=research_proposals,
        future_bars={"SYNTH:ALPHA": [entry_bar, target_bar]}, cash_per_trial=capital,
    )
    activity = await proactive_activity_report(db_path, days=30)
    outcomes = await proactive_shadow_comparison(db_path, days=30)
    trials = await proactive_shadow_research_report(db_path, research_run_id="demo-entry-exit-v1")

    if pending["allocations"] < 1 or expiry_sweep["expired_pending"] != 1:
        raise RuntimeError("demo did not prove persistent pending expiry")
    if selected["allocations"] != 1 or managed["managed_positions"] != 1:
        raise RuntimeError("demo allocation or completed-bar position management diverged")
    if selected["free_cash"] < 0 or managed["free_cash"] < 0:
        raise RuntimeError("demo synthetic cash became negative")
    if "MISSED_ENTRY_WINDOW_NO_HISTORICAL_BACKFILL" not in managed["reasons"].values():
        raise RuntimeError("demo did not prove historical entries are rejected after later cash release")
    if len(activity["shadow_positions"]) != 1 or activity["shadow_positions"][0]["closed_positions"] != 1:
        raise RuntimeError("demo admitted more than the single intended synthetic fill")
    if not outcomes["comparisons"] or len(trials["comparisons"]) != 6:
        raise RuntimeError("demo did not persist its outcome and matched-trial evidence")
    return {
        "mode": "SHADOW", "research_only": True, "can_place_orders": False,
        "authorization_effect": "NONE", "account_id": account_id, "run_id": run_id,
        "workflow": {"pending": pending, "expiry_sweep": expiry_sweep, "selected": selected, "managed": managed},
        "research_run": research, "activity": activity, "outcome_comparison": outcomes,
        "matched_trial_comparison": trials,
        "assertions": {"pending_expired": True, "one_affordable_allocation": True,
                       "completed_bar_exit": True, "nonnegative_synthetic_cash": True,
                       "matched_trials_retained": True},
    }
