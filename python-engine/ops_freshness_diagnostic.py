"""Read-only freshness checks over the real login and archive evidence."""
from __future__ import annotations

import json
from contextlib import closing
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


class ChannelState(str, Enum):
    PASS = "PASS"
    STALE = "STALE"
    MISSING = "MISSING"


@dataclass(frozen=True)
class ChannelReport:
    name: str
    state: ChannelState
    age_seconds: int | None
    threshold_seconds: int

    def to_dict(self) -> dict:
        return {"name": self.name, "state": self.state.value, "age_seconds": self.age_seconds,
                "threshold_seconds": self.threshold_seconds}


@dataclass(frozen=True)
class FreshnessDiagnostic:
    channels: tuple[ChannelReport, ...]
    any_stale: bool
    any_missing: bool

    def to_dict(self) -> dict:
        return {"channels": [channel.to_dict() for channel in self.channels],
                "any_stale": self.any_stale, "any_missing": self.any_missing}


def _age_seconds(now: datetime, value: datetime) -> int | None:
    age = int((now - value).total_seconds())
    return age if age >= 0 else None


def _report(name: str, age: int | None, threshold: int) -> ChannelReport:
    state = ChannelState.MISSING if age is None else ChannelState.STALE if age > threshold else ChannelState.PASS
    return ChannelReport(name=name, state=state, age_seconds=age, threshold_seconds=threshold)


def _login_age(token_path: Path, now: datetime) -> int | None:
    """Read the real token file without returning the token itself."""
    try:
        payload = json.loads(token_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not str(payload.get("access_token", "")).strip():
            return None
        if datetime.fromisoformat(str(payload["saved_date_ist"])).date() != now.astimezone(IST).date():
            return None
        return _age_seconds(now, datetime.fromtimestamp(token_path.stat().st_mtime, tz=timezone.utc))
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _public_input_age(archive_root: Path, now: datetime) -> int | None:
    path = archive_root / "partner-collection-attempts.sqlite3"
    if not path.is_file():
        return None
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            row = db.execute("SELECT MAX(public_observed_at_utc) FROM partner_collection_attempts").fetchone()
        if row is None or row[0] is None:
            return None
        observed = datetime.fromisoformat(str(row[0]))
        if observed.tzinfo is None or observed.utcoffset() is None:
            return None
        return _age_seconds(now, observed.astimezone(timezone.utc))
    except (OSError, ValueError, sqlite3.DatabaseError):
        return None


def diagnose_freshness(*, token_path: str | Path, archive_root: str | Path,
                       now: datetime | None = None, max_login_age_seconds: int = 86_400,
                       max_input_age_seconds: int = 1_800) -> FreshnessDiagnostic:
    """Assess actual persisted login and collection evidence without writing either store."""
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    channels = (
        _report("login", _login_age(Path(token_path), current), max_login_age_seconds),
        _report("public_input", _public_input_age(Path(archive_root), current), max_input_age_seconds),
    )
    return FreshnessDiagnostic(channels=channels,
        any_stale=any(channel.state == ChannelState.STALE for channel in channels),
        any_missing=any(channel.state == ChannelState.MISSING for channel in channels))


__all__ = ["ChannelReport", "ChannelState", "FreshnessDiagnostic", "diagnose_freshness"]
