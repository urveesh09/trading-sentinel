from __future__ import annotations

import ast
import asyncio
import copy
from dataclasses import replace
from datetime import date, datetime
import inspect
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import aiosqlite
import pandas as pd
import pytest
import pytz
from fastapi.testclient import TestClient

import fno_orchestrator
import fno_shadow
from config import settings
from fno_engine_mom import evaluate_fno_mom
from fno_models import Contract, ContractQuote, FnoDirection


IST = pytz.timezone("Asia/Kolkata")
DAY = date(2026, 7, 10)


def _bars(include_confirmation: bool = False) -> pd.DataFrame:
    frames = []
    for day in ("2026-07-03", "2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09"):
        index = pd.date_range(f"{day} 09:15", periods=74, freq="5min")
        frames.append(pd.DataFrame({
            "open": 25000.0, "high": 25010.0, "low": 24990.0,
            "close": 25000.0, "volume": 100.0,
        }, index=index))
    rows = [
        ("09:15", 25000), ("09:20", 25000), ("09:25", 25000),
        ("09:30", 25000), ("09:35", 25000), ("09:40", 25000),
        ("09:45", 25002), ("09:50", 25003), ("09:55", 25017),
    ]
    if include_confirmation:
        rows.append(("10:00", 25018))
    index = pd.to_datetime([f"2026-07-10 {time}" for time, _ in rows])
    closes = [close for _, close in rows]
    frames.append(pd.DataFrame({
        "open": closes, "high": [value + 10 for value in closes],
        "low": [value - 10 for value in closes], "close": closes,
        "volume": [300.0 if i >= 8 else 100.0 for i in range(len(rows))],
    }, index=index))
    return pd.concat(frames)


def test_baseline_is_exact_production_evaluator_parity():
    bars = _bars()
    now = IST.localize(datetime(2026, 7, 10, 10, 1))
    production = evaluate_fno_mom(bars, "REGIME_1_BULL", now)
    row = fno_shadow.evaluate_fno_shadows(
        bars, "REGIME_1_BULL", now, variants=["FNO_BASE"],
    )[0]
    assert row["accepted"] is (production.direction is not None)
    assert row["direction"] == (production.direction.value if production.direction else None)
    assert row["reject_reason"] == (None if production.direction else production.reject_reason)
    assert row["bar_ts"] == production.bar_ts
    assert row["features"]["stop_underlying"] == production.stop_underlying
    assert row["features"]["target_underlying"] == production.target_underlying


def test_without_the_ema_filter_a_break_against_the_multi_day_trend_is_taken():
    """[O27] After falling sessions the EMA(21) is under the EMA(50), so the shipped evaluator rejects the 09:55
    long break; a variant with ema_filter=False takes it with every other check, the stop and the target as the
    base's. The recorded live shadows all keep the EMA check."""
    bars = _bars()
    prior = bars.index.date < DAY
    count = int(prior.sum())
    fall = pd.Series([2.0 * (count - i) for i in range(count)], index=bars.index[prior])
    for column in ("open", "high", "low", "close"):
        bars.loc[prior, column] = bars.loc[prior, column] + fall
    now = IST.localize(datetime(2026, 7, 10, 10, 1))
    assert evaluate_fno_mom(bars, "REGIME_1_BULL", now).reject_reason == "ema_trend_disagreement"
    with_ema = replace(fno_shadow.VARIANTS["FNO_BASE"], name="OR30_EMA")       # the variant code path
    assert fno_shadow._variant_signal(bars, "REGIME_1_BULL", now, with_ema).reject_reason == "ema_trend_disagreement"
    taken = fno_shadow._variant_signal(bars, "REGIME_1_BULL", now, replace(with_ema, ema_filter=False))
    assert taken.direction is FnoDirection.LONG
    risk = taken.close - taken.stop_underlying
    assert risk > 0 and taken.target_underlying == pytest.approx(taken.close + settings.FNO_TARGET_R * risk)
    # Every recorded opening-range shadow keeps it; [O27h] the trend-day pullback has no EMA check at all.
    assert all(variant.ema_filter for variant in fno_shadow.VARIANTS.values()
               if variant.freshness != "trend_pullback")


def test_the_research_genes_each_change_one_check_and_default_to_the_base():
    """[O27b] The 09:55 long break of ``_bars``: flat prior sessions (range 20, opening range 20), today's open
    25,000, a 09:15-09:40 range closing at its open, a close of 25,017 just over the 25,015 level."""
    bars = _bars()
    now = IST.localize(datetime(2026, 7, 10, 10, 1))
    base = replace(fno_shadow.VARIANTS["FNO_BASE"], name="GENE_BASE")

    def signal(**genes):
        return fno_shadow._variant_signal(bars, "REGIME_1_BULL", now, replace(base, **genes))

    plain = signal()
    assert plain.direction is FnoDirection.LONG
    assert signal(ema_spans=(9, 21), vwap_side=True, gap_align=True, narrow_prior_days=4, max_or_width_ratio=1.25,
                  min_rvol=1.0, latest_entry_min=14 * 60 + 45).direction is FnoDirection.LONG
    assert signal(latest_entry_min=10 * 60).reject_reason == "after_latest_entry"
    assert signal(or_bias="with").reject_reason == "opening_range_bias_not_with"      # the range closed at its open
    assert signal(or_bias="against").direction is FnoDirection.LONG
    assert signal(max_or_width_ratio=0.8).reject_reason == "opening_range_too_wide"
    assert signal(min_rvol=50.0).reject_reason == "rvol_below_min"
    assert signal(stretch_buffer=True).reject_reason == "no_or_break"       # stretch 10 points: level 25,020
    wide = signal(stop_atr_mult=0.5, target_r=1.0)
    assert wide.stop_underlying == pytest.approx(max(wide.or_low, wide.close - 0.5 * wide.atr))
    assert wide.target_underlying == pytest.approx(wide.close + (wide.close - wide.stop_underlying))
    # Every gene at its default is the base evaluator exactly.
    assert (plain.stop_underlying, plain.target_underlying, plain.rvol) == pytest.approx(
        (evaluate_fno_mom(bars, "REGIME_1_BULL", now).stop_underlying,
         evaluate_fno_mom(bars, "REGIME_1_BULL", now).target_underlying,
         evaluate_fno_mom(bars, "REGIME_1_BULL", now).rvol))
    history = fno_shadow._prior_sessions(bars, DAY, 30)
    assert len(history) == 5 and history[-1]["or_width"] == 20.0 and history[-1]["high"] - history[-1]["low"] == 20.0


def test_confirmation_variant_accepts_only_first_bounded_bar_after_cross():
    bars = _bars(include_confirmation=True)
    now = IST.localize(datetime(2026, 7, 10, 10, 6))
    rows = {row["variant"]: row for row in fno_shadow.evaluate_fno_shadows(
        bars, "REGIME_1_BULL", now, variants=["FNO_BASE", "FNO_CONFIRM_1"],
    )}
    assert rows["FNO_BASE"]["accepted"] is False
    assert rows["FNO_BASE"]["reject_reason"] == "not_fresh_break"
    assert rows["FNO_CONFIRM_1"]["accepted"] is True
    assert rows["FNO_CONFIRM_1"]["direction"] == "LONG"


def test_cost_scenario_uses_resolved_quote_and_production_cost_model(monkeypatch):
    bars = _bars()
    now = IST.localize(datetime(2026, 7, 10, 10, 1))
    rows = fno_shadow.evaluate_fno_shadows(
        bars, "REGIME_1_BULL", now, variants=["FNO_BASE"],
    )
    contract = Contract(1, "NIFTYCE", "NIFTY", date(2026, 7, 14), 25000, "CE", 75)
    quote = ContractQuote(contract, bid=99.0, ask=101.0, ltp=100.0)
    monkeypatch.setattr(fno_shadow, "select_strike_by_delta", lambda *_: (quote, 0.15, 0.55))
    snapshot = SimpleNamespace(lot_size=75)
    fno_shadow.attach_resolved_cost_estimates(rows, snapshot, now)
    outcome = rows[0]["post_cost_outcome"]
    assert outcome["available"] is True
    assert outcome["estimated_costs"] > 0
    assert outcome["estimated_net_pnl"] < outcome["gross_pnl"]
    assert "target_scenario" in outcome["kind"]
    assert outcome["execution_snapshot"]["schedule_version"] == "ZERODHA_NSE_OPTIONS_2026-04-01"
    assert outcome["execution_snapshot"]["effective_date"] == "2026-04-01"


@pytest.mark.asyncio
async def test_persistence_is_idempotent_and_comparison_separates_counts(db_path):
    rows = fno_shadow.evaluate_fno_shadows(
        _bars(), "REGIME_1_BULL", IST.localize(datetime(2026, 7, 10, 10, 1)),
    )
    assert await fno_shadow.persist_fno_shadow_results(db_path, rows) == len(fno_shadow.VARIANTS) == 6  # [O27h]
    assert await fno_shadow.persist_fno_shadow_results(db_path, rows) == 0
    comparison = await fno_shadow.fno_shadow_comparison(db_path)
    base = next(row for row in comparison["variants"] if row["variant"] == "FNO_BASE")
    assert base["evaluations"] == 1
    assert base["accepted_evaluations"] == 1
    assert base["distinct_candidates"] == 1
    assert base["estimated_post_cost"]["available_samples"] == 0
    assert base["estimated_post_cost"]["estimated_net_pnl"] is None

    repeated = copy.deepcopy(next(row for row in rows if row["variant"] == "FNO_BASE"))
    repeated["bar_ts"] = "2026-07-10 10:05:00"
    repeated["candidate_key"] = "poisoned|per-bar|identity"
    assert await fno_shadow.persist_fno_shadow_results(db_path, [repeated]) == 1
    base = next(row for row in (await fno_shadow.fno_shadow_comparison(db_path))["variants"]
                if row["variant"] == "FNO_BASE")
    assert base["evaluations"] == 2
    assert base["accepted_evaluations"] == 2
    assert base["distinct_candidates"] == 1


@pytest.mark.asyncio
async def test_shadow_failure_is_isolated_from_orchestrator(monkeypatch, db_path):
    monkeypatch.setattr(fno_shadow, "evaluate_fno_shadows", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("shadow down")))
    assert await fno_orchestrator._record_shadow_observation(
        db_path, _bars(), "REGIME_1_BULL", IST.localize(datetime(2026, 7, 10, 10, 1)),
    ) == 0


@pytest.mark.asyncio
async def test_slow_shadow_is_supervised_and_never_awaited_by_tick_path(monkeypatch, db_path):
    release = threading.Event()

    def slow(*_args, **_kwargs):
        release.wait(timeout=5)
        return 1

    monkeypatch.setattr(fno_shadow, "persist_fno_shadow_results_sync", slow)
    task = fno_orchestrator._schedule_shadow_observation(
        db_path, _bars(), "REGIME_1_BULL", IST.localize(datetime(2026, 7, 10, 10, 1)),
    )
    assert task in fno_orchestrator._SHADOW_TASKS
    assert not task.done()
    # Scheduling returned while persistence is still blocked; the production
    # path does not receive a result that could alter signal/sizing/order flow.
    release.set()
    assert await asyncio.to_thread(task.result, 5) == 1
    assert task not in fno_orchestrator._SHADOW_TASKS

    # Entries for each underlying live in _single_leg_entries; the shadow is
    # scheduled (never awaited) only after both legs' entry attempts.
    source = inspect.getsource(fno_orchestrator._single_leg_entries)
    assert "shadow = _schedule_shadow_observation" in source
    assert source.rfind("_try_entry_for_leg(") < source.rfind("shadow(db_path, bars, regime, now_ist, snap)")


def test_operational_toggle_prevents_scheduling(monkeypatch, db_path):
    monkeypatch.setattr(settings, "FNO_SHADOW_ENABLED", False)
    submit = Mock(wraps=fno_orchestrator._SHADOW_EXECUTOR.submit)
    monkeypatch.setattr(fno_orchestrator._SHADOW_EXECUTOR, "submit", submit)
    assert fno_orchestrator._schedule_shadow_observation(
        db_path, _bars(), "REGIME_1_BULL", IST.localize(datetime(2026, 7, 10, 10, 1)),
    ) is None
    submit.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("trading_date", "not-a-date"),
    ("bar_ts", "2026-07-11 10:00:00"),
    ("underlying", ""),
    ("underlying", "NIFTY;DROP"),
    ("direction", "SIDEWAYS"),
])
async def test_malformed_identity_evidence_is_rejected(db_path, field, value):
    row = fno_shadow.evaluate_fno_shadows(
        _bars(), "REGIME_1_BULL", IST.localize(datetime(2026, 7, 10, 10, 1)),
        variants=["FNO_BASE"],
    )[0]
    row[field] = value
    with pytest.raises(ValueError):
        await fno_shadow.persist_fno_shadow_results(db_path, [row])
    async with aiosqlite.connect(db_path) as db:
        count = (await (await db.execute("SELECT COUNT(*) FROM fno_shadow_evaluations")).fetchone())[0]
    assert count == 0


@pytest.mark.asyncio
async def test_non_finite_close_cannot_poison_comparison(db_path):
    row = fno_shadow.evaluate_fno_shadows(
        _bars(), "REGIME_1_BULL", IST.localize(datetime(2026, 7, 10, 10, 1)),
        variants=["FNO_BASE"],
    )[0]
    row["features"]["close"] = float("nan")
    with pytest.raises(ValueError, match="finite close"):
        await fno_shadow.persist_fno_shadow_results(db_path, [row])


def test_shadow_has_no_order_sizing_or_broker_surface():
    tree = ast.parse(inspect.getsource(fno_shadow))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported.intersection({"fno_executor", "fno_positions", "fno_risk", "kite_client"})
    assert "kite" not in inspect.signature(fno_orchestrator._record_shadow_observation).parameters
    assert not hasattr(fno_shadow, "execute_entry")
    assert not hasattr(fno_shadow, "lots_for_pool")


def test_live_leg_remains_triple_disarmed_by_default():
    assert settings.FNO_DISABLE_LIVE is True
    assert settings.FNO_LIVE_TRADING is False
    assert settings.FNO_LIVE_BANKROLL == 0


def test_authenticated_registry_and_comparison_endpoint(monkeypatch, db_path):
    from main import app

    monkeypatch.setattr(settings, "DB_PATH", db_path)
    client = TestClient(app)
    assert client.get("/experiments/fno-opening-range").status_code == 403
    response = client.get(
        "/experiments/fno-opening-range",
        headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["research_only"] is True and body["can_place_orders"] is False
    assert set(body["registry"]) == set(fno_shadow.VARIANTS)
    assert body["comparison"]["can_place_orders"] is False

    monkeypatch.setattr(settings, "FNO_SHADOW_ENABLED", False)
    disabled = client.get(
        "/experiments/fno-opening-range",
        headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
    ).json()
    assert disabled["enabled"] is False
    assert disabled["config"] == {"enabled": False}
    assert disabled["status"] == "disabled"


def _trend_day(after_break):
    """Five flat sessions, then today's flat 30-minute opening range, a break at 09:55 and ``after_break``:
    (time, close) bars, each 10 points either side of its close."""
    frame = _bars()
    rows = [(stamp, close) for stamp, close in after_break]
    index = pd.to_datetime([f"2026-07-10 {stamp}" for stamp, _ in rows])
    closes = [close for _, close in rows]
    extra = pd.DataFrame({"open": closes, "high": [c + 10 for c in closes], "low": [c - 10 for c in closes],
                          "close": closes, "volume": 300.0}, index=index)
    return pd.concat([frame, extra])


def _continuation(after_break, minute):
    now = IST.localize(datetime(2026, 7, 10, 10, minute))
    return {row["variant"]: row for row in fno_shadow.evaluate_fno_shadows(
        _trend_day(after_break), "REGIME_1_BULL", now, variants=["FNO_BASE", "FNO_CONTINUATION"])}


def test_a_continuation_needs_a_pullback_to_the_break_and_a_resumption():
    """[O24g] Frozen definition: after the break (09:55) an extension (10:00), a pullback to within 0.25 ATR of
    the break level (10:05, low 25,008) and a bar closing above the previous high (10:10): the base calls it not
    fresh; the continuation takes it, with the base's stop and target rules."""
    rows = _continuation([("10:00", 25040), ("10:05", 25018), ("10:10", 25035)], 16)
    assert rows["FNO_BASE"]["reject_reason"] == "not_fresh_break"
    accepted = rows["FNO_CONTINUATION"]
    assert accepted["accepted"] is True and accepted["direction"] == "LONG"
    features = accepted["features"]
    risk = features["close"] - features["stop_underlying"]
    assert risk > 0 and features["target_underlying"] == pytest.approx(features["close"] + settings.FNO_TARGET_R * risk)
    # A straight extension (no pullback since the latest high) and a pullback that does not resume: no entry.
    assert _continuation([("10:00", 25040), ("10:05", 25050), ("10:10", 25065)], 16)["FNO_CONTINUATION"][
        "reject_reason"] == "no_pullback_resumption"
    assert _continuation([("10:00", 25040), ("10:05", 25018), ("10:10", 25020)], 16)["FNO_CONTINUATION"][
        "reject_reason"] == "no_pullback_resumption"
    # On the break bar itself it is the base signal.
    fresh = _continuation([], 1)
    assert fresh["FNO_CONTINUATION"]["accepted"] is fresh["FNO_BASE"]["accepted"] is True


def test_pullback_resumed_reads_closed_bars_both_ways():
    """[O24g] Level 102, ATR 4, tolerance 0.25 ATR (a pullback low at or under 103 counts, for a long)."""
    index = pd.date_range("2026-07-10 09:45", periods=5, freq="5min")

    def frame(closes, highs, lows):
        return pd.DataFrame({"close": closes, "high": highs, "low": lows}, index=index[:len(closes)])

    # break at 09:50, high 112 at 09:55, pullback to 101 at 10:00, 10:05 closes 108 above 10:00's high 106
    long = frame([100, 103, 110, 104, 108], [101, 104, 112, 106, 109], [99, 102, 108, 101, 105])
    assert fno_shadow.pullback_resumed(long, True, 102.0, 4.0, 0.25)
    assert not fno_shadow.pullback_resumed(long.iloc[:-1], True, 102.0, 4.0, 0.25)   # the last bar is the pullback
    shallow = frame([100, 103, 110, 107, 112], [101, 104, 112, 109, 113], [99, 102, 108, 105, 108])
    assert not fno_shadow.pullback_resumed(shallow, True, 102.0, 4.0, 0.25)          # low 105 > 103: no pullback
    stalled = frame([100, 103, 110, 104, 105], [101, 104, 112, 106, 107], [99, 102, 108, 101, 103])
    assert not fno_shadow.pullback_resumed(stalled, True, 102.0, 4.0, 0.25)          # 105 is not above 106
    # the short mirror: low 88, pullback high 99 >= 97, 10:05 closes 92 under 10:00's low 94
    short = frame([100, 97, 90, 96, 92], [101, 98, 92, 99, 95], [99, 96, 88, 94, 91])
    assert fno_shadow.pullback_resumed(short, False, 98.0, 4.0, 0.25)
    assert not fno_shadow.pullback_resumed(short, True, 98.0, 4.0, 0.25)            # not beyond a long level


# ---- [O27h] the trend-day VWAP pullback shadow --------------------------------------------------------------------

def _pullback_day(pull=((25100, 25080), (25080, 25058)), resume=(25059, 25085), mirror=False) -> pd.DataFrame:
    """Five flat sessions, then a steady climb from 24,998 to 25,100 by 11:20, a pullback toward VWAP (about
    25,051) and a resumption bar at 11:35 closing above the previous bar's high. ``mirror`` reflects every price
    about 25,000 (the same day, falling)."""
    frames = [pd.DataFrame({"open": 25000.0, "high": 25010.0, "low": 24990.0, "close": 25000.0, "volume": 100.0},
                           index=pd.date_range(f"{day} 09:15", periods=74, freq="5min"))
              for day in ("2026-07-03", "2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09")]
    rows, previous = [], 24998.0
    for step in range(26):
        rows.append((previous, 25000.0 + 4 * step))
        previous = 25000.0 + 4 * step
    rows += [*pull, resume]
    opens, closes = [float(o) for o, _ in rows], [float(c) for _, c in rows]
    frames.append(pd.DataFrame({"open": opens, "high": [max(o, c) + 1 for o, c in zip(opens, closes)],
                                "low": [min(o, c) - 3 for o, c in zip(opens, closes)], "close": closes,
                                "volume": 100.0}, index=pd.date_range("2026-07-10 09:15", periods=len(rows), freq="5min")))
    frame = pd.concat(frames)
    if mirror:
        frame = pd.DataFrame({"open": 50000 - frame["open"], "high": 50000 - frame["low"],
                              "low": 50000 - frame["high"], "close": 50000 - frame["close"],
                              "volume": frame["volume"]}, index=frame.index)
    return frame


def _pullback(frame, hhmm="11:41", regime="REGIME_1_BULL"):
    now = IST.localize(datetime.fromisoformat(f"2026-07-10 {hhmm}:00"))
    return fno_shadow._variant_signal(frame, regime, now, fno_shadow.VARIANTS["FNO_TREND_PULLBACK"])


def test_trend_pullback_takes_the_resumption_bar_both_ways_with_its_stop_and_3r_target():
    up, down = _pullback(_pullback_day()), _pullback(_pullback_day(mirror=True))
    assert (up.bar_ts, up.direction, down.direction) == ("2026-07-10 11:35:00", FnoDirection.LONG,
                                                         FnoDirection.SHORT)
    assert up.close == 25085.0 and down.close == 24915.0 and up.atr == pytest.approx(down.atr)
    assert up.stop_underlying == pytest.approx(25085.0 - 1.5 * up.atr)
    assert up.target_underlying == pytest.approx(25085.0 + 3.0 * 1.5 * up.atr)
    assert down.stop_underlying == pytest.approx(24915.0 + 1.5 * down.atr)
    assert down.target_underlying == pytest.approx(24915.0 - 4.5 * down.atr)


def test_trend_pullback_needs_the_window_a_real_pullback_a_resumption_and_no_crisis():
    assert _pullback(_pullback_day(), "11:21").reject_reason == "before_trend_window"       # bar closes 11:20
    assert _pullback(_pullback_day(), "11:36").reject_reason == "no_trend_pullback"         # the pullback bar
    shallow = _pullback_day(pull=((25100, 25098), (25098, 25096)), resume=(25096, 25104))
    assert _pullback(shallow).reject_reason == "no_trend_pullback"                         # never near VWAP
    assert _pullback(_pullback_day(), regime="REGIME_3_CRISIS").reject_reason == "regime_crisis"
    future = _pullback_day()
    assert _pullback(future, "11:39").bar_ts == "2026-07-10 11:30:00"                       # 11:35 not closed yet


def test_trend_pullback_is_registered_and_leaves_every_other_variant_unchanged():
    variant = fno_shadow.VARIANTS["FNO_TREND_PULLBACK"]
    assert (variant.freshness, variant.trend_atr, variant.trend_side, variant.pullback_touch_atr,
            variant.entry_from_min, variant.stop_atr_mult, variant.target_r) == ("trend_pullback", 1.5, 0.75, 0.5,
                                                                                  690, 1.5, 3.0)
    for name, other in fno_shadow.VARIANTS.items():
        if name != "FNO_TREND_PULLBACK":
            assert (other.trend_atr, other.trend_side, other.pullback_touch_atr, other.entry_from_min) == (None,) * 4
    from fno_policy_replay import resolve_policy
    arm = resolve_policy("FNO_SIG_TREND_PULLBACK")
    assert arm.signal_variant == "FNO_TREND_PULLBACK" and arm.manage_every_observation
    assert dict(arm.exit_overrides) == {"FNO_PROFIT_LOCK_ENABLED": False, "FNO_TIME_STOP_MIN": 120.0,
                                        "FNO_TRAIL_ATR_MULT": 2.0}

