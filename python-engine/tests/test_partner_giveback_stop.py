"""[SN121 2026-11-13] The give-back stop: one "stop for today" alert once a day that was up >= 5% of the cash has
fallen back 30% from its best (booked plus open trades at their bids). Messages only."""
import json
import math

import httpx
import pytest

from config import settings
import partner_bot
from partner_bot import send_partner_result
import partner_profit_protection as profit
import partner_watch as pw
from tests.test_partner_broker_sync import kite, partner_app  # noqa: F401
from tests.test_partner_watch import D, watch  # noqa: F401


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(settings, "PARTNER_WATCH_GIVEBACK_STOP_ENABLED", True)
    monkeypatch.setattr(settings, "PARTNER_WATCH_GIVEBACK_ARM", 0.05)
    monkeypatch.setattr(settings, "PARTNER_WATCH_GIVEBACK_STOP", 0.30)
    state = pw._State(cash=25000.0)
    monkeypatch.setattr(pw, "_state", state)
    return state


def _day(net, best):
    return {"net": net, "best": best, "at": D(11, 0)}


def test_rule_arms_at_five_percent_and_stops_at_thirty_percent_given_back():
    assert not profit.giveback_stop(1200, 0, 25000)            # never up 5% (Rs 1,250): not armed
    assert not profit.giveback_stop(6000, 4201, 25000)         # 29.98% given back
    assert profit.giveback_stop(6000, 4200, 25000)             # exactly 30%
    assert profit.giveback_stop(6000, -500, 25000)             # the whole gain and more
    assert not profit.giveback_stop(math.nan, 0, 25000)
    assert not profit.giveback_stop(6000, 4000, 0)


def test_text_is_short_concrete_and_leaves_the_choice():
    up = profit.giveback_stop_text(6000, 4200)
    assert up.splitlines()[0] == "Stop for today and keep your profit"
    assert "Best today +₹6,000, now +₹4,200: 30% of it given back." in up and up.endswith("Your call.")
    down = profit.giveback_stop_text(6000, -1000)
    assert down.splitlines()[0] == "🛑 Stop for today."
    assert "now -₹1,000: all of it given back." in down and "keep your profit" not in down


def test_watch_tells_once_per_best_and_again_only_after_a_new_best_20pct_higher(on):
    day = D(11, 0).date().isoformat()
    assert pw._giveback_item(day, _day(6000, 6000), [], D(11, 0)) is None
    item = pw._giveback_item(day, _day(4200, 6000), [], D(11, 30))
    assert item is not None and item[0] == f"gbstop:{day}:6000" and item[1] == "DAY" and item[3] == {"gbstop": 6000.0}
    assert pw._giveback_item(day, _day(4000, 6000), [], D(11, 35)) is None     # already told for this best
    assert pw._giveback_item(day, _day(4900, 7000), [], D(12, 0)) is None      # 7,000 < 1.2 x 6,000
    item = pw._giveback_item(day, _day(5000, 7500), [], D(13, 0))
    assert item is not None and item[0].endswith(":7500")
    tomorrow = "2099-01-02"                                                       # a new day starts clean
    assert pw._giveback_item(tomorrow, _day(1000, 1000), [], D(9, 30)) is None
    assert on.gb_day == tomorrow and on.gb_told == 0.0


def test_open_trades_count_at_their_bids_and_an_unknown_mark_sends_nothing(on, monkeypatch):
    day = D(11, 0).date().isoformat()
    held = [object()]
    monkeypatch.setattr(pw, "_profit_mark", lambda holdings, now, booked: None)
    assert pw._giveback_item(day, _day(4000, 6000), held, D(11, 0)) is None    # no fresh full-size bid: silent
    monkeypatch.setattr(pw, "_profit_mark", lambda holdings, now, booked: booked + 3000)   # +3,000 open
    assert pw._giveback_item(day, _day(6000, 6000), held, D(11, 5)) is None    # best now 9,000 marked
    monkeypatch.setattr(pw, "_profit_mark", lambda holdings, now, booked: booked + 200)
    item = pw._giveback_item(day, _day(6000, 6000), held, D(11, 10))           # 6,200 vs best 9,000: 31% back
    assert item is not None and item[3] == {"gbstop": 9000.0}


def test_switched_off_or_without_cash_sends_nothing(on, monkeypatch):
    day = D(11, 0).date().isoformat()
    monkeypatch.setattr(settings, "PARTNER_WATCH_GIVEBACK_STOP_ENABLED", False)
    assert pw._giveback_item(day, _day(4200, 6000), [], D(11, 0)) is None
    monkeypatch.setattr(settings, "PARTNER_WATCH_GIVEBACK_STOP_ENABLED", True)
    on.cash = None
    assert pw._giveback_item(day, _day(4200, 6000), [], D(11, 0)) is None


@pytest.mark.asyncio
async def test_message_is_rebuilt_at_send_time_and_dropped_after_a_recovery(on, monkeypatch):
    now = D(11, 31)
    view = pw.View(now.date().isoformat(), now, [], [], [])
    monkeypatch.setattr(pw, "day_so_far", lambda trips, cash: _day(4100, 6000))
    built = await pw._b_day("unused.db", {"gbstop": 6000.0}, view, now)
    assert built is not None and built[1] == "give-back stop"
    assert "Best today +₹6,000, now +₹4,100: 32% of it given back." in built[0]
    monkeypatch.setattr(pw, "day_so_far", lambda trips, cash: _day(4500, 6000))   # back above the 70% line
    assert await pw._b_day("unused.db", {"gbstop": 6000.0}, view, now) is None


@pytest.fixture
def telegram(monkeypatch):
    calls, responses = [], []
    client = httpx.AsyncClient

    def handle(request):
        method = request.url.path.rsplit("/", 1)[-1]
        payload = request.content if method == "sendSticker" else json.loads(request.content)
        calls.append((method, payload))
        status = responses.pop(0) if responses else 200
        if isinstance(status, Exception):
            raise status
        reply = {"ok": status == 200, "result": {"message_id": len(calls)}}
        if status == 429:
            reply["parameters"] = {"retry_after": 1}
        return httpx.Response(status, json=reply)

    monkeypatch.setattr(partner_bot.httpx, "AsyncClient", lambda: client(transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(partner_bot, "STOP_MESSAGE_GAP_SEC", 0.0)
    monkeypatch.setattr(partner_bot, "send_partner_result", send_partner_result)
    monkeypatch.setattr(settings, "PARTNER_BOT_ENABLED", True)
    monkeypatch.setattr(settings, "PARTNER_TELEGRAM_CHAT_ID", "12345678")
    return calls, responses


@pytest.mark.asyncio
@pytest.mark.parametrize("details_status", [200, 429])
async def test_watch_sends_the_sticker_then_headline_then_details_in_one_alert(watch, kite, telegram, details_status):
    """The stop replaces the earlier give-back step and retries only its full alert."""
    calls, responses = telegram
    responses.extend([200, 200, details_status])
    from tests.test_partner_watch import _login, _market, _messages, _o
    await _login()
    market = _market(D(10, 0))
    await pw.watch_tick(D(9, 59, 55), market=market)
    kite["orders"] = [_o("101", "BUY", D(10, 0), average_price=80.0), _o("102", "SELL", D(10, 5), average_price=100.0)]
    await pw.watch_tick(D(10, 5, 5), market=market)
    kite["orders"] += [_o("103", "BUY", D(10, 10), average_price=80.0), _o("104", "SELL", D(10, 15), average_price=72.0)]
    await pw.watch_tick(D(10, 15, 5), market=market)
    await pw.watch_tick(D(10, 15, 20), market=market)  # the full alert can retry before it expires
    kite["orders"] += [_o("105", "BUY", D(10, 20), average_price=80.0), _o("106", "SELL", D(10, 25), average_price=75.0)]
    await pw.watch_tick(D(10, 25, 5), market=market)
    for at in (D(10, 25, 10), D(10, 25, 30)):
        await pw.watch_tick(at, market=market)
    assert [method for method, _ in calls] == (
        ["sendSticker", "sendRichMessage", "sendRichMessage"]
        + (["sendRichMessage"] if details_status == 429 else [])
    )
    assert b'name="chat_id"\r\n\r\n12345678' in calls[0][1]
    assert b'filename="partner-stop.webp"' in calls[0][1] and b"image/webp" in calls[0][1]
    assert partner_bot.STOP_STICKER.read_bytes() in calls[0][1]
    heading = "<h2><b>Stop for today and keep your profit</b></h2>"
    assert calls[1][1] == {"chat_id": "12345678", "rich_message": {"html": heading}}
    for _, payload in calls[2:]:
        assert payload["chat_id"] == "12345678"
        html = payload["rich_message"]["html"]
        assert html.startswith(heading + "<p>Best today +₹")
        assert "of it given back.<br>On your recent days" in html and html.endswith("Your call.</p>")
    rows = [r for r in await _messages(settings.DB_PATH) if r[1] == "DAY"]
    assert len(rows) == 1 and rows[0][0].startswith("gbstop:2026-10-23:")
    assert rows[0][2:5] == (1, 2 if details_status == 429 else 1, "acknowledged")


@pytest.mark.asyncio
async def test_explicit_rich_rejection_falls_back_to_bold_and_sticker_failure_keeps_text(telegram):
    calls, responses = telegram
    responses.extend([400, 404, 200, 400, 200])
    headline = "Stop for today and keep your profit"
    text = headline + "\nP&L < ₹4,000"
    result = await send_partner_result(text, large_heading=True, stop_lead_in=True)

    assert result.delivered
    assert [method for method, _ in calls] == [
        "sendSticker", "sendRichMessage", "sendMessage", "sendRichMessage", "sendMessage",
    ]
    assert calls[3][1]["rich_message"]["html"].endswith("<p>P&amp;L &lt; ₹4,000</p>")
    for index, expected in ((2, headline), (4, text)):
        payload = calls[index][1]
        assert payload["text"] == expected
        assert payload["entities"] == [{"type": "bold", "offset": 0, "length": len(headline)}]


@pytest.mark.asyncio
async def test_ambiguous_rich_delivery_does_not_resend_as_plain_text(telegram):
    calls, responses = telegram
    responses.extend([200, 200, httpx.ReadTimeout("response lost")])

    result = await send_partner_result(profit.giveback_stop_text(6000, 4200), large_heading=True, stop_lead_in=True)

    assert result.state == "ambiguous_timeout"
    assert [method for method, _ in calls] == ["sendSticker", "sendRichMessage", "sendRichMessage"]
