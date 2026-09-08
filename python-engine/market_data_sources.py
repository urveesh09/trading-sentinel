"""Provider-neutral, non-order market-data source contracts."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence

import pandas as pd


class Capability(str, Enum):
    CURRENT_FULL_QUOTE = "CURRENT_FULL_QUOTE"
    FORWARD_DEPTH_STREAM = "FORWARD_DEPTH_STREAM"
    HISTORICAL_CANDLES = "HISTORICAL_CANDLES"
    HISTORICAL_OI = "HISTORICAL_OI"
    HISTORICAL_DEPTH = "HISTORICAL_DEPTH"
    DAILY_CONTRACT_MASTER = "DAILY_CONTRACT_MASTER"


@dataclass(frozen=True)
class SourceCapabilityReport:
    provider: str
    entitled: bool
    capabilities: tuple[Capability, ...]
    limitations: tuple[str, ...]


class MarketDataSource(Protocol):
    async def capability_report(self) -> SourceCapabilityReport: ...
    async def current_quotes(self, tokens: Sequence[int]) -> Mapping[int, Mapping[str, Any]]: ...
    async def historical_candles(self, token: int, from_datetime: str, to_datetime: str, interval: str = "5minute") -> pd.DataFrame: ...
    async def contract_master(self, segment: str) -> str: ...


class KiteMarketDataSource:
    """Thin adapter around the one existing KiteClient instance."""
    def __init__(self, kite):
        self.kite = kite

    async def capability_report(self) -> SourceCapabilityReport:
        entitled = bool(getattr(self.kite, "access_token", None))
        return SourceCapabilityReport(
            provider="KITE", entitled=entitled,
            capabilities=(Capability.CURRENT_FULL_QUOTE, Capability.FORWARD_DEPTH_STREAM,
                          Capability.HISTORICAL_CANDLES, Capability.HISTORICAL_OI,
                          Capability.DAILY_CONTRACT_MASTER) if entitled else (),
            limitations=("Historical API candles/OI are not historical bid/ask depth.",
                         "Forward quotes/depth are observations, not guaranteed fills.",
                         "Expired-option availability and tokens must be recorded, not assumed."),
        )

    async def current_quotes(self, tokens: Sequence[int]) -> Mapping[int, Mapping[str, Any]]:
        return await self.kite.get_quote(list(tokens))

    async def historical_candles(self, token: int, from_datetime: str, to_datetime: str, interval: str = "5minute") -> pd.DataFrame:
        return await self.kite.get_intraday_by_token(token, from_datetime, to_datetime, interval)

    async def contract_master(self, segment: str) -> str:
        return await self.kite.get_instruments_dump(segment)


@dataclass(frozen=True)
class BreezeHistoricalRequest:
    """Validated request shape for an optional authorised Breeze probe."""
    stock_code: str
    exchange_code: str
    product_type: str
    expiry_date: str
    right: str
    strike_price: str
    interval: str
    from_date: str
    to_date: str

    @classmethod
    def nifty_option(cls, *, expiry_date: str, right: str, strike_price: float, from_date: str, to_date: str, interval: str = "5minute") -> "BreezeHistoricalRequest":
        return cls("NIFTY", "NFO", "options", expiry_date, right.upper(), str(strike_price), interval, from_date, to_date)

    @classmethod
    def sensex_option(cls, *, expiry_date: str, right: str, strike_price: float, from_date: str, to_date: str, interval: str = "5minute") -> "BreezeHistoricalRequest":
        # BSESEN is Breeze's provider alias, never a Kite symbol.
        return cls("BSESEN", "BFO", "options", expiry_date, right.upper(), str(strike_price), interval, from_date, to_date)

    def as_payload(self) -> dict[str, str]:
        if self.exchange_code not in {"NFO", "BFO"} or self.right not in {"CE", "PE"}:
            raise ValueError("Breeze probe requires NFO/BFO option CE/PE identity")
        return {"stock_code": self.stock_code, "exchange_code": self.exchange_code,
                "product_type": self.product_type, "expiry_date": self.expiry_date,
                "right": self.right, "strike_price": self.strike_price,
                "interval": self.interval, "from_date": self.from_date, "to_date": self.to_date}
