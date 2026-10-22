"""Durable broker-free smart Penny paper twin, using existing scanner inputs.

Separate tables and virtual allocation; cannot reserve actual capital or order.
The existing stop-monitor cadence observes at most three held paper symbols in
one quote batch. No extra historical fetch, subscription or scheduler job.

[SX-P2 2026-10-21] Every function takes ``policy``: PEN_SMART_V1 (default,
unchanged binding) or PEN_SMART_V2 (penny_smart_v2.py, its own state row,
events, bankroll and binding). ``smart_policies()`` lists the enabled ones.
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
from penny_smart_v2 import SMART_V2_PARAMS, SMART_V2_VERSION

IST = ZoneInfo("Asia/Kolkata")


def smart_db_path(ledger_path):
    """A separate store prevents shadow write locks on the operational ledger."""
    return str(ledger_path) + ".penny-smart-paper.db"


def smart_policies() -> dict:
    """{policy: params} for the enabled Smart books, V1 first."""
    from config import settings
    out = {SMART_VERSION: SMART_PARAMS}
    if getattr(settings, "PENNY_SMART_V2_ENABLED", False):
        out[SMART_V2_VERSION] = SMART_V2_PARAMS
    return out


def _params_for(policy):
    if policy == SMART_VERSION:
        return SMART_PARAMS
    if policy == SMART_V2_VERSION:
        return SMART_V2_PARAMS
    raise ValueError(f"unknown smart policy {policy!r}")


def _digest_for(policy):
    """V1's binding digest is exactly as before; V2 adds its declaration file."""
    if policy == SMART_VERSION:
        return _policy_digest()
    root = Path(__file__).resolve().parent
    return {**_policy_digest(), "penny_smart_v2.py": hashlib.sha256((root / "penny_smart_v2.py").read_bytes()).hexdigest()}


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


def _explain_halts(events, state, quotes, *, observations, allow_entries, drift):
    """[O19-S2] Name the condition(s) behind each ENTRY_HALTED.

    The frozen book reports one merged reason. Exit-only batches (the stop
    monitor: sampled bars, no entry candidate) are not entry decisions and
    record no halt; Oct 19 logged 235 merged halts, most of them those.
    """
    if not any(obs.get("entry_allowed", True) for obs in observations.values()):
        return [e for e in events if e.get("kind") != "ENTRY_HALTED"]
    unmarked = sorted(t for t in state["positions"] if not quotes.get(t, {}).get("executable"))
    reasons = [name for name, held in (
        ("configuration_drift", drift),
        ("entries_not_allowed", not allow_entries),
        ("held_mark_unavailable", bool(unmarked)),
        ("daily_loss_latched", bool(state.get("daily_loss_latched"))),
    ) if held]
    for e in events:
        if e.get("kind") == "ENTRY_HALTED":
            e["reason"] = "+".join(reasons) or e["reason"]
            if unmarked:
                e["unmarked"] = unmarked
    return events


def smart_held_tickers(db_path):
    """Symbols any enabled Smart book holds (read-only; empty without a book).

    The entry scan quotes them with its batch so a held name that left the
    scan's universe still has an executable mark (the frozen book halts all
    entries while any held position cannot be marked).
    """
    import sqlite3

    if not Path(db_path).exists():
        return []
    held = set()
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0) as conn:
            for policy in smart_policies():
                row = conn.execute(
                    "SELECT state_json FROM penny_smart_paper_state WHERE policy=?", (policy,)
                ).fetchone()
                if row:
                    held.update(json.loads(row[0]).get("positions", {}))
    except sqlite3.Error:
        return sorted(held)
    return sorted(held)


async def observe_smart_shadow(
    db_path,
    observations,
    raw_quotes,
    *,
    now,
    bankroll=2000.0,
    allow_entries=True,
    stock_cap=500.0,
    max_positions=3,
    policy=SMART_VERSION,
):
    """One atomic paper transition, deduplicated across concurrent/restarted jobs."""
    policy_params = _params_for(policy)
    now = now.replace(tzinfo=IST) if now.tzinfo is None else now.astimezone(IST)
    converted, invalid = await asyncio.to_thread(_convert_observations, observations, now)
    quotes = {ticker: quote_evidence(raw, now) for ticker, raw in raw_quotes.items()}
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        await _schema(db)
        await db.execute("BEGIN IMMEDIATE")
        row = await (
            await db.execute(
                "SELECT state_json FROM penny_smart_paper_state WHERE policy=?", (policy,)
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
            "params": asdict(policy_params),
            "execution": _execution_snapshot("SMART_PAPER"),
            "policy_sha256": _digest_for(policy),
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
        events = _explain_halts(events, updated, quotes, observations=converted,
                                allow_entries=allow_entries, drift=drift)
        updated["events"] = [e for e in updated["events"] if e.get("kind") != "ENTRY_HALTED"
                             or any(e is kept for kept in events)]
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
            key = hashlib.sha256((policy + payload).encode()).hexdigest()
            await db.execute(
                "INSERT OR IGNORE INTO penny_smart_paper_events VALUES (?,?,?,?,?,?)",
                (key, policy, event["at"], event["ticker"], event["kind"], payload),
            )
        await db.execute(
            "INSERT OR REPLACE INTO penny_smart_paper_state VALUES (?,?)",
            (policy, json.dumps(updated, sort_keys=True, allow_nan=False)),
        )
        await db.commit()
    return {
        "policy": policy,
        "events": len(events),
        "open": len(updated["positions"]),
        "realized": updated["realized"],
        "invalid_observations": invalid,
        "configuration_drift": drift,
        "can_place_orders": False,
    }


async def monitor_smart_shadow(db_path, kite, *, now, policy=SMART_VERSION):
    """Bounded quote-only exit observation; independent of all entry brakes."""
    async with aiosqlite.connect(db_path, timeout=10.0) as db:
        await _schema(db)
        row = await (
            await db.execute(
                "SELECT state_json FROM penny_smart_paper_state WHERE policy=?", (policy,)
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
    tokens = {t: (getattr(kite, "instrument_cache", {}) or {}).get(t) for t in tickers}
    requested = [int(v) for v in tokens.values() if v is not None]
    batch = await kite.get_quote(requested) if requested else {}
    raw = {t: batch.get(int(token), {}) for t, token in tokens.items() if token is not None}
    # [O9-S1 2026-10-09] Held exits must not depend on the discovery cache.
    # On Oct 9 the post-restart cache stayed empty, so STEELXIND/TATSILV got
    # no quote after 11:17 and their session-deadline exits never filled.
    # A held symbol without a token is quoted by its documented
    # EXCHANGE:SYMBOL key instead; a missing answer stays unavailable.
    missing = [t for t, token in tokens.items() if token is None]
    if missing and hasattr(kite, "get_quote_by_instruments"):
        keyed = {-(index + 1): f"NSE:{ticker}" for index, ticker in enumerate(missing)}
        by_symbol = await kite.get_quote_by_instruments(keyed)
        for key, ticker in zip(keyed, missing):
            if key in by_symbol:
                raw[ticker] = by_symbol[key]
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
        policy=policy,
    )


STOP_EXITS = ("SMART_PAPER_STOP", "SMART_THESIS_FAILED")


def _round_trips(rows) -> list[dict]:
    """ENTRY_FILLED/EXIT_FILLED events (time order) as closed round trips."""
    open_by_ticker: dict = {}
    trips = []
    for at, ticker, kind, raw in rows:
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if kind == "ENTRY_FILLED":
            open_by_ticker.setdefault(ticker, []).append((at, payload))
            continue
        queue = open_by_ticker.get(ticker) or []
        if not queue:
            continue          # an exit whose entry is before the window
        entry_at, entry = queue.pop(0)
        try:
            shares, net = float(payload["shares"]), float(payload["net_pnl"])
            entry_px, exit_px = float(entry["price"]), float(payload["price"])
        except (KeyError, TypeError, ValueError):
            continue
        minutes = (datetime.fromisoformat(at) - datetime.fromisoformat(entry_at)).total_seconds() / 60
        trips.append({"day": entry_at[:10], "ticker": ticker, "entry_at": entry_at, "exit_at": at,
                      "reason": payload.get("reason") or "?", "net": net, "shares": shares,
                      "fees": round((exit_px - entry_px) * shares - net, 4), "hold_min": minutes,
                      "deployed": entry_px * shares})
    return trips


def _book_stats(trips: list[dict]) -> dict:
    nets = [t["net"] for t in trips]
    gains, losses = sum(n for n in nets if n > 0), -sum(n for n in nets if n < 0)
    reasons: dict = {}
    for t in trips:
        reasons[t["reason"]] = reasons.get(t["reason"], 0) + 1
    holds = sorted(t["hold_min"] for t in trips)
    return {
        "closes": len(nets), "wins": sum(n > 0 for n in nets), "losses": sum(n < 0 for n in nets),
        "net": round(sum(nets), 4), "average": round(sum(nets) / len(nets), 4) if nets else None,
        "profit_factor": round(gains / losses, 4) if losses else None, "exit_reasons": reasons,
        "fees": round(sum(t["fees"] for t in trips), 4),
        "median_hold_min": round(holds[len(holds) // 2], 1) if holds else None,
        # Capital occupancy: rupees held times hours held (a wider stop sizes smaller and holds longer).
        "rupee_hours": round(sum(t["deployed"] * t["hold_min"] / 60 for t in trips), 2),
        "average_deployed": round(sum(t["deployed"] for t in trips) / len(trips), 2) if trips else None,
    }


def _versus(base: list[dict], other: list[dict]) -> dict:
    """Same-day, same-ticker opportunities: the first round trip of each book."""
    def first(trips):
        out: dict = {}
        for t in trips:
            out.setdefault((t["day"], t["ticker"]), t)
        return out

    a, b = first(base), first(other)
    matched = sorted(set(a) & set(b))
    only_base, only_other = sorted(set(a) - set(b)), sorted(set(b) - set(a))

    def missed(keys, book):
        winners = [book[k]["net"] for k in keys if book[k]["net"] > 0]
        return {"count": len(winners), "net": round(sum(winners), 4)}

    return {
        "matched": len(matched),
        "matched_net_delta": round(sum(b[k]["net"] - a[k]["net"] for k in matched), 4),
        # The base book's stop or thesis exit lost, the other book on the same name did better.
        "base_stopped_other_better": sum(1 for k in matched if a[k]["reason"] in STOP_EXITS and a[k]["net"] < 0
                                         and b[k]["net"] > a[k]["net"]),
        "other_stopped_worse": sum(1 for k in matched if b[k]["reason"] in STOP_EXITS and b[k]["net"] < a[k]["net"]),
        "base_only": len(only_base), "other_only": len(only_other),
        "winners_missed_by_other": missed(only_base, a), "winners_missed_by_base": missed(only_other, b),
    }


def smart_policy_comparison(ledger_path, *, since="2026-10-22"):
    """[SX-P2] Each Smart book's closes from ``since`` (V2's first scored
    session): count, wins, losses, net, average, profit factor, exit reasons.

    [A22-E1] Opportunities as well as totals (Oct 22 audit): a wider stop
    changes which later trades fit the bankroll, not only each outcome. Per
    book: fees, median hold and capital occupancy (rupee-hours). Against V1
    (``versus``): same-day same-ticker opportunities both took and the net
    difference on them, V1 stop-outs where the other book did better, the
    other's wider-stop losses, and winners only one book took. Round trips
    pair each exit with its entry; an exit whose entry is before ``since``
    is left out. Reporting only: no threshold reads it."""
    import sqlite3
    path = smart_db_path(ledger_path)
    out = {"since": since, "policies": [], "versus": {}}
    if not Path(path).exists():
        return out
    trips_by_policy = {}
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0) as conn:
        for policy in smart_policies():
            try:
                rows = conn.execute(
                    "SELECT at, ticker, kind, payload_json FROM penny_smart_paper_events WHERE policy=? "
                    "AND kind IN ('ENTRY_FILLED','EXIT_FILLED') AND at >= ? ORDER BY at, kind DESC",
                    (policy, since)).fetchall()
            except sqlite3.OperationalError:
                rows = []
            trips_by_policy[policy] = _round_trips(rows)
            out["policies"].append({"policy": policy, **_book_stats(trips_by_policy[policy])})
    base = SMART_VERSION
    for policy, trips in trips_by_policy.items():
        if policy != base:
            out["versus"][policy] = {"base": base, **_versus(trips_by_policy[base], trips)}
    return out


def smart_exposure_snapshot(ledger_path, *, now=None, policy=SMART_VERSION):
    """Read-only view of the independent Smart book for /health.

    The classic Penny open count is a different book; on Oct 9 it read 0
    while two Smart positions sat OPEN, unpriced and past their deadline.
    """
    import sqlite3

    now = (now or datetime.now(IST)).astimezone(IST)
    path = smart_db_path(ledger_path)
    if not Path(path).exists():
        return {"status": "NO_BOOK", "open": 0, "positions": []}
    exits = []
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0) as conn:
        try:
            row = conn.execute(
                "SELECT state_json FROM penny_smart_paper_state WHERE policy=?", (policy,)
            ).fetchone()
        except sqlite3.OperationalError:
            row = None
        try:
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            exits = [r[0] for r in conn.execute(
                "SELECT payload_json FROM penny_smart_paper_events WHERE policy=? AND kind='EXIT_FILLED' "
                "AND at >= ?", (policy, day_start))]
        except sqlite3.OperationalError:
            exits = []
    if not row:
        return {"status": "NO_BOOK", "open": 0, "positions": []}
    state = json.loads(row[0])
    positions = []
    for ticker, pos in sorted(state.get("positions", {}).items()):
        managed = pos.get("managed_at")
        age = None
        if managed:
            age = round((now - datetime.fromisoformat(managed).astimezone(IST)).total_seconds() / 60, 1)
        positions.append({
            "ticker": ticker,
            "exit_pending": pos.get("exit_pending"),
            "managed_at": managed,
            "minutes_since_managed": age,
        })
    unpriced = state.get("mark_status") == "UNAVAILABLE"
    stale = any(p["minutes_since_managed"] is None or p["minutes_since_managed"] > 10 for p in positions)
    pending = any(p["exit_pending"] for p in positions)
    status = "FLAT" if not positions else ("ATTENTION" if (unpriced or stale or pending) else "OPEN")
    return {
        "status": status,
        "open": len(positions),
        "mark_status": state.get("mark_status"),
        "marked_pnl": state.get("marked_pnl"),
        "book_day": state.get("day"),
        "positions": positions,
        "exit_date": _exit_date_realized(exits, state, now),
    }


def _exit_date_realized(payloads, state, now):
    """Every Smart close dated today, including prior-day holdings settled today.

    [O12-S1 2026-10-12] Day rollover clears the trade list after settling the
    carried positions, so ``marked_pnl`` covers the new day's entries only.
    Oct 12 showed -18.01 there while the exit-date total was -11.44: two
    Friday holdings closed Monday for +6.58 and lived only in the durable
    events. This joins them so a reader of /health sees both numbers.
    """
    nets = []
    for raw in payloads:
        try:
            nets.append(float(json.loads(raw)["net_pnl"]))
        except (ValueError, KeyError, TypeError):
            continue
    same_day = state.get("day") == now.date().isoformat()
    day_trades = len(state.get("trades") or []) if same_day else 0
    return {
        "date": now.date().isoformat(),
        "closes": len(nets),
        "net": round(sum(nets), 4),
        "carried_closes": max(0, len(nets) - day_trades),
        "book_day_realized": round(float(state.get("realized") or 0.0), 4) if same_day else None,
    }
