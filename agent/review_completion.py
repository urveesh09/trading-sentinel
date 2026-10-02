"""Once-only delivery of a completed optional-AI review to its original alert.

[S10 R3 2026-10-02]  A momentum alert can be sent while its optional review is
still pending.  When that review completes, the operator should see it on the
*same* message -- not a new alert, not a new button.

Contract
- ``register`` persists the original message identity, its exact text and
  keyboard, the review key and a validity bound (the earlier of the EXEC
  callback window and the review's own expiry).
- ``deliver_due`` consumes each completion at most once.  A READY/CACHED
  review inside the window edits the original message, re-sending the same
  keyboard unchanged (Telegram drops an omitted keyboard).  The edit only
  appends an annotation: price, quantity, stop, target and EXEC validity are
  untouched, and nothing can veto an open trade retroactively.
- A window that has passed, a review that ended unavailable/expired, or a
  review state lost to a restart is recorded as a diagnostic and never
  published.  An edit Telegram reports as "not modified" counts as delivered,
  so an ambiguous timeout is safely retried rather than duplicated.
- State is persisted atomically and bounded; this module has no network code
  of its own -- the caller supplies the edit function.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Optional

MAX_ENTRIES = 200
MAX_TEXT = 4096
MAX_ATTEMPTS = 3
TERMINAL = {"DELIVERED", "EXPIRED_NOT_PUBLISHED", "REVIEW_NOT_AVAILABLE", "WORKER_STATE_LOST", "EDIT_FAILED"}
_READY = {"READY", "CACHED"}
_NOT_AVAILABLE = {"EXPIRED", "UNAVAILABLE", "CIRCUIT_OPEN", "QUEUE_FULL", "BUDGET_EXHAUSTED",
                  "BUDGET_STATE_UNAVAILABLE"}


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


class CompletionTracker:
    def __init__(self, path: str, *, now: Optional[Callable[[], datetime]] = None) -> None:
        self._path = Path(path)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._entries: dict[str, dict[str, Any]] = self._load()
        self.counters = {"published": 0, "expired_not_published": 0, "review_not_available": 0,
                         "worker_state_lost": 0, "edit_failed": 0}

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return {str(k): v for k, v in raw.items() if isinstance(v, dict)} if isinstance(raw, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        # Bound retention: keep the newest entries; never drop a pending one first.
        if len(self._entries) > MAX_ENTRIES:
            ordered = sorted(self._entries.items(),
                             key=lambda item: (item[1].get("state") not in TERMINAL, item[1].get("registered_at", "")))
            self._entries = dict(ordered[-MAX_ENTRIES:])
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".completions-", dir=str(self._path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self._entries, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def register(self, *, review_key: str, chat_id: Any, message_id: int, text: str,
                 reply_markup: str, valid_until: datetime) -> None:
        """Remember one alert awaiting its review; the first registration wins."""
        if not review_key or not isinstance(message_id, int) or message_id <= 0:
            raise ValueError("review key and positive message id are required")
        entry_key = f"{review_key}|{message_id}"
        if entry_key in self._entries:
            return
        self._entries[entry_key] = {
            "review_key": review_key, "chat_id": chat_id, "message_id": message_id,
            "text": str(text)[:MAX_TEXT], "reply_markup": reply_markup,
            "valid_until": _iso(valid_until), "registered_at": _iso(self._now()),
            "state": "PENDING", "attempts": 0,
        }
        self._save()

    def deliver_due(self, status_of: Callable[[str], Any], edit: Callable[..., str],
                    annotate: Callable[[Any], str]) -> dict[str, int]:
        """Publish ready completions once; returns this pass's outcome counts."""
        now = self._now()
        outcome = {state: 0 for state in ("published", "expired_not_published", "review_not_available",
                                          "worker_state_lost", "edit_failed", "retry_later")}
        changed = False
        for entry in self._entries.values():
            if entry.get("state") in TERMINAL:
                continue
            submission = status_of(entry["review_key"])
            state = getattr(submission, "state", None)
            if now >= datetime.fromisoformat(entry["valid_until"]):
                entry["state"], key = "EXPIRED_NOT_PUBLISHED", "expired_not_published"
            elif submission is None:
                entry["state"], key = "WORKER_STATE_LOST", "worker_state_lost"
            elif state in _NOT_AVAILABLE or (state in _READY and getattr(submission, "review", None) is None):
                entry["state"], key = "REVIEW_NOT_AVAILABLE", "review_not_available"
            elif state in _READY:
                text = f"{entry['text']}\n\n{annotate(submission.review)}"[:MAX_TEXT]
                result = edit(chat_id=entry["chat_id"], message_id=entry["message_id"], text=text,
                              reply_markup=entry["reply_markup"])
                entry["attempts"] = int(entry.get("attempts", 0)) + 1
                if result in ("OK", "NOT_MODIFIED"):
                    entry["state"], key = "DELIVERED", "published"
                    entry["delivered_at"] = _iso(now)
                elif entry["attempts"] >= MAX_ATTEMPTS:
                    entry["state"], key = "EDIT_FAILED", "edit_failed"
                else:
                    changed, key = True, "retry_later"  # ambiguous/failed: a repeat edit is idempotent
            else:
                continue  # still QUEUED/PENDING
            outcome[key] += 1
            if key in self.counters:
                self.counters[key] += 1
            changed = True
        if changed:
            self._save()
        return outcome

    def entries(self) -> dict[str, dict[str, Any]]:
        return json.loads(json.dumps(self._entries))


__all__ = ["CompletionTracker", "MAX_ATTEMPTS", "TERMINAL"]
