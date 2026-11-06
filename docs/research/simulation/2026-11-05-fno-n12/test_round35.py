from datetime import datetime, timedelta

from round35 import TWO, timed_exit


def test_stop_waits_for_next_sufficient_volume_print():
    opened = datetime(2024, 6, 3, 11)
    one, two, three, closed = (opened + timedelta(minutes=i) for i in range(1, 5))
    tape = {one: (80., TWO), two: (70., TWO - 1), three: (65., TWO), closed: (130., TWO)}
    assert timed_exit(opened, closed, tape, 85.) == (three, 65., "premium_backstop")
    assert timed_exit(opened, closed, tape, None) == (closed, 130., "native_deadline")


def test_guard_refuses_to_impute_a_trigger_inside_missing_minute():
    opened = datetime(2024, 6, 3, 11)
    closed = opened + timedelta(minutes=2)
    tape = {closed: (130., TWO)}
    assert timed_exit(opened, closed, tape, 85.) is None
    assert timed_exit(opened, closed, tape, None) == (closed, 130., "native_deadline")
