"""[SKILL 2026-08-05] Tests for the random-control skill test.

Built around a synthetic world where the right answer is known by construction:
some tickers are genuinely better than others, so a selector that picks them
HAS skill and a selector that picks at random does not. If the test cannot tell
those two apart it is worthless, and every assertion here is aimed at that.
"""
import random

import pytest

from skill_test import (
    HLZ_T_THRESHOLD,
    SINGLE_TEST_T_THRESHOLD,
    TradeSpec,
    categorise,
    format_report,
    run_control,
    skill_threshold,
    split_by_day,
)

DAYS = [f"2026-0{1 + d // 28}-{1 + d % 28:02d}" for d in range(120)]
UNIVERSE = [f"TICK{i:03d}" for i in range(60)]

#: A world where 10 of the 60 names have positive expectancy and the rest are
#: a fair coin. Deterministic per (ticker, day) so a control redraw of the same
#: pair is consistent, exactly as a real backtest would be.
GOOD = set(UNIVERSE[:10])


def simulate(ticker, day):
    rng = random.Random(f"{ticker}|{day}")
    base = rng.gauss(0.0, 1.0)
    return base + (0.9 if ticker in GOOD else 0.0)


def candidates_on_day(_day):
    return UNIVERSE


def _trades(picker, n=60, seed=1):
    """Build n trades by applying `picker` to spread-out days."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        day = DAYS[i % len(DAYS)]
        ticker = picker(day, rng)
        out.append(TradeSpec(ticker=ticker, day=day, r=simulate(ticker, day)))
    return out


# ── the two answers the test exists to distinguish ────────────────────────

def test_a_skilled_selector_beats_the_random_control():
    trades = _trades(lambda day, rng: rng.choice(sorted(GOOD)))
    result = run_control(trades, candidates_on_day, simulate, replications=300)

    assert result["observed_mean_r"] > result["control_mean_r"]
    assert result["skill_t"] > SINGLE_TEST_T_THRESHOLD
    assert result["p_value"] < 0.05
    assert categorise(result) == "confirmed_skill"


def test_a_random_selector_is_indistinguishable_from_the_control():
    """The case that matters most: a book riding drift must NOT read as skill."""
    trades = _trades(lambda day, rng: rng.choice(UNIVERSE))
    result = run_control(trades, candidates_on_day, simulate, replications=300)

    assert abs(result["skill_t"]) < SINGLE_TEST_T_THRESHOLD
    assert categorise(result) == "noise"


def test_an_inverted_selector_is_reported_as_reversed_not_noise():
    """Exact mirror of the skilled case: 10 good names, 10 bad, 40 neutral, so
    the random control sits at zero and a selector that reliably picks the bad
    ten is as far below the null as the skilled one is above it."""
    BAD = set(UNIVERSE[10:20])

    def sim(ticker, day):
        rng = random.Random(f"{ticker}|{day}")
        tilt = 0.9 if ticker in GOOD else (-0.9 if ticker in BAD else 0.0)
        return rng.gauss(0.0, 1.0) + tilt

    rng = random.Random(7)
    trades = []
    for i in range(60):
        day = DAYS[i % len(DAYS)]
        ticker = rng.choice(sorted(BAD))
        trades.append(TradeSpec(ticker, day, sim(ticker, day)))

    result = run_control(trades, candidates_on_day, sim, replications=300)
    # The control is centred near zero by construction.
    assert abs(result["control_mean_r"]) < 0.2
    assert result["skill_t"] < -SINGLE_TEST_T_THRESHOLD
    assert categorise(result) == "reversed"


# ── guards against over-claiming ──────────────────────────────────────────

def test_fewer_than_three_trades_is_an_error_not_a_verdict():
    trades = [TradeSpec("TICK000", DAYS[0], 1.0), TradeSpec("TICK001", DAYS[1], 2.0)]
    result = run_control(trades, candidates_on_day, simulate)
    assert "error" in result


def test_a_small_but_lucky_sample_is_still_noise():
    """Eight great trades must not read as a green light."""
    trades = _trades(lambda day, rng: rng.choice(sorted(GOOD)), n=8)
    result = run_control(trades, candidates_on_day, simulate, replications=300)
    assert categorise(result, min_trades=20) == "noise"


def test_p_value_is_never_exactly_zero():
    """500 draws cannot support p=0; the +1 correction enforces that."""
    trades = _trades(lambda day, rng: rng.choice(sorted(GOOD)))
    result = run_control(trades, candidates_on_day, simulate, replications=100)
    assert result["p_value"] > 0.0


def test_an_empty_candidate_universe_errors_rather_than_inventing_a_null():
    trades = _trades(lambda day, rng: rng.choice(UNIVERSE), n=30)
    result = run_control(trades, lambda _day: [], simulate, replications=100)
    assert "error" in result
    assert "too sparse" in result["error"]


def test_a_simulator_that_always_fails_errors():
    trades = _trades(lambda day, rng: rng.choice(UNIVERSE), n=30)
    result = run_control(trades, candidates_on_day, lambda t, d: None, replications=100)
    assert "error" in result


# ── mechanics ─────────────────────────────────────────────────────────────

def test_the_result_is_deterministic_for_a_fixed_seed():
    trades = _trades(lambda day, rng: rng.choice(UNIVERSE))
    a = run_control(trades, candidates_on_day, simulate, replications=120, seed=99)
    b = run_control(trades, candidates_on_day, simulate, replications=120, seed=99)
    assert a == b


def test_a_different_seed_moves_the_control_but_not_the_observation():
    trades = _trades(lambda day, rng: rng.choice(UNIVERSE))
    a = run_control(trades, candidates_on_day, simulate, replications=120, seed=1)
    b = run_control(trades, candidates_on_day, simulate, replications=120, seed=2)
    assert a["observed_mean_r"] == b["observed_mean_r"]
    assert a["control_mean_r"] != b["control_mean_r"]


def test_exclude_actual_ticker_keeps_the_real_pick_out_of_the_control():
    seen = []

    def spy(ticker, day):
        seen.append(ticker)
        return simulate(ticker, day)

    trades = [TradeSpec("TICK000", DAYS[i], 1.0) for i in range(30)]
    run_control(trades, candidates_on_day, spy, replications=50,
                exclude_actual_ticker=True)
    assert "TICK000" not in seen


def test_not_excluding_lets_the_real_pick_back_into_the_pool():
    seen = []

    def spy(ticker, day):
        seen.append(ticker)
        return simulate(ticker, day)

    trades = [TradeSpec("TICK000", DAYS[i], 1.0) for i in range(30)]
    run_control(trades, candidates_on_day, spy, replications=50,
                exclude_actual_ticker=False)
    assert "TICK000" in seen


# ── the multiple-testing bar ──────────────────────────────────────────────

def test_one_configuration_gets_the_textbook_bar():
    assert skill_threshold(1) == SINGLE_TEST_T_THRESHOLD


def test_a_search_gets_the_harvey_liu_zhu_bar():
    assert skill_threshold(12) == HLZ_T_THRESHOLD


def test_a_result_that_passes_at_2_can_fail_at_3_point_5():
    result = {"n_trades": 40, "skill_t": 2.5}
    assert categorise(result, t_threshold=2.0) == "confirmed_skill"
    assert categorise(result, t_threshold=3.5) == "noise"


# ── out-of-sample ─────────────────────────────────────────────────────────

def test_oos_decay_is_train_only():
    full = {"n_trades": 60, "skill_t": 3.0}
    train = {"n_trades": 40, "skill_t": 3.2}
    test = {"n_trades": 20, "skill_t": 0.4}
    assert categorise(full, train, test, t_threshold=2.0) == "train_only"


def test_oos_sign_flip_is_reversed_not_train_only():
    """The distinction the strict bench makes on purpose."""
    full = {"n_trades": 60, "skill_t": 3.0}
    train = {"n_trades": 40, "skill_t": 4.0}
    test = {"n_trades": 20, "skill_t": -2.6}
    assert categorise(full, train, test, t_threshold=2.0) == "reversed"


def test_skill_confined_to_the_test_half_is_noise_not_confirmation():
    full = {"n_trades": 60, "skill_t": 2.4}
    train = {"n_trades": 40, "skill_t": 0.1}
    test = {"n_trades": 20, "skill_t": 3.0}
    assert categorise(full, train, test, t_threshold=2.0) == "noise"


def test_both_halves_passing_is_confirmed():
    full = {"n_trades": 60, "skill_t": 3.0}
    train = {"n_trades": 40, "skill_t": 2.5}
    test = {"n_trades": 20, "skill_t": 2.2}
    assert categorise(full, train, test, t_threshold=2.0) == "confirmed_skill"


def test_split_is_chronological_not_random():
    trades = [TradeSpec(f"T{i}", DAYS[i], 0.0) for i in range(100)]
    train, test = split_by_day(trades, 0.7)
    assert len(train) == 70 and len(test) == 30
    assert max(str(t.day) for t in train) <= min(str(t.day) for t in test)


# ── reporting ─────────────────────────────────────────────────────────────

def test_report_names_the_verdict_and_the_bar():
    trades = _trades(lambda day, rng: rng.choice(sorted(GOOD)))
    result = run_control(trades, candidates_on_day, simulate, replications=200)
    text = format_report("connors", result, configurations_tried=12)
    assert "VERDICT" in text
    assert "3.5" in text          # the HLZ bar is stated, not implied
    assert "control" in text.lower()


def test_report_on_an_errored_result_says_so_plainly():
    text = format_report("x", {"error": "not enough trades"})
    assert "could not run" in text
