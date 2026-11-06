"""Declared candle-only execution for the frozen prior-range sleeve."""

from collections import defaultdict
from contextlib import closing
from dataclasses import replace
from datetime import date, datetime, timedelta
from math import isfinite

from config import settings
from fno_chain import ChainSnapshot
from fno_exit_rules import IST
from prior_range_reclaim import LAST, REFERENCE_END, clock, day_rows, decision
from reclaim_execution import RangeSleeve


STANDARD = 205.
DOUBLED = 410.


class MinuteSleeve(RangeSleeve):
    def enter_bar(self, signal, signal_at, obs, expiry, regime, traded):
        options = {
            (quote.contract.strike, quote.contract.instrument_type): replace(quote, bid_quantity=0, ask_quantity=0)
            for quote in obs.options.values() if quote.contract.expiry == expiry
        }
        chain = ChainSnapshot(obs.at, expiry, obs.future.ltp, None, obs.future.contract.lot_size, obs.future, options)
        return self._enter(signal, signal_at, chain, regime, False, True, traded)

    def manage_bar(self, obs, traded):
        token = self.position.token
        quote = obs.options.get(token)
        supported = quote is not None and token in traded and quote.last_trade_time == obs.at
        return self._manage(obs.at, obs.future.ltp, token, quote.bid if quote else 0., supported)


def active_minutes(db, data, day, expiry):
    active = defaultdict(set)
    for stamp, strike, right, price, volume in db.execute(
        "SELECT datetime,strike,opt,close,volume FROM candles WHERE kind='option' AND expiry=? "
        "AND datetime>=? AND datetime<? ORDER BY datetime",
        (expiry.isoformat(), f"{day} 09:15:00", f"{day} {clock(settings.FNO_HARD_FLAT_MIN + 1)}"),
    ):
        if volume is not None and isfinite(volume) and volume > 0 and price is not None and isfinite(price) and price > 0:
            active[stamp].add(data.option_contract(expiry, strike, right).token)
    return active


def active_futures(db, day, front):
    end = clock(settings.FNO_HARD_FLAT_MIN + 1)
    return {stamp for stamp, close, volume in db.execute(
        "SELECT datetime,close,volume FROM candles WHERE kind='future' AND expiry=? "
        "AND strike=0 AND opt='' AND datetime>=? AND datetime<?",
        (front.isoformat(), f"{day} 09:15:00", f"{day} {end}"),
    ) if all(value is not None and isfinite(value) and value > 0 for value in (close, volume))}


def observation_clock(at):
    return at.astimezone(IST).replace(tzinfo=None, second=0, microsecond=0).isoformat(sep=" ")


def evaluate_session(db, data, book, day, prior_day):
    today = date.fromisoformat(day)
    weekly = next((expiry for expiry in data.option_expiries()[0] if expiry >= today), None)
    front = data.front_expiry(today)
    if weekly is None:
        return {"status": "calendar_unavailable"}
    if today in (weekly, front):
        return {"status": "expiry"}
    if (today - date.fromisoformat(prior_day)).days > 4:
        return {"status": "prior_session_gap_excluded"}
    reason, signal = decision(day_rows(db, front.isoformat(), prior_day, REFERENCE_END),
                              day_rows(db, front.isoformat(), day, LAST))
    if signal is None:
        return {"status": reason}
    signal_at = IST.localize(datetime.fromisoformat(f"{day} {clock(signal.minute)}"))
    start = signal_at + timedelta(seconds=59)
    observations, _ = data.observations(day)
    tape = {obs.at: obs for obs in observations}
    if len(tape) != len(observations):
        raise ValueError(f"duplicate minute observation: {day}")
    obs = tape.get(start)
    futures_traded = active_futures(db, day, front)
    if obs is None or observation_clock(start) not in futures_traded:
        return {"status": "entry_minute_unavailable", "signal_at": signal_at.isoformat()}
    active = active_minutes(db, data, day, weekly)
    traded = active.get(observation_clock(start), set())
    if not obs.options:
        return {"status": "entry_chain_unavailable", "signal_at": signal_at.isoformat()}
    bar = f"{day} {clock(signal.minute - 5)}"
    regime, source = data.regime(bar, day)
    entry = book.enter_bar(signal, signal_at, obs, weekly, regime, traded)
    if entry != "accepted":
        return {"status": "entry_refused", "reason": entry, "signal_at": signal_at.isoformat(),
                "regime_source": source}

    position = book.position
    detail = {"entry_time": start.isoformat(), "tradingsymbol": position.symbol,
              "entry_qty": position.qty, "entry_premium": position.ask, "direction": signal.direction,
              "regime_source": source}
    flat_hour, flat_minute = divmod(settings.FNO_HARD_FLAT_MIN, 60)
    hard_flat = start.replace(hour=flat_hour, minute=flat_minute, second=59)
    at = start + timedelta(minutes=1)
    while at <= hard_flat:
        obs = tape.get(at)
        if obs is None or observation_clock(at) not in futures_traded:
            return {"status": "unresolved", "reason": "held_future_minute_unavailable", "gap_at": at.isoformat(), **detail}
        result, close = book.manage_bar(obs, active.get(observation_clock(at), set()))
        if close is not None:
            return {"status": "closed", "exit_time": at.isoformat(), "exit_reason": close.reason,
                    "exit_premium": close.bid, "fees": close.fees, "stress": close.stress,
                    "net_pnl": close.net, **detail}
        if result != "hold":
            return {"status": "unresolved", "reason": result, "gap_at": at.isoformat(), **detail}
        at += timedelta(minutes=1)
    return {"status": "unresolved", "reason": "hard_flat_missing", **detail}


def replay(data, sessions, *, allocation=250_000., stress=STANDARD):
    """Run one independent cash book over a declared holdout scope.

    sessions contains the previous trading session first, then the exact
    requested scoring sessions. The dataset manifest lists the scoring days.
    """
    sessions = tuple(sessions)
    if len(sessions) < 2 or sessions != tuple(sorted(set(sessions))) or tuple(data.days) != sessions[1:]:
        raise ValueError("scoring sessions differ from the declared calendar")
    if data.name != "NIFTY":
        raise ValueError("range reclaim is a NIFTY-only sleeve")
    book = MinuteSleeve(allocation, stress=stress)
    results = {}
    coverage_lost = False
    with closing(data._connect()) as db:
        db.execute("PRAGMA query_only=ON")
        for previous, day in zip(sessions, sessions[1:]):
            if coverage_lost:
                results[day] = {"status": "not_scored_after_gap"}
                continue
            try:
                row = evaluate_session(db, data, book, day, previous)
            except StopIteration:
                row = {"status": "calendar_unavailable"}
            results[day] = row
            coverage_lost = row["status"] not in {
                "expiry", "prior_session_gap_excluded", "no_setup", "open_outside_prior_range", "entry_refused", "closed",
            }
    return {"allocation": allocation, "stress": stress, "days": results,
            "net": None if coverage_lost else book.equity - allocation,
            "mode": "modeled_minute_close_bid_ask", "complete": not coverage_lost}


def replay_stresses(data, sessions, *, allocation=250_000.):
    return {label: replay(data, sessions, allocation=allocation, stress=cost)
            for label, cost in (("standard", STANDARD), ("doubled", DOUBLED))}
