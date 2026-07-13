"""[ROADMAP-5.1 2026-07-13] Real edge statistics.

analytics.py already does the hard, unfashionable part right: it gates on
sample size and labels its confidence instead of quoting a number from four
trades as if it meant something. What it computes, though, is only win rate and
average R -- and those two can describe a losing system perfectly happily. A
90%-win-rate strategy that gives it all back on the tenth trade has a fine win
rate and a fine average R per winner, and still bleeds money.

This module adds the statistics that can actually say "there is an edge here":

    expectancy       -- what one trade is worth, on average (R and rupees)
    profit_factor    -- gross profit / gross loss; <= 1.0 means no edge
    max_drawdown     -- the worst peak-to-trough the operator would have sat
                        through, which is what determines whether a strategy is
                        survivable rather than merely profitable
    bootstrap CI     -- an honest interval around each of the above

Everything here is a PURE function over a list of trades. No DB, no clock, no
config. That is deliberate: these are the numbers used to decide whether to put
more money at risk, so they must be trivially testable and reproducible.

THE HONESTY RULES, which are the point of the module:

1. A statistic from a small sample is not a smaller-but-valid version of the
   real one -- it is noise. Every result carries `n` and a `reliable` flag, and
   the bootstrap interval is what makes the uncertainty impossible to ignore:
   with 12 trades the 95% CI on profit factor is routinely [0.4, 3.1], which
   is the correct answer ("we do not know yet"), not a defect.

2. profit_factor with zero losing trades is NOT infinity, and must never be
   rendered as a large number. It is undefined, and it is reported as None with
   `profit_factor_undefined: True`. A system that has not lost yet has not been
   tested yet.

3. max_drawdown here is a CLOSED-TRADE drawdown: it walks the equity curve of
   realised P&L in close order. It is therefore a LOWER BOUND on what the
   operator actually lived through -- open positions swinging against you never
   appear. It is labelled as such rather than quietly passed off as the real
   drawdown.

4. The bootstrap is SEEDED. A confidence interval that changes every time you
   run the report is a confidence interval nobody will trust.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

# The repo's existing tiering (analytics.strategy_suggestions): >= 20 is "high",
# 5-20 "medium", < 5 "low". `reliable` is deliberately stricter than "we have
# some rows" -- 30 is the conventional floor at which a bootstrap on a
# heavy-tailed P&L distribution starts behaving, and trade P&L is very
# heavy-tailed.
MIN_SAMPLE_FOR_RELIABLE = 30

BOOTSTRAP_ITERATIONS = 2000
BOOTSTRAP_SEED = 20260713  # fixed: a CI that moves between runs is useless

# A resample on which the statistic is undefined (e.g. profit factor on a
# resample that happens to contain no losing trade) cannot simply be dropped and
# the rest averaged. Dropping them CONDITIONS the distribution on "this resample
# contained a loser", which biases the interval -- and the bias is worst exactly
# when the sample is thinnest and the operator is most likely to over-read the
# result.
#
# Concretely: with 1 loser in 21 trades, ~64% of resamples contain the loser. A
# 50% threshold would happily report an interval built by throwing away the
# other 36%. So require the statistic to be defined on the overwhelming majority
# of resamples, or report nothing at all.
BOOTSTRAP_MIN_DEFINED_FRAC = 0.95


@dataclass(frozen=True)
class Trade:
    """One closed trade. `r` may be None (older rows predate r_multiple)."""
    pnl: float
    r: Optional[float] = None


def _rs(trades: Sequence[Trade]) -> list[float]:
    return [t.r for t in trades if t.r is not None]


# ---------------------------------------------------------------------------
# Point statistics
# ---------------------------------------------------------------------------

def expectancy_r(trades: Sequence[Trade]) -> Optional[float]:
    """Expected R per trade. This IS the mean of R -- the textbook
    `win_rate * avg_win - loss_rate * avg_loss` expands to exactly that, and
    computing it the long way only invites a sign error."""
    rs = _rs(trades)
    return sum(rs) / len(rs) if rs else None


def expectancy_rupees(trades: Sequence[Trade]) -> Optional[float]:
    """Expected rupees per trade. Kept separate from expectancy_r on purpose:
    R is position-size-independent, rupees are not, and conflating them is how
    a strategy that is fine in R terms turns out to be worthless after the
    per-stock cap flattens its sizing (see the PENNY_PER_STOCK_CAP note in
    config -- regime sizing is a no-op in practice, so R and rupees diverge)."""
    if not trades:
        return None
    return sum(t.pnl for t in trades) / len(trades)


def profit_factor(trades: Sequence[Trade]) -> tuple[Optional[float], bool]:
    """gross profit / gross loss.

    Returns (value, undefined). <= 1.0 means the strategy loses money, however
    good the win rate looks.

    With no losing trades the ratio is UNDEFINED, not infinite: returns
    (None, True). Rendering that as a huge number -- or worse, as `inf` -- would
    make an untested strategy look like the best one in the book, which is the
    exact opposite of what the number is for.
    """
    gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss = -sum(t.pnl for t in trades if t.pnl < 0)  # positive magnitude
    if gross_loss == 0:
        return None, True
    return gross_profit / gross_loss, False


def max_drawdown(trades: Sequence[Trade]) -> dict:
    """Worst peak-to-trough on the CLOSED-TRADE equity curve.

    `trades` must already be in close order -- this function will not sort,
    because it cannot know which timestamp you meant, and silently sorting by
    the wrong key would produce a plausible, wrong number.

    Returns absolute rupees and the fraction of the running peak. The fraction
    is None while the peak is <= 0 (you cannot draw down 30% of nothing).

    LOWER BOUND, by construction: an open position swinging hard against you
    and recovering never touches this curve. See the module docstring.
    """
    equity = 0.0
    peak = 0.0
    worst_abs = 0.0
    worst_pct: Optional[float] = None

    for t in trades:
        equity += t.pnl
        peak = max(peak, equity)
        dd = peak - equity
        if dd > worst_abs:
            worst_abs = dd
            worst_pct = (dd / peak) if peak > 0 else None

    return {
        "max_drawdown_rupees": round(worst_abs, 2),
        "max_drawdown_pct_of_peak": round(worst_pct, 4) if worst_pct is not None else None,
        "closed_trade_basis": True,  # never let a caller forget rule 3
    }


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def bootstrap_ci(
    trades: Sequence[Trade],
    statistic: Callable[[Sequence[Trade]], Optional[float]],
    iterations: int = BOOTSTRAP_ITERATIONS,
    confidence: float = 0.95,
    seed: int = BOOTSTRAP_SEED,
) -> Optional[tuple[float, float]]:
    """Percentile bootstrap CI for any of the statistics above.

    Resample the trades WITH REPLACEMENT `iterations` times, recompute the
    statistic, and take the empirical percentiles. This makes no assumption of
    normality, which matters: trade P&L is heavy-tailed and skewed, so a
    textbook mean +/- 1.96*SE interval is quietly wrong on exactly the data we
    have.

    Returns None when the sample is too small to resample meaningfully (< 2) or
    the statistic is undefined on the resamples.

    A WIDE interval is the honest output, not a failure. If the 95% CI on
    expectancy straddles zero, the correct reading is "no demonstrated edge" --
    regardless of how good the point estimate looks.
    """
    if len(trades) < 2:
        return None

    rng = random.Random(seed)
    n = len(trades)
    vals: list[float] = []

    for _ in range(iterations):
        sample = [trades[rng.randrange(n)] for _ in range(n)]
        v = statistic(sample)
        if v is not None:
            vals.append(v)

    if len(vals) < BOOTSTRAP_MIN_DEFINED_FRAC * iterations:
        # The statistic was undefined on too many resamples -- e.g. profit
        # factor on a book with a single loser, where a third of resamples
        # contain no loser at all. Keeping only the resamples that "worked"
        # conditions the distribution and biases the interval. Report nothing.
        return None

    vals.sort()
    tail = (1.0 - confidence) / 2.0
    lo = vals[int(tail * len(vals))]
    hi = vals[min(int((1.0 - tail) * len(vals)), len(vals) - 1)]
    return round(lo, 4), round(hi, 4)


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------

def edge_report(trades: Sequence[Trade]) -> dict:
    """Everything above, in one dict, with the uncertainty attached.

    `trades` must be in close order (max_drawdown depends on it).

    The `verdict` is deliberately conservative and is the whole point of the
    module. An edge is only claimed when the 95% bootstrap CI on expectancy is
    ENTIRELY above zero. A good-looking point estimate with a CI that straddles
    zero is reported as "not demonstrated" -- because that is what it is.
    """
    n = len(trades)
    if n == 0:
        return {"n": 0, "reliable": False, "verdict": "no_data"}

    pf, pf_undefined = profit_factor(trades)
    exp_r = expectancy_r(trades)
    exp_rs = expectancy_rupees(trades)

    ci_exp_r = bootstrap_ci(trades, expectancy_r)
    ci_exp_rs = bootstrap_ci(trades, expectancy_rupees)
    ci_pf = bootstrap_ci(trades, lambda ts: profit_factor(ts)[0])

    wins = [t for t in trades if t.pnl > 0]

    if ci_exp_rs is None:
        verdict = "insufficient_data"
    elif ci_exp_rs[0] > 0:
        verdict = "edge_demonstrated"
    elif ci_exp_rs[1] < 0:
        verdict = "negative_edge"
    else:
        # The interval straddles zero. This is the common case early on, and
        # calling it anything else would be lying.
        verdict = "not_demonstrated"

    return {
        "n": n,
        "reliable": n >= MIN_SAMPLE_FOR_RELIABLE,
        "min_sample_for_reliable": MIN_SAMPLE_FOR_RELIABLE,
        "win_rate": round(len(wins) / n, 4),
        "expectancy_r": round(exp_r, 4) if exp_r is not None else None,
        "expectancy_r_ci95": ci_exp_r,
        "expectancy_rupees": round(exp_rs, 2) if exp_rs is not None else None,
        "expectancy_rupees_ci95": ci_exp_rs,
        "profit_factor": round(pf, 3) if pf is not None else None,
        "profit_factor_ci95": ci_pf,
        "profit_factor_undefined": pf_undefined,
        **max_drawdown(trades),
        "verdict": verdict,
    }
