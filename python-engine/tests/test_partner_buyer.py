"""[O12-PB 2026-10-12] Option-buyer partner messages.

The fixture mirrors the Oct 9 Production card: NIFTY future 22,535 about 58
points over the index, 22550/22600 CE vertical, published levels 22,522 /
22,475 / 22,628 on the future.
"""
import json
import math
from datetime import date, datetime

import aiosqlite
import pytest
import pytz

import partner_buyer as pb
from config import settings
from fno_chain import RISK_FREE_RATE, ChainSnapshot, years_to_expiry
from fno_instruments import FnoInstruments
from fno_models import Contract, ContractQuote, FnoDirection, OptionType
from partner_manual_advisory import (
    ADVICE_LABEL_UNCHECKED, PartnerAdvisoryProfile, build_directional_debit_spread,
    persist_candidate, queue_management_updates, run_intraday_session_lifecycle,
)

IST = pytz.timezone("Asia/Kolkata")
NOW = IST.localize(datetime(2026, 10, 9, 9, 54, 50))
EXPIRY = date(2026, 10, 13)
FUT = 22535.0
INDEX = 22477.0


def _setup(direction=FnoDirection.LONG, *, parity=True):
    book = FnoInstruments("NIFTY", segment="NFO")
    opt = OptionType.CE if direction == FnoDirection.LONG else OptionType.PE
    outer = 22600 if opt == OptionType.CE else 22500
    book._load_contracts([Contract(1, "NIFTY26OCTFUT", "NIFTY", date(2026, 10, 27), 0.0, "FUT", 65)] + [
        Contract(10 + i, f"NIFTY26O13{strike}{kind}", "NIFTY", EXPIRY, strike, kind, 65)
        for i, (strike, kind) in enumerate((s, k) for s in (22500, 22550, 22600) for k in ("CE", "PE"))
    ])

    def quote(strike, bid, ask):
        return ContractQuote(contract=book.option(EXPIRY, strike, opt), bid=bid, ask=ask, ltp=(bid + ask) / 2,
                             oi=10_000, volume=5_000, last_trade_time=NOW, bid_quantity=500, ask_quantity=500)

    prices = ((97.15, 97.35), (76.15, 76.35)) if opt == OptionType.CE else ((120.0, 120.4), (95.0, 95.4))
    forward = INDEX * math.exp(RISK_FREE_RATE * years_to_expiry(EXPIRY, NOW)) if parity else None
    snap = ChainSnapshot(NOW, EXPIRY, FUT, forward, 65, None, {
        (22550.0, opt.value): quote(22550, *prices[0]), (float(outer), opt.value): quote(outer, *prices[1]),
    })
    long_view = direction == FnoDirection.LONG
    candidate = build_directional_debit_spread(
        snap, book, direction, NOW,
        trigger_level=22522.09 if long_view else 22500.0,
        invalidation_level=22475.43 if long_view else 22560.0,
        target_level=22628.22 if long_view else 22420.0,
    )
    assert candidate is not None
    return candidate, snap


def test_buyer_plan_prices_the_long_leg_on_index_levels():
    candidate, snap = _setup()
    view = pb.buyer_plan(candidate, snap, NOW, entry_window_min=10)
    assert view["symbol"] == "NIFTY26O1322550CE" and view["opt_type"] == "CE"
    assert view["level_basis"] == "INDEX"
    assert view["fut_to_index_offset"] == pytest.approx(FUT - INDEX, abs=0.5)
    assert view["invalidation_index"] == pytest.approx(22475.43 - (FUT - INDEX), abs=0.5)
    assert view["target_index"] == pytest.approx(22628.22 - (FUT - INDEX), abs=0.5)
    # Stop below the ask, target above it, limit a few ticks over the ask.
    assert view["sl_premium"] < view["ask"] < view["target_premium"]
    assert view["ask"] < view["buy_limit"] <= round(view["ask"] * 1.04, 2) + 0.05
    assert round(view["buy_limit"] / 0.05, 6) == int(round(view["buy_limit"] / 0.05))
    # Max loss: filled at the limit, out one spread under the premium stop, plus charges.
    from fno_costs import calc_fno_costs
    exit_price = view["sl_premium"] - (view["ask"] - view["bid"])
    assert view["max_loss_per_lot"] == pytest.approx(
        (view["buy_limit"] - exit_price) * 65 + calc_fno_costs(view["buy_limit"], exit_price, 65), abs=0.01)
    assert view["fill_by"] == "2026-10-09T10:04:50+05:30"
    json.dumps(view)


def test_level_premiums_carry_an_hour_of_decay():
    # Calibrated on 41,950 Production snapshot pairs (Oct 5-12): with an hour
    # of decay the target-like median error is 0.0% (NIFTY), -1.7% (SENSEX).
    import options_math
    candidate, snap = _setup()
    view = pb.buyer_plan(candidate, snap, NOW, entry_window_min=10)
    T = years_to_expiry(EXPIRY, NOW) - 60 / (365 * 24 * 60)
    forward = snap.parity_forward + (22628.22 - FUT)
    expected = options_math.black76_price(forward, 22550, T, view["iv"], RISK_FREE_RATE, True)
    assert view["target_premium"] == pytest.approx(expected, abs=0.1)


def test_buyer_card_is_short_and_actionable():
    candidate, snap = _setup()
    view = pb.buyer_plan(candidate, snap, NOW, entry_window_min=10)
    card = pb.render_buyer_card(ADVICE_LABEL_UNCHECKED, view, underlying="NIFTY", direction="LONG",
                                management_deadline=candidate.management_deadline)
    lines = card.splitlines()
    assert lines[0] == ADVICE_LABEL_UNCHECKED
    assert lines[1] == "🟢 BUY NIFTY 22550 CE (13 Oct) @ ₹97.35"
    assert lines[2].startswith(f"Buy up to ₹{pb._px(view['buy_limit'])} · skip after 10:04 or if NIFTY drops under ≈22,46")
    assert lines[3] == (f"🛑 SL order at ₹{pb._px(view['sl_premium'])} right after buying "
                        "(or exit if NIFTY ≈22,417 breaks)")
    assert lines[4] == (f"🎯 Target: NIFTY ≈22,570 (option ≈₹{pb._est(view['target_premium_low'])}"
                        f"–{pb._est(view['target_premium'])})")
    assert view["target_premium_low"] == pytest.approx(view["target_premium"] * 0.85, abs=0.05)
    assert lines[5] == (f"Loss at SL ≈₹{view['max_loss_per_lot']:,.0f}/lot (65 qty, incl. charges) · "
                        "exit by 15:15 latest")
    assert len(card) < 450          # the spread card was 1,671 characters


def test_put_card_uses_put_language():
    candidate, snap = _setup(FnoDirection.SHORT)
    view = pb.buyer_plan(candidate, snap, NOW, entry_window_min=10)
    card = pb.render_buyer_card(ADVICE_LABEL_UNCHECKED, view, underlying="NIFTY", direction="SHORT",
                                management_deadline=candidate.management_deadline)
    assert "🔴 BUY NIFTY 22550 PE" in card and "rises over" in card and "close below" in card
    assert view["sl_premium"] < view["ask"] < view["target_premium"]


def test_without_parity_levels_stay_on_the_future_and_say_so():
    candidate, snap = _setup(parity=False)
    view = pb.buyer_plan(candidate, snap, NOW, entry_window_min=10)
    assert view["level_basis"] == "FUTURES" and view["fut_to_index_offset"] is None
    assert view["invalidation_index"] == pytest.approx(22475.43)
    card = pb.render_buyer_card(ADVICE_LABEL_UNCHECKED, view, underlying="NIFTY", direction="LONG",
                                management_deadline=candidate.management_deadline)
    assert "NIFTY fut drops under 22,522" in card and "exit if NIFTY fut 22,475 breaks" in card


def test_implausible_parity_is_refused():
    candidate, snap = _setup()
    snap.parity_forward = FUT * 1.05
    assert pb.fut_to_index_offset(snap, NOW) is None


def test_updates_are_one_line_actions():
    candidate, snap = _setup()
    view = pb.buyer_plan(candidate, snap, NOW, entry_window_min=10)
    at = NOW.replace(hour=13, minute=50, second=0)
    stop = pb.render_buyer_update(view, "INVALIDATION", underlying="NIFTY", observed_fut=22470.0,
                                  observed_at=at, management_deadline=candidate.management_deadline)
    assert stop.startswith("🛑 EXIT NIFTY 22550 CE now") and "NIFTY ≈22,41" in stop and "13:50" in stop
    target = pb.render_buyer_update(view, "TARGET_ZONE", underlying="NIFTY", observed_fut=22633.0,
                                    observed_at=at, management_deadline=candidate.management_deadline)
    assert "target reached" in target and "move SL to your entry price" in target
    reminder = pb.render_buyer_update(view, "SESSION_EXIT_REMINDER", underlying="NIFTY", observed_fut=0.0,
                                      observed_at=at, management_deadline=candidate.management_deadline)
    assert reminder == "⏰ NIFTY 22550 CE: square off by 15:15. No overnight hold."
    assert all("\n" not in text for text in (stop, target, reminder))


def _view(**changes):
    view = {"strike": 22550, "opt_type": "CE", "expiry": "2026-10-13", "dte": 1, "ask": 100.0,
            "buy_limit": 103.0, "sl_premium": 80.0, "target_premium": 140.0, "target_premium_low": 119.0,
            "max_loss_per_lot": 1600.0, "lot_size": 65, "level_basis": "INDEX", "trigger_index": 22464.0,
            "invalidation_index": 22417.0, "target_index": 22570.0, "fill_by": "2026-10-09T10:04:50+05:30"}
    view.update(changes)
    return pb.render_buyer_card("L", view, underlying="NIFTY", direction="LONG",
                                management_deadline=NOW.replace(hour=15, minute=15))


def test_reward_is_judged_on_the_low_end_of_the_target_range():
    # Low end 119 - 103 paid = 16 reward vs 103 - 80 = 23 risk.
    card = _view()
    assert "⚠ reward < risk in premium" in card and "expiry tomorrow" in card
    assert "⚠" not in _view(target_premium_low=130.0, target_premium=153.0)


def test_a_stop_hugging_the_price_is_flagged():
    # Oct 7 13:11 card: put ask 169.65, premium stop 166.4.
    card = _view(ask=169.65, buy_limit=170.15, sl_premium=166.4, target_premium=233.25, target_premium_low=198.25)
    assert "⚠ stop only ₹3.25 under the price, skip or tiny size" in card


def test_flow_lean_needs_two_net_votes():
    assert pb.flow_lean(2) == "CALLS ▲" and pb.flow_lean(-3) == "PUTS ▼" and pb.flow_lean(1) == "NEUTRAL"


def test_premium_path_and_range_line():
    assert pb.premium_path(97.35, [("t1", 107.05), ("t2", 140.6), ("t3", 109.25)]) == (
        "option ₹97.35 → peak ₹140.6 (+44%), last ₹109.25 (+12%)")
    assert pb.premium_path(97.35, []) == ""
    assert pb.range_line(22480, 22650, 22630) == "fut range 22,480–22,650, closed 22,630 (near the high)"


# ---------------------------------------------------------------------------
# advisory store: the partner's card and updates follow the flag
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", False)
    monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_SEND_UNQUALIFIED", True)
    return str(tmp_path / "advisory.db")


async def _persist(db, buyer_on, monkeypatch):
    monkeypatch.setattr(settings, "PARTNER_BUYER_MESSAGES", buyer_on)
    candidate, snap = _setup()
    view = pb.buyer_plan(candidate, snap, NOW, entry_window_min=10)
    stored = await persist_candidate(db, candidate, PartnerAdvisoryProfile(holding_period="INTRADAY"), now=NOW,
                                     queue_for_delivery=True, buyer_view=view)
    return candidate, view, stored


@pytest.mark.asyncio
async def test_queued_card_is_the_buyer_card_and_keeps_the_dispatch_label(store, monkeypatch):
    candidate, view, stored = await _persist(store, True, monkeypatch)
    assert stored["status"] == "QUEUED"
    card = stored["rendered_card"]
    # hedge_advisory._authorize_dispatch sends an unqualified card only when it opens with this label.
    assert card.startswith(ADVICE_LABEL_UNCHECKED)
    assert "BUY NIFTY 22550 CE" in card and "Structure:" not in card
    async with aiosqlite.connect(store) as db:
        rendered, payload = await (await db.execute(
            "SELECT rendered_card, payload FROM partner_advisory_ideas WHERE advisory_id=?",
            (stored["advisory_id"],))).fetchone()
    assert rendered == card and json.loads(payload)["buyer_view"] == view


@pytest.mark.asyncio
async def test_flag_off_keeps_the_full_structure_card(store, monkeypatch):
    _candidate, _view, stored = await _persist(store, False, monkeypatch)
    assert "Structure:" in stored["rendered_card"] and "BUY 1× NIFTY26O1322550CE" in stored["rendered_card"]


@pytest.mark.asyncio
async def test_buyer_card_has_the_same_identity_as_the_full_card(tmp_path, store, monkeypatch):
    _c, _v, on = await _persist(store, True, monkeypatch)
    _c, _v, off = await _persist(str(tmp_path / "other.db"), False, monkeypatch)
    assert (on["advisory_id"], on["economic_version"]) == (off["advisory_id"], off["economic_version"])


@pytest.mark.asyncio
async def test_a_malformed_view_falls_back_and_never_drops_a_card_or_stop(store, monkeypatch):
    monkeypatch.setattr(settings, "PARTNER_BUYER_MESSAGES", True)
    candidate, _snap = _setup()
    stored = await persist_candidate(store, candidate, PartnerAdvisoryProfile(holding_period="INTRADAY"),
                                     now=NOW, queue_for_delivery=True, buyer_view={"strike": 22550})
    # [O13] Falls back to an unpriced ONE-option card, never the spread card
    # with its SELL leg.
    card = stored["rendered_card"]
    assert stored["status"] == "QUEUED" and "BUY NIFTY 22550 CE" in card
    assert "Structure:" not in card and "SELL" not in card and "premium stop not priced" in card
    async with aiosqlite.connect(store) as db:
        payload = json.loads((await (await db.execute(
            "SELECT payload FROM partner_advisory_ideas WHERE advisory_id=?", (stored["advisory_id"],))).fetchone())[0])
        assert payload["buyer_view"]["version"] == pb.FALLBACK_VERSION
        payload["buyer_view"] = {"strike": 22550}        # as if stored by an older build
        await db.execute("UPDATE partner_advisory_ideas SET status='DELIVERED_ACKNOWLEDGED', payload=? "
                         "WHERE advisory_id=?", (json.dumps(payload), stored["advisory_id"]))
        await db.commit()
    queued = await queue_management_updates(store, underlying="NIFTY", observed_underlying=22470.0,
                                            observed_at=NOW.replace(hour=13, minute=50, second=0))
    assert queued and queued[0]["rendered_update"].startswith("Update to published idea")


@pytest.mark.asyncio
async def test_management_updates_use_buyer_wording(store, monkeypatch):
    _candidate, _view, stored = await _persist(store, True, monkeypatch)
    async with aiosqlite.connect(store) as db:
        await db.execute("UPDATE partner_advisory_ideas SET status='DELIVERED_ACKNOWLEDGED' WHERE advisory_id=?",
                         (stored["advisory_id"],))
        await db.commit()
    queued = await queue_management_updates(store, underlying="NIFTY", observed_underlying=22470.0,
                                            observed_at=NOW.replace(hour=13, minute=50, second=0))
    assert [q["event_type"] for q in queued] == ["INVALIDATION"]
    assert queued[0]["rendered_update"].startswith("🛑 EXIT NIFTY 22550 CE now")
    # [O13-B1] The stop closed the idea: no square-off reminder follows it.
    reminders = await run_intraday_session_lifecycle(store, now=NOW.replace(hour=15, minute=10, second=5))
    assert reminders == []


@pytest.mark.asyncio
async def test_session_reminder_uses_buyer_wording_for_a_live_idea(store, monkeypatch):
    _candidate, _view, stored = await _persist(store, True, monkeypatch)
    async with aiosqlite.connect(store) as db:
        await db.execute("UPDATE partner_advisory_ideas SET status='DELIVERED_ACKNOWLEDGED' WHERE advisory_id=?",
                         (stored["advisory_id"],))
        await db.commit()
    reminders = await run_intraday_session_lifecycle(store, now=NOW.replace(hour=15, minute=10, second=5))
    assert [r["rendered_update"] for r in reminders] == ["⏰ NIFTY 22550 CE: square off by 15:15. No overnight hold."]
