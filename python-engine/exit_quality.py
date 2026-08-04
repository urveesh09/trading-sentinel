"""[EXIT-QUALITY 2026-08-05] Where does the money actually go?

THE FINDING THAT MOTIVATED THIS
-------------------------------
The random-control skill test (skill_test.py) run against 1,437 Connors trades
on real NSE daily bars returned something more useful than a pass/fail:

    observed mean R        -0.029
    random control mean R  -0.091
    excess over random     +0.062   (p = 0.005)

Read that carefully. A RANDOM entry, run through Connors' own exit rules, loses
0.091R. The screener beats that by a consistent, replicable margin -- so the
entry selection does carry information. The book still loses money because the
exit rules bleed more than the selection earns.

That reframes the whole problem. "The strategy does not work" would point at
the screener. What the data actually says is that the screener is the healthy
part and the exits are where the money leaks:

    stop      38.9%  mean -1.060R
    t1        26.9%  mean +0.938R      <- every winner capped at ~1R
    t2         7.3%  mean +1.935R
    max_hold  26.9%  mean -0.040R

A 1:1 stop-to-target at a 47% hit rate is arithmetically a losing machine, no
matter how good the entries are. But you cannot fix that by guessing. You need
to know, per trade, how much of the available move was captured -- which is
what this module measures.

WHAT IT MEASURES
----------------
For each closed trade, against the price path it actually lived through:

    give_back_r      the move was ALREADY in hand and we did not keep it
                     (max favourable excursion while held, minus what we took)
    left_on_table_r  the move arrived AFTER we exited, inside a bounded horizon

Both are non-negative and they are different diseases with different cures.
Give-back says the exit is too slow or the trail too loose. Left-on-table says
the exit is too eager -- a hard target cap, or a timer firing on a live thesis.
The 2026-08-04 F&O finding (two profitable positions cut by a time stop that
measured the wrong quantity) is a textbook left_on_table, and it was found by
hand. This makes it a standing number.

THE HONESTY RULES
-----------------
1. `left_on_table_r` is measured over a BOUNDED horizon, never "to the end of
   the data". An unbounded lookahead always finds a higher price eventually and
   would make every exit look premature. The horizon is an argument, and the
   report states it.

2. Max favourable excursion is computed from bar HIGHS, which assumes we could
   have sold at the high. We could not. MFE is therefore an upper bound on what
   was capturable, and give_back_r is an upper bound on the mistake -- labelled
   as such rather than quietly quoted as achievable profit.

3. A trade that stopped out is classified `stopped` and is NOT counted as
   give-back. A stop doing its job is not an exit defect, and lumping it in
   would make the stop look like the problem in every losing book.

Pure functions: no DB, no clock, no config. The caller supplies the path.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Optional, Sequence

#: An excursion smaller than this is noise, not a decision worth grading.
#: 0.25R on a 3% stop is ~0.75% of price -- inside a typical daily range.
DEFAULT_MATERIAL_R = 0.25

#: A trade whose realised R sits at or below this is treated as "the stop did
#: its job". Slightly above -1.0 because costs and gap-throughs push realised R
#: past the nominal stop.
STOPPED_R_CEILING = -0.95


@dataclass(frozen=True)
class Excursion:
    """One closed trade plus the path it lived through.

    Attributes:
        entry: Fill price.
        stop: The INITIAL stop. Defines R; do not pass a trailed stop, or the
            R-multiples stop being comparable across trades.
        exit_price: Realised exit.
        exit_reason: Free-form label ("stop", "t1", "time_stop", ...). Grouped
            in the report so a single bad rule is visible.
        highs: Bar highs from the bar AFTER entry onward, including bars after
            the exit. Index 0 is the first bar the position was live for.
        lows: Bar lows, same indexing and length as `highs`.
        exit_index: Index into highs/lows of the bar the exit happened on.
    """
    entry: float
    stop: float
    exit_price: float
    exit_reason: str
    highs: Sequence[float]
    lows: Sequence[float]
    exit_index: int


def grade(exc: Excursion, *, after_bars: int = 5,
          material_r: float = DEFAULT_MATERIAL_R) -> dict:
    """Grade one exit.

    Args:
        exc: The trade and its path.
        after_bars: How many bars past the exit count as "money left on the
            table". Bounded on purpose -- see honesty rule 1.
        material_r: Excursions below this are ignored as noise.

    Returns:
        A dict with r_realised, mfe_r, mae_r, give_back_r, left_on_table_r and
        a `verdict`. `error` instead when the trade cannot be graded.
    """
    risk = exc.entry - exc.stop
    if not (risk > 0):
        return {"error": f"non-positive risk: entry {exc.entry}, stop {exc.stop}"}
    if len(exc.highs) != len(exc.lows):
        return {"error": "highs and lows must be the same length"}
    if not exc.highs:
        return {"error": "empty path"}
    if not (0 <= exc.exit_index < len(exc.highs)):
        return {"error": f"exit_index {exc.exit_index} outside path of {len(exc.highs)}"}

    r_realised = (exc.exit_price - exc.entry) / risk

    held_highs = exc.highs[: exc.exit_index + 1]
    held_lows = exc.lows[: exc.exit_index + 1]
    mfe_r = (max(held_highs) - exc.entry) / risk
    mae_r = (min(held_lows) - exc.entry) / risk

    after = exc.highs[exc.exit_index + 1: exc.exit_index + 1 + after_bars]
    mfe_after_r = ((max(after) - exc.entry) / risk) if after else r_realised

    stopped = r_realised <= STOPPED_R_CEILING

    # Had it, did not keep it. Never negative: MFE is a max over a window that
    # includes the exit bar, so it cannot be below the realised R... except
    # when the exit filled below the exit bar's own high, which is the normal
    # case. max(0, ...) guards the degenerate rest.
    give_back_r = max(0.0, mfe_r - r_realised)

    # Arrived after we left, within the horizon.
    left_on_table_r = max(0.0, mfe_after_r - r_realised)

    # A stopped trade's realised R is pinned near -1 by the stop itself, so
    # both leak measures above degenerate into "the stop distance" and read
    # ~1.0R on EVERY stop -- which would swamp the totals with a number that
    # describes the risk model rather than any exit mistake. Zero them, and
    # surface the one thing that IS informative separately: how far the price
    # recovered after we were stopped out. A book with a large
    # recovery_after_stop has stops that are too tight; that is a different
    # repair from a target cap, and it deserves its own column.
    recovery_after_stop_r = 0.0
    if stopped:
        recovery_after_stop_r = left_on_table_r
        give_back_r = 0.0
        left_on_table_r = 0.0

    if stopped:
        verdict = "stopped"
    elif give_back_r < material_r and left_on_table_r < material_r:
        verdict = "good_exit"
    elif give_back_r >= left_on_table_r:
        verdict = "gave_back"
    else:
        verdict = "left_on_table"

    return {
        "exit_reason": exc.exit_reason,
        "r_realised": round(r_realised, 4),
        "mfe_r": round(mfe_r, 4),
        "mae_r": round(mae_r, 4),
        "give_back_r": round(give_back_r, 4),
        "left_on_table_r": round(left_on_table_r, 4),
        "recovery_after_stop_r": round(recovery_after_stop_r, 4),
        "capture_ratio": round(r_realised / mfe_r, 4) if mfe_r > 0 else None,
        "verdict": verdict,
        "after_bars": after_bars,
    }


def attribute(excursions: Sequence[Excursion], *, after_bars: int = 5,
              material_r: float = DEFAULT_MATERIAL_R) -> dict:
    """Aggregate grades into a book-level decomposition.

    The headline numbers are totals in R, because that is what tells you which
    leak is worth fixing first: a 0.4R average give-back over 1,400 trades is
    560R and dwarfs anything the entry logic could add.
    """
    graded = [grade(e, after_bars=after_bars, material_r=material_r)
              for e in excursions]
    ok = [g for g in graded if "error" not in g]
    if not ok:
        return {"n": 0, "n_ungradeable": len(graded)}

    by_verdict: dict[str, int] = {}
    for g in ok:
        by_verdict[g["verdict"]] = by_verdict.get(g["verdict"], 0) + 1

    #: Per exit_reason, so a single rule that is bleeding is visible by name.
    by_reason: dict[str, dict] = {}
    for g in ok:
        row = by_reason.setdefault(g["exit_reason"], {
            "n": 0, "total_r": 0.0, "give_back_r": 0.0, "left_on_table_r": 0.0,
            "recovery_after_stop_r": 0.0,
        })
        row["n"] += 1
        row["total_r"] += g["r_realised"]
        row["give_back_r"] += g["give_back_r"]
        row["left_on_table_r"] += g["left_on_table_r"]
        row["recovery_after_stop_r"] += g["recovery_after_stop_r"]
    for row in by_reason.values():
        row["mean_r"] = round(row["total_r"] / row["n"], 4)
        row["total_r"] = round(row["total_r"], 2)
        row["give_back_r"] = round(row["give_back_r"], 2)
        row["left_on_table_r"] = round(row["left_on_table_r"], 2)
        row["recovery_after_stop_r"] = round(row["recovery_after_stop_r"], 2)

    captures = [g["capture_ratio"] for g in ok if g["capture_ratio"] is not None]

    return {
        "n": len(ok),
        "n_ungradeable": len(graded) - len(ok),
        "after_bars": after_bars,
        "total_r": round(sum(g["r_realised"] for g in ok), 2),
        "mean_r": round(statistics.mean(g["r_realised"] for g in ok), 4),
        "total_give_back_r": round(sum(g["give_back_r"] for g in ok), 2),
        "total_left_on_table_r": round(sum(g["left_on_table_r"] for g in ok), 2),
        "mean_give_back_r": round(statistics.mean(g["give_back_r"] for g in ok), 4),
        "mean_left_on_table_r": round(
            statistics.mean(g["left_on_table_r"] for g in ok), 4),
        "total_recovery_after_stop_r": round(
            sum(g["recovery_after_stop_r"] for g in ok), 2),
        "median_capture_ratio": round(statistics.median(captures), 4) if captures else None,
        "by_verdict": by_verdict,
        "by_exit_reason": by_reason,
    }


def format_report(name: str, summary: dict) -> str:
    """Human-readable, and explicit about what the numbers are NOT."""
    if not summary.get("n"):
        return f"EXIT QUALITY — {name}\n\n  no gradeable trades"

    lines = [
        f"EXIT QUALITY — {name}",
        "",
        f"  trades                 {summary['n']}"
        + (f"  ({summary['n_ungradeable']} ungradeable)"
           if summary.get("n_ungradeable") else ""),
        f"  realised               {summary['total_r']:+.1f}R"
        f"   (mean {summary['mean_r']:+.4f})",
        "",
        f"  gave back              {summary['total_give_back_r']:+.1f}R"
        f"   (mean {summary['mean_give_back_r']:.3f})",
        f"  left on table          {summary['total_left_on_table_r']:+.1f}R"
        f"   (mean {summary['mean_left_on_table_r']:.3f},"
        f" {summary['after_bars']}-bar horizon)",
        f"  recovered after stop   {summary['total_recovery_after_stop_r']:+.1f}R"
        "   (stops too tight, if large)",
    ]
    if summary.get("median_capture_ratio") is not None:
        lines.append(
            f"  median capture ratio   {summary['median_capture_ratio']:.2f}"
            "   (realised R / best R while held)")

    lines += ["", "  exits by verdict:"]
    for verdict, n in sorted(summary["by_verdict"].items(), key=lambda kv: -kv[1]):
        lines.append(f"    {verdict:<16} {n:>6}  {n / summary['n'] * 100:5.1f}%")

    lines += ["", "  by exit rule:",
              f"    {'rule':<14}{'n':>7}{'meanR':>9}{'totalR':>10}"
              f"{'gaveBack':>10}{'leftTbl':>10}{'recovStop':>11}"]
    for reason, row in sorted(summary["by_exit_reason"].items(),
                              key=lambda kv: kv[1]["total_r"]):
        lines.append(
            f"    {reason:<14}{row['n']:>7}{row['mean_r']:>+9.3f}"
            f"{row['total_r']:>+10.1f}{row['give_back_r']:>10.1f}"
            f"{row['left_on_table_r']:>10.1f}"
            f"{row['recovery_after_stop_r']:>11.1f}")

    lines += [
        "",
        "  Reading these: 'gave back' is an UPPER BOUND -- it is measured to the",
        "  bar high, and nobody sells at the high. 'left on table' is bounded to",
        f"  {summary['after_bars']} bars after the exit on purpose; an unbounded",
        "  horizon always finds a better price and would condemn every exit.",
        "  Stopped trades are excluded from give-back: a stop doing its job is",
        "  not a defect.",
    ]
    return "\n".join(lines)
