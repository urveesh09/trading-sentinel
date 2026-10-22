"""[O21-PK] The partner's Zerodha book: read-only calls, order -> report mapping,
card matching, refresh on re-read, the evening flow and the coach on Zerodha days."""
import hashlib
import json
from datetime import datetime
from pathlib import Path

import aiosqlite
import pytest
import pytz
from fastapi import FastAPI
from fastapi.testclient import TestClient

import partner_broker_sync as zerodha
import partner_coach as pc
import partner_fill_capture as pfc
from config import settings
from tests.test_partner_fill_capture import CARD_ID, _seed

IST = pytz.timezone("Asia/Kolkata")
SYMBOL = "SENSEX26O2274200PE"      # the Oct 19 card's option (BFO, lot 20)
OFF_SYMBOL = "NIFTY26O2022950PE"


def T(h, m, s=0, day=19):
    return IST.localize(datetime(2026, 10, day, h, m, s))


def _ts(at):
    return at.strftime("%Y-%m-%d %H:%M:%S")


def _order(order_id, side, qty, at, symbol=SYMBOL, exchange="BFO", status="COMPLETE", order_type="LIMIT", **over):
    row = {"order_id": order_id, "transaction_type": side, "tradingsymbol": symbol, "exchange": exchange,
           "status": status, "order_type": order_type, "product": "MIS", "quantity": qty,
           "filled_quantity": qty if status == "COMPLETE" else 0, "average_price": 0,
           "order_timestamp": _ts(at), "exchange_timestamp": _ts(at)}
    row.update(over)
    return row


def _trade(order_id, qty, price, at):
    return {"trade_id": f"t{order_id}{at.second}", "order_id": order_id, "quantity": qty, "average_price": price,
            "fill_timestamp": _ts(at), "exchange_timestamp": _ts(at)}


LOTS = {"SENSEX": 20, "NIFTY": 75}


def _resolve(symbol, exchange):
    parsed = zerodha.parse_option_symbol(symbol)
    if parsed is not None:
        parsed["lot_size"] = LOTS.get(parsed["underlying"])
    return parsed


def _card(advisory_id="c1", at=T(12, 6, 54), symbol=SYMBOL, lot_size=20):
    return {"advisory_id": advisory_id, "tradingsymbol": symbol, "exchange": "BFO", "delivered_at": at,
            "session_date": "2026-10-19", "lot_size": lot_size}


@pytest.fixture(autouse=True)
def partner_app(monkeypatch):
    monkeypatch.setattr(settings, "PARTNER_KITE_API_KEY", "pk_test")
    monkeypatch.setattr(settings, "PARTNER_KITE_API_SECRET", "ps_test")
    monkeypatch.setattr(settings, "PARTNER_KITE_USER_ID", "ab1234")
    monkeypatch.setattr(settings, "PARTNER_ZERODHA_SYNC_ENABLED", True)
    zerodha.disconnect()
    monkeypatch.setattr(zerodha, "_review_task", None)
    monkeypatch.setattr(zerodha, "_review_state", {"state": "idle"})
    yield
    zerodha.disconnect()


@pytest.fixture
def kite(monkeypatch):
    """Fake Kite: records calls, serves the session, orders, trades, GTTs and
    [O21-PX] order histories, positions and margins."""
    state = {"calls": [], "user_id": "AB1234", "orders": [], "trades": [], "gtts": [], "histories": {},
             "positions": {"net": [], "day": []}, "margins": {}}

    async def fake(method, path, *, data=None, params=None, token=None):
        assert zerodha.allowed(method, path)
        state["calls"].append((method, path, data, params, token))
        if path == "/session/token" and method == "POST":
            return {"access_token": "tok-secret-123", "user_id": state["user_id"], "user_name": "Partner"}
        if path == "/session/token":
            return True
        if path.startswith("/orders/"):
            return state["histories"].get(path.rsplit("/", 1)[1], [])
        return {"/orders": state["orders"], "/trades": state["trades"], "/gtt/triggers": state["gtts"],
                "/portfolio/positions": state["positions"], "/user/margins/equity": state["margins"]}[path]

    monkeypatch.setattr(zerodha, "_kite_call", fake)
    monkeypatch.setattr(zerodha, "resolve_option", _resolve)
    return state


# ---------------------------------------------------------------------------
# pure parts
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("symbol, expected", [
    ("NIFTY25O2122950PE", ("NIFTY", 22950.0, "PE", "2025-10-21", None)),
    ("SENSEX26O2274200PE", ("SENSEX", 74200.0, "PE", "2026-10-22", None)),
    ("NIFTY2561222950CE", ("NIFTY", 22950.0, "CE", "2025-06-12", None)),
    ("BANKNIFTY25OCT56000CE", ("BANKNIFTY", 56000.0, "CE", None, "2025-10")),
    ("NIFTY25D0925000PE", ("NIFTY", 25000.0, "PE", "2025-12-09", None)),
])
def test_option_symbols_are_read(symbol, expected):
    parsed = zerodha.parse_option_symbol(symbol)
    assert (parsed["underlying"], parsed["strike"], parsed["opt_type"], parsed["expiry"],
            parsed["expiry_month"]) == expected


@pytest.mark.parametrize("symbol", ["RELIANCE", "NIFTY25OCTFUT", "", "NIFTY25O2122950XX"])
def test_non_options_are_not_read(symbol):
    assert zerodha.parse_option_symbol(symbol) is None


def test_orders_become_one_report_each_with_exact_fills():
    orders = [
        _order("O1", "BUY", 40, T(12, 9, 5)),
        _order("O2", "SELL", 40, T(13, 5), order_type="MARKET"),
        _order("O3", "BUY", 75, T(13, 10), symbol=OFF_SYMBOL, exchange="NFO"),
        _order("O4", "BUY", 20, T(13, 20), status="REJECTED"),
        _order("O5", "BUY", 1, T(13, 25), symbol="RELIANCE", exchange="NSE"),
        _order("O6", "SELL", 75, T(13, 40), symbol=OFF_SYMBOL, exchange="NFO", status="CANCELLED",
               filled_quantity=75),
        _order("O7", "BUY", 20, T(12, 5)),      # before the card reached the partner
    ]
    trades = [_trade("O1", 20, 518.0, T(12, 9, 10)), _trade("O1", 20, 519.0, T(12, 9, 12)),
              _trade("O2", 40, 600.0, T(13, 5, 1)), _trade("O3", 75, 120.0, T(13, 10, 2)),
              _trade("O6", 75, 104.5, T(13, 40, 3)), _trade("O7", 20, 510.0, T(12, 5, 1))]
    reports, counts = zerodha.build_reports(orders, trades, [_card()], received_at=T(15, 41), resolve=_resolve)
    assert counts == {"option_orders": 5, "other_orders": 1, "unfilled_orders": 1}
    by_key = {r["dedup_key"]: r for r in reports}
    buy = by_key["kite:O1"]
    assert (buy["action"], buy["price"], buy["lots"], buy["lot_size"], buy["advisory_id"]) == ("BUY", 518.5, 2, 20, "c1")
    assert buy["trade_at"] == T(12, 9, 10).isoformat()          # the first fill, not the order time
    assert (buy["source"], buy["price_basis"], buy["trade_at_basis"]) == ("ZERODHA", "BROKER_FILL", "EXCHANGE_FILL")
    assert by_key["kite:O2"]["advisory_id"] == "c1" and by_key["kite:O2"]["lots"] == 2
    off = by_key["kite:O3"]
    assert (off["advisory_id"], off["underlying"], off["strike"], off["lots"], off["exchange"]) == \
        (None, "NIFTY", 22950.0, 1, "NFO")
    assert "cancelled after 75 filled" in by_key["kite:O6"]["note"]
    assert by_key["kite:O7"]["advisory_id"] is None
    assert [r["dedup_key"] for r in reports] == ["kite:O7", "kite:O1", "kite:O2", "kite:O3", "kite:O6"]


def test_a_sell_closes_the_card_still_holding_quantity():
    cards = [_card("c1", T(12, 6)), _card("c2", T(13, 30))]
    orders = [_order("B1", "BUY", 20, T(12, 10)), _order("B2", "BUY", 20, T(13, 35)),
              _order("S1", "SELL", 20, T(14, 0)), _order("S2", "SELL", 20, T(14, 5)),
              _order("S3", "SELL", 20, T(14, 10))]
    trades = [_trade(o["order_id"], 20, 500.0, T(int(o["order_timestamp"][11:13]), int(o["order_timestamp"][14:16])))
              for o in orders]
    reports, _ = zerodha.build_reports(orders, trades, cards, received_at=T(15, 41), resolve=_resolve)
    assert [(r["dedup_key"], r["advisory_id"]) for r in reports] == [
        ("kite:B1", "c1"), ("kite:B2", "c2"), ("kite:S1", "c2"), ("kite:S2", "c1"), ("kite:S3", "c2")]


def test_quantity_that_is_not_whole_lots_is_scored_as_units():
    reports, _ = zerodha.build_reports([_order("O1", "BUY", 30, T(12, 10))], [_trade("O1", 30, 500.0, T(12, 10))],
                                       [_card()], received_at=T(15, 41), resolve=_resolve)
    [report] = reports
    assert (report["lots"], report["lot_size"]) == (30, 1)
    assert "not a multiple of lot size 20" in report["note"]


def test_an_order_without_trades_uses_its_own_average():
    order = _order("O1", "BUY", 20, T(12, 10), average_price=517.25)
    [report], _ = zerodha.build_reports([order], [], [_card()], received_at=T(15, 41), resolve=_resolve)
    assert (report["price"], report["lots"], report["trade_at"]) == (517.25, 1, T(12, 10).isoformat())


# ---------------------------------------------------------------------------
# session and read-only guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_checks_the_account_and_never_returns_the_token(kite):
    session = await zerodha.create_session("reqtok12", T(15, 41))
    method, path, data, _params, _token = kite["calls"][0]
    expected = hashlib.sha256(b"pk_test" + b"reqtok12" + b"ps_test").hexdigest()
    assert (method, path, data["checksum"], data["api_key"]) == ("POST", "/session/token", expected, "pk_test")
    assert session["account"] == "AB***34" and "tok-secret" not in json.dumps(session)
    assert zerodha.connected(T(15, 42)) and session["expires_at"] == T(6, 0, day=20).isoformat()
    assert not zerodha.connected(T(6, 0, day=20))
    assert "tok-secret" not in json.dumps(zerodha.status(T(15, 42)))


@pytest.mark.asyncio
async def test_another_account_is_refused_and_logged_out(kite):
    kite["user_id"] = "ZZ9999"
    with pytest.raises(zerodha.BrokerError) as err:
        await zerodha.create_session("reqtok12", T(15, 41))
    assert err.value.code == "wrong_account"
    assert kite["calls"][-1][:2] == ("DELETE", "/session/token")
    assert not zerodha.connected(T(15, 42))


@pytest.mark.asyncio
async def test_bad_or_unconfigured_logins_are_refused(kite, monkeypatch):
    with pytest.raises(zerodha.BrokerError) as err:
        await zerodha.create_session("bad token!", T(15, 41))
    assert err.value.code == "bad_request_token" and kite["calls"] == []
    monkeypatch.setattr(settings, "PARTNER_KITE_USER_ID", "")
    assert not zerodha.configured() and zerodha.login_url() is None
    with pytest.raises(zerodha.BrokerError) as err:
        await zerodha.create_session("reqtok12", T(15, 41))
    assert err.value.code == "not_configured"


@pytest.mark.asyncio
async def test_only_read_calls_can_leave_the_process():
    assert zerodha._ALLOWED_CALLS == {("POST", "/session/token"), ("DELETE", "/session/token"),
                                      ("GET", "/orders"), ("GET", "/trades"), ("GET", "/gtt/triggers"),
                                      ("GET", "/portfolio/positions"), ("GET", "/user/margins/equity")}
    # [O21-PX] One order's history is a GET with a numeric id; placing (POST
    # /orders/{variety}), modifying (PUT) and cancelling (DELETE
    # /orders/{variety}/{id}) can never match.
    assert zerodha.allowed("GET", "/orders/251021000123456")
    for method, path in (("POST", "/orders/regular"), ("PUT", "/orders/regular/1"), ("POST", "/gtt/triggers"),
                         ("PUT", "/gtt/triggers/7"), ("DELETE", "/gtt/triggers/7"), ("DELETE", "/orders/regular/1"),
                         ("POST", "/orders/251021000123456"), ("PUT", "/orders/251021000123456"),
                         ("DELETE", "/orders/251021000123456"), ("GET", "/orders/regular"),
                         ("GET", "/orders/251021000123456/trades"), ("GET", "/orders/1?x=1"),
                         ("POST", "/portfolio/positions"), ("PUT", "/portfolio/positions"), ("GET", "/user/margins"),
                         ("POST", "/margins/orders"), ("POST", "/charges/orders")):
        assert not zerodha.allowed(method, path), (method, path)
        with pytest.raises(zerodha.BrokerError) as err:
            await zerodha._kite_call(method, path)
        assert err.value.code == "not_allowed"
    source = Path(zerodha.__file__).read_text(encoding="utf-8")
    assert "/orders/regular" not in source and "/gtt/triggers/" not in source and '"PUT"' not in source


def test_login_url_carries_only_the_api_key():
    assert zerodha.login_url() == "https://kite.zerodha.com/connect/login?v=3&api_key=pk_test"
    [[button]] = zerodha.review_keyboard()["inline_keyboard"]
    assert button["url"] == zerodha.login_url() and "ps_test" not in json.dumps(button)


@pytest.mark.asyncio
async def test_an_expired_token_disconnects(kite, monkeypatch):
    await zerodha.create_session("reqtok12", T(12, 0))

    async def expired(method, path, **kwargs):
        raise zerodha.BrokerError("TokenException", "Token is invalid or has expired.")

    monkeypatch.setattr(zerodha, "_kite_call", expired)
    with pytest.raises(zerodha.BrokerError):
        await zerodha.sync_book(T(12, 30))
    assert not zerodha.connected(T(12, 31))


# ---------------------------------------------------------------------------
# storage, the evening flow and the coach
# ---------------------------------------------------------------------------

async def _zerodha_rows(db):
    async with aiosqlite.connect(db) as conn:
        rows = await (await conn.execute(
            "SELECT report_id, dedup_key, lots, price, status, advisory_id FROM partner_trade_reports "
            "WHERE source='ZERODHA' ORDER BY report_id")).fetchall()
    return rows


@pytest.mark.asyncio
async def test_rereads_refresh_the_same_report_and_mark_the_day(kite):
    db = settings.DB_PATH
    await _seed(db)
    await zerodha.create_session("reqtok12", T(12, 0))
    kite["orders"] = [_order("O1", "BUY", 40, T(12, 9, 5), status="OPEN", filled_quantity=20)]
    kite["trades"] = [_trade("O1", 20, 518.0, T(12, 9, 10))]
    first = await zerodha.sync_book(T(12, 30))
    assert first["days"] == {"2026-10-19": {"option_orders": 1, "complete": False, "stops_known": True}}
    assert first["on_card"] == 1
    [(report_id, key, lots, price, status, advisory)] = await _zerodha_rows(db)
    assert (key, lots, price, advisory) == ("kite:O1", 1, 518.0, CARD_ID)
    kite["orders"] = [_order("O1", "BUY", 40, T(12, 9, 5))]
    kite["trades"].append(_trade("O1", 20, 519.0, T(12, 9, 12)))
    await zerodha.sync_book(T(15, 41))
    assert await _zerodha_rows(db) == [(report_id, "kite:O1", 2, 518.5, "ACTIVE", CARD_ID)]
    days = await zerodha.broker_days(db, "2026-10-19", "2026-10-19")
    assert days["2026-10-19"]["complete"] is True
    # A report the owner voided stays voided on the next read.
    await pfc.void_report(db, report_id, "wrong")
    await zerodha.sync_book(T(15, 50))
    assert (await _zerodha_rows(db))[0][4] == "VOIDED"


@pytest.mark.asyncio
async def test_a_refused_trade_book_falls_back_to_order_averages(kite, monkeypatch):
    db = settings.DB_PATH
    await _seed(db)
    await zerodha.create_session("reqtok12", T(15, 41))
    fake = zerodha._kite_call

    async def no_trades(method, path, **kwargs):
        if path == "/trades":
            raise zerodha.BrokerError("PermissionException", "not on this plan")
        return await fake(method, path, **kwargs)

    monkeypatch.setattr(zerodha, "_kite_call", no_trades)
    kite["orders"] = [_order("O1", "BUY", 20, T(12, 9, 30), average_price=518.25)]
    result = await zerodha.sync_book(T(15, 45))
    assert result["option_orders"] == 1
    [(_id, key, lots, price, status, advisory)] = await _zerodha_rows(db)
    assert (key, lots, price, advisory) == ("kite:O1", 1, 518.25, CARD_ID)


@pytest.mark.asyncio
async def test_coach_scores_zerodha_fills_over_taps(kite):
    db = settings.DB_PATH
    await _seed(db)
    await pfc.insert_report(db, {"dedup_key": "tg:1", "source": "TELEGRAM_BUTTON", "received_at": T(12, 9).isoformat(),
                                 "trade_at": T(12, 9).isoformat(), "trade_at_basis": "TAP", "action": "BUY",
                                 "advisory_id": CARD_ID, "session_date": "2026-10-19", "underlying": "SENSEX",
                                 "lots": 1, "lot_size": 20, "exchange": "BFO", "price": 516.0,
                                 "price_basis": "ASK_AT_TAP"})
    partial = await pc.load_partner_coach(db, days=3, now=T(16, 0))
    assert partial["days"][0]["cards"][0]["partner"]["status"] == "BOUGHT"
    await zerodha.create_session("reqtok12", T(15, 41))
    kite["orders"] = [_order("O1", "BUY", 20, T(12, 9, 5)), _order("O2", "SELL", 20, T(15, 11))]
    kite["trades"] = [_trade("O1", 20, 518.0, T(12, 9, 10)), _trade("O2", 20, 640.0, T(15, 11, 2))]
    await zerodha.sync_book(T(15, 41))
    view = await pc.load_partner_coach(db, days=3, now=T(16, 0))
    item = view["days"][0]["cards"][0]
    assert [f["source"] for f in item["partner"]["buys"] + item["partner"]["sells"]] == ["ZERODHA", "ZERODHA"]
    assert item["partner"]["avg_entry"] == 518.0 and item["partner"]["estimated"] is False
    assert view["data_quality"]["superseded_by_zerodha"] == 1
    assert view["zerodha"]["days"]["2026-10-19"]["complete"] is True and view["zerodha"]["connected"] is True
    note = pc.render_coach_note(view, "2026-10-19")
    assert note.startswith("📒 Your trades today (from Zerodha)") and "≈" not in note


@pytest.mark.asyncio
async def test_a_card_without_orders_is_not_traded_only_after_a_full_read(kite):
    db = settings.DB_PATH
    await _seed(db)
    await zerodha.create_session("reqtok12", T(11, 0))
    await zerodha.sync_book(T(12, 0))
    view = await pc.load_partner_coach(db, days=3, now=T(12, 30))
    assert view["days"][0]["cards"][0]["partner"]["status"] == "NOT_REPORTED"
    await zerodha.sync_book(T(15, 45))
    view = await pc.load_partner_coach(db, days=3, now=T(16, 0))
    item = view["days"][0]["cards"][0]
    assert item["partner"]["status"] == "NOT_TRADED" and item["verdict"].startswith("Not traded")
    assert view["summary"]["cards_not_traded"] == 1 and view["summary"]["cards_not_reported"] == 0


@pytest.fixture
def partner_chat(monkeypatch):
    import partner_bot
    monkeypatch.setattr(settings, "PARTNER_BOT_ENABLED", True)
    monkeypatch.setattr(settings, "PARTNER_TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setattr(settings, "PARTNER_TELEGRAM_CHAT_ID", "c")
    monkeypatch.setattr(settings, "PARTNER_COACH_NOTE_ENABLED", True)
    sent = []

    async def result(text, *, kind="partner_msg", reply_markup=None):
        sent.append((kind, text, reply_markup))
        return partner_bot.PartnerSendResult(True, state="delivered")

    async def plain(text, *, kind="partner_msg"):
        sent.append((kind, text, None))
        return True

    monkeypatch.setattr(partner_bot, "send_partner_result", result)
    monkeypatch.setattr(partner_bot, "send_partner", plain)
    return sent


@pytest.mark.asyncio
async def test_evening_wrap_sends_the_review_button_once(kite, partner_chat):
    from partner_orchestrator import init_partner_db
    db = settings.DB_PATH
    await init_partner_db(db)
    assert (await zerodha.partner_broker_eod(T(15, 40)))["status"] == "prompted"
    assert (await zerodha.partner_broker_eod(T(15, 45)))["status"] == "already_prompted"
    [(kind, text, markup)] = partner_chat
    assert kind == "zerodha_prompt" and "read-only" in text
    assert markup["inline_keyboard"][0][0]["url"] == zerodha.login_url()
    # The coach note waits for the read instead of using a partial book.
    await _seed(db)
    assert (await pc.partner_coach_eod(T(15, 46)))["note"] == "awaiting_zerodha"


@pytest.mark.asyncio
async def test_login_after_the_close_reads_and_sends_the_note(kite, partner_chat):
    from partner_orchestrator import init_partner_db
    db = settings.DB_PATH
    await init_partner_db(db)
    await _seed(db)
    kite["orders"] = [_order("O1", "BUY", 20, T(12, 9, 5)), _order("O2", "SELL", 20, T(15, 11))]
    kite["trades"] = [_trade("O1", 20, 518.0, T(12, 9, 10)), _trade("O2", 20, 640.0, T(15, 11, 2))]
    result = await zerodha.on_login("reqtok12", T(15, 52))
    assert result["connected"] and result["automatic_execution"] is False
    assert "tok-secret" not in json.dumps(result)
    # [A22-P4] The login answers on the fills; the deeper read and the note follow.
    assert result["sync"]["state"] in ("enriching", "done") and result["sync"]["option_orders"] == 2
    synced = await zerodha.wait_review_sync()
    assert synced["note"] == "sent" and zerodha.review_sync(T(15, 53))["state"] == "done"
    [(kind, text, markup)] = partner_chat
    assert kind == "coach" and text.startswith("📒 Your trades today (from Zerodha)")
    assert markup["inline_keyboard"][0][0]["text"] == "📒 Open full review"
    # The 15:40-style wrap after that: one read, no second note or prompt.
    assert (await zerodha.partner_broker_eod(T(15, 55)))["status"] == "synced"
    assert (await pc.partner_coach_eod(T(15, 55)))["note"] == "already_sent" and len(partner_chat) == 1


@pytest.mark.asyncio
async def test_login_before_the_close_reads_but_waits_for_the_wrap(kite, partner_chat):
    db = settings.DB_PATH
    await _seed(db)
    await zerodha.on_login("reqtok12", T(11, 0))
    assert (await zerodha.wait_review_sync())["note"] == "before_close" and partner_chat == []


@pytest.mark.asyncio
async def test_a_slow_deeper_read_never_delays_the_login(kite, monkeypatch):
    """[A22-P4] Order histories, positions, cash and prices could take minutes
    (40 histories at 3 at a time, 15 s per call); the gateway waits 45 s."""
    import asyncio
    release = asyncio.Event()
    real = zerodha._read_details

    async def slow(*args):
        await release.wait()
        return await real(*args)

    monkeypatch.setattr(zerodha, "_read_details", slow)
    kite["orders"] = [_order("O1", "BUY", 20, T(12, 9, 5))]
    kite["trades"] = [_trade("O1", 20, 518.0, T(12, 9, 10))]
    result = await asyncio.wait_for(zerodha.on_login("reqtok12", T(12, 30)), 2)
    assert result["sync"] == {"state": "enriching", "started_at": T(12, 30).isoformat(), "option_orders": 1}
    release.set()
    assert (await zerodha.wait_review_sync())["note"] == "before_close"
    assert zerodha.review_sync(T(12, 31))["state"] == "done"


@pytest.mark.asyncio
async def test_one_deadline_covers_the_session_and_the_fills(kite, monkeypatch):
    import asyncio
    real = zerodha._sync_fills

    async def slow_fills(*args):
        await asyncio.sleep(0.5)
        return await real(*args)

    monkeypatch.setattr(zerodha, "_sync_fills", slow_fills)
    monkeypatch.setattr(zerodha, "LOGIN_DEADLINE_SEC", 0.1)
    result = await asyncio.wait_for(zerodha.on_login("reqtok12", T(12, 30)), 2)
    # The page opens and shows "reading"; the read finishes in the background.
    assert result["connected"] and result["sync"]["state"] == "reading"
    await zerodha.wait_review_sync()
    assert zerodha.review_sync(T(12, 31))["state"] == "done"


@pytest.mark.asyncio
async def test_the_deeper_read_has_its_own_budget_and_a_failed_fills_read_is_the_logins_error(kite, monkeypatch):
    import asyncio

    async def stuck(*args):
        await asyncio.sleep(5)

    monkeypatch.setattr(zerodha, "_read_details", stuck)
    monkeypatch.setattr(zerodha, "ENRICH_BUDGET_SEC", 0.1)
    await zerodha.on_login("reqtok12", T(12, 30))
    synced = await zerodha.wait_review_sync()
    assert synced["details"] == "deadline" and zerodha.review_sync(T(12, 31))["state"] == "partial"

    async def expired(*args):
        raise zerodha.BrokerError("TokenException", "Token is invalid or has expired.")

    monkeypatch.setattr(zerodha, "_sync_fills", expired)
    with pytest.raises(zerodha.BrokerError) as err:
        await zerodha.on_login("reqtok12", T(12, 40))
    assert err.value.code == "TokenException"
    assert zerodha.review_sync(T(12, 41)) == {"state": "failed", "started_at": T(12, 40).isoformat(),
                                               "finished_at": zerodha._review_state["finished_at"],
                                               "error": "TokenException"}


def test_card_buttons_stay_off_with_zerodha(monkeypatch):
    monkeypatch.setattr(settings, "PARTNER_FILL_CAPTURE_ENABLED", True)
    assert pfc.keyboard_for("manual_market_advisory", {"advisory_id": CARD_ID}) is None
    monkeypatch.setattr(settings, "PARTNER_FILL_BUTTONS_WITH_ZERODHA", True)
    assert pfc.keyboard_for("manual_market_advisory", {"advisory_id": CARD_ID}) is not None
    monkeypatch.setattr(settings, "PARTNER_FILL_BUTTONS_WITH_ZERODHA", False)
    monkeypatch.setattr(settings, "PARTNER_KITE_API_KEY", "")
    assert pfc.keyboard_for("manual_market_advisory", {"advisory_id": CARD_ID}) is not None


# ---------------------------------------------------------------------------
# stops (O21-PL)
# ---------------------------------------------------------------------------

def test_sl_sell_orders_on_options_become_stops_with_their_state():
    orders = [
        _order("S1", "SELL", 20, T(12, 10), order_type="SL", status="TRIGGER PENDING", trigger_price=465.0),
        _order("S2", "SELL", 20, T(12, 11), order_type="SL-M", status="CANCELLED", trigger_price=460.0,
               exchange_update_timestamp=_ts(T(12, 38))),
        _order("S3", "SELL", 20, T(12, 12), order_type="SL", status="CANCELLED", trigger_price=455.0,
               filled_quantity=20),
        _order("S4", "SELL", 20, T(12, 13), order_type="SL", status="COMPLETE", trigger_price=450.0),
        _order("S5", "SELL", 20, T(12, 14), order_type="LIMIT", status="OPEN", price=600.0),
        _order("S6", "BUY", 20, T(12, 15), order_type="SL", status="TRIGGER PENDING", trigger_price=530.0),
        _order("S7", "SELL", 1, T(12, 16), symbol="RELIANCE", exchange="NSE", order_type="SL", trigger_price=1.0),
        _order("S8", "SELL", 20, T(12, 17), order_type="SL", status="REJECTED", trigger_price=470.0),
    ]
    stops = zerodha.stops_from_orders(orders, resolve=_resolve)
    # A target (LIMIT), a buy stop and an equity order are not stops; a part-filled cancel did sell.
    assert [(s["source_id"], s["status"], s["trigger_price"]) for s in stops] == [
        ("kite:S1", "PENDING", 465.0), ("kite:S2", "CANCELLED", 460.0), ("kite:S3", "TRIGGERED", 455.0),
        ("kite:S4", "TRIGGERED", 450.0), ("kite:S8", "REJECTED", 470.0)]
    assert stops[1]["updated_at"] == T(12, 38).isoformat() and stops[0]["kind"] == "SL_ORDER"


def _gtt(gid, triggers, last, status="active", side="SELL", kind="single"):
    return {"id": gid, "type": kind, "status": status, "created_at": _ts(T(12, 11)), "updated_at": _ts(T(12, 40)),
            "condition": {"exchange": "BFO", "tradingsymbol": SYMBOL, "trigger_values": triggers, "last_price": last},
            "orders": [{"transaction_type": side, "quantity": 20, "order_type": "LIMIT", "price": triggers[0]}]}


def test_sell_gtts_that_protect_the_position_become_stops():
    gtts = [_gtt(1, [465.0], 518.0), _gtt(2, [600.0], 518.0),
            _gtt(3, [460.0, 620.0], 518.0, kind="two-leg", status="triggered"),
            _gtt(4, [465.0], 518.0, side="BUY"), _gtt(5, [465.0], 518.0, status="deleted")]
    stops = zerodha.stops_from_gtts(gtts, resolve=_resolve)
    # A single trigger above the price is a target; an OCO's stop is its lower leg.
    assert [(s["source_id"], s["kind"], s["trigger_price"], s["status"]) for s in stops] == [
        ("gtt:1", "GTT", 465.0, "PENDING"), ("gtt:3", "GTT", 460.0, "TRIGGERED"),
        ("gtt:5", "GTT", 465.0, "CANCELLED")]


@pytest.mark.asyncio
async def test_a_zerodha_day_checks_stops_from_the_order_book(kite):
    db = settings.DB_PATH
    await _seed(db)
    await zerodha.create_session("reqtok12", T(15, 41))
    kite["orders"] = [_order("O1", "BUY", 20, T(12, 9, 5)),
                      _order("S1", "SELL", 20, T(12, 10), order_type="SL", status="CANCELLED", trigger_price=465.0,
                             exchange_update_timestamp=_ts(T(12, 38))),
                      _order("O2", "SELL", 20, T(12, 56), order_type="MARKET")]
    kite["trades"] = [_trade("O1", 20, 518.0, T(12, 9, 10)), _trade("O2", 20, 430.0, T(12, 56, 2))]
    result = await zerodha.sync_book(T(15, 45))
    assert result["option_orders"] == 2 and result["unfilled_orders"] == 1
    stops = await zerodha.stop_orders(db, "2026-10-19", "2026-10-19")
    assert [(s["source_id"], s["status"], s["updated_at"]) for s in stops] == [
        ("kite:S1", "CANCELLED", T(12, 38).isoformat())]
    view = await pc.load_partner_coach(db, days=3, now=T(16, 0))
    item = view["days"][0]["cards"][0]
    codes = [f["code"] for f in item["flags"]]
    assert "STOP_CANCELLED" in codes and "NO_STOP_ORDER" not in codes
    assert view["zerodha"]["days"]["2026-10-19"]["stops_known"] is True


@pytest.mark.asyncio
async def test_unreadable_gtts_turn_the_stop_checks_off(kite, monkeypatch):
    db = settings.DB_PATH
    await _seed(db)
    await zerodha.create_session("reqtok12", T(15, 41))
    fake = zerodha._kite_call

    async def no_gtts(method, path, **kwargs):
        if path == "/gtt/triggers":
            raise zerodha.BrokerError("PermissionException", "not on this plan")
        return await fake(method, path, **kwargs)

    monkeypatch.setattr(zerodha, "_kite_call", no_gtts)
    kite["orders"] = [_order("O1", "BUY", 20, T(12, 9, 5)), _order("O2", "SELL", 20, T(12, 56))]
    kite["trades"] = [_trade("O1", 20, 518.0, T(12, 9, 10)), _trade("O2", 20, 430.0, T(12, 56, 2))]
    result = await zerodha.sync_book(T(15, 45))
    assert result["days"]["2026-10-19"] == {"option_orders": 2, "complete": True, "stops_known": False}
    view = await pc.load_partner_coach(db, days=3, now=T(16, 0))
    item = view["days"][0]["cards"][0]
    # Without the GTT list a missing SL order may be a GTT stop: say nothing about stops.
    assert "NO_STOP_ORDER" not in [f["code"] for f in item["flags"]] and "stops" not in item


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------

def _client(monkeypatch):
    import main  # noqa: F401  (main includes the router; importing the route first is circular)
    import routes_partner_coach as route
    monkeypatch.setattr(route._main, "_check_internal_secret", lambda request, name: None)
    app = FastAPI()
    app.include_router(route.router)
    return TestClient(app)


def test_session_route_maps_errors_without_details(kite, monkeypatch):
    client = _client(monkeypatch)
    assert client.post("/partner/broker/session", json={"request_token": "bad token!"}).status_code == 422
    kite["user_id"] = "ZZ9999"
    response = client.post("/partner/broker/session", json={"request_token": "reqtok12"})
    assert response.status_code == 403 and response.json()["detail"] == {"code": "wrong_account"}
    response = client.post("/partner/broker/sync")
    assert response.status_code == 409 and response.json()["detail"] == {"code": "not_connected"}
    status = client.get("/partner/broker/status").json()
    assert status == {"configured": True, "connected": False, "account": None, "login_at": None,
                      "expires_at": None, "read_only": True}
