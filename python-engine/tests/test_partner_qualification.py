from datetime import datetime, timedelta

import pandas as pd
import pytest
import pytz

import partner_qualification as qualification
from fno_engine_mom import MomSignal, evaluate_fno_mom
from fno_models import FnoDirection


IST = pytz.timezone("Asia/Kolkata")


def bars():
    # Deliberately incomplete current opening range: this is an exact deployed
    # no-setup, not a made-up research opportunity.
    index = pd.to_datetime(["2026-09-11 09:15:00", "2026-09-11 09:20:00"])
    return pd.DataFrame({"open": [100, 101], "high": [102, 103], "low": [99, 100],
                         "close": [101, 102], "volume": [100, 100]}, index=index)


def provenance(now):
    return {"state": "CONTEMPORANEOUS", "source": "recorded-futures-bars",
            "event_at": now - timedelta(minutes=5), "received_at": now - timedelta(seconds=1),
            "retrieved_at": now}


@pytest.mark.parametrize("underlying", ["NIFTY", "SENSEX"])
def test_full_policy_adapter_reuses_deployed_no_setup_and_is_deterministic(underlying):
    now = IST.localize(datetime(2026, 9, 11, 9, 28))
    expected = evaluate_fno_mom(bars(), "REGIME_1_NORMAL", now)
    one = qualification.evaluate_deployed_full_policy(underlying=underlying, bars=bars(), regime="REGIME_1_NORMAL",
                                                       decision_at=now, bar_provenance=provenance(now))
    two = qualification.evaluate_deployed_full_policy(underlying=underlying, bars=bars(), regime="REGIME_1_NORMAL",
                                                       decision_at=now, bar_provenance=provenance(now))
    assert one.state == "NO_SETUP" and one.reason == expected.reject_reason
    assert one.signal == expected and one.decision_id == two.decision_id
    assert one.manifest["bars_sha256"] == two.manifest["bars_sha256"]
    assert one.can_qualify is False


def test_full_policy_rejects_future_contemporaneous_input():
    now = IST.localize(datetime(2026, 9, 11, 9, 28))
    bad = provenance(now); bad["received_at"] = now + timedelta(seconds=1)
    with pytest.raises(ValueError, match="unavailable at decision time"):
        qualification.evaluate_deployed_full_policy(underlying="SENSEX", bars=bars(), regime="REGIME_1_NORMAL",
                                                     decision_at=now, bar_provenance=bad)


def test_fired_policy_without_chain_is_explicit_rejection(monkeypatch):
    now = IST.localize(datetime(2026, 9, 11, 10, 0))
    fired = MomSignal(bar_ts="2026-09-11 09:55:00", direction=FnoDirection.LONG, close=100,
                      or_high=99, or_low=90, atr=2, rvol=2, stop_underlying=97, target_underlying=105)
    monkeypatch.setattr(qualification, "evaluate_fno_mom", lambda *_args: fired)
    decision = qualification.evaluate_deployed_full_policy(underlying="NIFTY", bars=bars(), regime="REGIME_1_NORMAL",
                                                            decision_at=now, bar_provenance=provenance(now))
    assert decision.state == "REJECTED"
    assert decision.validation_reasons == ("candidate_input_missing",)


def test_utc_clock_and_aware_bars_match_ist_decision():
    now = IST.localize(datetime(2026, 9, 11, 9, 28))
    frame = bars()
    aware = frame.copy()
    aware.index = aware.index.tz_localize(IST).tz_convert("UTC")
    arguments = dict(underlying="NIFTY", regime="REGIME_1_NORMAL", bar_provenance=provenance(now))
    local = qualification.evaluate_deployed_full_policy(bars=frame, decision_at=now, **arguments)
    utc = qualification.evaluate_deployed_full_policy(bars=aware, decision_at=now.astimezone(pytz.UTC), **arguments)
    assert utc.signal == local.signal
    assert utc.decision_id == local.decision_id


@pytest.mark.parametrize("fault", ["duplicate", "unordered", "nan", "inconsistent"])
def test_invalid_bars_cannot_produce_research_decisions(fault):
    now = IST.localize(datetime(2026, 9, 11, 9, 28))
    frame = bars()
    if fault == "duplicate":
        frame.index = pd.DatetimeIndex([frame.index[0], frame.index[0]])
    elif fault == "unordered":
        frame = frame.iloc[::-1]
    elif fault == "nan":
        frame.iloc[0, frame.columns.get_loc("close")] = float("nan")
    else:
        frame.iloc[0, frame.columns.get_loc("high")] = 1
    with pytest.raises(ValueError):
        qualification.evaluate_deployed_full_policy(underlying="NIFTY", bars=frame, regime="REGIME_1_NORMAL",
                                                     decision_at=now, bar_provenance=provenance(now))


def candidate_bundle():
    contracts = [dict(token=token, tradingsymbol=f"NIFTY{token}", name="NIFTY", expiry="2026-09-17",
                      strike=strike, instrument_type="CE", lot_size=75, tick_size=0.05)
                 for token, strike in [(1, 25000), (2, 25050)]]
    return dict(underlying="NIFTY", segment="NFO", received_at="2026-09-11T10:00:00+05:30",
                contracts=contracts, profile={"holding_period": "INTRADAY"},
                snapshot=dict(taken_at="2026-09-11T10:00:00+05:30", expiry="2026-09-17", forward=25000.,
                              lot_size=75, quotes=[dict(token=token, bid=bid, ask=ask, oi=10000, volume=5000,
                                  bid_quantity=500, ask_quantity=500, last_trade_time="2026-09-11T10:00:00+05:30")
                                  for token, bid, ask in [(1, 88., 90.), (2, 45., 47.)]]))


def test_candidate_bundle_reaches_deployed_spread_validation(monkeypatch):
    now = IST.localize(datetime(2026, 9, 11, 10))
    book, snapshot, profile = qualification.load_candidate_evidence(candidate_bundle(), underlying="NIFTY", decision_at=now)
    fired = MomSignal(bar_ts="2026-09-11 09:55:00", direction=FnoDirection.LONG, close=25020,
                      or_high=25010, or_low=24900, atr=20, rvol=2, stop_underlying=24950, target_underlying=25100)
    monkeypatch.setattr(qualification, "evaluate_fno_mom", lambda *_args: fired)
    result = qualification.evaluate_deployed_full_policy(underlying="NIFTY", bars=bars(), regime="REGIME_1_NORMAL",
        decision_at=now, bar_provenance=provenance(now), book=book, snapshot=snapshot, profile=profile)
    assert result.candidate is not None
    assert "candidate_input_missing" not in result.validation_reasons
    assert result.can_qualify is False


@pytest.mark.parametrize("fault", ["future", "scope", "duplicate"])
def test_candidate_bundle_rejects_bad_provenance(fault):
    now = IST.localize(datetime(2026, 9, 11, 10))
    value = candidate_bundle()
    if fault == "future":
        value["received_at"] = "2026-09-11T10:01:00+05:30"
    elif fault == "scope":
        value["segment"] = "BFO"
    else:
        value["contracts"].append(value["contracts"][0])
    with pytest.raises(ValueError):
        qualification.load_candidate_evidence(value, underlying="NIFTY", decision_at=now)


def test_frozen_policy_is_stable_across_observations_but_changes_with_configuration(monkeypatch):
    now = IST.localize(datetime(2026, 9, 11, 10))
    def manifest(at):
        return qualification.policy_manifest(underlying="NIFTY", structure_kind="DIRECTIONAL_DEBIT_SPREAD",
            bars=bars(), regime="REGIME_1_NORMAL", decision_at=at, bar_provenance=provenance(at))
    first = manifest(now)
    later = manifest(now + timedelta(minutes=5))
    assert first["manifest_sha256"] != later["manifest_sha256"]
    assert first["policy_sha256"] == later["policy_sha256"]
    monkeypatch.setattr(qualification.settings, "FNO_OR_BUFFER_ATR", qualification.settings.FNO_OR_BUFFER_ATR + 0.01)
    assert manifest(now)["policy_sha256"] != first["policy_sha256"]


def test_real_signal_and_candidate_pipeline_without_evaluator_mock():
    from tests.test_fno_signal_scan import _frame, LONG_ROWS, NOW, EXPIRY
    value = candidate_bundle()
    value["received_at"] = NOW.isoformat()
    value["snapshot"]["taken_at"] = NOW.isoformat()
    value["snapshot"]["expiry"] = EXPIRY.isoformat()
    for contract in value["contracts"]:
        contract["expiry"] = EXPIRY.isoformat()
    for quote in value["snapshot"]["quotes"]:
        quote["last_trade_time"] = NOW.isoformat()
    book, snapshot, profile = qualification.load_candidate_evidence(value, underlying="NIFTY", decision_at=NOW)
    result = qualification.evaluate_deployed_full_policy(underlying="NIFTY", bars=_frame(LONG_ROWS),
        regime="REGIME_1_NORMAL", decision_at=NOW, bar_provenance=provenance(NOW),
        book=book, snapshot=snapshot, profile=profile)
    assert result.signal.direction == FnoDirection.LONG
    assert result.candidate is not None
    assert result.state == "ACCEPTED", result.validation_reasons
    assert result.can_qualify is False


def test_decision_output_is_atomic_idempotent_and_never_overwritten(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace
    now = IST.localize(datetime(2026, 9, 11, 10))
    decision = qualification.evaluate_deployed_full_policy(underlying="NIFTY", bars=bars(),
        regime="REGIME_1_NORMAL", decision_at=now, bar_provenance=provenance(now))
    target = tmp_path / "decision.json"
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: qualification.write_full_policy_decision(target, decision), range(8)))
    before = target.read_bytes()
    assert all(result == results[0] for result in results)
    with pytest.raises(ValueError, match="different immutable evidence"):
        qualification.write_full_policy_decision(target, replace(decision, reason="different"))
    assert target.read_bytes() == before
    assert not list(tmp_path.glob(".decision-*"))
