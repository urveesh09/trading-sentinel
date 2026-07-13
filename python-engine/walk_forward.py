"""[ROADMAP-5.1 2026-07-13] Walk-forward / out-of-sample evaluation.

THE PROBLEM THIS EXISTS TO FIX
------------------------------
Every parameter in this system was chosen by running a sweep over a period and
keeping whichever setting scored best ON THAT PERIOD. penny_backtest_v2's own
docstring is candid about it, and the RSI 70-vs-80 comparison behind
PENNY_BREAKOUT_RSI_MAX is exactly that shape: run both over 2026-04-01..07-08,
observe that RSI<=80 lost ~Rs 13,500 relative to RSI<=70, keep 70.

The trouble is that "best on the data you chose it with" is not a result. With
three presets and one price history, the winner is partly signal and partly the
particular sequence of trades that happened to occur -- and you cannot tell
which from a single in-sample number. The reported P&L of the winner is
therefore biased UPWARD by construction, always, even when the underlying edge
is real.

Walk-forward is the cheapest honest answer:

    |---- train ----|-- test --|                     fold 1
              |---- train ----|-- test --|           fold 2
                        |---- train ----|-- test --| fold 3

Choose the config on TRAIN only. Score it on TEST, which the chooser never saw.
Concatenate the TEST results. That out-of-sample number is the only one you are
entitled to quote, and the gap between it and the in-sample number is a direct
measurement of how much of your "edge" was curve-fitting.

Everything here is pure: folds are computed from dates, and the backtest itself
arrives as an injected `runner` callable. No DB, no clock, no config. That means
the honesty machinery can be tested without 60 days of Kite candles -- which
matters, because those are precisely what this repo does not have yet.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Optional, Sequence


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _s(d: date) -> str:
    return d.strftime("%Y-%m-%d")


@dataclass(frozen=True)
class Fold:
    train_start: str
    train_end: str      # inclusive
    test_start: str     # strictly AFTER train_end
    test_end: str       # inclusive

    def __post_init__(self):
        # The one invariant that makes the whole exercise meaningful. A single
        # day of overlap and the "out-of-sample" score is contaminated by data
        # the selector already saw -- and it would still look like a valid
        # result, which is what makes it dangerous.
        if _d(self.test_start) <= _d(self.train_end):
            raise ValueError(
                f"LOOKAHEAD: test_start {self.test_start} is not strictly after "
                f"train_end {self.train_end}. The out-of-sample window would "
                f"contain data the selector already saw."
            )


def generate_folds(
    from_date: str,
    to_date: str,
    train_days: int,
    test_days: int,
    step_days: Optional[int] = None,
    anchored: bool = False,
) -> list[Fold]:
    """Sequential train/test folds over [from_date, to_date].

    `anchored=False` (rolling): the train window slides, keeping a fixed length.
    Use when you believe the market regime decays -- old data is not just less
    relevant, it is misleading.

    `anchored=True` (expanding): train always starts at from_date and grows.
    Use when data is scarce, which is this system's actual situation.

    `step_days` defaults to test_days, which makes the test windows exactly
    partition the tail with no overlap. Overlapping test windows would
    double-count trades and make the out-of-sample sample look larger and
    steadier than it is.
    """
    if train_days < 1 or test_days < 1:
        raise ValueError("train_days and test_days must be >= 1")
    step = step_days or test_days
    if step < 1:
        raise ValueError("step_days must be >= 1")

    start, end = _d(from_date), _d(to_date)
    if end <= start:
        raise ValueError(f"to_date {to_date} must be after from_date {from_date}")

    folds: list[Fold] = []
    train_begin = start
    while True:
        train_end = train_begin + timedelta(days=train_days - 1)
        test_start = train_end + timedelta(days=1)
        test_end = test_start + timedelta(days=test_days - 1)
        if test_end > end:
            break
        folds.append(
            Fold(
                train_start=_s(start if anchored else train_begin),
                train_end=_s(train_end),
                test_start=_s(test_start),
                test_end=_s(test_end),
            )
        )
        train_begin = train_begin + timedelta(days=step)
        if anchored:
            # Anchored: the start is pinned, so growth comes from train_end
            # advancing -- which the step above already does via train_begin.
            pass

    return folds


# Runner contract: (config_name, from_date, to_date) -> score.
# Higher is better. Returning None means "this config produced no trades in this
# window" and the config is skipped for that fold rather than scored as 0.0 --
# a strategy that did not trade is not the same as one that broke even, and
# scoring it 0.0 would let a config that never fires win a losing fold.
Runner = Callable[[str, str, str], Optional[float]]


@dataclass
class FoldResult:
    fold: Fold
    chosen_config: Optional[str]
    in_sample_score: Optional[float]
    out_of_sample_score: Optional[float]
    train_scores: dict


def walk_forward(
    configs: Sequence[str],
    folds: Sequence[Fold],
    runner: Runner,
) -> dict:
    """Select on train, score on test, for every fold.

    Returns the out-of-sample summary plus the OVERFIT GAP -- the mean
    in-sample score of the winners minus the mean out-of-sample score they
    actually delivered. A large positive gap means the sweep was fitting noise;
    that number is the whole point of the exercise and it is reported whether or
    not it flatters the strategy.

    `selection_stability` is the other tell: the fraction of folds won by the
    single most-frequent config. If the winner keeps changing, the sweep is not
    finding a parameter -- it is finding whatever happened to work last month.
    """
    if not configs:
        raise ValueError("no configs to select from")

    results: list[FoldResult] = []

    for fold in folds:
        train_scores: dict = {}
        for cfg in configs:
            train_scores[cfg] = runner(cfg, fold.train_start, fold.train_end)

        scored = {c: s for c, s in train_scores.items() if s is not None}
        if not scored:
            results.append(FoldResult(fold, None, None, None, train_scores))
            continue

        best = max(scored, key=lambda c: scored[c])
        # The selector has now seen ONLY train. Score it on test.
        oos = runner(best, fold.test_start, fold.test_end)

        results.append(FoldResult(fold, best, scored[best], oos, train_scores))

    scored_folds = [r for r in results if r.out_of_sample_score is not None]
    n = len(scored_folds)

    if n == 0:
        return {
            "n_folds": len(folds),
            "n_scored_folds": 0,
            "verdict": "insufficient_data",
            "folds": [_fold_dict(r) for r in results],
        }

    mean_is = sum(r.in_sample_score for r in scored_folds) / n
    mean_oos = sum(r.out_of_sample_score for r in scored_folds) / n
    winners = [r.chosen_config for r in scored_folds]
    stability = max(winners.count(c) for c in set(winners)) / n
    positive = sum(1 for r in scored_folds if r.out_of_sample_score > 0)

    return {
        "n_folds": len(folds),
        "n_scored_folds": n,
        "mean_in_sample_score": round(mean_is, 4),
        "mean_out_of_sample_score": round(mean_oos, 4),
        # The number that matters. Positive = the in-sample result overstated
        # the edge by this much, on average, per fold.
        "overfit_gap": round(mean_is - mean_oos, 4),
        "positive_oos_folds": positive,
        "positive_oos_fraction": round(positive / n, 4),
        "selection_stability": round(stability, 4),
        "most_selected_config": max(set(winners), key=winners.count),
        "verdict": _verdict(mean_oos, positive, n, stability),
        "folds": [_fold_dict(r) for r in results],
    }


def _verdict(mean_oos: float, positive: int, n: int, stability: float) -> str:
    """Deliberately hard to please, in the same spirit as edge_stats.

    Out-of-sample profitability is necessary but NOT sufficient: one lucky fold
    out of three can carry the mean. We also want most folds positive, and a
    stable winner -- a config that only wins because it happened to top the
    board in a different month each time has not been validated, it has been
    re-fitted.
    """
    if mean_oos <= 0:
        return "no_out_of_sample_edge"
    if n < 3:
        return "too_few_folds"
    if positive / n < 0.5:
        return "carried_by_outlier_folds"
    if stability < 0.5:
        return "unstable_selection"
    return "out_of_sample_edge"


def _fold_dict(r: FoldResult) -> dict:
    return {
        "train": [r.fold.train_start, r.fold.train_end],
        "test": [r.fold.test_start, r.fold.test_end],
        "chosen_config": r.chosen_config,
        "in_sample_score": r.in_sample_score,
        "out_of_sample_score": r.out_of_sample_score,
        "train_scores": r.train_scores,
    }


# ---------------------------------------------------------------------------
# Adapter: run the real penny v2 backtest as the runner
# ---------------------------------------------------------------------------

def penny_v2_runner(
    db_path: str = "/data/cache.db",
    bankroll: float = 2500.0,
    objective: str = "net_pnl",
) -> Runner:
    """A Runner backed by penny_backtest_v2.run_backtest.

    Kept OUT of the pure code above so the honesty machinery can be tested
    without a database -- which matters, because the 60 days of Kite minute
    candles this repo would need do not exist yet, and "we could not test it"
    is how untested statistics code ends up deciding position sizes.
    """
    from penny_backtest_v2 import run_backtest

    def _run(config_name: str, from_date: str, to_date: str) -> Optional[float]:
        result = run_backtest(
            from_date=from_date,
            to_date=to_date,
            config_name=config_name,
            bankroll=bankroll,
            db_path=db_path,
        )
        if getattr(result, "n_trades", 0) == 0:
            return None  # did not trade != broke even
        return float(getattr(result, objective))

    return _run
