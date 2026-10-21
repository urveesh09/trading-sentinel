"""[O21-PC] Partner fill capture: parsing, buttons, taps, replies and the inbound tick."""
import json
from datetime import datetime, timedelta

import aiosqlite
import pytest
import pytz

import partner_fill_capture as pfc
from config import settings

IST = pytz.timezone("Asia/Kolkata")
CARD_ID = "3476dc83a38ed4a3b5cab3a8"
CARD_MSG, UPDATE_MSG = 1467, 1474
CHAT = "-1001234"
TAP_AT = IST.localize(datetime(2026, 10, 19, 12, 9, 0))


def _payload() -> dict:
    # The Oct 19 SENSEX card as stored on Production.
    return {
        "session_date": "2026-10-19", "direction": "SHORT", "segment": "BFO",
        "management_deadline": "2026-10-19T15:15:00+05:30",
        "buyer_view": {
            "ask": 514.8, "bid": 513.4, "buy_limit": 522.35, "sl_premium": 464.7,
            "target_premium": 667.3, "target_premium_low": 567.2, "lot_size": 20, "tick_size": 0.05,
            "expiry": "2026-10-22", "fee_segment": "BFO", "opt_type": "PE", "strike": 74200.0,
            "symbol": "SENSEX26O2274200PE", "fill_by": "2026-10-19T12:16:50+05:30",
            "quote_at": "2026-10-19T12:06:50+05:30", "version": "BUYER_VIEW_V2",
        },
        "legs": [{"side": "BUY", "instrument_token": 287684613, "tradingsymbol": "SENSEX26O2274200PE",
                  "strike": 74200.0, "option_type": "PE", "expiry": "2026-10-22", "lot_size": 20,
                  "ask": 514.8, "tick_size": 0.05}],
    }


async def _seed(db_path: str) -> None:
    from hedge_advisory import init_hedge_advisory_db
    from partner_manual_advisory import init_partner_advisory_db
    await init_partner_advisory_db(db_path)
    await init_hedge_advisory_db(db_path)
    await pfc.init_partner_fill_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO partner_advisory_ideas(advisory_id,economic_version,scope,underlying,exchange,status,"
            "evidence,profile_id,profile_version,quote_time,valid_until,rendered_card,payload,supersedes_id,"
            "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (CARD_ID, "v1", "MARKET_SETUP", "SENSEX", "BSE", "RETIRED_SESSION_END", "e", "p", 1,
             "2026-10-19T12:06:52+05:30", "2026-10-19T12:16:52+05:30", "card", json.dumps(_payload()), None,
             "2026-10-19T12:06:52+05:30", "2026-10-19T12:06:52+05:30"))
        for kind, key, sent_at, detail in (
                ("manual_market_advisory", CARD_ID, "2026-10-19T12:06:54+05:30",
                 {"advisory_id": CARD_ID, "delivery": {"message_id": CARD_MSG}}),
                ("manual_advisory_update", "upd1", "2026-10-19T15:10:05+05:30",
                 {"advisory_id": CARD_ID, "event_type": "TARGET_ZONE", "delivery": {"message_id": UPDATE_MSG}})):
            await db.execute(
                "INSERT INTO partner_hedge_messages(kind,dedup_key,sent_at,delivered,detail,claim_token) "
                "VALUES(?,?,?,?,?,?)", (kind, key, sent_at, 1, json.dumps(detail), "t"))
        await db.commit()


@pytest.fixture
def api_calls(monkeypatch):
    calls = []

    async def fake_api(method, payload, *, timeout=10.0):
        calls.append((method, payload))
        return True

    monkeypatch.setattr(pfc, "partner_api", fake_api)
    monkeypatch.setattr(settings, "PARTNER_TELEGRAM_CHAT_ID", CHAT)
    monkeypatch.setattr(settings, "PARTNER_FILL_CAPTURE_ENABLED", True)
    return calls


async def _quote(_token, _now):
    return {"bid": 515.0, "ask": 516.0, "ltp": 515.5}


async def _active(db_path: str) -> list[dict]:
    return [r for r in await pfc.card_reports(db_path, CARD_ID) if r["status"] == "ACTIVE"]


@pytest.mark.parametrize("text, expected", [
    ("518.5", (None, 518.5, None, None)),
    ("b 518.5 x2", ("BUY", 518.5, 2, None)),
    ("Bought 2 lots at 518", ("BUY", 518.0, 2, None)),
    ("s 560 @14:42", ("SELL", 560.0, None, "14:42")),
    ("sold", ("SELL", None, None, None)),
    ("skip", ("SKIP", None, None, None)),
    ("/b@sentinel_bot 120", ("BUY", 120.0, None, None)),
    ("₹97.35", (None, 97.35, None, None)),
    ("sl hit 410", ("SELL", 410.0, None, None)),
])
def test_parse_report_text(text, expected):
    parsed = pfc.parse_report_text(text)
    assert (parsed.action, parsed.price, parsed.lots, parsed.stated_time) == expected


@pytest.mark.parametrize("text", ["good morning", "what do you think", "b 1 2 3", "skip 120", "", "x" * 130])
def test_chat_is_not_a_report(text):
    assert pfc.parse_report_text(text) is None


def test_off_card_contract_is_read():
    parsed = pfc.parse_report_text("b NIFTY 22950 PE 120 x2")
    assert (parsed.underlying, parsed.strike, parsed.opt_type, parsed.price, parsed.lots) == \
        ("NIFTY", 22950.0, "PE", 120.0, 2)
    merged = pfc.parse_report_text("s sensex 74200pe 640")
    assert (merged.underlying, merged.strike, merged.opt_type, merged.price) == ("SENSEX", 74200.0, "PE", 640.0)


def test_keyboards_only_on_cards_and_exit_updates(monkeypatch):
    monkeypatch.setattr(settings, "PARTNER_FILL_CAPTURE_ENABLED", True)
    card = pfc.keyboard_for("manual_market_advisory", {"advisory_id": CARD_ID})
    codes = [b["callback_data"] for row in card["inline_keyboard"] for b in row]
    assert codes == [f"pf:b1:{CARD_ID}", f"pf:b2:{CARD_ID}", f"pf:sk:{CARD_ID}"]
    assert all(len(code.encode()) <= 64 for code in codes)   # Telegram's callback_data limit
    assert pfc.keyboard_for("manual_advisory_update", {"advisory_id": CARD_ID, "event_type": "INVALIDATION"})
    assert pfc.keyboard_for("manual_advisory_update", {"advisory_id": CARD_ID, "event_type": "OTHER"}) is None
    assert pfc.keyboard_for("protective_put_alert", {"advisory_id": CARD_ID}) is None
    assert pfc.keyboard_for("manual_market_advisory", {"advisory_id": "not hex!"}) is None
    monkeypatch.setattr(settings, "PARTNER_FILL_CAPTURE_ENABLED", False)
    assert pfc.keyboard_for("manual_market_advisory", {"advisory_id": CARD_ID}) is None


@pytest.mark.asyncio
async def test_tap_flow_records_estimates_then_corrections(api_calls):
    db = settings.DB_PATH
    await _seed(db)
    card = await pfc.load_card(db, CARD_ID)
    assert (card["token"], card["lot_size"], card["exchange"]) == (287684613, 20, "BFO")

    toast = await pfc.apply_tap(db, card, "b1", dedup_key="tg:1", now=TAP_AT, quote_fn=_quote)
    assert "bought 1 lot ≈₹516" in toast
    [buy] = await _active(db)
    assert (buy["action"], buy["price"], buy["price_basis"], buy["lots"]) == ("BUY", 516.0, "ASK_AT_TAP", 1)
    # A second tap 5 s later is the same tap.
    assert await pfc.apply_tap(db, card, "b1", dedup_key="tg:2", now=TAP_AT + timedelta(seconds=5),
                               quote_fn=_quote) == "Already noted."
    # The partner types the real price: it replaces the estimate, keeps the tap time.
    recorded, reason = await pfc.apply_text(
        db, card, pfc.parse_report_text("518.5"), dedup_key="tg:3", reported_at=TAP_AT + timedelta(minutes=2),
        now=TAP_AT + timedelta(minutes=2), raw_text="518.5", message_id=9001, quote_fn=_quote)
    assert recorded and reason == "recorded"
    [buy] = await _active(db)
    assert (buy["price"], buy["price_basis"], buy["trade_at"]) == (518.5, "PARTNER_STATED", TAP_AT.isoformat())
    # Sold all, then a second exit tap is refused.
    sold_at = TAP_AT + timedelta(minutes=50)
    assert "sold 1 lot ≈₹515" in await pfc.apply_tap(db, card, "sa", dedup_key="tg:4", now=sold_at, quote_fn=_quote)
    assert "already closed" in await pfc.apply_tap(db, card, "s1", dedup_key="tg:5",
                                                   now=sold_at + timedelta(minutes=1), quote_fn=_quote)
    state = pfc.position_state(await pfc.card_reports(db, CARD_ID))
    assert state["closed"] and state["avg_buy"] == 518.5 and state["avg_sell"] == 515.0
    # Undo removes the last report only.
    assert "Removed: sold" in await pfc.apply_tap(db, card, "ud", dedup_key="tg:6", now=sold_at, quote_fn=_quote)
    assert [r["action"] for r in await _active(db)] == ["BUY"]


@pytest.mark.asyncio
async def test_typed_buy_with_lots_and_time_and_skip_conflict(api_calls):
    db = settings.DB_PATH
    await _seed(db)
    card = await pfc.load_card(db, CARD_ID)
    now = TAP_AT + timedelta(minutes=30)
    recorded, _ = await pfc.apply_text(db, card, pfc.parse_report_text("b 520 x2 @12:10"), dedup_key="tg:1",
                                       reported_at=now, now=now, raw_text="b 520 x2 @12:10", message_id=1)
    assert recorded
    [buy] = await _active(db)
    assert (buy["lots"], buy["price"], buy["trade_at_basis"]) == (2, 520.0, "STATED")
    assert buy["trade_at"] == IST.localize(datetime(2026, 10, 19, 12, 10)).isoformat()
    assert await pfc.apply_text(db, card, pfc.parse_report_text("skip"), dedup_key="tg:2", reported_at=now,
                                now=now, raw_text="skip", message_id=2) == (False, "skip_conflicts")
    assert "2 lot(s) open" in await pfc.apply_tap(db, card, "sk", dedup_key="tg:3", now=now)
    # A time still ahead and an implausible price are refused.
    assert (await pfc.apply_text(db, card, pfc.parse_report_text("s 560 @15:00"), dedup_key="tg:4",
                                 reported_at=now, now=now, raw_text="", message_id=3))[1] == "time_in_future"
    assert (await pfc.apply_text(db, card, pfc.parse_report_text("s 56000"), dedup_key="tg:5",
                                 reported_at=now, now=now, raw_text="", message_id=4))[1] == "price_far_from_option"


@pytest.mark.asyncio
async def test_handle_update_reads_only_the_partner_chat(api_calls):
    db = settings.DB_PATH
    await _seed(db)
    foreign = {"update_id": 10, "callback_query": {"id": "cq", "data": f"pf:b1:{CARD_ID}",
                                                   "message": {"message_id": CARD_MSG, "chat": {"id": 999}}}}
    assert await pfc.handle_update(db, foreign, TAP_AT, quote_fn=_quote) == "foreign_chat"
    assert await _active(db) == [] and api_calls == []
    tap = {"update_id": 11, "callback_query": {"id": "cq2", "data": f"pf:b2:{CARD_ID}",
                                               "message": {"message_id": CARD_MSG, "chat": {"id": int(CHAT)}}}}
    assert await pfc.handle_update(db, tap, TAP_AT, quote_fn=_quote) == "tap"
    methods = [m for m, _ in api_calls]
    assert methods[0] == "answerCallbackQuery"
    edits = {p["message_id"]: p["reply_markup"] for m, p in api_calls if m == "editMessageReplyMarkup"}
    assert set(edits) == {CARD_MSG, UPDATE_MSG}
    card_buttons = [b["text"] for row in edits[CARD_MSG]["inline_keyboard"] for b in row]
    assert card_buttons[0].startswith("✅ Open 2 lots ≈₹516") and "💰 Sold all" in card_buttons


@pytest.mark.asyncio
async def test_reply_to_an_update_records_the_sell_and_reacts(api_calls):
    db = settings.DB_PATH
    await _seed(db)
    card = await pfc.load_card(db, CARD_ID)
    await pfc.apply_tap(db, card, "b1", dedup_key="tg:1", now=TAP_AT, quote_fn=_quote)
    at = int(IST.localize(datetime(2026, 10, 19, 15, 12)).timestamp())
    reply = {"update_id": 12, "message": {"message_id": 501, "date": at, "text": "s 640",
                                          "chat": {"id": int(CHAT)}, "reply_to_message": {"message_id": UPDATE_MSG}}}
    assert await pfc.handle_update(db, reply, TAP_AT + timedelta(hours=3, minutes=4), quote_fn=_quote) == "recorded"
    sells = [r for r in await _active(db) if r["action"] == "SELL"]
    assert sells[0]["price"] == 640.0 and sells[0]["lots"] == 1 and sells[0]["trade_at_basis"] == "REPORT_TIME"
    assert ("setMessageReaction", {"chat_id": CHAT, "message_id": 501,
                                   "reaction": [{"type": "emoji", "emoji": "👍"}]}) in api_calls


@pytest.mark.asyncio
async def test_off_card_trade_and_help_cooldown(api_calls, monkeypatch):
    db = settings.DB_PATH
    await _seed(db)
    monkeypatch.setattr(pfc, "_off_card_lot_size", lambda underlying: 75)
    at = int(TAP_AT.timestamp())
    off = {"update_id": 20, "message": {"message_id": 600, "date": at, "text": "b NIFTY 22950 PE 120 x2",
                                        "chat": {"id": int(CHAT)}}}
    assert await pfc.handle_update(db, off, TAP_AT, quote_fn=_quote) == "recorded"
    rows = await pfc.reports_between(db, "2026-10-19", "2026-10-19")
    [row] = [r for r in rows if r["advisory_id"] is None]
    assert (row["underlying"], row["strike"], row["lots"], row["lot_size"], row["exchange"]) == \
        ("NIFTY", 22950.0, 2, 75, "NFO")
    chat = {"update_id": 21, "message": {"message_id": 601, "date": at, "text": "lunch?", "chat": {"id": int(CHAT)}}}
    assert await pfc.handle_update(db, chat, TAP_AT, quote_fn=_quote) == "ignored"
    bad = {"update_id": 22, "message": {"message_id": 602, "date": at, "text": "hmm not sure",
                                        "chat": {"id": int(CHAT)}, "reply_to_message": {"message_id": CARD_MSG}}}
    assert await pfc.handle_update(db, bad, TAP_AT, quote_fn=_quote) == "help"
    assert await pfc.handle_update(db, {**bad, "update_id": 23}, TAP_AT + timedelta(minutes=1),
                                   quote_fn=_quote) == "help"
    helps = [p for m, p in api_calls if m == "sendMessage"]
    assert len(helps) == 1 and helps[0]["reply_parameters"]["message_id"] == 602


@pytest.mark.asyncio
async def test_inbox_tick_gates_backs_off_and_keeps_offset(api_calls, monkeypatch):
    db = settings.DB_PATH
    await _seed(db)
    monkeypatch.setattr(pfc, "partner_enabled", lambda: True)
    monkeypatch.setattr(pfc, "_backoff_until", None)
    monkeypatch.setattr(settings, "PARTNER_FILL_CAPTURE_ENABLED", False)
    assert (await pfc.partner_inbox_tick(TAP_AT))["reason"] == "disabled"
    monkeypatch.setattr(settings, "PARTNER_FILL_CAPTURE_ENABLED", True)
    assert (await pfc.partner_inbox_tick(TAP_AT.replace(hour=22)))["reason"] == "outside_window"

    async def failing(method, payload, *, timeout=10.0):
        return None

    monkeypatch.setattr(pfc, "partner_api", failing)
    assert (await pfc.partner_inbox_tick(TAP_AT))["status"] == "FAILED"
    assert (await pfc.partner_inbox_tick(TAP_AT + timedelta(minutes=1)))["reason"] == "backoff"
    monkeypatch.setattr(pfc, "_backoff_until", None)
    seen = []

    async def updates(method, payload, *, timeout=10.0):
        seen.append((method, payload))
        if method == "getUpdates":
            return [{"update_id": 41, "message": {"message_id": 1, "date": int(TAP_AT.timestamp()),
                                                  "text": "hello", "chat": {"id": int(CHAT)}}}]
        return True

    monkeypatch.setattr(pfc, "partner_api", updates)
    result = await pfc.partner_inbox_tick(TAP_AT)
    assert result == {"status": "COMPLETED", "updates": 1, "outcomes": {"ignored": 1}}
    assert await pfc._get_state(db, "telegram_offset") == "42"
    await pfc.partner_inbox_tick(TAP_AT)
    assert seen[-1][1]["offset"] == 42


@pytest.mark.asyncio
async def test_dashboard_report_validates(api_calls):
    db = settings.DB_PATH
    await _seed(db)
    rid = await pfc.record_dashboard_report(db, advisory_id=CARD_ID, action="buy", price=519.0, lots=1,
                                            trade_at=TAP_AT, note="told me on the phone")
    assert rid > 0
    with pytest.raises(ValueError):
        await pfc.record_dashboard_report(db, advisory_id="ffffffffffffffffffffffff", action="BUY", price=1.0,
                                          lots=1, trade_at=TAP_AT, note=None)
    with pytest.raises(ValueError):
        await pfc.record_dashboard_report(db, advisory_id=None, action="BUY", price=1.0, lots=1,
                                          trade_at=TAP_AT, note=None)


@pytest.mark.asyncio
@pytest.mark.parametrize("capture", [True, False])
async def test_exit_update_delivery_carries_sold_buttons(tmp_path, monkeypatch, capture):
    """Through the real delivery ledger: the square-off reminder gets Sold
    buttons, with the text unchanged; with capture off nothing is attached."""
    import hedge_advisory
    from partner_bot import PartnerSendResult
    from partner_manual_advisory import (
        PartnerAdvisoryProfile, dispatch_queued_management_update, pending_management_updates,
        run_intraday_session_lifecycle, save_partner_profile,
    )
    from tests.test_oct13_audit_fixes import _delivered
    from tests.test_partner_buyer import NOW
    for name, value in (("RESEARCH_ARCHIVE_ENABLED", False), ("PARTNER_MANUAL_ADVISORY_SEND_UNQUALIFIED", True),
                        ("PARTNER_MANUAL_ADVISORY_ENABLED", True), ("PARTNER_MANUAL_ADVISORY_DELIVERY_ENABLED", True),
                        ("PARTNER_FILL_CAPTURE_ENABLED", capture)):
        monkeypatch.setattr(settings, name, value)
    store = str(tmp_path / "advisory.db")
    await save_partner_profile(store, PartnerAdvisoryProfile(holding_period="INTRADAY"), now=NOW)
    advisory_id = await _delivered(store, monkeypatch)
    reminder_at = NOW.replace(hour=15, minute=10, second=5)
    await run_intraday_session_lifecycle(store, now=reminder_at)
    sent = []

    async def transport(text, *, kind, **kwargs):
        sent.append((kind, text, kwargs.get("reply_markup")))
        return PartnerSendResult(True, message_id=7, state="acknowledged")

    monkeypatch.setattr(hedge_advisory, "send_partner_result", transport)
    at = reminder_at + timedelta(seconds=1)
    [update] = await pending_management_updates(store, now=at)
    assert await dispatch_queued_management_update(store, update, now=at, clock=lambda: at)
    [(kind, text, markup)] = sent
    assert kind == "manual_advisory_update" and text == update["rendered_update"]
    if capture:
        assert [b["callback_data"] for b in markup["inline_keyboard"][0]] == \
            [f"pf:sa:{advisory_id}", f"pf:s1:{advisory_id}"]
    else:
        assert markup is None
