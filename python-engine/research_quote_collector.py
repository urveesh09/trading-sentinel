"""Forward-only NIFTY/SENSEX quote evidence collection.

This module is intentionally independent from partner delivery, profiles,
qualification and every order API.  It records exactly what the permitted
provider returned and marks the REST path as lower-frequency; a WebSocket
consumer may feed ``ingest_provider_packet`` without changing its evidence
format.
"""
from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import pytz
import structlog

from config import settings
from fno_instruments import FnoInstruments
from fno_models import Contract, OptionType
from fno_underlyings import SPECS, get_instruments_for
from research_archive import QuoteArchive, _iso

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")
_archive: Optional[QuoteArchive] = None
_last_collection_epoch: Optional[float] = None


def _configured_underlyings() -> List[str]:
    requested = [value.strip().upper() for value in settings.RESEARCH_ARCHIVE_UNDERLYINGS.split(",")]
    return [name for name in requested if name in SPECS and name in {"NIFTY", "SENSEX"}]


def _quote_archive() -> QuoteArchive:
    global _archive
    path = settings.RESEARCH_ARCHIVE_PATH
    if _archive is None or str(_archive.root) != path:
        _archive = QuoteArchive(path, max_queue=settings.RESEARCH_QUOTE_MAX_QUEUE,
                                reserved_free_bytes=settings.RESEARCH_RESERVED_FREE_BYTES)
    return _archive


def _provider_timestamp(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = IST.localize(value)
        return _iso(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = IST.localize(parsed)
        return _iso(parsed)
    except ValueError:
        return text  # preserve an unparseable provider value, never invent UTC


def _five_levels(levels: Any) -> List[Dict[str, Optional[int | float]]]:
    values: List[Dict[str, Optional[int | float]]] = []
    for raw in list(levels or [])[:5]:
        values.append({
            "price": float(raw["price"]) if raw.get("price") not in (None, "") else None,
            "quantity": int(raw["quantity"]) if raw.get("quantity") not in (None, "") else None,
            "orders": int(raw["orders"]) if raw.get("orders") not in (None, "") else None,
        })
    values.extend([{"price": None, "quantity": None, "orders": None}] * (5 - len(values)))
    return values


def normalise_quote(
    contract: Contract, quote: Mapping[str, Any], *, source: str, mode: str,
    received_at: Optional[datetime] = None, reconnect_epoch: int = 0,
    selection_reason: str, exchange: str = "UNKNOWN",
) -> Dict[str, Any]:
    """Create a replay-safe quote event without replacing absent depth."""
    received_at = received_at or datetime.now(timezone.utc)
    depth = quote.get("depth") or {}
    bids, asks = _five_levels(depth.get("buy")), _five_levels(depth.get("sell"))
    crossed = bool(bids[0]["price"] and asks[0]["price"] and bids[0]["price"] >= asks[0]["price"])
    missing_depth = bids[0]["price"] is None or asks[0]["price"] is None
    return {
        "source": source, "mode": mode, "reconnect_epoch": int(reconnect_epoch),
        "received_at_utc": _iso(received_at),
        "local_monotonic_ns": time.monotonic_ns(),
        "exchange_timestamp": _provider_timestamp(quote.get("exchange_timestamp")),
        "last_trade_time": _provider_timestamp(quote.get("last_trade_time")),
        "contract": {"exchange": exchange.upper(),
                     "underlying": contract.name, "tradingsymbol": contract.tradingsymbol,
                     "instrument_token": str(contract.token), "expiry": contract.expiry.isoformat(),
                     "strike": contract.strike, "instrument_type": contract.instrument_type,
                     "lot_size": contract.lot_size, "tick_size": contract.tick_size},
        "selection_reason": selection_reason,
        "ltp": float(quote.get("last_price") or 0.0), "oi": int(quote.get("oi") or 0),
        "volume": int(quote.get("volume") or 0), "buy_depth": bids, "sell_depth": asks,
        "missing_depth": missing_depth, "crossed_depth": crossed,
        "raw_sha256": __import__("hashlib").sha256(
            __import__("json").dumps(dict(quote), sort_keys=True, default=str, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def _select_contracts(book: FnoInstruments, forward: float, today, window: int) -> List[Tuple[Contract, str]]:
    selected: Dict[int, Tuple[Contract, str]] = {}
    future = book.front_future(today)
    if future:
        selected[future.token] = (future, "underlying_future_reference")
    expiries = [expiry for expiry in book.option_expiries if expiry >= today][:2]
    for expiry in expiries:
        for strike in book.strikes_window(forward, window):
            for option_type in (OptionType.CE, OptionType.PE):
                contract = book.option(expiry, strike, option_type)
                if contract:
                    selected[contract.token] = (contract, f"atm_window_expiry={expiry.isoformat()}")
    return list(selected.values())


async def collect_rest_quote_snapshot(
    kite, *, now_ist: Optional[datetime] = None,
    books: Optional[Mapping[str, FnoInstruments]] = None,
) -> Dict[str, Any]:
    """Collect a bounded REST full-quote snapshot for active research books.

    REST is deliberately recorded as ``KITE_REST_FULL_LOWER_FREQUENCY``.  It
    is not presented as tick/depth history and all unavailable packets become
    explicit gaps in the result rather than synthetic quotes.
    """
    now_ist = now_ist or datetime.now(IST)
    result: Dict[str, Any] = {"collected": 0, "requested": 0, "gaps": [], "mode": "KITE_REST_FULL_LOWER_FREQUENCY"}
    if not settings.RESEARCH_ARCHIVE_ENABLED or not settings.RESEARCH_QUOTE_COLLECTION_ENABLED:
        result["reason"] = "disabled"
        return result
    if not getattr(kite, "access_token", None):
        result["reason"] = "no_market_data_token"
        return result
    archive = _quote_archive()
    archive.finalize_prior_days(now_ist.astimezone(IST).date().isoformat())
    books = books or {name: get_instruments_for(name) for name in _configured_underlyings()}
    for name in _configured_underlyings():
        book = books.get(name)
        if book is None or not book.ready(now_ist.date()):
            result["gaps"].append({"underlying": name, "reason": "fresh_contract_master_unavailable"})
            continue
        future = book.front_future(now_ist.date())
        if future is None:
            result["gaps"].append({"underlying": name, "reason": "front_future_unavailable"})
            continue
        future_data = await kite.get_quote([future.token])
        future_quote = future_data.get(future.token) if future_data else None
        forward = float((future_quote or {}).get("last_price") or 0.0)
        if forward <= 0:
            result["gaps"].append({"underlying": name, "reason": "future_quote_unavailable", "token": future.token})
            continue
        selected = _select_contracts(book, forward, now_ist.date(), settings.RESEARCH_QUOTE_STRIKE_WINDOW)
        tokens = [contract.token for contract, _ in selected]
        result["requested"] += len(tokens)
        data = await kite.get_quote(tokens)
        # Receipt time is deliberately captured after the provider call, not
        # from the scheduler tick's start.  It is evidence timing, never an
        # advisory validity clock.
        batch_received_at = datetime.now(IST)
        if not data:
            result["gaps"].append({"underlying": name, "reason": "quote_batch_empty", "tokens": len(tokens)})
            continue
        for contract, reason in selected:
            quote = data.get(contract.token)
            if quote is None:
                result["gaps"].append({"underlying": name, "reason": "contract_packet_missing", "token": contract.token})
                continue
            event = normalise_quote(contract, quote, source="KITE", mode=result["mode"],
                                    received_at=batch_received_at, selection_reason=reason,
                                    exchange=SPECS[name].segment)
            archive.append(event)
            result["collected"] += 1
    return result


async def research_quote_collection_tick(now_ist: Optional[datetime] = None) -> Dict[str, Any]:
    """Scheduler entry point; market-data only and independent of advice gates."""
    now_ist = now_ist or datetime.now(IST)
    if not settings.RESEARCH_QUOTE_COLLECTION_ENABLED:
        return {"reason": "disabled"}
    if now_ist.weekday() > 4 or (now_ist.hour, now_ist.minute) < (9, 15) or (now_ist.hour, now_ist.minute) > (15, 30):
        return {"reason": "outside_weekday_session"}
    import main as _main
    if not await _main.is_trading_day(now_ist.date(), settings.DB_PATH):
        return {"reason": "market_closed"}
    return await collect_rest_quote_snapshot(_main.kite, now_ist=now_ist)
