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
Nothing here trades, retries or backfills: a gap's missed fills are never
invented.
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
MAX_EVENTS = 2000
MARKET_OPEN = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)


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


def market_overlap_sec(start_epoch: float, end_epoch: float) -> float:
    """Seconds of [start, end] inside 09:15-15:30 IST on weekdays.

    Holidays are not excluded here; the caller decides with the calendar.
    """
    if end_epoch <= start_epoch:
        return 0.0
    start = datetime.fromtimestamp(start_epoch, IST)
    end = datetime.fromtimestamp(end_epoch, IST)
    total, day = 0.0, start.date()
    while day <= end.date():
        if day.weekday() < 5:
            lo = IST.localize(datetime.combine(day, MARKET_OPEN))
            hi = IST.localize(datetime.combine(day, MARKET_CLOSE))
            overlap = (min(hi, end) - max(lo, start)).total_seconds()
            total += max(0.0, overlap)
        day += timedelta(days=1)
    return total


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
    receipt = {
        "boot_id": boot_id,
        "prior_boot_id": (prior or {}).get("boot_id"),
        "prior_heartbeat_ist": (datetime.fromtimestamp(prior_epoch, IST).isoformat() if prior_epoch else None),
        "gap_sec": round(gap, 1) if gap is not None else None,
        "market_overlap_sec": round(market_overlap_sec(prior_epoch, now_epoch), 1) if prior_epoch else 0.0,
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
    """Operator page for a market-hours restart gap, else ``None``."""
    overlap = receipt.get("market_overlap_sec") or 0.0
    if overlap < MARKET_GAP_ALERT_SEC:
        return None
    held = ", ".join(f"{name} {count}" for name, count in open_exposure.items() if count) or "none"
    since = (receipt.get("prior_heartbeat_ist") or "?")[11:16]
    suspend = (f" Host sleep of {receipt['prior_host_suspend_sec']:.0f}s was seen first."
               if receipt.get("prior_host_suspend_sec") else "")
    return (f"⚠️ Engine restarted after a {overlap / 60:.0f}-min market-hours gap (last heartbeat {since} IST). "
            f"Cause seen: {receipt.get('cause')}.{suspend} Open at restart: {held}. "
            "Exits resume now; nothing was traded or monitored during the gap.")
