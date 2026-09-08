"""Acceptance tests for the NIFTY 50/SENSEX manual-advisory boundary."""
from datetime import date, datetime, timedelta

import pytest
import pytz

from fno_chain import ChainSnapshot
from fno_instruments import FnoInstruments
from fno_models import Contract, ContractQuote, FnoDirection, OptionType
from partner_manual_advisory import (
    AdvisoryScope, ManualDecision, PartnerAdvisoryProfile, StrategyEvidence,
    build_conditional_index_protective_put, build_directional_debit_spread, load_advisory_cards, persist_candidate,
    record_manual_feedback, save_partner_profile, validate_candidate,
    select_preferred_market_candidates, dispatch_queued_advisory, record_strategy_qualification,
    advisory_identity, dispatch_queued_management_update, queue_management_updates,
    load_advisory_diagnostics,
)

IST = pytz.timezone("Asia/Kolkata")
NOW = IST.localize(datetime(2026, 9, 7, 10, 0))


def _book(name: str, segment: str, expiry: date, step: float, lot: int) -> FnoInstruments:
    book = FnoInstruments(name, segment=segment)
    atm = 25000 if name == "NIFTY" else 82000
    contracts = [
        Contract(1, f"{name}FUT", name, expiry, 0.0, "FUT", lot),
        Contract(2, f"{name}LONG", name, expiry, atm, "CE", lot),
        Contract(3, f"{name}SHORT", name, expiry, atm + step, "CE", lot),
        Contract(4, f"{name}PUTLONG", name, expiry, atm, "PE", lot),
        Contract(5, f"{name}PUTSHORT", name, expiry, atm - step, "PE", lot),
    ]
    book._load_contracts(contracts)
    return book


def _quote(contract: Contract, bid: float, ask: float) -> ContractQuote:
    return ContractQuote(
        contract=contract, bid=bid, ask=ask, ltp=(bid + ask) / 2,
        oi=10_000, volume=5_000, last_trade_time=NOW,
        bid_quantity=500, ask_quantity=500,
    )


def _candidate(name="NIFTY", direction=FnoDirection.LONG):
    segment, step, lot, forward = (
        ("NFO", 50.0, 75, 25000.0) if name == "NIFTY" else ("BFO", 100.0, 20, 82000.0)
    )
    expiry = date(2026, 9, 10) if name == "NIFTY" else date(2026, 9, 11)
    book = _book(name, segment, expiry, step, lot)
    opt = OptionType.CE if direction == FnoDirection.LONG else OptionType.PE
    atm = book.atm_strike(forward)
    outer = atm + step if opt == OptionType.CE else atm - step
    long = book.option(expiry, atm, opt)
    short = book.option(expiry, outer, opt)
    quotes = {
        (atm, opt.value): _quote(long, 88.0, 90.0),
        (outer, opt.value): _quote(short, 45.0, 47.0),
    }
    snap = ChainSnapshot(NOW, expiry, forward, None, lot, None, quotes)
    candidate = build_directional_debit_spread(snap, book, direction, NOW)
    assert candidate is not None
    return candidate


@pytest.mark.parametrize("name", ["NIFTY", "SENSEX"])
def test_each_index_has_an_independent_valid_same_expiry_candidate(name):
    candidate = _candidate(name)
    result = validate_candidate(candidate, NOW)
    assert result.valid, result.reasons
    assert candidate.exchange == ("NSE" if name == "NIFTY" else "BSE")
    assert candidate.segment == ("NFO" if name == "NIFTY" else "BFO")
    assert len({leg.expiry for leg in candidate.legs}) == 1
    assert candidate.max_loss_rs and candidate.max_loss_rs > 0


def test_stale_or_missing_depth_never_makes_an_actionable_card():
    candidate = _candidate()
    assert "stale_or_future_quote" in validate_candidate(candidate, NOW + timedelta(seconds=31)).reasons
    no_depth = candidate.__class__(
        **{**candidate.__dict__, "legs": tuple(
            leg.__class__(**{**leg.__dict__, "ask_quantity": 0}) for leg in candidate.legs
        )}
    )
    assert "insufficient_displayed_depth" in validate_candidate(no_depth, NOW).reasons
    out_of_sync = candidate.__class__(
        **{**candidate.__dict__, "legs": (
            candidate.legs[0],
            candidate.legs[1].__class__(**{**candidate.legs[1].__dict__, "quote_time": (NOW - timedelta(seconds=6)).isoformat()}),
        )}
    )
    assert "out_of_sync_leg_quotes" in validate_candidate(out_of_sync, NOW).reasons


def test_full_lot_depth_and_independent_expiry_oracle_cannot_be_bypassed():
    candidate = _candidate()
    # One displayed unit is not an executable 75-unit NIFTY lot.
    shallow = candidate.__class__(**{**candidate.__dict__, "legs": tuple(
        leg.__class__(**{**leg.__dict__, "ask_quantity": 1, "bid_quantity": 1}) for leg in candidate.legs
    )})
    assert "insufficient_displayed_depth" in validate_candidate(shallow, NOW).reasons
    # ₹3,975 debit against a ₹3,750 payout must fail even if a supplied
    # display field claims a positive reward.
    expensive_legs = (
        candidate.legs[0].__class__(**{**candidate.legs[0].__dict__, "ask": 98.0}),
        candidate.legs[1],
    )
    impossible = candidate.__class__(**{**candidate.__dict__, "legs": expensive_legs,
        "net_debit_rs": 3975.0, "max_loss_rs": 3975.0, "max_profit_rs": 500.0})
    reasons = validate_candidate(impossible, NOW).reasons
    assert "vertical_nonpositive_expiry_reward" in reasons


def test_wrong_index_exchange_is_rejected_not_translated():
    candidate = _candidate("SENSEX")
    bad = candidate.__class__(**{**candidate.__dict__, "exchange": "NSE"})
    assert "wrong_exchange_for_underlying" in validate_candidate(bad, NOW).reasons


def test_personalised_scope_cannot_bypass_reconciled_portfolio_gate():
    candidate = _candidate()
    personal = candidate.__class__(**{**candidate.__dict__, "scope": AdvisoryScope.PERSONALISED_HEDGE})
    assert "personalised_scope_requires_reconciled_portfolio" in validate_candidate(personal, NOW).reasons


def test_conditional_protection_requires_explicit_coverage_and_never_claims_portfolio_bound():
    name, segment, step, lot, forward = "NIFTY", "NFO", 50.0, 75, 25000.0
    expiry = date(2026, 9, 10)
    book = _book(name, segment, expiry, step, lot)
    put = book.option(expiry, 24950.0, OptionType.PE)
    snap = ChainSnapshot(NOW, expiry, forward, None, lot, None, {(24950.0, "PE"): _quote(put, 80.0, 82.0)})
    assert build_conditional_index_protective_put(snap, book, NOW, exposure_assumption="", coverage_units=75) is None
    card = build_conditional_index_protective_put(
        snap, book, NOW, exposure_assumption="Assumes an existing long NIFTY futures exposure of 75 units.", coverage_units=75,
    )
    assert card is not None
    assert validate_candidate(card, NOW).valid
    from partner_manual_advisory import render_advisory_card
    text = render_advisory_card(card, "conditional-test")
    assert "Protection premium at risk" in text
    assert "not the loss bound of an unknown protected position" in text


def test_same_direction_nifty_and_sensex_are_overlap_suppressed_by_economics():
    nifty = _candidate("NIFTY")
    sensex = _candidate("SENSEX")
    preferred, suppressed = select_preferred_market_candidates([nifty, sensex])
    assert len(preferred) == 1
    assert len(suppressed) == 1
    assert {preferred[0].underlying, suppressed[0].underlying} == {"NIFTY", "SENSEX"}


@pytest.mark.asyncio
async def test_no_holdings_market_card_persists_without_send_or_order(db_path):
    profile = PartnerAdvisoryProfile(version=1, holding_period="INTRADAY_TO_3_SESSIONS")
    await save_partner_profile(db_path, profile, now=NOW)
    stored = await persist_candidate(db_path, _candidate(), profile, now=NOW)
    assert stored["status"] == "VALIDATED_SHADOW"
    assert stored["can_send"] is False and stored["can_place_orders"] is False
    assert "[MARKET SETUP] • NIFTY (NSE)" in stored["rendered_card"]
    assert "theoretical maximum loss" in stored["rendered_card"]
    cards = await load_advisory_cards(db_path)
    assert cards["cards"][0]["manual_feedback"] == []
    await record_manual_feedback(db_path, stored["advisory_id"], ManualDecision.TAKEN, reported_at=NOW)
    cards = await load_advisory_cards(db_path)
    assert cards["cards"][0]["manual_feedback"][0]["decision"] == "TAKEN"


@pytest.mark.asyncio
async def test_queued_manual_card_uses_hardened_delivery_boundary(db_path, monkeypatch):
    from config import settings
    import hedge_advisory

    profile = PartnerAdvisoryProfile(version=1, holding_period="INTRADAY_TO_3_SESSIONS")
    await save_partner_profile(db_path, profile, now=NOW)
    candidate = _candidate()
    candidate = candidate.__class__(**{**candidate.__dict__, "evidence": StrategyEvidence.QUALIFIED_FOR_ADVISORY})
    await record_strategy_qualification(
        db_path, underlying="NIFTY", structure_kind=candidate.structure_kind,
        horizon="INTRADAY_TO_3_SESSIONS", policy_version=candidate.policy_version,
        dataset_ref="frozen-test", reviewed_at=NOW,
    )
    stored = await persist_candidate(db_path, candidate, profile, now=NOW, queue_for_delivery=True)
    assert stored["status"] == "QUEUED"
    calls = []

    async def acknowledged(*args, **kwargs):
        calls.append((args, kwargs))
        return True

    monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_DELIVERY_ENABLED", True)
    monkeypatch.setattr(hedge_advisory, "_send_claimed_review", acknowledged)
    assert await dispatch_queued_advisory(db_path, stored, profile, now=NOW, clock=lambda: NOW)
    assert calls[0][0][1] == "manual_market_advisory"
    assert calls[0][1]["detail"]["phase"] == "manual_v1"
    cards = await load_advisory_cards(db_path)
    assert cards["cards"][0]["status"] == "DELIVERED_ACKNOWLEDGED"


@pytest.mark.asyncio
async def test_research_card_cannot_queue_and_expired_card_never_reaches_transport(db_path, monkeypatch):
    from config import settings
    import hedge_advisory

    profile = PartnerAdvisoryProfile(version=1, holding_period="INTRADAY_TO_3_SESSIONS")
    await save_partner_profile(db_path, profile, now=NOW)
    candidate = _candidate()
    await record_strategy_qualification(
        db_path, underlying="NIFTY", structure_kind=candidate.structure_kind,
        horizon="INTRADAY_TO_3_SESSIONS", policy_version=candidate.policy_version,
        dataset_ref="frozen-test", reviewed_at=NOW,
    )
    research = await persist_candidate(db_path, candidate, profile, now=NOW, queue_for_delivery=True)
    assert research["status"] == "VALIDATED_SHADOW"
    assert research["delivery_eligible"] is False

    qualified = candidate.__class__(**{**candidate.__dict__, "evidence": StrategyEvidence.QUALIFIED_FOR_ADVISORY})
    queued = await persist_candidate(db_path, qualified, profile, now=NOW, queue_for_delivery=True)
    assert queued["status"] == "QUEUED"
    calls = []
    async def transport(*args, **kwargs):
        calls.append((args, kwargs))
        return True
    monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_DELIVERY_ENABLED", True)
    monkeypatch.setattr(hedge_advisory, "_send_claimed_review", transport)
    assert not await dispatch_queued_advisory(
        db_path, queued, profile, now=NOW, clock=lambda: NOW + timedelta(seconds=31),
    )
    assert calls == []


@pytest.mark.asyncio
async def test_profile_structure_risk_and_window_are_delivery_gates(db_path):
    candidate = _candidate()
    profile = PartnerAdvisoryProfile(
        version=1, holding_period="INTRADAY_TO_3_SESSIONS",
        permitted_structures=("CONDITIONAL_PROTECTIVE_PUT",), risk_limit_rs=100.0,
        delivery_start_minute=11 * 60, delivery_end_minute=12 * 60,
    )
    await save_partner_profile(db_path, profile, now=NOW)
    stored = await persist_candidate(db_path, candidate, profile, now=NOW, queue_for_delivery=True)
    assert stored["status"] == "REJECTED"
    assert {"profile_structure_not_permitted", "profile_risk_limit_exceeded", "profile_delivery_window_closed"}.issubset(
        set(stored["validation"]["reasons"])
    )


@pytest.mark.asyncio
async def test_material_economics_create_linked_generation_without_quote_time_churn(db_path):
    profile = PartnerAdvisoryProfile(version=1, holding_period="INTRADAY_TO_3_SESSIONS")
    await save_partner_profile(db_path, profile, now=NOW)
    original = _candidate()
    same_economics_new_time = original.__class__(**{**original.__dict__,
        "quote_time": NOW + timedelta(seconds=2), "valid_until": NOW + timedelta(seconds=32),
    })
    assert advisory_identity(original) == advisory_identity(same_economics_new_time)
    first = await persist_candidate(db_path, original, profile, now=NOW)
    # A different executable ask changes the economic generation but retains
    # the thesis identity and links/retire the older preview.
    changed_legs = (original.legs[0].__class__(**{**original.legs[0].__dict__, "ask": 91.0}), original.legs[1])
    changed = original.__class__(**{**original.__dict__, "legs": changed_legs,
        "net_debit_rs": 3450.0, "max_loss_rs": 3450.0, "max_profit_rs": 300.0})
    second = await persist_candidate(db_path, changed, profile, now=NOW)
    assert first["advisory_id"] != second["advisory_id"]
    cards = await load_advisory_cards(db_path)
    by_id = {card["advisory_id"]: card for card in cards["cards"]}
    assert by_id[first["advisory_id"]]["status"] == "SUPERSEDED_MARKET"
    assert by_id[second["advisory_id"]]["supersedes_id"] == first["advisory_id"]


@pytest.mark.asyncio
async def test_market_condition_management_update_never_reads_partner_orders(db_path, monkeypatch):
    from config import settings
    import aiosqlite
    import hedge_advisory

    profile = PartnerAdvisoryProfile(version=1, holding_period="INTRADAY_TO_3_SESSIONS")
    await save_partner_profile(db_path, profile, now=NOW)
    base = _candidate()
    candidate = base.__class__(**{**base.__dict__, "trigger_level": 25010.0,
        "invalidation_level": 24950.0, "target_level": 25100.0})
    stored = await persist_candidate(db_path, candidate, profile, now=NOW)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE partner_advisory_ideas SET status='DELIVERED_ACKNOWLEDGED' WHERE advisory_id=?", (stored["advisory_id"],))
        await db.commit()
    updates = await queue_management_updates(
        db_path, underlying="NIFTY", observed_underlying=25105.0, observed_at=NOW + timedelta(seconds=10),
    )
    assert len(updates) == 1
    assert updates[0]["event_type"] == "TARGET_ZONE"
    assert "If you took the idea" in updates[0]["rendered_update"]
    # The same milestone is idempotent; no account/order information exists in
    # this API at all.
    assert not await queue_management_updates(
        db_path, underlying="NIFTY", observed_underlying=25106.0, observed_at=NOW + timedelta(seconds=11),
    )
    sent = []
    async def transport(*args, **kwargs):
        sent.append((args, kwargs))
        return True
    monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_ENABLED", True)
    monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_DELIVERY_ENABLED", True)
    monkeypatch.setattr(hedge_advisory, "_send_claimed_review", transport)
    assert await dispatch_queued_management_update(db_path, updates[0], now=NOW, clock=lambda: NOW + timedelta(seconds=12))
    assert sent[0][0][1] == "manual_advisory_update"


@pytest.mark.asyncio
async def test_diagnostics_are_per_index_and_do_not_claim_partner_pnl(db_path):
    profile = PartnerAdvisoryProfile(version=1, holding_period="INTRADAY_TO_3_SESSIONS")
    await save_partner_profile(db_path, profile, now=NOW)
    await persist_candidate(db_path, _candidate("NIFTY"), profile, now=NOW)
    rejected = _candidate("SENSEX").__class__(**{**_candidate("SENSEX").__dict__, "exchange": "NSE"})
    await persist_candidate(db_path, rejected, profile, now=NOW)
    diagnostic = await load_advisory_diagnostics(db_path)
    assert diagnostic["by_index"]["NIFTY"]["validated_shadow"] == 1
    assert diagnostic["by_index"]["SENSEX"]["rejected"] == 1
    assert "not a fill or P&L" in diagnostic["outcome_interpretation"]


@pytest.mark.asyncio
async def test_profile_revision_supersedes_old_market_card(db_path):
    profile = PartnerAdvisoryProfile(version=1, holding_period="INTRADAY_TO_3_SESSIONS")
    await save_partner_profile(db_path, profile, now=NOW)
    await persist_candidate(db_path, _candidate(), profile, now=NOW)
    revised = PartnerAdvisoryProfile(version=2, instruments=("SENSEX",), holding_period="INTRADAY_TO_3_SESSIONS")
    await save_partner_profile(db_path, revised, now=NOW + timedelta(minutes=1))
    cards = await load_advisory_cards(db_path)
    assert cards["cards"][0]["status"] == "SUPERSEDED_PROFILE"
    with pytest.raises(ValueError, match="increase monotonically"):
        await save_partner_profile(db_path, revised, now=NOW + timedelta(minutes=2))


@pytest.mark.asyncio
async def test_one_profile_cannot_supersede_another_profiles_cards(db_path):
    first = PartnerAdvisoryProfile(profile_id="desk-a", version=1, holding_period="INTRADAY_TO_3_SESSIONS")
    second = PartnerAdvisoryProfile(profile_id="desk-b", version=5, holding_period="INTRADAY_TO_3_SESSIONS")
    await save_partner_profile(db_path, first, now=NOW)
    card = await persist_candidate(db_path, _candidate(), first, now=NOW)
    await save_partner_profile(db_path, second, now=NOW + timedelta(seconds=1))
    cards = await load_advisory_cards(db_path)
    assert next(item for item in cards["cards"] if item["advisory_id"] == card["advisory_id"])["status"] == "VALIDATED_SHADOW"


def test_research_evidence_is_not_delivery_eligible_by_default(db_path):
    candidate = _candidate()
    assert candidate.evidence == StrategyEvidence.RESEARCH_ONLY
