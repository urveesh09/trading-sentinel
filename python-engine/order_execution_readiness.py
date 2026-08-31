"""Persistent, evidence-based Kite order-execution readiness.

Market data and token health do not prove that Kite will accept orders.  In
particular, Kite can serve quotes while rejecting every order because the
request did not originate from the static IP registered for the app.  This
module keeps that concern separate and deliberately reports UNVERIFIED until
an order has actually been accepted.

BLOCKED is sticky across process restarts.  Recovery is recorded only after
Kite accepts an order; callers must still clear the filesystem halt manually
after investigating the route/IP configuration.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from config import settings

UNVERIFIED = "UNVERIFIED"
AUTHORIZED = "AUTHORIZED"
BLOCKED = "BLOCKED"

_lock = threading.Lock()
_memory_state: Dict[str, Any] | None = None


def _state_path() -> Path:
    configured = str(getattr(settings, "ORDER_EXECUTION_STATE_PATH", "") or "").strip()
    if configured:
        return Path(configured)
    return Path(settings.DB_PATH).resolve().parent / "order_execution_readiness.json"


def _default_state() -> Dict[str, Any]:
    return {
        "status": UNVERIFIED,
        "endpoint": str(settings.KITE_BASE_URL),
        "updated_at": None,
        "reason": "no accepted broker order has verified this route",
        "http_status": None,
    }


def _load() -> Dict[str, Any]:
    global _memory_state
    if _memory_state is not None:
        return dict(_memory_state)
    state = _default_state()
    try:
        raw = json.loads(_state_path().read_text(encoding="utf-8"))
        if isinstance(raw, dict) and raw.get("status") in {UNVERIFIED, AUTHORIZED, BLOCKED}:
            state.update(raw)
    except (FileNotFoundError, OSError, ValueError, TypeError):
        pass
    # A result from another endpoint does not establish this route's ability
    # to place orders.  A BLOCKED state remains useful evidence even if config
    # changed, but an old AUTHORIZED state must not follow the new route.
    if state.get("endpoint") != str(settings.KITE_BASE_URL) and state.get("status") != BLOCKED:
        state = _default_state()
    _memory_state = state
    return dict(state)


def snapshot() -> Dict[str, Any]:
    with _lock:
        return _load()


def is_permission_or_static_ip_rejection(http_status: int | None, body: str) -> bool:
    """Recognise broker-level order authorization failures conservatively."""
    text = str(body or "").lower()
    if http_status not in (401, 403):
        return False
    markers = (
        "static ip", "static_ip", "ip address", "ip not allowed",
        "not allowed to place orders", "permissionexception",
        "permission exception", "insufficient permission",
    )
    return any(marker in text for marker in markers)


def mark_blocked(reason: str, *, http_status: int | None = None) -> bool:
    """Persist BLOCKED and return True only for the first blocked transition."""
    with _lock:
        before = _load()
        changed = before.get("status") != BLOCKED
        state = {
            "status": BLOCKED,
            "endpoint": str(settings.KITE_BASE_URL),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "reason": str(reason)[:500],
            "http_status": http_status,
        }
        _save(state)
        return changed


def mark_authorized() -> None:
    """Record direct evidence that Kite accepted an order request."""
    with _lock:
        state = {
            "status": AUTHORIZED,
            "endpoint": str(settings.KITE_BASE_URL),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "reason": "Kite accepted an order on this route",
            "http_status": None,
        }
        _save(state)


def _save(state: Dict[str, Any]) -> None:
    global _memory_state
    _memory_state = dict(state)
    path = _state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".order-ready-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, sort_keys=True, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        except BaseException:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise
    except OSError:
        # The in-memory latch still protects this process.  The broker-boundary
        # caller also trips the independently persistent filesystem halt.
        pass


def _reset_for_tests() -> None:
    global _memory_state
    with _lock:
        _memory_state = None
