"""[ROADMAP-5.1 2026-07-13] Tests for walk-forward evaluation.

The load-bearing tests here are the ones that prove the harness can DETECT
overfitting -- i.e. that it says "no" to a strategy that only looks good on the
data it was chosen with. A walk-forward harness that always says yes is worse
than no harness, because it launders a bad number as a validated one.
"""
import pytest

from walk_forward import Fold, generate_folds, walk_forward


# ===================================================================
# Fold construction -- the lookahead invariant
# ===================================================================

def test_test_window_is_strictly_after_train_window():
    folds = generate_folds("2026-01-01", "2026-03-31", train_days=30, test_days=10)
    assert folds
    for f in folds:
        assert f.train_end < f.test_start


def test_a_fold_that_overlaps_is_rejected_outright():
    """One day of overlap and the out-of-sample score is contaminated by data
    the selector already saw -- and it would still LOOK like a valid result.
    Refuse to construct it at all."""
    with pytest.raises(ValueError, match="LOOKAHEAD"):
        Fold(
            train_start="2026-01-01",
            train_end="2026-01-31",
            test_start="2026-01-31",   # same day: overlap
            test_end="2026-02-10",
        )


def test_rolling_folds_slide_and_do_not_overlap_their_test_windows():
    folds = generate_folds("2026-01-01", "2026-04-10", train_days=30, test_days=10)
    # Default step == test_days, so test windows partition the tail exactly.
    for a, b in zip(folds, folds[1:]):
        assert a.test_end < b.test_start
    # rolling: train window keeps a fixed length, so its start moves
    assert folds[0].train_start != folds[-1].train_start


def test_anchored_folds_pin_the_start_and_grow():
    folds = generate_folds(
        "2026-01-01", "2026-04-10", train_days=30, test_days=10, anchored=True
    )
    assert len(folds) >= 2
    assert all(f.train_start == "2026-01-01" for f in folds)
    # ...and the training window genuinely grows
    assert folds[0].train_end < folds[-1].train_end


def test_no_folds_when_the_window_is_too_short():
    assert generate_folds("2026-01-01", "2026-01-20", train_days=30, test_days=10) == []


def test_overlapping_oos_windows_are_rejected():
    with pytest.raises(ValueError, match="do not overlap"):
        generate_folds(
            "2026-01-01", "2026-06-30", train_days=30,
            test_days=10, step_days=5,
        )


# ===================================================================
# THE POINT: does it catch overfitting?
# ===================================================================

def test_an_overfit_config_is_caught_by_a_large_positive_gap():
    """The scenario the roadmap is worried about.

    'lucky' scores brilliantly on any TRAIN window and terribly on any TEST
    window -- exactly what a parameter tuned to noise does. The in-sample number
    says +100; the honest number is -50, and the harness must report both, plus
    the gap between them.
    """
    folds = generate_folds("2026-01-01", "2026-06-30", train_days=30, test_days=10)
    assert len(folds) >= 3

    # Key on the exact (start, end) window. Keying on `end` alone is wrong:
    # with rolling folds, one fold's TEST end can coincide with a later fold's
    # TRAIN end, so the runner would misclassify an out-of-sample call as
    # in-sample -- which is how this test failed the first time it was run.
    train_windows = {(f.train_start, f.train_end) for f in folds}

    def runner(cfg, start, end):
        is_train = (start, end) in train_windows
        if cfg == "lucky":
            return 100.0 if is_train else -50.0   # pure curve-fit
        return 1.0                                # boring but real, in and out

    report = walk_forward(["lucky", "boring"], folds, runner)

    # 'lucky' wins every train window, so it is what gets selected...
    assert report["most_selected_config"] == "lucky"
    assert report["selection_stability"] == 1.0
    # ...and the harness reports what it ACTUALLY delivered.
    assert report["mean_out_of_sample_score"] == -50.0
    assert report["overfit_gap"] == 150.0          # 100 in-sample - (-50) real
    assert report["verdict"] == "no_out_of_sample_edge"


def test_a_genuine_edge_survives_out_of_sample():
    """The counterpart. A harness that can only say 'no' is useless."""
    folds = generate_folds("2026-01-01", "2026-06-30", train_days=30, test_days=10)

    def runner(cfg, start, end):
        return 10.0 if cfg == "good" else -5.0     # good everywhere, in and out

    report = walk_forward(["good", "bad"], folds, runner)

    assert report["most_selected_config"] == "good"
    assert report["mean_out_of_sample_score"] == 10.0
    assert report["overfit_gap"] == 0.0
    assert report["positive_oos_fraction"] == 1.0
    assert report["verdict"] == "out_of_sample_edge"


def test_profit_carried_by_one_lucky_fold_is_not_an_edge():
    """Mean out-of-sample P&L is positive, but only because ONE fold was huge.
    That is not a validated strategy, it is a lottery ticket -- and a naive
    'is mean OOS > 0' check would have waved it through."""
    folds = generate_folds("2026-01-01", "2026-06-30", train_days=30, test_days=10)
    assert len(folds) >= 4

    train_windows = {(f.train_start, f.train_end) for f in folds}
    jackpot = sorted({f.test_start for f in folds})[0]

    def runner(cfg, start, end):
        if (start, end) in train_windows:
            return 5.0                       # identical in-sample
        return 1000.0 if start == jackpot else -10.0

    report = walk_forward(["a"], folds, runner)

    assert report["mean_out_of_sample_score"] > 0      # looks profitable
    assert report["positive_oos_fraction"] < 0.5       # ...but almost every fold lost
    assert report["verdict"] == "carried_by_outlier_folds"


def test_an_unstable_winner_is_flagged():
    """If a different config wins every fold, the sweep is not finding a
    parameter -- it is finding whatever happened to work last month."""
    folds = generate_folds("2026-01-01", "2026-06-30", train_days=30, test_days=10)
    train_windows = [(f.train_start, f.train_end) for f in folds]

    def runner(cfg, start, end):
        if (start, end) in train_windows:
            # rotate the winner fold by fold
            i = train_windows.index((start, end))
            return 10.0 if cfg == ["a", "b", "c"][i % 3] else 1.0
        return 5.0  # everything is mildly profitable out of sample

    report = walk_forward(["a", "b", "c"], folds, runner)

    assert report["mean_out_of_sample_score"] > 0
    assert report["selection_stability"] < 0.5
    assert report["verdict"] == "unstable_selection"


# ===================================================================
# Honesty plumbing
# ===================================================================

def test_a_config_that_never_traded_is_skipped_not_scored_zero():
    """A strategy that did not trade is NOT the same as one that broke even.
    Scoring it 0.0 would let a config that never fires WIN a fold in which
    everything else lost money -- and the sweep would then 'select' doing
    nothing, and report it as an edge."""
    folds = generate_folds("2026-01-01", "2026-03-31", train_days=30, test_days=10)

    def runner(cfg, start, end):
        if cfg == "never_trades":
            return None          # no trades in the window
        return -20.0             # the only config that actually traded, and it lost

    report = walk_forward(["never_trades", "loses"], folds, runner)

    assert report["most_selected_config"] == "loses"     # not 'never_trades'
    assert report["mean_out_of_sample_score"] == -20.0
    assert report["verdict"] == "no_out_of_sample_edge"


def test_all_configs_silent_in_a_fold_yields_no_score_not_a_fake_one():
    folds = generate_folds("2026-01-01", "2026-03-31", train_days=30, test_days=10)
    report = walk_forward(["a"], folds, lambda c, s, e: None)
    assert report["n_scored_folds"] == 0
    assert report["verdict"] == "insufficient_data"


def test_fewer_than_three_scored_folds_exposes_no_aggregate():
    folds = generate_folds(
        "2026-01-01", "2026-02-10", train_days=30, test_days=10
    )
    report = walk_forward(["a"], folds, lambda c, s, e: 5.0)
    assert report["n_scored_folds"] == 1
    assert report["verdict"] == "insufficient_data"
    assert report["minimum_scored_folds"] == 3
    assert "mean_out_of_sample_score" not in report
    assert "overfit_gap" not in report


def test_selection_uses_train_only_never_test():
    """Guards the core contract. Record every window the runner is asked about
    while CHOOSING; none of them may be a test window."""
    folds = generate_folds("2026-01-01", "2026-06-30", train_days=30, test_days=10)
    test_windows = {(f.test_start, f.test_end) for f in folds}
    seen: list[tuple] = []

    def runner(cfg, start, end):
        seen.append((cfg, start, end))
        return 1.0

    walk_forward(["a", "b"], folds, runner)

    # For each fold the runner is called once per config on TRAIN, then exactly
    # once on TEST with the winner. So a test window may appear at most once,
    # and never more than one config deep.
    for f in folds:
        calls_on_test = [c for c in seen if (c[1], c[2]) == (f.test_start, f.test_end)]
        assert len(calls_on_test) == 1, (
            "a test window was evaluated more than once -- the selector is "
            "peeking at out-of-sample data"
        )
