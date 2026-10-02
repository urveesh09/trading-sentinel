"""S7a: capital-skipped evidence and frozen allocation replay."""
from __future__ import annotations

import asyncio
import itertools
import json
import random
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
import pytz

import momentum_allocation_research as alloc
from momentum_exit_study import DEADLINE_FIRST_WITHIN_GAP, ExitStudyError, Quote, StudyEntry

IST = pytz.timezone("Asia/Kolkata")
SOURCE = "sha256:" + "d" * 64
POOL = 50_000.0


def test_allocation_manifest_rejects_fee_override_drift(monkeypatch):
    manifest = alloc.freeze_allocation_manifest(experiment_id="fee-drift")
    monkeypatch.setattr(alloc.settings, "ZERODHA_BROKERAGE_MAX", alloc.settings.ZERODHA_BROKERAGE_MAX + 1)
    with pytest.raises(ExitStudyError, match="cost_schedule"):
        alloc.verify_allocation_manifest(manifest)


def _quotes(start, price_at, end=None):
    end = end or IST.localize(datetime(2026, 9, 25, 15, 15))
    rows, current = [], start
    while current <= end:
        rows.append(Quote(observed_at=current, ltp=round(price_at((current - start).total_seconds() / 60), 4)))
        current += timedelta(minutes=1)
    return tuple(rows)


def _candidate(key, ticker, price, stop, target, *, batch_at, index, risk_pct=0.01, path=None, kind="OPENED"):
    entry = StudyEntry(entry_id=key, admission_key=key, source_ref=SOURCE, ticker=ticker, entry_at=batch_at,
                       entry_price=price, stop_loss_initial=stop, target_1=target, shares=1,
                       atr_14_at_entry=None, vwap_at_entry=None, regime_at_entry="REGIME_1_NORMAL")
    flat = path or (lambda _m: price)
    return alloc.Candidate(admission_key=key, kind=kind, batch_at=batch_at, arrival_index=index, entry=entry,
                           risk_pct=risk_pct, quotes=_quotes(batch_at + timedelta(minutes=1), flat))


BATCH = IST.localize(datetime(2026, 10, 1, 10, 0))


def _brigade_batch(batch_at=BATCH):
    # First arrival is expensive and tight-stopped, so the fixed-pool rule lets
    # it take almost the whole pool (the October 1 BRIGADE pattern).
    batch_at = batch_at.replace(year=2026, month=9, day=25)
    return [
        _candidate("a-brigade", "BRIGADE", 573.10, 567.0, 590.0, batch_at=batch_at, index=0),
        _candidate("b-idfc", "IDFCFIRSTB", 70.0, 68.0, 75.0, batch_at=batch_at, index=1),
        _candidate("c-bandhan", "BANDHANBNK", 180.0, 175.0, 190.0, batch_at=batch_at, index=2, kind="CAPITAL_SKIPPED"),
    ]


def _run(candidates, policy):
    return alloc.replay_allocation(candidates, policy=policy, pool=POOL, max_gap_seconds=60)


def _shares(report):
    return {row["ticker"]: (row["state"], row["shares"]) for row in report["outcomes"]}


def test_first_arrival_concentrates_and_equal_policies_spread_capital():
    first = _shares(_run(_brigade_batch(), alloc.FIRST_ARRIVAL))
    equal = _shares(_run(_brigade_batch(), alloc.FIXED_EQUAL))
    assert first["BRIGADE"][0] == "SELECTED" and first["BRIGADE"][1] * 573.10 > 0.9 * POOL
    assert first["BANDHANBNK"][0] == "CAPITAL_UNAVAILABLE"
    assert all(state == "SELECTED" for state, _ in equal.values())


def test_first_arrival_matches_the_live_paper_admission_sizes(tmp_path):
    from momentum_paper import _paper_risk_pct, open_momentum_paper_positions
    from tests.test_momentum_paper import _db
    db = _db(tmp_path)
    signals = [{"ticker": "BRIGADE", "close": 573.10, "stop_loss": 567.0, "target_1": 590.0, "target_2": 590.0,
                "regime": "REGIME_1_NORMAL", "vwap": 570.0},
               {"ticker": "IDFCFIRSTB", "close": 70.0, "stop_loss": 68.0, "target_1": 75.0, "target_2": 75.0,
                "regime": "REGIME_1_NORMAL", "vwap": 69.5},
               {"ticker": "BANDHANBNK", "close": 180.0, "stop_loss": 175.0, "target_1": 190.0, "target_2": 190.0,
                "regime": "REGIME_1_NORMAL", "vwap": 179.0}]
    asyncio.run(open_momentum_paper_positions(db, signals, BATCH.astimezone(timezone.utc)))
    with sqlite3.connect(db) as con:
        live = {ticker: shares for ticker, shares in con.execute(
            "SELECT ticker, shares FROM positions WHERE source='MOMENTUM_PAPER'")}
    risk = _paper_risk_pct(signals[0])
    batch = [_candidate(f"{i}", s["ticker"], s["close"], s["stop_loss"], s["target_1"], batch_at=BATCH.replace(month=9, day=25),
                        index=i, risk_pct=risk) for i, s in enumerate(signals)]
    replay = {row["ticker"]: row["shares"] for row in _run(batch, alloc.FIRST_ARRIVAL)["outcomes"]
              if row["state"] == "SELECTED"}
    assert replay == live


@pytest.mark.parametrize("policy", [alloc.FIXED_EQUAL, alloc.RISK_BUDGET])
def test_order_invariant_policies_ignore_arrival_order(policy):
    base = _brigade_batch()
    expected = _shares(_run(base, policy))
    for order in itertools.permutations(range(3)):
        shuffled = [alloc.Candidate(**{**vars(c), "arrival_index": order[i]}) for i, c in enumerate(base)]
        assert _shares(_run(shuffled, policy)) == expected


@pytest.mark.parametrize("policy", alloc.POLICIES)
def test_random_books_never_overspend_or_duplicate(policy):
    rng = random.Random(policy)
    tickers = ["T%d" % i for i in range(6)]
    for _trial in range(30):
        candidates = []
        for batch_number in range(4):
            batch_at = IST.localize(datetime(2026, 9, 25, 10, 0)) + timedelta(minutes=37 * batch_number)
            for index in range(rng.randint(1, 4)):
                price = rng.uniform(20, 900)
                stop = price * rng.uniform(0.95, 0.995)
                target = price * rng.uniform(1.005, 1.04)
                drift = rng.uniform(-0.0004, 0.0004) * price
                candidates.append(_candidate(f"{batch_number}-{index}", rng.choice(tickers), price, stop, target,
                                             batch_at=batch_at, index=index, risk_pct=rng.choice([0.005, 0.01, 0.02]),
                                             path=lambda m, p=price, d=drift: max(1.0, p + d * m)))
        report = _run(candidates, policy)  # raises if the book overspends
        assert report["peak_deployed_inr"] <= POOL + 1e-6
        selected_tickers_by_batch = {}
        for row in report["outcomes"]:
            if row["state"] == "SELECTED":
                batch = row["admission_key"].split("-")[0]
                assert (batch, row["ticker"]) not in selected_tickers_by_batch
                selected_tickers_by_batch[(batch, row["ticker"])] = True


def test_capital_is_released_at_exit_for_a_later_batch():
    first_at = IST.localize(datetime(2026, 9, 25, 10, 0))
    big = _candidate("1-big", "BIG", 100.0, 99.0, 101.0, batch_at=first_at, index=0, risk_pct=0.05,
                     path=lambda m: 100.0 if m < 30 else 101.5)  # target hit at minute 30
    for minutes, expected in ((15, "CAPITAL_UNAVAILABLE"), (90, "SELECTED")):
        later = _candidate("2-late", "LATE", 100.0, 99.0, 103.0, batch_at=first_at + timedelta(minutes=minutes),
                           index=0, risk_pct=0.05)
        states = _shares(_run([big, later], alloc.FIRST_ARRIVAL))
        assert states["BIG"][0] == "SELECTED" and states["LATE"][0] == expected


def test_duplicate_ticker_and_incomplete_path_are_explicit():
    batch = _brigade_batch()
    duplicate = _candidate("d-dup", "BRIGADE", 573.10, 567.0, 590.0, batch_at=batch[0].batch_at, index=3)
    broken = alloc.Candidate(**{**vars(_candidate("e-gap", "GAPCO", 50.0, 49.0, 52.0,
                                                 batch_at=batch[0].batch_at, index=4)), "quotes": ()})
    states = {row["admission_key"]: row["state"] for row in _run(batch + [duplicate, broken], alloc.FIRST_ARRIVAL)["outcomes"]}
    assert states["d-dup"] == "TICKER_ALREADY_HELD" and states["e-gap"] == "PATH_UNAVAILABLE"


def test_manifest_freezes_policies_and_splits_holdout(monkeypatch):
    early = datetime(2026, 9, 1, tzinfo=timezone.utc)
    manifest = alloc.freeze_allocation_manifest(experiment_id="s7a", frozen_at=early)
    report = alloc.build_allocation_report(_brigade_batch(), manifest, deadline_policy="exact_1515")
    assert report["holdout"]["candidates"] == 3 and report["development"]["candidates"] == 0
    assert report["holdout"]["net_delta_vs_first_arrival"][alloc.FIRST_ARRIVAL] == 0.0
    assert report["qualification"] == "NOT_ASSESSED"
    from config import settings
    monkeypatch.setattr(settings, "MOMENTUM_PAPER_BANKROLL", 75_000.0)
    with pytest.raises(ExitStudyError, match="pool_inr"):
        alloc.build_allocation_report(_brigade_batch(), manifest, deadline_policy="exact_1515")


def test_capital_skipped_admission_records_candidate_path_without_trading_effect(tmp_path):
    from momentum_paper import open_momentum_paper_positions, record_momentum_paper_path_observations
    from momentum_paper_path_adapter import build_allocation_candidates, build_momentum_paper_exit_study_packet
    from tests.test_momentum_paper import _db, _envelope
    db = _db(tmp_path)
    entry_at = datetime(2026, 9, 25, 9, 20, tzinfo=timezone.utc)
    signals = [{"ticker": t, "close": c, "stop_loss": s, "target_1": c * 1.03, "target_2": c * 1.03,
                "regime": "REGIME_1_NORMAL", "vwap": c - 0.5}
               for t, c, s in (("BRIGADE", 573.10, 567.0), ("BANDHANBNK", 180.0, 175.0))]
    opened = asyncio.run(open_momentum_paper_positions(db, signals, entry_at))
    assert opened == ["BRIGADE"]
    with sqlite3.connect(db) as con:
        outcome, economics = con.execute(
            "SELECT outcome, entry_economics_json FROM momentum_paper_admission_outcomes WHERE ticker='BANDHANBNK'").fetchone()
        kinds = dict(con.execute("SELECT ticker, subscription_kind FROM momentum_paper_path_subscriptions"))
        positions = [row[0] for row in con.execute("SELECT ticker FROM positions")]
    assert outcome == "zero_shares" and positions == ["BRIGADE"]
    assert json.loads(economics)["schema"] == "momentum_paper_candidate_economics_v1"
    assert kinds == {"BRIGADE": "OPENED", "BANDHANBNK": "CAPITAL_SKIPPED"}
    observations, current = [], entry_at + timedelta(seconds=30)
    while current <= datetime(2026, 9, 25, 9, 45, tzinfo=timezone.utc):
        for ticker, price in (("BRIGADE", 573.10), ("BANDHANBNK", 180.0)):
            observations.append({"ticker": ticker, "ltp": price, "provider_observed_at": current.isoformat(),
                                 "receipt_at": current.isoformat(), "source_packet": _envelope(ticker, price, current)})
        current += timedelta(seconds=30 if current.second == 0 else 30)
    asyncio.run(record_momentum_paper_path_observations(db, observations))
    # The exit study still uses opened lifecycles only.
    study_packet = build_momentum_paper_exit_study_packet(db)
    assert [entry["ticker"] for entry in study_packet["packet"]["entries"]] == ["BRIGADE"]
    built = build_allocation_candidates(db)
    assert sorted((c.entry.ticker, c.kind) for c in built["candidates"]) == [
        ("BANDHANBNK", "CAPITAL_SKIPPED"), ("BRIGADE", "OPENED")]
    manifest = alloc.freeze_allocation_manifest(experiment_id="db", frozen_at=entry_at - timedelta(days=1))
    report = alloc.build_allocation_report(built["candidates"], manifest,
                                           deadline_policy=DEADLINE_FIRST_WITHIN_GAP)
    states = {row["ticker"]: row["state"]
              for row in report["holdout"]["policies"][alloc.FIRST_ARRIVAL]["outcomes"]}
    assert states == {"BRIGADE": "SELECTED", "BANDHANBNK": "CAPITAL_UNAVAILABLE"}
    equal = {row["ticker"]: row["state"] for row in report["holdout"]["policies"][alloc.FIXED_EQUAL]["outcomes"]}
    assert equal == {"BRIGADE": "SELECTED", "BANDHANBNK": "SELECTED"}


# [S7 R5 2026-10-02] Causality, capital bases and recorded batch identity.
@pytest.mark.parametrize("basis", [alloc.FIXED_POOL, alloc.REALIZED_EQUITY])
@pytest.mark.parametrize("policy", alloc.POLICIES)
def test_future_path_cannot_change_admission_time_selection(policy, basis):
    base = _brigade_batch()
    crashed = [alloc.Candidate(**{**vars(c), "quotes": c.quotes[:5] + tuple(
        Quote(observed_at=q.observed_at, ltp=q.ltp * 0.9) for q in c.quotes[5:])}) if c.entry.ticker == "IDFCFIRSTB"
               else c for c in base]
    first = _run_basis(base, policy, basis)
    second = _run_basis(crashed, policy, basis)
    sizing = lambda report: {row["ticker"]: (row["state"], row["shares"]) for row in report["outcomes"]}
    assert sizing(first) == sizing(second)


def _run_basis(candidates, policy, basis, pool=POOL):
    return alloc.replay_allocation(candidates, policy=policy, pool=pool, max_gap_seconds=60, basis=basis)


def test_realized_equity_grows_with_wins_and_reserves_fees():
    start = IST.localize(datetime(2026, 9, 25, 10, 0))
    winner = _candidate("1-win", "WIN", 100.0, 99.0, 102.0, batch_at=start, index=0, risk_pct=0.05,
                        path=lambda m: 100.0 if m < 20 else 102.5)
    later = _candidate("2-late", "LATE", 50.0, 49.5, 52.0, batch_at=start + timedelta(minutes=60), index=0,
                       risk_pct=0.2)
    fixed = _shares(_run_basis([winner, later], alloc.FIRST_ARRIVAL, alloc.FIXED_POOL))
    equity = _shares(_run_basis([winner, later], alloc.FIRST_ARRIVAL, alloc.REALIZED_EQUITY))
    assert equity["LATE"][1] > fixed["LATE"][1]          # realised gains add capacity
    # A batch that exactly fills the pool cannot also pay reserved entry fees.
    full = [_candidate("x", "FULL", 100.0, 99.0, 103.0, batch_at=start, index=0, risk_pct=1.0)]
    assert _shares(_run_basis(full, alloc.FIRST_ARRIVAL, alloc.REALIZED_EQUITY))["FULL"][1] < \
        _shares(_run_basis(full, alloc.FIRST_ARRIVAL, alloc.FIXED_POOL))["FULL"][1]


def test_recorded_batch_identity_separates_same_clock_admissions():
    at = IST.localize(datetime(2026, 9, 25, 10, 0))
    a = alloc.Candidate(**{**vars(_candidate("a", "AAA", 100.0, 99.0, 103.0, batch_at=at, index=0, risk_pct=1.0)),
                           "batch_id": "batch-1"})
    b = alloc.Candidate(**{**vars(_candidate("b", "BBB", 100.0, 99.0, 103.0, batch_at=at, index=0, risk_pct=1.0)),
                           "batch_id": "batch-2"})
    states = _shares(_run(_brigade_batch()[:0] + [a, b], alloc.FIXED_EQUAL))
    # Separate recorded batches do not split one equal slice between them.
    assert states["AAA"][1] * 100.0 > 0.9 * POOL and states["BBB"][0] == "CAPITAL_UNAVAILABLE"


def test_real_budget_capacity_is_unavailable_until_configured_and_concentration_reported(monkeypatch):
    from config import settings
    early = datetime(2026, 9, 1, tzinfo=timezone.utc)
    report = alloc.build_allocation_report(_brigade_batch(), alloc.freeze_allocation_manifest(
        experiment_id="r5", frozen_at=early), deadline_policy="exact_1515")
    bases = report["holdout"]["bases"]
    assert bases[alloc.REAL_BUDGET] == {"state": "UNAVAILABLE_NO_OPERATOR_CONFIRMED_BUDGET"}
    first = bases[alloc.FIXED_POOL]["policies"][alloc.FIRST_ARRIVAL]
    assert first["max_concurrent_positions"] == 2 and first["max_single_position_share_of_deployed"] > 0.9
    monkeypatch.setattr(settings, "MOMENTUM_REAL_BUDGET_INR", 8000.0)
    report = alloc.build_allocation_report(_brigade_batch(), alloc.freeze_allocation_manifest(
        experiment_id="r5b", frozen_at=early), deadline_policy="exact_1515")
    capacity = report["holdout"]["bases"][alloc.REAL_BUDGET]["policies"][alloc.FIRST_ARRIVAL]
    assert capacity["pool_inr"] == 8000.0 and capacity["peak_deployed_inr"] <= 8000.0
