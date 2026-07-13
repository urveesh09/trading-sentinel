"""
[FNO-MODELS 2026-07-10] Data types for the F&O subsystem (spec §5).

Owns:
  - OptionType: CE / PE
  - FnoSource:  FNO_PAPER / FNO_LIVE source tags (spec §10.3)
  - Leg:        one option leg of a position (input to fno_risk.max_loss)
  - Contract:   a resolved NFO contract (token + symbol + terms)
  - FnoDirection: LONG (buy CE) / SHORT (buy PE) -- direction of the
    underlying view, NOT of the option position (we only ever buy in P1)

Hard architectural rule (enforced by tests/test_fno_isolation.py):
  no fno_* module imports penny_*, engine, risk_engine, portfolio,
  evaluate_signal or evaluate_momentum_signal. A read-only import of
  regime.py is permitted (spec §5).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Optional


class OptionType(str, Enum):
    CE = "CE"
    PE = "PE"


class FnoDirection(str, Enum):
    """Directional view on the underlying. LONG expresses as buy-CE,
    SHORT as buy-PE. There is no short option leg anywhere in P1."""
    LONG = "LONG"
    SHORT = "SHORT"


class FnoSource(str, Enum):
    """Ledger/positions source tags. Purely additive next to
    SYSTEM / MOMENTUM / PENNY / EDGE_* -- the existing strict-separation
    queries filter on their own tags, so F&O P&L can never contaminate
    another pool (spec §10.3, operator mandate 2026-06-24)."""
    FNO_PAPER = "FNO_PAPER"
    FNO_LIVE = "FNO_LIVE"


@dataclass(frozen=True)
class Leg:
    """One option leg. quantity is in LOTS, signed: +n long, -n short.

    premium is the per-unit premium paid (long) or received (short),
    always positive; the sign of the cashflow comes from quantity.
    """
    opt_type: OptionType
    strike: float
    quantity: int          # lots; + = long, - = short
    premium: float         # per-unit premium, >= 0


@dataclass(frozen=True)
class Contract:
    """A resolved NFO contract from the instrument dump.

    lot_size and expiry are read from /instruments/NFO every morning,
    never hardcoded (VERIFY-2, VERIFY-3).
    """
    token: int
    tradingsymbol: str
    name: str              # underlying, e.g. "NIFTY"
    expiry: date
    strike: float          # 0.0 for futures
    instrument_type: str   # "CE" / "PE" / "FUT"
    lot_size: int
    tick_size: float = 0.05


@dataclass
class ContractQuote:
    """One contract's slice of a chain snapshot (from a batched /quote)."""
    contract: Contract
    bid: float = 0.0
    ask: float = 0.0
    ltp: float = 0.0
    oi: int = 0
    volume: int = 0
    last_trade_time: Optional[datetime] = None

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2.0
        return self.ltp

    @property
    def spread_pct(self) -> float:
        m = self.mid
        if m <= 0 or self.bid <= 0 or self.ask <= 0:
            return float("inf")
        return (self.ask - self.bid) / m

    @property
    def two_sided(self) -> bool:
        return self.bid > 0 and self.ask > 0
