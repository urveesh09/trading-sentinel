"""Restartable, own-cash simulated Penny book. Never submits a broker order.

All fills are explicitly paper quote assumptions. This book has its own durable
cash, risk, costs and entry halt, separate from incumbent positions and F&O.
"""

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from decimal import Decimal
import math

from adaptive_penny_policy import (
    TickerMemory,
    PennySetup,
    ThesisPosition,
    plan_entry,
    open_thesis_position,
)
from penny_smart_policy import (
    SMART_PARAMS,
    affordable_intent,
    manage_smart,
    smart_setup,
    visible_bars,
)


def new_book(day, bankroll, execution):
    if isinstance(bankroll, bool) or not math.isfinite(bankroll) or bankroll <= 0:
        raise ValueError("positive finite bankroll required")
    return {
        "day": day,
        "bankroll": bankroll,
        "execution": execution,
        "realized": 0.0,
        "setups": {},
        "memory": {},
        "positions": {},
        "last_bars": {},
        "trades": [],
        "events": [],
    }


def _memory(value):
    data = dict(value)
    if data.get("cooldown_until"):
        data["cooldown_until"] = datetime.fromisoformat(data["cooldown_until"])
    return TickerMemory(**data)


def _position(value):
    data = dict(value)
    data["entry_at"] = datetime.fromisoformat(data["entry_at"])
    return ThesisPosition(**data)


def _serialize(value):
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in asdict(value).items()}


def step_book(
    state,
    observations,
    quotes,
    *,
    now,
    cost,
    allow_entries=True,
    max_positions=3,
    stock_cap=500.0,
    risk_pct=0.0025,
    total_risk_pct=0.0075,
    daily_loss_pct=0.01,
    params=SMART_PARAMS,
    manage_exits=True
):
    """One causal observation batch: exits first, ranked intents second.

    observations[ticker] = {bars, median_volume, benchmark_bars?}.
    quotes[ticker] = {entry, exit, executable}; caller owns freshness evidence.
    Missing executable evidence leaves exits pending and blocks entries while
    an existing position cannot be marked. Cash reserves include modeled costs.
    """
    if now.tzinfo is None:
        raise ValueError("aware decision clock required")
    if max_positions < 1 or not all(
        math.isfinite(x) and x > 0 for x in (stock_cap, risk_pct, total_risk_pct, daily_loss_pct)
    ):
        raise ValueError("invalid paper risk limits")
    for obs in observations.values():
        visible_bars(obs["bars"], now)
    # Reject invalid cost evidence rather than accidentally creating free cash.
    supplied_cost = cost

    def cost(entry, exit_price, quantity):
        value = float(supplied_cost(entry, exit_price, quantity))
        if not math.isfinite(value) or value < 0:
            raise ValueError("finite nonnegative modeled cost required")
        return value

    book = deepcopy(state)
    events = []
    if state.get("last_clock") and now < datetime.fromisoformat(state["last_clock"]):
        raise ValueError("out-of-order paper clock")
    book["last_clock"] = now.isoformat()
    overnight = book["day"] != now.date().isoformat()

    def event(kind, ticker, **data):
        events.append({"at": now.isoformat(), "kind": kind, "ticker": ticker, **data})

    # Quote exits remain operational even when observations/regime are absent.
    for ticker, row in list(book["positions"].items()):
        q = quotes.get(ticker, {})
        raw = q.get("exit")
        executable = bool(
            q.get("executable") and isinstance(raw, (float, int)) and math.isfinite(raw) and raw > 0
        )
        position = _position(row["thesis"])
        reason = row.get("exit_pending")
        if overnight or now.hour * 60 + now.minute >= 900:
            reason = reason or "SMART_SESSION_DEADLINE"
        if executable:
            row["mark"] = raw
            if raw <= position.stop:
                reason = reason or "SMART_PAPER_STOP"
        obs = observations.get(ticker)
        if obs and obs["bars"]:
            bar = obs["bars"][-1]
            if not row.get("managed_at") or bar.available_at > datetime.fromisoformat(
                row["managed_at"]
            ):
                if manage_exits:
                    if (
                        row.get("managed_at")
                        and (
                            bar.available_at - datetime.fromisoformat(row["managed_at"])
                        ).total_seconds()
                        > 90
                    ):
                        position = replace(position, closes_below_anchor=0)
                    outcome = manage_smart(position, bar, decision_at=now, params=params)
                    position = outcome.position
                    reason = reason or outcome.exit_reason
                    if outcome.new_stop is not None:
                        event("STOP_RAISED", ticker, stop=outcome.new_stop)
                row["managed_bar"] = bar.observation_id
                row["managed_at"] = bar.available_at.isoformat()
                row["exit_observation_source"] = obs.get(
                    "exit_observation_source", "COMPLETED_CANDLE"
                )
                row["thesis"] = _serialize(position)
        if not manage_exits and now.hour * 60 + now.minute >= 870 and not row.get("eod_checked"):
            from penny_engine_breakout import smart_eod_check, time_stop_triggered

            if executable:
                incumbent = {
                    "entry_price": position.entry_price,
                    "stop_loss_initial": position.initial_stop,
                    "target_1": position.entry_price + 2 * position.risk_per_share,
                    "entry_date": position.entry_at.isoformat(),
                }
                if raw < position.entry_price and time_stop_triggered(position.entry_at, now):
                    reason = reason or "INCUMBENT_TIME_STOP_IN_LOSS"
                else:
                    decision = smart_eod_check(incumbent, raw, now)
                    if decision["action"] == "exit_now":
                        reason = reason or "INCUMBENT_EOD:" + decision["reason"]
                row["eod_checked"] = True
        if executable and raw <= position.stop:
            reason = reason or "SMART_PAPER_TRAIL"
        if reason:
            row["exit_pending"] = reason
            if not executable:
                event("EXIT_PENDING", ticker, reason=reason)
                continue
            quantity = position.shares_open
            fees = cost(position.entry_price, raw, quantity)
            net = (raw - position.entry_price) * quantity - fees
            book["realized"] += net
            trade = {
                **row,
                "status": "CLOSED",
                "exit_price": raw,
                "exit_at": now.isoformat(),
                "exit_reason": reason,
                "net_pnl": net,
                "costs": fees,
            }
            book["trades"].append(trade)
            memory = _memory(book["memory"].get(ticker, {}))
            if net < 0:
                memory = memory.after_failure(position.anchor, now, params)
            book["memory"][ticker] = _serialize(memory)
            del book["positions"][ticker]
            event("EXIT_FILLED", ticker, reason=reason, net_pnl=net, price=raw, shares=quantity)
    if overnight:
        # Never silently reset unresolved prior-day exposure into new free cash.
        event("SESSION_ROLLOVER_PENDING", "", open_positions=len(book["positions"]))
        book["events"] = (book["events"] + events)[-25:]
        return book, events
    markable = all(
        quotes.get(t, {}).get("executable")
        and isinstance(quotes.get(t, {}).get("exit"), (int, float))
        and math.isfinite(quotes[t]["exit"])
        and quotes[t]["exit"] > 0
        for t in book["positions"]
    )
    marked = book["realized"] + sum(
        (p["mark"] - _position(p["thesis"]).entry_price) * _position(p["thesis"]).shares_open
        - cost(_position(p["thesis"]).entry_price, p["mark"], _position(p["thesis"]).shares_open)
        for p in book["positions"].values()
    )
    if markable and marked <= -book["bankroll"] * daily_loss_pct:
        book["daily_loss_latched"] = True
    halted = not allow_entries or not markable or book.get("daily_loss_latched", False)
    if halted:
        event("ENTRY_HALTED", "", reason="regime_or_missing_marks_or_daily_loss", marked_pnl=marked)
    intents = []
    for ticker, obs in sorted(observations.items()):
        bars = obs["bars"]
        if not bars or ticker in book["positions"]:
            continue
        bar = bars[-1]
        if book["last_bars"].get(ticker) == bar.observation_id:
            continue
        previous = book.setdefault("last_bar_times", {}).get(ticker)
        if previous and bar.available_at <= datetime.fromisoformat(previous):
            event("OBSERVATION_UNAVAILABLE", ticker, reason="out_of_order_completed_bar")
            continue
        if (now - bar.available_at).total_seconds() > 120:
            event("OBSERVATION_UNAVAILABLE", ticker, reason="stale_completed_bar")
            continue
        book["last_bars"][ticker] = bar.observation_id
        book["last_bar_times"][ticker] = bar.available_at.isoformat()
        if halted or not obs.get("entry_allowed", True):
            continue
        setup = PennySetup.from_dict(book["setups"][ticker]) if ticker in book["setups"] else None
        outcome = smart_setup(
            ticker,
            bars,
            median_volume=obs["median_volume"],
            decision_at=now,
            setup=setup,
            benchmark_bars=obs.get("benchmark_bars", ()),
            params=params,
        )
        event(
            "SETUP",
            ticker,
            action=outcome.action,
            reason=outcome.reason,
            evidence=dict(outcome.evidence),
        )
        if outcome.setup is not None:
            book["setups"][ticker] = outcome.setup.to_dict()
        if outcome.action in ("INVALIDATED", "EXPIRED", "TERMINAL") or outcome.setup is None:
            book["setups"].pop(ticker, None)
            if setup and outcome.action == "INVALIDATED":
                book["memory"][ticker] = _serialize(
                    _memory(book["memory"].get(ticker, {})).after_failure(setup.anchor, now, params)
                )
        if outcome.intent:
            book["setups"].pop(ticker, None)  # one shot, including failed quote/capacity
            intents.append(outcome)
    intents.sort(key=lambda o: (-(o.intent.score or 0.0), o.intent.ticker))
    for outcome in intents:
        intent = outcome.intent
        ticker = intent.ticker
        memory = _memory(book["memory"].get(ticker, {}))
        blocked = memory.allows(anchor=intent.anchor, now=now, params=params)
        q = quotes.get(ticker, {})
        entry = q.get("entry")
        atr = outcome.setup.atr
        exit_quote = q.get("exit")
        if (
            blocked
            or len(book["positions"]) >= max_positions
            or not q.get("executable")
            or not isinstance(exit_quote, (int, float))
            or not math.isfinite(exit_quote)
            or exit_quote <= 0
            or entry is None
            or not affordable_intent(intent, executable_price=entry, atr=atr, params=params)
        ):
            event("ENTRY_EXPIRED", ticker, reason=blocked or "capacity_quote_or_price_budget")
            continue
        used_cash = sum(
            _position(p["thesis"]).entry_price * _position(p["thesis"]).shares_open
            + p["cost_reserve"]
            for p in book["positions"].values()
        )
        used_risk = sum(
            max(p["mark"] - _position(p["thesis"]).stop, 0) * _position(p["thesis"]).shares_open
            + p["cost_reserve"]
            for p in book["positions"].values()
        )
        free_cash = book["bankroll"] + book["realized"] - used_cash
        risk = min(book["bankroll"] * risk_pct, book["bankroll"] * total_risk_pct - used_risk)
        if free_cash <= 0 or risk <= 0:
            event("ENTRY_EXPIRED", ticker, reason="cash_or_total_risk")
            continue
        plan = plan_entry(
            intent,
            executable_price=entry,
            own_cash=free_cash,
            risk_budget=risk,
            per_position_cash_cap=stock_cap,
            round_trip_cost=cost,
            max_shares=q.get("max_quantity"),
            params=params,
        )
        if plan is None:
            event("ENTRY_EXPIRED", ticker, reason="structural_or_cost_plan")
            continue
        # Stop costs are part of both cash and risk reservation, using exact
        # Decimal distance. Binary search avoids O(quantity) reduction loops.
        distance = Decimal(str(entry)) - Decimal(str(intent.stop))
        lo, hi = 0, plan.shares
        while lo < hi:
            n = (lo + hi + 1) // 2
            fee = Decimal(str(cost(entry, intent.stop, n)))
            if n * distance + fee <= Decimal(str(risk)) and n * Decimal(
                str(entry)
            ) + fee <= Decimal(str(min(free_cash, stock_cap))):
                lo = n
            else:
                hi = n - 1
        if not lo:
            event("ENTRY_EXPIRED", ticker, reason="fee_inclusive_budget")
            continue
        fees = cost(entry, intent.stop, lo)
        plan = replace(
            plan,
            shares=lo,
            risk_rupees=float(distance * lo),
            cash_rupees=entry * lo,
            round_trip_cost=fees,
        )
        position = open_thesis_position(
            plan, ticker=ticker, anchor=intent.anchor, atr=atr, entry_at=now
        )
        book["positions"][ticker] = {
            "thesis": _serialize(position),
            "cost_reserve": fees,
            "mark": exit_quote,
            "entry_at": now.isoformat(),
            "evidence": dict(outcome.evidence),
            "status": "OPEN",
        }
        book["memory"][ticker] = _serialize(memory.after_entry(intent.anchor))
        event("ENTRY_FILLED", ticker, price=entry, shares=lo, stop=intent.stop, score=intent.score)
    book["events"].extend(events)
    # Events are archived by the runtime store per batch; bounded in-memory tail.
    book["events"] = book["events"][-25:]
    # Include newly occupied cash, spread and costs in this observation's mark.
    marked = book["realized"] + sum(
        (p["mark"] - _position(p["thesis"]).entry_price) * _position(p["thesis"]).shares_open
        - cost(_position(p["thesis"]).entry_price, p["mark"], _position(p["thesis"]).shares_open)
        for p in book["positions"].values()
    )
    book["marked_pnl"] = marked if markable else None
    if markable:
        book["peak_marked_pnl"] = max(book.get("peak_marked_pnl", 0.0), marked)
        book["max_marked_drawdown"] = max(
            book.get("max_marked_drawdown", 0.0), book["peak_marked_pnl"] - marked
        )
        if marked <= -book["bankroll"] * daily_loss_pct:
            book["daily_loss_latched"] = True
    book["mark_status"] = "OBSERVED" if markable else "UNAVAILABLE"
    return book, events
