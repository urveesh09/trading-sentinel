"""Versioned transaction-cost schedules frozen into research evidence.

Snapshot functions read active settings once. New evidence therefore records
both its declared published schedule and any operator-overridden rates, while
previously persisted JSON remains untouched and self-contained.
"""
from __future__ import annotations

from config import settings

EQUITY_INTRADAY_SCHEDULE_VERSION = "ZERODHA_NSE_EQUITY_INTRADAY_AS_OF_2026-08-10"
EQUITY_INTRADAY_EFFECTIVE_DATE = None
EQUITY_INTRADAY_VERIFIED_AS_OF = "2026-08-10"
OPTIONS_SCHEDULE_VERSION = "ZERODHA_NSE_OPTIONS_2026-04-01"
OPTIONS_EFFECTIVE_DATE = "2026-04-01"


def equity_intraday_cost_snapshot(*, namespace: str = "ZERODHA") -> dict:
    prefix = namespace.strip().upper()
    if prefix not in {"ZERODHA", "PENNY"}:
        raise ValueError("equity cost namespace must be ZERODHA or PENNY")
    return {
        "schedule_version": EQUITY_INTRADAY_SCHEDULE_VERSION,
        "effective_date": EQUITY_INTRADAY_EFFECTIVE_DATE,
        "verified_as_of": EQUITY_INTRADAY_VERIFIED_AS_OF,
        "market": "NSE_EQUITY_INTRADAY",
        "rates": {
            "brokerage_pct": float(getattr(settings, f"{prefix}_BROKERAGE_PCT")),
            "brokerage_max": float(getattr(settings, f"{prefix}_BROKERAGE_MAX")),
            "stt_sell_pct": float(getattr(settings, f"{prefix}_STT_MIS")),
            "exchange_pct": float(getattr(settings, f"{prefix}_EXCHANGE_PCT")),
            "stamp_duty_buy_pct": float(getattr(settings, f"{prefix}_STAMP_DUTY_PCT")),
            "sebi_pct": float(getattr(settings, f"{prefix}_SEBI_PCT")),
            "ipft_pct": float(getattr(settings, f"{prefix}_IPFT_PCT")),
            "gst_pct": float(getattr(settings, f"{prefix}_GST_PCT")),
        },
    }


def options_cost_snapshot() -> dict:
    return {
        "schedule_version": OPTIONS_SCHEDULE_VERSION,
        "effective_date": OPTIONS_EFFECTIVE_DATE,
        "market": "NSE_EQUITY_OPTIONS_PREMIUM",
        "rates": {
            "brokerage_flat_per_order": float(settings.FNO_BROKERAGE_FLAT),
            "stt_sell_pct": float(settings.FNO_STT_SELL_PCT),
            "exchange_pct": float(settings.FNO_EXCHANGE_TXN_PCT),
            "sebi_pct": float(settings.FNO_SEBI_PCT),
            "stamp_duty_buy_pct": float(settings.FNO_STAMP_DUTY_PCT),
            "ipft_pct": float(settings.FNO_IPFT_PCT),
            "gst_pct": float(settings.FNO_GST_PCT),
        },
    }
