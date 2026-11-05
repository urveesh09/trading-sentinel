from datetime import datetime
from types import SimpleNamespace

import pytest

import round23 as study


def test_repair_and_hold_use_different_completed_gap_behavior():
    gap = study.setup(study.REPAIR, 1100., 1075., 1050., 1000., 100., 2050., 80.)
    assert gap == study.Gap(-1, 28., 2050., 2000.)
    assert study.fill_levels(gap, 2052.) == (2080., 2000.)
    assert study.fill_levels(gap, 2060.) is None
    assert study.setup(study.HOLD, 1100., 1075., 1050., 1000., 100., 2050., 80.) is None
    continuation = study.setup(study.HOLD, 900., 902., 894., 1000., 100., 2050., 20.)
    assert continuation == study.Gap(-1, 12., 2050., None)
    assert study.fill_levels(continuation, 2050.) == pytest.approx((2062., 2028.4))


def test_protection_prioritizes_underlying_and_premium_before_clock():
    position = SimpleNamespace(side=1, stop_underlying=100., target_underlying=140., premium_stop=90.)
    assert study.reason_at(position, 99., 85., 580) == "underlying_stop"
    assert study.reason_at(position, 145., 85., 580) == "premium_backstop"
    assert study.reason_at(position, 145., None, 580) == "early_target"
    assert study.reason_at(position, 120., None, 580) == "early_clock"
    assert study.reason_at(position, 120., 100., 579) is None


def test_prior_closes_exclude_same_day():
    data = {f"2026-01-{i:02d}": 1000. + i for i in range(1, 24)}
    day = datetime.fromisoformat("2026-01-22").date().isoformat()
    prior = study.prior(data, day)
    data[day] = 1e7
    assert study.prior(data, day) == prior
