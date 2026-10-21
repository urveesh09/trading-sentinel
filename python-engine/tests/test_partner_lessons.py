"""[O21-PL] The partner's day review: which lesson comes first, how mistakes
on one trade are told together, what went well, the trade stories, the
cards not taken, the data notes, progress over weeks and the evening note."""
import pytest

import partner_coach as pc
import partner_lessons as pl
from tests.test_partner_coach import (DAY, FALLING, KNOWN, OFF, RISING, STOPPED_OUT, T, _card, _net, _rep, _series,
                                      _stop, _view, _zr, rs)


def _review(cards, reports, day=DAY, **kw):
    return pl.day_review(_view(cards, reports, **kw), day)


REVENGE_DAY = [_rep("BUY", T(12, 10), 540.0), _rep("SELL", T(12, 56), 430.0),
               _rep("BUY", T(13, 5), 100.0, lots=2, **OFF), _rep("SELL", T(13, 40), 80.0, lots=2, **OFF)]


def test_the_costliest_mistake_is_the_lesson_and_its_trade_is_told_once():
    review = _review([_card(series=FALLING)], REVENGE_DAY)
    lesson = review["lesson"]
    # Revenge and "no card" cost the same (the whole second trade); revenge comes first by priority.
    assert lesson["code"] == "QUICK_REENTRY_AFTER_LOSS"
    assert lesson["impact_rs"] == _net(100.0, 80.0, 150, "NFO")
    assert [a["code"] for a in lesson["also"]] == ["OFF_CARD", "SIZE_UP_AFTER_LOSS"]
    # The SENSEX trade's mistakes follow, costliest first; the NIFTY trade is not repeated.
    assert [m["code"] for m in review["more_lessons"]] == ["ENTRY_ABOVE_LIMIT", "HELD_PAST_STOP"]
    assert all(e["option"] == "SENSEX 74200 PE" for m in review["more_lessons"] for e in m["examples"])
    total = round(_net(540.0, 430.0, 20) + _net(100.0, 80.0, 150, "NFO"), 2)
    assert review["headline"]["text"] == (f"2 trades · {rs(total)} after charges · following the cards exactly: ₹0 · "
                                          f"1 without a card")
    assert review["well_done"] == []


def test_repeated_mistakes_are_grouped_with_their_total():
    c2 = _card("c2", delivered_at=T(13, 30), fill_by=T(13, 40), series=_series({(13, 50): 500, (14, 30): 520,
                                                                               (15, 15): 530}))
    reports = [_rep("BUY", T(12, 25), 520.0), _rep("SELL", T(13, 3), 598.0),
               _rep("BUY", T(13, 50), 500.0, advisory="c2"), _rep("SELL", T(14, 30), 520.0, advisory="c2")]
    review = _review([_card(updates=[("TARGET_ZONE", T(13, 0))]), c2], reports)
    lesson = review["lesson"]
    assert lesson["code"] == "LATE_ENTRY" and lesson["count"] == 2
    assert lesson["impact_rs"] == round(_net(520.0, 598.0, 20) + _net(500.0, 520.0, 20), 2)
    assert [e["time"] for e in lesson["examples"]] == ["12:07", "13:30"]
    note = pl.render_note(review)
    assert "Lesson: Bought after the skip-after time (2 times today)." in note


def test_a_rule_break_that_made_money_is_still_the_lesson():
    review = _review([_card(updates=[("TARGET_ZONE", T(13, 0))])],
                     [_rep("BUY", T(12, 25), 520.0), _rep("SELL", T(13, 3), 598.0)])
    lesson = review["lesson"]
    assert lesson["code"] == "LATE_ENTRY" and lesson["impact_rs"] > 0
    assert "It made" in lesson["examples"][0]["why"]
    assert [g["code"] for g in review["well_done"]] == ["EXITED_WITH_CARD"]


def test_a_clean_day_says_so_and_names_the_habits():
    review = _review([_card(updates=[("TARGET_ZONE", T(13, 0))])],
                     [_rep("BUY", T(12, 9), 518.0), _rep("SELL", T(13, 3), 598.0)])
    assert review["lesson"] is None and review["more_lessons"] == []
    assert [g["code"] for g in review["well_done"]] == ["CLEAN_DAY", "BOUGHT_IN_LIMIT", "EXITED_WITH_CARD"]
    assert review["well_done"][0]["reason"] == "1 trade today and no mistakes flagged. This is the habit to repeat."
    note = pl.render_note(review).split("\n")
    assert note == ["📒 Your trades today (from your taps and replies)",
                    f"1 trade · {rs(_net(518.0, 598.0, 20))} after charges · card plan {rs(_net(518.0, 600.0, 20))}",
                    "✅ Every trade followed its card · Bought inside the limit and on time"]


def test_the_trade_story_runs_in_time_order_with_stops_and_the_card_stop():
    stops = [_stop(465.0, "CANCELLED", T(12, 10), T(12, 38))]
    review = _review([_card(series=FALLING)], STOPPED_OUT, stops=stops, stops_known_days=KNOWN)
    [story] = review["trades"]
    assert [(e["at"], e["who"], e["text"]) for e in story["timeline"]] == [
        ("12:07", "card", "Card: buy up to ₹522.35 (ask ₹514.8), SL ₹464.7, target ₹567.2–₹667.3, skip after 12:16, "
                          "exit by 15:15"),
        ("12:09", "you", "You bought 1 lot at ₹518"),
        ("12:10", "you", "You placed an SL order at ₹465"),
        ("12:38", "you", "You cancelled the stop at ₹465"),
        ("12:40", "card", "The option reached the card's SL ₹464.7"),
        ("12:56", "you", "You sold 1 lot at ₹430"),
    ]
    assert story["result"] == (f"Result {rs(_net(518.0, 430.0, 20))} after charges; the card as written: "
                               f"{rs(_net(518.0, 464.7, 20))}.")
    assert review["lesson"]["code"] == "STOP_CANCELLED"
    assert [a["code"] for a in review["lesson"]["also"]] == ["HELD_PAST_STOP"]
    assert review["source"] == "ZERODHA" and pl.render_note(review).startswith("📒 Your trades today (from Zerodha)")


def test_cards_not_taken_are_neutral_and_a_day_without_trades_sends_no_note():
    c2 = _card("c2", series=FALLING, delivered_at=T(13, 0), fill_by=T(13, 10))
    review = _review([_card(), c2], [], complete_days=KNOWN)
    assert review["headline"]["text"] == "No trades today. 2 cards were sent."
    assert review["lesson"] is None and review["trades"] == []
    assert [(c["time"], c["status"]) for c in review["untaken"]["cards"]] == [("12:07", "Not traded"),
                                                                             ("13:00", "Not traded")]
    assert review["untaken"]["text"].startswith("Not taking a card is always allowed.")
    assert pl.render_note(review) is None


def test_notes_say_what_the_data_can_and_cannot_show():
    taps = _review([_card()], [_rep("BUY", T(12, 9), 518.0, price_basis="ASK_AT_TAP")])
    assert "Prices are from your Telegram taps and replies; ≈ marks an estimate." in taps["notes"]
    assert taps["trades"][0]["timeline"][1]["text"] == "You bought 1 lot at ≈₹518"
    view = _view([_card()], [_zr("BUY", T(12, 9), 518.0)])
    view["zerodha"] = {"days": {DAY: {"complete": False, "synced_at": T(12, 30).isoformat(), "stops_known": True}}}
    assert "Zerodha was read at 12:30, before the close: later trades are not here yet." in \
        pl.day_review(view, DAY)["notes"]
    view["zerodha"] = {"days": {DAY: {"complete": True, "synced_at": T(15, 45).isoformat(), "stops_known": False}}}
    assert "Stop orders could not be read for this day, so the stop-loss checks are off." in \
        pl.day_review(view, DAY)["notes"]
    assert pl.day_review(view, "2026-10-01")["headline"]["text"] == "No cards and no trades on this day."


def _day_card(day, advisory_id, **over):
    """A card on another day: same levels, times on that day."""
    points = {(12, 10): 516, (12, 15): 520, (12, 30): 540, (13, 0): 590, (13, 5): 600, (15, 15): 548}
    return _card(advisory_id, series=_series(points, day=day), day=f"2026-10-{day:02d}",
                 delivered_at=T(12, 7, day=day), fill_by=T(12, 16, 50, day=day), exit_by=T(15, 15, day=day),
                 updates=[("TARGET_ZONE", T(13, 0, day=day))], **over)


def test_progress_compares_this_week_with_last_and_counts_the_clean_streak():
    days = {6: "late", 13: "late", 16: "clean", 19: "clean"}
    cards, reports = [], []
    for day, kind in days.items():
        cards.append(_day_card(day, f"d{day}"))
        buy_at = T(12, 25, day=day) if kind == "late" else T(12, 9, day=day)
        reports += [_rep("BUY", buy_at, 518.0, advisory=f"d{day}"),
                    _rep("SELL", T(13, 3, day=day), 598.0, advisory=f"d{day}")]
    view = _view(cards, reports, now=T(16, 0))
    progress = pl.progress(view, DAY)
    [late] = progress["patterns"]
    # Oct 13-19 is this week, Oct 6-12 the week before.
    assert (late["code"], late["total"], late["last_7_days"], late["previous_7_days"], late["trend"]) == \
        ("LATE_ENTRY", 2, 1, 1, "same")
    assert progress["trades"] == 4 and progress["clean_trades"] == 2 and progress["clean_rate"] == 0.5
    assert progress["clean_streak_days"] == 2
    assert [d["day"] for d in progress["days"]] == ["2026-10-19", "2026-10-16", "2026-10-13", "2026-10-06"]
    assert progress["days"][2] == {"day": "2026-10-13", "trades": 1, "pnl": _net(518.0, 598.0, 20),
                                   "plan_pnl": 0.0, "mistakes": 1, "clean": False}
    assert pl.active_days(view) == ["2026-10-19", "2026-10-16", "2026-10-13", "2026-10-06"]


def test_the_note_keeps_to_six_lines_with_lesson_better_and_rule():
    note = pl.render_note(_review([_card(series=FALLING)], REVENGE_DAY)).split("\n")
    assert len(note) == 5
    assert note[2].startswith("Lesson: Quick re-entry after a loss (revenge pattern). You closed SENSEX 74200 PE")
    assert note[3].startswith("Better: Pause 30 minutes and wait for the next card.")
    assert note[4] == "Next time: After a loss, take a 30-minute break and trade only the next card."
    view = _view([_card(series=FALLING)], REVENGE_DAY)
    assert pc.render_coach_note(view, DAY) == "\n".join(note)


@pytest.mark.asyncio
async def test_review_route_picks_today_or_the_latest_day(monkeypatch):
    import json
    import main  # noqa: F401  (main includes the router; importing the route first is circular)
    import routes_partner_coach as route
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from tests.test_partner_fill_capture import _seed
    from config import settings
    await _seed(settings.DB_PATH)
    monkeypatch.setattr(route._main, "_check_internal_secret", lambda request, name: None)

    class _Clock(route.datetime):
        @classmethod
        def now(cls, tz=None):
            return T(16, 0, day=21)

    monkeypatch.setattr(route, "datetime", _Clock)    # a fixed "today": Oct 21
    app = FastAPI()
    app.include_router(route.router)
    client = TestClient(app)
    body = client.get("/partner/review?day=2026-10-19").json()
    assert body["day"] == "2026-10-19" and body["automatic_execution"] is False
    assert set(body) >= {"review", "progress", "days_available", "zerodha"}
    assert body["review"]["untaken"]["cards"][0]["option"] == "SENSEX 74200 PE"
    assert "access_token" not in json.dumps(body)
    assert client.get("/partner/review?day=19-10-2026").status_code == 422
    assert client.get("/partner/review?day=2020-01-01").status_code == 422
    # No day asked and nothing on Oct 21: the latest day with a card opens.
    latest = client.get("/partner/review").json()
    assert latest["day"] == "2026-10-19" and latest["days_available"] == ["2026-10-19"]
