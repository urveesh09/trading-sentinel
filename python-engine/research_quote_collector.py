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
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import pytz
import structlog

from config import settings
from fno_instruments import FnoInstruments
from fno_models import Contract, OptionType
from fno_underlyings import SPECS, get_instruments_for
from research_archive import QuoteArchive, _iso
from research_leg_subscriptions import ActiveLeg, ResearchLegSubscriptionStore

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")
_archive: Optional[QuoteArchive] = None
_last_collection_epoch: Optional[float] = None


def _configured_underlyings() -> List[str]:
    requested = [value.strip().upper() for value in settings.RESEARCH_ARCHIVE_UNDERLYINGS.split(",")]
    return [name for name in requested if name in SPECS and name in {"NIFTY", "SENSEX"}]


def _fair_collection_order(now_ist: datetime) -> List[str]:
    """Rotate the first underlying per scheduled slot, including after restart.

    A process-local toggle would reset after every deploy/restart and could
    repeatedly starve the same index when a first provider request times out.
    The UTC scheduler-slot number gives every process the same deterministic
    NIFTY/SENSEX order without adding mutable operational state.
    """
    names = _configured_underlyings()
    if len(names) < 2:
        return names
    if now_ist.tzinfo is None or now_ist.utcoffset() is None:
        now_ist = IST.localize(now_ist)
    interval = max(1, int(settings.RESEARCH_QUOTE_INTERVAL_SEC))
    slot = int(now_ist.astimezone(timezone.utc).timestamp()) // interval
    offset = slot % len(names)
    return names[offset:] + names[:offset]


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


def _with_active_legs(selected: Sequence[Tuple[Contract, str]], active: Sequence[ActiveLeg]) -> List[Tuple[Contract, str]]:
    """Union rolling discovery with exact retained legs without substitution."""
    merged: Dict[int, Tuple[Contract, str]] = {contract.token: (contract, reason) for contract, reason in selected}
    for leg in active:
        prior = merged.get(leg.contract.token)
        reason = f"active_selected_leg decision={leg.decision_id}"
        if prior is not None:
            reason = prior[1] + ";" + reason
        merged[leg.contract.token] = (leg.contract, reason)
    return list(merged.values())


async def _documented_quotes(kite, contracts: Sequence[Contract], segment: str) -> Mapping[int, Mapping[str, Any]]:
    """Prefer documented exchange:symbol lookup; retain fake/legacy support."""
    request = {contract.token: f"{segment}:{contract.tradingsymbol}" for contract in contracts}
    if hasattr(kite, "get_quote_by_instruments"):
        return await kite.get_quote_by_instruments(request)
    return await kite.get_quote(list(request))


class _ProviderDeadlineExceeded(TimeoutError):
    """A single provider operation consumed the remaining collection budget."""


async def _bounded_documented_quotes(
    kite,
    contracts: Sequence[Contract],
    segment: str,
    *,
    remaining_runtime_sec: Optional[Callable[[], float]],
) -> Mapping[int, Mapping[str, Any]]:
    """Await one quote operation, cancelling it at the tick's remaining budget.

    ``asyncio.wait_for`` cancels *and waits for* the provider coroutine; this
    is intentional.  It is not a detached background timeout, so a stalled
    HTTP/rate-limiter operation cannot continue using the shared Kite client
    after a later collection slot begins.  Direct/offline callers retain the
    former unbounded helper behaviour by passing ``None``.
    """
    operation = _documented_quotes(kite, contracts, segment)
    if remaining_runtime_sec is None:
        return await operation
    remaining = float(remaining_runtime_sec())
    if not math.isfinite(remaining) or remaining <= 0:
        # The coroutine has not been awaited yet.  Close it explicitly before
        # raising, otherwise Python emits an un-awaited-coroutine warning.
        operation.close()
        raise _ProviderDeadlineExceeded("no collection runtime remains")
    try:
        return await asyncio.wait_for(operation, timeout=remaining)
    except asyncio.TimeoutError as exc:
        raise _ProviderDeadlineExceeded("provider quote exceeded collection runtime") from exc


def _index_coverage() -> Dict[str, Any]:
    """Return the complete, explicitly empty coverage shape for one index."""
    return {
        "requested_tokens": [], "received_tokens": [],
        "active_leg_requested_tokens": [], "active_leg_received_tokens": [],
        "active_leg_capacity_shortfall_tokens": [], "collection_state": "not_started",
    }


async def collect_rest_quote_snapshot(
    kite, *, now_ist: Optional[datetime] = None,
    books: Optional[Mapping[str, FnoInstruments]] = None,
    runtime_exceeded: Optional[Callable[[], bool]] = None,
    remaining_runtime_sec: Optional[Callable[[], float]] = None,
    mark_runtime_capped: Optional[Callable[[], None]] = None,
    partial_collected_ref: Optional[Dict[str, int]] = None,
    result_telemetry: Optional[Callable[[Dict[str, Any]], None]] = None,
    underlying_order: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Collect a bounded REST full-quote snapshot for active research books.

    REST is deliberately recorded as ``KITE_REST_FULL_LOWER_FREQUENCY``.  It
    is not presented as tick/depth history and all unavailable packets become
    explicit gaps in the result rather than synthetic quotes.

    [WORKFLOW-C.F2 2026-09-16] Defensive runtime cap.
    ``runtime_exceeded`` is an optional callable invoked before each
    underlying. ``remaining_runtime_sec`` is the stronger scheduler contract:
    every provider request is cancelled at the remaining tick budget.  A
    capped result records the current and every later underlying as an
    unobserved gap; it never fabricates a stale packet or pretends a selected
    active leg was received. ``None`` retains the direct/offline legacy path.
    """
    now_ist = now_ist or datetime.now(IST)
    # Local no-op defaults so the cap-discipline is testable
    # in isolation -- ``runtime_exceeded`` always returns
    # False when not provided.
    if runtime_exceeded is None:
        runtime_exceeded = lambda: False
    if partial_collected_ref is None:
        partial_collected_ref = {"n": 0}
    partial_collected_ref["n"] = 0
    underlyings = list(underlying_order) if underlying_order is not None else _configured_underlyings()
    result: Dict[str, Any] = {
        "collected": 0, "requested": 0, "partial_collected": 0,
        "partial_count": 0, "gaps": [], "indices": {},
        "mode": "KITE_REST_FULL_LOWER_FREQUENCY", "underlying_order": underlyings,
        "stage_durations_sec": {},
    }

    def _annotate_result() -> None:
        result["partial_collected"] = partial_collected_ref["n"]
        result["partial_count"] = partial_collected_ref["n"]
        if result_telemetry is not None:
            result_telemetry(result)

    async def _journal_result() -> None:
        """Persist the exact final result used by the scheduler caller."""
        _annotate_result()
        stage_started = time.monotonic()
        await asyncio.to_thread(
            archive.record_collection_run, result,
            expected_interval_sec=settings.RESEARCH_QUOTE_INTERVAL_SEC,
        )
        result["stage_durations_sec"]["archive_journal"] = round(
            time.monotonic() - stage_started, 6,
        )

    def _mark_deadline_skips(underlyings: Sequence[str], start: int) -> None:
        """Make every not-started index and active-leg coverage gap auditable."""
        for skipped_name in underlyings[start:]:
            index = result["indices"].setdefault(skipped_name, _index_coverage())
            index["collection_state"] = "skipped_runtime_deadline"
            result["gaps"].append({
                "underlying": skipped_name,
                "reason": "underlying_skipped_runtime_deadline",
            })
            # No subscription read is attempted after the deadline: reporting
            # a specific token then would be fabricated.  The named gap makes
            # that unknown active-leg coverage explicit instead.
            result["gaps"].append({
                "underlying": skipped_name,
                "reason": "active_leg_coverage_unobserved_runtime_deadline",
            })

    def _mark_current_active_unobserved(name: str, active_tokens: set[int]) -> None:
        if active_tokens:
            result["gaps"].extend({
                "underlying": name,
                "reason": "active_leg_unobserved_runtime_deadline",
                "token": token,
            } for token in sorted(active_tokens))
        else:
            result["gaps"].append({
                "underlying": name,
                "reason": "active_leg_coverage_unobserved_runtime_deadline",
            })

    if not settings.RESEARCH_ARCHIVE_ENABLED or not settings.RESEARCH_QUOTE_COLLECTION_ENABLED:
        result["reason"] = "disabled"
        _annotate_result()
        return result
    archive = _quote_archive()
    subscriptions = ResearchLegSubscriptionStore(getattr(archive, "root", settings.RESEARCH_ARCHIVE_PATH))
    # This is cheap, bounded SQLite housekeeping run out of the event loop.
    # A terminal row remains retained for the configured evidence window.
    result["selected_leg_retention"] = await asyncio.to_thread(
        subscriptions.finalize, now=now_ist, evidence_retention_days=settings.RESEARCH_COMPRESSED_RETENTION_DAYS,
    )
    if not getattr(kite, "access_token", None):
        result["reason"] = "no_market_data_token"
        await _journal_result()
        return result
    stage_started = time.monotonic()
    await asyncio.to_thread(archive.finalize_prior_days, now_ist.astimezone(IST).date().isoformat())
    result["stage_durations_sec"]["archive_finalization"] = round(time.monotonic() - stage_started, 6)
    books = books or {name: get_instruments_for(name) for name in underlyings}
    for underlying_index, name in enumerate(underlyings):
        # [WORKFLOW-C.F2 2026-09-16] Cap check at the start
        # of each underlying's iteration. If the tick has
        # already exceeded its runtime budget, break out
        # -- the partial result is still useful, and we
        # avoid cascade-skip at the scheduler.
        if runtime_exceeded():
            _mark_deadline_skips(underlyings, underlying_index)
            break
        result["indices"][name] = _index_coverage()
        result["indices"][name]["collection_state"] = "started"
        active, capacity_shortfall = await asyncio.to_thread(
            subscriptions.active, underlying=name, now=now_ist,
            capacity=settings.RESEARCH_ACTIVE_LEG_MAX_TOKENS,
        )
        active_tokens = {leg.contract.token for leg in active}
        result["indices"][name]["active_leg_requested_tokens"] = sorted(active_tokens)
        result["indices"][name]["active_leg_capacity_shortfall_tokens"] = sorted(
            leg.contract.token for leg in capacity_shortfall
        )
        if capacity_shortfall:
            result["gaps"].extend({"underlying": name, "reason": "active_leg_capacity_shortfall",
                                   "token": leg.contract.token, "decision_id": leg.decision_id}
                                  for leg in capacity_shortfall)
        rolling_selected: List[Tuple[Contract, str]] = []
        try:
            book = books.get(name)
            if book is None or not book.ready(now_ist.date()):
                result["gaps"].append({"underlying": name, "reason": "fresh_contract_master_unavailable"})
            else:
                future = book.front_future(now_ist.date())
                if future is None:
                    result["gaps"].append({"underlying": name, "reason": "front_future_unavailable"})
                else:
                    stage_started = time.monotonic()
                    future_data = await _bounded_documented_quotes(
                        kite, [future], SPECS[name].segment,
                        remaining_runtime_sec=remaining_runtime_sec,
                    )
                    result["stage_durations_sec"]["provider_quote"] = round(result["stage_durations_sec"].get("provider_quote", 0) + time.monotonic() - stage_started, 6)
                    future_quote = future_data.get(future.token) if future_data else None
                    packet_token = future_quote.get("instrument_token") if isinstance(future_quote, Mapping) else None
                    forward = _finite_positive((future_quote or {}).get("last_price"), float)
                    if packet_token not in (None, "", future.token, str(future.token)) or forward is None:
                        result["gaps"].append({"underlying": name, "reason": "future_reference_invalid", "token": future.token})
                    else:
                        rolling_selected = _select_contracts(book, float(forward), now_ist.date(), settings.RESEARCH_QUOTE_STRIKE_WINDOW)
        except _ProviderDeadlineExceeded:
            if mark_runtime_capped is not None:
                mark_runtime_capped()
            result["indices"][name]["collection_state"] = "provider_deadline_exceeded"
            result["gaps"].append({"underlying": name, "reason": "provider_deadline_exceeded",
                                   "stage": "future_reference", "token": future.token})
            _mark_current_active_unobserved(name, active_tokens)
            _mark_deadline_skips(underlyings, underlying_index + 1)
            break
        except Exception as exc:
            result["gaps"].append({"underlying": name, "reason": "future_reference_exception", "error_type": type(exc).__name__})
        try:
            # Active decisions survive a missing/changed rolling universe.
            selected = _with_active_legs(rolling_selected, active)
            if not selected:
                await asyncio.to_thread(subscriptions.record_collection, requested_tokens=active_tokens,
                                        received_tokens=(), now=now_ist, capacity_shortfall=capacity_shortfall)
                result["indices"][name]["collection_state"] = "completed_no_selectable_contracts"
                continue
            tokens = [contract.token for contract, _ in selected]
            result["indices"][name]["requested_tokens"] = tokens
            result["requested"] += len(tokens)
            stage_started = time.monotonic()
            data = await _bounded_documented_quotes(
                kite, [contract for contract, _ in selected], SPECS[name].segment,
                remaining_runtime_sec=remaining_runtime_sec,
            )
            result["stage_durations_sec"]["provider_quote"] = round(result["stage_durations_sec"].get("provider_quote", 0) + time.monotonic() - stage_started, 6)
            if not isinstance(data, Mapping):
                raise ValueError("quote batch must be a mapping")
        except _ProviderDeadlineExceeded:
            if mark_runtime_capped is not None:
                mark_runtime_capped()
            result["indices"][name]["collection_state"] = "provider_deadline_exceeded"
            result["gaps"].append({"underlying": name, "reason": "provider_deadline_exceeded",
                                   "stage": "quote_batch", "tokens": len(tokens)})
            _mark_current_active_unobserved(name, active_tokens)
            _mark_deadline_skips(underlyings, underlying_index + 1)
            break
        except Exception as exc:
            result["gaps"].append({"underlying": name, "reason": "quote_batch_exception", "error_type": type(exc).__name__})
            result["indices"][name]["collection_state"] = "quote_batch_exception"
            await asyncio.to_thread(subscriptions.record_collection, requested_tokens=active_tokens,
                                    received_tokens=(), now=now_ist, capacity_shortfall=capacity_shortfall)
            continue
        # Receipt time is deliberately captured after the provider call, not
        # from the scheduler tick's start.  It is evidence timing, never an
        # advisory validity clock.
        batch_received_at = datetime.now(IST)
        if not data:
            result["gaps"].append({"underlying": name, "reason": "quote_batch_empty", "tokens": len(tokens)})
            result["indices"][name]["collection_state"] = "completed_empty_batch"
            await asyncio.to_thread(subscriptions.record_collection, requested_tokens=active_tokens,
                                    received_tokens=(), now=batch_received_at,
                                    capacity_shortfall=capacity_shortfall)
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
                partial_collected_ref["n"] += 1
            except OSError as exc:
                logger.error("research_storage_stop reason=%s", str(exc))
                result["reason"] = "storage_stop"
                result["gaps"].append({"underlying": name, "reason": "storage_stop"})
                result["indices"][name]["collection_state"] = "storage_stop"
                await _journal_result()
                return result
            except Exception as exc:
                result["gaps"].append({"underlying": name, "reason": "packet_normalisation_exception", "token": contract.token, "error_type": type(exc).__name__})
        received_active = active_tokens.intersection(result["indices"][name]["received_tokens"])
        result["indices"][name]["active_leg_received_tokens"] = sorted(received_active)
        await asyncio.to_thread(subscriptions.record_collection, requested_tokens=active_tokens,
                                received_tokens=received_active, now=batch_received_at,
                                capacity_shortfall=capacity_shortfall)
        if result["indices"][name]["collection_state"] == "started":
            result["indices"][name]["collection_state"] = "completed"
    await _journal_result()
    return result


async def research_quote_collection_tick(now_ist: Optional[datetime] = None) -> Dict[str, Any]:
    """Scheduler entry point; market-data only and independent of advice gates."""
    now_ist = now_ist or datetime.now(IST)
    archive = _quote_archive() if settings.RESEARCH_ARCHIVE_ENABLED else None
    # [WORKFLOW-C.F2 2026-09-16] Defensive runtime cap.
    # The 2026-09-16 production audit reported avg runtime 14s
    # but max runtime 114s on a 60s trigger -- the tail causes
    # ``MAX_INSTANCES`` skips at the scheduler. Per the user's
    # directive ("earn good and fast profit"): keep the 60s
    # cadence (fresh data is critical), but cap tail latency
    # so a slow tick no longer cascades into a skip.
    #
    # Every provider operation is bounded to the remaining cap, not merely the
    # boundary between NIFTY and SENSEX.  ``wait_for`` cancels and joins the
    # operation before this tick returns, preventing a hidden shared-client
    # request from surviving into the next scheduler slot.
    tick_started_at = time.monotonic()
    runtime_cap_sec = float(getattr(
        settings, "RESEARCH_QUOTE_RUNTIME_CAP_SEC", 48.0,
    ))
    runtime_capped = False
    partial_collected = 0
    tick_index = {"n": 0}  # mutable counter for the helper closure below

    def _runtime_exceeded() -> bool:
        nonlocal runtime_capped
        if _remaining_runtime_sec() <= 0:
            runtime_capped = True
            return True
        return False

    def _remaining_runtime_sec() -> float:
        nonlocal runtime_capped
        remaining = runtime_cap_sec - (time.monotonic() - tick_started_at)
        if remaining <= 0:
            runtime_capped = True
            return 0.0
        return remaining

    def _mark_runtime_capped() -> None:
        nonlocal runtime_capped
        runtime_capped = True

    def annotate_telemetry(result: Dict[str, Any]) -> None:
        # [WORKFLOW-C.F2 2026-09-16] Annotate the journal entry
        # with runtime-capped diagnostics so the audit's
        # ``SELECT * FROM research_runs WHERE runtime_capped``-
        # style query returns rows.
        nonlocal runtime_capped
        elapsed = round(time.monotonic() - tick_started_at, 6)
        if elapsed >= runtime_cap_sec:
            runtime_capped = True
        result["runtime_capped"] = runtime_capped
        result["elapsed_sec"] = elapsed
        result["runtime_cap_sec"] = runtime_cap_sec
        result["partial_collected"] = tick_index["n"]
        result["partial_count"] = tick_index["n"]

    async def journal(result: Dict[str, Any]) -> Dict[str, Any]:
        annotate_telemetry(result)
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
        return await collect_rest_quote_snapshot(
            _main.kite, now_ist=now_ist,
            runtime_exceeded=_runtime_exceeded,
            remaining_runtime_sec=_remaining_runtime_sec,
            mark_runtime_capped=_mark_runtime_capped,
            partial_collected_ref=tick_index,
            result_telemetry=annotate_telemetry,
            underlying_order=_fair_collection_order(now_ist),
        )
    except Exception as exc:
        await journal({"reason": "scheduler_exception", "error_type": type(exc).__name__})
        raise
