"""N08: fixes from the partner's Nov 6 session (Production evidence, read-only).

- C1: a buy of a card's option inside its buy window takes the card's stop and target. The N04-A lookup only ran
  when ``size`` was None and _start_plan always passes one, so no real buy ever did: the 09:50 SENSEX 79800 CE card
  said SL ₹636.85, the watch said "Plan stop ₹671.1"; the partner's stop at ₹680 sold at 10:54 (low ₹648), and the
  card reached its target at 13:20.
- C2: a card's follow-up never tells the partner to sell an option the trade watch sees none of: the 13:20 "Book
  profit" and 15:10 "square off by 15:15" came after the partner's stop had sold the option at 10:54.
- C3: the evening review does not call a sale by the partner's own SL order "selling on a wobble".
- L1: a stop moved down but still above the plan stop says so (it is still told).
"""
import json
from datetime import datetime, timedelta

import aiosqlite
import pytest
import pytz

import partner_coach as pc
import partner_watch as pw
from config import settings
from tests.test_partner_broker_sync import kite, partner_app  # noqa: F401
from tests.test_partner_watch import D, SYMBOL, _login, _market, _o, watch  # noqa: F401

IST = pytz.timezone("Asia/Kolkata")


# ---------------------------------------------------------------------------
# C1: the card's plan for a buy on the card
# ---------------------------------------------------------------------------

async def _deliver_card(db_path: str, *, made, fill_by, sl=66.0, symbol=SYMBOL, advisory_id="card1"):
    view = {"symbol": symbol, "quote_at": made.isoformat(), "fill_by": fill_by.isoformat(), "buy_limit": 76.0,
            "sl_premium": sl, "target_premium_low": 84.0, "target_premium": 92.0, "level_basis": "INDEX",
            "invalidation_index": 22560.0, "target_index": 22420.0, "strike": 22300.0, "opt_type": "PE",
            "lot_size": 65, "fee_segment": "NFO", "fut_to_index_offset": 0.0}
    payload = {"session_date": made.date().isoformat(), "buyer_view": view, "profile_id": "default",
               "management_deadline": made.replace(hour=15, minute=15, second=0, microsecond=0).isoformat()}
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO partner_advisory_ideas(advisory_id,economic_version,scope,underlying,exchange,status,evidence,"
            "profile_id,profile_version,quote_time,valid_until,rendered_card,payload,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (advisory_id, "v", "MARKET_SETUP", "NIFTY", "NSE", "DELIVERED_ACKNOWLEDGED", "RESEARCH_ONLY", "default", 1,
             made.isoformat(), fill_by.isoformat(), "card", json.dumps(payload), made.isoformat(), made.isoformat()))
        await db.execute("INSERT INTO partner_hedge_messages(kind,dedup_key,sent_at,delivered) VALUES(?,?,?,1)",
                         ("manual_market_advisory", advisory_id, (made + timedelta(seconds=3)).isoformat()))
        await db.commit()
    return payload


@pytest.mark.asyncio
async def test_a_buy_on_the_card_gets_the_cards_stop_in_its_plan_message(watch, kite):
    db = settings.DB_PATH
    await _login()
    market = _market(D(11, 29, 30))
    await pw.watch_tick(D(11, 29, 0), market=market)                     # the first read seeds
    await _deliver_card(db, made=D(11, 28, 40), fill_by=D(11, 38, 40))
    kite["orders"] = [_o("101", "BUY", D(11, 29, 17), average_price=75.05)]
    await pw.watch_tick(D(11, 29, 25), market=market)
    text = watch[-1]["text"]
    assert watch[-1]["kind"] == "watch_plan"
    lines = text.splitlines()
    assert lines[0] == "🟢 You bought NIFTY 22300 PE · 1 lot (65) at ₹75.05 on the 11:28 card"
    assert any(line.startswith("🛑 The card's stop ₹66 (or exit on a 5-min close over") for line in lines)
    assert "trigger ₹66," in text and "Plan stop ₹" not in text          # one stop: the card's
    [version] = await pw.plan_versions(db, "101")
    assert (version["plan"].stop, version["plan"].stop_basis, version["plan"].target) == (66.0, "CARD", 92.0)


@pytest.mark.asyncio
async def test_a_buy_after_the_card_window_is_told_it_is_not_the_cards_trade(watch, kite):
    db = settings.DB_PATH
    await _login()
    market = _market(D(11, 45, 30))
    await pw.watch_tick(D(11, 45, 0), market=market)
    await _deliver_card(db, made=D(11, 28, 40), fill_by=D(11, 38, 40))
    kite["orders"] = [_o("101", "BUY", D(11, 45, 10), average_price=75.05)]
    await pw.watch_tick(D(11, 45, 20), market=market)
    lines = watch[-1]["text"].splitlines()
    assert lines[1] == "• Not the 11:28 card's trade: its buy window ended 11:38. This plan is for your own buy."
    assert lines[2].startswith("🛑 Plan stop ₹")
    [version] = await pw.plan_versions(db, "101")
    assert version["plan"].stop_basis != "CARD"


@pytest.mark.asyncio
async def test_nov6_the_0950_card_and_the_partners_two_buys(tmp_path):
    """The stored Nov 6 card (buyer view as delivered) and the partner's buys: 09:50:29 at ₹764.3 (on the card) and
    10:55:29 at ₹706.75 (after its 10:00 skip-after)."""
    from hedge_advisory import init_hedge_advisory_db
    from partner_manual_advisory import init_partner_advisory_db
    db_path = str(tmp_path / "nov6.db")
    await init_partner_advisory_db(db_path)
    await init_hedge_advisory_db(db_path)
    view = {"ask": 743.7, "bid": 742.75, "buy_limit": 759.75, "dte": 6, "expiry": "2026-11-12", "fee_segment": "BFO",
            "fill_by": "2026-11-06T10:00:10.322423+05:30", "fut_to_index_offset": 146.49,
            "invalidation_index": 79460.4, "level_basis": "INDEX", "lot_size": 20, "opt_type": "CE",
            "quote_at": "2026-11-06T09:50:10.322423+05:30", "sl_premium": 636.85, "strike": 79800.0,
            "symbol": "SENSEX26N1279800CE", "target_index": 80003.77, "target_premium": 913.15,
            "target_premium_low": 776.2, "tick_size": 0.05, "version": "BUYER_VIEW_V2"}
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO partner_advisory_ideas(advisory_id,economic_version,scope,underlying,exchange,status,evidence,"
            "profile_id,profile_version,quote_time,valid_until,rendered_card,payload,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("389bfe0c20ac36c6b762bb2f", "v", "MARKET_SETUP", "SENSEX", "BSE", "RETIRED_SESSION_END", "RESEARCH_ONLY",
             "default", 1, view["quote_at"], view["fill_by"], "card",
             json.dumps({"session_date": "2026-11-06", "buyer_view": view}), view["quote_at"], view["quote_at"]))
        await db.execute("INSERT INTO partner_hedge_messages(kind,dedup_key,sent_at,delivered) VALUES(?,?,?,1)",
                         ("manual_market_advisory", "389bfe0c20ac36c6b762bb2f", "2026-11-06T09:50:13.030822+05:30"))
        await db.commit()

    def buy(h, m, s, price):
        return pw.Trip("k", "BFO", "SENSEX26N1279800CE", "NRML", IST.localize(datetime(2026, 11, 6, h, m, s)),
                       bought=20, buy_value=20 * price, buy_orders=1)

    first, again = buy(9, 50, 29, 764.3), buy(10, 55, 29, 706.75)
    card = await pw.card_for(db_path, "2026-11-06", first)
    assert pw.card_relation(card, first) == "ON_CARD"
    watch_plan = pw.Plan(entry=764.3, qty=20, stop=671.1, stop_basis="INDEX", stop_index=79724.4, target=954.35,
                         target_index=80267.8, cash=82611.8)                       # what the 09:50:31 PLAN said
    plan = pw.adopt_card(watch_plan, card, "BFO")
    assert (plan.stop, plan.stop_basis, plan.target) == (636.85, "CARD", 913.15)
    lines = pw.plan_text(first, plan, lots=1, card=card, card_relation_="ON_CARD").splitlines()
    assert lines[0] == "🟢 You bought SENSEX 79800 CE · 1 lot (20) at ₹764.3 on the 09:50 card"
    assert lines[1] == "⚠️ You paid ₹764.3; the card said buy up to ₹759.75."
    assert lines[2].startswith("🛑 The card's stop ₹636.85 (or exit on a 5-min close under SENSEX ≈79,460).")
    assert pw.card_relation(await pw.card_for(db_path, "2026-11-06", again), again) == "AFTER_WINDOW"


# ---------------------------------------------------------------------------
# C2: what the partner holds, for the card's follow-ups
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_watch_says_what_is_held_and_nothing_when_it_cannot(watch, kite, monkeypatch):
    await _login()
    market = _market(D(10, 0, 30))
    assert pw.held_units(SYMBOL, D(10, 0)) is None                       # no book read yet
    await pw.watch_tick(D(10, 0), market=market)
    kite["orders"] = [_o("101", "BUY", D(10, 0, 10), average_price=75.05)]
    await pw.watch_tick(D(10, 0, 20), market=market)
    assert pw.held_units(SYMBOL, D(10, 0, 30)) == 65
    assert pw.held_units("NIFTY26OCT22400CE", D(10, 0, 30)) == 0          # another option: none held
    # The stop sells it.
    kite["orders"].append(_o("201", "SELL", D(10, 5), order_type="SL", status="COMPLETE", trigger_price=70.0,
                             average_price=70.0))
    await pw.watch_tick(D(10, 5, 5), market=market)
    assert pw.held_units(SYMBOL, D(10, 5, 10)) == 0
    # A read older than HELD_VIEW_FRESH, or the watch off, says nothing.
    assert pw.held_units(SYMBOL, D(10, 5, 5) + pw.HELD_VIEW_FRESH + timedelta(seconds=1)) is None
    monkeypatch.setattr(settings, "PARTNER_WATCH_ENABLED", False)
    assert pw.held_units(SYMBOL, D(10, 5, 10)) is None


async def _queued_update(db_path: str, event_type: str, observed, *, payload: dict, update_id="u1"):
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO partner_advisory_updates(update_id,advisory_id,event_type,observed_at,observed_underlying,"
            "rendered_update,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (update_id, "card1", event_type, observed.isoformat(), 22420.0,
             "🎯 NIFTY 22300 PE (11:28 card, bought by 11:38): target reached (NIFTY ≈22,420 at 13:20). Book profit; "
             "on anything you keep, move SL to your entry price." if event_type == "TARGET_ZONE" else
             "⏰ NIFTY 22300 PE (11:28 card, bought by 11:38): square off by 15:15. No overnight hold.",
             "QUEUED", observed.isoformat(), observed.isoformat()))
        await db.commit()


@pytest.fixture
def advisory_db(tmp_path, monkeypatch):
    import hedge_advisory
    sent = []

    async def transport(*args, **kwargs):
        sent.append(args[3])
        return True

    monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_ENABLED", True)
    monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_DELIVERY_ENABLED", True)
    monkeypatch.setattr(hedge_advisory, "_send_claimed_review", transport)
    return str(tmp_path / "advisory.db"), sent


async def _init(db_path):
    from hedge_advisory import init_hedge_advisory_db
    from partner_manual_advisory import init_partner_advisory_db
    await init_partner_advisory_db(db_path)
    await init_hedge_advisory_db(db_path)


async def _status(db_path, update_id="u1"):
    async with aiosqlite.connect(db_path) as db:
        return await (await db.execute(
            "SELECT status, status_reason, rendered_update FROM partner_advisory_updates WHERE update_id=?",
            (update_id,))).fetchone()


@pytest.mark.asyncio
@pytest.mark.parametrize("held, said", [
    (None, "Book profit; on anything you keep, move SL to your entry price."),   # the watch cannot say: as before
    (65, "Book profit; on anything you keep, move SL to your entry price."),     # held: as before
    (0, "🎯 NIFTY 22300 PE (11:28 card, bought by 11:38): target reached (NIFTY ≈22,420 at 13:20). You hold none "
        "of it: nothing to sell."),
])
async def test_a_target_is_told_as_nothing_to_sell_when_none_is_held(advisory_db, monkeypatch, held, said):
    from partner_manual_advisory import dispatch_queued_management_update, pending_management_updates
    db_path, sent = advisory_db
    await _init(db_path)
    observed = IST.localize(datetime(2026, 11, 6, 13, 20))
    payload = await _deliver_card(db_path, made=IST.localize(datetime(2026, 11, 6, 11, 28, 40)),
                                  fill_by=IST.localize(datetime(2026, 11, 6, 11, 38, 40)))
    await _queued_update(db_path, "TARGET_ZONE", observed, payload=payload)
    asked = []
    monkeypatch.setattr(pw, "held_units", lambda symbol, now: asked.append(symbol) or held)
    now = observed + timedelta(seconds=26)
    [update] = await pending_management_updates(db_path, now=now)
    assert update["symbol"] == SYMBOL
    assert await dispatch_queued_management_update(db_path, update, now=now, clock=lambda: now)
    assert asked == [SYMBOL] and sent[0].endswith(said)
    status, reason, stored = await _status(db_path)
    assert status == "DELIVERED_ACKNOWLEDGED" and stored == sent[0]
    assert reason == ("partner_holds_none" if held == 0 else None)


@pytest.mark.asyncio
async def test_an_unsent_not_held_line_leaves_the_update_to_be_checked_again(advisory_db, monkeypatch):
    import hedge_advisory
    from partner_manual_advisory import dispatch_queued_management_update, pending_management_updates
    db_path, _sent = advisory_db
    await _init(db_path)
    observed = IST.localize(datetime(2026, 11, 6, 13, 20))
    payload = await _deliver_card(db_path, made=IST.localize(datetime(2026, 11, 6, 11, 28, 40)),
                                  fill_by=IST.localize(datetime(2026, 11, 6, 11, 38, 40)))
    await _queued_update(db_path, "TARGET_ZONE", observed, payload=payload)

    async def refused(*args, **kwargs):
        return False

    monkeypatch.setattr(hedge_advisory, "_send_claimed_review", refused)
    monkeypatch.setattr(pw, "held_units", lambda symbol, now: 0)
    now = observed + timedelta(seconds=26)
    [update] = await pending_management_updates(db_path, now=now)
    assert not await dispatch_queued_management_update(db_path, update, now=now, clock=lambda: now)
    status, reason, stored = await _status(db_path)
    assert (status, reason) == ("QUEUED", None) and stored.endswith("move SL to your entry price.")


@pytest.mark.asyncio
async def test_the_square_off_reminder_is_not_sent_when_none_is_held(advisory_db, monkeypatch):
    from partner_manual_advisory import HELD_NONE, dispatch_queued_management_update, pending_management_updates
    db_path, sent = advisory_db
    await _init(db_path)
    observed = IST.localize(datetime(2026, 11, 6, 15, 10, 5))
    payload = await _deliver_card(db_path, made=IST.localize(datetime(2026, 11, 6, 11, 28, 40)),
                                  fill_by=IST.localize(datetime(2026, 11, 6, 11, 38, 40)))
    await _queued_update(db_path, "SESSION_EXIT_REMINDER", observed, payload=payload)
    monkeypatch.setattr(pw, "held_units", lambda symbol, now: 0)
    now = observed + timedelta(seconds=1)
    [update] = await pending_management_updates(db_path, now=now)
    assert not await dispatch_queued_management_update(db_path, update, now=now, clock=lambda: now)
    assert sent == []
    status, reason, _text = await _status(db_path)
    assert (status, reason) == ("EXPIRED_UNSENT", HELD_NONE) == ("EXPIRED_UNSENT", pc.HELD_NONE_REASON)
    assert await pending_management_updates(db_path, now=now + timedelta(seconds=5)) == []    # never retried
    # The evening review still replays a hold of the card with that reminder at its time.
    [card] = await pc.load_cards(db_path, "2026-11-06", "2026-11-06")
    [reminder] = card["updates"]
    assert reminder["delivered_at"] is None and reminder["would_at"] == observed


def test_a_held_back_reminder_still_ends_a_replayed_hold():
    from tests.test_partner_coach import T, _card
    card = _card(updates=[], series=[(T(12, 10), 516.0), (T(15, 10), 550.0), (T(15, 15), 548.0)])
    card["updates"] = [{"event_type": "SESSION_EXIT_REMINDER", "delivered_at": None, "would_at": T(15, 10)}]
    out = pc.card_exit(card, T(12, 9), timedelta(seconds=0))
    assert (out["reason"], out["at"], out["price"]) == ("SQUARE_OFF_MESSAGE", T(15, 10), 550.0)


# ---------------------------------------------------------------------------
# C3: the partner's own stop is not "a wobble"
# ---------------------------------------------------------------------------

def test_a_sale_by_the_partners_own_closer_stop_is_not_called_an_early_exit():
    from tests.test_partner_coach import DAY, T, _card, _codes, _item, _rep, _stop, _view, _net, rs
    card = _card(updates=[("TARGET_ZONE", T(13, 0))])
    reports = [_rep("BUY", T(12, 9), 518.0), _rep("SELL", T(12, 20), 500.0)]
    stops = [_stop(500.0, "TRIGGERED", T(12, 10), T(12, 20))]
    item = _item(_view([card], reports, stops=stops, stops_known_days=frozenset({DAY})))
    assert "EARLY_EXIT" not in _codes(item)
    flag = next(f for f in item["flags"] if f["code"] == "STOP_TIGHTER_THAN_CARD")
    actual, held = _net(518.0, 500.0, 20), _net(518.0, 600.0, 20)
    assert flag["reason"] == ("Your SL order at ₹500 sold at 12:20 for ₹500; the card's SL was ₹464.7. The card's "
                              "target message came at 13:00 with the option at ₹600.")
    assert flag["better"] == f"The SL order at the card's ₹464.7: {rs(held)} instead of {rs(actual)}."
    assert flag["advice"] == pc.ADVICE["STOP_TIGHTER_THAN_CARD"]
    # A sale by hand (no stop fired) is still an early exit.
    manual = _item(_view([card], reports, stops=[_stop(470.0, "CANCELLED", T(12, 10), T(12, 25))],
                         stops_known_days=frozenset({DAY})))
    assert "EARLY_EXIT" in _codes(manual) and "STOP_TIGHTER_THAN_CARD" not in _codes(manual)


def test_the_stop_that_sold_is_matched_by_its_order_id_first():
    from tests.test_partner_coach import T
    trade = {"sells": [{"order_id": "261106220364825"}], "last_sell_at": T(10, 54, 48)}
    other = {"source_id": "kite:999", "status": "TRIGGERED", "trigger_price": 690.0, "updated_dt": T(10, 54, 50)}
    mine = {"source_id": "kite:261106220364825", "status": "TRIGGERED", "trigger_price": 680.0,
            "updated_dt": T(10, 54, 48)}
    assert pc._sold_by_own_stop(trade, [other, mine]) is mine
    assert pc._sold_by_own_stop(trade, [other]) is other                  # no id match: the one that fired then
    assert pc._sold_by_own_stop(trade, [dict(other, updated_dt=T(10, 57))]) is None
    assert pc._sold_by_own_stop(trade, None) is None


# ---------------------------------------------------------------------------
# L1: a stop moved down within the plan
# ---------------------------------------------------------------------------

def test_a_stop_moved_down_but_above_the_plan_stop_says_so():
    """Nov 6, 10:10: "you moved your stop down ₹98 → ₹96. If it is hit: −₹2,604 instead of −₹2,085. A stop moved down
    adds to the loss you chose when you placed it." The plan stop was ₹82.05."""
    at = IST.localize(datetime(2026, 11, 6, 9, 58, 59))
    trip = pw.Trip("1", "NFO", "NIFTY26N0924750CE", "NRML", at, bought=260, buy_value=260 * 105.51)
    plan = pw.Plan(entry=105.51, qty=260, stop=82.05, stop_basis="INDEX", stop_index=24573.0)
    text = pw.lowered_text(trip, 98.0, 96.0, "FIRST", plan)
    assert text.startswith("⚠️ NIFTY 24750 CE: you moved your stop down ₹98 → ₹96. If it is hit: −")
    assert text.endswith(" Still above the plan stop ₹82.05.")
    # Under the plan stop, giving up the buy price, or still in profit: as before.
    assert pw.lowered_text(trip, 98.0, 80.0, "BELOW_PLAN", plan).endswith(
        "That is under your plan stop ₹82.05: the loss can now be bigger than planned.")
    assert pw.lowered_text(trip, 106.0, 100.0, "GUARD", plan).endswith(
        "It was guarding your buy price; now this trade can end in a loss.")
    assert pw.lowered_text(trip, 125.0, 120.0, "FIRST", plan).endswith(
        "A stop moved down gives back profit it had kept for you.")
    assert pw.lowered_text(trip, 98.0, 96.0, "FIRST").endswith(               # no plan known: as before
        "A stop moved down adds to the loss you chose when you placed it.")
    moves = [{"id": "a", "old": 98.0, "new": 96.0, "units": 130}, {"id": "b", "old": 97.0, "new": 90.0, "units": 130}]
    assert pw.moved_text(trip, moves, "FIRST", plan).endswith(" Still above the plan stop ₹82.05.")
