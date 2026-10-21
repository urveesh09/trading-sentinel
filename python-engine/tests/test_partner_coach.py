"""[O21-PC] Partner coach: plan pricing, behaviour flags, rupee impacts and the evening note."""
import json
from datetime import datetime, timedelta

import aiosqlite
import pytest
import pytz

import partner_coach as pc
import partner_fill_capture as pfc
from config import settings
from fno_costs import calc_fno_costs

IST = pytz.timezone("Asia/Kolkata")
DAY = "2026-10-19"


def T(h, m, s=0):
    return IST.localize(datetime(2026, 10, 19, h, m, s))


def _series(points: dict) -> list:
    """{(h, m): ltp} -> sorted 5-minute prints."""
    return sorted((T(h, m), float(p)) for (h, m), p in points.items())


RISING = _series({(12, 10): 516, (12, 15): 520, (12, 20): 520, (12, 30): 540, (12, 45): 560, (13, 0): 590,
                  (13, 5): 600, (13, 30): 610, (14, 0): 560, (15, 10): 550, (15, 15): 548})
FALLING = _series({(12, 10): 540, (12, 15): 530, (12, 25): 500, (12, 40): 460, (12, 55): 430, (13, 10): 420,
                   (15, 15): 400})


def _card(advisory_id="c1", series=RISING, updates=(), **over):
    card = dict(advisory_id=advisory_id, underlying="SENSEX", day=DAY, delivered_at=T(12, 7), direction="SHORT",
                option="SENSEX 74200 PE", strike=74200.0, opt_type="PE", expiry="2026-10-22", lot_size=20,
                exchange="BFO", tick_size=0.05, ask=514.8, buy_limit=522.35, sl_premium=464.7,
                target_premium=667.3, target_low=567.2, fill_by=T(12, 16, 50), exit_by=T(15, 15),
                updates=[{"event_type": e, "delivered_at": at} for e, at in updates], series=list(series))
    card.update(over)
    return card


_ids = iter(range(1, 10_000))


def _rep(action, at, price, lots=1, advisory="c1", **over):
    row = {"report_id": next(_ids), "status": "ACTIVE", "action": action, "trade_at": at.isoformat(),
           "price": price, "lots": lots, "lot_size": 20, "advisory_id": advisory, "session_date": DAY,
           "underlying": "SENSEX", "strike": 74200.0, "opt_type": "PE", "tradingsymbol": "SENSEX26O2274200PE",
           "exchange": "BFO", "price_basis": "PARTNER_STATED", "source": "TELEGRAM_TEXT", "trade_at_basis": "STATED"}
    row.update(over)
    return row


def _net(entry, exit_, qty, exchange="BFO"):
    return round((exit_ - entry) * qty - calc_fno_costs(entry, exit_, qty, exchange=exchange), 2)


def _view(cards, reports, now=T(16, 0)):
    return pc.analyse(cards, reports, reaction_sec=120, now=now)


def _item(view, advisory_id="c1"):
    return next(i for row in view["days"] for i in row["cards"] if i["advisory_id"] == advisory_id)


def _codes(item):
    return [f["code"] for f in item["flags"]]


def test_a_followed_card_scores_both_sides_and_earns_positives():
    card = _card(updates=[("TARGET_ZONE", T(13, 0))])
    view = _view([card], [_rep("BUY", T(12, 9), 518.0), _rep("SELL", T(13, 3), 598.0)])
    item = _item(view)
    assert _codes(item) == []
    assert {p["code"] for p in item["positives"]} == {"BOUGHT_IN_LIMIT", "EXITED_WITH_CARD"}
    # The card's exit is the first 5-minute print 2 minutes after the target message: 13:05 = 600.
    assert item["plan"]["exit"] == 600.0 and item["plan"]["exit_reason"] == "TARGET_MESSAGE"
    assert item["plan"]["pnl"] == _net(518.0, 600.0, 20)
    assert item["partner"]["pnl"] == _net(518.0, 598.0, 20)
    summary = view["summary"]
    assert summary["followed_cards"] == 1 and summary["gap_vs_plan"] == round(_net(518, 598, 20) - _net(518, 600, 20), 2)


def test_chased_entry_and_held_past_stop_are_priced():
    view = _view([_card(series=FALLING)], [_rep("BUY", T(12, 10), 540.0), _rep("SELL", T(12, 56), 430.0)])
    item = _item(view)
    flags = {f["code"]: f for f in item["flags"]}
    assert set(flags) == {"ENTRY_ABOVE_LIMIT", "HELD_PAST_STOP"}
    assert flags["ENTRY_ABOVE_LIMIT"]["impact_rs"] == round(-(540.0 - 522.35) * 20, 2)
    assert "above the card's buy-up-to ₹522.35" in flags["ENTRY_ABOVE_LIMIT"]["reason"]
    assert flags["HELD_PAST_STOP"]["impact_rs"] == round((430.0 - 464.7) * 20, 2)
    # Chasing above the limit was a skip on the card: plan ₹0.
    assert item["plan"]["pnl"] == 0.0 and "price above the limit" in item["plan"]["note"]
    assert item["same_entry"]["reason"] == "STOP" and item["same_entry"]["exit"] == 464.7


def test_quick_reentry_after_a_loss_and_size_up_are_flagged_with_context():
    off = dict(advisory=None, underlying="NIFTY", strike=22950.0, opt_type="PE", lot_size=75, exchange="NFO")
    reports = [_rep("BUY", T(12, 10), 540.0), _rep("SELL", T(12, 56), 430.0),
               _rep("BUY", T(13, 5), 100.0, lots=2, **off), _rep("SELL", T(13, 40), 80.0, lots=2, **off)]
    view = _view([_card(series=FALLING)], reports)
    [off_item] = view["days"][0]["off_card"]
    codes = _codes(off_item)
    assert codes == ["OFF_CARD", "QUICK_REENTRY_AFTER_LOSS", "SIZE_UP_AFTER_LOSS"]
    reentry = off_item["flags"][1]
    assert "Bought 9 min after a −₹" in reentry["reason"] and "without a card" in reentry["reason"]
    assert "with 2 lots after 1" in reentry["reason"]
    assert off_item["partner"]["pnl"] == _net(100.0, 80.0, 150, "NFO")
    leak_codes = [leak["code"] for leak in view["leaks"]]
    assert leak_codes[0] in ("OFF_CARD", "QUICK_REENTRY_AFTER_LOSS", "SIZE_UP_AFTER_LOSS")
    note = pc.render_coach_note(view, DAY)
    lines = note.split("\n")
    assert lines[0].startswith("📒 Your trades today") and len(lines) <= 6
    assert lines[1].startswith("2 trades · −₹") and "card plan +₹0" in lines[1]
    assert any(line.startswith("Biggest gap:") for line in lines)
    assert any(line.startswith("Next time:") for line in lines)


def test_a_skipped_card_that_stopped_out_shows_the_saving():
    view = _view([_card(series=FALLING)], [_rep("SKIP", T(12, 8), None, lots=None)])
    item = _item(view)
    assert item["partner"]["status"] == "SKIPPED"
    # Following it: the print at 12:09 + 2 min is 12:10 = 540, above the 522.35 limit -> the card said skip.
    assert item["plan"]["pnl"] == 0.0 and "above the buy-up-to" in item["plan"]["note"]
    lower = _card(series=_series({(12, 10): 518, (12, 25): 500, (12, 40): 460, (15, 15): 400}))
    item = _item(_view([lower], [_rep("SKIP", T(12, 8), None, lots=None)]))
    assert item["plan"]["pnl"] == _net(518.0, 464.7, 20) < 0
    assert [p["code"] for p in item["positives"]] == ["SKIP_SAVED"]


def test_early_exit_and_giving_back_after_target():
    card = _card(updates=[("TARGET_ZONE", T(13, 0))])
    early = _item(_view([card], [_rep("BUY", T(12, 9), 518.0), _rep("SELL", T(12, 20), 520.0)]))
    [flag] = early["flags"]
    assert flag["code"] == "EARLY_EXIT" and flag["impact_rs"] == round((520.0 - 600.0) * 20, 2)
    late = _item(_view([card], [_rep("BUY", T(12, 9), 518.0), _rep("SELL", T(14, 0), 540.0)]))
    [flag] = late["flags"]
    assert flag["code"] == "GAVE_BACK_AFTER_TARGET" and flag["impact_rs"] == round((540.0 - 600.0) * 20, 2)


def test_late_entry_averaging_down_and_square_off():
    card = _card(series=FALLING)
    item = _item(_view([card], [_rep("BUY", T(12, 25), 500.0), _rep("BUY", T(12, 40), 460.0),
                                _rep("SELL", T(15, 25), 400.0, lots=2)]))
    assert _codes(item) == ["LATE_ENTRY", "AVERAGED_DOWN", "HELD_PAST_STOP", "HELD_PAST_SQUARE_OFF"]
    assert item["plan"]["pnl"] == 0.0
    # Three orders: the extra one pays its flat ₹20 + GST.
    assert item["partner"]["pnl"] == round((400.0 - 480.0) * 40 - pc.round_trip_costs(480.0, 400.0, 40, "BFO", orders=3), 2)


def test_overtrading_is_a_day_flag():
    reports = []
    for n, (h, m) in enumerate(((12, 10), (12, 30), (13, 0), (13, 30))):
        off = dict(advisory=None, underlying="NIFTY", strike=22900.0 + 50 * n, opt_type="CE", lot_size=75,
                   exchange="NFO")
        reports += [_rep("BUY", T(h, m), 100.0, **off), _rep("SELL", T(h, m + 10), 104.0, **off)]
    view = _view([_card()], reports)
    assert [f["code"] for f in view["days"][0]["day_flags"]] == ["OVERTRADING"]


def test_unreported_card_and_exit_without_buy_are_data_gaps_not_flags():
    card = _card(updates=[("TARGET_ZONE", T(13, 0))])
    item = _item(_view([card], []))
    assert item["partner"]["status"] == "NOT_REPORTED" and item["flags"] == []
    assert item["plan"]["entry"] == 516.0 and item["plan"]["pnl"] == _net(516.0, 600.0, 20)
    view = _view([card], [_rep("SELL", T(13, 3), 598.0, lots=None)])
    item = _item(view)
    assert item["partner"]["status"] == "EXIT_ONLY" and "buy price not reported" in item["plan"]["note"]
    assert view["data_quality"]["exits_without_buy"] == 1


@pytest.mark.asyncio
async def test_loader_uses_delivery_times_and_frozen_paths(monkeypatch):
    import fno_oi_store
    from tests.test_partner_fill_capture import CARD_ID, UPDATE_MSG, _seed
    db = settings.DB_PATH
    await _seed(db)
    await fno_oi_store.init_oi_db(db)
    async with aiosqlite.connect(db) as conn:
        await conn.execute(
            "INSERT INTO partner_advisory_updates(update_id,advisory_id,event_type,observed_at,observed_underlying,"
            "rendered_update,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            ("upd1", CARD_ID, "TARGET_ZONE", "2026-10-19T15:10:00+05:30", 73901.0, "t", "DELIVERED_ACKNOWLEDGED",
             "x", "x"))
        for hhmm, ltp in (("12:10:00", 516.0), ("15:10:00", 640.0), ("15:15:00", 650.0)):
            await conn.execute(
                "INSERT INTO fno_chain_oi(snap_ts,underlying,expiry,strike,opt_type,oi,volume,ltp,iv) "
                "VALUES(?,?,?,?,?,?,?,?,?)", (f"{DAY} {hhmm}", "SENSEX", "2026-10-22", 74200.0, "PE", 1, 1, ltp, 0.15))
        await conn.commit()
    await pfc.insert_report(db, {"dedup_key": "d1", "source": "DASHBOARD", "received_at": T(12, 9).isoformat(),
                                 "trade_at": T(12, 9).isoformat(), "trade_at_basis": "STATED", "action": "BUY",
                                 "advisory_id": CARD_ID, "session_date": DAY, "underlying": "SENSEX", "lots": 1,
                                 "lot_size": 20, "exchange": "BFO", "price": 518.0, "price_basis": "PARTNER_STATED"})
    view = await pc.load_partner_coach(db, days=3, now=T(16, 0))
    [item] = view["days"][0]["cards"]
    assert item["time"] == "12:06" and item["card_messages"] == [{"type": "TARGET_ZONE", "at": "15:10", "delivered": True}]
    assert item["same_entry"]["exit"] == 650.0      # first print >= 15:10:05 + 120 s
    assert view["data_quality"]["open_without_exit"] == 1
    assert await pc.freeze_card_paths(db, DAY, T(16, 0)) == 1
    async with aiosqlite.connect(db) as conn:
        await conn.execute("DELETE FROM fno_chain_oi")
        await conn.commit()
    again = await pc.load_partner_coach(db, days=3, now=T(16, 0))
    assert again["days"][0]["cards"][0]["same_entry"]["exit"] == 650.0
