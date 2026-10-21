"""[O21-PC 2026-10-21] Partner coach: what the partner did, what each card
said, and the difference in rupees with a reason.

The partner is a manual trader, so every card instruction is priced
PARTNER_COACH_REACTION_SEC (default 120 s) after the message reached them,
using the 5-minute option prints the analytics tick already stores
(fno_chain_oi). The coach never compares the partner with the engine's
10-second clock, and it never blocks or changes a card.

Three numbers per traded card:
  - actual: the partner's reported prices, after charges;
  - card exits on your entry: same entry, exits where the card said (premium
    SL order, exit/target update, square-off). The gap to actual is what the
    exit behaviour cost or earned;
  - card plan: the whole card, entry included. A chased, late or after-close
    entry was "skip" on the card, so its plan is ₹0.

Behaviour flags are rules with fixed thresholds, each with the numbers that
triggered it, so the partner can see exactly why: a chased entry (FOMO), a
quick re-entry after a loss (revenge pattern), size up after a loss, adding
to a losing option, holding past the stop, exiting before the plan, giving
back after the target, holding past square-off and more trades than cards.

[O21-PL] Each flag explains itself to the partner: ``reason`` (what
happened, with times and prices), ``why`` (why it matters, with this
trade's numbers, e.g. the extra risk a chased entry took to the same stop),
``better`` and ``better_pnl`` (the better action and what it would have paid
after charges, charged for the same number of orders), and ``advice`` (the
rule). ``impact_rs`` = actual - better. A rule-break that made money says so
and is still flagged (process over outcome). On Zerodha days whose stops are
fully known (SL orders and GTTs read), stop discipline is checked too:
NO_STOP_ORDER, STOP_WIDER_THAN_CARD, STOP_CANCELLED; placing the stop, a
pause after a loss and an exit ahead of the stop are positives.
partner_lessons.py turns a day of this into the partner's review.

[O21-PX] partner_insights.py adds what the option did around each trade (the
owner's 1-minute candles), what the partner's Zerodha book shows (order
changes, rejections, positions, the day's cash) and the lessons that follow
from them: CHASED_SPIKE, GAVE_BACK_PROFIT, STOP_LOWERED, PRICE_RAISED_TO_FILL,
BIG_RISK, HELD_OVERNIGHT and INSUFFICIENT_FUNDS.

Honesty rules (paper-fill-honesty): reported prices are the partner's;
"≈" prices came from a quote at the tap; a plan exit is a 5-minute print,
not a fill; nothing is called a maximum or breakeven. 5-minute prints can
miss a touch between samples, which the output says.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

import aiosqlite
import pytz
import structlog

from config import settings
from cost_schedules import options_cost_snapshot
from fno_costs import calc_fno_costs

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")

CARD_KIND = "manual_market_advisory"
UPDATE_KIND = "manual_advisory_update"
PRINT_MAX_WAIT = timedelta(minutes=15)   # a plan exit needs a print this soon
LIMIT_TOLERANCE_TICKS = 1                # paid more than one tick over the limit
STOP_SLIPPAGE_PCT = 0.03                 # a fast fall fills a little under the SL
STOP_LATE_MIN = 10                       # minutes after the exit message
EARLY_EXIT_MIN = 10                      # sold this long before the card's exit
EARLY_EXIT_PCT = 0.05                    # ... and the card's exit print was 5% higher
GAVE_BACK_MIN = 15                       # held this long after the target message
GAVE_BACK_PCT = 0.05                     # ... and sold 5% under the target print
SQUARE_OFF_GRACE_MIN = 5
REENTRY_WINDOW_MIN = 30                  # a buy this soon after a losing exit
AVERAGED_DOWN_PCT = 0.02
OVERTRADE_MIN_BUYS = 3
# [O21-PL] Stop discipline, from Zerodha's order book (SL orders and GTTs).
STOP_CLOCK_SLACK = timedelta(seconds=60)  # a stop placed this close before the buy is for it
STOP_CHECK_MIN_HOLD_MIN = 5               # "no stop" only for a trade held at least this long
STOP_PROMPT_MIN = 5                       # a stop this soon after the buy earns the positive
STOP_WIDER_PCT = 0.03                     # a stop this far under the card's SL is "wider"
STOP_CANCEL_SLIP_PCT = 0.01               # sold this far under a cancelled stop
SQUARE_OFF_MIN = 15 * 60 + 15             # a stop cancelled after this may be the broker's square-off
EXIT_LABELS = {"TARGET_MESSAGE": "target message", "SQUARE_OFF_MESSAGE": "square-off message",
               "EXIT_BY": "exit-by time"}

# The rule for next time: one short line the partner can remember.
ADVICE = {
    "ENTRY_ABOVE_LIMIT": "Above the buy-up-to price, skip. Use a LIMIT order at the card's price instead "
                         "of chasing.",
    "LATE_ENTRY": "After the skip-after time the card is over; wait for the next one.",
    "AFTER_CARD_CLOSED": "Once the card's exit or target message has come, the idea is finished; do not buy it.",
    "OFF_CARD": "No card, no trade. If you take one, write down the stop before buying.",
    "QUICK_REENTRY_AFTER_LOSS": "After a loss, take a 30-minute break and trade only the next card.",
    "SIZE_UP_AFTER_LOSS": "Keep the same size after a loss. Size up only after a run of trades that "
                          "followed the card.",
    "AVERAGED_DOWN": "Never add to a falling option. One entry, one stop.",
    "HELD_PAST_STOP": "Place the SL order right after buying, as the card says. It exits for you, "
                      "even when you are busy.",
    "EARLY_EXIT": "Let the SL order protect you and exit on the card's message, not on a wobble.",
    "GAVE_BACK_AFTER_TARGET": "At the target message, book at least half and move the SL to your entry on "
                              "the rest.",
    "HELD_PAST_SQUARE_OFF": "Be flat by the card's exit-by time; set an alarm for it.",
    "OVERTRADING": "Trade the cards only; close the app between cards.",
    "NO_STOP_ORDER": "Place the SL order right after the buy fills, every time. It exits for you even when "
                     "you are busy or the price falls fast.",
    "STOP_WIDER_THAN_CARD": "Put the SL order at the card's price.",
    "STOP_CANCELLED": "Never cancel or lower a stop once it is placed. Move it only up, to lock in profit.",
    # [O21-PX] partner_insights.py
    "CHASED_SPIKE": "Do not buy an option that has just jumped. Wait for a card, or let the price settle first.",
    "GAVE_BACK_PROFIT": "Once a trade is up 20%, move the SL order to your buy price.",
    "STOP_LOWERED": "Never cancel or lower a stop once it is placed. Move it only up, to lock in profit.",
    "PRICE_RAISED_TO_FILL": "Set the buy price once. If it does not fill, let the trade go.",
    "BIG_RISK": "Keep what one trade can lose (to its stop) under a tenth of the cash in your account.",
    "HELD_OVERNIGHT": "Be out of every intraday option buy before the close.",
    "INSUFFICIENT_FUNDS": "Decide the lots before the trade, from the cash you have; never try the whole balance.",
    "ENTRY_UNDER_STOP": "If the option is already at or under the card's SL, the card is over; do not buy it.",
}
TITLES = {
    "ENTRY_ABOVE_LIMIT": "Chased the entry (FOMO)",
    "LATE_ENTRY": "Bought after the skip-after time",
    "AFTER_CARD_CLOSED": "Bought after the card closed",
    "OFF_CARD": "Trade without a card",
    "QUICK_REENTRY_AFTER_LOSS": "Quick re-entry after a loss (revenge pattern)",
    "SIZE_UP_AFTER_LOSS": "Bigger size after a loss",
    "AVERAGED_DOWN": "Added to a losing option",
    "HELD_PAST_STOP": "Held past the stop",
    "EARLY_EXIT": "Sold before the card's exit",
    "GAVE_BACK_AFTER_TARGET": "Gave back after the target",
    "HELD_PAST_SQUARE_OFF": "Held past square-off",
    "OVERTRADING": "More trades than cards",
    "NO_STOP_ORDER": "No stop-loss order",
    "STOP_WIDER_THAN_CARD": "Stop wider than the card",
    "STOP_CANCELLED": "Cancelled the stop",
    "CHASED_SPIKE": "Bought after a spike (FOMO)",
    "GAVE_BACK_PROFIT": "A winning trade turned into a loss",
    "STOP_LOWERED": "Moved the stop down",
    "PRICE_RAISED_TO_FILL": "Raised the buy price to get filled",
    "BIG_RISK": "Too much of the account on one trade",
    "HELD_OVERNIGHT": "Held an option past the close",
    "INSUFFICIENT_FUNDS": "Order refused: not enough money",
    "ENTRY_UNDER_STOP": "Bought under the card's SL",
}
POSITIVE_TITLES = {
    "BOUGHT_IN_LIMIT": "Bought inside the limit and on time",
    "EXITED_WITH_CARD": "Exited with the card",
    "SKIP_SAVED": "Skipping saved money",
    "STOP_PLACED": "Placed the stop-loss order",
    "EXITED_BEFORE_STOP": "Got out before the stop",
    "PAUSED_AFTER_LOSS": "Paused after a loss",
    "CUT_LOSS_SAVED": "Cut the loss in time",
    "STOP_TRAILED": "Moved the stop up",
}


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _dt(value) -> Optional[datetime]:
    """ISO with offset, or a naive 'YYYY-MM-DD HH:MM:SS' IST print time."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else IST.localize(value)
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed.astimezone(IST) if parsed.tzinfo else IST.localize(parsed)


def _hhmm(value: Optional[datetime]) -> str:
    return value.astimezone(IST).strftime("%H:%M") if value else "?"


def _rs(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    if round(value) == 0:
        return "₹0"
    sign = "−" if value < 0 else "+"
    return f"{sign}₹{abs(value):,.0f}"


def _px(value: Optional[float]) -> str:
    if value is None:
        return "?"
    return "₹" + f"{value:,.2f}".rstrip("0").rstrip(".")


def round_trip_costs(entry: float, exit_: float, qty: int, exchange: str, orders: int = 2) -> float:
    """calc_fno_costs plus the flat brokerage (with GST) of any extra orders."""
    costs = calc_fno_costs(entry, exit_, qty, exchange=exchange or "NFO")
    if orders > 2:
        rates = options_cost_snapshot(exchange or "NFO")["rates"]
        costs += (orders - 2) * float(rates["brokerage_flat_per_order"]) * (1 + float(rates["gst_pct"]))
    return round(costs, 2)


def print_at(series: list, at: datetime, max_wait: timedelta = PRINT_MAX_WAIT):
    """First (time, price) at or after ``at`` within ``max_wait``."""
    for ts, ltp in series:
        if ts >= at:
            return (ts, ltp) if ts - at <= max_wait else None
    return None


def last_print_before(series: list, at: datetime):
    found = None
    for ts, ltp in series:
        if ts <= at:
            found = (ts, ltp)
        else:
            break
    return found


# ---------------------------------------------------------------------------
# the card's plan
# ---------------------------------------------------------------------------

def card_exit(card: dict, entry_at: datetime, reaction: timedelta) -> Optional[dict]:
    """Where the card said to get out of a position opened at ``entry_at``.

    Earliest of: the premium SL order (first 5-minute print at/under it),
    a delivered exit/target/square-off message (the print ``reaction``
    after it) and the exit-by deadline. ``None`` without any usable price.
    """
    series = card["series"]
    events = []
    sl = card.get("sl_premium")
    if sl:
        for ts, ltp in series:
            if ts >= entry_at and ltp <= sl:
                events.append({"at": ts, "price": float(sl), "reason": "STOP",
                               "note": f"premium SL {_px(sl)} (5-min print {_px(ltp)} at {_hhmm(ts)})"})
                break
    labels = {"INVALIDATION": "EXIT_MESSAGE", "TARGET_ZONE": "TARGET_MESSAGE",
              "SESSION_EXIT_REMINDER": "SQUARE_OFF_MESSAGE"}
    for update in card.get("updates") or []:
        if not update.get("delivered_at") or update["delivered_at"] < entry_at:
            continue
        found = print_at(series, update["delivered_at"] + reaction)
        if found:
            events.append({"at": update["delivered_at"], "price": found[1], "reason": labels.get(update["event_type"], update["event_type"]),
                           "note": f"{_hhmm(update['delivered_at'])} message, print {_px(found[1])} at {_hhmm(found[0])}"})
    exit_by = card.get("exit_by")
    if exit_by and exit_by > entry_at:
        found = last_print_before(series, exit_by)
        if found and found[0] >= entry_at:
            events.append({"at": exit_by, "price": found[1], "reason": "EXIT_BY",
                           "note": f"exit-by {_hhmm(exit_by)}, print {_px(found[1])} at {_hhmm(found[0])}"})
    if not events:
        return None
    return min(events, key=lambda e: e["at"])


def card_entry(card: dict, reaction: timedelta) -> dict:
    """What following the card would have paid, for a card the partner did not buy."""
    delivered = card["delivered_at"]
    found = print_at(card["series"], delivered + reaction)
    limit = card.get("buy_limit")
    if found is None:
        return {"price": card.get("ask"), "at": delivered + reaction, "basis": "CARD_ASK",
                "skip": False}
    if limit and found[1] > limit:
        return {"price": None, "at": found[0], "basis": "PRINT_ABOVE_LIMIT", "skip": True,
                "note": f"print {_px(found[1])} at {_hhmm(found[0])} was above the buy-up-to {_px(limit)}"}
    sl = card.get("sl_premium")
    if sl and found[1] <= sl:
        # The option was already at the stop: the card's setup had failed.
        return {"price": None, "at": found[0], "basis": "PRINT_AT_STOP", "skip": True,
                "note": f"print {_px(found[1])} at {_hhmm(found[0])} was already at or under the SL {_px(sl)}"}
    return {"price": found[1], "at": found[0], "basis": "5MIN_PRINT", "skip": False}


# ---------------------------------------------------------------------------
# the partner's trades
# ---------------------------------------------------------------------------

def round_trips(rows: list[dict]) -> list[list[dict]]:
    """[O21-PX] One option's fills split where the position is flat again.

    A buy after a full exit is a new trade (a re-entry), not an addition to
    the old one: before, a stop-out and a re-buy of the same option read as
    "added to a losing option" and hid the re-entry. Scaling in or out keeps
    one trade. A sale with nothing bought before it (a position from an
    earlier day) is kept apart, last; skips stay with the first trade."""
    if not any(r["action"] == "BUY" for r in rows):
        return [rows]
    trips, current, held, strays, skips = [], [], 0, [], []
    for row in rows:
        if row["action"] == "SKIP":
            skips.append(row)
            continue
        if row["action"] == "SELL" and held <= 0:
            strays.append(row)
            continue
        current.append(row)
        if row["action"] == "BUY":
            held += row.get("lots") or 1
        elif row["action"] == "SELL":
            held = 0 if row.get("lots") is None else held - row["lots"]
            if held <= 0:
                trips.append(current)
                current, held = [], 0
    if current:
        trips.append(current)
    trips[0] = skips + trips[0]
    if strays:
        trips.append(strays)
    return trips


def build_trades(reports: list[dict]) -> dict:
    """Group ACTIVE reports into trades: one per card (or off-card contract
    and day), then [O21-PX] one per round trip. The first round trip keeps
    the group's key; a later one is "<key>#2", "#3"..."""
    groups: dict = defaultdict(list)
    for report in reports:
        if report.get("status") != "ACTIVE":
            continue
        key = report.get("advisory_id") or (
            f"off:{report['session_date']}:{report.get('underlying')}:{report.get('strike')}:{report.get('opt_type')}")
        groups[key].append(report)
    trips: dict = {}
    for key, rows in groups.items():
        rows.sort(key=lambda r: (str(r["trade_at"]), r["report_id"]))
        for n, trip in enumerate(round_trips(rows)):
            trips[key if n == 0 else f"{key}#{n + 1}"] = trip
    trades = {}
    for key, rows in trips.items():
        lot_size = next((r.get("lot_size") for r in rows if r.get("lot_size")), None)
        buys = [r for r in rows if r["action"] == "BUY"]
        sells = [r for r in rows if r["action"] == "SELL"]
        bought_lots = sum(r.get("lots") or 1 for r in buys)
        sold_known = sum(r.get("lots") or 0 for r in sells)
        sold_all = any(r.get("lots") is None for r in sells)
        sold_lots = bought_lots if sold_all and bought_lots else sold_known

        def avg(items, lots_of):
            priced = [(r["price"], lots_of(r)) for r in items if r.get("price") is not None]
            total = sum(l for _, l in priced)
            return (round(sum(p * l for p, l in priced) / total, 4), total) if total else (None, 0)

        avg_entry, priced_buy_lots = avg(buys, lambda r: r.get("lots") or 1)
        avg_exit, priced_sell_lots = avg(sells, lambda r: r.get("lots") or max(bought_lots, 1))
        closed_lots = min(bought_lots, sold_lots) if buys and sells else 0
        qty = closed_lots * lot_size if lot_size else None
        exchange = next((r.get("exchange") for r in rows if r.get("exchange")), "NFO")
        pnl = None
        complete_prices = (avg_entry is not None and avg_exit is not None
                           and priced_buy_lots >= bought_lots and (priced_sell_lots >= sold_lots or sold_all))
        if qty and complete_prices:
            pnl = round((avg_exit - avg_entry) * qty
                        - round_trip_costs(avg_entry, avg_exit, qty, exchange, orders=len(buys) + len(sells)), 2)
        trades[key] = {
            "key": key, "advisory_id": rows[0].get("advisory_id"),
            "tradingsymbol": next((r.get("tradingsymbol") for r in rows if r.get("tradingsymbol")), None),
            "session_date": rows[0]["session_date"], "underlying": rows[0].get("underlying"),
            "expiry": next((r.get("expiry") for r in rows if r.get("expiry")), None),
            "option": _option_label(rows[0]), "exchange": exchange, "lot_size": lot_size,
            "skipped": any(r["action"] == "SKIP" for r in rows) and not buys,
            "buys": [_fill(r) for r in buys], "sells": [_fill(r) for r in sells],
            "bought_lots": bought_lots, "sold_lots": sold_lots, "open_lots": max(bought_lots - sold_lots, 0),
            "avg_entry": avg_entry, "avg_exit": avg_exit, "qty": qty, "pnl": pnl,
            "estimated": any(r.get("price_basis") in ("ASK_AT_TAP", "BID_AT_TAP", "LTP_AT_TAP") for r in buys + sells),
            "first_buy_at": _dt(buys[0]["trade_at"]) if buys else None,
            "last_sell_at": _dt(sells[-1]["trade_at"]) if sells else None,
            "exit_without_buy": bool(sells) and not buys,
        }
    return trades


def _option_label(report: dict) -> str:
    strike = report.get("strike")
    if report.get("underlying") and strike:
        return f"{report['underlying']} {float(strike):g} {report.get('opt_type') or ''}".strip()
    return str(report.get("tradingsymbol") or "?")


def _fill(report: dict) -> dict:
    key = str(report.get("dedup_key") or "")
    return {"report_id": report["report_id"], "at": report["trade_at"], "lots": report.get("lots"),
            "price": report.get("price"), "price_basis": report.get("price_basis"),
            "source": report.get("source"), "time_basis": report.get("trade_at_basis"),
            "order_id": key[5:] if key.startswith("kite:") else None}


# ---------------------------------------------------------------------------
# analysis
# ---------------------------------------------------------------------------

def _flag(code: str, reason: str, impact: Optional[float] = None, *, why: str = "", better: str = "",
          better_pnl: Optional[float] = None, actual_pnl: Optional[float] = None) -> dict:
    """One mistake, explained for the partner:

    reason  what happened, with times and prices;
    why     why it matters, with the numbers of this trade;
    better  the better action and what it would have paid (after charges);
    advice  the rule for next time.

    ``impact_rs`` is actual minus better where both are known: the rupees
    this behaviour changed. Impacts of different flags can overlap."""
    return {"code": code, "title": TITLES[code], "reason": reason, "why": why, "better": better,
            "better_pnl": round(better_pnl, 2) if better_pnl is not None else None,
            "actual_pnl": round(actual_pnl, 2) if actual_pnl is not None else None,
            "impact_rs": round(impact, 2) if impact is not None else None, "advice": ADVICE[code]}


def _positive(code: str, reason: str) -> dict:
    return {"code": code, "title": POSITIVE_TITLES[code], "reason": reason}


def _pnl(entry: Optional[float], exit_: Optional[float], qty: Optional[int], exchange: str,
         orders: int = 2) -> Optional[float]:
    """Net P&L after charges; ``orders`` keeps a what-if on the same position
    charged for the same number of orders as what was done."""
    if entry is None or exit_ is None or not qty:
        return None
    return round((exit_ - entry) * qty - round_trip_costs(entry, exit_, qty, exchange, orders=orders), 2)


def _orders(trade: dict) -> int:
    """Orders in this trade, counting the exit still to come on an open one."""
    return max(len(trade["buys"]) + max(len(trade["sells"]), 1), 2)


def _amt(value: float) -> str:
    """An unsigned amount: ₹1,506."""
    return f"₹{abs(value):,.0f}"


def _instead(better: Optional[float], actual: Optional[float]) -> str:
    """'₹0 instead of −₹1,906', or just the better figure when the actual is unknown."""
    if better is None:
        return ""
    return f"{_rs(better)} instead of {_rs(actual)}" if actual is not None else _rs(better)


def _gap(actual: Optional[float], better: Optional[float]) -> Optional[float]:
    return round(actual - better, 2) if actual is not None and better is not None else None


def _worked(actual: Optional[float]) -> str:
    """Process over outcome: a rule-break that made money is still a rule-break."""
    if actual is not None and actual > 0:
        return f" It made {_rs(actual)} this time; the rule is about the risk taken, not about this result."
    return ""


def _day_close(day: str) -> datetime:
    return IST.localize(datetime.fromisoformat(day) + timedelta(hours=15, minutes=30))


def _first_under(series: list, after: datetime, level: float):
    """The first 5-minute print at or under ``level`` after ``after``."""
    return next(((ts, px) for ts, px in series if ts >= after and px <= level), None)


def _limit_print_after(card: dict, after: datetime):
    """A print at or under the buy-up-to after ``after`` and before the skip-after time."""
    limit, fill_by = card.get("buy_limit"), card.get("fill_by")
    if not (limit and fill_by and after):
        return None
    return next(((ts, px) for ts, px in card["series"] if after < ts <= fill_by and px <= limit), None)


def _chased(card: dict, trade: dict, first_px: float, first_qty: Optional[int]) -> dict:
    """ENTRY_ABOVE_LIMIT with the risk arithmetic of this entry."""
    limit, sl, target_low = card["buy_limit"], card.get("sl_premium"), card.get("target_low")
    first_at = _dt(trade["buys"][0]["at"])
    actual = trade["pnl"]
    over = first_px - limit
    reason = (f"The card said buy up to {_px(limit)}. You paid {_px(first_px)} at {_hhmm(first_at)}, "
              f"{_px(over)} ({over / limit:.1%}) more.")
    why = "Paying above the limit buys the same stop and target from a worse price."
    if sl and first_qty and limit > sl and first_px > sl:
        risk_card, risk_you = (limit - sl) * first_qty, (first_px - sl) * first_qty
        why = (f"The stop stays at {_px(sl)}, so a stop-out loses {_amt(risk_you)} instead of {_amt(risk_card)} "
               f"on {first_qty} qty ({risk_you / risk_card - 1:.0%} more)")
        if target_low:
            room_you, room_card = target_low - first_px, target_low - limit
            why += (f", while the first target {_px(target_low)} is {_px(room_you)} away instead of {_px(room_card)}."
                    if room_you > 0 else f", and you paid more than the first target {_px(target_low)}.")
        else:
            why += "."
    why += _worked(actual)
    better = f"Skip it, as the card says above the limit: {_instead(0.0, actual)}."
    wait = _limit_print_after(card, first_at)
    if wait:
        better += (f" Or wait with a limit order at {_px(limit)}: the option traded at {_px(wait[1])} at "
                   f"{_hhmm(wait[0])}, before the skip-after time.")
    return _flag("ENTRY_ABOVE_LIMIT", reason, _gap(actual, 0.0), why=why, better=better, better_pnl=0.0,
                 actual_pnl=actual)


def trade_stops(trade: dict, stops: list) -> list:
    """The partner's stops on this option placed while the trade was open."""
    first = trade.get("first_buy_at")
    if first is None or not trade.get("tradingsymbol"):
        return []
    end = (trade["last_sell_at"] if trade.get("last_sell_at") and not trade.get("open_lots")
           else _day_close(trade["session_date"]))
    out = []
    for stop in stops:
        placed = _dt(stop["placed_at"])
        if (stop["exchange"] == trade.get("exchange") and stop["tradingsymbol"] == trade["tradingsymbol"]
                and stop["status"] != "REJECTED" and placed is not None
                and first - STOP_CLOCK_SLACK <= placed <= end):
            out.append(stop | {"placed_dt": placed, "updated_dt": _dt(stop.get("updated_at"))})
    return sorted(out, key=lambda s: s["placed_dt"])


def _stop_checks(out: dict, trade: dict, card: Optional[dict], stops: Optional[list], qty: Optional[int],
                 exchange: str) -> None:
    """Stop discipline from Zerodha's order book. ``stops`` is None when the
    day's stops are unknown (no complete read, or GTTs unreadable): then
    nothing about stops is claimed."""
    first = trade.get("first_buy_at")
    if stops is None or first is None:
        return
    out["stops"] = [{"kind": s["kind"], "trigger": float(s["trigger_price"]), "status": s["status"],
                     "placed": _hhmm(s["placed_dt"]), "updated": _hhmm(s["updated_dt"])} for s in stops]
    flags, positives = out["flags"], out["positives"]
    actual, entry, exit_px, last_sell = trade["pnl"], trade["avg_entry"], trade["avg_exit"], trade["last_sell_at"]
    end = last_sell if last_sell and not trade["open_lots"] else _day_close(trade["session_date"])
    held = (end - first).total_seconds() / 60
    sl = (card or {}).get("sl_premium")
    n_orders = _orders(trade)
    if not stops:
        if held >= STOP_CHECK_MIN_HOLD_MIN:
            flags.append(_flag(
                "NO_STOP_ORDER",
                f"You bought at {_hhmm(first)} and held {held:.0f} min with no stop-loss order in Zerodha "
                f"(no SL order or GTT on this option).", None,
                why="Without a resting stop the exit depends on watching the screen; one distraction or a "
                    "fast fall and the loss has no floor.",
                better=(f"Place an SL order at the card's {_px(sl)} right after the buy fills." if sl else
                        "Decide the stop before buying and place the SL order right after the buy fills.")))
        return
    stop = stops[0]
    prompt = None
    trigger = float(stop["trigger_price"])
    after = (stop["placed_dt"] - first).total_seconds() / 60
    kind = "GTT" if stop["kind"] == "GTT" else "SL order"
    if sl and trigger < sl * (1 - STOP_WIDER_PCT):
        triggered = stop["status"] == "TRIGGERED"
        at_card = _pnl(entry, sl, qty, exchange, n_orders) if triggered else None
        why = "A wider stop is a bigger loss, not a safer trade."
        if entry is not None and qty and entry > trigger and entry > sl:
            why = (f"Your stop risked {_amt((entry - trigger) * qty)} instead of {_amt((entry - sl) * qty)} on "
                   f"{qty} qty. " + why)
        flags.append(_flag(
            "STOP_WIDER_THAN_CARD", f"Your {kind} was at {_px(trigger)}; the card's SL was {_px(sl)}.",
            _gap(actual, at_card), why=why,
            better=(f"The stop at the card's {_px(sl)}: {_instead(at_card, actual)}." if at_card is not None
                    else f"Put the stop at the card's {_px(sl)}."),
            better_pnl=at_card, actual_pnl=actual if at_card is not None else None))
    elif after <= STOP_PROMPT_MIN:
        prompt = _positive("STOP_PLACED", f"{kind} at {_px(trigger)} placed {max(after, 0):.0f} min after buying.")
    cancelled = [s for s in stops if s["status"] == "CANCELLED" and s["updated_dt"] and last_sell
                 and s["updated_dt"] < last_sell and s["updated_dt"].hour * 60 + s["updated_dt"].minute < SQUARE_OFF_MIN]
    protected_after = any(s["status"] in ("PENDING", "TRIGGERED") for s in stops
                          if cancelled and s["placed_dt"] > cancelled[-1]["updated_dt"])
    if cancelled and not protected_after and exit_px is not None:
        gone = cancelled[-1]
        level = float(gone["trigger_price"])
        if exit_px < level * (1 - STOP_CANCEL_SLIP_PCT):
            at_level = _pnl(entry, level, qty, exchange, n_orders)
            flags.append(_flag(
                "STOP_CANCELLED",
                f"You cancelled your stop at {_px(level)} at {_hhmm(gone['updated_dt'])} and sold at "
                f"{_px(exit_px)} at {_hhmm(last_sell)}.", _gap(actual, at_level),
                why="Cancelling a stop as the price gets close is hoping, not planning: the stop exists for "
                    "exactly that moment.",
                better=f"Leaving it in place: about {_instead(at_level, actual)}.", better_pnl=at_level,
                actual_pnl=actual))
    if prompt is not None and not any(f["code"] == "STOP_CANCELLED" for f in flags):
        positives.append(prompt)


def analyse_card(card: dict, trade: Optional[dict], reaction: timedelta, traded_known: bool = False,
                 stops: Optional[list] = None) -> dict:
    """One delivered card: the partner's action, the card's plan and the flags.

    ``traded_known``: the day's whole Zerodha book was read, so a card with
    no order was not traded (NOT_TRADED) rather than not reported.
    ``stops``: the partner's stops on this trade (None: unknown)."""
    out = {
        "advisory_id": card["advisory_id"], "underlying": card["underlying"], "day": card["day"],
        "time": _hhmm(card["delivered_at"]), "option": card["option"], "direction": card.get("direction"),
        "card": {k: card.get(k) for k in ("ask", "buy_limit", "sl_premium", "target_low", "target_premium",
                                         "lot_size")}
               | {"fill_by": _hhmm(card.get("fill_by")), "exit_by": _hhmm(card.get("exit_by"))},
        "card_messages": [{"type": u["event_type"], "at": _hhmm(u.get("delivered_at")),
                           "delivered": bool(u.get("delivered_at"))} for u in card.get("updates") or []],
        "prices_available": bool(card["series"]), "flags": [], "positives": [],
    }
    lot_size = card.get("lot_size") or (trade or {}).get("lot_size")
    exchange = card.get("exchange") or "NFO"
    if trade is None or (not trade["buys"] and not trade["sells"]):
        status = ("SKIPPED" if trade is not None and trade["skipped"]
                  else "NOT_TRADED" if traded_known else "NOT_REPORTED")
        label = {"SKIPPED": "Skipped", "NOT_TRADED": "Not traded", "NOT_REPORTED": "Not reported"}[status]
        entry = card_entry(card, reaction)
        plan = {"qty": lot_size, "entry": entry["price"], "entry_basis": entry["basis"]}
        if entry["skip"]:
            plan.update(pnl=0.0, note="card said skip: " + entry["note"])
        elif entry["price"] is not None:
            ex = card_exit(card, entry["at"], reaction)
            if ex:
                plan.update(exit=ex["price"], exit_at=_hhmm(ex["at"]), exit_reason=ex["reason"],
                            note=ex["note"], pnl=_pnl(entry["price"], ex["price"], lot_size, exchange))
        out.update(partner={"status": status}, plan=plan)
        if status in ("SKIPPED", "NOT_TRADED") and (plan.get("pnl") or 0) < 0:
            out["positives"].append(_positive("SKIP_SAVED", f"Following it would have been {_rs(plan['pnl'])} "
                                                            f"on 1 lot."))
        out["verdict"] = (f"{label}; the card on 1 lot: {_rs(plan.get('pnl'))}" if plan.get("pnl") is not None
                          else f"{label}; no option prices to score the card")
        return out

    out["partner"] = {k: trade[k] for k in ("buys", "sells", "bought_lots", "sold_lots", "open_lots", "avg_entry",
                                            "avg_exit", "qty", "pnl", "estimated", "exit_without_buy")}
    out["partner"]["status"] = "BOUGHT" if trade["buys"] else "EXIT_ONLY"
    qty = trade["qty"] or (trade["bought_lots"] * lot_size if lot_size else None)
    first_buy = trade["first_buy_at"]
    entry = trade["avg_entry"]
    actual = trade["pnl"]
    first_px = next((b["price"] for b in trade["buys"][:1] if b["price"] is not None), entry)
    n_orders = _orders(trade)
    first_qty = (trade["buys"][0].get("lots") or 1) * lot_size if trade["buys"] and lot_size else qty
    # Card exits on the partner's own entry.
    same_entry = None
    if first_buy is not None and entry is not None:
        ex = card_exit(card, first_buy, reaction)
        if ex:
            same_entry = {"exit": ex["price"], "exit_at": _hhmm(ex["at"]), "exit_at_dt": ex["at"],
                          "reason": ex["reason"], "note": ex["note"], "pnl": _pnl(entry, ex["price"], qty, exchange)}
    # Whole-card plan: a chased, late or after-close entry was a skip.
    closing = min((u for u in card.get("updates") or []
                   if u.get("delivered_at") and u["event_type"] in ("INVALIDATION", "TARGET_ZONE")),
                  key=lambda u: u["delivered_at"], default=None)
    tick = card.get("tick_size") or 0.05
    flags, positives = out["flags"], out["positives"]
    skip_reasons = []
    limit = card.get("buy_limit")
    sl = card.get("sl_premium")
    if first_px is not None and limit and first_px > limit + LIMIT_TOLERANCE_TICKS * tick:
        skip_reasons.append("price above the limit")
        flags.append(_chased(card, trade, first_px, first_qty))
    fill_by = card.get("fill_by")
    if first_buy and fill_by and first_buy > fill_by + reaction:
        late = int((first_buy - fill_by).total_seconds() // 60)
        skip_reasons.append("after the skip-after time")
        moved = (f" At {_hhmm(first_buy)} the option was {_px(first_px)} against the card's "
                 f"{_px(card.get('ask'))}, so the plan no longer fitted the price."
                 if first_px is not None and card.get("ask") else " After it the plan no longer fits the price.")
        flags.append(_flag(
            "LATE_ENTRY", f"The card's skip-after time was {_hhmm(fill_by)}. You bought at {_hhmm(first_buy)}, "
                          f"{late} min later.", _gap(actual, 0.0),
            why=f"The card's price, stop and target were set for an entry by {_hhmm(fill_by)}." + moved
                + _worked(actual),
            better=f"Let it go: {_instead(0.0, actual)}.", better_pnl=0.0, actual_pnl=actual))
    if first_px is not None and sl and first_px <= sl:
        # [O21-PX] The card's idea had failed before this buy: its stop is
        # above the entry, so none of its exits describe this trade.
        skip_reasons.append("price at or under the card's SL")
        same_entry = None
        flags.append(_flag(
            "ENTRY_UNDER_STOP", f"You bought at {_px(first_px)} at {_hhmm(first_buy)}; the card's SL was {_px(sl)}, so "
                                f"the card's idea had already failed.", _gap(actual, 0.0),
            why="Under the SL the card's plan no longer applies: there is no stop under you and no target that "
                "fits this price." + _worked(actual),
            better=f"No trade: {_instead(0.0, actual)}.", better_pnl=0.0, actual_pnl=actual))
    if first_buy and closing and first_buy > closing["delivered_at"]:
        failed = closing["event_type"] == "INVALIDATION"
        skip_reasons.append("after the card closed")
        flags.append(_flag(
            "AFTER_CARD_CLOSED", f"You bought at {_hhmm(first_buy)}; the card's "
                                 f"{'exit' if failed else 'target'} message came at {_hhmm(closing['delivered_at'])}.",
            _gap(actual, 0.0),
            why=("An exit message means the card's idea failed; buying after it trades an idea that is "
                 "already wrong." if failed else
                 "A target message means the planned move is mostly done; buying after it pays for a move "
                 "that has already happened.") + _worked(actual),
            better=f"No trade: {_instead(0.0, actual)}.", better_pnl=0.0, actual_pnl=actual))
    if skip_reasons:
        plan = {"pnl": 0.0, "note": "card said skip (" + ", ".join(skip_reasons) + ")"}
    elif same_entry is not None:
        plan = {"pnl": same_entry["pnl"], "note": same_entry["note"], "exit": same_entry["exit"],
                "exit_at": same_entry["exit_at"], "exit_reason": same_entry["reason"]}
    elif first_buy is None or entry is None:
        plan = {"pnl": None, "note": "buy price not reported: reply to the card with it to score the trade"}
    else:
        plan = {"pnl": None, "note": "no option prices recorded to price the card's exit"}
    plan["qty"] = qty
    out["plan"] = plan
    out["same_entry"] = {k: v for k, v in (same_entry or {}).items() if k != "exit_at_dt"} or None
    exit_px, last_sell = trade["avg_exit"], trade["last_sell_at"]
    if len(trade["buys"]) >= 2 and first_px:
        lower = [b for b in trade["buys"][1:] if b["price"] is not None
                 and b["price"] < first_px * (1 - AVERAGED_DOWN_PCT)]
        if lower:
            add = lower[0]
            first_lots = trade["buys"][0].get("lots") or 1
            only_first = (_pnl(first_px, exit_px, first_lots * lot_size, exchange, max(1 + len(trade["sells"]), 2))
                          if lot_size and not trade["open_lots"] else None)
            why = "Adding to a falling option raises the size exactly when the trade is going wrong"
            why += (f": {qty} qty were exposed instead of {first_lots * lot_size}." if qty and lot_size else ".")
            if sl:
                why += f" The card's stop at {_px(sl)} was the plan for a fall."
            flags.append(_flag(
                "AVERAGED_DOWN", f"First buy {_px(first_px)} at {str(trade['buys'][0]['at'])[11:16]}; you added "
                                 f"at {_px(add['price'])} at {str(add['at'])[11:16]}, "
                                 f"{1 - add['price'] / first_px:.1%} lower.", _gap(actual, only_first),
                why=why,
                better=(f"Only the first buy: {_instead(only_first, actual)}." if only_first is not None
                        else "Keep only the first buy and let the stop decide."),
                better_pnl=only_first, actual_pnl=actual))
    if exit_px is not None and qty:
        if sl and entry is not None and entry > sl and exit_px < sl * (1 - STOP_SLIPPAGE_PCT):
            under = _first_under(card["series"], first_buy, sl) if first_buy else None
            at_sl = _pnl(entry, sl, qty, exchange, n_orders)
            flags.append(_flag(
                "HELD_PAST_STOP",
                f"The card's SL was {_px(sl)}. You sold at {_px(exit_px)} at {_hhmm(last_sell)}"
                + (f"; the option was under the SL by {_hhmm(under[0])} (5-minute print {_px(under[1])})"
                   if under else "") + ".", _gap(actual, at_sl),
                why="The SL is the price where the card's idea is wrong. Holding past it turns a planned loss "
                    "into a bigger one, and options fall fast.",
                better=f"An SL order at {_px(sl)} right after buying would have sold near {_px(sl)} (a fast "
                       f"fall can fill a little lower): {_instead(at_sl, actual)}.",
                better_pnl=at_sl, actual_pnl=actual))
        elif (same_entry and same_entry["reason"] in ("STOP", "EXIT_MESSAGE") and last_sell
              and last_sell > same_entry["exit_at_dt"] + timedelta(minutes=STOP_LATE_MIN)
              and exit_px < same_entry["exit"]):
            word = "stop" if same_entry["reason"] == "STOP" else "exit message"
            at_card = _pnl(entry, same_entry["exit"], qty, exchange, n_orders)
            flags.append(_flag(
                "HELD_PAST_STOP",
                f"The card's {word} came at {same_entry['exit_at']} with the option at "
                f"{_px(same_entry['exit'])}; you sold at {_hhmm(last_sell)} for {_px(exit_px)}.",
                _gap(actual, at_card),
                why="Once the card says the idea is over, waiting is hoping for a comeback the plan does not "
                    "expect, and options fall fast.",
                better=f"Selling at the card's {word}: {_instead(at_card, actual)}.",
                better_pnl=at_card, actual_pnl=actual))
        if (same_entry and same_entry["reason"] in ("TARGET_MESSAGE", "SQUARE_OFF_MESSAGE", "EXIT_BY")
                and last_sell and last_sell < same_entry["exit_at_dt"] - timedelta(minutes=EARLY_EXIT_MIN)
                and same_entry["exit"] >= exit_px * (1 + EARLY_EXIT_PCT)):
            label = EXIT_LABELS[same_entry["reason"]]
            held = _pnl(entry, same_entry["exit"], qty, exchange, n_orders)
            flags.append(_flag(
                "EARLY_EXIT", f"You sold at {_hhmm(last_sell)} for {_px(exit_px)}. The card's {label} came at "
                              f"{same_entry['exit_at']} with the option at {_px(same_entry['exit'])}.",
                _gap(actual, held),
                why="Selling early on a wobble keeps the wins small while the stop still allows a full loss, so "
                    "the wins stop paying for the losses.",
                better=f"Holding with the SL order in place until the card's {label}: {_instead(held, actual)}.",
                better_pnl=held, actual_pnl=actual))
        target = next((u for u in card.get("updates") or [] if u["event_type"] == "TARGET_ZONE"
                       and u.get("delivered_at") and first_buy and u["delivered_at"] > first_buy), None)
        if target and last_sell and last_sell > target["delivered_at"] + timedelta(minutes=GAVE_BACK_MIN):
            at_target = print_at(card["series"], target["delivered_at"] + reaction)
            if at_target and exit_px <= at_target[1] * (1 - GAVE_BACK_PCT):
                booked = _pnl(entry, at_target[1], qty, exchange, n_orders)
                flags.append(_flag(
                    "GAVE_BACK_AFTER_TARGET",
                    f"The target message came at {_hhmm(target['delivered_at'])} with the option at "
                    f"{_px(at_target[1])}. You sold at {_hhmm(last_sell)} for {_px(exit_px)}.",
                    _gap(actual, booked),
                    why="A target message means most of the planned move is done; after it the option can fall "
                        "back as fast as it rose.",
                    better=f"Booking at the message: {_instead(booked, actual)}. Booking half and moving the SL "
                           f"to your entry also protects the rest.", better_pnl=booked, actual_pnl=actual))
    exit_by = card.get("exit_by")
    if exit_by and ((last_sell and last_sell > exit_by + timedelta(minutes=SQUARE_OFF_GRACE_MIN))
                    or (trade["open_lots"] and card.get("day_over"))):
        at_eb = last_print_before(card["series"], exit_by)
        eb_pnl = (_pnl(entry, at_eb[1], qty, exchange, n_orders)
                  if at_eb and first_buy and at_eb[0] >= first_buy and not trade["open_lots"] else None)
        flags.append(_flag(
            "HELD_PAST_SQUARE_OFF",
            f"Exit-by was {_hhmm(exit_by)}; " + (f"you sold at {_hhmm(last_sell)}." if last_sell and
                                                 not trade["open_lots"] else "no exit by the close."),
            _gap(actual, eb_pnl),
            why="Late in the day options lose time value fast and spreads widen; the card's plan ends at exit-by.",
            better=(f"Selling at {_hhmm(exit_by)} (option {_px(at_eb[1])}): {_instead(eb_pnl, actual)}."
                    if eb_pnl is not None and actual is not None and abs(eb_pnl - actual) >= 1
                    else f"Be out by {_hhmm(exit_by)}."),
            better_pnl=eb_pnl, actual_pnl=actual if eb_pnl is not None else None))
    _stop_checks(out, trade, card, stops, qty, exchange)
    if entry is not None and not skip_reasons:
        positives.append(_positive("BOUGHT_IN_LIMIT", f"Paid {_px(first_px)} with the limit at {_px(limit)}."))
    if (same_entry and last_sell and exit_px is not None
            and abs((last_sell - same_entry["exit_at_dt"]).total_seconds()) <= EARLY_EXIT_MIN * 60):
        positives.append(_positive("EXITED_WITH_CARD", f"Sold at {_hhmm(last_sell)} with the card's "
                                                       f"{same_entry['exit_at']} exit."))
    elif (same_entry and same_entry["reason"] == "STOP" and last_sell and exit_px is not None and sl
          and last_sell < same_entry["exit_at_dt"] and exit_px > sl):
        positives.append(_positive("EXITED_BEFORE_STOP", f"Sold at {_px(exit_px)} before the stop {_px(sl)} was "
                                                         f"hit: {_instead(actual, same_entry['pnl'])} at the stop."))
    if actual is not None and plan.get("pnl") is not None:
        out["verdict"] = f"You {_rs(actual)} · card plan {_rs(plan['pnl'])} · gap {_rs(actual - plan['pnl'])}"
    elif actual is not None:
        out["verdict"] = f"You {_rs(actual)} · the card could not be priced"
    else:
        out["verdict"] = "Prices incomplete: reply to the card with your buy and sell prices to score it"
    return out


def analyse_off_card(trade: dict, stops: Optional[list] = None) -> dict:
    actual = trade["pnl"]
    out = {"key": trade["key"], "day": trade["session_date"], "option": trade["option"],
           "time": _hhmm(trade["first_buy_at"] or trade["last_sell_at"]), "partner": {
               k: trade[k] for k in ("buys", "sells", "avg_entry", "avg_exit", "qty", "pnl", "estimated")},
           "flags": [], "positives": []}
    if trade["buys"]:
        what = f"You bought {trade['option']} at {_hhmm(trade['first_buy_at'])} without a card."
    else:
        what = f"You sold {trade['option']} at {_hhmm(trade['last_sell_at'])}; no card was sent for this option."
    out["flags"].append(_flag(
        "OFF_CARD", what, _gap(actual, 0.0),
        why="Without a card there is no written stop, target or exit time, so nothing limits the loss except "
            "a decision in the moment." + _worked(actual),
        better=f"No trade: {_instead(0.0, actual)}." if actual is None or actual <= 0 else
               "If you take one, decide the stop before buying and place it right after.",
        better_pnl=0.0, actual_pnl=actual))
    if trade["buys"]:
        qty = trade["qty"] or (trade["bought_lots"] * trade["lot_size"] if trade["lot_size"] else None)
        _stop_checks(out, trade, None, stops, qty, trade["exchange"])
    out["verdict"] = f"Off-card trade {_rs(actual)}" if actual is not None else "Off-card trade, prices incomplete"
    return out


def _sequence_flags(day_trades: list[dict]) -> None:
    """Re-entry soon after a loss and size up after a loss, in time order;
    a pause after a loss before the next card is a positive."""
    ordered = sorted((t for t in day_trades if t["_first_buy"] is not None), key=lambda t: t["_first_buy"])
    previous = None
    for item in ordered:
        if previous is not None and previous["_pnl"] is not None and previous["_pnl"] < 0 and previous["_last_sell"]:
            gap = (item["_first_buy"] - previous["_last_sell"]).total_seconds() / 60
            trade, actual = item["_trade"], item["_pnl"]
            if 0 <= gap <= REENTRY_WINDOW_MIN:
                extra = []
                if item.get("advisory_id") is None:
                    extra.append("without a card")
                if item["_lots"] > previous["_lots"]:
                    extra.append(f"with {item['_lots']} lots after {previous['_lots']}")
                why = ("A buy straight after a loss is the revenge pattern: the aim is to win the money back "
                       "quickly, not to follow a setup.")
                if actual is not None:
                    why += (f" This trade {'made' if actual > 0 else 'lost'} {_amt(actual)}, so the two trades "
                            f"together came to {_rs(previous['_pnl'] + actual)}.")
                item["flags"].append(_flag(
                    "QUICK_REENTRY_AFTER_LOSS",
                    f"You closed {previous['option']} at {_hhmm(previous['_last_sell'])} for "
                    f"{_rs(previous['_pnl'])} and bought {item['option']} {gap:.0f} min later"
                    + (" (" + ", ".join(extra) + ")" if extra else "") + ".", _gap(actual, 0.0),
                    why=why, better=f"Pause 30 minutes and wait for the next card. Without this trade: "
                                    f"{_instead(0.0, actual)}.", better_pnl=0.0, actual_pnl=actual))
            elif gap > REENTRY_WINDOW_MIN and item.get("advisory_id"):
                item["positives"].append(_positive(
                    "PAUSED_AFTER_LOSS", f"After the {_rs(previous['_pnl'])} exit at "
                                         f"{_hhmm(previous['_last_sell'])} you waited {gap:.0f} min and took a card."))
            if item["_lots"] > previous["_lots"]:
                lot = trade.get("lot_size")
                same_size = (_pnl(trade["avg_entry"], trade["avg_exit"], previous["_lots"] * lot, trade["exchange"],
                                  _orders(trade)) if lot and not trade["open_lots"] else None)
                why = "A bigger size after a loss makes the next loss bigger too."
                if lot:
                    why = (f"Each ₹1 move in the option was {_amt(item['_lots'] * lot)} instead of "
                           f"{_amt(previous['_lots'] * lot)}. " + why)
                item["flags"].append(_flag(
                    "SIZE_UP_AFTER_LOSS", f"{item['_lots']} lots right after a {_rs(previous['_pnl'])} trade "
                                          f"with {previous['_lots']}.", _gap(actual, same_size),
                    why=why, better=(f"The same {previous['_lots']} lot{'s' if previous['_lots'] != 1 else ''}: "
                                     f"{_instead(same_size, actual)}." if same_size is not None
                                     else "Keep the size you had before the loss."),
                    better_pnl=same_size, actual_pnl=actual))
        previous = item


def _overtrading(buys: int, cards: int, traded: list[dict]) -> dict:
    """Day flag: more buys than cards, with the charges and the cards-only day."""
    priced = [i["_trade"] for i in traded if i["_trade"]["pnl"] is not None]
    actual = round(sum(t["pnl"] for t in priced), 2) if priced and len(priced) == len(traded) else None
    charges = 0.0
    for t in priced:
        if t["avg_entry"] is not None and t["avg_exit"] is not None and t["qty"]:
            charges += (t["avg_exit"] - t["avg_entry"]) * t["qty"] - t["pnl"]
    card_only = (round(sum(i["_trade"]["pnl"] for i in traded if i.get("advisory_id") and not i.get("reentry")), 2)
                 if actual is not None else None)
    return _flag(
        "OVERTRADING", f"{buys} buys against {cards} card{'s' if cards != 1 else ''}.", _gap(actual, card_only),
        why="Extra trades come from watching the screen rather than from a setup"
            + (f"; today's trades paid {_amt(charges)} in charges." if charges > 0 else ".") + _worked(actual),
        better=(f"Only the card trades: {_instead(card_only, actual)}." if card_only is not None
                else "Trade the cards only."), better_pnl=card_only, actual_pnl=actual)


def analyse(cards: list[dict], reports: list[dict], *, reaction_sec: int, now: datetime,
            complete_days: frozenset = frozenset(), stops: Optional[list] = None,
            stops_known_days: frozenset = frozenset(), context: Optional[dict] = None) -> dict:
    """The coach view for the cards and reports in a window (pure).

    ``complete_days``: days whose whole Zerodha book was read after the close.
    ``stops`` / ``stops_known_days``: the partner's stop orders, and the days
    on which they are fully known (stop flags only on those days).
    ``context``: [O21-PX] price paths and the Zerodha book's details
    (partner_insights.Context); without it the analysis is as before."""
    import partner_insights as insights
    ctx = insights.Context.of(context, complete_days, now)
    reaction = timedelta(seconds=reaction_sec)
    trades = build_trades(reports)

    def stops_for(trade):
        if not trade or trade["session_date"] not in stops_known_days:
            return None
        return trade_stops(trade, stops or [])

    items = []
    by_card = {card["advisory_id"]: card for card in cards}
    for card in cards:
        card["day_over"] = now.astimezone(IST).date().isoformat() > card["day"] or (
            card.get("exit_by") is not None and now > card["exit_by"] + timedelta(minutes=SQUARE_OFF_GRACE_MIN))
        trade = trades.get(card["advisory_id"])
        item = analyse_card(card, trade, reaction, traded_known=card["day"] in complete_days,
                            stops=stops_for(trade))
        insights.apply(item, trade, card, stops_for(trade), ctx)
        item["_trade"] = trade
        items.append(item)
    # [O21-PX] The card's option bought again after a closed round trip: its
    # own trade, checked against the same card (late, after the card closed,
    # above the limit) and in the day's sequence (a re-entry after a loss).
    reentries = []
    for key, trade in trades.items():
        card = by_card.get(trade["advisory_id"]) if trade["advisory_id"] else None
        if card is None or key == trade["advisory_id"] or not trade["buys"]:
            continue
        item = analyse_card(card, trade, reaction, traded_known=card["day"] in complete_days,
                            stops=stops_for(trade))
        item.update(reentry=True, card_time=item["time"], time=_hhmm(trade["first_buy_at"]))
        insights.apply(item, trade, card, stops_for(trade), ctx)
        item["_trade"] = trade
        reentries.append(item)
    off_card = []
    for key, trade in trades.items():
        if trade["advisory_id"] in by_card:
            continue
        if trade["advisory_id"]:
            continue   # a card outside the window
        item = analyse_off_card(trade, stops_for(trade))
        insights.apply(item, trade, None, stops_for(trade), ctx)
        item["_trade"] = trade
        item["advisory_id"] = None
        off_card.append(item)
    # Sequence flags need every traded item of a day in time order.
    days: dict = defaultdict(list)
    for item in items + reentries + off_card:
        trade = item.get("_trade")
        if not trade or not trade["buys"]:
            continue
        item["_first_buy"] = trade["first_buy_at"]
        item["_last_sell"] = trade["last_sell_at"]
        item["_pnl"] = trade["pnl"]
        item["_lots"] = trade["bought_lots"]
        days[item["day"]].append(item)
    for day_items in days.values():
        _sequence_flags(day_items)
    day_rows = []
    all_days = sorted({c["day"] for c in cards} | {i["day"] for i in off_card}, reverse=True)
    for day in all_days:
        day_cards = [i for i in items if i["day"] == day]
        day_again = sorted((i for i in reentries if i["day"] == day), key=lambda i: i["time"])
        day_off = [i for i in off_card if i["day"] == day]
        traded = [i for i in day_cards + day_again + day_off if i.get("_trade") and i["_trade"]["buys"]]
        day_flags = []
        buys = sum(len(i["_trade"]["buys"]) for i in traded)
        actual = [i["_trade"]["pnl"] for i in traded if i["_trade"]["pnl"] is not None]
        if buys >= OVERTRADE_MIN_BUYS and buys > len(day_cards) + 1:
            day_flags.append(_overtrading(buys, len(day_cards), traded))
        plans = [i["plan"]["pnl"] for i in day_cards + day_again if i.get("_trade") and i["_trade"]["buys"]
                 and i.get("plan", {}).get("pnl") is not None and i["_trade"]["pnl"] is not None]
        row = {
            "day": day, "cards": [_public(i) for i in day_cards + day_again],
            "off_card": [_public(i) for i in day_off],
            "day_flags": day_flags,
            "actual_pnl": round(sum(actual), 2) if actual else None,
            "plan_pnl_on_traded_cards": round(sum(plans), 2) if plans else None,
            "stops_known": day in stops_known_days,
        }
        insights.day_details(row, ctx)
        day_rows.append(row)
    flagged = [f for row in day_rows for i in row["cards"] + row["off_card"] for f in i["flags"]] + \
              [f for row in day_rows for f in row["day_flags"]]
    leaks: dict = {}
    for flag in flagged:
        leak = leaks.setdefault(flag["code"], {"code": flag["code"], "title": flag["title"], "count": 0,
                                               "impact_rs": 0.0, "priced": 0, "advice": flag["advice"]})
        leak["count"] += 1
        if flag["impact_rs"] is not None:
            leak["impact_rs"] = round(leak["impact_rs"] + flag["impact_rs"], 2)
            leak["priced"] += 1
    traded_items = [i for i in items + reentries + off_card if i.get("_trade") and i["_trade"]["buys"]]
    scored = [i for i in traded_items if i["_trade"]["pnl"] is not None]
    plan_pairs = [(i["_trade"]["pnl"], i["plan"]["pnl"]) for i in items + reentries
                  if i.get("_trade") and i["_trade"]["buys"]
                  and i["_trade"]["pnl"] is not None and i.get("plan", {}).get("pnl") is not None]
    reported = [r for r in reports if r.get("status") == "ACTIVE"]
    summary = {
        "cards_delivered": len(cards),
        "cards_bought": sum(1 for i in items if i["partner"]["status"] == "BOUGHT"),
        "cards_skipped": sum(1 for i in items if i["partner"]["status"] == "SKIPPED"),
        "cards_not_reported": sum(1 for i in items if i["partner"]["status"] == "NOT_REPORTED"),
        "cards_not_traded": sum(1 for i in items if i["partner"]["status"] == "NOT_TRADED"),
        "off_card_trades": len(off_card),
        "card_reentries": len(reentries),
        "trades_scored": len(scored),
        "actual_pnl": round(sum(i["_trade"]["pnl"] for i in scored), 2) if scored else None,
        "actual_pnl_on_cards": round(sum(a for a, _ in plan_pairs), 2) if plan_pairs else None,
        "plan_pnl_on_same_cards": round(sum(p for _, p in plan_pairs), 2) if plan_pairs else None,
        "unreported_cards_plan_pnl": round(sum(i["plan"]["pnl"] for i in items
                                               if i["partner"]["status"] in ("NOT_REPORTED", "SKIPPED", "NOT_TRADED")
                                               and i["plan"].get("pnl") is not None), 2),
        "followed_cards": sum(1 for i in items if not i["flags"] and i["partner"]["status"] == "BOUGHT"),
    }
    if summary["actual_pnl_on_cards"] is not None:
        summary["gap_vs_plan"] = round(summary["actual_pnl_on_cards"] - summary["plan_pnl_on_same_cards"], 2)
    quality = {
        "reports": len(reported),
        "estimated_prices": sum(1 for r in reported if r.get("price_basis") in ("ASK_AT_TAP", "BID_AT_TAP", "LTP_AT_TAP")),
        "missing_prices": sum(1 for r in reported if r["action"] in ("BUY", "SELL") and r.get("price") is None),
        "exits_without_buy": sum(1 for t in trades.values() if t["exit_without_buy"]),
        "open_without_exit": sum(1 for t in trades.values() if t["open_lots"] and t["buys"]),
        "cards_without_prices": sum(1 for c in cards if not c["series"]),
    }
    return {
        "summary": summary,
        "leaks": sorted(leaks.values(), key=lambda l: (l["impact_rs"], -l["count"])),
        "days": day_rows,
        "data_quality": quality,
        "assumptions": {
            "reaction_sec": reaction_sec,
            "card_prices": "5-minute option prints stored by the analytics tick; a touch between prints can be missed",
            "partner_prices": "Zerodha fills (exact price and exchange time) where the partner logged in; "
                              "otherwise as reported, and ≈ prices came from a quote at the tap",
            "plan_entry_for_unbought_cards": "the first 5-minute print after the card plus the reaction time",
            "costs": "current F&O charges per contract segment, ₹20 per order",
        },
        "automatic_execution": False,
        "blocks_cards": False,
    }


def _public(item: dict) -> dict:
    return {k: v for k, v in item.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

_PATH_DDL = """
CREATE TABLE IF NOT EXISTS partner_coach_card_paths (
  advisory_id TEXT PRIMARY KEY,
  session_date TEXT NOT NULL,
  series_json TEXT NOT NULL,
  frozen_at TEXT NOT NULL
)
"""


async def init_partner_coach_db(db_path: str) -> None:
    from partner_fill_capture import init_partner_fill_db
    await init_partner_fill_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(_PATH_DDL)
        await db.commit()


async def _live_series(db_path: str, card: dict) -> list:
    import fno_oi_store
    start = card["delivered_at"].astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")
    try:
        rows = await fno_oi_store.strike_ltp_series(
            db_path, card["underlying"], card["day"], str(card["expiry"]), float(card["strike"]),
            str(card["opt_type"]), from_ts=start)
    except (aiosqlite.Error, ValueError, TypeError):
        return []
    return [(_dt(ts), float(ltp)) for ts, ltp in rows]


async def load_cards(db_path: str, first_day: str, last_day: str) -> list[dict]:
    """Delivered buyer cards in [first_day, last_day] with updates and prices."""
    await init_partner_coach_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        try:
            delivered = await (await db.execute(
                "SELECT kind, dedup_key, sent_at, detail FROM partner_hedge_messages "
                "WHERE kind IN (?,?) AND delivered=1", (CARD_KIND, UPDATE_KIND))).fetchall()
            ideas = await (await db.execute(
                "SELECT advisory_id, underlying, payload FROM partner_advisory_ideas")).fetchall()
            updates = await (await db.execute(
                "SELECT update_id, advisory_id, event_type, observed_at FROM partner_advisory_updates")).fetchall()
            frozen = dict(await (await db.execute(
                "SELECT advisory_id, series_json FROM partner_coach_card_paths "
                "WHERE session_date>=? AND session_date<=?", (first_day, last_day))).fetchall())
        except aiosqlite.OperationalError:
            return []
    sent = {}
    for kind, key, sent_at, _detail in delivered:
        sent[(kind, key)] = _dt(sent_at)
    payloads = {aid: (underlying, payload) for aid, underlying, payload in ideas}
    by_card: dict = defaultdict(list)
    for update_id, advisory_id, event_type, observed_at in updates:
        by_card[advisory_id].append({"event_type": event_type, "observed_at": observed_at,
                                     "delivered_at": sent.get((UPDATE_KIND, update_id))})
    cards = []
    for (kind, key), delivered_at in sent.items():
        if kind != CARD_KIND or key not in payloads or delivered_at is None:
            continue
        underlying, payload_json = payloads[key]
        try:
            payload = json.loads(payload_json)
        except (TypeError, ValueError):
            continue
        day = str(payload.get("session_date") or delivered_at.date().isoformat())
        if not first_day <= day <= last_day:
            continue
        view = payload.get("buyer_view") or {}
        if not view.get("strike"):
            continue
        card = {
            "advisory_id": key, "underlying": underlying, "day": day, "delivered_at": delivered_at,
            "direction": payload.get("direction"),
            "option": f"{underlying} {float(view['strike']):g} {view.get('opt_type')}",
            "strike": view["strike"], "opt_type": view.get("opt_type"), "expiry": view.get("expiry"),
            "lot_size": view.get("lot_size"), "exchange": view.get("fee_segment") or "NFO",
            "tick_size": view.get("tick_size") or 0.05, "ask": view.get("ask"),
            "buy_limit": view.get("buy_limit"), "sl_premium": view.get("sl_premium"),
            "target_premium": view.get("target_premium"), "target_low": view.get("target_premium_low"),
            "fill_by": _dt(view.get("fill_by")),
            "exit_by": _dt(payload.get("management_deadline")),
            "updates": sorted(by_card.get(key, []), key=lambda u: str(u["observed_at"])),
        }
        if key in frozen:
            card["series"] = [(_dt(ts), float(px)) for ts, px in json.loads(frozen[key])]
        else:
            card["series"] = await _live_series(db_path, card)
        cards.append(card)
    cards.sort(key=lambda c: c["delivered_at"])
    return cards


async def freeze_card_paths(db_path: str, day: str, now: Optional[datetime] = None) -> int:
    """Keep a day's card price paths past the 7-day OI purge."""
    now = now or datetime.now(IST)
    cards = await load_cards(db_path, day, day)
    frozen = 0
    async with aiosqlite.connect(db_path) as db:
        for card in cards:
            if not card["series"]:
                continue
            series = [(ts.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S"), px) for ts, px in card["series"]]
            await db.execute(
                "INSERT OR REPLACE INTO partner_coach_card_paths(advisory_id,session_date,series_json,frozen_at) "
                "VALUES(?,?,?,?)", (card["advisory_id"], day, json.dumps(series), now.isoformat()))
            frozen += 1
        await db.commit()
    return frozen


async def load_partner_coach(db_path: str, *, days: int = 30, now: Optional[datetime] = None) -> dict:
    now = (now or datetime.now(IST)).astimezone(IST)
    days = max(1, min(int(days), 120))
    last_day = now.date().isoformat()
    first_day = (now.date() - timedelta(days=days - 1)).isoformat()
    from partner_fill_capture import reports_between
    import partner_broker_sync as zerodha
    cards = await load_cards(db_path, first_day, last_day)
    broker = await zerodha.broker_days(db_path, first_day, last_day)
    reports, superseded = zerodha_first(await reports_between(db_path, first_day, last_day), broker)
    complete = frozenset(day for day, row in broker.items() if row["complete"])
    known = frozenset(day for day, row in broker.items() if row["complete"] and row["stops_known"])
    from partner_trade_paths import load_paths
    context = await zerodha.book_details(db_path, first_day, last_day)
    context["paths"] = await load_paths(db_path, first_day, last_day)
    view = analyse(cards, reports, reaction_sec=int(settings.PARTNER_COACH_REACTION_SEC), now=now,
                   complete_days=complete, stops=await zerodha.stop_orders(db_path, first_day, last_day),
                   stops_known_days=known, context=context)
    view["data_quality"]["superseded_by_zerodha"] = superseded
    view["window"] = {"first_day": first_day, "last_day": last_day, "days": days}
    view["capture_enabled"] = bool(settings.PARTNER_FILL_CAPTURE_ENABLED)
    view["zerodha"] = zerodha.status(now) | {"days": broker}
    view["as_of"] = now.isoformat()
    return view


def zerodha_first(reports: list[dict], broker: dict) -> tuple[list[dict], int]:
    """On a day read from Zerodha its fills replace typed or tapped BUY/SELL
    reports up to the read (the whole day once the read was after the close).
    Skips stay: Zerodha cannot tell a decision to skip from a missed card."""
    kept, superseded = [], 0
    for report in reports:
        day = broker.get(report.get("session_date"))
        traded_at = _dt(report.get("trade_at"))
        if (day and report.get("status") == "ACTIVE" and report.get("source") != "ZERODHA"
                and report.get("action") in ("BUY", "SELL")
                and (day["complete"] or (traded_at is not None and traded_at <= _dt(day["synced_at"])))):
            superseded += 1
            continue
        kept.append(report)
    return kept, superseded


# ---------------------------------------------------------------------------
# the evening note to the partner
# ---------------------------------------------------------------------------

def render_coach_note(view: dict, day: str) -> Optional[str]:
    """The evening Telegram note: the day's lesson first (partner_lessons.py)."""
    from partner_lessons import day_review, render_note
    return render_note(day_review(view, day))


async def partner_coach_eod(now: Optional[datetime] = None) -> dict:
    """Freeze today's card prices, then send the note when trades were reported.

    With Zerodha configured the note waits for a read of the whole day (the
    partner's evening login, or the wrap's own read when a login is held),
    so it is never built from a partial book."""
    from partner_bot import partner_enabled, send_partner, send_partner_result
    import partner_broker_sync as zerodha
    now = (now or datetime.now(IST)).astimezone(IST)
    day = now.date().isoformat()
    db_path = settings.DB_PATH
    frozen = await freeze_card_paths(db_path, day, now)
    if not (settings.PARTNER_COACH_NOTE_ENABLED and partner_enabled()):
        return {"frozen": frozen, "note": "disabled"}
    from partner_orchestrator import _record, _seen
    if await _seen(db_path, "coach", day):
        return {"frozen": frozen, "note": "already_sent"}
    if zerodha.configured() and not (await zerodha.broker_days(db_path, day, day)).get(day, {}).get("complete"):
        return {"frozen": frozen, "note": "awaiting_zerodha"}
    view = await load_partner_coach(db_path, days=1, now=now)
    text = render_coach_note(view, day)
    if text is None:
        return {"frozen": frozen, "note": "no_reported_trades"}
    keyboard = zerodha.review_keyboard("📒 Open full review")
    if keyboard is not None:
        ok = (await send_partner_result(text, kind="coach", reply_markup=keyboard)).delivered
    else:
        ok = await send_partner(text, kind="coach")
    await _record(db_path, "coach", day, ok, now=now)
    return {"frozen": frozen, "note": "sent" if ok else "failed"}
