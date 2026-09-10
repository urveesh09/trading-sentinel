"""Forward-only NIFTY/SENSEX quote evidence collection.

This module is intentionally independent from partner delivery, profiles,
qualification and every order API.  It records exactly what the permitted
provider returned and marks the REST path as lower-frequency; a WebSocket
consumer may feed ``ingest_provider_packet`` without changing its evidence
format.
"""
from __future__ import annotations

from datetime import datetime, timezone
import asyncio
import hashlib
import json
import math
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
                                reserved_free_bytes=settings.RESEARCH_RESERVED_FREE_BYTES,
                                session_max_bytes=settings.RESEARCH_SESSION_MAX_BYTES)
    return _archive


def _provider_timestamp(value: Any) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return raw value, parsed UTC and an explicit parse failure."""
    if value is None or str(value).strip() == "":
        return None, None, None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = IST.localize(value)
        return value.isoformat(), _iso(value), None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = IST.localize(parsed)
        return text, _iso(parsed), None
    except ValueError:
        return text, None, "unparseable_provider_timestamp"


def _finite_positive(value: Any, cast) -> Optional[int | float]:
    try:
        parsed = cast(value)
        return parsed if math.isfinite(float(parsed)) and parsed > 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _five_levels(levels: Any) -> tuple[List[Dict[str, Optional[int | float]]], bool]:
    values: List[Dict[str, Optional[int | float]]] = []
    malformed = not isinstance(levels or [], list)
    for raw in list(levels or [])[:5] if isinstance(levels or [], list) else []:
        if not isinstance(raw, Mapping):
            malformed = True
            values.append({"price": None, "quantity": None, "orders": None})
            continue
        values.append({
            "price": _finite_positive(raw.get("price"), float),
            "quantity": _finite_positive(raw.get("quantity"), int),
            "orders": _finite_positive(raw.get("orders"), int),
        })
    values.extend([{"price": None, "quantity": None, "orders": None}] * (5 - len(values)))
    return values, malformed


def normalise_quote(
    contract: Contract, quote: Mapping[str, Any], *, source: str, mode: str,
    received_at: Optional[datetime] = None, reconnect_epoch: int = 0,
    selection_reason: str, exchange: str = "UNKNOWN",
) -> Dict[str, Any]:
    """Create a replay-safe quote event without replacing absent depth."""
    received_at = received_at or datetime.now(timezone.utc)
    depth = quote.get("depth") if isinstance(quote.get("depth"), Mapping) else {}
    bids, malformed_bids = _five_levels(depth.get("buy"))
    asks, malformed_asks = _five_levels(depth.get("sell"))
    bid_ok = bids[0]["price"] is not None and bids[0]["quantity"] is not None
    ask_ok = asks[0]["price"] is not None and asks[0]["quantity"] is not None
    crossed = bool(bid_ok and ask_ok and bids[0]["price"] > asks[0]["price"])
    locked = bool(bid_ok and ask_ok and bids[0]["price"] == asks[0]["price"])
    missing_depth = not (bid_ok and ask_ok)
    raw_timestamp, timestamp_utc, timestamp_error = _provider_timestamp(
        quote.get("timestamp") if mode.startswith("KITE_REST") else quote.get("exchange_timestamp")
    )
    raw_exchange, exchange_utc, exchange_error = _provider_timestamp(quote.get("exchange_timestamp"))
    return {
        "source": source, "mode": mode, "reconnect_epoch": int(reconnect_epoch),
        "received_at_utc": _iso(received_at),
        "local_monotonic_ns": time.monotonic_ns(),
        "provider_timestamp_raw": raw_timestamp, "provider_timestamp_utc": timestamp_utc,
        "provider_timestamp_parse_error": timestamp_error,
        "exchange_timestamp_raw": raw_exchange, "exchange_timestamp_utc": exchange_utc,
        "exchange_timestamp_parse_error": exchange_error,
        "last_trade_time": _provider_timestamp(quote.get("last_trade_time"))[1],
        "contract": {"exchange": exchange.upper(),
                     "underlying": contract.name, "tradingsymbol": contract.tradingsymbol,
                     "instrument_token": str(contract.token), "expiry": contract.expiry.isoformat(),
                     "strike": contract.strike, "instrument_type": contract.instrument_type,
                     "lot_size": contract.lot_size, "tick_size": contract.tick_size},
        "selection_reason": selection_reason,
        "ltp": _finite_positive(quote.get("last_price"), float) or 0.0,
        "oi": int(_finite_positive(quote.get("oi"), int) or 0),
        "volume": int(_finite_positive(quote.get("volume"), int) or 0),
        "buy_depth": bids, "sell_depth": asks, "missing_depth": missing_depth,
        "crossed_depth": crossed, "locked_depth": locked,
        "depth_state": "MALFORMED" if malformed_bids or malformed_asks else (
            "MISSING_OR_UNUSABLE" if missing_depth else "CROSSED" if crossed else "LOCKED" if locked else "USABLE"),
        "raw_packet": dict(quote),
        "raw_sha256": hashlib.sha256(json.dumps(dict(quote), sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest(),
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


async def _documented_quotes(kite, contracts: Sequence[Contract], segment: str) -> Mapping[int, Mapping[str, Any]]:
    """Prefer documented exchange:symbol lookup; retain fake/legacy support."""
    request = {contract.token: f"{segment}:{contract.tradingsymbol}" for contract in contracts}
    if hasattr(kite, "get_quote_by_instruments"):
        return await kite.get_quote_by_instruments(request)
    return await kite.get_quote(list(request))


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
    result: Dict[str, Any] = {"collected": 0, "requested": 0, "gaps": [], "indices": {},
                              "mode": "KITE_REST_FULL_LOWER_FREQUENCY", "stage_durations_sec": {}}
    if not settings.RESEARCH_ARCHIVE_ENABLED or not settings.RESEARCH_QUOTE_COLLECTION_ENABLED:
        result["reason"] = "disabled"
        return result
    archive = _quote_archive()
    if not getattr(kite, "access_token", None):
        result["reason"] = "no_market_data_token"
        await asyncio.to_thread(archive.record_collection_run, result, expected_interval_sec=settings.RESEARCH_QUOTE_INTERVAL_SEC)
        return result
    stage_started = time.monotonic()
    await asyncio.to_thread(archive.finalize_prior_days, now_ist.astimezone(IST).date().isoformat())
    result["stage_durations_sec"]["archive_finalization"] = round(time.monotonic() - stage_started, 6)
    books = books or {name: get_instruments_for(name) for name in _configured_underlyings()}
    for name in _configured_underlyings():
        result["indices"][name] = {"requested_tokens": [], "received_tokens": []}
        try:
            book = books.get(name)
            if book is None or not book.ready(now_ist.date()):
                result["gaps"].append({"underlying": name, "reason": "fresh_contract_master_unavailable"}); continue
            future = book.front_future(now_ist.date())
            if future is None:
                result["gaps"].append({"underlying": name, "reason": "front_future_unavailable"}); continue
            stage_started = time.monotonic()
            future_data = await _documented_quotes(kite, [future], SPECS[name].segment)
            result["stage_durations_sec"]["provider_quote"] = round(result["stage_durations_sec"].get("provider_quote", 0) + time.monotonic() - stage_started, 6)
            future_quote = future_data.get(future.token) if future_data else None
            packet_token = future_quote.get("instrument_token") if isinstance(future_quote, Mapping) else None
            forward = _finite_positive((future_quote or {}).get("last_price"), float)
            if packet_token not in (None, "", future.token, str(future.token)) or forward is None:
                result["gaps"].append({"underlying": name, "reason": "future_reference_invalid", "token": future.token}); continue
        except Exception as exc:
            result["gaps"].append({"underlying": name, "reason": "future_reference_exception", "error_type": type(exc).__name__}); continue
        try:
            selected = _select_contracts(book, float(forward), now_ist.date(), settings.RESEARCH_QUOTE_STRIKE_WINDOW)
            tokens = [contract.token for contract, _ in selected]
            result["indices"][name]["requested_tokens"] = tokens
            result["requested"] += len(tokens)
            stage_started = time.monotonic()
            data = await _documented_quotes(kite, [contract for contract, _ in selected], SPECS[name].segment)
            result["stage_durations_sec"]["provider_quote"] = round(result["stage_durations_sec"].get("provider_quote", 0) + time.monotonic() - stage_started, 6)
            if not isinstance(data, Mapping):
                raise ValueError("quote batch must be a mapping")
        except Exception as exc:
            result["gaps"].append({"underlying": name, "reason": "quote_batch_exception", "error_type": type(exc).__name__})
            continue
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
            packet_token = quote.get("instrument_token") if isinstance(quote, Mapping) else None
            if packet_token not in (None, "", contract.token, str(contract.token)):
                result["gaps"].append({"underlying": name, "reason": "returned_token_mismatch", "requested_token": contract.token, "returned_token": str(packet_token)})
                continue
            try:
                event = normalise_quote(contract, quote, source="KITE", mode=result["mode"], received_at=batch_received_at, selection_reason=reason, exchange=SPECS[name].segment)
                stage_started = time.monotonic()
                await asyncio.to_thread(archive.append, event)
                result["stage_durations_sec"]["archive_write"] = round(result["stage_durations_sec"].get("archive_write", 0) + time.monotonic() - stage_started, 6)
                result["collected"] += 1; result["indices"][name]["received_tokens"].append(contract.token)
            except OSError as exc:
                logger.error("research_storage_stop reason=%s", str(exc))
                result["reason"] = "storage_stop"
                result["gaps"].append({"underlying": name, "reason": "storage_stop"})
                return result
            except Exception as exc:
                result["gaps"].append({"underlying": name, "reason": "packet_normalisation_exception", "token": contract.token, "error_type": type(exc).__name__})
    stage_started = time.monotonic()
    await asyncio.to_thread(archive.record_collection_run, result, expected_interval_sec=settings.RESEARCH_QUOTE_INTERVAL_SEC)
    result["stage_durations_sec"]["archive_journal"] = round(time.monotonic() - stage_started, 6)
    return result


async def research_quote_collection_tick(now_ist: Optional[datetime] = None) -> Dict[str, Any]:
    """Scheduler entry point; market-data only and independent of advice gates."""
    now_ist = now_ist or datetime.now(IST)
    archive = _quote_archive() if settings.RESEARCH_ARCHIVE_ENABLED else None
    async def journal(result: Dict[str, Any]) -> Dict[str, Any]:
        if archive is not None:
            await asyncio.to_thread(archive.record_collection_run, result, expected_interval_sec=settings.RESEARCH_QUOTE_INTERVAL_SEC)
        return result
    if not settings.RESEARCH_QUOTE_COLLECTION_ENABLED:
        return await journal({"reason": "disabled"})
    if now_ist.weekday() > 4 or (now_ist.hour, now_ist.minute) < (9, 15) or (now_ist.hour, now_ist.minute) > (15, 30):
        return await journal({"reason": "outside_weekday_session"})
    try:
        import main as _main
        if not await _main.is_trading_day(now_ist.date(), settings.DB_PATH):
            return await journal({"reason": "market_closed"})
        return await collect_rest_quote_snapshot(_main.kite, now_ist=now_ist)
    except Exception as exc:
        await journal({"reason": "scheduler_exception", "error_type": type(exc).__name__})
        raise
