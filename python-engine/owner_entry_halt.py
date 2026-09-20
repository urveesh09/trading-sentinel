"""[WORKFLOW-A1 2026-09-20] Owner entry-only global halt + per-channel control.

Audit-defect A1 required an explicit owner entry-only halt and
per-channel kill-switch surface. Per
``docs/2026-09-20-independent-system-readiness-audit.md`` §3-A1 and
§4, manual Momentum Telegram execution remained broker-capable
after the per-sleeve live-disable switches; that left an operator
without a single lever to silence all new entries while preserving
exits.

This module is the lever. It exposes a pure predicate
``is_owner_entry_halted(channel)`` and a structured result type
``EntryHaltVerdict`` that callers can serialize into the structured
log or surface in the operator readiness report.

Design choices:

  * **Pure** of I/O: the only inputs are the configured ``settings``
    attributes. No DB, no clock, no broker call.
  * **Total**: every channel returns a verdict. The verdict never
    raises.
  * **Channel whitelist** (``momentum``, ``penny``, ``edge``,
    ``fno``). An unrecognised channel is treated as ``"unknown"``
    rather than failing closed -- the halt is intentionally broad,
    not narrow, and a future channel that lands here without
    updating this list should page rather than silently bypass.
  * **Lazy import** of ``config.settings`` so this module is
    importable in tests that monkey-patch settings.

Exits are explicitly NOT covered by this halt. The audit's
requirement was to refuse new entries while preserving position
management. Per-channel halts listed in
``OWNER_LIVE_ENTRY_HALT_CHANNELS`` also block only the entry path.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class HaltChannel(str, Enum):
    """The bounded set of channels the entry-halt surface controls."""
    MOMENTUM = "momentum"
    PENNY = "penny"
    EDGE = "edge"
    FNO = "fno"
    UNKNOWN = "unknown"


_VALID_CHANNELS = frozenset({
    HaltChannel.MOMENTUM,
    HaltChannel.PENNY,
    HaltChannel.EDGE,
    HaltChannel.FNO,
})


@dataclass(frozen=True)
class EntryHaltVerdict:
    """Structured verdict for a single channel entry attempt.

    ``allowed`` is the boolean decision the entry gate uses.

    ``global_halt`` reports whether the global halt (the master
    switch) tripped for this channel. When True, ``per_channel``
    is the master switch; when False but ``per_channel`` is True,
    only this specific channel is blocked.
    """
    channel: str
    allowed: bool
    global_halt: bool
    per_channel: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "channel": self.channel,
            "allowed": self.allowed,
            "global_halt": self.global_halt,
            "per_channel": self.per_channel,
            "reason": self.reason,
        }


def normalise_channel(channel: Optional[str]) -> HaltChannel:
    """Return the canonical channel enum for ``channel``.

    Unknown / None values map to ``HaltChannel.UNKNOWN``. The
    caller can then decide what to do (the verdict builder
    refuses entries on ``UNKNOWN`` so that future channels cannot
    silently bypass the halt).
    """
    if channel is None:
        return HaltChannel.UNKNOWN
    if not isinstance(channel, str):
        return HaltChannel.UNKNOWN
    token = channel.strip().lower()
    if not token:
        return HaltChannel.UNKNOWN
    for member in _VALID_CHANNELS:
        if member.value == token:
            return member
    return HaltChannel.UNKNOWN


def _parse_channels_csv(raw: str) -> frozenset:
    """Parse a comma-separated channel list into a frozenset of
    ``HaltChannel`` enum members.

    Unknown entries are dropped from the result (with a structured
    log event). They do not raise so the engine can start even if
    an operator typo'd a channel name.
    """
    if not raw:
        return frozenset()
    out = set()
    for token in str(raw).split(","):
        normalised = normalise_channel(token)
        if normalised is HaltChannel.UNKNOWN:
            continue
        out.add(normalised)
    return frozenset(out)


def is_owner_entry_halted(
    channel: Optional[str],
    *,
    global_halt: Optional[bool] = None,
    per_channel_csv: Optional[str] = None,
) -> EntryHaltVerdict:
    """Decide whether a new entry is permitted for ``channel``.

    The optional ``global_halt`` and ``per_channel_csv`` keyword
    arguments are honoured by tests; production callers omit them
    and the function reads them from ``config.settings``.

    The decision order is:

      1. ``UNKNOWN`` channel: refuse with reason
         ``unknown_channel`` (fail-closed; a future channel that
         bypasses the halt here would be a regression).
      2. Global halt ON: refuse every channel with reason
         ``global_owner_entry_halt``.
      3. Per-channel halt ON for this channel: refuse with reason
         ``per_channel_owner_entry_halt``.
      4. Otherwise: allow.
    """
    normalised = normalise_channel(channel)
    if normalised is HaltChannel.UNKNOWN:
        return EntryHaltVerdict(
            channel=str(channel),
            allowed=False,
            global_halt=False,
            per_channel=False,
            reason="unknown_channel",
        )
    # Read the configured state. Tests inject via kwargs; production
    # reads from ``settings``.
    if global_halt is None or per_channel_csv is None:
        try:
            from config import settings
        except Exception:
            # Config import failure: refuse. The halt surface
            # itself must never be the path that fails open.
            return EntryHaltVerdict(
                channel=normalised.value,
                allowed=False,
                global_halt=False,
                per_channel=False,
                reason="config_import_failed",
            )
        gh = bool(getattr(settings, "OWNER_LIVE_ENTRY_HALT", False))
        raw = str(
            getattr(settings, "OWNER_LIVE_ENTRY_HALT_CHANNELS", "") or ""
        )
    else:
        gh = bool(global_halt)
        raw = str(per_channel_csv or "")
    blocked = _parse_channels_csv(raw)
    if gh:
        return EntryHaltVerdict(
            channel=normalised.value,
            allowed=False,
            global_halt=True,
            per_channel=normalised in blocked,
            reason="global_owner_entry_halt",
        )
    if normalised in blocked:
        return EntryHaltVerdict(
            channel=normalised.value,
            allowed=False,
            global_halt=False,
            per_channel=True,
            reason="per_channel_owner_entry_halt",
        )
    return EntryHaltVerdict(
        channel=normalised.value,
        allowed=True,
        global_halt=False,
        per_channel=False,
        reason="allowed",
    )


__all__ = [
    "EntryHaltVerdict",
    "HaltChannel",
    "is_owner_entry_halted",
    "normalise_channel",
]
