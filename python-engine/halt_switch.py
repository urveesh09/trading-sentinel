"""[HALT 2026-08-05] Filesystem kill switch, enforced at the broker boundary.

THE DEFECT THIS EXISTS TO FIX
-----------------------------
`performance.check_circuit_breakers` has computed a correct `halted` boolean
since the system was built, and nothing has ever acted on it. The candour is
already in the tree, at partner_orchestrator.py:533:

    # [HONEST-HALT 2026-07-26] This used to broadcast "Our system halted its
    # own trading" ... No entry path is gated by it, so nothing was halted.

Worse, node-gateway -- the container that actually places the momentum orders --
had no concept of a halt at all. The kill switch was a Telegram message.

WHY A FILE AND NOT A DATABASE FLAG
----------------------------------
The halt has to work in exactly the situations where the rest of the system is
not working. A flag in cache.db is unreadable when SQLite is locked by a long
scan; a flag in process memory dies with the process; a flag the LLM has to
respect is not a control at all. A file on the shared volume is checked with one
stat() call, needs no lock, survives a restart, is visible to both containers,
and -- the property that matters at 09:20 on a bad morning -- can be tripped by
hand:

    docker exec python-engine touch /data/HALT

FAIL-CLOSED, PRECISELY
----------------------
The file's EXISTENCE is the halt. Its contents are attribution metadata and
nothing more: a sentinel containing corrupt JSON, an empty sentinel, or one
written by `touch` all halt trading identically. Parsing must never be able to
un-halt.

The subtle half is the error path. `os.path.exists()` returns False when the
stat fails for any reason -- including EACCES and EIO -- so using it here would
fail OPEN on precisely the storage faults that should stop us cold. We stat()
directly and treat every OSError that is not "no such file" as halted: if we
cannot determine the state of the kill switch, we are not trading. That does
mean an unmountable /data halts everything, which is correct; cache.db and the
Kite token live there too, so a system that cannot see /data has no business
sending orders.

SCOPE
-----
A global sentinel (`/data/HALT`) stops every channel. A per-channel sentinel
(`/data/HALT.momentum`) stops one. The global sentinel always wins -- a channel
check consults both, so there is no way to leave a channel live during a global
halt.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

#: Directory holding the sentinels. Shared docker volume, mounted by both
#: python-engine and node-gateway.
HALT_DIR = "/data"

#: Global sentinel filename. Kept short and uppercase so it is obvious in an
#: `ls /data` during an incident.
GLOBAL_SENTINEL = "HALT"

#: Recognised trip sources, recorded in the payload for the audit trail. Not
#: enforced -- an unknown value is stored as-is rather than rejected, because
#: refusing to record a trip is worse than recording an odd label.
TRIP_SOURCES = ("operator", "circuit_breaker", "watchdog", "manual_file")


class TradingHalted(Exception):
    """Raised at the broker boundary when a sentinel is present.

    Carries the attribution payload so the caller can tell the operator WHY
    trading stopped without re-reading the file.
    """

    def __init__(self, channel: Optional[str], attribution: dict):
        self.channel = channel
        self.attribution = attribution
        reason = attribution.get("reason") or "no reason recorded"
        by = attribution.get("by") or "unknown"
        scope = attribution.get("scope") or "global"
        super().__init__(
            f"trading halted ({scope}) by {by}: {reason}"
        )


def sentinel_path(channel: Optional[str] = None) -> str:
    """Path of the sentinel for `channel`, or the global sentinel when None."""
    if channel is None:
        return os.path.join(HALT_DIR, GLOBAL_SENTINEL)
    safe = _safe_channel(channel)
    return os.path.join(HALT_DIR, f"{GLOBAL_SENTINEL}.{safe}")


def _safe_channel(channel: str) -> str:
    """Reduce a channel name to something that cannot escape HALT_DIR.

    A channel name reaches this module from config and from Telegram commands.
    `/data/HALT.../../etc/passwd` must not be constructible, and a name that
    normalises to empty must not silently become the GLOBAL sentinel -- that
    would turn a typo in a per-channel clear into an unintended global clear.
    """
    cleaned = "".join(c for c in str(channel).strip().lower() if c.isalnum() or c in "_-")
    if not cleaned:
        raise ValueError(f"channel name is empty after sanitising: {channel!r}")
    return cleaned


def _read_sentinel(path: str) -> Optional[dict]:
    """Return the attribution dict when `path` exists, else None.

    Fail-closed: an unreadable-but-present sentinel, or a stat that fails for
    any reason other than absence, yields a dict (i.e. HALTED). Only a clean
    "file is not there" yields None.
    """
    try:
        os.stat(path)
    except FileNotFoundError:
        return None
    except OSError as exc:
        # Cannot determine the kill switch state. Do not trade.
        logger.error("halt_sentinel_stat_failed", path=path, err=str(exc))
        return {
            "by": "unknown",
            "reason": f"halt sentinel unreadable ({exc.__class__.__name__}); failing closed",
            "tripped_at": None,
            "unreadable": True,
        }

    # Present. Contents are attribution only and can never un-halt.
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read(4096)
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
    except (OSError, ValueError) as exc:
        logger.warning("halt_sentinel_payload_unparsed", path=path, err=str(exc))
        payload = {}

    payload.setdefault("by", "manual_file")
    payload.setdefault("reason", "sentinel present with no recorded reason")
    payload.setdefault("tripped_at", None)
    return payload


def halt_state(channel: Optional[str] = None) -> tuple[bool, Optional[dict]]:
    """Is trading halted for `channel`?

    The global sentinel is consulted first and always wins, so a per-channel
    sentinel can never leave a channel trading during a global halt.

    Returns:
        (halted, attribution). `attribution` is None when not halted, and
        carries a `scope` key of "global" or the channel name when it is.
    """
    payload = _read_sentinel(sentinel_path(None))
    if payload is not None:
        return True, {**payload, "scope": "global"}

    if channel is not None:
        try:
            path = sentinel_path(channel)
        except ValueError as exc:
            # A malformed channel name must not silently resolve to "not
            # halted" -- that is the fail-open we are here to eliminate.
            logger.error("halt_channel_invalid", channel=channel, err=str(exc))
            return True, {
                "by": "unknown",
                "reason": f"invalid halt channel {channel!r}; failing closed",
                "tripped_at": None,
                "scope": str(channel),
            }
        payload = _read_sentinel(path)
        if payload is not None:
            return True, {**payload, "scope": _safe_channel(channel)}

    return False, None


def channel_state(channel: str) -> tuple[bool, Optional[dict]]:
    """State of a channel's OWN sentinel, ignoring the global one.

    `halt_state` deliberately lets the global sentinel win, which is right for
    the enforcement path but wrong for a status display: during a global halt
    every channel would report HALTED and the operator could not see what a
    global clear would leave behind. This answers that question.
    """
    payload = _read_sentinel(sentinel_path(channel))
    if payload is None:
        return False, None
    return True, {**payload, "scope": _safe_channel(channel)}


def assert_not_halted(channel: Optional[str] = None) -> None:
    """Raise `TradingHalted` when a sentinel is present. Call before ordering."""
    halted, attribution = halt_state(channel)
    if halted:
        raise TradingHalted(channel, attribution or {})


def trip(
    reason: str,
    by: str = "operator",
    channel: Optional[str] = None,
) -> dict:
    """Write a sentinel. Idempotent: re-tripping preserves the FIRST trip.

    Preserving the first trip matters because the first reason is the diagnostic
    one. If the daily-loss breaker trips at 10:05 and the drawdown breaker trips
    at 14:20, the operator needs to see 10:05 -- overwriting would erase the
    origin of the incident and leave only its aftershock.

    Raises:
        OSError: if the sentinel cannot be written. A kill switch that silently
            fails to engage is worse than no kill switch, so this is loud.
    """
    path = sentinel_path(channel)

    existing = _read_sentinel(path)
    if existing is not None:
        logger.info(
            "halt_already_tripped",
            path=path, original_by=existing.get("by"),
            original_reason=existing.get("reason"),
        )
        return existing

    payload = {
        "tripped_at": datetime.now(timezone.utc).isoformat(),
        "by": str(by),
        "reason": str(reason)[:500],
        "scope": "global" if channel is None else _safe_channel(channel),
    }
    _atomic_write(path, payload)
    logger.error("halt_tripped", path=path, by=by, reason=reason)
    return payload


def clear(channel: Optional[str] = None) -> bool:
    """Remove a sentinel. Returns True if one was actually removed.

    Clearing the global sentinel does NOT clear per-channel sentinels; each
    scope is cleared explicitly, so "resume everything" cannot be typed by
    accident.
    """
    path = sentinel_path(channel)
    try:
        os.unlink(path)
    except FileNotFoundError:
        return False
    logger.warning("halt_cleared", path=path)
    return True


def _atomic_write(path: str, payload: dict) -> None:
    """Write JSON via temp file + rename.

    Never truncate-then-write. On 2026-07-13 a deploy filled the disk and a
    truncate-on-write zeroed /data/kite_token.json, and the engine ran unarmed
    for a full session. A rename is atomic: the sentinel is either the old
    content or the new one, never an empty file -- and an empty file here would
    still halt, but with no reason recorded.
    """
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".halt-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def describe(channel: Optional[str] = None) -> str:
    """One-line human summary for Telegram / status routes."""
    halted, attribution = halt_state(channel)
    if not halted:
        return "ARMED - no halt sentinel present"
    a = attribution or {}
    when = a.get("tripped_at") or "unknown time"
    return (
        f"HALTED ({a.get('scope', 'global')}) since {when} "
        f"by {a.get('by', 'unknown')}: {a.get('reason', 'no reason recorded')}"
    )
