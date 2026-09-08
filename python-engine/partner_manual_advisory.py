"""Scoped, non-executing advisory cards for the NIFTY 50/SENSEX partner.

This module deliberately sits between read-only market scanning and the
hardened delivery ledger.  It has no broker-order import and no dependency on
Sentinel cash, paper fills or partner holdings for a ``MARKET_SETUP``.  A
personalised hedge is a different scope and is rejected here unless a caller
supplies separately reconciled exposure.

The first release is intentionally small: same-index, same-expiry directional
debit spreads.  Every leg comes from the current exchange-specific instrument
book and the conservative executable side of a single quote batch.  The
module produces persisted preview/shadow cards; delivery stays separately
gated by the existing delivery lifecycle.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Iterable, Optional

import aiosqlite
import pytz

from config import settings
from fno_chain import ChainSnapshot
from fno_costs import calc_fno_costs
from fno_defined_risk import Structure, build_debit_spread, structure_round_trip_cost
from fno_instruments import FnoInstruments
from fno_models import ContractQuote, FnoDirection, OptionType
from fno_underlyings import SPECS

IST = pytz.timezone("Asia/Kolkata")
INTRADAY_HORIZON = "INTRADAY"
INTRADAY_POLICY_VERSION = "partner-manual-intraday-v1"


class AdvisoryScope(str, Enum):
    MARKET_SETUP = "MARKET_SETUP"
    CONDITIONAL_PROTECTION = "CONDITIONAL_PROTECTION"
    PERSONALISED_HEDGE = "PERSONALISED_HEDGE"


class StrategyEvidence(str, Enum):
    UNVALIDATED = "UNVALIDATED"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    QUALIFIED_FOR_ADVISORY = "QUALIFIED_FOR_ADVISORY"
    SUSPENDED = "SUSPENDED"


class ManualDecision(str, Enum):
    NOT_REPORTED = "NOT_REPORTED"
    TAKEN = "TAKEN"
    SKIPPED = "SKIPPED"
    CLOSED = "CLOSED"


# This release intentionally excludes BANKNIFTY, stock derivatives and any
# cross-index construction.  The exchange is part of the identity, not a
# cosmetic display label.
INDEX_EXCHANGES = {"NIFTY": "NSE", "SENSEX": "BSE"}
INDEX_SEGMENTS = {"NIFTY": "NFO", "SENSEX": "BFO"}


@dataclass(frozen=True)
class PartnerAdvisoryProfile:
    profile_id: str = "default"
    version: int = 1
    enabled_scopes: tuple[str, ...] = (AdvisoryScope.MARKET_SETUP.value,)
    instruments: tuple[str, ...] = ("NIFTY", "SENSEX")
    holding_period: Optional[str] = None
    timezone: str = "Asia/Kolkata"
    delivery_start_minute: int = 9 * 60 + 20
    delivery_end_minute: int = 15 * 60 + 15
    permitted_structures: tuple[str, ...] = ("DIRECTIONAL_DEBIT_SPREAD",)
    preference: str = "ACTIONABLE"
    capital_limit_rs: Optional[float] = None
    risk_limit_rs: Optional[float] = None
    confirmed_holdings_revision: Optional[int] = None
    # Conditional protection is allowed only when the operator explicitly
    # supplies an assumption.  These fields are never inferred from Sentinel
    # cash, partner positions, or a delivery recipient.
    conditional_exposure_assumption: Optional[str] = None
    conditional_coverage_units: Optional[int] = None

    def permits(self, scope: AdvisoryScope, underlying: str) -> bool:
        return scope.value in self.enabled_scopes and underlying.upper() in self.instruments


@dataclass(frozen=True)
class AdvisoryLeg:
    side: str
    tradingsymbol: str
    instrument_token: int
    expiry: str
    strike: float
    option_type: str
    ratio: int
    lot_size: int
    tick_size: float
    bid: float
    ask: float
    bid_quantity: int
    ask_quantity: int
    oi: int
    volume: int
    quote_time: Optional[str]


@dataclass(frozen=True)
class AdvisoryCandidate:
    scope: AdvisoryScope
    underlying: str
    exchange: str
    segment: str
    structure_kind: str
    direction: Optional[str]
    generated_at: datetime
    quote_time: datetime
    valid_until: datetime
    policy_version: str
    evidence: StrategyEvidence
    thesis_id: str
    legs: tuple[AdvisoryLeg, ...]
    net_debit_rs: Optional[float]
    net_credit_rs: Optional[float]
    estimated_round_trip_cost_rs: Optional[float]
    max_loss_rs: Optional[float]
    max_profit_rs: Optional[float]
    breakevens: tuple[float, ...] = ()
    why_now: tuple[str, ...] = ()
    uncertainty: str = ""
    exposure_assumption: Optional[str] = None
    coverage_units: Optional[int] = None
    invalidation: str = ""
    management: str = ""
    trigger_level: Optional[float] = None
    invalidation_level: Optional[float] = None
    target_level: Optional[float] = None
    holding_horizon: Optional[str] = None
    session_date: Optional[str] = None
    signal_at: Optional[datetime] = None
    entry_deadline: Optional[datetime] = None
    management_deadline: Optional[datetime] = None
    quote_observed_at: Optional[datetime] = None
    quote_received_at: Optional[datetime] = None
    quote_valid_until: Optional[datetime] = None


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reasons: tuple[str, ...]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS partner_advisory_profiles (
  profile_id TEXT PRIMARY KEY,
  version INTEGER NOT NULL,
  payload TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS partner_advisory_ideas (
  advisory_id TEXT PRIMARY KEY,
  economic_version TEXT NOT NULL,
  scope TEXT NOT NULL,
  underlying TEXT NOT NULL,
  exchange TEXT NOT NULL,
  status TEXT NOT NULL,
  evidence TEXT NOT NULL,
  profile_id TEXT NOT NULL,
  profile_version INTEGER NOT NULL,
  quote_time TEXT NOT NULL,
  valid_until TEXT NOT NULL,
  rendered_card TEXT NOT NULL,
  payload TEXT NOT NULL,
  supersedes_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS partner_advisory_ideas_current_idx
  ON partner_advisory_ideas(underlying, scope, status, valid_until);
CREATE TABLE IF NOT EXISTS partner_advisory_feedback (
  advisory_id TEXT NOT NULL,
  decision TEXT NOT NULL,
  reported_at TEXT NOT NULL,
  note TEXT,
  PRIMARY KEY(advisory_id, decision, reported_at)
);
CREATE TABLE IF NOT EXISTS partner_advisory_strategy_qualifications (
  underlying TEXT NOT NULL,
  structure_kind TEXT NOT NULL,
  horizon TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  dataset_ref TEXT NOT NULL,
  reviewed_at TEXT NOT NULL,
  status TEXT NOT NULL,
  PRIMARY KEY(underlying, structure_kind, horizon, policy_version)
);
CREATE TABLE IF NOT EXISTS partner_advisory_updates (
  update_id TEXT PRIMARY KEY,
  advisory_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  observed_underlying REAL NOT NULL,
  rendered_update TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(advisory_id, event_type)
);
"""


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("advisory timestamps must be timezone-aware")
    return value.astimezone(IST).isoformat()


def _profile_payload(profile: PartnerAdvisoryProfile) -> str:
    return json.dumps(asdict(profile), sort_keys=True, separators=(",", ":"))


def _candidate_payload(candidate: AdvisoryCandidate) -> dict:
    data = asdict(candidate)
    data["scope"] = candidate.scope.value
    data["evidence"] = candidate.evidence.value
    data["generated_at"] = _iso(candidate.generated_at)
    data["quote_time"] = _iso(candidate.quote_time)
    data["valid_until"] = _iso(candidate.valid_until)
    for key in ("signal_at", "entry_deadline", "management_deadline", "quote_observed_at", "quote_received_at", "quote_valid_until"):
        if data[key] is not None:
            data[key] = _iso(data[key])
    return data


def intraday_deadlines(now: datetime) -> tuple[datetime, datetime, datetime]:
    """Return dated IST entry, exit-reminder and management deadlines."""
    if now.tzinfo is None:
        raise ValueError("intraday clock must be timezone-aware")
    local = now.astimezone(IST)
    def at(minute: int) -> datetime:
        return local.replace(hour=minute // 60, minute=minute % 60, second=0, microsecond=0)
    return (at(settings.PARTNER_MANUAL_ADVISORY_ENTRY_END_MINUTE),
            at(settings.PARTNER_MANUAL_ADVISORY_EXIT_REMINDER_MINUTE),
            at(settings.PARTNER_MANUAL_ADVISORY_MANAGEMENT_END_MINUTE))


def _finite_positive(value: object) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value)) and float(value) > 0


def _vertical_oracle(candidate: AdvisoryCandidate) -> tuple[Optional[dict], tuple[str, ...]]:
    """Independent two-leg expiry oracle; never trusts displayed payoff fields."""
    if candidate.scope != AdvisoryScope.MARKET_SETUP or candidate.structure_kind != "DIRECTIONAL_DEBIT_SPREAD":
        return None, ()
    if len(candidate.legs) != 2:
        return None, ("vertical_requires_exactly_two_legs",)
    buy = next((leg for leg in candidate.legs if leg.side == "BUY"), None)
    sell = next((leg for leg in candidate.legs if leg.side == "SELL"), None)
    if buy is None or sell is None or buy is sell:
        return None, ("vertical_requires_buy_sell_pair",)
    if buy.ratio != sell.ratio or buy.ratio <= 0 or int(buy.ratio) != buy.ratio:
        return None, ("vertical_ratio_invalid",)
    if buy.option_type != sell.option_type or buy.option_type not in {"CE", "PE"}:
        return None, ("vertical_option_type_invalid",)
    if buy.expiry != sell.expiry or buy.lot_size != sell.lot_size or buy.lot_size <= 0:
        return None, ("vertical_contract_mismatch",)
    if candidate.direction == FnoDirection.LONG.value:
        ordered = buy.option_type == "CE" and buy.strike < sell.strike
    elif candidate.direction == FnoDirection.SHORT.value:
        ordered = buy.option_type == "PE" and buy.strike > sell.strike
    else:
        ordered = False
    if not ordered:
        return None, ("vertical_strike_order_invalid",)
    if not all(_finite_positive(value) for value in (buy.ask, sell.bid, buy.strike, sell.strike)):
        return None, ("vertical_nonfinite_economics",)
    quantity = buy.lot_size * buy.ratio
    debit = (buy.ask - sell.bid) * quantity
    width = abs(sell.strike - buy.strike) * quantity
    max_profit = width - debit
    max_loss = debit
    if debit <= 0 or debit >= width or max_profit <= 0:
        return None, ("vertical_nonpositive_expiry_reward",)
    return {"debit": debit, "width": width, "max_profit": max_profit, "max_loss": max_loss}, ()


def validate_profile(profile: PartnerAdvisoryProfile, candidate: AdvisoryCandidate, now: datetime) -> tuple[str, ...]:
    reasons: list[str] = []
    if profile.timezone != "Asia/Kolkata":
        reasons.append("unsupported_profile_timezone")
    if profile.holding_period != INTRADAY_HORIZON:
        reasons.append("profile_horizon_not_intraday")
    if candidate.holding_horizon != INTRADAY_HORIZON or profile.holding_period != candidate.holding_horizon:
        reasons.append("profile_horizon_mismatch")
    if candidate.structure_kind not in profile.permitted_structures:
        reasons.append("profile_structure_not_permitted")
    minute = now.astimezone(IST).hour * 60 + now.astimezone(IST).minute
    if not (profile.delivery_start_minute <= minute <= profile.delivery_end_minute):
        reasons.append("profile_delivery_window_closed")
    cost = candidate.estimated_round_trip_cost_rs
    all_in_risk = ((candidate.max_loss_rs or 0.0) + cost) if isinstance(cost, (int, float)) and math.isfinite(float(cost)) else math.inf
    all_in_entry = ((candidate.net_debit_rs or 0.0) + cost) if isinstance(cost, (int, float)) and math.isfinite(float(cost)) else math.inf
    if profile.risk_limit_rs is not None and (candidate.max_loss_rs is None or all_in_risk > profile.risk_limit_rs):
        reasons.append("profile_risk_limit_exceeded")
    if profile.capital_limit_rs is not None and (candidate.net_debit_rs is None or all_in_entry > profile.capital_limit_rs):
        reasons.append("profile_capital_limit_exceeded")
    return tuple(reasons)


async def init_partner_advisory_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.executescript(_SCHEMA)
        columns = {row[1] for row in await (await db.execute("PRAGMA table_info(partner_advisory_ideas)")).fetchall()}
        if "profile_id" not in columns:
            # Backward-compatible migration.  Historical rows predate
            # multiple profiles and are conservatively attributed to default;
            # they cannot authorize another profile's delivery.
            await db.execute("ALTER TABLE partner_advisory_ideas ADD COLUMN profile_id TEXT NOT NULL DEFAULT 'default'")
        await db.commit()


async def save_partner_profile(
    db_path: str, profile: PartnerAdvisoryProfile, *, now: Optional[datetime] = None,
) -> PartnerAdvisoryProfile:
    """Save a versioned profile and retire affected unexpired ideas.

    A profile update cannot make an old card newly permissible.  Retiring it
    forces any later delivery path to validate/render a fresh economic version.
    """
    if not profile.profile_id.strip():
        raise ValueError("profile_id is required")
    if not set(profile.instruments).issubset(INDEX_EXCHANGES):
        raise ValueError("only NIFTY and SENSEX are supported in this release")
    if not set(profile.enabled_scopes).issubset({item.value for item in AdvisoryScope}):
        raise ValueError("unknown advisory scope")
    if profile.capital_limit_rs is not None and profile.capital_limit_rs <= 0:
        raise ValueError("capital_limit_rs must be positive when supplied")
    if profile.risk_limit_rs is not None and profile.risk_limit_rs <= 0:
        raise ValueError("risk_limit_rs must be positive when supplied")
    if profile.delivery_start_minute > profile.delivery_end_minute:
        raise ValueError("delivery window start must not follow its end")
    if profile.holding_period not in {None, INTRADAY_HORIZON}:
        raise ValueError("only INTRADAY holding_period is supported")
    if (profile.conditional_exposure_assumption is None) != (profile.conditional_coverage_units is None):
        raise ValueError("conditional protection requires both exposure assumption and coverage units")
    if profile.conditional_coverage_units is not None and profile.conditional_coverage_units <= 0:
        raise ValueError("conditional_coverage_units must be positive")
    stamp = _iso(now or datetime.now(IST))
    await init_partner_advisory_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("BEGIN IMMEDIATE")
        existing = await (await db.execute(
            "SELECT version FROM partner_advisory_profiles WHERE profile_id=?", (profile.profile_id,)
        )).fetchone()
        if existing is not None and profile.version <= int(existing[0]):
            await db.rollback()
            raise ValueError("profile version must increase monotonically")
        await db.execute(
            "INSERT INTO partner_advisory_profiles(profile_id,version,payload,updated_at) "
            "VALUES(?,?,?,?) ON CONFLICT(profile_id) DO UPDATE SET "
            "version=excluded.version,payload=excluded.payload,updated_at=excluded.updated_at",
            (profile.profile_id, profile.version, _profile_payload(profile), stamp),
        )
        await db.execute(
            "UPDATE partner_advisory_ideas SET status='SUPERSEDED_PROFILE', updated_at=? "
            "WHERE status IN ('VALIDATED_SHADOW','QUEUED') AND profile_id=? AND profile_version < ?",
            (stamp, profile.profile_id, profile.version),
        )
        await db.commit()
    return profile


async def load_partner_profile(
    db_path: str, profile_id: str = "default",
) -> PartnerAdvisoryProfile:
    await init_partner_advisory_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        row = await (await db.execute(
            "SELECT payload FROM partner_advisory_profiles WHERE profile_id=?", (profile_id,)
        )).fetchone()
    if row is None:
        return PartnerAdvisoryProfile(profile_id=profile_id)
    raw = json.loads(row[0])
    raw["enabled_scopes"] = tuple(raw.get("enabled_scopes", ()))
    raw["instruments"] = tuple(raw.get("instruments", ()))
    raw["permitted_structures"] = tuple(raw.get("permitted_structures", ()))
    return PartnerAdvisoryProfile(**raw)


async def record_strategy_qualification(
    db_path: str, *, underlying: str, structure_kind: str, horizon: str,
    policy_version: str, dataset_ref: str, reviewed_at: datetime,
    status: StrategyEvidence = StrategyEvidence.QUALIFIED_FOR_ADVISORY,
) -> None:
    """Persist a reviewable qualification; a config flag cannot manufacture it."""
    if reviewed_at.tzinfo is None:
        raise ValueError("qualification reviewed_at must be timezone-aware")
    if underlying not in INDEX_EXCHANGES or not dataset_ref.strip() or horizon != INTRADAY_HORIZON:
        raise ValueError("qualification requires supported underlying, INTRADAY horizon and dataset_ref")
    if policy_version != INTRADAY_POLICY_VERSION:
        raise ValueError("qualification policy_version is not the current intraday policy")
    if reviewed_at.astimezone(IST) > datetime.now(IST) + timedelta(minutes=5):
        raise ValueError("qualification reviewed_at cannot be in the future")
    if status not in {StrategyEvidence.QUALIFIED_FOR_ADVISORY, StrategyEvidence.SUSPENDED}:
        raise ValueError("qualification status must be QUALIFIED_FOR_ADVISORY or SUSPENDED")
    await init_partner_advisory_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO partner_advisory_strategy_qualifications "
            "(underlying,structure_kind,horizon,policy_version,dataset_ref,reviewed_at,status) VALUES(?,?,?,?,?,?,?)",
            (underlying, structure_kind, horizon, policy_version, dataset_ref, _iso(reviewed_at), status.value),
        )
        await db.commit()


async def is_strategy_qualified(db_path: str, candidate: AdvisoryCandidate) -> bool:
    """Return whether an independently recorded review permits this setup.

    Evidence carried by a just-built candidate is deliberately not an input to
    this lookup.  The scanner starts every idea as research-only and upgrades
    it only after this persisted registry answers yes; otherwise a caller
    could self-assert qualification by choosing an enum value.
    """
    if not candidate.holding_horizon:
        return False
    await init_partner_advisory_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        row = await (await db.execute(
            "SELECT status FROM partner_advisory_strategy_qualifications WHERE underlying=? AND structure_kind=? "
            "AND horizon=? AND policy_version=?",
            (candidate.underlying, candidate.structure_kind, candidate.holding_horizon, candidate.policy_version),
        )).fetchone()
    return bool(row and row[0] == StrategyEvidence.QUALIFIED_FOR_ADVISORY.value)


def _quote_time(quote: ContractQuote, snapshot: ChainSnapshot) -> Optional[str]:
    return _iso(quote.last_trade_time) if quote.last_trade_time else _iso(snapshot.taken_at)


def _leg(side: str, quote: ContractQuote, snapshot: ChainSnapshot) -> AdvisoryLeg:
    contract = quote.contract
    return AdvisoryLeg(
        side=side, tradingsymbol=contract.tradingsymbol, instrument_token=contract.token,
        expiry=contract.expiry.isoformat(), strike=contract.strike,
        option_type=contract.instrument_type, ratio=1, lot_size=contract.lot_size,
        tick_size=contract.tick_size, bid=quote.bid, ask=quote.ask,
        bid_quantity=quote.bid_quantity, ask_quantity=quote.ask_quantity,
        oi=quote.oi, volume=quote.volume, quote_time=_quote_time(quote, snapshot),
    )


def resolve_advisory_expiry(book: FnoInstruments, today) -> Optional[object]:
    """Select the nearest strictly future listed expiry for this index.

    Same-day products have a separately unqualified policy, so an expiry-day
    scan rolls to the next contract instead of silently abandoning the index.
    """
    return next((expiry for expiry in book.option_expiries if expiry > today), None)


def build_directional_debit_spread(
    snapshot: ChainSnapshot, book: FnoInstruments, direction: FnoDirection,
    now: datetime, *, evidence: StrategyEvidence = StrategyEvidence.RESEARCH_ONLY,
    width_steps: int = 1, quote_ttl_seconds: int = 30,
    policy_version: str = INTRADAY_POLICY_VERSION, thesis_id: Optional[str] = None,
    trigger_level: Optional[float] = None, invalidation_level: Optional[float] = None,
    target_level: Optional[float] = None, holding_horizon: str = INTRADAY_HORIZON,
) -> Optional[AdvisoryCandidate]:
    """Build one conservative, same-index/same-expiry vertical, or ``None``.

    Long legs use ask and short legs use bid.  This prevents the common
    midpoint-only card from claiming a debit that cannot be executed.
    """
    if holding_horizon != INTRADAY_HORIZON or policy_version != INTRADAY_POLICY_VERSION:
        return None
    entry_deadline, _exit_reminder, management_deadline = intraday_deadlines(now)
    if now.astimezone(IST) > entry_deadline:
        return None
    if not all(_finite_positive(value) for value in (trigger_level, invalidation_level, target_level)):
        return None
    underlying = book.underlying.upper()
    if underlying not in INDEX_EXCHANGES or book.segment != INDEX_SEGMENTS[underlying]:
        return None
    # Same-day expiry has materially different liquidity/settlement dynamics
    # and is deliberately outside this initial profile.  Expiry dates come
    # from the current book; no weekday or holiday assumption is encoded.
    if snapshot.expiry <= now.date() or snapshot.expiry not in book.option_expiries or snapshot.lot_size <= 0:
        return None
    atm = book.atm_strike(snapshot.forward)
    if atm <= 0 or book.strike_step <= 0:
        return None
    opt = OptionType.CE if direction == FnoDirection.LONG else OptionType.PE
    long_strike = atm
    short_strike = atm + width_steps * book.strike_step if opt == OptionType.CE else atm - width_steps * book.strike_step
    long_contract = book.option(snapshot.expiry, long_strike, opt)
    short_contract = book.option(snapshot.expiry, short_strike, opt)
    long_quote = snapshot.quote(long_strike, opt)
    short_quote = snapshot.quote(short_strike, opt)
    if not all((long_contract, short_contract, long_quote, short_quote)):
        return None
    if long_contract != long_quote.contract or short_contract != short_quote.contract:
        return None
    if long_contract.expiry != short_contract.expiry or long_contract.lot_size != short_contract.lot_size:
        return None
    # Builder uses conservative sides.  Its structural payoff is then an
    # independent oracle for the displayed bounds.
    prices = {(opt, long_strike): long_quote.ask, (opt, short_strike): short_quote.bid}
    structure = build_debit_spread(
        direction, atm, book.strike_step, width_steps,
        lambda option_type, strike: prices.get((option_type, strike)), long_contract.lot_size,
    )
    if structure is None or not structure.is_defined_risk:
        return None
    net_debit = -structure.net_premium * structure.lot_size
    if net_debit <= 0:
        return None
    return AdvisoryCandidate(
        scope=AdvisoryScope.MARKET_SETUP, underlying=underlying,
        exchange=INDEX_EXCHANGES[underlying], segment=book.segment,
        structure_kind="DIRECTIONAL_DEBIT_SPREAD", direction=direction.value,
        generated_at=now, quote_time=snapshot.taken_at,
        valid_until=snapshot.taken_at + timedelta(seconds=quote_ttl_seconds),
        policy_version=policy_version, evidence=evidence,
        thesis_id=thesis_id or f"{underlying}:{direction.value}:{snapshot.expiry.isoformat()}",
        legs=(_leg("BUY", long_quote, snapshot), _leg("SELL", short_quote, snapshot)),
        net_debit_rs=round(net_debit, 2), net_credit_rs=None,
        estimated_round_trip_cost_rs=structure_round_trip_cost(structure),
        max_loss_rs=structure.max_loss_rs, max_profit_rs=structure.max_profit_rs,
        breakevens=tuple(structure.breakevens),
        why_now=(f"{direction.value} completed-bar confirmation at {trigger_level:,.2f}" if _finite_positive(trigger_level) else f"{direction.value} completed-bar confirmation", "same-expiry capped-risk vertical"),
        uncertainty="Research qualification is separate from any profitability claim.",
        invalidation=(f"Underlying invalidation: {invalidation_level:,.2f}. " if _finite_positive(invalidation_level) else "") + "Skip if combined executable debit exceeds the stated limit or a leg becomes stale/one-sided.",
        management=(f"Consider target zone {target_level:,.2f}; " if _finite_positive(target_level) else "") + "recheck both legs together before entry; take no new entry after the stated horizon or expiry cutoff.",
        trigger_level=trigger_level, invalidation_level=invalidation_level,
        target_level=target_level, holding_horizon=holding_horizon,
        session_date=now.astimezone(IST).date().isoformat(), signal_at=now,
        entry_deadline=entry_deadline, management_deadline=management_deadline,
        quote_observed_at=snapshot.taken_at, quote_received_at=now,
        quote_valid_until=snapshot.taken_at + timedelta(seconds=quote_ttl_seconds),
    )


def build_conditional_index_protective_put(
    snapshot: ChainSnapshot, book: FnoInstruments, now: datetime, *,
    exposure_assumption: str, coverage_units: int,
    evidence: StrategyEvidence = StrategyEvidence.RESEARCH_ONLY,
    quote_ttl_seconds: int = 30, policy_version: str = INTRADAY_POLICY_VERSION,
    thesis_id: Optional[str] = None,
) -> Optional[AdvisoryCandidate]:
    """Build a conditional protective-put *idea*, never a personal hedge.

    Index protection is only meaningful relative to the stated long exposure.
    Therefore the caller must name the assumed exposure and its coverage in
    units; the function refuses a vague "portfolio hedge" label and never
    derives a quantity from capital or an unconfirmed holding.
    """
    entry_deadline, _exit_reminder, management_deadline = intraday_deadlines(now)
    if policy_version != INTRADAY_POLICY_VERSION or now.astimezone(IST) > entry_deadline:
        return None
    underlying = book.underlying.upper()
    if (
        underlying not in INDEX_EXCHANGES or book.segment != INDEX_SEGMENTS[underlying]
        or snapshot.expiry <= now.date() or not exposure_assumption.strip() or coverage_units <= 0
    ):
        return None
    strike = book.atm_strike(snapshot.forward) - book.strike_step
    contract = book.option(snapshot.expiry, strike, OptionType.PE)
    quote = snapshot.quote(strike, OptionType.PE)
    if contract is None or quote is None or contract != quote.contract or contract.lot_size <= 0:
        return None
    premium_risk = quote.ask * contract.lot_size
    if premium_risk <= 0:
        return None
    return AdvisoryCandidate(
        scope=AdvisoryScope.CONDITIONAL_PROTECTION, underlying=underlying,
        exchange=INDEX_EXCHANGES[underlying], segment=book.segment,
        structure_kind="CONDITIONAL_PROTECTIVE_PUT", direction="DOWN",
        generated_at=now, quote_time=snapshot.taken_at,
        valid_until=snapshot.taken_at + timedelta(seconds=quote_ttl_seconds),
        policy_version=policy_version, evidence=evidence, legs=(_leg("BUY", quote, snapshot),),
        thesis_id=thesis_id or f"{underlying}:PROTECTION:{snapshot.expiry.isoformat()}",
        net_debit_rs=round(premium_risk, 2), net_credit_rs=None,
        estimated_round_trip_cost_rs=round(calc_fno_costs(quote.ask, quote.ask, contract.lot_size), 2),
        # This bound is the option premium only, not the loss of the unknown
        # protected position.  The renderer says this explicitly.
        max_loss_rs=round(premium_risk, 2), max_profit_rs=None,
        why_now=("conditional downside protection", "exchange-specific index put"),
        uncertainty="This is not personalised sizing and does not establish your current exposure.",
        exposure_assumption=exposure_assumption, coverage_units=coverage_units,
        invalidation="Skip if coverage, expiry, executable quote or broker margin differs from the stated assumption.",
        management="Confirm the protected exposure and recheck the option quote before acting.",
        holding_horizon=INTRADAY_HORIZON, session_date=now.astimezone(IST).date().isoformat(),
        signal_at=now, entry_deadline=entry_deadline, management_deadline=management_deadline,
        quote_observed_at=snapshot.taken_at, quote_received_at=now,
        quote_valid_until=snapshot.taken_at + timedelta(seconds=quote_ttl_seconds),
    )


def select_preferred_market_candidates(
    candidates: Iterable[AdvisoryCandidate],
) -> tuple[list[AdvisoryCandidate], list[AdvisoryCandidate]]:
    """Choose one best expression per same-direction index thesis.

    NIFTY and SENSEX are not diversification simply because their labels
    differ.  Ranking uses bounded payoff adjusted for estimated costs, then
    all-leg executable spread, never premium points alone.  The returned
    alternatives are intentionally not dispatch candidates; callers can keep
    them as operator evidence.
    """
    grouped: dict[str, list[AdvisoryCandidate]] = {}
    for candidate in candidates:
        if candidate.scope == AdvisoryScope.MARKET_SETUP and candidate.direction:
            grouped.setdefault(candidate.direction, []).append(candidate)
    selected: list[AdvisoryCandidate] = []
    suppressed: list[AdvisoryCandidate] = []

    def quality(item: AdvisoryCandidate) -> tuple[float, float, str]:
        reward = item.max_profit_rs or 0.0
        risk = (item.max_loss_rs or math.inf) + (item.estimated_round_trip_cost_rs or math.inf)
        payoff_quality = reward / risk if risk > 0 and math.isfinite(risk) else -math.inf
        spreads = [((leg.ask - leg.bid) / ((leg.ask + leg.bid) / 2.0)) for leg in item.legs if leg.bid > 0 and leg.ask > 0]
        execution_quality = -max(spreads) if spreads else -math.inf
        return (-payoff_quality, -execution_quality, item.underlying)

    for group in grouped.values():
        ranked = sorted(group, key=quality)
        selected.append(ranked[0])
        suppressed.extend(ranked[1:])
    return selected, suppressed


def validate_candidate(
    candidate: AdvisoryCandidate, now: datetime, *, max_quote_age_seconds: int = 30,
    max_spread_pct: float = 0.15, min_oi: int = 1, min_volume: int = 1,
    min_depth_units: int = 1,
) -> ValidationResult:
    """Strictly validate structural, quote and scope facts before any render.

    It is intentionally reusable at preview and immediately before dispatch.
    A caller that cannot provide bid/ask sizes gets a rejection rather than a
    card that pretends a displayed price is executable.
    """
    reasons: list[str] = []
    if candidate.holding_horizon != INTRADAY_HORIZON or candidate.policy_version != INTRADAY_POLICY_VERSION:
        reasons.append("non_intraday_policy")
    local_now = now.astimezone(IST)
    if candidate.session_date != local_now.date().isoformat():
        reasons.append("wrong_or_stale_session_date")
    for field_name in ("signal_at", "entry_deadline", "management_deadline", "quote_observed_at", "quote_received_at", "quote_valid_until"):
        value = getattr(candidate, field_name)
        if value is None or value.tzinfo is None:
            reasons.append(f"{field_name}_missing")
    if candidate.entry_deadline is not None and local_now > candidate.entry_deadline.astimezone(IST):
        reasons.append("entry_deadline_elapsed")
    if candidate.management_deadline is not None and candidate.entry_deadline is not None and candidate.management_deadline <= candidate.entry_deadline:
        reasons.append("management_deadline_invalid")
    if candidate.quote_valid_until is not None and candidate.quote_valid_until != candidate.valid_until:
        reasons.append("quote_validity_mismatch")
    if candidate.underlying not in INDEX_EXCHANGES:
        reasons.append("unsupported_underlying")
    if candidate.exchange != INDEX_EXCHANGES.get(candidate.underlying):
        reasons.append("wrong_exchange_for_underlying")
    if candidate.segment != INDEX_SEGMENTS.get(candidate.underlying):
        reasons.append("wrong_segment_for_underlying")
    if candidate.quote_time.tzinfo is None or candidate.valid_until.tzinfo is None:
        reasons.append("timezone_missing")
    else:
        age = (now - candidate.quote_time).total_seconds()
        if age < -5 or age > max_quote_age_seconds:
            reasons.append("stale_or_future_quote")
        if now > candidate.valid_until:
            reasons.append("candidate_expired")
    if not candidate.legs:
        reasons.append("no_legs")
    expiries = {leg.expiry for leg in candidate.legs}
    lots = {leg.lot_size for leg in candidate.legs}
    if len(expiries) != 1:
        reasons.append("mixed_expiry")
    if len(lots) != 1 or 0 in lots:
        reasons.append("inconsistent_lot_size")
    for leg in candidate.legs:
        if leg.option_type not in {"CE", "PE"} or leg.side not in {"BUY", "SELL"}:
            reasons.append("invalid_leg")
            continue
        if not leg.tradingsymbol or leg.instrument_token <= 0 or leg.strike <= 0 or leg.tick_size <= 0:
            reasons.append("incomplete_contract_metadata")
        if leg.bid <= 0 or leg.ask <= 0 or leg.bid > leg.ask:
            reasons.append("non_executable_or_crossed_quote")
        else:
            midpoint = (leg.bid + leg.ask) / 2.0
            if (leg.ask - leg.bid) / midpoint > max_spread_pct:
                reasons.append("spread_too_wide")
        # A card represents one structure, not one displayed unit.  Depth
        # must cover its full lot-adjusted leg ratio on the executable side.
        required_depth = max(min_depth_units, leg.lot_size * leg.ratio)
        needed = leg.ask_quantity if leg.side == "BUY" else leg.bid_quantity
        if needed < required_depth:
            reasons.append("insufficient_displayed_depth")
        if leg.oi < min_oi:
            reasons.append("insufficient_oi")
        if leg.volume < min_volume:
            reasons.append("insufficient_volume")
    leg_times = []
    for leg in candidate.legs:
        if not leg.quote_time:
            reasons.append("leg_quote_time_missing")
            continue
        try:
            leg_time = datetime.fromisoformat(leg.quote_time)
        except ValueError:
            reasons.append("leg_quote_time_invalid")
            continue
        if leg_time.tzinfo is None:
            reasons.append("leg_quote_time_timezone_missing")
            continue
        if (now - leg_time).total_seconds() > max_quote_age_seconds or (leg_time - now).total_seconds() > 5:
            reasons.append("stale_or_future_leg_quote")
        leg_times.append(leg_time)
    if len(leg_times) == len(candidate.legs) and leg_times:
        if (max(leg_times) - min(leg_times)).total_seconds() > 5:
            reasons.append("out_of_sync_leg_quotes")
    if candidate.scope == AdvisoryScope.MARKET_SETUP:
        if candidate.structure_kind != "DIRECTIONAL_DEBIT_SPREAD":
            reasons.append("market_structure_not_permitted")
        if candidate.max_loss_rs is None or not math.isfinite(candidate.max_loss_rs) or candidate.max_loss_rs <= 0:
            reasons.append("defined_risk_bound_missing")
        if candidate.net_debit_rs is None or candidate.net_debit_rs <= 0:
            reasons.append("debit_missing")
        if not all(_finite_positive(value) for value in (candidate.trigger_level, candidate.invalidation_level, candidate.target_level)):
            reasons.append("intraday_levels_missing")
        oracle, oracle_reasons = _vertical_oracle(candidate)
        reasons.extend(oracle_reasons)
        if oracle is not None:
            cost = candidate.estimated_round_trip_cost_rs
            if not isinstance(cost, (int, float)) or not math.isfinite(float(cost)) or cost < 0:
                reasons.append("cost_invalid")
            else:
                if oracle["max_profit"] - float(cost) <= 0:
                    reasons.append("cost_erases_expiry_reward")
            tolerance = 0.02
            for displayed, computed, label in (
                (candidate.net_debit_rs, oracle["debit"], "debit"),
                (candidate.max_loss_rs, oracle["max_loss"], "max_loss"),
                (candidate.max_profit_rs, oracle["max_profit"], "max_profit"),
            ):
                if not isinstance(displayed, (int, float)) or not math.isfinite(float(displayed)) or abs(float(displayed) - computed) > tolerance:
                    reasons.append(f"displayed_{label}_does_not_match_legs")
    elif candidate.scope == AdvisoryScope.CONDITIONAL_PROTECTION:
        if not candidate.exposure_assumption or not candidate.coverage_units:
            reasons.append("protection_coverage_assumption_missing")
    elif candidate.scope == AdvisoryScope.PERSONALISED_HEDGE:
        # No synthetic zero position can pass this.  The portfolio-aware
        # hedge service remains the authority for reconciled exposure.
        reasons.append("personalised_scope_requires_reconciled_portfolio")
    return ValidationResult(not reasons, tuple(sorted(set(reasons))))


def advisory_identity(candidate: AdvisoryCandidate) -> tuple[str, str]:
    payload = _candidate_payload(candidate)
    # Quote receipt timestamps describe evidence freshness, not economic
    # content.  Including them would fabricate a new generation every scan.
    economic_legs = [
        {key: value for key, value in leg.items() if key != "quote_time"}
        for leg in payload["legs"]
    ]
    economic = {
        key: payload[key] for key in (
            "scope", "underlying", "exchange", "segment", "structure_kind", "direction",
            "net_debit_rs", "net_credit_rs", "max_loss_rs", "max_profit_rs", "breakevens",
            "policy_version", "thesis_id", "exposure_assumption", "coverage_units",
        )
    }
    economic["legs"] = economic_legs
    economic_version = hashlib.sha256(json.dumps(economic, sort_keys=True).encode()).hexdigest()[:20]
    # A stored card is an immutable economic generation.  Transport dedup is
    # separately tied to the stable thesis below, so a material quote change
    # can supersede a preview without becoming another partner notification.
    advisory_id = hashlib.sha256(
        f"{payload['scope']}:{payload['underlying']}:{payload['thesis_id']}:{payload['policy_version']}:{economic_version}".encode()
    ).hexdigest()[:24]
    return advisory_id, economic_version


def render_advisory_card(candidate: AdvisoryCandidate, advisory_id: str) -> str:
    """Render a complete bounded card; never transport-truncate an advisory."""
    header = candidate.scope.value.replace("_", " ")
    lines = [
        f"[{header}] • {candidate.underlying} ({candidate.exchange})",
        f"Idea {advisory_id}/{candidate.policy_version} • Data {_iso(candidate.quote_time)} • Valid until {_iso(candidate.valid_until)}",
        f"INTRADAY ONLY — do not carry overnight. Manual action only; the system cannot close any position for you.",
        f"Why now: {'; '.join(candidate.why_now)}",
        "Structure:",
    ]
    for leg in candidate.legs:
        lines.append(
            f"{leg.side} {leg.ratio}× {leg.tradingsymbol} | {leg.expiry} {leg.strike:g}{leg.option_type} "
            f"| lot {leg.lot_size} | bid/ask {leg.bid:g}/{leg.ask:g}"
        )
    if candidate.net_debit_rs is not None:
        lines.append(f"Act only if: combined debit ≤ ₹{candidate.net_debit_rs:,.2f} before fees")
    if candidate.net_credit_rs is not None:
        lines.append(f"Act only if: combined credit ≥ ₹{candidate.net_credit_rs:,.2f} before fees")
    if candidate.estimated_round_trip_cost_rs is not None:
        lines.append(f"Per structure: estimated round-trip costs ₹{candidate.estimated_round_trip_cost_rs:,.2f}")
    if candidate.max_loss_rs is not None:
        risk_label = "Protection premium at risk" if candidate.scope == AdvisoryScope.CONDITIONAL_PROTECTION else "Risk: theoretical maximum loss"
        lines.append(
            f"{risk_label} ₹{candidate.max_loss_rs:,.2f}"
            + ("; this is not the loss bound of an unknown protected position" if candidate.scope == AdvisoryScope.CONDITIONAL_PROTECTION else " if all intended legs fill and remain paired")
        )
    if candidate.max_profit_rs is not None:
        lines.append(f"Theoretical expiry maximum profit: ₹{candidate.max_profit_rs:,.2f}")
    if candidate.breakevens:
        lines.append("Expiry breakeven(s): " + ", ".join(f"{item:,.2f}" for item in candidate.breakevens))
    if candidate.exposure_assumption:
        lines.append(f"Coverage assumption: {candidate.exposure_assumption}")
    if candidate.trigger_level is not None:
        comparator = "above" if candidate.direction == FnoDirection.LONG.value else "below"
        lines.append(f"Entry trigger: underlying confirms {comparator} {candidate.trigger_level:,.2f} on the stated completed-bar signal.")
    if candidate.invalidation_level is not None:
        lines.append(f"Thesis invalidation level: {candidate.invalidation_level:,.2f}.")
    if candidate.target_level is not None:
        lines.append(f"First profit-taking / review level: {candidate.target_level:,.2f}; do not treat it as a guarantee.")
    if candidate.holding_horizon:
        deadline = _iso(candidate.management_deadline) if candidate.management_deadline else "unavailable"
        lines.append(f"Holding horizon: {candidate.holding_horizon}; exit/reassess by {deadline} (IST), not contract expiry.")
    lines.extend([
        f"Invalidation: {candidate.invalidation}",
        f"Management: {candidate.management}",
        f"Uncertainty: {candidate.uncertainty}",
        f"Evidence: {candidate.evidence.value}. Per-structure economics only; no personal quantity is supplied.",
        "Manual decision. Recheck current executable quotes and broker requirements before acting.",
    ])
    text = "\n".join(lines)
    if len(text) > 4096:
        raise ValueError("advisory_card_over_telegram_limit")
    return text


async def persist_candidate(
    db_path: str, candidate: AdvisoryCandidate, profile: PartnerAdvisoryProfile,
    now: Optional[datetime] = None, *, validation_options: Optional[dict] = None,
    queue_for_delivery: bool = False,
) -> dict:
    """Persist a validated shadow card with conservative dedup/version links.

    This does not send, create an order, fabricate a position or grant any
    execution authority.  Research-only evidence is intentionally previewable
    but never delivery-eligible.
    """
    now = now or datetime.now(IST)
    validation = validate_candidate(candidate, now, **(validation_options or {}))
    advisory_id, economic_version = advisory_identity(candidate)
    await init_partner_advisory_db(db_path)
    payload = _candidate_payload(candidate)
    payload["delivery_thesis_id"] = hashlib.sha256(
        f"{candidate.scope.value}:{candidate.underlying}:{candidate.thesis_id}:{candidate.policy_version}".encode()
    ).hexdigest()[:24]
    payload["validation_reasons"] = list(validation.reasons)
    payload["profile_id"] = profile.profile_id
    profile_reasons = validate_profile(profile, candidate, now)
    if not profile.permits(candidate.scope, candidate.underlying):
        profile_reasons += ("profile_scope_not_permitted",)
    if profile_reasons:
        validation = ValidationResult(False, tuple(sorted(set(validation.reasons + profile_reasons))))
        payload["validation_reasons"] = list(validation.reasons)
    registry_qualified = await is_strategy_qualified(db_path, candidate)
    # The registry permits promotion, but a raw research result must still be
    # explicitly promoted by the controlled scanner before it can queue.
    qualified = registry_qualified and candidate.evidence == StrategyEvidence.QUALIFIED_FOR_ADVISORY
    payload["strategy_qualified"] = qualified
    payload["qualification_registry_match"] = registry_qualified
    delivery_reasons = list(validation.reasons)
    if queue_for_delivery and not qualified:
        # A research preview remains a useful, explicitly non-deliverable
        # record.  Qualification is a transport gate, not a claim that its
        # leg arithmetic became invalid.
        delivery_reasons.append("strategy_not_qualified_for_delivery")
    payload["delivery_reasons"] = sorted(set(delivery_reasons))
    card = render_advisory_card(candidate, advisory_id) if validation.valid else ""
    status = "QUEUED" if validation.valid and queue_for_delivery and qualified else (
        "VALIDATED_SHADOW" if validation.valid else "REJECTED"
    )
    stamp = _iso(now)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("BEGIN IMMEDIATE")
        prior = await (await db.execute(
            "SELECT advisory_id,payload FROM partner_advisory_ideas WHERE underlying=? AND scope=? "
            "AND status IN ('VALIDATED_SHADOW','QUEUED') ORDER BY created_at DESC",
            (candidate.underlying, candidate.scope.value),
        )).fetchall()
        prior_id = None
        for old_id, old_payload in prior:
            try:
                if json.loads(old_payload).get("delivery_thesis_id") == payload["delivery_thesis_id"]:
                    prior_id = old_id
                    break
            except (TypeError, json.JSONDecodeError):
                continue
        if prior_id and prior_id != advisory_id:
            await db.execute(
                "UPDATE partner_advisory_ideas SET status='SUPERSEDED_MARKET', updated_at=? WHERE advisory_id=?",
                (stamp, prior_id),
            )
        await db.execute(
            "INSERT INTO partner_advisory_ideas(advisory_id,economic_version,scope,underlying,exchange,status,evidence,profile_id,profile_version,quote_time,valid_until,rendered_card,payload,supersedes_id,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(advisory_id) DO UPDATE SET updated_at=excluded.updated_at",
            (advisory_id, economic_version, candidate.scope.value, candidate.underlying,
             candidate.exchange, status, candidate.evidence.value, profile.profile_id, profile.version,
             _iso(candidate.quote_time), _iso(candidate.valid_until), card,
             json.dumps(payload, sort_keys=True), prior_id, stamp, stamp),
        )
        await db.commit()
    return {
        "advisory_id": advisory_id, "economic_version": economic_version, "status": status,
        "underlying": candidate.underlying, "valid_until": _iso(candidate.valid_until),
        "evidence": candidate.evidence.value,
        "validation": {"valid": validation.valid, "reasons": list(validation.reasons)},
        "delivery_reasons": payload["delivery_reasons"],
        "delivery_eligible": bool(validation.valid and queue_for_delivery and qualified),
        "can_place_orders": False, "can_send": bool(status == "QUEUED"), "rendered_card": card,
        "delivery_thesis_id": payload["delivery_thesis_id"],
        "entry_deadline": payload.get("entry_deadline"), "management_deadline": payload.get("management_deadline"),
        "session_date": payload.get("session_date"),
    }


async def dispatch_queued_advisory(
    db_path: str, stored: dict, profile: PartnerAdvisoryProfile, *, now: datetime,
    clock=None,
) -> bool:
    """Deliver one queued card through the durable hedge transport ledger.

    This reuses claim ownership, generation/destination deduplication,
    transport-start persistence, timeout ambiguity and bounded recovery.  The
    hedge module independently authorizes the live manual scope immediately
    before transport; this function cannot bypass that check.
    """
    # This is the final time boundary, not the scan-start clock.  A slow scan,
    # database wait or competing index must not consume a quote TTL unnoticed.
    final_now = (clock() if clock is not None else datetime.now(IST)).astimezone(IST)
    if (not settings.PARTNER_MANUAL_ADVISORY_ENABLED or not settings.PARTNER_MANUAL_ADVISORY_DELIVERY_ENABLED
            or stored.get("status") != "QUEUED"):
        return False
    try:
        valid_until = datetime.fromisoformat(str(stored["valid_until"])).astimezone(IST)
    except (KeyError, TypeError, ValueError):
        return False
    if valid_until <= final_now:
        return False
    try:
        entry_deadline = datetime.fromisoformat(str(stored.get("entry_deadline", ""))).astimezone(IST) if stored.get("entry_deadline") else None
    except (TypeError, ValueError):
        return False
    if entry_deadline is None or final_now > entry_deadline or stored.get("session_date") != final_now.date().isoformat():
        return False
    from hedge_advisory import _send_claimed_review
    candidate_id = str(stored["advisory_id"])
    sent = await _send_claimed_review(
        db_path, "manual_market_advisory", candidate_id, str(stored["rendered_card"]),
        detail={
            "phase": "manual_v1", "policy_version": INTRADAY_POLICY_VERSION,
            "advisory_id": candidate_id, "economic_version": stored["economic_version"],
            "profile_id": profile.profile_id, "profile_version": profile.version,
            "account_id": f"manual-profile:{profile.profile_id}",
            "decision_id": str(stored.get("delivery_thesis_id", candidate_id)), "generation_id": candidate_id,
            "exposure_lifecycle_id": "manual-advisory",
            "underlying": str(stored["underlying"]),
            "valid_until": str(stored["valid_until"]),
            "entry_deadline": str(stored["entry_deadline"]), "management_deadline": str(stored["management_deadline"]),
            "session_date": str(stored["session_date"]),
        },
        now=final_now, min_gap=timedelta(minutes=1),
        daily_cap=settings.PARTNER_MANUAL_ADVISORY_DAILY_CAP,
    )
    if sent:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "UPDATE partner_advisory_ideas SET status='DELIVERED_ACKNOWLEDGED', updated_at=? "
                "WHERE advisory_id=? AND status='QUEUED'",
                (_iso(final_now), candidate_id),
            )
            await db.commit()
    # The dispatch authorizer reads the persisted card's original validity,
    # so pass it here too rather than extending its life at send time.
    return sent


async def queue_management_updates(
    db_path: str, *, underlying: str, observed_underlying: float, observed_at: datetime,
) -> list[dict]:
    """Record one material, condition-based follow-up per published idea.

    It observes only the public underlying level and the published card.  It
    neither reads nor infers a partner order, position, fill, or P&L.
    """
    if observed_at.tzinfo is None or not _finite_positive(observed_underlying):
        return []
    await init_partner_advisory_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute(
            "SELECT advisory_id,payload FROM partner_advisory_ideas WHERE underlying=? "
            "AND status='DELIVERED_ACKNOWLEDGED'", (underlying.upper(),)
        )).fetchall()
    queued: list[dict] = []
    for advisory_id, raw_payload in rows:
        try:
            payload = json.loads(raw_payload)
            direction = payload.get("direction")
            invalidation = payload.get("invalidation_level")
            target = payload.get("target_level")
            profile_id = payload.get("profile_id")
            session_date = payload.get("session_date")
            management_deadline = datetime.fromisoformat(str(payload.get("management_deadline"))).astimezone(IST)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if session_date != observed_at.astimezone(IST).date().isoformat():
            continue
        if observed_at.astimezone(IST) >= management_deadline:
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    "UPDATE partner_advisory_ideas SET status='RETIRED_SESSION_END',updated_at=? "
                    "WHERE advisory_id=? AND status='DELIVERED_ACKNOWLEDGED'", (_iso(observed_at), advisory_id),
                )
                await db.commit()
            continue
        event_type = None
        level = None
        _entry_deadline, exit_reminder, _management_deadline = intraday_deadlines(observed_at)
        if observed_at.astimezone(IST) >= exit_reminder:
            event_type, level = "SESSION_EXIT_REMINDER", 0.0
        elif direction == FnoDirection.LONG.value and _finite_positive(invalidation) and observed_underlying <= float(invalidation):
            event_type, level = "INVALIDATION", float(invalidation)
        elif direction == FnoDirection.SHORT.value and _finite_positive(invalidation) and observed_underlying >= float(invalidation):
            event_type, level = "INVALIDATION", float(invalidation)
        elif direction == FnoDirection.LONG.value and _finite_positive(target) and observed_underlying >= float(target):
            event_type, level = "TARGET_ZONE", float(target)
        elif direction == FnoDirection.SHORT.value and _finite_positive(target) and observed_underlying <= float(target):
            event_type, level = "TARGET_ZONE", float(target)
        if event_type is None or not isinstance(profile_id, str):
            continue
        update_id = hashlib.sha256(f"{advisory_id}:{event_type}".encode()).hexdigest()[:24]
        wording = (
            f"Update to published idea {advisory_id}: underlying observed at {observed_underlying:,.2f} "
            f"at {_iso(observed_at)}. "
            + (f"It reached the published invalidation level {level:,.2f}." if event_type == "INVALIDATION"
               else (f"It reached the published target/review level {level:,.2f}." if event_type == "TARGET_ZONE"
                     else f"The intraday exit/reassessment deadline is {_iso(management_deadline)}; do not carry overnight."))
            + " If you took the idea, reassess the paired structure with current executable quotes; this is not order or position monitoring."
        )
        stamp = _iso(observed_at)
        async with aiosqlite.connect(db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            cur = await db.execute(
                "INSERT OR IGNORE INTO partner_advisory_updates(update_id,advisory_id,event_type,observed_at,observed_underlying,rendered_update,status,created_at,updated_at) "
                "VALUES(?,?,?,?,? ,?,'QUEUED',?,?)",
                (update_id, advisory_id, event_type, stamp, observed_underlying, wording, stamp, stamp),
            )
            await db.commit()
        if cur.rowcount == 1:
            queued.append({"update_id": update_id, "advisory_id": advisory_id, "profile_id": profile_id,
                           "event_type": event_type, "observed_at": stamp, "rendered_update": wording, "status": "QUEUED"})
    return queued


async def dispatch_queued_management_update(db_path: str, update: dict, *, now: datetime, clock=None) -> bool:
    """Deliver a queued material update with its own quota and authorization."""
    final_now = (clock() if clock is not None else datetime.now(IST)).astimezone(IST)
    if (not settings.PARTNER_MANUAL_ADVISORY_ENABLED or not settings.PARTNER_MANUAL_ADVISORY_DELIVERY_ENABLED
            or update.get("status") != "QUEUED"):
        return False
    observed_at = datetime.fromisoformat(str(update["observed_at"])).astimezone(IST)
    if (final_now - observed_at).total_seconds() > settings.PARTNER_MANUAL_ADVISORY_MAX_QUOTE_AGE_SEC:
        return False
    from hedge_advisory import _send_claimed_review
    update_id = str(update["update_id"])
    sent = await _send_claimed_review(
        db_path, "manual_advisory_update", update_id, str(update["rendered_update"]),
        detail={
            "phase": "manual_update_v1", "policy_version": INTRADAY_POLICY_VERSION,
            "update_id": update_id, "advisory_id": str(update["advisory_id"]),
            "profile_id": str(update["profile_id"]), "event_type": str(update["event_type"]),
            "observed_at": str(update["observed_at"]), "decision_id": update_id,
            "generation_id": update_id, "exposure_lifecycle_id": "manual-advisory-update",
        }, now=final_now, min_gap=timedelta(minutes=1),
        daily_cap=settings.PARTNER_MANUAL_ADVISORY_UPDATE_DAILY_CAP,
    )
    if sent:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("UPDATE partner_advisory_updates SET status='DELIVERED_ACKNOWLEDGED',updated_at=? WHERE update_id=? AND status='QUEUED'", (_iso(final_now), update_id))
            await db.commit()
    return sent


async def record_manual_feedback(
    db_path: str, advisory_id: str, decision: ManualDecision, *, reported_at: datetime,
    note: Optional[str] = None,
) -> None:
    """Record explicit partner feedback without treating delivery as a fill."""
    if reported_at.tzinfo is None:
        raise ValueError("reported_at must be timezone-aware")
    await init_partner_advisory_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        exists = await (await db.execute(
            "SELECT 1 FROM partner_advisory_ideas WHERE advisory_id=?", (advisory_id,)
        )).fetchone()
        if exists is None:
            raise ValueError("unknown_advisory_id")
        await db.execute(
            "INSERT OR IGNORE INTO partner_advisory_feedback(advisory_id,decision,reported_at,note) VALUES(?,?,?,?)",
            (advisory_id, decision.value, _iso(reported_at), note),
        )
        await db.commit()


async def load_advisory_cards(db_path: str, limit: int = 20) -> dict:
    await init_partner_advisory_db(db_path)
    limit = max(1, min(int(limit), 100))
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute(
            "SELECT advisory_id,economic_version,scope,underlying,exchange,status,evidence,quote_time,valid_until,rendered_card,payload,supersedes_id "
            "FROM partner_advisory_ideas ORDER BY created_at DESC LIMIT ?", (limit,)
        )).fetchall()
        feedback = await (await db.execute(
            "SELECT advisory_id,decision,reported_at,note FROM partner_advisory_feedback ORDER BY reported_at DESC"
        )).fetchall()
    by_advisory: dict[str, list[dict]] = {}
    for advisory_id, decision, reported_at, note in feedback:
        by_advisory.setdefault(advisory_id, []).append({
            "decision": decision, "reported_at": reported_at, "note": note,
        })
    cards = []
    for row in rows:
        payload = json.loads(row[10])
        cards.append({
            "advisory_id": row[0], "economic_version": row[1], "scope": row[2],
            "underlying": row[3], "exchange": row[4], "status": row[5],
            "evidence": row[6], "quote_time": row[7], "valid_until": row[8],
            "rendered_card": row[9], "validation_reasons": payload.get("validation_reasons", []),
            "delivery_reasons": payload.get("delivery_reasons", payload.get("validation_reasons", [])),
            "supersedes_id": row[11], "manual_feedback": by_advisory.get(row[0], []),
            "can_place_orders": False, "can_send": row[5] == "QUEUED",
        })
    return {"cards": cards, "automatic_execution": False, "delivery_authority": False}


async def load_advisory_diagnostics(db_path: str) -> dict:
    """Per-index funnel and lifecycle evidence, without manufacturing P&L."""
    await init_partner_advisory_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute(
            "SELECT advisory_id,underlying,status,payload,created_at,updated_at FROM partner_advisory_ideas "
            "ORDER BY created_at DESC"
        )).fetchall()
        update_rows = await (await db.execute(
            "SELECT i.underlying,u.event_type,u.status FROM partner_advisory_updates u "
            "JOIN partner_advisory_ideas i ON i.advisory_id=u.advisory_id"
        )).fetchall()
    by_index: dict[str, dict] = {name: {
        "generated": 0, "validated_shadow": 0, "queued": 0, "delivered": 0,
        "rejected": 0, "superseded": 0, "delivery_blocked": {}, "updates": {},
    } for name in INDEX_EXCHANGES}
    for _advisory_id, underlying, status, raw_payload, _created, _updated in rows:
        bucket = by_index.setdefault(underlying, {"generated": 0, "validated_shadow": 0, "queued": 0,
            "delivered": 0, "rejected": 0, "superseded": 0, "delivery_blocked": {}, "updates": {}})
        bucket["generated"] += 1
        if status == "VALIDATED_SHADOW":
            bucket["validated_shadow"] += 1
        elif status == "QUEUED":
            bucket["queued"] += 1
        elif status == "DELIVERED_ACKNOWLEDGED":
            bucket["delivered"] += 1
        elif status == "REJECTED":
            bucket["rejected"] += 1
        elif str(status).startswith("SUPERSEDED"):
            bucket["superseded"] += 1
        try:
            payload = json.loads(raw_payload)
            for reason in payload.get("delivery_reasons", []):
                bucket["delivery_blocked"][reason] = bucket["delivery_blocked"].get(reason, 0) + 1
        except (TypeError, json.JSONDecodeError):
            bucket["delivery_blocked"]["malformed_payload"] = bucket["delivery_blocked"].get("malformed_payload", 0) + 1
    for underlying, event_type, status in update_rows:
        updates = by_index.setdefault(underlying, {"updates": {}})["updates"]
        key = f"{event_type}:{status}"
        updates[key] = updates.get(key, 0) + 1
    return {
        "by_index": by_index,
        "outcome_interpretation": "Delivery is not a fill or P&L. Only explicitly reported feedback is partner-specific.",
        "automatic_execution": False,
    }


__all__ = [
    "AdvisoryCandidate", "AdvisoryLeg", "AdvisoryScope", "INDEX_EXCHANGES",
    "ManualDecision", "PartnerAdvisoryProfile", "StrategyEvidence", "ValidationResult",
    "advisory_identity", "build_conditional_index_protective_put", "build_directional_debit_spread", "init_partner_advisory_db",
    "is_strategy_qualified", "load_advisory_cards", "load_advisory_diagnostics", "load_partner_profile", "persist_candidate", "record_manual_feedback",
    "queue_management_updates", "dispatch_queued_management_update", "record_strategy_qualification", "render_advisory_card", "resolve_advisory_expiry", "save_partner_profile", "select_preferred_market_candidates", "validate_candidate", "validate_profile",
]
