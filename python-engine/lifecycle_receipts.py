"""[O13-R1 2026-10-15] Durable process-lifecycle receipts.

Oct 13 lost 94 minutes of market time (10:05 -> 11:40 IST) with a NIFTY
defined-risk spread open, and the audit could not tell host sleep, a manual
stop, a crash or an OOM apart: no retained record said how the old process
ended or what the container saw. This module records the evidence that is
observable from inside the container:

* ``clean_shutdown``: written on graceful lifespan exit, so the next startup
  knows whether the previous process was stopped (deploy/manual) or died
  (crash, power cut, kill, OOM).
* ``host_suspend``: the heartbeat thread compares wall-clock and monotonic
  advance between ticks. Linux ``CLOCK_MONOTONIC`` does not run while the
  machine (or the Docker VM) is suspended, so wall time jumping ahead of
  monotonic time is a host sleep, not a frozen process.
* ``thread_stall``: monotonic time itself advanced far past the tick period,
  which is a starved or frozen process.
* ``startup``: prior heartbeat clock, gap, prior shutdown flag, host (VM)
  uptime, and whether the gap overlapped market hours.

Events append to ``lifecycle_events.jsonl`` beside the database (bounded).
Nothing here trades or backfills: a gap's missed fills are never invented.

Evidence limits (review 2026-10-15): wall time running ahead of monotonic
time fits a host sleep, but a stepped realtime clock looks the same; a
heartbeat-thread stall does not prove the asyncio loop froze. The page
therefore names a *likely* cause, to be checked against host logs.

[review F4] Open positions are read from every book, including the
overnight, expiry and Smart sibling stores, read-only. A store that cannot
be read is UNKNOWN, never zero. The page goes through a small durable
outbox with acknowledged delivery (``require_delivery``), bounded retries
and one id per boot. A lost acknowledgement can still repeat a page; it is
at-least-once, not exactly-once.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, time as dtime, timedelta
from typing import Optional

import pytz

IST = pytz.timezone("Asia/Kolkata")
SUSPEND_THRESHOLD_SEC = 30.0       # wall-ahead-of-monotonic jump that counts as host sleep
STALL_THRESHOLD_SEC = 120.0        # extra monotonic time between heartbeat ticks
MARKET_GAP_ALERT_SEC = 300.0       # matches ops_metrics.LIVENESS_MAX_GAP_SEC
HELD_GAP_ALERT_SEC = 60.0          # any book open (or unknown): a shorter gap still pages
PROVIDER_OUTAGE_ALERT_SEC = 120.0  # market-hours provider silence that pages the operator
PROVIDER_OUTAGE_MIN_FAILURES = 5   # one stray failure is not an outage
MAX_EVENTS = 2000
MARKET_OPEN = dtime(9, 15)
MARKET_CLOSE = dtime(15, 40)        # [O24-MC 2026-10-24] the session runs to the 15:40 derivatives close


def events_path(db_path: str) -> str:
    return os.path.join(os.path.dirname(db_path) or ".", "lifecycle_events.jsonl")


def heartbeat_path(db_path: str) -> str:
    return os.path.join(os.path.dirname(db_path) or ".", "scheduler_tick.json")


def record_event(db_path: str, kind: str, **fields) -> dict:
    """Append one event; never raises (evidence must not stop trading)."""
    event = {"kind": kind, "ist": datetime.now(IST).isoformat(), "ts_epoch": time.time(), **fields}
    path = events_path(db_path)
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, default=str) + "\n")
        if os.path.getsize(path) > MAX_EVENTS * 600:
            with open(path, encoding="utf-8") as fh:
                lines = fh.readlines()[-MAX_EVENTS // 2:]
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.writelines(lines)
            os.replace(tmp, path)
    except OSError:
        pass
    return event


def recent_events(db_path: str, limit: int = 50) -> list[dict]:
    try:
        with open(events_path(db_path), encoding="utf-8") as fh:
            lines = fh.readlines()[-limit:]
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def clock_jump(prev_wall: float, prev_mono: float, now_wall: float, now_mono: float,
               period_sec: float) -> Optional[dict]:
    """Classify one heartbeat interval. ``None`` when it was ordinary."""
    wall, mono = now_wall - prev_wall, now_mono - prev_mono
    if wall - mono >= SUSPEND_THRESHOLD_SEC:
        return {"kind": "host_suspend", "suspended_sec": round(wall - mono, 1),
                "wall_sec": round(wall, 1), "monotonic_sec": round(mono, 1)}
    if mono - period_sec >= STALL_THRESHOLD_SEC:
        return {"kind": "thread_stall", "stall_sec": round(mono - period_sec, 1),
                "wall_sec": round(wall, 1), "monotonic_sec": round(mono, 1)}
    return None


def mark_clean_shutdown(db_path: str, boot_id: str) -> None:
    """Flag the heartbeat file so the next startup sees a deliberate stop."""
    path = heartbeat_path(db_path)
    try:
        with open(path, encoding="utf-8") as fh:
            beat = json.load(fh)
    except (OSError, ValueError):
        beat = {}
    beat.update(clean_shutdown=True, shutdown_epoch=time.time(), boot_id=beat.get("boot_id", boot_id))
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(beat, fh)
        os.replace(tmp, path)
    except OSError:
        pass
    record_event(db_path, "clean_shutdown", boot_id=boot_id)


def host_uptime_sec() -> Optional[float]:
    """Uptime of the kernel the container runs on (the Docker VM on a
    desktop host). Shorter than a gap means that kernel restarted."""
    try:
        with open("/proc/uptime", encoding="utf-8") as fh:
            return float(fh.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def market_overlap_sec(start_epoch: float, end_epoch: float, is_session=None) -> float:
    """Seconds of [start, end] inside 09:15-15:40 IST on session days.

    ``is_session(date) -> bool`` decides each day (the exchange calendar);
    without it every weekday counts, which is the raw wall-clock measure.
    """
    if end_epoch <= start_epoch:
        return 0.0
    start = datetime.fromtimestamp(start_epoch, IST)
    end = datetime.fromtimestamp(end_epoch, IST)
    total, day = 0.0, start.date()
    while day <= end.date():
        if day.weekday() < 5 and (is_session is None or is_session(day)):
            lo = IST.localize(datetime.combine(day, MARKET_OPEN))
            hi = IST.localize(datetime.combine(day, MARKET_CLOSE))
            overlap = (min(hi, end) - max(lo, start)).total_seconds()
            total += max(0.0, overlap)
        day += timedelta(days=1)
    return total


def _session_day(db_path: str):
    """A dated exchange-calendar check for each day of a gap; a calendar that
    cannot be read counts the weekday (never hides a market-hours gap)."""
    def is_session(day) -> bool:
        try:
            from market_calendar import is_trading_day_sync
            return is_trading_day_sync(day, db_path)
        except Exception:
            return True
    return is_session


def classify_restart(prior: Optional[dict], gap_sec: Optional[float],
                     uptime_sec: Optional[float]) -> str:
    """Best cause the container can see; ``unknown`` when it cannot."""
    if not prior or gap_sec is None:
        return "first_boot_or_no_heartbeat"
    if prior.get("clean_shutdown"):
        return "clean_shutdown"
    if uptime_sec is not None and uptime_sec < gap_sec:
        return "host_or_vm_restarted"
    return "unclean_stop"   # crash, kill, OOM, or host sleep then container restart


def startup_receipt(db_path: str, prior: Optional[dict], now_epoch: float, boot_id: str) -> dict:
    """Build and append the startup receipt. ``prior`` is the heartbeat file
    as read before this process overwrote it."""
    prior_epoch = None
    try:
        prior_epoch = float(prior["ts_epoch"]) if prior else None
    except (KeyError, TypeError, ValueError):
        prior_epoch = None
    gap = max(0.0, now_epoch - prior_epoch) if prior_epoch else None
    uptime = host_uptime_sec()
    # [S21-L1] The restart page uses trading sessions only: Oct 20 (Dussehra)
    # read as 375 market minutes. The raw weekday figure stays as evidence.
    receipt = {
        "boot_id": boot_id,
        "prior_boot_id": (prior or {}).get("boot_id"),
        "prior_heartbeat_ist": (datetime.fromtimestamp(prior_epoch, IST).isoformat() if prior_epoch else None),
        "gap_sec": round(gap, 1) if gap is not None else None,
        "market_overlap_sec": (round(market_overlap_sec(prior_epoch, now_epoch, _session_day(db_path)), 1)
                               if prior_epoch else 0.0),
        "weekday_overlap_sec": round(market_overlap_sec(prior_epoch, now_epoch), 1) if prior_epoch else 0.0,
        "prior_clean_shutdown": bool((prior or {}).get("clean_shutdown")),
        "host_uptime_sec": round(uptime, 1) if uptime is not None else None,
        "cause": classify_restart(prior, gap, uptime),
    }
    # A suspend recorded by the previous process right before it ended is
    # the strongest available cause evidence.
    for event in reversed(recent_events(db_path, 20)):
        if event.get("kind") == "host_suspend" and event.get("boot_id") == receipt["prior_boot_id"]:
            receipt["prior_host_suspend_sec"] = event.get("suspended_sec")
            break
    record_event(db_path, "startup", **receipt)
    return receipt


def restart_alert_text(receipt: dict, open_exposure: dict) -> Optional[str]:
    """Operator page for a market-hours restart gap, else ``None``.

    ``open_exposure`` maps book -> open count, or ``None`` when that book
    could not be read (shown as "unknown", never as flat).
    """
    overlap = receipt.get("market_overlap_sec") or 0.0
    parts = [f"{name} {'unknown' if count is None else count}"
             for name, count in open_exposure.items() if count is None or count]
    # [O15-R1] Oct 15 10:35-10:37: a 168 s host restart with a NIFTY spread
    # held paged nobody (bar was 300 s). Held or unknown exposure pages from
    # 60 s; a flat book keeps the 300 s bar.
    if overlap < (HELD_GAP_ALERT_SEC if parts else MARKET_GAP_ALERT_SEC):
        return None
    held = ", ".join(parts) or "none in any book"
    since = (receipt.get("prior_heartbeat_ist") or "?")[11:16]
    suspend = (f" The wall clock jumped {receipt['prior_host_suspend_sec']:.0f}s ahead of the monotonic "
               "clock first (host sleep or a clock step)."
               if receipt.get("prior_host_suspend_sec") else "")
    gap = f"{overlap / 60:.0f}-min" if overlap >= 600 else f"{overlap / 60:.1f}-min"
    return (f"⚠️ Engine restarted after a {gap} market-hours gap (last heartbeat {since} IST). "
            f"Likely cause: {receipt.get('cause')}; check host logs.{suspend} "
            f"Open at recovery: {held}. "
            "Exits resume now; nothing was traded or monitored during the gap.")


# --- open exposure across every book -------------------------------------

def _count(path: str, sql: str) -> Optional[int]:
    """COUNT from a store opened read-only. A missing store or table means
    the book never existed (0); any other failure is UNKNOWN (None)."""
    import sqlite3
    if not os.path.exists(path):
        return 0
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
        try:
            return int(conn.execute(sql).fetchone()[0])
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        return 0 if "no such table" in str(exc) else None
    except sqlite3.Error:
        return None


def open_exposure_counts(db_path: str) -> dict:
    """Open positions per book, observed now (not an atomic snapshot)."""
    from edge_overnight_paper import overnight_db_path
    from expiry_paper import expiry_db_path
    counts = {
        "F&O singles": _count(db_path, "SELECT COUNT(*) FROM fno_positions WHERE status='OPEN'"),
        "F&O spreads": _count(db_path, "SELECT COUNT(*) FROM fno_dr_positions "
                                       "WHERE status IN ('OPEN','UNRESOLVED')"),
        "equity/Penny/EDGE": _count(db_path, "SELECT COUNT(*) FROM positions WHERE status='OPEN'"),
        "overnight": _count(overnight_db_path(db_path),
                            "SELECT COUNT(*) FROM edge_overnight_paper_trades WHERE status='OPEN'"),
        "expiry": _count(expiry_db_path(db_path),
                         "SELECT COUNT(*) FROM expiry_paper_positions WHERE status='OPEN'"),
    }
    try:
        from penny_smart_shadow import smart_exposure_snapshot
        snap = smart_exposure_snapshot(db_path)
        counts["Smart"] = int(snap.get("open", 0)) if snap.get("status") != "ERROR" else None
    except Exception:  # noqa: BLE001 - unreadable is unknown, not flat
        counts["Smart"] = None
    return counts


# --- acknowledged restart-page outbox -------------------------------------

ALERT_MAX_AGE_SEC = 6 * 3600     # a restart page older than this is stale news
ALERT_MAX_ATTEMPTS = 20
ALERT_BACKOFF_CAP_SEC = 600.0
_OUTBOX_LOCK = None


def _outbox_lock():
    import asyncio
    global _OUTBOX_LOCK
    if _OUTBOX_LOCK is None:
        _OUTBOX_LOCK = asyncio.Lock()
    return _OUTBOX_LOCK


def _backoff_sec(attempts: int) -> float:
    return 0.0 if attempts <= 0 else min(30.0 * 2 ** (attempts - 1), ALERT_BACKOFF_CAP_SEC)


def outbox_path(db_path: str) -> str:
    return os.path.join(os.path.dirname(db_path) or ".", "restart_alert_outbox.json")


def _load_outbox(db_path: str) -> list:
    try:
        with open(outbox_path(db_path), encoding="utf-8") as fh:
            rows = json.load(fh)
        return rows if isinstance(rows, list) else []
    except (OSError, ValueError):
        return []


def _save_outbox(db_path: str, rows: list) -> None:
    path = outbox_path(db_path)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rows[-50:], fh)
    os.replace(tmp, path)


def queue_restart_alert(db_path: str, alert_id: str, text: str, now_epoch: float) -> bool:
    """Queue one page per ``alert_id`` (the boot id); False if already queued.

    Synchronous load-append-save: within the event loop it cannot interleave
    with a delivery's own row updates (see ``_update_alert``)."""
    rows = _load_outbox(db_path)
    if any(row.get("id") == alert_id for row in rows):
        return False
    rows.append({"id": alert_id, "text": text, "created_epoch": now_epoch, "attempts": 0,
                 "state": "PENDING", "sent_epoch": None, "last_attempt_epoch": None})
    _save_outbox(db_path, rows)
    return True


def has_pending_alerts(db_path: str) -> bool:
    return any(row.get("state") == "PENDING" for row in _load_outbox(db_path))


async def deliver_restart_alerts(db_path: str, post, now_epoch: float) -> int:
    """Attempt each pending page whose backoff has elapsed; returns how many
    stay pending. Called once at startup, then from the 60 s scheduler tick,
    under one lock so two callers never send the same row.

    ``post(text)`` returns ``"delivered"`` (gateway acknowledged),
    ``"rejected"`` (Telegram refused this text; never retried) or
    ``"failed"`` (retried with backoff 30 s doubling to 10 min, at most
    ``ALERT_MAX_ATTEMPTS`` times and within ``ALERT_MAX_AGE_SEC``).
    """
    async with _outbox_lock():
        return await _deliver_locked(db_path, post, now_epoch)


def _update_alert(db_path: str, alert_id: str, **changes) -> None:
    """Reload, change one row, save, with no await in between. Any row
    queued meanwhile (e.g. by the startup task while a send was in flight)
    is kept; review R2 found a stale whole-list save dropping it."""
    rows = _load_outbox(db_path)
    for row in rows:
        if row.get("id") == alert_id:
            row.update(changes)
    _save_outbox(db_path, rows)


async def _deliver_locked(db_path: str, post, now_epoch: float) -> int:
    pending = 0
    for row in _load_outbox(db_path):
        if row.get("state") != "PENDING":
            continue
        alert_id = row.get("id")
        attempts = int(row.get("attempts") or 0)
        if now_epoch - float(row.get("created_epoch") or 0) > ALERT_MAX_AGE_SEC or attempts >= ALERT_MAX_ATTEMPTS:
            _update_alert(db_path, alert_id, state="EXPIRED")
            record_event(db_path, "restart_alert_expired", alert_id=alert_id, attempts=attempts)
            continue
        last = row.get("last_attempt_epoch")
        if last is not None and now_epoch - float(last) < _backoff_sec(attempts):
            pending += 1
            continue
        # Count the attempt before the send: a crash cannot loop it.
        _update_alert(db_path, alert_id, attempts=attempts + 1, last_attempt_epoch=now_epoch)
        try:
            outcome = await post(row["text"])
        except Exception:  # noqa: BLE001 - a transport error is a retryable failure
            outcome = "failed"
        if outcome == "delivered":
            _update_alert(db_path, alert_id, state="DELIVERED", sent_epoch=now_epoch)
        elif outcome == "rejected":
            _update_alert(db_path, alert_id, state="REJECTED")
        else:
            pending += 1
        record_event(db_path, "restart_alert_attempt", alert_id=alert_id, outcome=outcome,
                     attempts=attempts + 1)
    return pending


def supersede_alert(db_path: str, alert_id: str) -> bool:
    """Retire a still-pending page that a newer one replaces."""
    rows = _load_outbox(db_path)
    if not any(row.get("id") == alert_id and row.get("state") == "PENDING" for row in rows):
        return False
    _update_alert(db_path, alert_id, state="SUPERSEDED")
    return True


def alert_queued(db_path: str, alert_id: str) -> bool:
    return any(row.get("id") == alert_id for row in _load_outbox(db_path))


# --- provider (market data) outage pages ----------------------------------

def _kinds(outage: dict) -> str:
    return ", ".join(f"{kind} {n}" for kind, n in sorted((outage.get("kinds") or {}).items()))


def outage_lost_text(outage: dict, now_epoch: float, open_exposure: dict) -> str:
    since = datetime.fromtimestamp(float(outage["start_epoch"]), IST).strftime("%H:%M")
    mins = (now_epoch - float(outage["start_epoch"])) / 60
    parts = [f"{name} {'unknown' if count is None else count}"
             for name, count in open_exposure.items() if count is None or count]
    held = ", ".join(parts) or "none"
    return (f"⚠️ Market data down since {since} IST ({mins:.0f} min): {outage.get('failures', 0)} "
            f"broker calls got no answer ({_kinds(outage)}). Quotes and bars are missing, so "
            f"entries and marks wait; nothing is priced from old data. Open: {held}.")


def outage_restored_text(outage: dict) -> str:
    start = datetime.fromtimestamp(float(outage["start_epoch"]), IST)
    end = datetime.fromtimestamp(float(outage["end_epoch"]), IST)
    mins = (float(outage["end_epoch"]) - float(outage["start_epoch"])) / 60
    return (f"✅ Market data back {end.strftime('%H:%M')} IST after {mins:.0f} min "
            f"({start.strftime('%H:%M')}-{end.strftime('%H:%M')}): {outage.get('failures', 0)} broker "
            f"calls got no answer ({_kinds(outage)}). Decisions in that window had no data; "
            "they were skipped, not judged.")


def provider_outage_alerts(db_path: str, connectivity: dict, now_epoch: float,
                           exposure_fn=None) -> list[str]:
    """[O15-N1 2026-10-15] Queue outage pages from
    ``EndpointBudget.connectivity()``; returns the ids queued now.

    Oct 15 14:57-15:15: DNS failures blanked quotes for 18 minutes (101
    expiry decisions, every B-window entry, a partner reminder) and nobody
    was told; the engine's health read OK again afterwards. An outage that
    covers >= PROVIDER_OUTAGE_ALERT_SEC of market time with at least
    PROVIDER_OUTAGE_MIN_FAILURES failures pages once while it lasts and once
    when it ends; the end page retires an undelivered start page (it carries
    the whole window). Delivery is the acknowledged outbox above.
    """
    queued = []
    current = (connectivity or {}).get("current")
    if current and int(current.get("failures") or 0) >= PROVIDER_OUTAGE_MIN_FAILURES:
        start = float(current["start_epoch"])
        if market_overlap_sec(start, now_epoch) >= PROVIDER_OUTAGE_ALERT_SEC:
            alert_id = f"provider-outage:{int(start)}:lost"
            if not alert_queued(db_path, alert_id):
                exposure = exposure_fn() if exposure_fn is not None else {}
                if queue_restart_alert(db_path, alert_id, outage_lost_text(current, now_epoch, exposure),
                                       now_epoch):
                    queued.append(alert_id)
    for outage in (connectivity or {}).get("recent") or []:
        try:
            start, end = float(outage["start_epoch"]), float(outage["end_epoch"])
        except (KeyError, TypeError, ValueError):
            continue
        if (int(outage.get("failures") or 0) < PROVIDER_OUTAGE_MIN_FAILURES
                or market_overlap_sec(start, end) < PROVIDER_OUTAGE_ALERT_SEC
                or now_epoch - end > ALERT_MAX_AGE_SEC):
            continue
        alert_id = f"provider-outage:{int(start)}:restored"
        if queue_restart_alert(db_path, alert_id, outage_restored_text(outage), now_epoch):
            queued.append(alert_id)
            supersede_alert(db_path, f"provider-outage:{int(start)}:lost")
            record_event(db_path, "provider_outage", start_epoch=start, end_epoch=end,
                         failures=outage.get("failures"), kinds=outage.get("kinds"))
    return queued
