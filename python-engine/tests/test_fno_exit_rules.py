"""S6b: the extracted single-leg ladder is behaviour-identical to the inline one.

``_inline_oracle`` is a frozen transcription of the pre-extraction block in
``fno_orchestrator`` (commit 19a5471), minus logging and the database write.
Randomised differential cases cover both directions, hard flat, absent/zero
futures quotes, armed/unarmed trails, naive/aware/unparseable entry times,
the premium deferral flag and every precedence collision.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
import pytz

from fno_exit_rules import evaluate_single_leg_exit

IST = pytz.timezone("Asia/Kolkata")
NOW = IST.localize(datetime(2026, 7, 10, 11, 0))


def _inline_oracle(p, *, now_ist, fut_price, exit_px_basis, hard_flat, params):
    exit_reason = ""
    long_view = p.direction == "LONG"
    trail_active = bool(p.trail_active)
    trail_stop = p.trail_stop_underlying
    best = p.best_underlying
    persisted = None
    if hard_flat:
        exit_reason = "hard_flat_1510"
    elif fut_price is not None and fut_price > 0:
        best = p.best_underlying or p.entry_underlying
        best = max(best, fut_price) if long_view else min(best, fut_price)
        target_hit = (fut_price >= p.target_underlying if long_view
                      else fut_price <= p.target_underlying)
        if target_hit and not trail_active:
            trail_active = True
        if trail_active:
            dist = params["FNO_TRAIL_ATR_MULT"] * (p.atr_at_entry or 0.0)
            new_trail = best - dist if long_view else best + dist
            if trail_stop is None:
                trail_stop = new_trail
            else:
                trail_stop = max(trail_stop, new_trail) if long_view else min(trail_stop, new_trail)
        stopped = fut_price <= p.stop_underlying if long_view else fut_price >= p.stop_underlying
        trailed = (trail_active and trail_stop is not None
                   and (fut_price <= trail_stop if long_view else fut_price >= trail_stop))
        premium_stopped = exit_px_basis > 0 and exit_px_basis <= p.premium_stop
        timed_out = False
        if not trail_active:
            try:
                entry_dt = datetime.fromisoformat(p.entry_time)
                if entry_dt.tzinfo is None:
                    entry_dt = IST.localize(entry_dt)
                age_min = (now_ist - entry_dt).total_seconds() / 60.0
            except (ValueError, TypeError):
                age_min = 0.0
            if age_min >= params["FNO_TIME_STOP_MIN"]:
                r_points = abs(p.entry_underlying - p.stop_underlying)
                progress = (fut_price - p.entry_underlying if long_view
                            else p.entry_underlying - fut_price)
                if progress < params["FNO_TIME_STOP_MIN_R"] * r_points:
                    timed_out = True
                if timed_out and params["FNO_TIME_STOP_RESPECTS_PREMIUM"]:
                    premium_pnl_per_lot = (exit_px_basis - p.entry_premium)
                    if exit_px_basis > 0 and premium_pnl_per_lot > 0:
                        timed_out = False
        if stopped:
            exit_reason = "underlying_stop"
        elif trailed:
            exit_reason = "trail_stop"
        elif premium_stopped:
            exit_reason = "premium_backstop"
        elif timed_out:
            exit_reason = "time_stop"
        if not exit_reason:
            persisted = (1 if trail_active else 0, trail_stop, best)
    else:
        if exit_px_basis > 0 and exit_px_basis <= p.premium_stop:
            exit_reason = "premium_backstop"
    return exit_reason, persisted


def _random_case(rng):
    direction = rng.choice(["LONG", "SHORT"])
    sign = 1 if direction == "LONG" else -1
    entry_u = 25000.0
    r_pts = rng.choice([10.0, 25.0, 40.0])
    trail_active = rng.random() < 0.3
    entry_offset = rng.choice([5, 30, 44.9, 45, 60, 120])
    entry_time = rng.choice([
        (NOW - timedelta(minutes=entry_offset)).isoformat(),
        (NOW - timedelta(minutes=entry_offset)).replace(tzinfo=None).isoformat(),
        "not-a-time", None,
    ])
    p = SimpleNamespace(
        direction=direction, entry_underlying=entry_u,
        stop_underlying=entry_u - sign * r_pts, target_underlying=entry_u + sign * 1.8 * r_pts,
        atr_at_entry=rng.choice([None, 0.0, 12.0, 30.0]),
        entry_premium=100.0, premium_stop=rng.choice([60.0, 70.0]),
        entry_time=entry_time, trail_active=1 if trail_active else 0,
        trail_stop_underlying=(entry_u + sign * rng.uniform(-10, 40)) if trail_active and rng.random() < 0.7 else None,
        best_underlying=rng.choice([None, entry_u + sign * rng.uniform(0, 80)]),
    )
    fut = rng.choice([None, 0.0, entry_u + sign * rng.uniform(-2.2 * r_pts, 2.5 * r_pts)])
    basis = rng.choice([0.0, rng.uniform(40, 160)])
    params = {"FNO_TRAIL_ATR_MULT": rng.choice([0.5, 1.0]), "FNO_TIME_STOP_MIN": 45.0,
              "FNO_TIME_STOP_MIN_R": 0.5, "FNO_TIME_STOP_RESPECTS_PREMIUM": rng.random() < 0.6}
    return p, dict(now_ist=NOW, fut_price=fut, exit_px_basis=basis,
                   hard_flat=rng.random() < 0.1, params=params)


def test_extracted_ladder_matches_the_inline_oracle_on_random_cases():
    rng = random.Random(20261002)
    reasons = set()
    for _ in range(20_000):
        p, kwargs = _random_case(rng)
        expected_reason, expected_persist = _inline_oracle(p, **kwargs)
        decision = evaluate_single_leg_exit(p, **kwargs)
        assert decision.exit_reason == expected_reason
        if expected_persist is None:
            assert decision.persist_trail is False
        else:
            assert decision.persist_trail is True
            assert (1 if decision.trail_active else 0, decision.trail_stop,
                    decision.best_underlying) == expected_persist
        reasons.add(decision.exit_reason)
    # The sample must actually exercise every branch of the ladder.
    assert reasons == {"", "hard_flat_1510", "underlying_stop", "trail_stop",
                       "premium_backstop", "time_stop"}


def test_deferral_and_unparseable_entry_time_are_reported_for_logging():
    p = SimpleNamespace(direction="LONG", entry_underlying=25000.0, stop_underlying=24975.0,
                        target_underlying=25045.0, atr_at_entry=10.0, entry_premium=100.0,
                        premium_stop=60.0, entry_time=(NOW - timedelta(minutes=50)).isoformat(),
                        trail_active=0, trail_stop_underlying=None, best_underlying=None)
    params = {"FNO_TRAIL_ATR_MULT": 1.0, "FNO_TIME_STOP_MIN": 45.0,
              "FNO_TIME_STOP_MIN_R": 0.5, "FNO_TIME_STOP_RESPECTS_PREMIUM": True}
    decision = evaluate_single_leg_exit(p, now_ist=NOW, fut_price=25001.0, exit_px_basis=105.0,
                                        hard_flat=False, params=params)
    assert decision.exit_reason == "" and decision.time_stop_deferred is not None
    assert decision.time_stop_deferred["premium_pnl_per_unit"] == pytest.approx(5.0)
    p.entry_time = "garbage"
    decision = evaluate_single_leg_exit(p, now_ist=NOW, fut_price=25001.0, exit_px_basis=95.0,
                                        hard_flat=False, params=params)
    assert decision.entry_time_unparseable is True and decision.exit_reason == ""
