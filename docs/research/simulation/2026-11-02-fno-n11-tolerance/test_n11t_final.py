"""The final book is what PLAN_FINAL.md says, and the plan-wording patches are in force. Needs the research stack: N11_WITH_LAB=1 N08_YEAR=2024 pytest test_n11t_final.py"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
pytestmark = pytest.mark.skipif(os.environ.get("N11_WITH_LAB") != "1", reason="set N11_WITH_LAB=1 and N08_YEAR=2024")


@pytest.fixture(scope="module")
def lab():
    import n11t_final
    return n11t_final


def test_the_final_book_is_the_plans(lab):
    final = lab.fpanel_books()["FINAL"]
    assert final["n11t"]["limit"] == 6250.0 and final["n11"]["k"] == 1.75 and final["n11"]["flat"] == 6250.0
    assert final["n11t"]["clamp"] == "SECOND_LOT" and final["n11t"]["strict"] is True
    assert final["n11t"]["when"] == ["VOL", "EV"] and final["n11t"]["add"] is False


def test_every_book_but_the_reference_follows_the_plans_wording(lab):
    books = lab.fpanel_books()
    assert "n11t" not in books["N11"]
    assert all(b["n11t"]["strict"] for name, b in books.items() if name != "N11")


def test_neighbours_differ_only_where_named(lab):
    books = lab.fpanel_books()
    assert books["K1.5"]["n11"]["k"] == 1.5 and books["K1.5"]["n11t"]["limit"] == 6250.0
    assert books["K2.0"]["n11"]["k"] == 2.0 and books["L5500"]["n11t"]["limit"] == 5500.0 and books["L7000"]["n11t"]["limit"] == 7000.0
    assert books["NO_READING"]["n11t"]["when"] == ["VOL"] and books["REVERSED"]["n11t"]["when"] == ["VOL", "EV_NOT"]
    assert books["DOUBLE"]["cost"] == [400.0, 10.0]


def test_the_strict_patches_are_in_force(lab):
    assert lab.Q.second_lot is lab.S.second_lot
    assert lab.Y.BookReplay._entry is lab.S.entry
