"""
[MOMENTUM-PAPER 2026-07-26] A paper twin of the live momentum book.

WHY THIS EXISTS
---------------
Live momentum entry is manual: the screener sends a Telegram EXEC button and a
human decides. The ledger therefore records what the *operator* did, never what
the *strategy* proposed -- 8 recorded momentum trades in months of running, which
is why nothing can be concluded about the strategy from them. A signal that fired
at 11:04 while nobody was looking left no trace at all.

This book takes EVERY accepted momentum signal automatically, sizes it off its
own pool, manages it with the same pure exit logic the live book uses, and books
cost-adjusted P&L to source='MOMENTUM_PAPER'. The result is a record of the
strategy's own decisions, which is the thing the promotion ladder actually needs.

It matters now in particular because MOMENTUM_MIN_STOP_PCT just changed the stop,
the position size and the R distribution simultaneously, and that cannot be
evaluated on roughly two manual trades a month.

SAFETY
------
This module contains NO order-placing code. Not a disabled branch, not a flag
that must stay False -- there is no call to place_order, no square-off endpoint,
no executor import anywhere in the file. The only outbound call is a read-only
LTP fetch, injected as `ltp_fn` so tests never touch the network.

That is deliberate. The 2026-07-21..24 incident was a book placing real orders it
was never meant to place, and the cheapest way to guarantee that cannot happen
here is to leave the capability out of the module entirely.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, time, timedelta, timezone
from typing import Awaitable, Callable, Optional
from zoneinfo import ZoneInfo

import aiosqlite
from momentum_path_envelope import verify_path_quote_envelope
import structlog

from config import settings
from engine import calc_zerodha_costs, resolve_momentum_regime_params
from models import Regime
from momentum_exits import (
    ACTION_EXIT, ACTION_SCALE_OUT, ACTION_TRAIL,
    evaluate_momentum_exit, momentum_exit_status,
)

logger = structlog.get_logger()

SOURCE = "MOMENTUM_PAPER"
_ADMISSION_OUTCOMES_TABLE = "momentum_paper_admission_outcomes"
_ADMISSION_OUTCOMES = frozenset({
    "opened",
    "already_held",
    "zero_shares",
    "disabled",
    "upstream_deduplicated",
    "transaction_failure",
})
_ADMISSION_PACKET_MAX_BYTES = 4096
_PATH_SUBSCRIPTIONS_TABLE = "momentum_paper_path_subscriptions"
_PATH_OBSERVATIONS_TABLE = "momentum_paper_path_observations"
_IST = ZoneInfo("Asia/Kolkata")

# Fills are modelled at the quoted price with real Zerodha costs applied on top.
# No slippage model: intraday MIS on liquid NSE names fills close to the quote,
# and inventing a slippage number would make the paper book look precise about
# something it is guessing at. Costs are NOT optional -- a cost-free paper book
# would report the exact optimism this system has already been burned by.
LtpFn = Callable[[str], Awaitable[Optional[float]]]


def paper_position_size(close: float, stop_loss: float, pool: float,
                        risk_pct: float,
                        available_capital: Optional[float] = None) -> int:
    """Shares for the paper book, using the live sizing rule at paper scale.

    Mirrors engine.evaluate_momentum_signal: risk a fixed fraction of the pool,
    divided by per-share risk, then cap so one position cannot exceed the pool.
    Sized from the PAPER pool rather than copying the live share count, because
    copying would just reproduce the Rs 2,500 pool's 0-1 share positions, where
    tick size and costs swamp whatever edge the signal has.
    """
    if close <= 0 or stop_loss <= 0 or pool <= 0:
        return 0
    risk_per_share = close - stop_loss
    if risk_per_share <= 0:
        return 0
    shares = math.floor((pool * risk_pct) / risk_per_share)
    # Risk remains a fraction of the strategy pool, while deployable notional
    # is capped by capital that is not already tied up in another open paper
    # position.  Without this fence every accepted signal was independently
    # allowed to spend the entire pool.
    capital_cap = pool if available_capital is None else min(
        pool, max(0.0, float(available_capital))
    )
    if shares * close > capital_cap:
        shares = math.floor(capital_cap / close)
    return max(0, shares)


def _sig_get(sig, key, default=None):
    """Accepted signals arrive as dicts or pydantic models depending on caller."""
    if sig is None:
        return default
    if isinstance(sig, dict):
        return sig.get(key, default)
    return getattr(sig, key, default)


def _sqlite_safe(value):
    """Coerce a value into something sqlite3 can bind.

    [PAPER-REGIME 2026-08-04] This book had recorded ZERO trades since it was
    built on 2026-07-26. Every single open raised

        Error binding parameter 15: type 'Regime' is not supported

    because `regime` on an accepted signal is a pydantic enum, not a string.
    The live path never hit it -- there the regime arrives already serialised
    through node-gateway's sync payload -- so only the paper book, the one
    component whose entire purpose is generating strategy evidence, was
    silently producing none. Five signals were lost to it on 2026-08-04 alone.

    The failure was logged at error level and wrapped in a try/except so it
    could not break the live scan, which is correct behaviour and also exactly
    why it survived: a loud log nobody greps for is a silent failure.
    """
    if value is None or isinstance(value, (str, int, float, bytes)):
        return value
    # Enum -> its value (Regime.REGIME_1_NORMAL -> "REGIME_1_NORMAL")
    inner = getattr(value, "value", None)
    if isinstance(inner, (str, int, float)):
        return inner
    return str(value)


def _paper_risk_pct(sig) -> float:
    """Resolve the same regime risk fraction used by the live evaluator.

    Old/manual signal shapes may not carry a regime.  Preserve their historical
    paper sizing through ``MOMENTUM_RISK_PCT`` rather than guessing a regime.
    """
    raw = _sig_get(sig, "regime")
    if raw is None:
        return float(settings.MOMENTUM_RISK_PCT)
    try:
        regime = raw if isinstance(raw, Regime) else Regime(str(raw))
    except (TypeError, ValueError):
        logger.warning(
            "momentum_paper_unknown_regime regime=%r fallback=legacy", raw
        )
        return float(settings.MOMENTUM_RISK_PCT)
    _target, risk_pct, should_block = resolve_momentum_regime_params(regime)
    return 0.0 if should_block else float(risk_pct)


def _admission_signal_key(sig, now_utc: datetime) -> tuple[str, str]:
    """Return an opaque, deterministic identity for one accepted signal.

    Admission evidence needs to distinguish a genuinely changed signal from a
    duplicate scan, but must not persist the full strategy payload.  The hash
    is computed from the small set of decision inputs that can alter a paper
    admission, plus the UTC trading date.  Only the digest and ticker are
    retained in SQLite.
    """
    ticker = str(_sig_get(sig, "ticker", "") or "").strip().upper()
    identity = {
        "ticker": ticker,
        "date": now_utc.date().isoformat(),
        "close": _sqlite_safe(_sig_get(sig, "close")),
        "stop_loss": _sqlite_safe(_sig_get(sig, "stop_loss")),
        "target_1": _sqlite_safe(_sig_get(sig, "target_1")),
        "target_2": _sqlite_safe(_sig_get(sig, "target_2")),
        "regime": _sqlite_safe(_sig_get(sig, "regime")),
        "bar_ts": _sqlite_safe(_sig_get(sig, "bar_ts")),
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest(), ticker


def _admission_source_packet(sig, now_utc: datetime) -> tuple[str | None, str | None]:
    """Return the bounded canonical bytes receipt for an accepted signal.

    This is deliberately not a second market-data fetch.  It seals the exact
    decision inputs already supplied by the screener, so an offline reader can
    recompute the hash from the persisted packet bytes instead of trusting a
    claimed hash string.
    """
    packet = {
        "schema": "momentum_paper_admission_packet_v1",
        "received_at": now_utc.astimezone(timezone.utc).isoformat(),
        "ticker": str(_sig_get(sig, "ticker", "") or "").strip().upper(),
        "close": _sqlite_safe(_sig_get(sig, "close")),
        "stop_loss": _sqlite_safe(_sig_get(sig, "stop_loss")),
        "target_1": _sqlite_safe(_sig_get(sig, "target_1")),
        "target_2": _sqlite_safe(_sig_get(sig, "target_2")),
        "atr_at_entry": _sqlite_safe(_sig_get(sig, "atr_at_entry")),
        "vwap": _sqlite_safe(_sig_get(sig, "vwap")),
        "regime": _sqlite_safe(_sig_get(sig, "regime")),
        "bar_ts": _sqlite_safe(_sig_get(sig, "bar_ts")),
    }
    try:
        raw = json.dumps(packet, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        return None, None
    if len(raw) > _ADMISSION_PACKET_MAX_BYTES:
        return None, None
    return raw.decode("utf-8"), f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _zero_share_reason(close: float, stop: float, pool: float, risk_pct: float,
                       available_capital: float) -> str:
    """Explain a retained ``zero_shares`` result without changing its meaning."""
    if not all(math.isfinite(value) for value in (close, stop, pool, risk_pct)):
        return "invalid_input"
    if close <= 0 or stop <= 0 or pool <= 0 or risk_pct <= 0 or stop >= close:
        return "invalid_input"
    if available_capital < close:
        return "capital_exhausted"
    if math.floor((pool * risk_pct) / (close - stop)) < 1:
        return "risk_budget_below_one_share"
    # A finite, valid input can only reach this branch through a cap/rounding
    # boundary.  Keep it explicit rather than relabelling an old outcome.
    return "allocation_rounding"


async def _realised_paper_cash_basis(db, pool: float) -> float:
    """Read prior realised paper P&L; sizing remains the configured fixed pool."""
    try:
        row = await (await db.execute(
            "SELECT COALESCE(SUM(pnl), 0) FROM bankroll_ledger WHERE source=? "
            "AND event_type IN ('TRADE_PARTIAL','TRADE_CLOSED')", (SOURCE,),
        )).fetchone()
        return pool + float(row[0] or 0.0)
    except Exception:
        # A legacy/minimal fixture can lack the ledger.  Do not turn evidence
        # enrichment into an admission failure; label the basis unavailable.
        return float("nan")


def _admission_economics(*, pool: float, deployed: float, risk_pct: float,
                         close: float, stop: float, shares: int,
                         realised_cash_basis: float, source_packet_sha256: str | None) -> dict:
    available = max(0.0, pool - deployed)
    return {
        "schema": "momentum_paper_admission_economics_v1",
        "sizing_benchmark_pool_inr": pool,
        "sizing_benchmark_label": "FIXED_CONFIGURED_PAPER_POOL_NOT_DRAWDOWN_ADJUSTED",
        "realised_paper_cash_basis_inr": realised_cash_basis if math.isfinite(realised_cash_basis) else None,
        "deployed_notional_inr": deployed,
        "reserved_notional_inr": 0.0,
        "available_notional_inr": available,
        "risk_pct": risk_pct,
        "risk_budget_inr": pool * risk_pct,
        "allocation_policy_version": "MOMENTUM_PAPER_FIXED_POOL_V1",
        "entry_price": close,
        "stop_loss": stop,
        "requested_shares": shares,
        "requested_notional_inr": shares * close,
        "fees_basis": "broker_costs_applied_on_realised_legs_not_admission_capital",
        "source_packet_sha256": source_packet_sha256,
    }


async def _init_admission_outcomes(db) -> None:
    await db.execute(f"""
        CREATE TABLE IF NOT EXISTS {_ADMISSION_OUTCOMES_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admission_key TEXT NOT NULL UNIQUE,
            signal_key TEXT NOT NULL,
            ticker TEXT NOT NULL,
            outcome TEXT NOT NULL CHECK(outcome IN (
                'opened', 'already_held', 'zero_shares', 'disabled',
                'upstream_deduplicated', 'transaction_failure'
            )),
            reason TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        )
    """)
    columns = {row[1] for row in await (await db.execute(
        f"PRAGMA table_info({_ADMISSION_OUTCOMES_TABLE})"
    )).fetchall()}
    if "entry_economics_json" not in columns:
        await db.execute(
            f"ALTER TABLE {_ADMISSION_OUTCOMES_TABLE} ADD COLUMN entry_economics_json TEXT"
        )
    if "admission_economics_json" not in columns:
        await db.execute(
            f"ALTER TABLE {_ADMISSION_OUTCOMES_TABLE} ADD COLUMN admission_economics_json TEXT"
        )
    if "source_packet_json" not in columns:
        await db.execute(
            f"ALTER TABLE {_ADMISSION_OUTCOMES_TABLE} ADD COLUMN source_packet_json TEXT"
        )
    if "source_packet_sha256" not in columns:
        await db.execute(
            f"ALTER TABLE {_ADMISSION_OUTCOMES_TABLE} ADD COLUMN source_packet_sha256 TEXT"
        )
    await db.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{_ADMISSION_OUTCOMES_TABLE}_recorded "
        f"ON {_ADMISSION_OUTCOMES_TABLE}(recorded_at DESC)"
    )
    await db.commit()


async def _init_path_collector(db) -> None:
    """Create additive passive-path tables; this performs no market I/O."""
    await db.execute(f"""
        CREATE TABLE IF NOT EXISTS {_PATH_SUBSCRIPTIONS_TABLE} (
            admission_key TEXT PRIMARY KEY,
            ticker TEXT NOT NULL,
            entry_at TEXT NOT NULL,
            study_deadline_at TEXT NOT NULL,
            original_shares INTEGER NOT NULL CHECK(original_shares > 0),
            created_at TEXT NOT NULL
        )
    """)
    await db.execute(f"""
        CREATE TABLE IF NOT EXISTS {_PATH_OBSERVATIONS_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admission_key TEXT NOT NULL,
            ticker TEXT NOT NULL,
            provider_observed_at TEXT NOT NULL,
            receipt_at TEXT NOT NULL,
            ltp REAL NOT NULL CHECK(ltp > 0),
            deadline_observation INTEGER NOT NULL CHECK(deadline_observation IN (0, 1)),
            source_packet BLOB NOT NULL,
            source_packet_sha256 TEXT NOT NULL,
            UNIQUE(admission_key, provider_observed_at, source_packet_sha256)
        )
    """)
    await db.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{_PATH_OBSERVATIONS_TABLE}_key_clock "
        f"ON {_PATH_OBSERVATIONS_TABLE}(admission_key, provider_observed_at)"
    )


def _study_deadline_utc(entry_at: datetime) -> datetime:
    local = entry_at.astimezone(_IST)
    return datetime.combine(local.date(), time(15, 15), tzinfo=_IST).astimezone(timezone.utc)


async def _subscribe_paper_path(db, admission_key: str, ticker: str, entry_at: datetime,
                                original_shares: int) -> None:
    await _init_path_collector(db)
    deadline = _study_deadline_utc(entry_at)
    await db.execute(
        f"INSERT OR IGNORE INTO {_PATH_SUBSCRIPTIONS_TABLE} "
        "(admission_key,ticker,entry_at,study_deadline_at,original_shares,created_at) "
        "VALUES (?,?,?,?,?,?)",
        (admission_key, ticker, entry_at.astimezone(timezone.utc).isoformat(),
         deadline.isoformat(), original_shares, entry_at.astimezone(timezone.utc).isoformat()),
    )


def _parse_observation_clock(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a timezone-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a timezone-aware ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware ISO timestamp")
    return parsed.astimezone(timezone.utc)


def active_paper_path_tickers(db_path: str, now_utc: datetime, *, limit: int) -> list[str]:
    """Tickers whose passive path is still collecting (read-only, bounded).

    A subscription stays active from entry until the declared gap past its
    15:15 IST study deadline, so the closing observation can be captured.
    """
    import sqlite3
    from pathlib import Path
    path = Path(db_path)
    if limit < 1 or not path.is_file():
        return []
    gap = max(1, min(300, int(settings.MOMENTUM_PAPER_PATH_MAX_GAP_SECONDS)))
    now_utc = now_utc.astimezone(timezone.utc)
    try:
        con = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=1.0)
    except sqlite3.Error:
        return []
    try:
        rows = con.execute(
            f"SELECT DISTINCT ticker FROM {_PATH_SUBSCRIPTIONS_TABLE} "
            "WHERE entry_at<=? AND study_deadline_at>=? ORDER BY ticker LIMIT ?",
            (now_utc.isoformat(), (now_utc - timedelta(seconds=gap)).isoformat(), int(limit)),
        ).fetchall()
    except sqlite3.Error:
        return []  # schema not yet created: nothing is subscribed
    finally:
        con.close()
    return [str(row[0]) for row in rows]


async def record_momentum_paper_path_observations(db_path: str, observations: list[dict]) -> int:
    """Persist caller-supplied quote receipts for subscribed paper paths.

    The caller must pass the exact provider packet bytes and both provider and
    local receipt clocks.  This function has no LTP callback and imports no
    HTTP client, making it impossible for admission, exits, or evidence capture
    to create a provider request.  Invalid/missing packets are rejected as
    unavailable evidence, never replaced with inferred prices.
    """
    if not observations:
        return 0
    written = 0
    try:
        async with aiosqlite.connect(db_path) as db:
            await _init_path_collector(db)
            await db.execute("BEGIN IMMEDIATE")
            packet_cap = max(1, int(settings.MOMENTUM_PAPER_PATH_PACKET_MAX_BYTES))
            max_gap = max(1, min(300, int(settings.MOMENTUM_PAPER_PATH_MAX_GAP_SECONDS)))
            for raw in observations:
                try:
                    if not isinstance(raw, dict):
                        raise ValueError("observation must be an object")
                    ticker = str(raw.get("ticker") or "").strip().upper()
                    ltp = float(raw.get("ltp"))
                    if not ticker or not math.isfinite(ltp) or ltp <= 0:
                        raise ValueError("ticker and positive finite ltp are required")
                    provider_at = _parse_observation_clock(raw.get("provider_observed_at"), "provider_observed_at")
                    receipt_at = _parse_observation_clock(raw.get("receipt_at"), "receipt_at")
                    if receipt_at < provider_at:
                        raise ValueError("receipt_at cannot precede provider_observed_at")
                    packet = raw.get("source_packet")
                    if not isinstance(packet, bytes) or not packet or len(packet) > packet_cap:
                        raise ValueError("source_packet must be bounded non-empty bytes")
                    # Columns must be derived from the bytes, not merely
                    # accompany them (typed envelope; S4 review correction).
                    verify_path_quote_envelope(packet, ticker=ticker, ltp=ltp,
                                               provider_observed_at=provider_at)
                    packet_hash = f"sha256:{hashlib.sha256(packet).hexdigest()}"
                except (TypeError, ValueError, OverflowError):
                    logger.warning("momentum_paper_path_observation_rejected")
                    continue
                # The closing observation may arrive just after 15:15; keep
                # observations up to the declared gap past the deadline.
                closing_window = provider_at - timedelta(seconds=max_gap)
                rows = await (await db.execute(
                    f"SELECT admission_key,study_deadline_at FROM {_PATH_SUBSCRIPTIONS_TABLE} "
                    "WHERE ticker=? AND entry_at<=? AND study_deadline_at>=?",
                    (ticker, provider_at.isoformat(), closing_window.isoformat()),
                )).fetchall()
                for admission_key, deadline_raw in rows:
                    deadline = _parse_observation_clock(deadline_raw, "study_deadline_at")
                    cur = await db.execute(
                        f"INSERT OR IGNORE INTO {_PATH_OBSERVATIONS_TABLE} "
                        "(admission_key,ticker,provider_observed_at,receipt_at,ltp,deadline_observation,"
                        "source_packet,source_packet_sha256) VALUES (?,?,?,?,?,?,?,?)",
                        (admission_key, ticker, provider_at.isoformat(), receipt_at.isoformat(), ltp,
                         int(provider_at >= deadline), packet, packet_hash),
                    )
                    written += int(cur.rowcount)
            retention = max(1, int(settings.MOMENTUM_PAPER_PATH_RETENTION))
            await db.execute(
                f"DELETE FROM {_PATH_OBSERVATIONS_TABLE} WHERE id IN ("
                f"SELECT id FROM {_PATH_OBSERVATIONS_TABLE} ORDER BY id DESC LIMIT -1 OFFSET ?)",
                (retention,),
            )
            await db.commit()
    except Exception as exc:
        logger.error("momentum_paper_path_observation_failed err=%s", str(exc), exc_info=True)
        return 0
    return written


async def _record_admission_outcome(
    db, admission_key: str, signal_key: str, ticker: str, outcome: str,
    now_utc: datetime, *, reason: Optional[str] = None,
    entry_economics: Optional[dict] = None, admission_economics: Optional[dict] = None,
    source_packet_json: Optional[str] = None, source_packet_sha256: Optional[str] = None,
) -> bool:
    """Insert one immutable outcome, returning whether it was newly recorded."""
    if outcome not in _ADMISSION_OUTCOMES:
        raise ValueError(f"unsupported momentum-paper admission outcome: {outcome}")
    def _encode_evidence(value: Optional[dict]) -> Optional[str]:
        if value is None:
            return None
        try:
            candidate = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
            if len(candidate) <= 4096:
                return candidate
        except (ValueError, TypeError):
            # Invalid evidence must not change paper admission authority.
            # A missing snapshot makes the offline review unavailable.
            pass
        return None
    encoded_economics = _encode_evidence(entry_economics)
    encoded_admission = _encode_evidence(admission_economics)
    if source_packet_json is not None and len(source_packet_json.encode("utf-8")) > _ADMISSION_PACKET_MAX_BYTES:
        source_packet_json, source_packet_sha256 = None, None
    cur = await db.execute(
        f"INSERT OR IGNORE INTO {_ADMISSION_OUTCOMES_TABLE} "
        "(admission_key, signal_key, ticker, outcome, reason, recorded_at, entry_economics_json, "
        "admission_economics_json, source_packet_json, source_packet_sha256) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (admission_key, signal_key, ticker, outcome, reason or outcome, now_utc.isoformat(),
         encoded_economics, encoded_admission, source_packet_json, source_packet_sha256),
    )
    return bool(cur.rowcount)


async def _bound_admission_outcomes(db) -> None:
    retention = max(1, int(settings.MOMENTUM_PAPER_ADMISSION_RETENTION))
    await db.execute(
        f"DELETE FROM {_ADMISSION_OUTCOMES_TABLE} WHERE id IN ("
        f"SELECT id FROM {_ADMISSION_OUTCOMES_TABLE} "
        "ORDER BY id DESC LIMIT -1 OFFSET ?)",
        (retention,),
    )


async def _supports_paper_admission_identity(db) -> bool:
    """Whether this connection has received the additive position migration.

    Main startup applies the migration before paper admission.  Keeping this
    small probe lets isolated legacy fixtures retain their established paper
    bookkeeping behavior while making their missing lineage visible to the
    Phase-2 audit instead of failing the strategy path.
    """
    rows = await (await db.execute("PRAGMA table_info(positions)")).fetchall()
    return any(str(row[1]) == "paper_admission_key" for row in rows)


async def record_momentum_paper_upstream_deduplications(
    db_path: str, signals: list, now_utc: Optional[datetime] = None,
) -> int:
    """Durably record accepted signals suppressed before the paper opener.

    This function is called at the alert-deduplication boundary in ``main``.
    It intentionally says ``upstream_deduplicated`` rather than pretending the
    paper book evaluated or rejected an input it never received.
    """
    if not signals:
        return 0
    now_utc = now_utc or datetime.now(timezone.utc)
    written = 0
    try:
        async with aiosqlite.connect(db_path) as db:
            await _init_admission_outcomes(db)
            await db.execute("BEGIN IMMEDIATE")
            for sig in signals:
                signal_key, ticker = _admission_signal_key(sig, now_utc)
                if not ticker:
                    logger.warning("momentum_paper_admission_skip reason=missing_ticker")
                    continue
                written += int(await _record_admission_outcome(
                    db, f"upstream:{signal_key}", signal_key, ticker,
                    "upstream_deduplicated", now_utc,
                ))
            await _bound_admission_outcomes(db)
            await db.commit()
    except Exception as exc:
        logger.error(
            "momentum_paper_upstream_dedup_record_failed err=%s", str(exc),
            exc_info=True,
        )
        return 0
    return written


async def _record_disabled_admissions(
    db_path: str, candidates: list[tuple[str, str]], now_utc: datetime,
) -> None:
    """Best-effort durable evidence for a deliberately disabled paper book."""
    if not candidates:
        return
    try:
        async with aiosqlite.connect(db_path) as db:
            await _init_admission_outcomes(db)
            await db.execute("BEGIN IMMEDIATE")
            for signal_key, ticker in candidates:
                await _record_admission_outcome(
                    db, f"disabled:{signal_key}", signal_key, ticker,
                    "disabled", now_utc,
                )
            await _bound_admission_outcomes(db)
            await db.commit()
    except Exception as exc:
        logger.error(
            "momentum_paper_disabled_record_failed err=%s", str(exc),
            exc_info=True,
        )


async def _record_transaction_failures(
    db_path: str, candidates: list[tuple[str, str, str]], now_utc: datetime,
) -> None:
    """Record a rolled-back admission failure when the evidence DB permits.

    If SQLite itself is unavailable this cannot manufacture durable evidence;
    the outer caller logs the failure and returns no opened ticker.  When a
    position mutation fails after the admission table exists, a fresh short
    transaction preserves the truthful ``transaction_failure`` result.
    """
    if not candidates:
        return
    try:
        async with aiosqlite.connect(db_path) as db:
            await _init_admission_outcomes(db)
            await db.execute("BEGIN IMMEDIATE")
            for admission_key, signal_key, ticker in candidates:
                await _record_admission_outcome(
                    db, admission_key, signal_key, ticker,
                    "transaction_failure", now_utc,
                )
            await _bound_admission_outcomes(db)
            await db.commit()
    except Exception as exc:
        logger.error(
            "momentum_paper_admission_failure_record_failed err=%s", str(exc),
            exc_info=True,
        )


async def open_momentum_paper_positions(db_path: str, accepted: list,
                                        now_utc: Optional[datetime] = None) -> list:
    """Open a paper position for each accepted signal not already held today.

    Returns the list of opened tickers. Never raises into the screener: a paper
    bookkeeping failure must not take down the live scan that produced the signal.
    """
    if not accepted:
        return []

    now_utc = now_utc or datetime.now(timezone.utc)
    candidates = []
    for sig in accepted:
        candidate = _admission_signal_key(sig, now_utc)
        if candidate[1]:
            candidates.append(candidate)
    if not settings.MOMENTUM_PAPER_ENABLED:
        # Feature disablement is a real outcome, not an invisible empty list.
        # This helper remains paper-only and never touches a broker/order path.
        await _record_disabled_admissions(db_path, candidates, now_utc)
        return []

    pool = float(settings.MOMENTUM_PAPER_BANKROLL)
    opened = []
    attempted: list[tuple[str, str, str]] = []

    try:
        async with aiosqlite.connect(db_path) as db:
            await _init_admission_outcomes(db)
            # Serialize capital allocation within this SQLite book.  The
            # scheduler normally calls this once, but BEGIN IMMEDIATE also
            # prevents overlapping scans from both observing the same cash.
            await db.execute("BEGIN IMMEDIATE")
            has_admission_identity = await _supports_paper_admission_identity(db)
            async with db.execute(
                "SELECT ticker,entry_price,shares FROM positions "
                "WHERE source=? AND exit_date IS NULL",
                (SOURCE,),
            ) as cur:
                open_rows = await cur.fetchall()
                held = {str(r[0] or "").strip().upper() for r in open_rows}
                deployed = sum(
                    max(0.0, float(r[1] or 0)) * max(0, int(r[2] or 0))
                    for r in open_rows
                )
            realised_cash_basis = await _realised_paper_cash_basis(db, pool)

            for sig in accepted:
                signal_key, ticker = _admission_signal_key(sig, now_utc)
                if not ticker:
                    logger.warning("momentum_paper_admission_skip reason=missing_ticker")
                    continue
                admission_key = f"entry:{signal_key}"
                source_packet_json, source_packet_sha256 = _admission_source_packet(sig, now_utc)
                async with db.execute(
                    f"SELECT outcome FROM {_ADMISSION_OUTCOMES_TABLE} "
                    "WHERE admission_key=?",
                    (admission_key,),
                ) as cur:
                    prior = await cur.fetchone()
                # Preserve the established reopen-after-close contract. A
                # committed former opening is not a current position; assign a
                # new immutable attempt key rather than overwriting history.
                if prior is not None and prior[0] == "opened" and ticker not in held:
                    async with db.execute(
                        f"SELECT COUNT(*) FROM {_ADMISSION_OUTCOMES_TABLE} "
                        "WHERE signal_key=? AND outcome='opened'",
                        (signal_key,),
                    ) as cur:
                        reopen_number = int((await cur.fetchone())[0]) + 1
                    admission_key = f"entry:{signal_key}:reopen:{reopen_number}"
                    prior = None
                if prior is not None:
                    # The same accepted decision was already accounted for.
                    # Preserve the public return contract: repeat calls never
                    # report a prior committed opening as a new opening.
                    continue
                attempted.append((admission_key, signal_key, ticker))
                close = float(_sig_get(sig, "close", 0) or 0)
                stop = float(_sig_get(sig, "stop_loss", 0) or 0)
                risk_pct = _paper_risk_pct(sig)
                available_capital = max(0.0, pool - deployed)
                if ticker in held:
                    await _record_admission_outcome(
                        db, admission_key, signal_key, ticker, "already_held", now_utc,
                        reason="ticker_already_open",
                        admission_economics=_admission_economics(
                            pool=pool, deployed=deployed, risk_pct=risk_pct, close=close,
                            stop=stop, shares=0, realised_cash_basis=realised_cash_basis,
                            source_packet_sha256=source_packet_sha256,
                        ), source_packet_json=source_packet_json,
                        source_packet_sha256=source_packet_sha256,
                    )
                    continue
                shares = paper_position_size(
                    close, stop, pool, risk_pct, available_capital=available_capital,
                )
                if shares < 1:
                    logger.info("momentum_paper_skip ticker=%s reason=zero_shares "
                                "close=%s stop=%s", ticker, close, stop)
                    await _record_admission_outcome(
                        db, admission_key, signal_key, ticker, "zero_shares", now_utc,
                        reason=_zero_share_reason(close, stop, pool, risk_pct, available_capital),
                        admission_economics=_admission_economics(
                            pool=pool, deployed=deployed, risk_pct=risk_pct, close=close,
                            stop=stop, shares=0, realised_cash_basis=realised_cash_basis,
                            source_packet_sha256=source_packet_sha256,
                        ), source_packet_json=source_packet_json,
                        source_packet_sha256=source_packet_sha256,
                    )
                    continue

                columns = (
                    "ticker, exchange, entry_date, entry_price, shares, "
                    "stop_loss_initial, trailing_stop_current, target_1, target_2, "
                    "atr_14_at_entry, highest_close_since_entry, status, source, "
                    "product_type, regime_at_entry, t1_fired, vwap_at_entry, "
                    "initial_capital_at_risk"
                )
                values = [
                    ticker, "NSE", now_utc.isoformat(), close, shares, stop, stop,
                    _sqlite_safe(_sig_get(sig, "target_1")),
                    _sqlite_safe(_sig_get(sig, "target_2")),
                    _sqlite_safe(_sig_get(sig, "atr_at_entry")), close, "OPEN", SOURCE,
                    "MIS", _sqlite_safe(_sig_get(sig, "regime")), 0,
                    _sqlite_safe(_sig_get(sig, "vwap")), (close - stop) * shares,
                ]
                if has_admission_identity:
                    columns += ", paper_admission_key"
                    values.append(admission_key)
                await db.execute(
                    f"INSERT INTO positions ({columns}) VALUES ({','.join('?' for _ in values)})",
                    values,
                )
                # Register the accepted opportunity for passive evidence before
                # any later scale-out can reduce the position's live share
                # count.  Registration itself fetches no quote and does not
                # alter the paper exit path.
                await _subscribe_paper_path(db, admission_key, ticker, now_utc, shares)
                held.add(ticker)
                deployed += shares * close
                opened.append(ticker)
                await _record_admission_outcome(
                    db, admission_key, signal_key, ticker, "opened", now_utc,
                    entry_economics={
                        "schema": "momentum_paper_entry_economics_v1",
                        "ticker": ticker,
                        "entry_at": now_utc.astimezone(timezone.utc).isoformat(),
                        "entry_price": close, "shares": shares,
                        "stop_loss_initial": stop, "target_1": values[7],
                        "atr_14_at_entry": values[9], "vwap_at_entry": values[16],
                        "regime_at_entry": values[14],
                        "initial_capital_at_risk": (close - stop) * shares,
                    },
                    admission_economics=_admission_economics(
                        pool=pool, deployed=deployed - (shares * close), risk_pct=risk_pct,
                        close=close, stop=stop, shares=shares,
                        realised_cash_basis=realised_cash_basis,
                        source_packet_sha256=source_packet_sha256,
                    ), source_packet_json=source_packet_json,
                    source_packet_sha256=source_packet_sha256,
                )
                logger.info(
                    "momentum_paper_opened ticker=%s shares=%d entry=%.2f stop=%.2f "
                    "notional=%.0f pool=%.0f", ticker, shares, close, stop,
                    shares * close, pool,
                )
            await _bound_admission_outcomes(db)
            await db.commit()
    except Exception as exc:
        logger.error("momentum_paper_open_failed err=%s", str(exc), exc_info=True)
        # The single transaction rolls every INSERT back. Never report tickers
        # from the in-memory list as opened when none were committed.
        await _record_transaction_failures(db_path, attempted, now_utc)
        return []

    return opened


async def _close_paper_position(db, db_path: str, pos: dict, exit_price: float,
                                status: str, reason: str) -> Optional[float]:
    """Persist the close, then book cost-adjusted P&L. Returns realised P&L.

    Same rowcount discipline as the live path (see auto_square_momentum): the
    ledger is only written when a position row actually closed. A close that
    matched nothing must never book P&L -- that is precisely how four sessions of
    fabricated losses got into the real ledger.
    """
    from performance import record_trade_close

    entry = float(pos["entry_price"])
    shares = int(pos["shares"])
    gross = (exit_price - entry) * shares
    costs = calc_zerodha_costs(entry, exit_price, shares, is_intraday=True)
    realised = gross - costs
    previous_realised = float(pos.get("realised_pnl") or 0.0)
    total_realised = previous_realised + realised
    risk_initial = float(pos.get("initial_capital_at_risk") or 0.0)
    if risk_initial <= 0:
        # Legacy rows predate the immutable denominator. They could not have
        # scaled out before that feature existed, so current shares are safe.
        risk_initial = (
            entry - float(pos["stop_loss_initial"])
        ) * shares
    r_multiple = total_realised / risk_initial if risk_initial > 0 else 0.0

    # The row and the single closed outcome carry whole-trade P&L/R. The ledger
    # remains leg-based (TRADE_PARTIAL plus the runner's TRADE_CLOSED), so its
    # sum equals this aggregate without double-booking cash equity.
    cur = await db.execute(
        "UPDATE positions SET status=?, exit_price=?, exit_date=?, "
        "       realised_pnl=?, r_multiple=? "
        "WHERE ticker=? AND source=? AND exit_date IS NULL",
        (status, exit_price, datetime.now(timezone.utc).isoformat(),
         total_realised, r_multiple, pos["ticker"], SOURCE),
    )
    await db.commit()
    if cur.rowcount != 1:
        logger.error("momentum_paper_close_not_persisted ticker=%s rows=%d",
                     pos["ticker"], cur.rowcount)
        return None

    await record_trade_close(db_path, pos["ticker"], realised,
                            r_multiple=r_multiple, notes=f"paper:{reason}",
                            outcome_pnl=total_realised,
                            outcome_r_multiple=r_multiple,
                            source=SOURCE,
                            origin_ref=pos.get("paper_admission_key"))
    logger.info("momentum_paper_closed ticker=%s exit=%.2f pnl=%.2f r=%.2f reason=%s",
                pos["ticker"], exit_price, total_realised, r_multiple, reason)
    return total_realised


async def momentum_paper_monitor(db_path: str, ltp_fn: LtpFn,
                                 now_ist: datetime) -> dict:
    """Evaluate stops/targets/trails on open paper positions.

    Reuses evaluate_momentum_exit -- the same pure decision function the live book
    uses -- so the paper record reflects the live exit policy rather than a
    parallel one that could quietly drift.
    """
    if not settings.MOMENTUM_PAPER_ENABLED:
        return {"checked": 0, "exited": [], "trailed": [], "scaled": []}

    exited, trailed, scaled = [], [], []
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM positions WHERE source=? AND exit_date IS NULL",
                (SOURCE,),
            ) as cur:
                positions = [dict(r) for r in await cur.fetchall()]

            for pos in positions:
                ltp = await ltp_fn(pos["ticker"])
                if not ltp or ltp <= 0:
                    continue
                decision = evaluate_momentum_exit(pos, float(ltp), now_ist)
                action = decision.get("action")
                if action == ACTION_EXIT:
                    status = momentum_exit_status(decision.get("reason", ""))
                    pnl = await _close_paper_position(
                        db, db_path, pos, float(ltp), status,
                        decision.get("reason", "exit"),
                    )
                    if pnl is not None:
                        exited.append((pos["ticker"], round(pnl, 2)))
                elif action == ACTION_SCALE_OUT:
                    # [SCALE-OUT 2026-08-04] The paper book has to take the
                    # partial too. Its whole purpose is to record what the
                    # STRATEGY decided rather than what the operator did, and a
                    # paper book that exits all-or-nothing while the live book
                    # scales out is measuring a strategy nobody is running.
                    #
                    # No broker leg to sequence here, so this is just the
                    # bookkeeping half of the live path: shares down, stop up,
                    # t1_fired set, P&L on the shares sold.
                    sold = int(decision["scale_shares"])
                    runner = int(pos["shares"]) - sold
                    gross = (float(ltp) - pos["entry_price"]) * sold
                    costs = calc_zerodha_costs(
                        pos["entry_price"], float(ltp), sold, is_intraday=True,
                    )
                    pnl = gross - costs
                    cur = await db.execute(
                        "UPDATE positions SET shares=?, trailing_stop_current=?, "
                        "t1_fired=1, realised_pnl=COALESCE(realised_pnl, 0) + ? "
                        "WHERE ticker=? AND source=? AND exit_date IS NULL AND t1_fired=0",
                        (runner, float(decision["new_stop"]), pnl,
                         pos["ticker"], SOURCE),
                    )
                    if cur.rowcount != 1:
                        # Another monitor/close won the race after our snapshot.
                        # Never write a partial ledger event unless this call
                        # actually consumed the t1_fired=0 state transition.
                        await db.rollback()
                        logger.warning(
                            "momentum_paper_scale_not_persisted ticker=%s rows=%d",
                            pos["ticker"], cur.rowcount,
                        )
                        continue
                    await db.commit()
                    from performance import record_partial_realisation
                    await record_partial_realisation(
                        db_path,
                        pos["ticker"],
                        pnl,
                        source=SOURCE,
                        notes=f"momentum_scale_out {decision['reason']}",
                        origin_ref=pos.get("paper_admission_key"),
                    )
                    scaled.append((pos["ticker"], round(pnl, 2)))

                elif action == ACTION_TRAIL and decision.get("new_stop"):
                    await db.execute(
                        "UPDATE positions SET trailing_stop_current=? "
                        "WHERE ticker=? AND source=? AND exit_date IS NULL",
                        (float(decision["new_stop"]), pos["ticker"], SOURCE),
                    )
                    await db.commit()
                    trailed.append(pos["ticker"])
    except Exception as exc:
        logger.error("momentum_paper_monitor_failed err=%s", str(exc), exc_info=True)

    return {
        "checked": len(exited) + len(trailed) + len(scaled),
        "exited": exited, "trailed": trailed, "scaled": scaled,
    }


async def momentum_paper_square_off(db_path: str, ltp_fn: LtpFn,
                                    now_ist: datetime) -> list:
    """15:15 IST: flatten every open paper position, mirroring the live MIS book.

    Momentum is intraday, so nothing may be carried overnight -- otherwise the
    paper record would show a strategy the live book cannot run.
    """
    if not settings.MOMENTUM_PAPER_ENABLED:
        return []

    closed = []
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM positions WHERE source=? AND exit_date IS NULL",
                (SOURCE,),
            ) as cur:
                positions = [dict(r) for r in await cur.fetchall()]

            for pos in positions:
                ltp = await ltp_fn(pos["ticker"])
                if not ltp or ltp <= 0:
                    # No quote: fall back to the entry price so the position is
                    # still flattened. Carrying it would misreport an intraday
                    # strategy as holding overnight.
                    ltp = float(pos["entry_price"])
                    logger.warning("momentum_paper_squareoff_no_quote ticker=%s "
                                   "using_entry_price", pos["ticker"])
                pnl = await _close_paper_position(
                    db, db_path, pos, float(ltp), "CLOSED_TIME", "eod_square_off",
                )
                if pnl is not None:
                    closed.append((pos["ticker"], round(pnl, 2)))
    except Exception as exc:
        logger.error("momentum_paper_squareoff_failed err=%s", str(exc), exc_info=True)

    if closed:
        logger.info("momentum_paper_squared_off n=%d total_pnl=%.2f",
                    len(closed), sum(p for _, p in closed))
    return closed
