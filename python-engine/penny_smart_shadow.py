"""Durable broker-free smart Penny paper twin, using existing scanner inputs.

Separate tables and virtual allocation; cannot reserve actual capital or order.
The existing stop-monitor cadence observes at most three held paper symbols in
one quote batch. No extra historical fetch, subscription or scheduler job.
"""

from dataclasses import asdict
import asyncio
from datetime import datetime, timedelta
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import aiosqlite
from adaptive_penny_policy import CompletedBar, TraderParams
from penny_shadow import _execution_snapshot, _costs_from_snapshot
from penny_smart_book import new_book, step_book
from penny_smart_policy import SMART_PARAMS, SMART_VERSION, visible_bars

IST = ZoneInfo("Asia/Kolkata")


def smart_db_path(ledger_path):
    """A separate store prevents shadow write locks on the operational ledger."""
    return str(ledger_path) + ".penny-smart-paper.db"


@lru_cache(maxsize=1)
def _policy_digest():
    root = Path(__file__).resolve().parent
    return {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in (
            "penny_smart_policy.py",
            "penny_smart_book.py",
            "adaptive_penny_policy.py",
            "penny_prices.py",
        )
    }


def completed_frame(frame, now):
    """Only valid completed current-session bars; malformed input is unavailable."""
    bars = []
    values = frame[["open", "high", "low", "close", "volume"]].itertuples(index=False, name=None)
    for ts, row in zip(frame.index, values):
        stamp = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
        stamp = stamp.replace(tzinfo=IST) if stamp.tzinfo is None else stamp.astimezone(IST)
        if stamp.date() != now.date() or stamp + timedelta(minutes=1) > now:
            continue
        bars.append(
            CompletedBar(
                stamp.isoformat(),
                stamp,
                stamp + timedelta(minutes=1),
                *(float(value) for value in row)
            )
        )
    return bars


def quote_evidence(raw, now):
    """No fill from an absent/stale quote, one-sided depth or a crossed market."""
    try:
        stamp = raw["timestamp"]
        if isinstance(stamp, str):
            stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=IST)
        age = (now - stamp).total_seconds()
        depth = raw["depth"]
        ask = float(depth["sell"][0]["price"])
        bid = float(depth["buy"][0]["price"])
        if (
            not 0 <= age <= 60
            or not all(math.isfinite(p) for p in (bid, ask))
            or not 0 < bid <= ask
        ):
            raise ValueError("unusable quote")
        sizes = [float(depth[side][0]["quantity"]) for side in ("sell", "buy")]
        if not all(math.isfinite(size) and size >= 1 for size in sizes):
            raise ValueError("empty depth")
        size = int(min(sizes))
        if size < 1:
            raise ValueError("no whole-share depth")
        return {
            "entry": ask,
            "exit": bid,
            "executable": True,
            "quote_at": stamp.isoformat(),
            "max_quantity": size,
        }
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, OverflowError):
        return {"executable": False, "reason": "quote_timestamp_or_depth_unavailable"}


async def _schema(db):
    await db.execute(
        "CREATE TABLE IF NOT EXISTS penny_smart_paper_state (policy TEXT PRIMARY KEY, state_json TEXT NOT NULL)"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS penny_smart_paper_events (event_id TEXT PRIMARY KEY, policy TEXT NOT NULL, at TEXT NOT NULL, ticker TEXT NOT NULL, kind TEXT NOT NULL, payload_json TEXT NOT NULL)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_penny_smart_events_clock ON penny_smart_paper_events(policy,at)"
    )


def _convert_observations(observations, now):
    converted = {}
    invalid = []
    for ticker, obs in observations.items():
        try:
            bars = completed_frame(obs["frame"], now)
            visible_bars(bars, now)
            converted[ticker] = {"bars": bars, "median_volume": obs["median_volume"]}
        except (ValueError, KeyError, TypeError, AttributeError):
            invalid.append(ticker)
    return converted, invalid


def _exit_observations(state, observations, now):
    """Use an archived quote sample only after its minute has finished.

    This is explicitly a sampled bid close, never fabricated candle OHLC.
    It keeps thesis management working when entry scans no longer fetch bars.
    Missing minutes are not filled. Prefer an actual completed candle.
    """
    result = dict(observations)
    for ticker in state["positions"]:
        sample = state.get("quote_samples", {}).get(ticker)
        if not sample:
            continue
        observed = datetime.fromisoformat(sample["at"])
        available = observed.replace(second=0, microsecond=0) + timedelta(minutes=1)
        if observed.date() != now.date() or not 0 <= (now - available).total_seconds() < 60:
            continue
        existing = result.get(ticker, {}).get("bars", [])
        if existing and existing[-1].available_at >= available:
            continue
        price = sample["price"]
        bar = CompletedBar(
            "sampled_bid:" + available.isoformat(),
            observed,
            available,
            price,
            price,
            price,
            price,
            0.0,
        )
        result[ticker] = {
            "bars": [bar],
            "median_volume": 0.0,
            "entry_allowed": False,
            "exit_observation_source": "SAMPLED_BID_CLOSE",
        }
    return result


async def observe_smart_shadow(
    db_path,
    observations,
    raw_quotes,
    *,
    now,
    bankroll=2000.0,
    allow_entries=True,
    stock_cap=500.0,
    max_positions=3
):
    """One atomic paper transition, deduplicated across concurrent/restarted jobs."""
    now = now.replace(tzinfo=IST) if now.tzinfo is None else now.astimezone(IST)
    converted, invalid = await asyncio.to_thread(_convert_observations, observations, now)
    quotes = {ticker: quote_evidence(raw, now) for ticker, raw in raw_quotes.items()}
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        await _schema(db)
        await db.execute("BEGIN IMMEDIATE")
        row = await (
            await db.execute(
                "SELECT state_json FROM penny_smart_paper_state WHERE policy=?", (SMART_VERSION,)
            )
        ).fetchone()
        state = (
            json.loads(row[0])
            if row
            else new_book(now.date().isoformat(), bankroll, _execution_snapshot("SMART_PAPER"))
        )
        binding = {
            "bankroll": bankroll,
            "stock_cap": stock_cap,
            "max_positions": max_positions,
            "params": asdict(SMART_PARAMS),
            "execution": _execution_snapshot("SMART_PAPER"),
            "policy_sha256": _policy_digest(),
        }
        frozen = state.get("binding", binding)
        state["binding"] = frozen
        drift = frozen != binding
        # Closed prior sessions can start a new allocation; unresolved exposure
        # is managed before any rollover. The event archive retains prior days.
        if state["day"] != now.date().isoformat() and not state["positions"]:
            equity = state["bankroll"] + state["realized"]
            if equity > 0:
                state = new_book(now.date().isoformat(), equity, state["execution"])
                state["binding"] = frozen
            # No daily refill or configuration change supplies new capital.
        params = TraderParams(**frozen["params"])
        cost = lambda e, x, q: _costs_from_snapshot(e, x, q, state["execution"])
        converted = _exit_observations(state, converted, now)
        updated, events = await asyncio.to_thread(
            step_book,
            state,
            converted,
            quotes,
            now=now,
            cost=cost,
            allow_entries=allow_entries and not drift,
            stock_cap=frozen["stock_cap"],
            max_positions=frozen["max_positions"],
            params=params,
        )
        samples = {
            t: s for t, s in state.get("quote_samples", {}).items() if t in updated["positions"]
        }
        for ticker in updated["positions"]:
            q = quotes.get(ticker, {})
            if q.get("executable") and (
                ticker not in samples or q["quote_at"] > samples[ticker]["at"]
            ):
                samples[ticker] = {"at": q["quote_at"], "price": q["exit"]}
        updated["quote_samples"] = samples
        for ticker in invalid:
            events.append(
                {
                    "at": now.isoformat(),
                    "kind": "OBSERVATION_UNAVAILABLE",
                    "ticker": ticker,
                    "reason": "invalid_frame",
                }
            )
        for event in events:
            payload = json.dumps(event, sort_keys=True, allow_nan=False)
            key = hashlib.sha256((SMART_VERSION + payload).encode()).hexdigest()
            await db.execute(
                "INSERT OR IGNORE INTO penny_smart_paper_events VALUES (?,?,?,?,?,?)",
                (key, SMART_VERSION, event["at"], event["ticker"], event["kind"], payload),
            )
        await db.execute(
            "INSERT OR REPLACE INTO penny_smart_paper_state VALUES (?,?)",
            (SMART_VERSION, json.dumps(updated, sort_keys=True, allow_nan=False)),
        )
        await db.commit()
    return {
        "policy": SMART_VERSION,
        "events": len(events),
        "open": len(updated["positions"]),
        "realized": updated["realized"],
        "invalid_observations": invalid,
        "configuration_drift": drift,
        "can_place_orders": False,
    }


async def monitor_smart_shadow(db_path, kite, *, now):
    """Bounded quote-only exit observation; independent of all entry brakes."""
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        await _schema(db)
        row = await (
            await db.execute(
                "SELECT state_json FROM penny_smart_paper_state WHERE policy=?", (SMART_VERSION,)
            )
        ).fetchone()
        await db.commit()
    if not row:
        return {"checked": 0, "can_place_orders": False}
    state = json.loads(row[0])
    tickers = list(state["positions"])
    if not tickers:
        return {"checked": 0, "can_place_orders": False}
    # A corrupted/oversized state must not turn into an unbounded provider job.
    if len(tickers) > 3:
        raise ValueError("smart shadow exceeds hard three-position observation bound")
    tokens = {t: getattr(kite, "instrument_cache", {}).get(t) for t in tickers}
    requested = [int(v) for v in tokens.values() if v is not None]
    batch = await kite.get_quote(requested) if requested else {}
    raw = {t: batch.get(int(token), {}) for t, token in tokens.items() if token is not None}
    frozen = state["binding"]
    return await observe_smart_shadow(
        db_path,
        {},
        raw,
        now=datetime.now(IST),
        allow_entries=False,
        bankroll=frozen["bankroll"],
        stock_cap=frozen["stock_cap"],
        max_positions=frozen["max_positions"],
    )
