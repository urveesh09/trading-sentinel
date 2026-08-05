"""[SKILL 2026-08-05] Does the ENTRY SELECTION have skill, or is it drift?

THE QUESTION THIS ANSWERS, AND WHY IT IS NOT THE ONE WE WERE ASKING
-------------------------------------------------------------------
`edge_stats.edge_report` asks "is expectancy greater than ZERO?" and answers it
honestly with a bootstrap CI. That is the right question for "will this book
make money", but it is the WRONG question for "does this screener know
anything", and the difference is the whole reason every parameter in this system
is suspect.

Consider a long-only book run over a sample where the market drifted up. Buy a
random NSE mid-cap every Tuesday, exit on the same rules, and you will show
positive expectancy. A bootstrap CI entirely above zero would call that an edge.
It is not an edge -- it is beta with extra steps, and it will hand the money
back the moment the drift reverses.

The fix is to stop benchmarking against zero and start benchmarking against a
SAME-UNIVERSE RANDOM CONTROL: take the days the strategy actually fired, pick
random tickers from the same eligible universe on those same days, apply the
IDENTICAL exit rules, and ask whether the real selection beat the coin flip.
Everything shared -- market drift, the exit logic, the cost model, the sample
period, the trade count -- cancels in the comparison. What is left is selection.

WHERE THE IDEA COMES FROM
-------------------------
HKUDS/Vibe-Trading's `bench_runner_strict` (MIT) makes the same argument for
cross-sectional factors, citing an A-share audit in which every one of twelve
factors passed a raw IC test at some parameter setting and only ONE survived a
parallel random control. It also cites Harvey, Liu & Zhu (2016), "...and the
Cross-Section of Expected Returns": once you correct for how many
configurations were tried, the |t| bar for believing a factor is ~3.5, not 2.0.
Both points apply to us directly. `tools/connors_backtest.py --sweep` tries a
dozen configurations and reports the best; that is exactly the multiple-testing
setting Harvey-Liu-Zhu is about.

THE FOUR VERDICTS
-----------------
Pass/fail is too coarse, so we bucket like the strict bench does:

  confirmed_skill  beats the control on the full sample, and -- when an
                   out-of-sample split is supplied -- independently in BOTH
                   halves.
  train_only       beats it in-sample, decays into the noise band out-of-sample.
  reversed         either significantly WORSE than random on the full sample, or
                   it flips sign out-of-sample. Filed here rather than under
                   train_only deliberately: a sign flip is the single most
                   diagnostic evidence that the in-sample result was an
                   artefact, and it deserves to be visible as such.
  noise            indistinguishable from picking at random.

WHAT THIS STILL CANNOT DO
-------------------------
It cannot manufacture sample size. With nine trades the control distribution is
wide and almost nothing will clear the bar -- which IS the finding, not a defect
of the test. It also inherits every assumption of the simulator it is handed:
if that simulator has lookahead, so does the control, and the comparison stays
valid while both absolute numbers stay wrong.

Pure functions only: no DB, no clock, no config. The caller injects the
universe and the simulator.
"""
from __future__ import annotations

import random
import statistics
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Sequence

#: Default replication count. 500 puts the resolution of the empirical p-value
#: at 0.002, far finer than the sample sizes we have.
DEFAULT_REPLICATIONS = 500

#: Fixed seed: a significance verdict that moves between runs is not a verdict.
DEFAULT_SEED = 20260805

#: The Harvey-Liu-Zhu multiple-testing bar. Used when the caller declares how
#: many configurations were searched; see `skill_threshold`.
HLZ_T_THRESHOLD = 3.5

#: The conventional single-hypothesis bar, correct only for a PRE-REGISTERED
#: test of one configuration.
SINGLE_TEST_T_THRESHOLD = 2.0


@dataclass(frozen=True)
class TradeSpec:
    """One trade the strategy actually took.

    Attributes:
        ticker: Instrument traded.
        day: The decision day. Opaque to this module -- whatever key the
            caller's `candidates_on_day` and `simulate` agree on (an ISO date,
            a bar index, ...). It is only ever used for lookup and grouping.
        r: Realised R-multiple, net of costs.
    """
    ticker: str
    day: object
    r: float


def skill_threshold(configurations_tried: int = 1) -> float:
    """The |t| a result must clear to be believed.

    One pre-registered configuration gets the textbook 2.0. Anything found by
    searching gets the Harvey-Liu-Zhu 3.5, because the best of N noisy
    configurations looks significant at 2.0 by construction.

    Args:
        configurations_tried: How many settings were evaluated before this one
            was selected. `--sweep` tries a dozen; be honest here.
    """
    if configurations_tried <= 1:
        return SINGLE_TEST_T_THRESHOLD
    return HLZ_T_THRESHOLD


def run_control(
    actual: Sequence[TradeSpec],
    candidates_on_day: Callable[[object], Sequence[str]],
    simulate: Callable[[str, object], Optional[float]],
    *,
    replications: int = DEFAULT_REPLICATIONS,
    seed: int = DEFAULT_SEED,
    exclude_actual_ticker: bool = True,
) -> dict:
    """Compare the real selection against random picks on the same days.

    For each replication we redraw one random ticker per actual trade, from the
    universe eligible on THAT trade's day, and simulate it with the caller's
    exit rules. The result is a distribution of "mean R if you had no skill".

    Args:
        actual: The trades the strategy really took.
        candidates_on_day: day -> tickers that were eligible to be bought that
            day. This must be the SAME investability filter the strategy faced
            (listed, liquid, enough history) but WITHOUT the strategy's own
            entry signal -- otherwise the control is not random, it is the
            strategy again.
        simulate: (ticker, day) -> realised R for a hypothetical entry, or None
            when the trade could not be simulated (missing bars, no exit
            window). Must apply the same stop/target/hold/cost rules as the
            real book.
        replications: Control samples to draw.
        seed: Fixed for reproducibility.
        exclude_actual_ticker: Drop the ticker the strategy actually chose from
            that day's candidate pool. Default True. Leaving it in lets the
            control occasionally re-draw the real trade, which pulls the null
            toward the observed value and makes the test conservative in a way
            that is hard to reason about.

    Returns:
        A dict with the observed and control means, the empirical p-value, a
        paired t-statistic, and diagnostics. `error` is set instead when the
        test could not be run.
    """
    if len(actual) < 3:
        return {"error": f"need at least 3 trades, got {len(actual)}",
                "n_trades": len(actual)}
    if replications < 1:
        return {"error": f"replications must be >= 1, got {replications}"}

    observed_mean = statistics.mean(t.r for t in actual)
    rng = random.Random(seed)

    control_means: list[float] = []
    #: Per-replication mean of (control R) so we can pair against the observed
    #: mean. We also track how often a replication could not be filled, because
    #: a control that keeps failing to simulate is not a null distribution --
    #: it is a bug in `simulate` or a too-narrow universe.
    unfilled_draws = 0
    total_draws = 0

    for _ in range(replications):
        sample: list[float] = []
        for trade in actual:
            pool = list(candidates_on_day(trade.day))
            if exclude_actual_ticker:
                pool = [t for t in pool if t != trade.ticker]
            total_draws += 1
            if not pool:
                unfilled_draws += 1
                continue
            r = simulate(rng.choice(pool), trade.day)
            if r is None:
                unfilled_draws += 1
                continue
            sample.append(r)
        if sample:
            control_means.append(statistics.mean(sample))

    if len(control_means) < max(10, replications // 10):
        return {
            "error": (
                f"only {len(control_means)}/{replications} control replications "
                "could be simulated; the candidate universe or the simulator is "
                "too sparse for this test to mean anything"
            ),
            "n_trades": len(actual),
            "unfilled_draw_rate": round(unfilled_draws / total_draws, 4) if total_draws else None,
        }

    control_mean = statistics.mean(control_means)
    control_sd = statistics.pstdev(control_means) if len(control_means) > 1 else 0.0

    # Empirical one-sided p-value: how often does no-skill match or beat us?
    # The +1 in numerator and denominator is the standard finite-sample
    # correction -- it keeps p from ever being exactly 0, which would claim
    # more certainty than `replications` draws can support.
    at_least_as_good = sum(1 for m in control_means if m >= observed_mean)
    p_value = (at_least_as_good + 1) / (len(control_means) + 1)

    # Standardised skill: how many control-distribution SDs above the null the
    # observed mean sits. Directly comparable to the Harvey-Liu-Zhu bar.
    skill_t = ((observed_mean - control_mean) / control_sd) if control_sd > 0 else 0.0

    return {
        "n_trades": len(actual),
        "observed_mean_r": round(observed_mean, 4),
        "control_mean_r": round(control_mean, 4),
        "control_sd": round(control_sd, 4),
        "control_p5": round(_percentile(control_means, 5), 4),
        "control_p95": round(_percentile(control_means, 95), 4),
        "excess_r": round(observed_mean - control_mean, 4),
        "p_value": round(p_value, 4),
        "skill_t": round(skill_t, 3),
        "replications_used": len(control_means),
        "unfilled_draw_rate": round(unfilled_draws / total_draws, 4) if total_draws else 0.0,
    }


def categorise(
    full: dict,
    train: Optional[dict] = None,
    test: Optional[dict] = None,
    *,
    t_threshold: float = SINGLE_TEST_T_THRESHOLD,
    min_trades: int = 20,
) -> str:
    """Bucket a control result into one of the four verdicts.

    Args:
        full: `run_control` output over the whole sample.
        train / test: optional `run_control` outputs over an out-of-sample
            split. Both must be present for the split to be considered.
        t_threshold: the bar from `skill_threshold`.
        min_trades: below this the answer is "noise" regardless of the numbers.
            Not a statistical constant -- a floor that stops a lucky handful of
            trades from ever being reported as a green light.

    Returns:
        "confirmed_skill" | "train_only" | "reversed" | "noise"
    """
    if full.get("error") or full.get("n_trades", 0) < min_trades:
        return "noise"

    t_full = full.get("skill_t", 0.0)

    # Significantly WORSE than random. Real information, inverted -- and worth
    # distinguishing from noise, because a reliably bad selector is a good
    # selector with the sign flipped.
    if t_full <= -t_threshold:
        return "reversed"

    if t_full < t_threshold:
        return "noise"

    # Full sample clears the bar. Without a split, that is all we can say.
    if not train or not test or train.get("error") or test.get("error"):
        return "confirmed_skill"

    t_train = train.get("skill_t", 0.0)
    t_test = test.get("skill_t", 0.0)

    # An out-of-sample SIGN FLIP is the strongest evidence the in-sample result
    # was an artefact. Filed as reversed, not train_only, so it cannot be read
    # as benign decay.
    if t_test <= -t_threshold:
        return "reversed"
    if t_train < t_threshold:
        # The full sample only cleared the bar on the strength of the test
        # half. That is not a train/test validation of anything.
        return "noise"
    if t_test >= t_threshold:
        return "confirmed_skill"
    return "train_only"


def format_report(
    name: str,
    full: dict,
    train: Optional[dict] = None,
    test: Optional[dict] = None,
    *,
    configurations_tried: int = 1,
    min_trades: int = 20,
) -> str:
    """Human-readable summary, including what the verdict permits."""
    threshold = skill_threshold(configurations_tried)
    verdict = categorise(full, train, test,
                         t_threshold=threshold, min_trades=min_trades)

    lines = [f"SKILL TEST — {name}", ""]
    if full.get("error"):
        lines.append(f"  could not run: {full['error']}")
        return "\n".join(lines)

    lines += [
        f"  trades                {full['n_trades']}",
        f"  observed mean R       {full['observed_mean_r']:+.4f}",
        f"  random control mean R {full['control_mean_r']:+.4f}"
        f"   (5-95%: {full['control_p5']:+.3f} to {full['control_p95']:+.3f})",
        f"  excess over random    {full['excess_r']:+.4f}",
        f"  skill t               {full['skill_t']:+.2f}   (bar: {threshold:.1f})",
        f"  p-value               {full['p_value']:.4f}",
    ]
    if train and test and not train.get("error") and not test.get("error"):
        lines += [
            f"  train skill t         {train['skill_t']:+.2f}  ({train['n_trades']} trades)",
            f"  test  skill t         {test['skill_t']:+.2f}  ({test['n_trades']} trades)",
        ]
    if full.get("unfilled_draw_rate"):
        lines.append(f"  unfilled control draws {full['unfilled_draw_rate']:.1%}")

    lines += ["", f"  VERDICT: {verdict}", "", "  " + _verdict_meaning(verdict)]
    if configurations_tried > 1:
        lines.append(
            f"  ({configurations_tried} configurations were searched, so the bar is "
            f"the Harvey-Liu-Zhu {HLZ_T_THRESHOLD}, not {SINGLE_TEST_T_THRESHOLD}.)"
        )
    return "\n".join(lines)


def _verdict_meaning(verdict: str) -> str:
    return {
        "confirmed_skill": "The selection beat a same-universe coin flip. This is "
                           "the only verdict that supports risking real money, and "
                           "it still says nothing about size.",
        "train_only": "Beat the control in-sample, decayed out-of-sample. Treat as "
                      "unproven: this is what curve-fitting looks like.",
        "reversed": "Significantly WORSE than random, or it flipped sign out-of-"
                    "sample. Do not trade it. Worth understanding — a reliably "
                    "inverted signal is information.",
        "noise": "Indistinguishable from picking at random on the same days. "
                 "Usually means not enough trades yet, not that the idea is dead.",
    }.get(verdict, "")


def _percentile(values: Sequence[float], pct: float) -> float:
    """Nearest-rank percentile. Plain stdlib: matches edge_stats' style and
    avoids pulling numpy into a module the engine imports."""
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round(pct / 100.0 * (len(ordered) - 1)))
    return ordered[max(0, min(idx, len(ordered) - 1))]


def split_by_day(
    trades: Iterable[TradeSpec], fraction: float = 0.7
) -> tuple[list[TradeSpec], list[TradeSpec]]:
    """Chronological train/test split on the trade's day key.

    Chronological, never random: a random split leaks the future into the
    training half, which is the mistake that makes almost every published
    strategy look better than it is.
    """
    ordered = sorted(trades, key=lambda t: str(t.day))
    cut = int(len(ordered) * fraction)
    return ordered[:cut], ordered[cut:]
