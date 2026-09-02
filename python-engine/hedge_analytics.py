"""Safe, advisory-only analytics and position truth for partner hedging.

This module deliberately has no broker or order-placement dependency.  A
position is useful to an advisory workflow only after a partner/broker
reconciliation has confirmed it; signals and messages are not treated as
executed positions.

Quantity convention (important): ``signed_quantity`` is the *only* direction
field.  Positive is long and negative is short.  For F&O it is a number of
contracts, and ``lot_size`` converts contracts to underlying units.  For
equity it is a number of shares and ``lot_size`` is always one.  There is no
second BUY/SELL field that could disagree with the signed quantity.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Literal, Optional, Sequence

import aiosqlite


InstrumentType = Literal["EQUITY", "FUT", "CE", "PE"]
PositionStatus = Literal["OPEN", "CLOSED"]
VerificationStatus = Literal[
    "PENDING_CONFIRMATION", "RECONCILED", "DISPUTED", "STALE"
]

_INSTRUMENT_TYPES = frozenset(("EQUITY", "FUT", "CE", "PE"))
_POSITION_STATUSES = frozenset(("OPEN", "CLOSED"))
_VERIFICATION_STATUSES = frozenset(
    ("PENDING_CONFIRMATION", "RECONCILED", "DISPUTED", "STALE")
)


def _finite(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _positive(value: float, name: str) -> float:
    value = _finite(value, name)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _normalise_underlying(value: str) -> str:
    value = str(value).strip().upper()
    if not value:
        raise ValueError("underlying is required")
    return value


@dataclass(frozen=True)
class Greeks:
    """Greeks per underlying unit, before signed quantity/lot multiplication."""

    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0

    def __post_init__(self) -> None:
        for name in ("delta", "gamma", "theta", "vega"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))

    def scaled(self, multiplier: float) -> "Greeks":
        multiplier = _finite(multiplier, "multiplier")
        return Greeks(
            delta=self.delta * multiplier,
            gamma=self.gamma * multiplier,
            theta=self.theta * multiplier,
            vega=self.vega * multiplier,
        )

    def __add__(self, other: "Greeks") -> "Greeks":
        if not isinstance(other, Greeks):
            return NotImplemented
        return Greeks(
            self.delta + other.delta,
            self.gamma + other.gamma,
            self.theta + other.theta,
            self.vega + other.vega,
        )


@dataclass(frozen=True)
class PartnerHolding:
    """A confirmed cash/equity holding, represented in the same units as F&O."""

    underlying: str
    tradingsymbol: str
    signed_quantity: int
    entry_price: float
    current_price: Optional[float]
    beta: float = 1.0
    price_as_of: Optional[datetime] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "underlying", _normalise_underlying(self.underlying))
        if not str(self.tradingsymbol).strip():
            raise ValueError("tradingsymbol is required")
        if not isinstance(self.signed_quantity, int) or isinstance(self.signed_quantity, bool) or self.signed_quantity == 0:
            raise ValueError("signed_quantity must be a non-zero integer")
        object.__setattr__(self, "entry_price", _positive(self.entry_price, "entry_price"))
        object.__setattr__(self, "beta", _positive(self.beta, "beta"))
        if self.current_price is not None:
            object.__setattr__(self, "current_price", _positive(self.current_price, "current_price"))
            if self.price_as_of is None:
                raise ValueError("price_as_of is required with current_price")
        if self.price_as_of is not None:
            _aware(self.price_as_of, "price_as_of")

    @property
    def delta_units(self) -> float:
        return float(self.signed_quantity) * self.beta


@dataclass(frozen=True)
class PartnerPosition:
    """One actual (or awaiting-confirmation) partner instrument position.

    ``greeks`` is per underlying unit.  It is mandatory for options because
    treating unknown option Greeks as zero would understate risk.  Futures and
    equities have a deterministic delta of one when no explicit Greeks are
    supplied.
    """

    underlying: str
    instrument_type: InstrumentType
    tradingsymbol: str
    signed_quantity: int
    lot_size: int
    entry_price: float
    opened_at: datetime
    source: str
    position_id: Optional[int] = None
    expiry: Optional[date] = None
    strike: Optional[float] = None
    current_price: Optional[float] = None
    # Current spot/forward used to turn option Greeks into rupee exposure.
    # For a future, ``current_price`` is the futures quote used for the same
    # conversion; the optional underlying_price retains the reference spot.
    underlying_price: Optional[float] = None
    beta: float = 1.0
    greeks: Optional[Greeks] = None
    price_as_of: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    status: PositionStatus = "OPEN"
    verification_status: VerificationStatus = "PENDING_CONFIRMATION"
    broker_order_id: Optional[str] = None
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "underlying", _normalise_underlying(self.underlying))
        instrument_type = str(self.instrument_type).upper()
        if instrument_type not in _INSTRUMENT_TYPES:
            raise ValueError("instrument_type must be EQUITY, FUT, CE, or PE")
        object.__setattr__(self, "instrument_type", instrument_type)
        if not str(self.tradingsymbol).strip():
            raise ValueError("tradingsymbol is required")
        if not isinstance(self.signed_quantity, int) or isinstance(self.signed_quantity, bool):
            raise ValueError("signed_quantity must be an integer")
        if not isinstance(self.lot_size, int) or isinstance(self.lot_size, bool) or self.lot_size <= 0:
            raise ValueError("lot_size must be a positive integer")
        if instrument_type == "EQUITY" and self.lot_size != 1:
            raise ValueError("equity lot_size must be one")
        object.__setattr__(self, "entry_price", _positive(self.entry_price, "entry_price"))
        object.__setattr__(self, "beta", _positive(self.beta, "beta"))
        _aware(self.opened_at, "opened_at")
        if self.current_price is not None:
            object.__setattr__(self, "current_price", _positive(self.current_price, "current_price"))
            if self.price_as_of is None:
                raise ValueError("price_as_of is required with current_price")
        if self.underlying_price is not None:
            object.__setattr__(self, "underlying_price", _positive(self.underlying_price, "underlying_price"))
        if self.price_as_of is not None:
            _aware(self.price_as_of, "price_as_of")
        if self.updated_at is not None:
            _aware(self.updated_at, "updated_at")
        if self.closed_at is not None:
            _aware(self.closed_at, "closed_at")
        if self.status not in _POSITION_STATUSES:
            raise ValueError("status must be OPEN or CLOSED")
        if self.status == "OPEN" and self.signed_quantity == 0:
            raise ValueError("OPEN position requires a non-zero signed_quantity")
        if self.status == "CLOSED" and self.closed_at is None:
            raise ValueError("closed_at is required for a CLOSED position")
        if self.status == "OPEN" and self.closed_at is not None:
            raise ValueError("OPEN position cannot have closed_at")
        if self.verification_status not in _VERIFICATION_STATUSES:
            raise ValueError("unknown verification_status")
        if instrument_type in ("CE", "PE"):
            if self.expiry is None or self.strike is None:
                raise ValueError("option positions require expiry and strike")
            object.__setattr__(self, "strike", _positive(self.strike, "strike"))
            if self.greeks is None:
                raise ValueError("option positions require explicit Greeks")
            if self.underlying_price is None:
                raise ValueError("option positions require underlying_price")
        elif self.strike is not None:
            raise ValueError("only option positions may have a strike")
        if self.expiry is not None and not isinstance(self.expiry, date):
            raise ValueError("expiry must be a date")
        if self.position_id is not None and self.position_id <= 0:
            raise ValueError("position_id must be positive")

    @property
    def units(self) -> int:
        """Signed underlying units after applying the exchange lot size."""
        return self.signed_quantity * self.lot_size

    @property
    def per_unit_greeks(self) -> Greeks:
        if self.greeks is not None:
            return self.greeks
        # A cash equity unit and one futures underlying unit both carry a
        # delta of one. beta is only applied to equity to make beta-adjusted
        # index hedge sizing explicit.
        return Greeks(delta=self.beta if self.instrument_type == "EQUITY" else 1.0)

    @property
    def net_greeks(self) -> Greeks:
        return self.per_unit_greeks.scaled(self.units)

    @property
    def gross_notional(self) -> Optional[float]:
        if self.current_price is None:
            return None
        return abs(self.units) * self.current_price

    @property
    def delta_reference_price(self) -> Optional[float]:
        """Price used to convert delta-equivalent units to rupee exposure."""
        if self.instrument_type == "EQUITY":
            return self.current_price
        if self.instrument_type == "FUT":
            return self.current_price
        return self.underlying_price

    @property
    def net_delta_notional(self) -> Optional[float]:
        reference = self.delta_reference_price
        if reference is None:
            return None
        return self.net_greeks.delta * reference


@dataclass(frozen=True)
class PortfolioExposure:
    """Aggregate risk. ``valid`` is false instead of silently using gaps."""

    positions_count: int
    underlyings: tuple[str, ...]
    net_greeks: Greeks
    gross_notional: float
    long_delta_notional: float
    short_delta_notional: float
    net_delta_notional: float
    hedged_pct: Optional[float]
    valid: bool
    reason: Optional[str] = None

    @property
    def net_delta_units(self) -> float:
        """Underlying units; not comparable across symbols and never sized on."""
        return self.net_greeks.delta


@dataclass(frozen=True)
class QuoteFreshness:
    fresh: bool
    reason: str
    observed_at: Optional[datetime]
    age_seconds: Optional[float]


@dataclass(frozen=True)
class VixRegimeReading:
    """Informational VIX posture; it can never be an execution instruction."""

    regime: str
    spot: Optional[float]
    pct_change: Optional[float]
    z_score: Optional[float]
    data_fresh: bool
    posture: str
    should_review_protection: bool
    automatic_action: bool = False


@dataclass(frozen=True)
class FuturesHedgeSizing:
    """Conservative, advisory-only sizing in signed futures contracts."""

    valid: bool
    reason: Optional[str]
    underlying: str
    target_hedge_ratio: float
    existing_hedge_pct: Optional[float]
    post_trade_hedge_pct: Optional[float]
    contracts_raw: Optional[float]
    contracts_rounded: Optional[int]
    lot_size: int
    futures_price: Optional[float]
    advisory_only: bool = True


def assess_quote_freshness(
    observed_at: Optional[datetime],
    *,
    now: Optional[datetime] = None,
    max_age: timedelta = timedelta(minutes=5),
) -> QuoteFreshness:
    """Validate quote age. Naive/future/missing timestamps fail closed."""
    if observed_at is None:
        return QuoteFreshness(False, "missing quote timestamp", None, None)
    if max_age.total_seconds() <= 0:
        raise ValueError("max_age must be positive")
    try:
        _aware(observed_at, "observed_at")
        now = now or datetime.now(timezone.utc)
        _aware(now, "now")
    except ValueError:
        return QuoteFreshness(False, "timezone-aware timestamp required", observed_at, None)
    age_seconds = (now.astimezone(timezone.utc) - observed_at.astimezone(timezone.utc)).total_seconds()
    if age_seconds < -60:
        return QuoteFreshness(False, "quote timestamp is implausibly in the future", observed_at, age_seconds)
    if age_seconds > max_age.total_seconds():
        return QuoteFreshness(False, "quote is stale", observed_at, age_seconds)
    return QuoteFreshness(True, "fresh", observed_at, age_seconds)


def position_is_actionable(
    position: PartnerPosition,
    *,
    now: Optional[datetime] = None,
    max_quote_age: timedelta = timedelta(minutes=5),
) -> bool:
    """A narrow guard for later advisory builders, never an order gate."""
    if position.status != "OPEN" or position.verification_status != "RECONCILED":
        return False
    if position.current_price is None:
        return False
    if position.instrument_type in ("CE", "PE") and position.expiry is not None:
        today = (now or datetime.now(timezone.utc)).date()
        if position.expiry < today:
            return False
    return assess_quote_freshness(position.price_as_of, now=now, max_age=max_quote_age).fresh


def aggregate_portfolio(positions: Iterable[PartnerPosition]) -> PortfolioExposure:
    """Aggregate confirmed current positions, failing closed for risk gaps.

    An aggregate may include multiple underlyings for reporting, but it must be
    filtered to one underlying before using delta units to size an index future.
    """
    positions = tuple(positions)
    if not positions:
        return PortfolioExposure(0, (), Greeks(), 0.0, 0.0, 0.0, 0.0, None, False, "no positions")
    if any(p.status != "OPEN" for p in positions):
        return PortfolioExposure(0, (), Greeks(), 0.0, 0.0, 0.0, 0.0, None, False, "closed position supplied")
    if any(p.verification_status != "RECONCILED" for p in positions):
        return PortfolioExposure(0, (), Greeks(), 0.0, 0.0, 0.0, 0.0, None, False, "unreconciled position supplied")
    if any(p.current_price is None for p in positions):
        return PortfolioExposure(0, (), Greeks(), 0.0, 0.0, 0.0, 0.0, None, False, "missing current price")

    total = Greeks()
    gross = 0.0
    long_delta_notional = 0.0
    short_delta_notional = 0.0
    for position in positions:
        total = total + position.net_greeks
        notional = position.gross_notional
        if notional is None:  # Defensive: checked above, but preserve fail closed.
            return PortfolioExposure(0, (), Greeks(), 0.0, 0.0, 0.0, 0.0, None, False, "missing current price")
        gross += notional
        delta_notional = position.net_delta_notional
        if delta_notional is None:
            return PortfolioExposure(0, (), Greeks(), 0.0, 0.0, 0.0, 0.0, None, False, "missing delta reference price")
        long_delta_notional += max(delta_notional, 0.0)
        short_delta_notional += max(-delta_notional, 0.0)
    hedged = min(short_delta_notional / long_delta_notional, 1.0) if long_delta_notional > 0 else None
    return PortfolioExposure(
        positions_count=len(positions),
        underlyings=tuple(sorted({p.underlying for p in positions})),
        net_greeks=total,
        gross_notional=gross,
        long_delta_notional=long_delta_notional,
        short_delta_notional=short_delta_notional,
        net_delta_notional=long_delta_notional - short_delta_notional,
        hedged_pct=hedged,
        valid=True,
    )


def portfolio_aggregate(positions: Iterable[PartnerPosition]) -> PortfolioExposure:
    """Compatibility name for the hedge blueprint's portfolio roll-up."""
    return aggregate_portfolio(positions)


def net_greeks(positions: Iterable[PartnerPosition]) -> Optional[Greeks]:
    """Return confirmed net Greeks, or ``None`` instead of a false zero."""
    exposure = aggregate_portfolio(positions)
    return exposure.net_greeks if exposure.valid else None


def size_futures_hedge(
    exposure: PortfolioExposure,
    *,
    futures_underlying: str,
    lot_size: int,
    futures_price: float,
    target_hedge_ratio: float,
) -> FuturesHedgeSizing:
    """Size an additional short futures hedge conservatively.

    Rounding is toward zero, never away from zero: one whole lot must not turn
    a long book net short merely because the exact contract count is fractional.
    The caller must still perform suitability and human review.
    """
    underlying = _normalise_underlying(futures_underlying)
    invalid = lambda reason: FuturesHedgeSizing(
        False, reason, underlying, target_hedge_ratio, None, None, None, None,
        lot_size if isinstance(lot_size, int) and lot_size > 0 else 0,
        futures_price if isinstance(futures_price, (int, float)) and math.isfinite(float(futures_price)) else None,
    )
    if not exposure.valid:
        return invalid(exposure.reason or "invalid portfolio exposure")
    if exposure.underlyings != (underlying,):
        return invalid("futures sizing requires a reconciled single-underlying exposure")
    if not isinstance(lot_size, int) or isinstance(lot_size, bool) or lot_size <= 0:
        return invalid("lot_size must be a positive integer")
    try:
        futures_price = _positive(futures_price, "futures_price")
        target_hedge_ratio = _finite(target_hedge_ratio, "target_hedge_ratio")
    except ValueError as exc:
        return invalid(str(exc))
    if not 0.0 <= target_hedge_ratio <= 1.0:
        return invalid("target_hedge_ratio must be between zero and one")
    if exposure.long_delta_notional <= 0:
        return invalid("portfolio has no positive delta notional to hedge")

    required_short_notional = target_hedge_ratio * exposure.long_delta_notional
    additional_short_notional = max(0.0, required_short_notional - exposure.short_delta_notional)
    contract_notional = futures_price * lot_size
    raw = -additional_short_notional / contract_notional
    rounded = math.ceil(raw)  # Negative ceil rounds toward zero.
    post_short = exposure.short_delta_notional + abs(rounded) * contract_notional
    existing_pct = min(exposure.short_delta_notional / exposure.long_delta_notional, 1.0)
    post_pct = min(post_short / exposure.long_delta_notional, 1.0)
    reason = None if rounded != 0 else "one futures lot would overhedge; no contract-sized advisory"
    return FuturesHedgeSizing(
        valid=rounded != 0,
        reason=reason,
        underlying=underlying,
        target_hedge_ratio=target_hedge_ratio,
        existing_hedge_pct=existing_pct,
        post_trade_hedge_pct=post_pct,
        contracts_raw=raw,
        contracts_rounded=rounded,
        lot_size=lot_size,
        futures_price=futures_price,
    )


def futures_hedge_size(
    exposure: PortfolioExposure,
    *,
    futures_underlying: str,
    lot_size: int,
    futures_price: float,
    target_hedge_ratio: float,
) -> FuturesHedgeSizing:
    """Blueprint-compatible name for :func:`size_futures_hedge`."""
    return size_futures_hedge(
        exposure,
        futures_underlying=futures_underlying,
        lot_size=lot_size,
        futures_price=futures_price,
        target_hedge_ratio=target_hedge_ratio,
    )


def vix_regime_reading(
    india_vix_spot: Optional[float] = None,
    india_vix_prev_close: Optional[float] = None,
    india_vix_20d_avg: Optional[float] = None,
    *,
    history: Optional[Sequence[float]] = None,
    observed_at: Optional[datetime] = None,
    now: Optional[datetime] = None,
    max_age: timedelta = timedelta(minutes=15),
) -> VixRegimeReading:
    """Classify volatility for an advisory review, never a trade instruction.

    The preferred ``history`` has at least 20 previous closes and yields a
    genuine z-score.  A supplied 20-day mean without dispersion is retained as
    context but intentionally cannot manufacture a z-score.
    """
    try:
        spot = _positive(india_vix_spot, "india_vix_spot") if india_vix_spot is not None else None
    except ValueError:
        spot = None
    if spot is None:
        return VixRegimeReading("UNAVAILABLE", None, None, None, False, "VIX unavailable — no hedge action", False)
    freshness = assess_quote_freshness(observed_at, now=now, max_age=max_age) if observed_at else QuoteFreshness(True, "timestamp not supplied", None, None)
    if not freshness.fresh:
        return VixRegimeReading("UNAVAILABLE", spot, None, None, False, "VIX is stale — no hedge action", False)

    pct_change: Optional[float] = None
    if india_vix_prev_close is not None:
        try:
            prev = _positive(india_vix_prev_close, "india_vix_prev_close")
            pct_change = spot / prev - 1.0
        except ValueError:
            pct_change = None
    values: list[float] = []
    for value in history or ():
        try:
            values.append(_positive(value, "vix history value"))
        except ValueError:
            continue
    z_score: Optional[float] = None
    if len(values) >= 20:
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        if variance > 0:
            z_score = (spot - mean) / math.sqrt(variance)
    # Mean-only input is not enough to produce a standard deviation.  It is
    # intentionally not substituted with an arbitrary threshold.
    _ = india_vix_20d_avg
    if (pct_change is not None and pct_change >= 0.20) or (z_score is not None and z_score >= 2.0):
        return VixRegimeReading("PANIC", spot, pct_change, z_score, True, "Volatility shock: review existing protection; avoid automatic long-premium buys", True)
    if (pct_change is not None and pct_change >= 0.12) or (z_score is not None and z_score >= 1.0):
        return VixRegimeReading("ELEVATED", spot, pct_change, z_score, True, "Volatility elevated: review exposure and hedge cost with a human", True)
    if z_score is not None and z_score <= -1.0:
        return VixRegimeReading("LOW", spot, pct_change, z_score, True, "Volatility subdued: protection may merit a cost review; no automatic action", True)
    return VixRegimeReading("NORMAL", spot, pct_change, z_score, True, "Volatility normal: continue monitoring; no automatic action", False)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS partner_positions (
    position_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL DEFAULT 'UNKNOWN',
    verification_status TEXT NOT NULL DEFAULT 'PENDING_CONFIRMATION',
    underlying TEXT NOT NULL DEFAULT '',
    instrument_type TEXT NOT NULL DEFAULT 'EQUITY',
    tradingsymbol TEXT NOT NULL DEFAULT '',
    expiry TEXT,
    strike REAL,
    signed_quantity INTEGER NOT NULL DEFAULT 0,
    lot_size INTEGER NOT NULL DEFAULT 1,
    entry_price REAL NOT NULL DEFAULT 0,
    current_price REAL,
    underlying_price REAL,
    beta REAL NOT NULL DEFAULT 1,
    current_greeks_json TEXT,
    price_as_of TEXT,
    opened_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    closed_at TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN',
    broker_order_id TEXT,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS partner_position_reconciliations (
    reconciliation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER NOT NULL,
    reconciled_at TEXT NOT NULL,
    observed_quantity INTEGER NOT NULL,
    observed_price REAL,
    observed_greeks_json TEXT,
    source TEXT NOT NULL,
    notes TEXT,
    FOREIGN KEY(position_id) REFERENCES partner_positions(position_id)
);
CREATE INDEX IF NOT EXISTS ix_partner_positions_reconciled_open
    ON partner_positions (underlying, status, verification_status)
    WHERE status = 'OPEN' AND verification_status = 'RECONCILED';
CREATE INDEX IF NOT EXISTS ix_partner_position_reconciliations_position
    ON partner_position_reconciliations (position_id, reconciled_at DESC);
"""

_MIGRATION_COLUMNS = {
    "source": "TEXT NOT NULL DEFAULT 'UNKNOWN'",
    "verification_status": "TEXT NOT NULL DEFAULT 'PENDING_CONFIRMATION'",
    "instrument_type": "TEXT NOT NULL DEFAULT 'EQUITY'",
    "tradingsymbol": "TEXT NOT NULL DEFAULT ''",
    "expiry": "TEXT",
    "strike": "REAL",
    "signed_quantity": "INTEGER NOT NULL DEFAULT 0",
    "lot_size": "INTEGER NOT NULL DEFAULT 1",
    "entry_price": "REAL NOT NULL DEFAULT 0",
    "current_price": "REAL",
    "underlying_price": "REAL",
    "beta": "REAL NOT NULL DEFAULT 1",
    "current_greeks_json": "TEXT",
    "price_as_of": "TEXT",
    "updated_at": "TEXT NOT NULL DEFAULT ''",
    "status": "TEXT NOT NULL DEFAULT 'OPEN'",
    "broker_order_id": "TEXT",
    "notes": "TEXT",
}


async def init_hedge_db(db_path: str) -> None:
    """Create the schema and add non-destructive columns to an older table."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=5000")
        await db.executescript(_SCHEMA)
        cur = await db.execute("PRAGMA table_info(partner_positions)")
        columns = {row[1] for row in await cur.fetchall()}
        for name, ddl in _MIGRATION_COLUMNS.items():
            if name not in columns:
                await db.execute(f"ALTER TABLE partner_positions ADD COLUMN {name} {ddl}")
        # A NULL broker order id is allowed repeatedly. A real order id is an
        # idempotency key, so re-importing a broker snapshot cannot duplicate it.
        await db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_partner_positions_broker_order "
            "ON partner_positions (broker_order_id) WHERE broker_order_id IS NOT NULL"
        )
        await db.commit()


def _timestamp(value: datetime) -> str:
    return _aware(value, "timestamp").isoformat()


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if value in (None, ""):
        return None
    parsed = datetime.fromisoformat(value)
    return _aware(parsed, "stored timestamp")


def _greeks_json(greeks: Optional[Greeks]) -> Optional[str]:
    if greeks is None:
        return None
    return json.dumps({"delta": greeks.delta, "gamma": greeks.gamma, "theta": greeks.theta, "vega": greeks.vega}, sort_keys=True)


def _parse_greeks(value: Optional[str]) -> Optional[Greeks]:
    if not value:
        return None
    try:
        raw = json.loads(value)
        return Greeks(**raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _row_to_position(row: aiosqlite.Row) -> Optional[PartnerPosition]:
    try:
        expiry = date.fromisoformat(row["expiry"]) if row["expiry"] else None
        return PartnerPosition(
            position_id=int(row["position_id"]),
            source=row["source"],
            verification_status=row["verification_status"],
            underlying=row["underlying"],
            instrument_type=row["instrument_type"],
            tradingsymbol=row["tradingsymbol"],
            expiry=expiry,
            strike=float(row["strike"]) if row["strike"] is not None else None,
            signed_quantity=int(row["signed_quantity"]),
            lot_size=int(row["lot_size"]),
            entry_price=float(row["entry_price"]),
            current_price=float(row["current_price"]) if row["current_price"] is not None else None,
            underlying_price=float(row["underlying_price"]) if row["underlying_price"] is not None else None,
            beta=float(row["beta"]),
            greeks=_parse_greeks(row["current_greeks_json"]),
            price_as_of=_parse_timestamp(row["price_as_of"]),
            opened_at=_parse_timestamp(row["opened_at"]),
            updated_at=_parse_timestamp(row["updated_at"]),
            closed_at=_parse_timestamp(row["closed_at"]),
            status=row["status"],
            broker_order_id=row["broker_order_id"],
            notes=row["notes"],
        )
    except (KeyError, TypeError, ValueError):
        # Legacy/partially migrated rows cannot be silently represented as a
        # valid actual holding. They are excluded until manually reconciled.
        return None


_POSITION_COLUMNS = (
    "source, verification_status, underlying, instrument_type, tradingsymbol, "
    "expiry, strike, signed_quantity, lot_size, entry_price, current_price, underlying_price, beta, "
    "current_greeks_json, price_as_of, opened_at, updated_at, closed_at, status, "
    "broker_order_id, notes"
)


def _position_values(position: PartnerPosition) -> tuple:
    return (
        position.source,
        position.verification_status,
        position.underlying,
        position.instrument_type,
        position.tradingsymbol,
        position.expiry.isoformat() if position.expiry else None,
        position.strike,
        position.signed_quantity,
        position.lot_size,
        position.entry_price,
        position.current_price,
        position.underlying_price,
        position.beta,
        _greeks_json(position.greeks),
        _timestamp(position.price_as_of) if position.price_as_of else None,
        _timestamp(position.opened_at),
        _timestamp(position.updated_at or position.opened_at),
        _timestamp(position.closed_at) if position.closed_at else None,
        position.status,
        position.broker_order_id,
        position.notes,
    )


async def create_partner_position(db_path: str, position: PartnerPosition) -> PartnerPosition:
    """Persist a position; broker order IDs provide restart-safe idempotency."""
    await init_hedge_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        if position.broker_order_id:
            cur = await db.execute(
                "SELECT * FROM partner_positions WHERE broker_order_id=?",
                (position.broker_order_id,),
            )
            row = await cur.fetchone()
            existing = _row_to_position(row) if row is not None else None
        else:
            existing = None
        if existing is not None:
            identity = (
                existing.underlying, existing.instrument_type,
                existing.tradingsymbol, existing.signed_quantity,
                existing.lot_size, existing.entry_price,
            )
            requested = (
                position.underlying, position.instrument_type,
                position.tradingsymbol, position.signed_quantity,
                position.lot_size, position.entry_price,
            )
            if identity != requested:
                await db.rollback()
                raise ValueError(
                    "broker_order_id already belongs to a different partner position"
                )
            await db.commit()
            return existing
        marks = ", ".join("?" for _ in _position_values(position))
        cur = await db.execute(
            f"INSERT INTO partner_positions ({_POSITION_COLUMNS}) VALUES ({marks})",
            _position_values(position),
        )
        position_id = int(cur.lastrowid)
        await db.commit()
    return PartnerPosition(**{**position.__dict__, "position_id": position_id})


# More discoverable alias for call sites that import broker snapshots.
upsert_partner_position = create_partner_position


async def get_partner_position(db_path: str, position_id: int) -> Optional[PartnerPosition]:
    await init_hedge_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM partner_positions WHERE position_id=?", (position_id,))
        row = await cur.fetchone()
    return _row_to_position(row) if row is not None else None


async def load_partner_positions(db_path: str, *, include_closed: bool = False) -> list[PartnerPosition]:
    """Load valid rows only. This includes unconfirmed rows for reconciliation UI."""
    await init_hedge_db(db_path)
    query = "SELECT * FROM partner_positions"
    if not include_closed:
        query += " WHERE status='OPEN'"
    query += " ORDER BY position_id"
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(query)
        rows = await cur.fetchall()
    return [position for row in rows if (position := _row_to_position(row)) is not None]


async def load_reconciled_open_partner_positions(db_path: str) -> list[PartnerPosition]:
    """The only loader suitable for analytics that influence hedge advice."""
    await init_hedge_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM partner_positions WHERE status='OPEN' "
            "AND verification_status='RECONCILED' ORDER BY position_id"
        )
        rows = await cur.fetchall()
    return [position for row in rows if (position := _row_to_position(row)) is not None]


async def reconcile_partner_position(
    db_path: str,
    position_id: int,
    *,
    observed_quantity: int,
    reconciled_at: datetime,
    source: str,
    current_price: Optional[float] = None,
    underlying_price: Optional[float] = None,
    price_as_of: Optional[datetime] = None,
    greeks: Optional[Greeks] = None,
    notes: Optional[str] = None,
) -> Optional[PartnerPosition]:
    """Record an observed broker/partner state and mark the row reconciled.

    A zero observed quantity closes the position.  Options cannot become
    reconciled without current Greeks; this prevents their risk disappearing
    from a portfolio aggregate.
    """
    if not isinstance(observed_quantity, int) or isinstance(observed_quantity, bool):
        raise ValueError("observed_quantity must be an integer")
    _aware(reconciled_at, "reconciled_at")
    if not str(source).strip():
        raise ValueError("source is required")
    if current_price is not None:
        _positive(current_price, "current_price")
        if price_as_of is None:
            raise ValueError("price_as_of is required with current_price")
    if price_as_of is not None:
        _aware(price_as_of, "price_as_of")
    if underlying_price is not None:
        _positive(underlying_price, "underlying_price")
    position = await get_partner_position(db_path, position_id)
    if position is None:
        return None
    if position.status == "CLOSED":
        return position
    if position.instrument_type in ("CE", "PE") and observed_quantity != 0:
        if greeks is None:
            raise ValueError("reconciling an open option requires current Greeks")
        if underlying_price is None and position.underlying_price is None:
            raise ValueError("reconciling an open option requires underlying_price")

    status = "CLOSED" if observed_quantity == 0 else "OPEN"
    verification = "RECONCILED"
    closed_at = reconciled_at if status == "CLOSED" else None
    await init_hedge_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("BEGIN IMMEDIATE")
        updated = await db.execute(
            "UPDATE partner_positions SET signed_quantity=?, current_price=?, underlying_price=?, current_greeks_json=?, "
            "price_as_of=?, updated_at=?, closed_at=?, status=?, verification_status=?, notes=? "
            "WHERE position_id=? AND status='OPEN'",
            (
                observed_quantity,
                current_price if current_price is not None else position.current_price,
                underlying_price if underlying_price is not None else position.underlying_price,
                _greeks_json(greeks) if greeks is not None else _greeks_json(position.greeks),
                _timestamp(price_as_of) if price_as_of else (_timestamp(position.price_as_of) if position.price_as_of else None),
                _timestamp(reconciled_at),
                _timestamp(closed_at) if closed_at else None,
                status,
                verification,
                notes if notes is not None else position.notes,
                position_id,
            ),
        )
        if updated.rowcount != 1:
            await db.rollback()
            return await get_partner_position(db_path, position_id)
        await db.execute(
            "INSERT INTO partner_position_reconciliations "
            "(position_id, reconciled_at, observed_quantity, observed_price, observed_greeks_json, source, notes) "
            "VALUES (?,?,?,?,?,?,?)",
            (position_id, _timestamp(reconciled_at), observed_quantity, current_price,
             _greeks_json(greeks), source, notes),
        )
        await db.commit()
    return await get_partner_position(db_path, position_id)


async def close_partner_position(
    db_path: str, position_id: int, *, closed_at: datetime, source: str, notes: Optional[str] = None,
) -> Optional[PartnerPosition]:
    """Idempotently close a confirmed position through the reconciliation log."""
    return await reconcile_partner_position(
        db_path, position_id, observed_quantity=0, reconciled_at=closed_at,
        source=source, notes=notes,
    )
