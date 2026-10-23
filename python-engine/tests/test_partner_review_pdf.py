"""[O23] The partner's review of earlier days, the day's review as a PDF and
what each rule means.

An earlier day must read "that day" wherever today's review says "today",
and today's review must read exactly as before. Progress must not change
with the day that is open. The PDF must carry the page's content with the
page's number formats, and lose no character whatever font is available."""
import sys
from datetime import datetime
from pathlib import Path

import pytest

import partner_coach as pc
import partner_lessons as pl
import partner_review_pdf as pdf
from tests.test_partner_coach import DAY, T, _card, _view, _zr
from tests.test_partner_insights import _cash, _held, _sl, ctx, flag, net, off, off_item

LATER = T(16, 0, day=21)          # the review read two days after the trades
LATER_DAY = "2026-10-21"
CLEAN = ([_card(updates=[("TARGET_ZONE", T(13, 0))])], [_zr("BUY", T(12, 9), 518.0), _zr("SELL", T(13, 3), 598.0)])


# ---------------------------------------------------------------------------
# O23-PM: what each rule means
# ---------------------------------------------------------------------------

def test_every_rule_says_what_it_means():
    keys = [key for key, _, _ in pl.CHECKS + pl.DAY_CHECKS]
    assert sorted(pl.RULE_MEANINGS) == sorted(keys)
    assert pl.RULE_MEANINGS["card"].startswith("The trade was on a card the system sent you on Telegram that day")
    review = pl.day_review(_view(*CLEAN), DAY)
    assert all(rule["means"] == pl.RULE_MEANINGS[rule["key"]] for rule in review["score"]["rules"])
    # The thresholds named in the lines are the coach's own.
    assert pc.REENTRY_WINDOW_MIN == 30 and "30 minutes" in pl.RULE_MEANINGS["calm"]
    assert pc.STOP_CHECK_MIN_HOLD_MIN == 5 and "under 5 minutes" in pl.RULE_MEANINGS["stop"]
    assert pc.OVERTRADE_MIN_BUYS == 3 and "two buys are always within it" in pl.RULE_MEANINGS["cards_only"]
    import partner_insights as pi
    assert pi.RISK_OF_CASH_PCT == 0.10 and "a tenth of your cash" in pl.RULE_MEANINGS["size"]
    assert pi.PROTECT_GAIN_PCT == pi.SPIKE_RUN_PCT == 0.20
    assert "20%" in pl.RULE_MEANINGS["exit"] and "20% jump" in pl.RULE_MEANINGS["entry"]


# ---------------------------------------------------------------------------
# O23-PH: an earlier day reads "that day"; today reads as before
# ---------------------------------------------------------------------------

def test_an_earlier_day_reads_that_day_and_today_reads_as_before():
    untraded = _view([_card()], [])
    assert pl.day_review(untraded, DAY, today=DAY)["headline"]["text"] == "No trades today. 1 card was sent."
    assert pl.day_review(untraded, DAY)["headline"]["text"] == "No trades today. 1 card was sent."
    assert pl.day_review(untraded, DAY, today=LATER_DAY)["headline"]["text"] == "No trades that day. 1 card was sent."
    clean = pl.day_review(_view(*CLEAN, now=LATER), DAY, today=LATER_DAY)
    assert clean["well_done"][0]["reason"] == "1 trade that day and no mistakes flagged. This is the habit to repeat."
    view = _view([_card()], [_zr("BUY", T(12, 9), 518.0)])
    view["zerodha"] = {"days": {DAY: {"complete": False, "synced_at": T(12, 30).isoformat(), "stops_known": True}}}
    assert "Zerodha was read at 12:30, before the close: later trades are not here yet." in \
        pl.day_review(view, DAY, today=DAY)["notes"]
    assert "Zerodha was read at 12:30, before the close: trades after that are not in this review." in \
        pl.day_review(view, DAY, today=LATER_DAY)["notes"]


def test_the_analysis_of_an_earlier_session_says_that_day():
    reports = [off("BUY", T(10, 0), 30.0, lots=3), off("SELL", T(10, 30), 20.0, lots=3)]
    context = ctx(None, accounts=_cash(45000.0, 5000.0))
    for now, word in ((T(16, 0), "today"), (LATER, "that day")):
        view = _view([], reports, now=now, context=context)
        assert flag(off_item(view), "BIG_RISK")["reason"].endswith(f"cash in your account {word}.")
        story = pl.day_review(view, DAY, today=now.date().isoformat())["trades"][0]
        assert f"At risk: ₹6,750 in premium paid, 14% of your cash {word}." in story["option_lines"]
    expiring = [off("BUY", T(14, 0), 100.0, expiry=DAY)]
    known = frozenset({DAY})
    item = off_item(_view([], expiring, now=LATER, complete_days=known, context=ctx(None, positions=_held(75))))
    assert flag(item, "HELD_OVERNIGHT")["reason"].endswith("It expired that day.")
    refusals = [_sl(order_id, at, 0.0, transaction_type="BUY", order_type="LIMIT", status="REJECTED", filled_quantity=0,
                    quantity=450, status_message="Insufficient funds.") for order_id, at in
                (("3001", T(10, 5)), ("3002", T(10, 7)))]
    for now, word in ((T(16, 0), "today"), (LATER, "that day")):
        view = _view([], [off("BUY", T(10, 6), 100.0), off("SELL", T(10, 30), 104.0)], now=now,
                     context=ctx(None, orders=refusals))
        [funds] = view["days"][0]["day_flags"]
        assert funds["reason"].endswith(f"(2 refusals {word}).")
    trips = [fill for at in (10, 11, 12) for fill in (off("BUY", T(at, 0), 100.0), off("SELL", T(at, 10), 98.0))]
    for now, word in ((T(16, 0), "today's"), (LATER, "that day's")):
        [over] = _view([], trips, now=now)["days"][0]["day_flags"]
        assert over["code"] == "OVERTRADING" and f"; {word} trades paid ₹" in over["why"]


# ---------------------------------------------------------------------------
# O23-PH/PD: the routes
# ---------------------------------------------------------------------------

def _client(monkeypatch, now):
    import main  # noqa: F401  (main includes the router; importing the route first is circular)
    import routes_partner_coach as route
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    monkeypatch.setattr(route._main, "_check_internal_secret", lambda request, name: None)

    class _Clock(route.datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(route, "datetime", _Clock)
    app = FastAPI()
    app.include_router(route.router)
    return TestClient(app)


@pytest.mark.asyncio
async def test_an_old_day_opens_without_widening_progress_and_the_day_list_reaches_120_days(monkeypatch):
    from config import settings
    from tests.test_partner_fill_capture import _seed
    await _seed(settings.DB_PATH)
    client = _client(monkeypatch, pc.IST.localize(datetime(2026, 11, 25, 16, 0)))   # Oct 19 is 37 days back
    body = client.get("/partner/review?day=2026-10-19").json()
    assert (body["day"], body["today"], body["newest"]) == ("2026-10-19", "2026-11-25", True)
    assert body["review"]["headline"]["text"] == "No trades that day. 1 card was sent."
    # Progress is the last 30 days; before, opening Oct 19 widened it to 38 days.
    assert body["progress"]["days"] == [] and body["progress"]["trades"] == 0
    assert client.get("/partner/review").json()["day"] == "2026-11-25"   # nothing in the last 30 days
    days = client.get("/partner/review/days").json()
    assert days == {"days": ["2026-10-19"], "today": "2026-11-25", "automatic_execution": False}


@pytest.mark.asyncio
async def test_tomorrows_focus_belongs_to_the_newest_day_only(monkeypatch):
    from config import settings
    from tests.test_partner_fill_capture import _seed
    await _seed(settings.DB_PATH)
    client = _client(monkeypatch, T(16, 0, day=21))
    assert client.get("/partner/review").json()["newest"] is True              # Oct 19, the latest day
    assert client.get("/partner/review?day=2026-10-21").json()["newest"] is True   # today, empty
    assert client.get("/partner/review?day=2026-10-15").json()["newest"] is False


@pytest.mark.asyncio
async def test_the_pdf_route_returns_the_days_pdf_and_fails_plainly(monkeypatch):
    from config import settings
    from tests.test_partner_fill_capture import _seed
    await _seed(settings.DB_PATH)
    client = _client(monkeypatch, T(16, 0, day=21))
    response = client.get("/partner/review/pdf?day=2026-10-19")
    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="trading-review-2026-10-19.pdf"'
    assert response.headers["cache-control"] == "no-store"
    assert response.content.startswith(b"%PDF-") and response.content.rstrip().endswith(b"%%EOF")
    assert client.get("/partner/review/pdf").headers["content-disposition"].endswith('-2026-10-19.pdf"')
    assert client.get("/partner/review/pdf?day=19-10-2026").status_code == 422
    assert client.get("/partner/review/pdf?day=2020-01-01").status_code == 422
    monkeypatch.setitem(sys.modules, "partner_review_pdf", None)     # an image without reportlab
    missing = client.get("/partner/review/pdf?day=2026-10-19")
    assert missing.status_code == 503 and missing.json()["detail"] == {"code": "pdf_unavailable"}


# ---------------------------------------------------------------------------
# O23-PD: the PDF itself
# ---------------------------------------------------------------------------

def _document(**over):
    view = _view([_card()], [_zr("BUY", T(12, 9), 518.0), _zr("SELL", T(12, 56), 430.0),
                             off("BUY", T(13, 5), 100.0, lots=2), off("SELL", T(13, 40), 80.0, lots=2)])
    review = pl.day_review(view, DAY, today=over.pop("today", DAY))
    review["notes"].append("A note with <angle> & ampersand.")
    return {"day": DAY, "today": DAY, "review": review, "as_of": T(16, 0).isoformat(),
            "focus": {"rule": "After a loss, take a 30-minute break.", "text": "Quick re-entry: 1 time in the last 7 days."},
            **over}


def test_numbers_are_formatted_as_the_page_formats_them():
    assert [pdf.format_rs(v) for v in (159586.95, -1261.49, 0, -0.4, 6135.36, None)] == \
        ["+₹1,59,587", "−₹1,261", "₹0", "−₹0", "+₹6,135", "n/a"]
    assert pdf.format_rs(708.3, signed=False) == "₹708" and pdf.format_rs(-708.3, signed=False) == "−₹708"
    assert [pdf.format_price(v) for v in (1234.5, 32.95, 131, 1.005, None)] == \
        ["₹1,234.5", "₹32.95", "₹131", "₹1", "?"]
    assert [pdf.signed_percent(v) for v in (-0.0123, 0.05, 0, -0.0004, None)] == ["−1.2%", "+5.0%", "0.0%", "0.0%", "n/a"]
    assert [pdf.minutes_label(v) for v in (45, 130, 120, 534, None)] == ["45 min", "2 h 10 min", "2 h", "8 h 54 min", "n/a"]
    assert (pdf.long_day("2026-10-23"), pdf.short_day("2026-10-23")) == ("Friday 23 October 2026", "Fri 23 Oct 2026")


def test_the_chart_matches_the_page_geometry():
    chart = {"points": [[55, 100], [75, 131], [104, 110]],
             "marks": [{"t": 75, "price": 131, "kind": "buy", "at": "10:30"},
                       {"t": 91, "price": 110, "kind": "sell", "at": "10:46"}],
             "levels": [{"label": "Your stop", "price": 105, "kind": "your_stop"},
                        {"label": "Card target", "price": 400, "kind": "target"}],
             "start": "10:10", "end": "10:59"}
    geo = pdf.chart_geometry(chart, 100, 100, pad_x=0, pad_y=0)
    assert geo["points"][0][0] == 0 and geo["points"][-1][0] == 100
    buy, sell = geo["marks"]
    assert buy["y"] > sell["y"]                       # y points up: a higher price is drawn higher
    assert buy["x"] == pytest.approx((75 - 55) / 49 * 100)
    assert [lv["label"] for lv in geo["levels"]] == ["Your stop"]
    assert [lv["label"] for lv in geo["hidden"]] == ["Card target"]
    assert (geo["high"]["price"], geo["low"]["price"]) == (131.0, 100.0)
    assert pdf.chart_geometry({"points": [[1, 100]]}, 100, 100) is None
    assert pdf.chart_geometry({"points": [[1, None], ["x", 2], [2, float("nan")]]}, 100, 100) is None


def test_a_character_the_font_cannot_show_is_replaced_never_dropped():
    assert pdf.plain("−₹1,113 ✓ ✗ ≈ ● · —", pdf._winansi) == "-Rs 1,113 + x ~ * · —"
    assert pdf.plain("日\n", pdf._winansi) == "? "


def _shown(body: bytes) -> str:
    """The uncompressed PDF with each line's text runs joined (reportlab draws
    "a <b> c" as three runs)."""
    return body.decode("latin-1").replace(") Tj (", "")


def test_the_pdf_has_the_pages_content_in_plain_fonts(monkeypatch):
    monkeypatch.setattr(pdf, "FONT_PAIRS", ())
    body = pdf.render_review_pdf(_document(), compress=False)
    assert body.startswith(b"%PDF-") and body.rstrip().endswith(b"%%EOF")
    text = _shown(body)
    for phrase in ("Your trading review", "Monday 19 October 2026", "TOMORROW, FOCUS ON ONE THING",
                   "Your lesson for today", "WHAT HAPPENED", "WHY IT MATTERS", "WHAT WOULD HAVE BEEN BETTER",
                   "Rules kept today", "Your trades, step by step", "Coaching only. Nothing here places an order.",
                   "Page 1 of", "A note with <angle> & ampersand."):
        assert phrase in text, phrase
    assert "Rs " in text and "\u20b9" not in text          # the rupee sign became "Rs", nothing was lost
    assert "/FontFile2" not in text                          # the built-in font, nothing embedded


def test_an_earlier_day_and_an_empty_day_print_without_today_or_focus(monkeypatch):
    monkeypatch.setattr(pdf, "FONT_PAIRS", ())
    text = _shown(pdf.render_review_pdf(_document(today=LATER_DAY) | {"today": LATER_DAY, "focus": None},
                                        compress=False))
    assert "Your lesson from that day" in text and "Rules kept that day" in text
    assert "Your lesson for today" not in text and "TOMORROW, FOCUS" not in text
    empty = pl.day_review(_view([], []), "2026-10-01")
    text = _shown(pdf.render_review_pdf({"day": "2026-10-01", "today": LATER_DAY, "review": empty, "focus": None,
                                         "as_of": None}, compress=False))
    assert "No cards and no trades on this day." in text and "Page 1 of 1" in text


_TTF_PAIRS = (
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
)


def test_an_installed_font_is_embedded_and_the_text_stays_complete(monkeypatch):
    pair = next((p for p in _TTF_PAIRS if Path(p[0]).is_file() and Path(p[1]).is_file()), None)
    if pair is None:
        pytest.skip("no TrueType font pair on this machine")
    monkeypatch.setattr(pdf, "FONT_PAIRS", (pair,))
    fonts = pdf.fonts()
    assert fonts.embedded and fonts.regular.startswith("ReviewSans-")
    body = pdf.render_review_pdf(_document())
    assert body.startswith(b"%PDF-") and b"/FontFile2" in body
    # Every character either has a glyph or is replaced; DejaVu (the engine image) has them all.
    text = "−₹1,113 ✓ ✗ ≈ ●"
    shown = pdf.plain(text, fonts.covers)
    assert len(shown) >= len(text) and "?" not in shown
    if "DejaVu" in pair[0]:
        assert shown == text
