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

Pure functions over the coach view; nothing here places orders or changes
a card. Wording rules: numbers come from the coach; a rule-break that made
money is still named (process over outcome); nothing is called a maximum
or breakeven.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from partner_coach import _rs

# When two mistakes cost the same, the one earlier here is the lesson. The
# order follows the damage they do to a manual option buyer: revenge and
# size first, then entries that break the card, then stop discipline.
LESSON_PRIORITY = (
    "QUICK_REENTRY_AFTER_LOSS", "SIZE_UP_AFTER_LOSS", "ENTRY_ABOVE_LIMIT", "HELD_PAST_STOP", "STOP_CANCELLED",
    "NO_STOP_ORDER", "AVERAGED_DOWN", "OFF_CARD", "OVERTRADING", "LATE_ENTRY", "AFTER_CARD_CLOSED",
    "STOP_WIDER_THAN_CARD", "GAVE_BACK_AFTER_TARGET", "EARLY_EXIT", "HELD_PAST_SQUARE_OFF",
)
MAX_MORE_LESSONS = 4
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
    main["also"] = []
    rest = []
    for lesson in lesson_list[1:]:
        same = [e for e in lesson["examples"] if (e["option"], e["time"]) in trades]
        other = [e for e in lesson["examples"] if (e["option"], e["time"]) not in trades]
        main["also"] += [{"code": lesson["code"], "title": lesson["title"], "what": e["what"], "why": e["why"],
                          "better": e["better"], "rule": lesson["rule"]} for e in same]
        if other:
            priced = [e["impact_rs"] for e in other if e["impact_rs"] is not None]
            rest.append(lesson | {"examples": other, "count": len(other),
                                  "impact_rs": round(sum(priced), 2) if priced else None})
    return main, sorted(rest, key=_rank)


def _well_done(row: dict, traded: list[dict], lesson_list: list[dict]) -> list[dict]:
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
                       "reason": f"{len(traded)} trade{'s' if len(traded) != 1 else ''} today and no mistakes "
                                 f"flagged. This is the habit to repeat.", "option": None})
    return out


# ---------------------------------------------------------------------------
# trade stories
# ---------------------------------------------------------------------------

def _fill_text(verb: str, fill: dict) -> str:
    price = fill.get("price")
    mark = "≈" if fill.get("price_basis") in ESTIMATES else ""
    shown = f"{mark}{_px(price)}" if price is not None else "an unreported price"
    return f"You {verb} {_lots(fill.get('lots'))} at {shown}" if fill.get("lots") else f"You {verb} at {shown}"


def story(item: dict) -> dict:
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
        events.append({"at": item["time"], "who": "card", "text": "Card: " + ", ".join(parts)})
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
        events.append({"at": str(fill["at"])[11:16], "who": "you", "text": _fill_text("bought", fill)})
    for stop in item.get("stops") or []:
        kind = "a GTT stop" if stop["kind"] == "GTT" else "an SL order"
        events.append({"at": stop["placed"], "who": "you", "text": f"You placed {kind} at {_px(stop['trigger'])}"})
        if stop["status"] == "CANCELLED":
            events.append({"at": stop["updated"], "who": "you", "text": f"You cancelled the stop at {_px(stop['trigger'])}"})
    for fill in partner.get("sells") or []:
        events.append({"at": str(fill["at"])[11:16], "who": "you", "text": _fill_text("sold", fill)})
    events.sort(key=lambda e: (e["at"], 0 if e["who"] == "card" else 1))
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
            "advisory_id": item.get("advisory_id"), "pnl": pnl, "plan_pnl": plan if card else None,
            "estimated": bool(partner.get("estimated")), "timeline": events, "result": result,
            "mistakes": [f["title"] for f in item["flags"]], "good": [g["title"] for g in item.get("positives", [])]}


# ---------------------------------------------------------------------------
# the day
# ---------------------------------------------------------------------------

def day_review(view: dict, day: str) -> dict:
    """Everything the partner reads about one day, the lesson first."""
    row = next((r for r in view["days"] if r["day"] == day), None)
    zerodha_day = ((view.get("zerodha") or {}).get("days") or {}).get(day)
    if row is None:
        return {"day": day, "headline": {"trades": 0, "text": "No cards and no trades on this day."},
                "lesson": None, "more_lessons": [], "well_done": [], "trades": [],
                "untaken": {"cards": [], "total_plan_pnl": None, "text": ""}, "notes": [], "source": None}
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
        text = "No trades today." + (f" {len(row['cards'])} card{'s were' if len(row['cards']) != 1 else ' was'} "
                                     f"sent." if row["cards"] else "")
    untaken = [i for i in row["cards"] if not _traded(i)]
    plan_total = [i["plan"]["pnl"] for i in untaken if i.get("plan", {}).get("pnl") is not None]
    fills = [f for i in traded for f in i["partner"].get("buys", []) + i["partner"].get("sells", [])]
    from_zerodha = any(f.get("source") == "ZERODHA" for f in fills)
    notes = []
    if fills and not from_zerodha:
        notes.append("Prices are from your Telegram taps and replies; ≈ marks an estimate.")
    if zerodha_day and not zerodha_day.get("complete"):
        notes.append(f"Zerodha was read at {str(zerodha_day.get('synced_at'))[11:16]}, before the close: later "
                     f"trades are not here yet.")
    if zerodha_day and zerodha_day.get("complete") and not zerodha_day.get("stops_known"):
        notes.append("Stop orders could not be read for this day, so the stop-loss checks are off.")
    if row["cards"]:
        notes.append("The card's results use 5-minute prices; a quick touch between them can be missed.")
    return {
        "day": day, "source": "ZERODHA" if from_zerodha else ("REPORTS" if fills else None),
        "headline": {"trades": len(traded), "off_card_trades": len(off), "pnl": row["actual_pnl"],
                     "plan_pnl": row["plan_pnl_on_traded_cards"], "text": text},
        "lesson": main,
        "more_lessons": rest[:MAX_MORE_LESSONS],
        "well_done": _well_done(row, traded, lesson_list),
        "trades": [story(i) for i in traded],
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
        per_day.append({"day": row["day"], "trades": len(traded), "pnl": row["actual_pnl"],
                        "plan_pnl": row["plan_pnl_on_traded_cards"], "mistakes": len(flags),
                        "clean": bool(traded) and not flags})
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
    return {
        "days": list(reversed(per_day)),
        "patterns": sorted(patterns.values(), key=lambda p: (p["impact_rs"] if p["priced"] else 0.0,
                                                             -p["total"], _priority(p["code"]))),
        "trades": trades_total, "clean_trades": clean_total,
        "clean_rate": round(clean_total / trades_total, 3) if trades_total else None,
        "clean_streak_days": streak,
        "pnl": round(sum(pnls), 2) if pnls else None,
        "plan_pnl_on_traded_cards": round(sum(plans), 2) if plans else None,
    }


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
