from datetime import datetime, timedelta

import pytest

import round22 as study


def test_bar_builder_rejects_missing_and_unfinished_minutes():
    start = datetime.fromisoformat("2026-11-05T09:15:00")
    boundary = start + timedelta(minutes=15)
    rows = [((start + timedelta(minutes=i)).isoformat(sep=" "), 100., 101., 99., 100.) for i in range(15)]
    assert study.bars15(rows, start, boundary) == [study.Bar(100., 101., 99., 100.)]
    assert study.bars15(rows[:4] + rows[5:], start, boundary) is None
    assert study.bars15(rows, start, boundary + timedelta(minutes=1)) is None
    assert study.bars15([*rows, (boundary.isoformat(sep=" "), 1., 2., .9, 1.)], start, boundary) is None


def test_acceptance_is_symmetric_and_requires_a_retest():
    bar = study.Bar
    bars = [bar(104, 110, 100, 107), bar(107, 110, 105, 109), bar(109, 110, 104, 108),
            bar(108, 115, 108, 112), bar(112, 117, 109.5, 113)]
    side, stop, target, atr = study.levels(bars, 114, study.ACCEPT)
    assert side == 1 and stop < 110 and target == pytest.approx(114 + 2 * (114 - stop))
    mirrored = [bar(300 - b.opened, 300 - b.low, 300 - b.high, 300 - b.close) for b in bars]
    assert study.levels(mirrored, 186, study.ACCEPT) == pytest.approx((-1, 300 - stop, 300 - target, atr))
    assert study.levels(bars[:-1] + [bar(112, 117, 112, 113)], 114, study.ACCEPT) is None


def test_rejection_requires_room_to_midpoint_and_single_edge():
    bar = study.Bar
    bars = [bar(120, 140, 100, 130), bar(130, 136, 130, 135), bar(135, 139, 133, 136), bar(136, 145, 135, 136)]
    side, stop, target, _ = study.levels(bars, 137, study.REJECT)
    assert side == -1 and stop > 145 and target == 120
    assert study.levels(bars, 134, study.REJECT) is None
    assert study.levels(bars[:-1] + [bar(136, 145, 99, 136)], 137, study.REJECT) is None
