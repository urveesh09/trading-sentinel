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
