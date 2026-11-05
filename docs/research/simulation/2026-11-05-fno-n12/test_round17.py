from datetime import date, datetime, timedelta, timezone

import round17 as study


DAY = date(2026, 11, 5)


def row(days_ago, net, expert="TPB", side="SHORT"):
    day = DAY - timedelta(days=days_ago)
    return datetime(day.year, day.month, day.day, 10, tzinfo=timezone.utc), expert, side, net


def test_matching_prior_distinct_dates_only():
    good = [row(ago, 600.) for ago in range(1, 9)]
    excluded = [row(-1, -1e6), row(0, -1e6), row(181, -1e6), row(1, -1e6, side="LONG"), row(1, -1e6, "OR20")]
    assert study.rating(good + excluded, DAY, "TPB", "SHORT") == 1
    assert study.rating(good[:7] + [good[0]] * 10 + excluded, DAY, "TPB", "SHORT") == 0
    assert study.rating([row(ago, -600.) for ago in range(1, 9)], DAY, "TPB", "SHORT") == -1


def test_outlier_neutrality_and_native_fallback():
    points = [row(ago, -200.) for ago in range(1, 8)] + [row(8, 1e8)]
    assert study.rating(points, DAY, "TPB", "SHORT") == 0
    assert study.gate(True, 0, "CONTEXT_GATE") == "NATIVE_HOLD"
    assert study.gate(False, -1, "CONTEXT_RELEASE") == "NATIVE_ALLOW"
    assert study.gate(False, -1, "CONTEXT_GATE") == "HOLD"
    assert study.gate(True, 1, "CONTEXT_RELEASE") == "RELEASE"
