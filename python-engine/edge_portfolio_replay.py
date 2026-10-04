"""R2: causal, own-cash EDGE portfolio replay and the EDGE_TRADER_V1 candidate.

Research only. Signals come from the shipped ``penny_edge_live.scan_today``
over a frozen daily cache; this module never fetches, places orders or edits
EDGE runtime policy.

Clock (declared, matching the live orchestrator as closely as daily bars can):

* D close: the shipped scan ranks candidates from D's completed daily bar.
* D+1 09:30: entry. The 09:30 LTP is approximated by D+1's open (daily data
  cannot show 09:30); the executor's 2% drift check and stop geometry are
  re-validated at that price, and quantity is re-sized to the signal's rupee
  risk at the actual price. A missing or zero-volume D+1 session is a no-fill.
* During each held session: a protective stop (gap-through fills at the open)
  is checked before a resting target. On one daily bar the order of high and
  low is unknown, so the stop wins any tie.
* Time exit at 15:15, approximated by that session's close, on the first
  session whose age reaches the hold. BASELINE uses the live rule (calendar
  age >= PENNY_EDGE_MAX_HOLD_DAYS); a scheduled exit never consults a later bar.

Portfolio contract: own cash only (no margin), one position per ticker, at
most ``max_positions`` new entries per day (live cap), CNC costs per order via
``calc_penny_costs``, daily marked equity for drawdown, and positions still
open at data end are marked, not closed.

EDGE_TRADER_V1 treats MR and MO as different theses (declared before scoring):

* MO (momentum continuation) enters only if the next open holds the signal
  close (a gap-down open means the overnight continuation thesis already
  failed); exits at the close if price gives back below the signal day's
  midpoint; locks breakeven after a +1R close; exits on its own subtype hold.
* MR (panic-drop bounce) enters only if the next open is above the signal
  day's low (no fresh breakdown); exits at the close if the bounce fails with a
  close below that low; locks breakeven after a +1R close; subtype hold.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
import math
import os
import sqlite3
import tempfile

EDGE_POLICIES = ("BASELINE", "EDGE_TRADER_V1")
MO_GAP_TOLERANCE = 0.005     # MO open may be at most 0.5% below the signal close
BREAKEVEN_R = 1.0
MIN_FILL_FRACTION = 0.25   # cash-limited fills below a quarter of planned size are skipped


class EdgeReplayUnavailable(RuntimeError):
    """Required frozen daily evidence is absent or invalid."""


@dataclass(frozen=True)
class EdgeReplayConfig:
    tickers: tuple
    nifty_ticker: str = "NIFTYBEES"
    bankroll: float = 100000.0
    max_positions: int = 3
    min_strength: float = 0.45
    policy: str = "BASELINE"
    entry_drift_pct: float = 0.02      # penny_executor.MAX_ENTRY_DRIFT_PCT
    slippage_bps: float = 5.0          # penny_edge_orchestrator.EDGE_SLIPPAGE_BPS
    max_hold_days: int = 3             # PENNY_EDGE_MAX_HOLD_DAYS (calendar age)

    def __post_init__(self):
        if self.policy not in EDGE_POLICIES:
            raise ValueError(f"policy must be one of {EDGE_POLICIES}")
        if not self.tickers:
            raise ValueError("EDGE replay requires an explicit universe")
        if not math.isfinite(self.bankroll) or self.bankroll <= 0:
            raise ValueError("bankroll must be positive")


def _costs(entry: float, exit_price: float, shares: int, intraday: bool) -> float:
    from config import settings
    from penny_risk import calc_penny_costs
    if getattr(settings, "PENNY_BROKERAGE_BYPASS", False):
        raise EdgeReplayUnavailable("PENNY_BROKERAGE_BYPASS is set; research refuses cost-free P&L")
    return float(calc_penny_costs(entry, exit_price, shares, is_intraday=intraday))


def _session_hold_reached(cfg: EdgeReplayConfig, position: dict, day: str, session_index: int) -> bool:
    if cfg.policy == "BASELINE":
        age = (date.fromisoformat(day) - date.fromisoformat(position["entry_date"])).days
        return age >= cfg.max_hold_days
    # Declared subtype hold in sessions after the entry session, capped by the
    # live calendar maximum so the candidate never holds longer than runtime.
    held = session_index - position["entry_session"]
    age = (date.fromisoformat(day) - date.fromisoformat(position["entry_date"])).days
    return held >= position["hold_days"] or age >= cfg.max_hold_days


def run_edge_portfolio(rows: list[tuple], *, start: str, end: str, config: EdgeReplayConfig) -> dict:
    from penny_edge_live import scan_today

    names = {config.nifty_ticker, *config.tickers}
    have = {str(row[0]).upper() for row in rows}
    missing = sorted(names - have)
    if missing:
        raise EdgeReplayUnavailable("missing required daily history: " + ", ".join(missing))
    bars: dict = defaultdict(dict)
    for ticker, stamp, open_, high, low, close, volume in rows:
        bars[str(ticker).upper()][str(stamp)] = {"open": float(open_), "high": float(high), "low": float(low),
                                                 "close": float(close), "volume": float(volume)}
    calendar = sorted(day for day in bars[config.nifty_ticker] if day >= start)
    if not [day for day in calendar if day <= end]:
        raise EdgeReplayUnavailable("no NIFTY sessions in requested window")
    slip = config.slippage_bps / 10000.0
    fd, path = tempfile.mkstemp(prefix="sentinel-edge-portfolio-", suffix=".sqlite")
    os.close(fd)
    try:
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE ohlcv_cache (ticker TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
        conn.executemany("INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?)", rows)
        conn.commit()
        conn.close()

        cash = config.bankroll
        realized = 0.0
        open_positions: dict[str, dict] = {}
        trades: list[dict] = []
        pending: list = []         # (signal_day, Position, signal_bar)
        outcomes: Counter = Counter()
        equity_curve: list[tuple[str, float]] = []
        capital_days = 0.0
        scans = 0

        def close_position(ticker: str, day: str, price: float, reason: str) -> None:
            nonlocal cash, realized
            position = open_positions.pop(ticker)
            exit_price = price * (1 - slip)
            costs = _costs(position["entry_price"], exit_price, position["shares"], day == position["entry_date"])
            gross = (exit_price - position["entry_price"]) * position["shares"]
            net = gross - costs
            cash += exit_price * position["shares"]
            # Entry-side cash already left the book at fill; settle costs once here.
            cash -= costs
            realized += net
            risk = position["initial_risk_per_share"] * position["shares"]
            position.update({"status": "CLOSED", "exit_date": day, "exit_price": round(exit_price, 6),
                             "exit_reason": reason, "gross_pnl": round(gross, 4), "costs": round(costs, 4),
                             "net_pnl": round(net, 4), "r_multiple": round(net / risk, 6) if risk > 0 else None})
            trades.append(position)

        for session_index, day in enumerate(calendar):
            in_window = day <= end
            # 1. 09:30 entries from the previous close's scan.
            entered_today = 0
            for signal_day, candidate, signal_bar in pending:
                ticker = candidate.ticker
                if entered_today >= config.max_positions:
                    outcomes["DAILY_ENTRY_CAP"] += 1
                    continue
                if ticker in open_positions:
                    outcomes["ALREADY_HELD"] += 1
                    continue
                bar = bars[ticker].get(day)
                if bar is None or bar["volume"] <= 0:
                    outcomes["NO_FILL_MISSING_OR_ZERO_VOLUME_SESSION"] += 1
                    continue
                open_ = bar["open"]
                if abs(open_ - candidate.entry_price) / candidate.entry_price > config.entry_drift_pct:
                    outcomes["DRIFT_REJECTED"] += 1
                    continue
                if candidate.stop_loss >= open_:
                    outcomes["STOP_ALREADY_BREACHED"] += 1
                    continue
                subtype = candidate.signal_subtype
                if config.policy == "EDGE_TRADER_V1":
                    if subtype.startswith("MO") and open_ < candidate.entry_price * (1 - MO_GAP_TOLERANCE):
                        outcomes["THESIS_SKIP_MO_GAP_DOWN"] += 1
                        continue
                    if subtype.startswith("MR") and open_ <= signal_bar["low"]:
                        outcomes["THESIS_SKIP_MR_FRESH_BREAKDOWN"] += 1
                        continue
                entry_price = open_ * (1 + slip)
                risk_rupees = candidate.shares * (candidate.entry_price - candidate.stop_loss)
                per_share = entry_price - candidate.stop_loss
                shares = int(risk_rupees // per_share)
                affordable = int(cash // (entry_price * 1.002))   # leave room for buy-side costs
                if affordable < shares:
                    # Remaining cash cannot fund a meaningful position; a dust
                    # fill only adds per-order costs to the book.
                    if affordable < MIN_FILL_FRACTION * shares:
                        outcomes["CASH_REJECTED_DUST"] += 1
                        continue
                    outcomes["CASH_LIMITED_RESIZE"] += 1
                    shares = affordable
                if shares < 1:
                    outcomes["CASH_REJECTED" if affordable < 1 else "SIZE_ZERO"] += 1
                    continue
                cash -= entry_price * shares
                entered_today += 1
                outcomes["FILLED"] += 1
                open_positions[ticker] = {
                    "ticker": ticker, "policy": config.policy, "signal_date": signal_day, "entry_date": day,
                    "entry_session": session_index, "signal_subtype": subtype,
                    "adjusted_strength": round(candidate.adjusted_strength, 6),
                    "signal_close": candidate.entry_price, "signal_low": signal_bar["low"],
                    "signal_mid": (signal_bar["open"] + signal_bar["close"]) / 2,
                    "entry_price": round(entry_price, 6), "shares": shares,
                    "stop": candidate.stop_loss, "initial_stop": candidate.stop_loss,
                    "initial_risk_per_share": entry_price - candidate.stop_loss,
                    "target": candidate.target, "hold_days": candidate.hold_days,
                    "discovery_shares": candidate.shares,
                }
            pending = []
            # 2. Intraday protective stop, then resting target, then 15:15 rules.
            for ticker in sorted(open_positions):
                position = open_positions[ticker]
                bar = bars[ticker].get(day)
                if bar is None or bar["volume"] <= 0:
                    continue   # no executable evidence today; the position stays open
                if bar["low"] <= position["stop"]:
                    gap = day != position["entry_date"] and bar["open"] <= position["stop"]
                    close_position(ticker, day, bar["open"] if gap else position["stop"],
                                   "STOP_GAP" if gap else "STOP")
                    continue
                if bar["high"] >= position["target"]:
                    close_position(ticker, day, position["target"], "TARGET")
                    continue
                if config.policy == "EDGE_TRADER_V1":
                    if position["signal_subtype"].startswith("MR") and bar["close"] < position["signal_low"]:
                        close_position(ticker, day, bar["close"], "THESIS_MR_BOUNCE_FAILED")
                        continue
                    if position["signal_subtype"].startswith("MO") and bar["close"] < position["signal_mid"]:
                        close_position(ticker, day, bar["close"], "THESIS_MO_GAVE_BACK")
                        continue
                if _session_hold_reached(config, position, day, session_index):
                    close_position(ticker, day, bar["close"], "TIME")
                    continue
                if (config.policy == "EDGE_TRADER_V1"
                        and bar["close"] >= position["entry_price"] + BREAKEVEN_R * position["initial_risk_per_share"]):
                    position["stop"] = max(position["stop"], position["entry_price"])
            # 3. Mark equity at the close; scan for the next session's entries.
            marked = cash
            for ticker, position in open_positions.items():
                last = bars[ticker].get(day)
                price = last["close"] if last else position["entry_price"]
                marked += price * position["shares"]
                capital_days += position["entry_price"] * position["shares"]
            equity_curve.append((day, round(marked, 4)))
            # Only decisions whose 09:30 entry still falls inside the window.
            if session_index + 1 < len(calendar) and calendar[session_index + 1] <= end:
                scan = scan_today(bankroll=config.bankroll + realized, max_positions=config.max_positions,
                                  min_strength=config.min_strength, db_path=path, as_of_date=day,
                                  nifty_ticker=config.nifty_ticker)
                scans += 1
                pending = [(day, candidate, bars[candidate.ticker][day]) for candidate in scan["positions"]
                           if day in bars[candidate.ticker]]
            if not in_window and not open_positions:
                break
        for ticker, position in sorted(open_positions.items()):
            last_day = max(d for d in bars[ticker] if d <= calendar[-1])
            position.update({"status": "OPEN_MARKED", "mark_date": last_day,
                             "mark_price": bars[ticker][last_day]["close"]})
            trades.append(position)
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
    return {"scope": "PORTFOLIO_PROXY", "policy": config.policy, "config": {**asdict(config), "tickers": list(config.tickers)},
            "clock": "scan_after_D_close; entry_D+1_open_as_0930_proxy; stop_before_target; time_exit_at_close",
            "scans": scans, "trades": trades, "admission_outcomes": dict(sorted(outcomes.items())),
            "summary": _summary(trades, equity_curve, config.bankroll, capital_days),
            "equity_curve": equity_curve}


def _summary(trades: list[dict], curve: list[tuple[str, float]], bankroll: float, capital_days: float) -> dict:
    closed = [t for t in trades if t["status"] == "CLOSED"]
    net = [t["net_pnl"] for t in closed]
    peak, drawdown = bankroll, 0.0
    for _, equity in curve:
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    by_subtype: dict = defaultdict(lambda: {"closed": 0, "net_pnl": 0.0, "wins": 0})
    for trade in closed:
        row = by_subtype[trade["signal_subtype"]]
        row["closed"] += 1
        row["net_pnl"] = round(row["net_pnl"] + trade["net_pnl"], 4)
        row["wins"] += int(trade["net_pnl"] > 0)
    best = max(net) if net else 0.0
    final = curve[-1][1] if curve else bankroll
    return {
        "entries": len(trades), "closed": len(closed),
        "open_marked": sum(t["status"] == "OPEN_MARKED" for t in trades),
        "net_pnl": round(sum(net), 4), "gross_pnl": round(sum(t["gross_pnl"] for t in closed), 4),
        "costs": round(sum(t["costs"] for t in closed), 4),
        "final_marked_equity": final, "marked_return_pct": round(100 * (final - bankroll) / bankroll, 4),
        "max_marked_drawdown": round(drawdown, 4), "max_marked_drawdown_pct": round(100 * drawdown / bankroll, 4),
        "win_rate_pct": round(100 * sum(x > 0 for x in net) / len(net), 2) if net else None,
        "profit_factor": (round(sum(x for x in net if x > 0) / abs(sum(x for x in net if x < 0)), 4)
                          if any(x < 0 for x in net) else None),
        "net_excluding_best_winner": round(sum(net) - best, 4) if best > 0 else round(sum(net), 4),
        "avg_capital_deployed_pct": round(100 * capital_days / (bankroll * max(len(curve), 1)), 4),
        "exit_reasons": dict(sorted(Counter(t.get("exit_reason", t["status"]) for t in trades).items())),
        "by_subtype": dict(sorted(by_subtype.items())),
    }
