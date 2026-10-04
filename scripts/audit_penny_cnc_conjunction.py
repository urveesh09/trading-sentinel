"""T2 Penny CNC audit: how often each Connors condition passes, alone and together.

python scripts/audit_penny_cnc_conjunction.py --start 2026-01-01 --end 2026-09-30

Diagnostic only (plan T2 "small CNC audit"): it reuses the shipped
``penny_engine_connors`` helpers on completed daily bars of the archived Penny
universe and reports, per ticker-day,

* each condition's independent pass count and the sequential first-reject
  funnel of ``evaluate_connors_entry``;
* the full conjunction (what the runtime can actually fire);
* an *armed pullback/reclaim* alternative: uptrend + RSI(2) below the buy
  threshold arms a thesis; a close above the prior day's high within
  ``ARM_SESSIONS`` triggers it — the rising-RSI clause is dropped because
  "oversold" and "rising for two bars" rarely coexist;
* the next-open → +5-session close return of each set, labelled as a
  descriptive statistic (no stops, costs or cash; not a strategy result).

No network, broker, order or database writes; prints JSON to stdout.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
from statistics import mean, median
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-engine"))

SNAPSHOT = ROOT / "docs/research/yahoo/2026-10-04-q3-review-baseline/_local/validated-yahoo.sqlite"
UNIVERSE = ROOT / "docs/research/yahoo/2026-10-04-q3-review-final/_local/penny-cnc-recent-diagnostic-report.json"
HISTORY_FLOOR = 250
ARM_SESSIONS = 3
HORIZON = 5


def _forward(bars: list, index: int) -> float | None:
    """Next open to the close HORIZON sessions later, as a fraction."""
    if index + 1 + HORIZON >= len(bars):
        return None
    entry = bars[index + 1].open
    return bars[index + 1 + HORIZON].close / entry - 1 if entry > 0 else None


def _describe(returns: list[float]) -> dict:
    if not returns:
        return {"count": 0}
    return {"count": len(returns), "mean_pct": round(100 * mean(returns), 3),
            "median_pct": round(100 * median(returns), 3),
            "positive_pct": round(100 * sum(r > 0 for r in returns) / len(returns), 1)}


def audit(start: str, end: str) -> dict:
    from config import settings
    from penny_engine_connors import _rsi_2, _sma
    from research_data_contracts import load_daily_dataset

    tickers = json.loads(UNIVERSE.read_text())["request"]["config"]["tickers"]
    data = load_daily_dataset(str(SNAPSHOT), tickers=tickers,
                              before=(date.fromisoformat(end) + timedelta(days=15)).isoformat())
    threshold = float(settings.PENNY_CONNORS_RSI2_BUY)
    passes = {name: 0 for name in ("history", "above_sma200", "above_sma50", "rsi2_below_buy",
                                   "rsi2_rising_two_bars", "volume_ok")}
    funnel: dict[str, int] = {}
    evaluated = 0
    returns: dict[str, list[float]] = {"all_days": [], "uptrend_oversold": [], "full_conjunction": [],
                                       "armed_reclaim": []}
    for ticker in tickers:
        bars = list(data.bars.get(ticker, ()))
        closes = [bar.close for bar in bars]
        armed_at: int | None = None
        for index, bar in enumerate(bars):
            if not start <= bar.day.isoformat() <= end:
                continue
            evaluated += 1
            history = closes[:index + 1]
            forward = _forward(bars, index)
            if forward is not None:
                returns["all_days"].append(forward)
            checks = {"history": len(history) >= HISTORY_FLOOR}
            sma200, sma50 = (_sma(history, 200), _sma(history, 50)) if checks["history"] else (None, None)
            checks["above_sma200"] = sma200 is not None and history[-1] > sma200
            checks["above_sma50"] = sma50 is not None and history[-1] > sma50
            rsi = _rsi_2(history) if len(history) >= 3 else 100.0
            checks["rsi2_below_buy"] = rsi < threshold
            checks["rsi2_rising_two_bars"] = (len(history) >= 5 and
                                              rsi > _rsi_2(history[:-1]) > _rsi_2(history[:-2]))
            window = [b.volume for b in bars[max(0, index - 20):index]]
            avg20 = sum(window) / len(window) if window else 0.0
            checks["volume_ok"] = avg20 > 0 and bar.volume >= 0.5 * avg20
            for name, ok in checks.items():
                passes[name] += ok
            first = next((name for name, ok in checks.items() if not ok), "FIRES")
            funnel[first] = funnel.get(first, 0) + 1
            uptrend = checks["history"] and checks["above_sma200"] and checks["above_sma50"]
            if uptrend and checks["rsi2_below_buy"] and forward is not None:
                returns["uptrend_oversold"].append(forward)
            if first == "FIRES" and forward is not None:
                returns["full_conjunction"].append(forward)
            # Armed pullback/reclaim alternative.
            if armed_at is not None and (index - armed_at > ARM_SESSIONS or not uptrend):
                armed_at = None
            if armed_at is not None and index > armed_at and bar.close > bars[index - 1].high:
                if forward is not None:
                    returns["armed_reclaim"].append(forward)
                armed_at = None
            elif uptrend and checks["rsi2_below_buy"]:
                armed_at = index
    return {"window": [start, end], "universe": len(tickers), "ticker_days": evaluated,
            "rsi2_buy_threshold": threshold, "independent_pass_counts": passes,
            "first_reject_funnel": dict(sorted(funnel.items(), key=lambda kv: -kv[1])),
            "forward_return_next_open_to_plus5_close": {k: _describe(v) for k, v in returns.items()},
            "interpretation": "Descriptive only: no stop, target, costs, cash or overlap; not a strategy result."}


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("--start", required=True)
    cli.add_argument("--end", required=True)
    args = cli.parse_args()
    print(json.dumps(audit(args.start, args.end), indent=2))


if __name__ == "__main__":
    main()
