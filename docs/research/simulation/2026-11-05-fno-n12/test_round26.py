import pytest

from round26 import INPUTS, MARKS, observe


def test_rotation_only_uses_completed_prefix_and_separate_outcome():
    base = {at: (1015., 985., 1000., 10.) for at in INPUTS}
    base["12:44:00"] = (1042., 1039., 1040., 10.)
    base["12:54:00"] = (1039., 1035., 1037., 10.)
    base["12:59:00"] = (1035., 1027., 1028., 10.)
    assert observe(base)[0] == "missing_outcome"
    base[MARKS[0]] = (1030., 1025., 1026., 10.)
    base[MARKS[1]] = (1008., 1000., 1002., 10.)
    tag, trade = observe(base)
    assert tag == "signal"
    assert trade["side"] == -1 and trade["points"] == 24.
    assert trade["repair"] == pytest.approx(.30)
    del base["09:41:00"]
    assert observe(base) == ("missing_input", None)


def test_missing_confirmation_cannot_use_entry_price():
    base = {at: (1015., 985., 1000., 10.) for at in INPUTS}
    base["12:44:00"] = (1042., 1039., 1040., 10.)
    base["12:54:00"] = (1047., 1041., 1045., 10.)
    base["12:59:00"] = (1035., 1027., 1028., 10.)
    base[MARKS[0]] = (1030., 1025., 1026., 10.)
    assert observe(base) == ("unconfirmed", None)
