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

ADVICE = {
    "ENTRY_ABOVE_LIMIT": "If the price is above the card's buy-up-to, skip it. A chased entry moves the "
                         "stop further away and raises the loss at SL.",
    "LATE_ENTRY": "After the card's skip-after time the move has mostly happened; let it go.",
    "AFTER_CARD_CLOSED": "Once the card's exit or target message has come, the idea is finished.",
    "OFF_CARD": "A trade without a card has no stop or target written down. If you take one, "
                "decide the SL before buying.",
    "QUICK_REENTRY_AFTER_LOSS": "After a loss, wait for the next card instead of re-entering. "
                                "A 30-minute pause stops a revenge trade.",
    "SIZE_UP_AFTER_LOSS": "Keep the same size after a loss. Size up only after a run of trades that "
                          "followed the card.",
    "AVERAGED_DOWN": "Don't add to an option that is falling. The card's SL is the plan.",
    "HELD_PAST_STOP": "Place the SL order right after buying, as the card says. It exits for you, "
                      "even when you are busy.",
    "EARLY_EXIT": "Let the card's target or exit message decide. Keep the SL order in place "
                  "instead of selling on a wobble.",
    "GAVE_BACK_AFTER_TARGET": "When the target message comes, book at least part and move the SL to "
                              "your entry on the rest.",
    "HELD_PAST_SQUARE_OFF": "Be flat by the card's exit-by time. Options lose value fast late in the day.",
    "OVERTRADING": "More trades than cards usually means trading on feel. Stick to the cards.",
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
}
POSITIVE_TITLES = {
    "BOUGHT_IN_LIMIT": "Bought inside the limit and on time",
    "EXITED_WITH_CARD": "Exited with the card",
    "SKIP_SAVED": "Skipping saved money",
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
    return {"price": found[1], "at": found[0], "basis": "5MIN_PRINT", "skip": False}


# ---------------------------------------------------------------------------
# the partner's trades
# ---------------------------------------------------------------------------

def build_trades(reports: list[dict]) -> dict:
    """Group ACTIVE reports into one trade per card (or off-card contract/day)."""
    groups: dict = defaultdict(list)
    for report in reports:
        if report.get("status") != "ACTIVE":
            continue
        key = report.get("advisory_id") or (
            f"off:{report['session_date']}:{report.get('underlying')}:{report.get('strike')}:{report.get('opt_type')}")
        groups[key].append(report)
    trades = {}
    for key, rows in groups.items():
        rows.sort(key=lambda r: (str(r["trade_at"]), r["report_id"]))
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
            "session_date": rows[0]["session_date"], "underlying": rows[0].get("underlying"),
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
    return {"report_id": report["report_id"], "at": report["trade_at"], "lots": report.get("lots"),
            "price": report.get("price"), "price_basis": report.get("price_basis"),
            "source": report.get("source"), "time_basis": report.get("trade_at_basis")}


# ---------------------------------------------------------------------------
# analysis
# ---------------------------------------------------------------------------

def _flag(code: str, reason: str, impact: Optional[float] = None) -> dict:
    return {"code": code, "title": TITLES[code], "reason": reason,
            "impact_rs": round(impact, 2) if impact is not None else None, "advice": ADVICE[code]}


def _pnl(entry: Optional[float], exit_: Optional[float], qty: Optional[int], exchange: str) -> Optional[float]:
    if entry is None or exit_ is None or not qty:
        return None
    return round((exit_ - entry) * qty - round_trip_costs(entry, exit_, qty, exchange), 2)


def analyse_card(card: dict, trade: Optional[dict], reaction: timedelta, traded_known: bool = False) -> dict:
    """One delivered card: the partner's action, the card's plan and the flags.

    ``traded_known``: the day's whole Zerodha book was read, so a card with
    no order was not traded (NOT_TRADED) rather than not reported."""
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
            out["positives"].append({"code": "SKIP_SAVED", "title": POSITIVE_TITLES["SKIP_SAVED"],
                                     "reason": f"Following it would have been {_rs(plan['pnl'])} on 1 lot."})
        out["verdict"] = (f"{label}; the card on 1 lot: {_rs(plan.get('pnl'))}" if plan.get("pnl") is not None
                          else f"{label}; no option prices to score the card")
        return out

    out["partner"] = {k: trade[k] for k in ("buys", "sells", "bought_lots", "sold_lots", "open_lots", "avg_entry",
                                            "avg_exit", "qty", "pnl", "estimated", "exit_without_buy")}
    out["partner"]["status"] = "BOUGHT" if trade["buys"] else "EXIT_ONLY"
    qty = trade["qty"] or (trade["bought_lots"] * lot_size if lot_size else None)
    first_buy = trade["first_buy_at"]
    entry = trade["avg_entry"]
    # Card exits on the partner's own entry.
    same_entry = None
    if first_buy is not None and entry is not None:
        ex = card_exit(card, first_buy, reaction)
        if ex:
            same_entry = {"exit": ex["price"], "exit_at": _hhmm(ex["at"]), "exit_at_dt": ex["at"],
                          "reason": ex["reason"], "note": ex["note"], "pnl": _pnl(entry, ex["price"], qty, exchange)}
    # Whole-card plan: a chased, late or after-close entry was a skip.
    closed_by = min((u["delivered_at"] for u in card.get("updates") or []
                     if u.get("delivered_at") and u["event_type"] in ("INVALIDATION", "TARGET_ZONE")), default=None)
    tick = card.get("tick_size") or 0.05
    flags, positives = out["flags"], out["positives"]
    skip_reasons = []
    limit = card.get("buy_limit")
    if entry is not None and limit and entry > limit + LIMIT_TOLERANCE_TICKS * tick:
        extra = (entry - limit) * (qty or 0)
        skip_reasons.append("price above the limit")
        flags.append(_flag("ENTRY_ABOVE_LIMIT",
                           f"Paid {_px(entry)}, {_px(entry - limit)} ({(entry - limit) / limit:.1%}) above the "
                           f"card's buy-up-to {_px(limit)}.", -extra if qty else None))
    fill_by = card.get("fill_by")
    if first_buy and fill_by and first_buy > fill_by + reaction:
        late = int((first_buy - fill_by).total_seconds() // 60)
        skip_reasons.append("after the skip-after time")
        flags.append(_flag("LATE_ENTRY", f"Bought at {_hhmm(first_buy)}, {late} min after the card's skip-after "
                                         f"time {_hhmm(fill_by)}.", trade["pnl"]))
    if first_buy and closed_by and first_buy > closed_by:
        skip_reasons.append("after the card closed")
        flags.append(_flag("AFTER_CARD_CLOSED", f"Bought at {_hhmm(first_buy)}; the card's exit/target message "
                                                f"came at {_hhmm(closed_by)}.", trade["pnl"]))
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
    if len(trade["buys"]) >= 2:
        first_px = trade["buys"][0]["price"]
        lower = [b for b in trade["buys"][1:] if b["price"] is not None and first_px
                 and b["price"] < first_px * (1 - AVERAGED_DOWN_PCT)]
        if lower:
            flags.append(_flag("AVERAGED_DOWN", f"First buy {_px(first_px)}, added at {_px(lower[0]['price'])} "
                                                f"({str(lower[0]['at'])[11:16]}) while it was falling."))
    exit_px, last_sell = trade["avg_exit"], trade["last_sell_at"]
    sl = card.get("sl_premium")
    if exit_px is not None and qty:
        if sl and exit_px < sl * (1 - STOP_SLIPPAGE_PCT):
            flags.append(_flag("HELD_PAST_STOP", f"Sold at {_px(exit_px)}; the card's SL was {_px(sl)} "
                                                 f"({_rs((exit_px - sl) * qty)} more on {qty} qty).",
                               (exit_px - sl) * qty))
        elif (same_entry and same_entry["reason"] in ("STOP", "EXIT_MESSAGE") and last_sell
              and last_sell > same_entry["exit_at_dt"] + timedelta(minutes=STOP_LATE_MIN)
              and exit_px < same_entry["exit"]):
            flags.append(_flag("HELD_PAST_STOP", f"The card's exit came at {same_entry['exit_at']} "
                                                 f"({_px(same_entry['exit'])}); you sold at {_hhmm(last_sell)} for "
                                                 f"{_px(exit_px)}.", (exit_px - same_entry["exit"]) * qty))
        if (same_entry and same_entry["reason"] in ("TARGET_MESSAGE", "SQUARE_OFF_MESSAGE", "EXIT_BY")
                and last_sell and last_sell < same_entry["exit_at_dt"] - timedelta(minutes=EARLY_EXIT_MIN)
                and same_entry["exit"] >= exit_px * (1 + EARLY_EXIT_PCT)):
            flags.append(_flag("EARLY_EXIT", f"Sold at {_hhmm(last_sell)} for {_px(exit_px)}; the card's "
                                             f"{same_entry['reason'].replace('_', ' ').lower()} came at "
                                             f"{same_entry['exit_at']} with the option at {_px(same_entry['exit'])}.",
                               (exit_px - same_entry["exit"]) * qty))
        target = next((u for u in card.get("updates") or [] if u["event_type"] == "TARGET_ZONE"
                       and u.get("delivered_at") and first_buy and u["delivered_at"] > first_buy), None)
        if target and last_sell and last_sell > target["delivered_at"] + timedelta(minutes=GAVE_BACK_MIN):
            at_target = print_at(card["series"], target["delivered_at"] + reaction)
            if at_target and exit_px <= at_target[1] * (1 - GAVE_BACK_PCT):
                flags.append(_flag("GAVE_BACK_AFTER_TARGET", f"Target message at {_hhmm(target['delivered_at'])} "
                                                             f"(option {_px(at_target[1])}); you sold at "
                                                             f"{_hhmm(last_sell)} for {_px(exit_px)}.",
                                   (exit_px - at_target[1]) * qty))
    exit_by = card.get("exit_by")
    if exit_by and ((last_sell and last_sell > exit_by + timedelta(minutes=SQUARE_OFF_GRACE_MIN))
                    or (trade["open_lots"] and card.get("day_over"))):
        flags.append(_flag("HELD_PAST_SQUARE_OFF",
                           f"Exit-by was {_hhmm(exit_by)}; " + (f"you sold at {_hhmm(last_sell)}."
                                                              if last_sell else "no exit reported.")))
    if entry is not None and not skip_reasons:
        positives.append({"code": "BOUGHT_IN_LIMIT", "title": POSITIVE_TITLES["BOUGHT_IN_LIMIT"],
                          "reason": f"Paid {_px(entry)} with the limit at {_px(limit)}."})
    if (same_entry and last_sell and exit_px is not None
            and abs((last_sell - same_entry["exit_at_dt"]).total_seconds()) <= EARLY_EXIT_MIN * 60):
        positives.append({"code": "EXITED_WITH_CARD", "title": POSITIVE_TITLES["EXITED_WITH_CARD"],
                          "reason": f"Sold at {_hhmm(last_sell)} with the card's {same_entry['exit_at']} exit."})
    actual = trade["pnl"]
    if actual is not None and plan.get("pnl") is not None:
        out["verdict"] = f"You {_rs(actual)} · card plan {_rs(plan['pnl'])} · gap {_rs(actual - plan['pnl'])}"
    elif actual is not None:
        out["verdict"] = f"You {_rs(actual)} · the card could not be priced"
    else:
        out["verdict"] = "Prices incomplete: reply to the card with your buy and sell prices to score it"
    return out


def analyse_off_card(trade: dict) -> dict:
    out = {"key": trade["key"], "day": trade["session_date"], "option": trade["option"],
           "time": _hhmm(trade["first_buy_at"] or trade["last_sell_at"]), "partner": {
               k: trade[k] for k in ("buys", "sells", "avg_entry", "avg_exit", "qty", "pnl", "estimated")},
           "flags": [_flag("OFF_CARD", "No card was sent for this option.", trade["pnl"])], "positives": []}
    out["verdict"] = f"Off-card trade {_rs(trade['pnl'])}" if trade["pnl"] is not None else "Off-card trade, prices incomplete"
    return out


def _sequence_flags(day_trades: list[dict]) -> None:
    """Re-entry soon after a loss and size up after a loss, in time order."""
    ordered = sorted((t for t in day_trades if t["_first_buy"] is not None), key=lambda t: t["_first_buy"])
    previous = None
    for item in ordered:
        if previous is not None and previous["_pnl"] is not None and previous["_pnl"] < 0 and previous["_last_sell"]:
            gap = (item["_first_buy"] - previous["_last_sell"]).total_seconds() / 60
            if 0 <= gap <= REENTRY_WINDOW_MIN:
                extra = []
                if item.get("advisory_id") is None:
                    extra.append("without a card")
                if item["_lots"] > previous["_lots"]:
                    extra.append(f"with {item['_lots']} lots after {previous['_lots']}")
                item["flags"].append(_flag(
                    "QUICK_REENTRY_AFTER_LOSS",
                    f"Bought {gap:.0f} min after a {_rs(previous['_pnl'])} exit on {previous['option']}"
                    + (" (" + ", ".join(extra) + ")" if extra else "") + ".", item["_pnl"]))
            if item["_lots"] > previous["_lots"]:
                item["flags"].append(_flag(
                    "SIZE_UP_AFTER_LOSS", f"{item['_lots']} lots right after a {_rs(previous['_pnl'])} trade "
                                          f"with {previous['_lots']}.", item["_pnl"]))
        previous = item


def analyse(cards: list[dict], reports: list[dict], *, reaction_sec: int, now: datetime,
            complete_days: frozenset = frozenset()) -> dict:
    """The coach view for the cards and reports in a window (pure).

    ``complete_days``: days whose whole Zerodha book was read after the close."""
    reaction = timedelta(seconds=reaction_sec)
    trades = build_trades(reports)
    items = []
    by_card = {card["advisory_id"]: card for card in cards}
    for card in cards:
        card["day_over"] = now.astimezone(IST).date().isoformat() > card["day"] or (
            card.get("exit_by") is not None and now > card["exit_by"] + timedelta(minutes=SQUARE_OFF_GRACE_MIN))
        trade = trades.get(card["advisory_id"])
        item = analyse_card(card, trade, reaction, traded_known=card["day"] in complete_days)
        item["_trade"] = trade
        items.append(item)
    off_card = []
    for key, trade in trades.items():
        if trade["advisory_id"] in by_card:
            continue
        if trade["advisory_id"]:
            continue   # a card outside the window
        item = analyse_off_card(trade)
        item["_trade"] = trade
        item["advisory_id"] = None
        off_card.append(item)
    # Sequence flags need every traded item of a day in time order.
    days: dict = defaultdict(list)
    for item in items + off_card:
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
        day_off = [i for i in off_card if i["day"] == day]
        traded = [i for i in day_cards + day_off if i.get("_trade") and i["_trade"]["buys"]]
        day_flags = []
        buys = sum(len(i["_trade"]["buys"]) for i in traded)
        if buys >= OVERTRADE_MIN_BUYS and buys > len(day_cards) + 1:
            day_flags.append(_flag("OVERTRADING", f"{buys} buys against {len(day_cards)} card(s)."))
        actual = [i["_trade"]["pnl"] for i in traded if i["_trade"]["pnl"] is not None]
        plans = [i["plan"]["pnl"] for i in day_cards if i.get("_trade") and i["_trade"]["buys"]
                 and i.get("plan", {}).get("pnl") is not None and i["_trade"]["pnl"] is not None]
        day_rows.append({
            "day": day, "cards": [_public(i) for i in day_cards], "off_card": [_public(i) for i in day_off],
            "day_flags": day_flags,
            "actual_pnl": round(sum(actual), 2) if actual else None,
            "plan_pnl_on_traded_cards": round(sum(plans), 2) if plans else None,
        })
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
    traded_items = [i for i in items + off_card if i.get("_trade") and i["_trade"]["buys"]]
    scored = [i for i in traded_items if i["_trade"]["pnl"] is not None]
    plan_pairs = [(i["_trade"]["pnl"], i["plan"]["pnl"]) for i in items if i.get("_trade") and i["_trade"]["buys"]
                  and i["_trade"]["pnl"] is not None and i.get("plan", {}).get("pnl") is not None]
    reported = [r for r in reports if r.get("status") == "ACTIVE"]
    summary = {
        "cards_delivered": len(cards),
        "cards_bought": sum(1 for i in items if i["partner"]["status"] == "BOUGHT"),
        "cards_skipped": sum(1 for i in items if i["partner"]["status"] == "SKIPPED"),
        "cards_not_reported": sum(1 for i in items if i["partner"]["status"] == "NOT_REPORTED"),
        "cards_not_traded": sum(1 for i in items if i["partner"]["status"] == "NOT_TRADED"),
        "off_card_trades": len(off_card),
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
    view = analyse(cards, reports, reaction_sec=int(settings.PARTNER_COACH_REACTION_SEC), now=now,
                   complete_days=complete)
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
    """Four or five short lines for a day with reported trades, else ``None``."""
    row = next((r for r in view["days"] if r["day"] == day), None)
    if row is None:
        return None
    traded = [i for i in row["cards"] + row["off_card"] if i.get("partner", {}).get("buys")]
    if not traded:
        return None
    from_zerodha = any(f.get("source") == "ZERODHA" for i in traded
                       for f in i["partner"].get("buys", []) + i["partner"].get("sells", []))
    lines = ["📒 Your trades today (from Zerodha)" if from_zerodha
             else "📒 Your trades today (from your taps and replies)"]
    head = f"{len(traded)} trade{'s' if len(traded) != 1 else ''}"
    if row["actual_pnl"] is not None:
        head += f" · {_rs(row['actual_pnl'])} after charges"
    if row["plan_pnl_on_traded_cards"] is not None:
        head += f" · card plan {_rs(row['plan_pnl_on_traded_cards'])}"
    lines.append(head)
    flags = [(f, i) for i in traded for f in i["flags"]] + [(f, None) for f in row["day_flags"]]
    priced = [(f, i) for f, i in flags if f["impact_rs"] is not None and f["impact_rs"] < 0]
    if priced:
        flag, item = min(priced, key=lambda pair: pair[0]["impact_rs"])
        lines.append(f"Biggest gap: {item['option'] + ' · ' if item else ''}{flag['reason']}")
        lines.append(f"Next time: {flag['advice']}")
    elif flags:
        flag, item = flags[0]
        lines.append(f"Watch: {flag['title']} · {flag['reason']}")
    goods = [p for i in traded for p in i.get("positives", [])]
    if goods:
        names = sorted({p["title"] for p in goods})
        lines.append("✅ " + " · ".join(names[:2]))
    if any(i["partner"].get("estimated") for i in traded):
        lines.append("≈ prices came from your taps; reply to a card with your price to correct.")
    return "\n".join(lines[:6])


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
