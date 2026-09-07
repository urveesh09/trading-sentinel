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
    select_preferred_market_candidates,
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
        (atm, opt.value): _quote(long, 100.0, 102.0),
        (outer, opt.value): _quote(short, 49.0, 51.0),
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
    profile = PartnerAdvisoryProfile(version=1)
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
async def test_profile_revision_supersedes_old_market_card(db_path):
    profile = PartnerAdvisoryProfile(version=1)
    await save_partner_profile(db_path, profile, now=NOW)
    await persist_candidate(db_path, _candidate(), profile, now=NOW)
    revised = PartnerAdvisoryProfile(version=2, instruments=("SENSEX",))
    await save_partner_profile(db_path, revised, now=NOW + timedelta(minutes=1))
    cards = await load_advisory_cards(db_path)
    assert cards["cards"][0]["status"] == "SUPERSEDED_PROFILE"
    with pytest.raises(ValueError, match="increase monotonically"):
        await save_partner_profile(db_path, revised, now=NOW + timedelta(minutes=2))


def test_research_evidence_is_not_delivery_eligible_by_default(db_path):
    candidate = _candidate()
    assert candidate.evidence == StrategyEvidence.RESEARCH_ONLY
