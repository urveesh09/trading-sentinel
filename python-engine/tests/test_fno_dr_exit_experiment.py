from datetime import datetime, timedelta
import hashlib
from zoneinfo import ZoneInfo

import pytest

from fno_dr_exit_experiment import BASELINE, TRAIL, DrEntry, DrObservation, build_report, freeze_manifest, simulate
from momentum_exit_study import ExitStudyError

IST = ZoneInfo("Asia/Kolkata")

def _entry():
    now = datetime(2026, 10, 2, 10, tzinfo=IST); packet=b"exact-source"
    return DrEntry("dr-1", "sha256:"+hashlib.sha256(packet).hexdigest(), packet, now, "DIRECTIONAL_DEBIT_SPREAD", 1000, 500, 20,
        ({"contract":{"underlying":"NIFTY","expiry":"2026-10-08","token":1,"tradingsymbol":"NIFTY","lot_size":65}},),
        (DrObservation(now+timedelta(minutes=1), 600, 10), DrObservation(now+timedelta(minutes=2), 300, 10), DrObservation(now+timedelta(minutes=3), 300, 10, True)))

def test_spread_candidate_holds_target_then_exits_on_giveback_and_costs_once():
    entry=_entry(); base=simulate(entry, BASELINE); candidate=simulate(entry, TRAIL)
    assert base["reason"] == "target" and base["costs"] == 30
    assert candidate["reason"] == "trail_giveback" and candidate["costs"] == 30

def test_packet_identity_and_frozen_holdout_are_explicit():
    entry=_entry()
    with pytest.raises(ExitStudyError, match="identity"):
        simulate(DrEntry(**{**vars(entry), "source_ref":"sha256:"+"0"*64}), BASELINE)
    report=build_report([entry], freeze_manifest(experiment_id="dr", frozen_at=entry.entry_at-timedelta(days=1)))
    assert report["pairs"][0]["sample"] == "HOLDOUT" and report["authorization_effect"] == "NONE"
