from dataclasses import replace
from datetime import datetime

import pytest
import pytz

from intraday_spread_chronological import ChronologicalReplay
from intraday_spread_holdout import HeldOutCase, build_heldout_comparison
from intraday_spread_replay import ReplayResult


def replay(state="CLOSED", pnl=5.0, identity="a"):
    result = ReplayResult(state, "fixture", 1.0, 2.0, 1.0, pnl if state == "CLOSED" else None,
                          "2026-09-10T10:00:00+05:30", "2026-09-10T10:05:00+05:30", identity * 64)
    return ChronologicalReplay(result, state, 1, (), result.entry_at, "take_profit", 2, identity * 64)


def test_heldout_comparison_preserves_group_and_no_fill_coverage():
    report = build_heldout_comparison(dataset_sha256="b" * 64, code_revision="abc",
        training_sessions=["2026-09-08"], holdout_sessions=["2026-09-10"],
        declared_coverage=[("NIFTY", "policy-a", "2026-09-10"), ("SENSEX", "policy-b", "2026-09-10")], cases=[
            HeldOutCase("NIFTY", "policy-a", "2026-09-10", replay("CLOSED", 8, "a"), "one", "d" * 64),
            HeldOutCase("NIFTY", "policy-a", "2026-09-10", replay("NO_FILL", identity="b"), "two", "d" * 64),
            HeldOutCase("SENSEX", "policy-b", "2026-09-10", replay("UNRESOLVED", identity="c"), "three", "d" * 64),
        ])
    assert report["automatic_qualification"] is False
    assert report["groups"][0]["closed"] == 1
    assert report["groups"][0]["no_fill"] == 1
    assert report["groups"][1]["unresolved"] == 1


def test_heldout_comparison_rejects_overlap_and_duplicate_evidence():
    with pytest.raises(ValueError, match="non-overlapping"):
        build_heldout_comparison(dataset_sha256="b" * 64, code_revision="abc", training_sessions=["2026-09-10"],
            holdout_sessions=["2026-09-10"], declared_coverage=[("NIFTY", "x", "2026-09-10")], cases=[])
    with pytest.raises(ValueError, match="duplicate"):
        build_heldout_comparison(dataset_sha256="b" * 64, code_revision="abc", training_sessions=["2026-09-08"],
            holdout_sessions=["2026-09-10"], declared_coverage=[("NIFTY", "x", "2026-09-10"), ("SENSEX", "x", "2026-09-10")],
            cases=[HeldOutCase("NIFTY", "x", "2026-09-10", replay(identity="a"), "one", "d" * 64),
                   HeldOutCase("SENSEX", "x", "2026-09-10", replay(identity="a"), "two", "d" * 64)])


def test_heldout_requires_chronological_split_and_keeps_unavailable_coverage():
    report = build_heldout_comparison(dataset_sha256="b" * 64, code_revision="abc", training_sessions=["2026-09-08"],
        holdout_sessions=["2026-09-10"], declared_coverage=[("NIFTY", "x", "2026-09-10")], cases=[])
    assert report["groups"][0]["coverage"] == {"2026-09-10": "UNAVAILABLE"}
    with pytest.raises(ValueError, match="precede"):
        build_heldout_comparison(dataset_sha256="b" * 64, code_revision="abc", training_sessions=["2026-09-11"],
            holdout_sessions=["2026-09-10"], declared_coverage=[("NIFTY", "x", "2026-09-10")], cases=[])
