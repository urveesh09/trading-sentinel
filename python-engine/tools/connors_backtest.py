"""
Walk-forward backtest for the EDGE / Connors RSI-2 book.

WHY THIS EXISTS
---------------
The operator's standing rule is that real capital does not get risked without
evidence the strategy will not lose. Until 2026-08-04 no such evidence could
exist for any book in this system:

  * momentum and F&O are intraday, and clear_intraday_cache deleted everything
    older than yesterday every night (fixed -- see INTRADAY_RETENTION_DAYS);
  * the daily books had history, but nothing that replayed the shipped gates
    against it. Every parameter was therefore tuned in-sample on the handful
    of trades the operator happened to take.

Connors is the one book that could be evaluated the day this was written: it is
pure daily-close logic and ohlcv_cache holds daily bars. It is also the only
live book that has ever been net positive, so it is the natural first candidate
for real money -- which makes "does it actually have an edge" the question that
has to be answered before anything is armed.

WHAT IT MEASURES HONESTLY
-------------------------
  * No lookahead. The signal is computed from closes THROUGH day i; the entry
    is day i+1's OPEN, the first price actually transactable after the decision.
  * Stop-before-target within a bar. When a daily bar's range spans both, the
    loss is assumed -- daily bars cannot tell us which came first, and the
    optimistic assumption is how backtests lie.
  * Real Zerodha CNC costs on every trade, via the same calc_zerodha_costs the
    live book uses.
  * No overlapping positions in one ticker.
  * Sizing is a constant. Share count does not change an R-multiple, and
    holding it fixed keeps the study about the SIGNAL rather than the
    position-sizing rules.

WHAT IT CANNOT TELL YOU
-----------------------
Significance. At the shipped gates this produces a single-digit number of
trades over the available history, and a good mean R across nine trades is
noise. The `t` column is printed for exactly that reason: treat anything under
~2 as "no answer yet", not as a green light. Depth accumulates now that
DAILY_HISTORY_DAYS is a rolling window; re-run this then.

USAGE
-----
    docker exec -e PYTHONPATH=/app:/app/.venv/lib/python3.11/site-packages \\
        python-engine python /app/tools/connors_backtest.py [--sweep]

--sweep varies the RSI(2) buy threshold and toggles the rising-confirmation
gate, which is the comparison that matters: it shows both how many signals a
configuration produces AND whether they make money. A gate is only worth
loosening if what it excluded has positive expectancy.
"""
from __future__ import annotations

import argparse
import sqlite3
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, "/app")

from config import settings                      # noqa: E402
from engine import calc_zerodha_costs            # noqa: E402
from penny_engine_connors import _rsi_2, _sma    # noqa: E402

# The engine's history floor is 250 bars (SMA-200 + warm-up). A little headroom
# keeps the first evaluated bar away from the boundary.
MIN_BARS = 260
SHARES = 100

Bar = Tuple[str, float, float, float, float, float]   # date, o, h, l, c, v


def load_bars(db_path: str, min_len: int = MIN_BARS + 5) -> Dict[str, List[Bar]]:
    """Daily OHLCV per ticker, ordered, with unusable rows dropped."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    bars: Dict[str, List[Bar]] = defaultdict(list)
    for tkr, d, o, h, l, c, v in conn.execute(
        "SELECT ticker, date, open, high, low, close, volume FROM ohlcv_cache "
        "WHERE close IS NOT NULL AND open IS NOT NULL ORDER BY ticker, date"
    ):
        try:
            bars[tkr].append((d, float(o), float(h), float(l), float(c), float(v or 0)))
        except (TypeError, ValueError):
            continue          # a few rows carry non-numeric prices
    return {t: b for t, b in bars.items() if len(b) >= min_len}


def _entry_signal(hist: List[float], vols: List[float], i: int,
                  rsi_buy: float, require_rising: bool) -> Optional[str]:
    """Mirror of evaluate_connors_entry's gate stack, in gate order.

    Reimplemented rather than called because the sweep has to vary two gates
    that the production function reads from settings. It is pinned to the
    production behaviour by test_connors_backtest.py, which asserts that at
    the shipped configuration this agrees with evaluate_connors_entry.
    Returns a reject reason, or None when the signal fires.
    """
    last = hist[-1]
    sma_200, sma_50 = _sma(hist, 200), _sma(hist, 50)
    if sma_200 is None or sma_50 is None:
        return "SMA not available"
    if last <= sma_200:
        return "below 200 SMA"
    if last <= sma_50:
        return "below 50 SMA"

    rsi = _rsi_2(hist)
    if rsi >= rsi_buy:
        return "RSI(2) not below buy threshold"
    if require_rising and not (rsi > _rsi_2(hist[:-1]) > _rsi_2(hist[:-2])):
        return "RSI not rising for 2 bars"

    avg20 = sum(vols[i - 19: i + 1]) / 20 if i >= 19 else 0.0
    if avg20 <= 0 or vols[i] < 0.5 * avg20:
        return "volume too low"
    return None


def last_entry_index(b: Sequence[Bar], max_hold: int) -> int:
    """First index too late to enter: entry needs bar i+1, the hold needs
    max_hold bars after that. See the long note in `simulate`."""
    return len(b) - 1 - max_hold


@dataclass(frozen=True)
class ExitPolicy:
    """How a position is managed after entry.

    [EXIT-SWEEP 2026-08-05] The exit-quality run over 1,437 real trades found
    both exit diseases at once: the hard t1 cap took 387 winners at exactly
    +1.000R while leaving 512R inside a 5-bar horizon, and the 3% stop was
    breached 559 times with the price recovering 1.88R on average afterwards.
    Median capture ratio was 0.16 -- we kept a sixth of the move we had.

    Neither number licenses a guess at better settings; they license a
    MEASUREMENT. This type makes the exit rule a variable so alternatives can
    be walked forward on the same bars, with the same entries, and judged by
    the same random control.

    Attributes:
        stop_pct: Initial stop, as a fraction below entry. Defines R.
        t1_pct / t2_pct: Hard target rungs. `t1_pct` is ignored when
            `scale_at_t1` is False and `trail_atr_mult` is set.
        max_hold: Bars before the position is closed at the close.
        trail_pct: When set, after the position closes a bar above
            `trail_arm_pct`, the stop ratchets to (highest high seen) *
            (1 - trail_pct) and never moves down. This is what lets a winner
            run past t1 instead of being capped there.
        trail_arm_pct: Profit needed before the trail engages. Arming late
            keeps the initial stop in place through the noisy first move.
        scale_at_t1: Take half off at t1 and trail the rest -- the momentum
            book's shipped pattern (MOMENTUM_USE_SCALE_OUT), applied here.
    """
    stop_pct: float
    t1_pct: float
    t2_pct: float
    max_hold: int
    trail_pct: Optional[float] = None
    trail_arm_pct: float = 0.0
    scale_at_t1: bool = False
    label: str = ""


def shipped_policy() -> ExitPolicy:
    """Exactly what the live book does today: hard rungs, no trail."""
    return ExitPolicy(
        stop_pct=settings.PENNY_CONNORS_STOP_PCT,
        t1_pct=settings.PENNY_CONNORS_T1_PCT,
        t2_pct=settings.PENNY_CONNORS_T2_PCT,
        max_hold=settings.PENNY_CONNORS_MAX_HOLD_DAYS,
        label="shipped",
    )


def simulate_trade(b: Sequence[Bar], i: int, max_hold: int,
                   policy: Optional[ExitPolicy] = None) -> Optional[dict]:
    """Exit rules for ONE hypothetical entry decided on bar `i`.

    Factored out of `simulate` so the random control in `skill_control` runs
    the IDENTICAL exit logic, cost model and truncation bound. If the control
    were allowed a rule the real book is denied -- most importantly the
    arbitrary last-cached-close exit -- the comparison would measure the
    difference in rules rather than the difference in selection.

    `policy` defaults to the shipped configuration, so every existing caller
    and test keeps its exact behaviour.

    Returns None when the bar cannot support a full trade.
    """
    p = policy or shipped_policy()
    hold = p.max_hold if policy is not None else max_hold
    if i < 0 or i >= last_entry_index(b, hold):
        return None
    entry = b[i + 1][1]                       # next bar's OPEN
    if entry <= 0:
        return None

    stop = entry * (1 - p.stop_pct)
    t1 = entry * (1 + p.t1_pct)
    t2 = entry * (1 + p.t2_pct)
    risk_ps = entry - stop
    if risk_ps <= 0:
        return None

    # Scale-out bookkeeping: `booked_r` accumulates R already realised on the
    # half taken off at t1, and `live_frac` is what remains exposed.
    booked_r = 0.0
    live_frac = 1.0
    trail_stop = stop
    peak_high = entry
    exit_px: Optional[float] = None
    exit_reason = ""

    for k in range(1, hold + 1):
        j = i + k
        if j >= len(b):
            break
        _d, _o, high, low, _c, _v = b[j]

        # Stop first: a daily bar cannot order intrabar events, so assume
        # the loss when both levels are inside the range.
        if low <= trail_stop:
            exit_px = trail_stop
            exit_reason = "stop" if trail_stop <= stop else "trail_stop"
            break

        if p.scale_at_t1 and live_frac == 1.0 and high >= t1:
            # Half off at t1; the rest rides the trail.
            booked_r += 0.5 * (t1 - entry) / risk_ps
            live_frac = 0.5
            exit_reason = "scaled_t1"

        if p.trail_pct is None:
            # Hard-rung behaviour, unchanged from the shipped book.
            if high >= t2:
                exit_px, exit_reason = t2, "t2"
                break
            if not p.scale_at_t1 and high >= t1:
                exit_px, exit_reason = t1, "t1"
                break
        else:
            peak_high = max(peak_high, high)
            if peak_high >= entry * (1 + p.trail_arm_pct):
                trail_stop = max(trail_stop, peak_high * (1 - p.trail_pct))

    if exit_px is None:
        j = min(i + hold, len(b) - 1)
        exit_px = b[j][4]
        exit_reason = exit_reason or "max_hold"
        if exit_reason == "scaled_t1":
            exit_reason = "scaled_then_max_hold"

    # Costs are charged on the full round trip. With a scale-out the exit is
    # split across two fills, so the cost model is applied to each leg at its
    # own size rather than pretending one fill happened.
    if live_frac < 1.0:
        shares_first = int(SHARES * 0.5)
        shares_rest = SHARES - shares_first
        gross = (t1 - entry) * shares_first + (exit_px - entry) * shares_rest
        costs = (calc_zerodha_costs(entry, t1, shares_first, is_intraday=False)
                 + calc_zerodha_costs(entry, exit_px, shares_rest, is_intraday=False))
    else:
        gross = (exit_px - entry) * SHARES
        costs = calc_zerodha_costs(entry, exit_px, SHARES, is_intraday=False)
    pnl = gross - costs

    return {
        "date": b[i][0], "entry": entry, "exit": exit_px,
        "reason": exit_reason, "pnl": pnl,
        "r_net": pnl / (risk_ps * SHARES),
    }


def simulate(bars: Dict[str, List[Bar]], rsi_buy: float,
             require_rising: bool,
             policy: Optional[ExitPolicy] = None,
             ) -> Tuple[List[dict], Dict[str, int], int]:
    trades: List[dict] = []
    rejects: Dict[str, int] = defaultdict(int)
    evaluated = 0
    max_hold = policy.max_hold if policy else settings.PENNY_CONNORS_MAX_HOLD_DAYS

    for tkr, b in bars.items():
        closes = [x[4] for x in b]
        vols = [x[5] for x in b]
        i = MIN_BARS
        # Stop early enough that EVERY simulated trade gets a full exit window:
        # entry needs bar i+1, and the hold needs max_hold bars after that.
        #
        # Admitting truncated trades is not a rounding detail. A trade with no
        # room left falls through to the max_hold branch and exits at whatever
        # the final cached close happens to be -- an arbitrary price, not an
        # exit rule. Over a period when the market drifted up, those arbitrary
        # exits were systematically favourable: with the truncated tail
        # included, the no-confirmation configuration reported mean R +0.009
        # and PF 1.06 (a profitable strategy); excluding it, the same
        # configuration is mean R -0.037 and PF 0.93 (a losing one). The sign
        # of the answer depended entirely on this bound.
        last_entry = last_entry_index(b, max_hold)
        while i < last_entry:
            evaluated += 1
            reason = _entry_signal(closes[max(0, i - 300): i + 1], vols, i,
                                   rsi_buy, require_rising)
            if reason is not None:
                rejects[reason] += 1
                i += 1
                continue

            trade = simulate_trade(b, i, max_hold, policy)
            if trade is None:
                i += 1
                continue
            trades.append({"ticker": tkr, **trade})
            i += max_hold                              # no overlapping positions

    return trades, dict(rejects), evaluated


def stats(trades: List[dict]) -> dict:
    if not trades:
        return {"n": 0}
    pnl = [t["pnl"] for t in trades]
    rn = [t["r_net"] for t in trades]
    wins = [p for p in pnl if p > 0]
    losses = [p for p in pnl if p <= 0]
    gross_w, gross_l = sum(wins), abs(sum(losses))
    sd = statistics.pstdev(rn) if len(rn) > 1 else 0.0
    se = sd / len(rn) ** 0.5 if rn else 0.0
    return {
        "n": len(trades),
        "win_pct": len(wins) / len(pnl) * 100,
        "mean_r": statistics.mean(rn),
        "total_pnl": sum(pnl),
        "profit_factor": (gross_w / gross_l) if gross_l else float("inf"),
        "t_stat": (statistics.mean(rn) / se) if se else 0.0,
    }


def skill_control(bars: Dict[str, List[Bar]], trades: List[dict],
                  *, label: str = "Connors RSI-2 entry selection",
                  replications: int = 300, configurations_tried: int = 1) -> str:
    """Ask whether the SELECTION beat a coin flip on the same days.

    `stats()` above answers "did this make money", which over a rising sample a
    long-only book answers yes to whether or not it knows anything. This asks
    the question that decides real money: on the days Connors fired, would
    picking a random eligible NSE name and applying the IDENTICAL exit rules
    have done just as well?

    The candidate universe for a day is every ticker that had enough history to
    be evaluated on that day AND enough forward bars for a full exit window --
    the same investability constraints the real book faced, minus the entry
    signal itself.
    """
    from skill_test import TradeSpec, format_report, run_control, split_by_day

    max_hold = settings.PENNY_CONNORS_MAX_HOLD_DAYS

    # date -> index, per ticker, plus the tradable index window.
    index_of: Dict[str, Dict[str, int]] = {}
    for tkr, b in bars.items():
        last = last_entry_index(b, max_hold)
        index_of[tkr] = {b[i][0]: i for i in range(MIN_BARS, max(MIN_BARS, last))}

    by_day: Dict[str, List[str]] = defaultdict(list)
    for tkr, table in index_of.items():
        for day in table:
            by_day[day].append(tkr)

    def candidates_on_day(day):
        return by_day.get(day, ())

    def simulate_one(ticker, day):
        i = index_of.get(ticker, {}).get(day)
        if i is None:
            return None
        t = simulate_trade(bars[ticker], i, max_hold)
        return None if t is None else t["r_net"]

    specs = [TradeSpec(t["ticker"], t["date"], t["r_net"]) for t in trades]
    full = run_control(specs, candidates_on_day, simulate_one,
                       replications=replications)

    train_specs, test_specs = split_by_day(specs, 0.7)
    train = run_control(train_specs, candidates_on_day, simulate_one,
                        replications=replications) if len(train_specs) >= 3 else None
    test = run_control(test_specs, candidates_on_day, simulate_one,
                       replications=replications) if len(test_specs) >= 3 else None

    return format_report(label, full, train, test,
                         configurations_tried=configurations_tried)


def exit_policies() -> List[ExitPolicy]:
    """Candidate exit rules, each a response to a measured leak.

    Deliberately a SHORT list. Every extra policy is another draw in a
    multiple-testing lottery, and the whole point of `skill_test` is that the
    bar rises with the number of things tried. These six are the hypotheses the
    exit-quality report actually generated, not a grid search.
    """
    base_t1 = settings.PENNY_CONNORS_T1_PCT
    base_t2 = settings.PENNY_CONNORS_T2_PCT
    hold = settings.PENNY_CONNORS_MAX_HOLD_DAYS
    return [
        shipped_policy(),
        # Leak 1: the stop is inside the noise (1.88R mean recovery after a
        # stop-out). Widen it and hold longer so the trade has room to work.
        ExitPolicy(0.05, base_t1, base_t2, hold, label="wide stop 5%"),
        ExitPolicy(0.05, base_t1, base_t2, hold * 2, label="wide stop + 2x hold"),
        # Leak 2: the t1 cap. Replace hard rungs with a ratchet so a winner
        # can run; arm it only after the position is meaningfully green.
        ExitPolicy(0.05, base_t1, base_t2, hold * 2,
                   trail_pct=0.04, trail_arm_pct=0.03, label="trail 4% (arm +3%)"),
        ExitPolicy(0.05, base_t1, base_t2, hold * 3,
                   trail_pct=0.06, trail_arm_pct=0.03, label="trail 6% (arm +3%)"),
        # Both leaks: bank half at t1, ratchet the rest. The momentum book's
        # shipped pattern.
        ExitPolicy(0.05, base_t1, base_t2, hold * 2,
                   trail_pct=0.05, trail_arm_pct=0.03, scale_at_t1=True,
                   label="scale half at t1 + trail 5%"),
    ]


def _print_row(label: str, s: dict) -> None:
    if not s["n"]:
        print(f"{label:<32}{0:>9}{'-':>7}{'-':>9}{'-':>12}{'-':>7}{'-':>7}")
        return
    print(f"{label:<32}{s['n']:>9}{s['win_pct']:>7.1f}{s['mean_r']:>+9.4f}"
          f"{s['total_pnl']:>12,.0f}{s['profit_factor']:>7.2f}{s['t_stat']:>7.2f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=settings.DB_PATH)
    ap.add_argument("--sweep", action="store_true",
                    help="vary RSI(2) threshold and the rising-confirmation gate")
    ap.add_argument("--skill", action="store_true",
                    help="run the same-universe random control on the shipped "
                         "configuration: does the SELECTION beat a coin flip?")
    ap.add_argument("--replications", type=int, default=300,
                    help="control samples for --skill (default 300)")
    ap.add_argument("--exits", action="store_true",
                    help="hold the entries fixed and sweep the EXIT policy, "
                         "which is where the measured leak is")
    ap.add_argument("--exit-rsi", type=float, default=25.0,
                    help="RSI(2) threshold to hold fixed during --exits")
    args = ap.parse_args()

    bars = load_bars(args.db)
    print(f"tickers with >= {MIN_BARS + 5} daily bars: {len(bars):,}")
    print()
    header = (f"{'config':<32}{'signals':>9}{'win%':>7}{'meanR':>9}"
              f"{'totalPnL':>12}{'PF':>7}{'t':>7}")
    print(header)
    print("-" * len(header))

    configs = [(settings.PENNY_CONNORS_RSI2_BUY, True)]
    if args.sweep:
        configs = [(r, g) for r in (10.0, 15.0, 20.0, 25.0) for g in (True, False)]

    last_rejects: Dict[str, int] = {}
    per_config: List[Tuple[str, List[dict]]] = []
    for rsi_buy, rising in configs:
        trades, rejects, _ev = simulate(bars, rsi_buy, rising)
        label = f"RSI<{rsi_buy:.0f} rising={'Y' if rising else 'N'}"
        _print_row(label, stats(trades))
        last_rejects = rejects
        per_config.append((label, trades))

    print()
    print("reject funnel (last configuration):")
    for reason, n in sorted(last_rejects.items(), key=lambda kv: -kv[1]):
        print(f"   {n:>9,}  {reason}")
    print()
    print("Reminder: t < ~2 means this has not answered the question yet.")

    if args.exits:
        print()
        print("=" * 83)
        print("EXIT POLICY SWEEP — same entries, same bars, only the exit rule moves.")
        print(f"(entries held at RSI<{args.exit_rsi:.0f} rising=N)")
        print("=" * 83)
        print(header)
        print("-" * len(header))
        policies = exit_policies()
        exit_results: List[Tuple[ExitPolicy, List[dict]]] = []
        for pol in policies:
            trades, _r, _e = simulate(bars, args.exit_rsi, False, pol)
            _print_row(pol.label, stats(trades))
            exit_results.append((pol, trades))

        if args.skill:
            # The exit sweep is itself a search, so the bar rises again: the
            # honest count is (entry configurations) x (exit policies).
            tried = len(configs) * len(policies)
            for pol, trades in exit_results:
                if len(trades) < 3:
                    continue
                print()
                print(skill_control(bars, trades, label=f"exit: {pol.label}",
                                    replications=args.replications,
                                    configurations_tried=tried))

    if args.skill:
        print()
        print("=" * 70)
        print("The t column above asks 'did it make money'. What follows asks")
        print("'did the SELECTION beat a coin flip on the same days' -- the")
        print("question that survives the market drifting up.")
        print("=" * 70)
        # Be honest about the search: --sweep evaluates eight configurations,
        # so the bar moves from 2.0 to the Harvey-Liu-Zhu 3.5.
        tried = len(configs)
        for label, trades in per_config:
            print()
            if len(trades) < 3:
                print(f"SKILL TEST — {label}")
                print(f"  skipped: only {len(trades)} trade(s) at this configuration")
                continue
            print(skill_control(bars, trades, label=label,
                                replications=args.replications,
                                configurations_tried=tried))


if __name__ == "__main__":
    main()
