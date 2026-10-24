"""[O21-PL 2026-10-21] The partner's daily review: today's learnings first.

partner_coach.analyse() finds what happened on each card and why it
mattered. This module turns one day of that into what the partner reads in
the evening, in this order:

  1. the day in one line: trades, P&L after charges, and the cards as
     written on the same trades;
  2. the lesson of the day: the mistake that cost the most (or, when nothing
     was lost, the most important rule broken), with what happened, why it
     matters, what would have been better and what it would have paid, and
     the rule for next time; repeated mistakes are grouped;
  3. the other lessons, shorter;
  4. what went well (so the habits to keep are said out loud);
  5. each trade as a story: the card, each buy and sell, stops and card
     messages in time order, and the result against the card;
  6. the cards not taken, neutrally: not taking a card is always allowed.

progress() is the "see more" view over the window: patterns this week
against last week, how many trades followed their card, and the streak of
clean trading days.

[O21-PX] Also: each trade checked against six rules (card, entry, stop,
exit, calm after a loss, size) plus the day's own (only the cards, orders
within the cash), counted as "rules kept" -- the score is about process,
not money; what the option did around each trade (partner_insights.py) in
plain lines and a small chart; the day's numbers (wins, losses, charges,
time in the market, the share of the account); and over the window the
trade statistics a trader learns from (win rate, average win against
average loss, card against no-card trades, trades soon after a loss, hold
time of winners against losers, time of day) with a plain line for each
pattern the numbers show, and the one rule to focus on tomorrow.

[O23-PH] The partner can open an earlier day: ``day_review(view, day,
today)`` then says "that day" where it would say "today". [O23-PM] Each rule
under "rules kept" carries a plain ``means`` line (RULE_MEANINGS).
partner_review_pdf.py prints one day's review as a PDF. [O24-SZ] The size
rule is "Usual size": the partner's own habit, not a fixed tenth of the cash.

Pure functions over the coach view; nothing here places orders or changes
a card. Wording rules: numbers come from the coach; a rule-break that made
money is still named (process over outcome); nothing is called a maximum
or breakeven.
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import median
from typing import Optional

from partner_coach import REENTRY_WINDOW_MIN, _amt, _dt, _rs

# When two mistakes cost the same, the one earlier here is the lesson. The
# order follows the damage they do to a manual option buyer: revenge and
# size first, then entries that break the card, then stop discipline.
LESSON_PRIORITY = (
    "QUICK_REENTRY_AFTER_LOSS", "SIZE_UP_AFTER_LOSS", "UNUSUAL_SIZE", "ENTRY_ABOVE_LIMIT", "CHASED_SPIKE",
    "HELD_PAST_STOP", "STOP_CANCELLED", "STOP_LOWERED", "NO_STOP_ORDER", "AVERAGED_DOWN", "OFF_CARD",
    "GAVE_BACK_PROFIT", "OVERTRADING", "INSUFFICIENT_FUNDS", "PRICE_RAISED_TO_FILL", "LATE_ENTRY",
    "AFTER_CARD_CLOSED", "ENTRY_UNDER_STOP", "HELD_OVERNIGHT", "STOP_WIDER_THAN_CARD", "GAVE_BACK_AFTER_TARGET",
    "EARLY_EXIT", "HELD_PAST_SQUARE_OFF",
)
# [O21-PX] The rules each trade is checked against. A rule is broken by any
# of its flags; "rules kept" counts kept checks, not money.
CHECKS = (
    ("card", "Traded a card", ("OFF_CARD",)),
    ("entry", "Entered as planned", ("ENTRY_ABOVE_LIMIT", "LATE_ENTRY", "AFTER_CARD_CLOSED", "ENTRY_UNDER_STOP",
                                     "CHASED_SPIKE", "PRICE_RAISED_TO_FILL")),
    ("stop", "Stop placed and kept", ("NO_STOP_ORDER", "STOP_WIDER_THAN_CARD", "STOP_CANCELLED", "STOP_LOWERED")),
    ("exit", "Exited by the plan", ("HELD_PAST_STOP", "EARLY_EXIT", "GAVE_BACK_AFTER_TARGET", "GAVE_BACK_PROFIT",
                                    "HELD_PAST_SQUARE_OFF", "HELD_OVERNIGHT")),
    ("calm", "Calm after a loss", ("QUICK_REENTRY_AFTER_LOSS", "SIZE_UP_AFTER_LOSS")),
    ("size", "Usual size", ("AVERAGED_DOWN", "UNUSUAL_SIZE")),
)
DAY_CHECKS = (
    ("cards_only", "Traded only the cards", ("OVERTRADING",)),
    ("cash", "Orders within your cash", ("INSUFFICIENT_FUNDS",)),
)
_RULE_ORDER = [key for key, _, _ in CHECKS + DAY_CHECKS]
# [O23-PM] What each rule means, in the partner's words (shown under "Rules
# kept" on the page and in the PDF). Each line matches the flags that break
# the rule above and their thresholds in partner_coach / partner_insights.
RULE_MEANINGS = {
    "card": "The trade was on a card the system sent you on Telegram that day: the same option, bought after the "
            "card arrived. A trade on any other option counts as a trade without a card.",
    "entry": "On a card: bought at or under its buy-up-to price, before its skip-after time, before its exit or "
             "target message and above its SL. On every trade: not straight after a 20% jump, and without raising "
             "your price again and again to get filled.",
    "stop": "A stop-loss order (an SL order or a GTT) was in Zerodha for the trade, no wider than the card's SL, and "
            "was not cancelled or moved down. Checked only on days your stop orders could be read; a trade held "
            "under 5 minutes needs none.",
    "exit": "Sold as the plan said: when the stop was hit, not long before the card's exit, soon after a target "
            "message, by the exit-by time and before the close; and a trade up 20% did not end as a loss.",
    "calm": "No new buy within 30 minutes of closing a losing trade, and no bigger size after a loss.",
    "size": "The money put into the trade was not much more than you usually put in (at most 1.5 times your usual "
            "share of cash, from your last 20 trades; checked once you have 5), and you did not buy more of a "
            "falling option.",
    "cards_only": "No more buys in the day than the cards sent plus one (two buys are always within it).",
    "cash": "Zerodha refused none of your buys for lack of money. Checked only when your order book was read.",
}
# Time-of-day buckets for the window statistics (minutes after midnight, IST).
TIME_BUCKETS = (("09:15–09:45", 555, 585), ("09:45–11:30", 585, 690), ("11:30–13:30", 690, 810),
                ("13:30–15:40", 810, 940))   # [O24-MC] F&O closes at 15:40
MIN_SAMPLE = 3                 # trades per side before a window pattern is put into words
MAX_MORE_LESSONS = 4
MAX_ALSO = 3          # [O21-PX] other mistakes told inside the lesson; the rest go to "more"
STATUS_TEXT = {"SKIPPED": "Skipped", "NOT_TRADED": "Not traded", "NOT_REPORTED": "Not reported"}
MESSAGE_TEXT = {"INVALIDATION": "Card: exit — the idea failed", "TARGET_ZONE": "Card: target zone reached",
                "SESSION_EXIT_REMINDER": "Card: square-off reminder"}
ESTIMATES = ("ASK_AT_TAP", "BID_AT_TAP", "LTP_AT_TAP")


def _priority(code: str) -> int:
    return LESSON_PRIORITY.index(code) if code in LESSON_PRIORITY else len(LESSON_PRIORITY)


def _px(value) -> str:
    if value is None:
        return "?"
    return "₹" + f"{value:,.2f}".rstrip("0").rstrip(".")


def _lots(lots) -> str:
    lots = lots or 1
    return f"{lots} lot{'s' if lots != 1 else ''}"


def _traded(item: dict) -> bool:
    partner = item.get("partner") or {}
    return bool(partner.get("buys") or partner.get("sells"))


# ---------------------------------------------------------------------------
# lessons
# ---------------------------------------------------------------------------

def lessons(row: dict) -> list[dict]:
    """The day's mistakes grouped by kind, the most costly first."""
    groups: dict = {}
    for item in row["cards"] + row["off_card"]:
        for flag in item["flags"]:
            groups.setdefault(flag["code"], []).append((item, flag))
    for flag in row["day_flags"]:
        groups.setdefault(flag["code"], []).append((None, flag))
    out = []
    for code, pairs in groups.items():
        priced = [f["impact_rs"] for _, f in pairs if f["impact_rs"] is not None]
        first = pairs[0][1]
        out.append({
            "code": code, "title": first["title"], "rule": first["advice"], "count": len(pairs),
            "impact_rs": round(sum(priced), 2) if priced else None,
            "examples": [{"option": item["option"] if item else None, "time": item["time"] if item else None,
                          "what": f["reason"], "why": f.get("why", ""), "better": f.get("better", ""),
                          "actual_pnl": f.get("actual_pnl"), "better_pnl": f.get("better_pnl"),
                          "impact_rs": f["impact_rs"]} for item, f in pairs],
        })

    return sorted(out, key=_rank)


def _rank(lesson: dict) -> tuple:
    cost = lesson["impact_rs"] if lesson["impact_rs"] is not None and lesson["impact_rs"] < 0 else 0.0
    return (0 if cost < 0 else 1, cost, _priority(lesson["code"]))


def _fold(lesson_list: list[dict]) -> tuple[Optional[dict], list[dict]]:
    """The lesson of the day, with the other mistakes made on the same trade
    told as part of it ("also on this trade"), then the remaining lessons.
    One revenge trade is one story, not three lessons repeating its loss."""
    if not lesson_list:
        return None, []
    main = dict(lesson_list[0])
    trades = {(e["option"], e["time"]) for e in main["examples"] if e["option"]}
    folded, kept = [], {}
    for lesson in lesson_list[1:]:
        for example in lesson["examples"]:
            if (example["option"], example["time"]) in trades:
                folded.append((lesson, example))
            else:
                kept.setdefault(lesson["code"], (lesson, []))[1].append(example)
    # [O21-PX] The first few (in the lessons' own order: cost, then priority)
    # are told in the lesson; the others stay as their own shorter lessons so
    # the main one stays readable.
    main["also"] = [{"code": lesson["code"], "title": lesson["title"], "what": e["what"], "why": e["why"],
                     "better": e["better"], "rule": lesson["rule"]} for lesson, e in folded[:MAX_ALSO]]
    for lesson, example in folded[MAX_ALSO:]:
        kept.setdefault(lesson["code"], (lesson, []))[1].append(example)
    rest = []
    for lesson, examples in kept.values():
        priced = [e["impact_rs"] for e in examples if e["impact_rs"] is not None]
        rest.append(lesson | {"examples": examples, "count": len(examples),
                              "impact_rs": round(sum(priced), 2) if priced else None})
    return main, sorted(rest, key=_rank)


def _well_done(row: dict, traded: list[dict], lesson_list: list[dict], on_day: str = "today") -> list[dict]:
    seen, out = set(), []
    for item in row["cards"] + row["off_card"]:
        for good in item.get("positives", []):
            key = (good["code"], item["option"])
            if key in seen:
                continue
            seen.add(key)
            out.append({"code": good["code"], "title": good["title"], "reason": good["reason"],
                        "option": item["option"]})
    if traded and not lesson_list:
        out.insert(0, {"code": "CLEAN_DAY", "title": "Every trade followed its card",
                       "reason": f"{len(traded)} trade{'s' if len(traded) != 1 else ''} {on_day} and no mistakes "
                                 f"flagged. This is the habit to repeat.", "option": None})
    return out


# ---------------------------------------------------------------------------
# rules kept
# ---------------------------------------------------------------------------

def trade_checks(item: dict) -> list[dict]:
    """Each rule for one trade, kept or broken. The stop rule counts only when
    the day's stops were readable, or a stop was seen moving."""
    codes = {f["code"] for f in item["flags"]}
    out = []
    for key, name, broken_by in CHECKS:
        broken = bool(codes & set(broken_by))
        if key == "stop" and "stops" not in item and not broken:
            continue
        out.append({"key": key, "name": name, "kept": not broken})
    return out


def score(row: dict, traded: list[dict]) -> Optional[dict]:
    """Rules kept on a day: every trade's checks plus the day's own."""
    if not traded:
        return None
    checks = [check for item in traded for check in trade_checks(item)]
    day_codes = {f["code"] for f in row["day_flags"]}
    for key, name, broken_by in DAY_CHECKS:
        if key == "cash" and "orders" not in row:
            continue   # Zerodha's order book was not read: refusals are unknown
        checks.append({"key": key, "name": name, "kept": not day_codes & set(broken_by)})
    rules: dict = {}
    for check in checks:
        rule = rules.setdefault(check["key"], {"key": check["key"], "name": check["name"], "kept": 0, "of": 0,
                                               "means": RULE_MEANINGS[check["key"]]})
        rule["of"] += 1
        rule["kept"] += int(check["kept"])
    kept = sum(1 for check in checks if check["kept"])
    return {"kept": kept, "of": len(checks), "pct": round(100 * kept / len(checks)),
            "rules": sorted(rules.values(), key=lambda r: _RULE_ORDER.index(r["key"]))}


# ---------------------------------------------------------------------------
# trade stories
# ---------------------------------------------------------------------------

_RISK_TEXT = {"STOP": "to your stop", "CARD_SL": "to the card's stop", "NO_STOP": "with no stop order",
              "PREMIUM": "in premium paid"}


def option_lines(insight: Optional[dict], on_day: str = "today") -> list[str]:
    """What the option did around the trade, in plain lines."""
    if not insight:
        return []
    lines = []
    before = insight.get("before")
    if before and before["run_pct"] >= 0.10:
        lines.append(f"Before you bought: up {before['run_pct']:.0%} in {before['minutes']} minutes "
                     f"(from {_px(before['low'])}).")
    best, worst = insight.get("best"), insight.get("worst")
    if best and worst:
        span = "to the close" if insight.get("held_to_close") else f"{insight['hold_min']} min"
        lines.append(f"While you held ({span}): best {_px(best['price'])} at {best['at']} ({_rs(best['move_rs'])} "
                     f"open), worst {_px(worst['price'])} at {worst['at']} ({_rs(worst['move_rs'])} open).")
    edge = insight.get("edge")
    if edge:
        # [A22-P5] Seen only in the minute of the buy or the sale: maybe outside the holding.
        span = (f"{_px(edge['low'])}–{_px(edge['high'])}" if edge["high"] - edge["low"] >= 0.05
                else _px(edge["low"]))
        lines.append(f"In the minute you bought or sold it also traded at {span}; that may have been before your "
                     "buy or after your sale.")
    after = insight.get("after")
    if after:
        between = (f" (it traded {_px(after['low'])}–{_px(after['high'])} in between)"
                   if after["high"] - after["low"] >= 0.05 else "")
        lines.append(f"{after['minutes']} min after you sold: {_px(after['price'])}{between}.")
    risk = insight.get("risk")
    if risk:
        lines.append(f"At risk: {_amt(risk['rs'])} {_RISK_TEXT[risk['basis']]}, {risk['pct_of_cash']:.0%} of your "
                     f"cash {on_day}.")
    if insight.get("charges") is not None and insight.get("gross_pnl") is not None:
        lines.append(f"Charges: {_amt(insight['charges'])} on a {_rs(insight['gross_pnl'])} price move.")
    if insight.get("basis") == "5MIN_PRINTS" and (best or after):
        lines.append("These prices are 5-minute prints; a quick move between them can be missed.")
    return lines

def _fill_text(verb: str, fill: dict) -> str:
    price = fill.get("price")
    mark = "≈" if fill.get("price_basis") in ESTIMATES else ""
    shown = f"{mark}{_px(price)}" if price is not None else "an unreported price"
    return f"You {verb} {_lots(fill.get('lots'))} at {shown}" if fill.get("lots") else f"You {verb} at {shown}"


def story(item: dict, on_day: str = "today") -> dict:
    """One traded card (or off-card trade) as a time-ordered story."""
    events = []
    card = item.get("card")
    if card:
        parts = [f"buy up to {_px(card.get('buy_limit'))} (ask {_px(card.get('ask'))})"]
        if card.get("sl_premium"):
            parts.append(f"SL {_px(card['sl_premium'])}")
        if card.get("target_low") or card.get("target_premium"):
            parts.append(f"target {_px(card.get('target_low'))}–{_px(card.get('target_premium'))}")
        parts.append(f"skip after {card.get('fill_by')}, exit by {card.get('exit_by')}")
        events.append({"at": item.get("card_time") or item["time"], "who": "card", "text": "Card: " + ", ".join(parts)})
    for message in item.get("card_messages") or []:
        if message.get("delivered"):
            events.append({"at": message["at"], "who": "card",
                           "text": MESSAGE_TEXT.get(message["type"], "Card: " + message["type"].lower())})
    same_entry = item.get("same_entry") or {}
    if same_entry.get("reason") == "STOP":
        events.append({"at": same_entry["exit_at"], "who": "card",
                       "text": f"The option reached the card's SL {_px(card.get('sl_premium'))}"})
    elif same_entry.get("reason") == "EXIT_BY":
        events.append({"at": same_entry["exit_at"], "who": "card",
                       "text": f"The card's exit-by time (option {_px(same_entry.get('exit'))})"})
    partner = item.get("partner") or {}
    for fill in partner.get("buys") or []:
        events.append({"at": str(fill["at"])[11:16], "who": "you", "text": _fill_text("bought", fill),
                       "sort_key": str(fill["at"])})
    for stop in item.get("stops") or []:
        kind = "a GTT stop" if stop["kind"] == "GTT" else "an SL order"
        # [O24-SR] Without the order's history only "in place by" this time is known.
        events.append({"at": stop["placed"], "who": "you",
                       "text": (f"You placed {kind} at {_px(stop['trigger'])}" if stop.get("exact", True) else
                                f"By this time you had an SL order at {_px(stop['trigger'])}")})
        if stop["status"] == "CANCELLED":
            events.append({"at": stop["updated"], "who": "you", "text": f"You cancelled the stop at {_px(stop['trigger'])}"})
    for fill in partner.get("sells") or []:
        events.append({"at": str(fill["at"])[11:16], "who": "you", "text": _fill_text("sold", fill),
                       "sort_key": str(fill["at"])})
    insight = item.get("insight") or {}
    events += [dict(event) for event in insight.get("events") or []]
    # Same minute: the card first, then the partner's actions to the second.
    events.sort(key=lambda e: (e["at"], 0 if e["who"] == "card" else 1, str(e.get("sort_key", ""))[11:19]))
    events = [{k: v for k, v in e.items() if k != "sort_key"} for e in events]
    pnl = partner.get("pnl")
    plan = (item.get("plan") or {}).get("pnl")
    if pnl is not None and card:
        result = f"Result {_rs(pnl)} after charges; the card as written: {_rs(plan)}." if plan is not None \
            else f"Result {_rs(pnl)} after charges; the card could not be priced."
    elif pnl is not None:
        result = f"Result {_rs(pnl)} after charges, without a card."
    else:
        result = "Prices incomplete, so the result is not scored."
    return {"option": item["option"], "time": item["time"], "on_card": bool(card),
            "reentry": bool(item.get("reentry")), "advisory_id": item.get("advisory_id"), "pnl": pnl, "plan_pnl": plan if card else None,
            "estimated": bool(partner.get("estimated")), "timeline": events, "result": result,
            "mistakes": [f["title"] for f in item["flags"]], "good": [g["title"] for g in item.get("positives", [])],
            "checks": trade_checks(item), "option_lines": option_lines(insight, on_day), "chart": insight.get("chart"),
            "numbers": {k: insight.get(k) for k in ("hold_min", "held_to_close", "best", "worst", "before", "after",
                                                   "risk", "gross_pnl", "charges", "basis", "edge")} if insight else None}


# ---------------------------------------------------------------------------
# the day
# ---------------------------------------------------------------------------

def day_review(view: dict, day: str, today: Optional[str] = None) -> dict:
    """Everything the partner reads about one day, the lesson first.

    [O23-PH] ``today`` (the session date now) words an earlier day as "that
    day"; without it the day is read as today (the evening note)."""
    past = today is not None and day < today
    on_day = "that day" if past else "today"
    row = next((r for r in view["days"] if r["day"] == day), None)
    zerodha_day = ((view.get("zerodha") or {}).get("days") or {}).get(day)
    if row is None:
        return {"day": day, "headline": {"trades": 0, "text": "No cards and no trades on this day."},
                "lesson": None, "more_lessons": [], "well_done": [], "trades": [],
                "untaken": {"cards": [], "total_plan_pnl": None, "text": ""}, "notes": [], "source": None,
                "score": None, "stats": None, "account": None, "orders": None, "open_positions": []}
    traded = sorted([i for i in row["cards"] + row["off_card"] if _traded(i)], key=lambda i: i["time"])
    lesson_list = lessons(row)
    main, rest = _fold(lesson_list)
    off = [i for i in traded if not i.get("card")]
    if traded:
        text = f"{len(traded)} trade{'s' if len(traded) != 1 else ''}"
        text += f" · {_rs(row['actual_pnl'])} after charges" if row["actual_pnl"] is not None else " · prices incomplete"
        if row["plan_pnl_on_traded_cards"] is not None:
            text += f" · following the cards exactly: {_rs(row['plan_pnl_on_traded_cards'])}"
        if off:
            text += f" · {len(off)} without a card"
    else:
        text = f"No trades {on_day}." + (f" {len(row['cards'])} card{'s were' if len(row['cards']) != 1 else ' was'} "
                                         f"sent." if row["cards"] else "")
    untaken = [i for i in row["cards"] if not _traded(i)]
    plan_total = [i["plan"]["pnl"] for i in untaken if i.get("plan", {}).get("pnl") is not None]
    fills = [f for i in traded for f in i["partner"].get("buys", []) + i["partner"].get("sells", [])]
    from_zerodha = any(f.get("source") == "ZERODHA" for f in fills)
    notes = []
    if fills and not from_zerodha:
        notes.append("Prices are from your Telegram taps and replies; ≈ marks an estimate.")
    if zerodha_day and not zerodha_day.get("complete"):
        # Kite returns only the current day's orders: a past day read before the close stays partial.
        notes.append(f"Zerodha was read at {str(zerodha_day.get('synced_at'))[11:16]}, before the close: "
                     + ("trades after that are not in this review." if past else "later trades are not here yet."))
    if zerodha_day and zerodha_day.get("complete") and not zerodha_day.get("stops_known"):
        notes.append("Stop orders could not be read for this day, so the stop-loss checks are off.")
    if row["cards"]:
        notes.append("The card's results use 5-minute prices; a quick touch between them can be missed.")
    if row.get("carried_in"):
        notes.append("You started the day holding " + ", ".join(p["tradingsymbol"] for p in row["carried_in"])
                     + " from an earlier day; selling it shows without its buy and is not scored.")
    if row.get("open_positions"):
        notes.append("Still open when Zerodha was read: " + ", ".join(
            f"{p['tradingsymbol']} ({p['quantity']} qty)" for p in row["open_positions"]) + ".")
    account = row.get("account")
    return {
        "day": day, "source": "ZERODHA" if from_zerodha else ("REPORTS" if fills else None),
        "headline": {"trades": len(traded), "off_card_trades": len(off), "pnl": row["actual_pnl"],
                     "plan_pnl": row["plan_pnl_on_traded_cards"], "text": text,
                     "account_pct": (account or {}).get("pnl_pct")},
        "score": score(row, traded),
        "stats": day_stats(traded),
        "account": account,
        "orders": row.get("orders"),
        "open_positions": row.get("open_positions") or [],
        "lesson": main,
        "more_lessons": rest[:MAX_MORE_LESSONS],
        "well_done": _well_done(row, traded, lesson_list, on_day),
        "trades": [story(i, on_day) for i in traded],
        "untaken": {
            "cards": [{"option": i["option"], "time": i["time"], "status": STATUS_TEXT.get(i["partner"]["status"],
                                                                                         i["partner"]["status"]),
                       "plan_pnl": i.get("plan", {}).get("pnl"), "note": i.get("plan", {}).get("note")}
                      for i in untaken],
            "total_plan_pnl": round(sum(plan_total), 2) if plan_total else None,
            "text": ("Not taking a card is always allowed. For learning, here is what each card did on 1 lot."
                     if untaken else ""),
        },
        "notes": notes,
    }


def day_stats(traded: list[dict]) -> Optional[dict]:
    """The day's numbers over its scored trades (charges only when every
    trade's are known)."""
    scored = [i for i in traded if (i.get("partner") or {}).get("pnl") is not None]
    if not scored:
        return None
    pnls = [i["partner"]["pnl"] for i in scored]
    gross = [(i.get("insight") or {}).get("gross_pnl") for i in scored]
    charges = [(i.get("insight") or {}).get("charges") for i in scored]
    holds = [(i.get("insight") or {}).get("hold_min") for i in traded]
    holds = [h for h in holds if h is not None]
    return {"trades": len(scored), "wins": sum(1 for p in pnls if p > 0), "losses": sum(1 for p in pnls if p < 0),
            "best": max(pnls), "worst": min(pnls),
            "gross_pnl": round(sum(gross), 2) if None not in gross else None,
            "charges": round(sum(charges), 2) if None not in charges else None,
            "time_in_market_min": sum(holds) if holds else None}


def active_days(view: dict) -> list[str]:
    """Days with a card or a trade, newest first."""
    return [r["day"] for r in view["days"]]


# ---------------------------------------------------------------------------
# progress ("see more")
# ---------------------------------------------------------------------------

def progress(view: dict, today: str) -> dict:
    """Patterns this week against last week, discipline and the clean streak."""
    end = date.fromisoformat(today)
    last_week = {(end - timedelta(days=n)).isoformat() for n in range(7)}
    week_before = {(end - timedelta(days=n)).isoformat() for n in range(7, 14)}
    patterns: dict = {}
    per_day = []
    trades_total = clean_total = 0
    for row in sorted(view["days"], key=lambda r: r["day"]):
        traded = [i for i in row["cards"] + row["off_card"] if _traded(i)]
        flags = [(i, f) for i in row["cards"] + row["off_card"] for f in i["flags"]] + \
                [(None, f) for f in row["day_flags"]]
        clean = [i for i in traded if not i["flags"]]
        trades_total += len(traded)
        clean_total += len(clean)
        for _, flag in flags:
            entry = patterns.setdefault(flag["code"], {"code": flag["code"], "title": flag["title"],
                                                       "rule": flag["advice"], "total": 0, "last_7_days": 0,
                                                       "previous_7_days": 0, "impact_rs": 0.0, "priced": 0})
            entry["total"] += 1
            entry["last_7_days"] += row["day"] in last_week
            entry["previous_7_days"] += row["day"] in week_before
            if flag["impact_rs"] is not None:
                entry["impact_rs"] = round(entry["impact_rs"] + flag["impact_rs"], 2)
                entry["priced"] += 1
        day_score = score(row, traded)
        per_day.append({"day": row["day"], "trades": len(traded), "pnl": row["actual_pnl"],
                        "plan_pnl": row["plan_pnl_on_traded_cards"], "mistakes": len(flags),
                        "clean": bool(traded) and not flags,
                        "rules_kept_pct": day_score["pct"] if day_score else None})
    for entry in patterns.values():
        last, before = entry["last_7_days"], entry["previous_7_days"]
        entry["trend"] = "fewer" if last < before else "more" if last > before else "same"
    streak = 0
    for day in sorted((d for d in per_day if d["trades"]), key=lambda d: d["day"], reverse=True):
        if not day["clean"]:
            break
        streak += 1
    pnls = [d["pnl"] for d in per_day if d["pnl"] is not None]
    plans = [d["plan_pnl"] for d in per_day if d["plan_pnl"] is not None]
    recent = [p for p in patterns.values() if p["last_7_days"]]
    focus = None
    if recent:
        top = min(recent, key=lambda p: (-p["last_7_days"], p["impact_rs"] if p["priced"] else 0.0,
                                         _priority(p["code"])))
        focus = {"code": top["code"], "title": top["title"], "rule": top["rule"], "count": top["last_7_days"],
                 "text": f"{top['title']}: {top['last_7_days']} time{'s' if top['last_7_days'] != 1 else ''} in "
                         f"the last 7 days."}
    return {
        "days": list(reversed(per_day)),
        "focus": focus,
        "stats": window_stats(view),
        "patterns": sorted(patterns.values(), key=lambda p: (p["impact_rs"] if p["priced"] else 0.0,
                                                             -p["total"], _priority(p["code"]))),
        "trades": trades_total, "clean_trades": clean_total,
        "clean_rate": round(clean_total / trades_total, 3) if trades_total else None,
        "clean_streak_days": streak,
        "pnl": round(sum(pnls), 2) if pnls else None,
        "plan_pnl_on_traded_cards": round(sum(plans), 2) if plans else None,
    }


def _bucket(rows: list[dict]) -> dict:
    return {"trades": len(rows), "pnl": round(sum(r["pnl"] for r in rows), 2) if rows else None}


def _mean(values: list) -> Optional[float]:
    return round(sum(values) / len(values), 2) if values else None


def window_stats(view: dict) -> dict:
    """[O21-PX] The numbers a trader learns from, over the window's scored
    trades, and a plain line for each pattern they show (only with at least
    MIN_SAMPLE trades on each side)."""
    rows = []
    for row in view["days"]:
        traded = [i for i in row["cards"] + row["off_card"] if (i.get("partner") or {}).get("buys")]
        traded.sort(key=lambda i: str(i["partner"]["buys"][0]["at"]))
        previous = None
        for item in traded:
            partner = item["partner"]
            first = _dt(partner["buys"][0]["at"])
            last = _dt(partner["sells"][-1]["at"]) if partner.get("sells") else None
            after_loss = bool(previous and previous["pnl"] is not None and previous["pnl"] < 0 and previous["last"]
                              and first and 0 <= (first - previous["last"]).total_seconds() <= REENTRY_WINDOW_MIN * 60)
            insight = item.get("insight") or {}
            rows.append({"pnl": partner.get("pnl"), "on_card": bool(item.get("card")), "after_loss": after_loss,
                         "minute": first.hour * 60 + first.minute if first else None,
                         "hold": insight.get("hold_min"), "charges": insight.get("charges")})
            previous = {"pnl": partner.get("pnl"), "last": last}
    scored = [r for r in rows if r["pnl"] is not None]
    wins = [r for r in scored if r["pnl"] > 0]
    losses = [r for r in scored if r["pnl"] < 0]
    avg_win, avg_loss = _mean([r["pnl"] for r in wins]), _mean([r["pnl"] for r in losses])
    total = round(sum(r["pnl"] for r in scored), 2) if scored else None
    charges = [r["charges"] for r in scored if r["charges"] is not None]
    hold_wins = [r["hold"] for r in wins if r["hold"] is not None]
    hold_losses = [r["hold"] for r in losses if r["hold"] is not None]
    by_time = [{"label": label, **_bucket([r for r in scored if r["minute"] is not None and lo <= r["minute"] < hi])}
               for label, lo, hi in TIME_BUCKETS]
    stats = {
        "trades": len(scored), "wins": len(wins), "losses": len(losses),
        "win_rate": round(len(wins) / len(scored), 3) if scored else None,
        "avg_win": avg_win, "avg_loss": avg_loss,
        "payoff": round(avg_win / abs(avg_loss), 2) if avg_win and avg_loss else None,
        "per_trade": round(total / len(scored), 2) if scored else None,
        "biggest_win": max((r["pnl"] for r in wins), default=None),
        "biggest_loss": min((r["pnl"] for r in losses), default=None),
        "charges": round(sum(charges), 2) if charges else None,
        "on_card": _bucket([r for r in scored if r["on_card"]]),
        "off_card": _bucket([r for r in scored if not r["on_card"]]),
        "after_loss": _bucket([r for r in scored if r["after_loss"]]),
        "other": _bucket([r for r in scored if not r["after_loss"]]),
        "hold_min": {"wins": median(hold_wins) if hold_wins else None,
                     "losses": median(hold_losses) if hold_losses else None},
        "by_time": by_time,
    }
    lines = []
    if len(hold_wins) >= MIN_SAMPLE and len(hold_losses) >= MIN_SAMPLE and stats["hold_min"]["wins"]:
        ratio = stats["hold_min"]["losses"] / stats["hold_min"]["wins"]
        if ratio >= 1.5:
            lines.append(f"You hold losing trades about {ratio:.1f}× as long as winning ones (median "
                         f"{stats['hold_min']['losses']:.0f} min against {stats['hold_min']['wins']:.0f} min). Losers "
                         f"get time to grow while winners get cut short: let the stop end a loser.")
    if (len(wins) >= MIN_SAMPLE and len(losses) >= MIN_SAMPLE and total is not None and total < 0
            and avg_win < abs(avg_loss)):
        lines.append(f"Your average loss ({_rs(avg_loss)}) is bigger than your average win ({_rs(avg_win)}), so "
                     f"even winning {stats['win_rate']:.0%} of trades loses money. Smaller losses (the stop) fix this "
                     f"faster than more wins.")
    off, on = stats["off_card"], stats["on_card"]
    if off["trades"] >= 2 and off["pnl"] < 0:
        lines.append(f"Trades without a card: {off['trades']}, {_rs(off['pnl'])}. Card trades: {on['trades']}, "
                     f"{_rs(on['pnl'])}.")
    after = stats["after_loss"]
    if after["trades"] >= 2 and after["pnl"] < 0:
        lines.append(f"Trades taken within {REENTRY_WINDOW_MIN} minutes of a loss: {after['trades']}, "
                     f"{_rs(after['pnl'])}.")
    worst_time = min((b for b in by_time if b["trades"] >= MIN_SAMPLE and b["pnl"] < 0), key=lambda b: b["pnl"],
                     default=None)
    if worst_time:
        lines.append(f"Your {worst_time['label']} trades: {worst_time['trades']}, {_rs(worst_time['pnl'])}.")
    if charges and len(scored) >= MIN_SAMPLE:
        lines.append(f"Charges: {_amt(sum(charges))} over {len(charges)} trades ({_amt(sum(charges) / len(charges))} "
                     f"a trade); every extra trade pays them again.")
    stats["insights"] = lines
    return stats


# ---------------------------------------------------------------------------
# the evening Telegram note
# ---------------------------------------------------------------------------

def render_note(review: dict) -> Optional[str]:
    """At most six short lines for a day with trades; ``None`` otherwise."""
    if not review["trades"]:
        return None
    source = "from Zerodha" if review["source"] == "ZERODHA" else "from your taps and replies"
    head = review["headline"]
    line = f"{head['trades']} trade{'s' if head['trades'] != 1 else ''}"
    if head["pnl"] is not None:
        line += f" · {_rs(head['pnl'])} after charges"
    if head["plan_pnl"] is not None:
        line += f" · card plan {_rs(head['plan_pnl'])}"
    if review.get("score"):
        line += f" · rules kept {review['score']['kept']}/{review['score']['of']}"
    lines = [f"📒 Your trades today ({source})", line]
    lesson = review["lesson"]
    if lesson:
        example = lesson["examples"][0]
        times = f" ({lesson['count']} times today)" if lesson["count"] > 1 else ""
        lines.append(f"Lesson: {lesson['title']}{times}. {example['what']}")
        if example["better"]:
            lines.append(f"Better: {example['better']}")
        lines.append(f"Next time: {lesson['rule']}")
    goods = [g["title"] for g in review["well_done"]]
    if goods:
        lines.append("✅ " + " · ".join(list(dict.fromkeys(goods))[:2]))
    if any(t["estimated"] for t in review["trades"]) and len(lines) < 6:
        lines.append("≈ prices came from your taps; reply to a card with your price to correct.")
    return "\n".join(lines[:6])
