"""[EXIT-QUALITY 2026-08-05] Tests for the exit-quality decomposition.

Every case is a hand-built path where the right answer is obvious by
inspection, because the whole value of this module is that its numbers get
believed and acted on.
"""
import pytest

from exit_quality import (
    DEFAULT_MATERIAL_R,
    Excursion,
    attribute,
    format_report,
    grade,
)


def _exc(entry=100.0, stop=97.0, exit_price=103.0, exit_reason="t1",
         highs=None, lows=None, exit_index=0):
    """R = 3.0 by default, so +3 points = +1R and the arithmetic is readable."""
    highs = [103.0] if highs is None else highs
    lows = [99.0] if lows is None else lows
    return Excursion(entry, stop, exit_price, exit_reason, highs, lows, exit_index)


# ── the two diseases ──────────────────────────────────────────────────────

def test_a_target_cap_that_misses_a_bigger_move_is_left_on_table():
    """The Connors t1 shape: capped at +1R while the move ran to +3R."""
    g = grade(_exc(
        exit_price=103.0, exit_reason="t1",
        highs=[103.0, 106.0, 109.0], lows=[99.0, 102.0, 105.0], exit_index=0,
    ), after_bars=5)

    assert g["r_realised"] == pytest.approx(1.0)
    assert g["left_on_table_r"] == pytest.approx(2.0)   # ran to 109 = +3R
    assert g["give_back_r"] == pytest.approx(0.0)
    assert g["verdict"] == "left_on_table"


def test_holding_a_winner_into_a_reversal_is_gave_back():
    g = grade(_exc(
        exit_price=100.5, exit_reason="trail_stop",
        highs=[103.0, 109.0, 101.0], lows=[99.0, 102.0, 100.0], exit_index=2,
    ), after_bars=5)

    assert g["mfe_r"] == pytest.approx(3.0)             # touched 109
    assert g["r_realised"] == pytest.approx(1 / 6, abs=1e-4)
    assert g["give_back_r"] > 2.8
    assert g["verdict"] == "gave_back"


def test_capturing_most_of_the_move_is_a_good_exit():
    g = grade(_exc(
        exit_price=108.7, exit_reason="t2",
        highs=[103.0, 109.0], lows=[99.0, 104.0], exit_index=1,
    ), after_bars=5)
    assert g["verdict"] == "good_exit"


def test_a_stop_doing_its_job_is_not_graded_as_a_defect():
    """Otherwise the stop looks like the problem in every losing book."""
    g = grade(_exc(
        exit_price=97.0, exit_reason="stop",
        highs=[100.5, 99.0], lows=[97.0, 95.0], exit_index=0,
    ))
    assert g["verdict"] == "stopped"


def test_a_stopped_trade_accrues_no_give_back_or_left_on_table():
    """Both measures are pinned to the stop distance on a stopped trade, so
    they would read ~1.0R on EVERY stop and swamp the totals with a number
    describing the risk model rather than any exit mistake."""
    g = grade(_exc(
        exit_price=97.0, exit_reason="stop",
        highs=[100.2, 104.0], lows=[96.5, 99.0], exit_index=0,
    ))
    assert g["give_back_r"] == 0.0
    assert g["left_on_table_r"] == 0.0


def test_a_price_recovering_after_a_stop_is_surfaced_separately():
    """Tight stops are a real defect, but a different one from a target cap."""
    g = grade(_exc(
        exit_price=97.0, exit_reason="stop",
        highs=[100.2, 106.0], lows=[96.5, 99.0], exit_index=0,
    ))
    assert g["recovery_after_stop_r"] == pytest.approx(3.0)   # -1R -> +2R
    assert g["verdict"] == "stopped"


def test_a_non_stopped_trade_reports_zero_recovery_after_stop():
    g = grade(_exc(
        exit_price=103.0, highs=[103.0, 112.0], lows=[99.0, 104.0], exit_index=0,
    ))
    assert g["recovery_after_stop_r"] == 0.0


# ── the honesty rules ─────────────────────────────────────────────────────

def test_left_on_table_respects_the_bounded_horizon():
    """A move that arrives long after the exit must not condemn the exit."""
    highs = [103.0] + [103.0] * 9 + [200.0]
    lows = [99.0] * 11
    near = grade(_exc(highs=highs, lows=lows, exit_index=0), after_bars=3)
    far = grade(_exc(highs=highs, lows=lows, exit_index=0), after_bars=20)

    assert near["left_on_table_r"] == pytest.approx(0.0)
    assert far["left_on_table_r"] > 30
    assert near["verdict"] == "good_exit"


def test_the_horizon_used_is_reported_so_the_number_is_interpretable():
    g = grade(_exc(), after_bars=7)
    assert g["after_bars"] == 7


def test_give_back_and_left_on_table_are_never_negative():
    g = grade(_exc(
        exit_price=110.0, exit_reason="gap",
        highs=[104.0, 103.0], lows=[99.0, 98.0], exit_index=1,
    ))
    assert g["give_back_r"] >= 0.0
    assert g["left_on_table_r"] >= 0.0


def test_noise_sized_excursions_do_not_trigger_a_verdict():
    small = DEFAULT_MATERIAL_R / 2 * 3.0        # in points, R = 3
    g = grade(_exc(
        exit_price=103.0,
        highs=[103.0 + small], lows=[99.0], exit_index=0,
    ))
    assert g["verdict"] == "good_exit"


# ── input validation ──────────────────────────────────────────────────────

def test_a_non_positive_risk_is_an_error_not_a_division_by_zero():
    g = grade(_exc(entry=100.0, stop=100.0))
    assert "error" in g


def test_a_stop_above_entry_is_an_error():
    g = grade(_exc(entry=100.0, stop=105.0))
    assert "error" in g


def test_mismatched_path_lengths_are_rejected():
    g = grade(_exc(highs=[1.0, 2.0], lows=[1.0]))
    assert "error" in g


def test_an_exit_index_outside_the_path_is_rejected():
    g = grade(_exc(highs=[103.0], lows=[99.0], exit_index=5))
    assert "error" in g


def test_an_empty_path_is_rejected():
    g = grade(_exc(highs=[], lows=[]))
    assert "error" in g


# ── aggregation ───────────────────────────────────────────────────────────

def _capped_winner():
    return _exc(exit_price=103.0, exit_reason="t1",
                highs=[103.0, 112.0], lows=[99.0, 104.0], exit_index=0)


def _clean_stop():
    return _exc(exit_price=97.0, exit_reason="stop",
                highs=[100.1, 99.0], lows=[97.0, 96.0], exit_index=0)


def test_attribute_totals_and_groups_by_exit_rule():
    summary = attribute([_capped_winner()] * 4 + [_clean_stop()] * 2, after_bars=5)

    assert summary["n"] == 6
    assert summary["by_verdict"]["left_on_table"] == 4
    assert summary["by_verdict"]["stopped"] == 2
    assert summary["by_exit_reason"]["t1"]["n"] == 4
    # 4 capped winners each left 3R behind (103 -> 112 is +4R, took +1R).
    # The two stops contribute nothing here -- they are counted under
    # recovery_after_stop instead, so the leak totals stay about winners.
    assert summary["total_left_on_table_r"] == pytest.approx(12.0)
    assert summary["by_exit_reason"]["stop"]["left_on_table_r"] == 0.0


def test_attribute_survives_a_mix_of_gradeable_and_broken_rows():
    broken = _exc(entry=100.0, stop=100.0)
    summary = attribute([_capped_winner(), broken])
    assert summary["n"] == 1
    assert summary["n_ungradeable"] == 1


def test_attribute_on_an_empty_book():
    assert attribute([])["n"] == 0


def test_report_names_the_worst_rule_and_states_the_caveats():
    summary = attribute([_capped_winner()] * 4 + [_clean_stop()] * 2)
    text = format_report("connors", summary)

    assert "EXIT QUALITY" in text
    assert "left on table" in text
    assert "t1" in text
    assert "UPPER BOUND" in text        # the MFE caveat is stated, not implied
    assert "not a defect" in text       # the stop caveat too


def test_report_on_an_empty_book_does_not_crash():
    assert "no gradeable trades" in format_report("x", attribute([]))
