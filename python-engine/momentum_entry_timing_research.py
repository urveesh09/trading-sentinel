"""Frozen, broker-free S7b entry-timing hypotheses for momentum evidence.

This module deliberately consumes declared completed-bar/quote evidence only.
It does not import runtime scanners, storage, a broker, HTTP, or an order path.
The two policies are hypotheses, not a replacement for paper admission.
"""
from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from config import settings
from cost_schedules import equity_intraday_cost_snapshot
from momentum_exit_study import (
    DEADLINE_EXACT, DEADLINE_FIRST_WITHIN_GAP, _POLICY_SETTINGS,
    ExitStudyError, Quote, StudyEntry, _simulate, _validated_quote_path,
)


SCHEMA = "momentum_entry_timing_research_v1"
MANIFEST_SCHEMA = "momentum_entry_timing_manifest_v1"
CONTINUATION = "COMPLETED_BAR_CONTINUATION_V1"
PULLBACK = "BOUNDED_PULLBACK_NO_CHASE_V1"
POLICIES = (CONTINUATION, PULLBACK)
_SOURCE_MODULES = ("momentum_entry_timing_research.py", "momentum_exit_study.py", "momentum_exits.py", "engine.py",
                   "cost_schedules.py", "momentum_paper_path_adapter.py", "momentum_path_envelope.py")
# [S7b R5 2026-10-02] Frozen entry-zone rule used by the evidence adapter.
# Pullback floor: VWAP-at-entry when recorded, else close - 0.5R, never below
# stop + 0.25R.  No-chase cap: close + 0.25R.  A pullback must occur within
# 30 minutes of the completed-bar decision or the candidate expires.
ZONE_RULE = {"pullback_depth_r_without_vwap": 0.5, "floor_min_above_stop_r": 0.25,
             "no_chase_cap_r": 0.25, "pullback_max_wait_seconds": 1800}


@dataclass(frozen=True)
class TimingCandidate:
    candidate_id: str
    ticker: str
    thesis_id: str
    state_id: str
    signal_at: datetime
    continuation_at: datetime
    continuation_price: float
    pullback_floor: float
    no_chase_cap: float
    stop_loss: float
    target_1: float
    shares: int
    source_ref: str
    quotes: tuple[Quote, ...]
    reentry_of: tuple[str, str] | None = None
    pullback_deadline: datetime | None = None   # None = no expiry (legacy declared candidates)


def _finite(value: object) -> float:
    if isinstance(value, bool):
        raise ExitStudyError("timing numeric values cannot be bool")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ExitStudyError("timing numeric value is invalid") from exc
    if not math.isfinite(result) or result <= 0:
        raise ExitStudyError("timing numeric value must be finite and positive")
    return result


def _validate(candidate: TimingCandidate) -> None:
    if not all(isinstance(getattr(candidate, name), str) and getattr(candidate, name).strip()
               for name in ("candidate_id", "ticker", "thesis_id", "state_id", "source_ref")):
        raise ExitStudyError("candidate identity fields must be non-empty")
    if candidate.signal_at.tzinfo is None or candidate.continuation_at.tzinfo is None:
        raise ExitStudyError("candidate clocks must be timezone-aware")
    if candidate.continuation_at < candidate.signal_at:
        raise ExitStudyError("continuation cannot precede the completed signal bar")
    values = [_finite(getattr(candidate, field)) for field in (
        "continuation_price", "pullback_floor", "no_chase_cap", "stop_loss", "target_1",
    )]
    continuation, floor, cap, stop, target = values
    if floor > cap or stop >= min(continuation, floor) or target <= cap:
        raise ExitStudyError("entry zone/stop/target is incoherent")
    if isinstance(candidate.shares, bool) or not isinstance(candidate.shares, int) or candidate.shares < 1:
        raise ExitStudyError("candidate shares must be a positive integer")
    if candidate.reentry_of is not None:
        if (not isinstance(candidate.reentry_of, tuple) or len(candidate.reentry_of) != 2
                or not all(isinstance(value, str) and value.strip() for value in candidate.reentry_of)):
            raise ExitStudyError("reentry_of must name a prior thesis and state")
        if candidate.reentry_of == (candidate.thesis_id, candidate.state_id):
            raise ExitStudyError("re-entry requires a new thesis or state")


def _entry(candidate: TimingCandidate, policy: str) -> tuple[datetime, float, tuple[Quote, ...]] | tuple[None, str, tuple[()]]:
    if policy == CONTINUATION:
        return (candidate.continuation_at, candidate.continuation_price,
                tuple(quote for quote in candidate.quotes if quote.observed_at >= candidate.continuation_at))
    if policy != PULLBACK:
        raise ExitStudyError(f"unknown timing policy: {policy}")
    saw_above_cap = False
    for quote in candidate.quotes:
        if quote.observed_at < candidate.continuation_at:
            continue
        if candidate.pullback_deadline is not None and quote.observed_at > candidate.pullback_deadline:
            return None, "PULLBACK_WINDOW_EXPIRED", ()
        if quote.ltp > candidate.no_chase_cap:
            saw_above_cap = True
            continue
        if candidate.pullback_floor <= quote.ltp <= candidate.no_chase_cap:
            return quote.observed_at, quote.ltp, tuple(q for q in candidate.quotes if q.observed_at >= quote.observed_at)
    return None, "NO_CHASE_CAP_EXCEEDED" if saw_above_cap else "NO_PULLBACK_IN_ZONE", ()


def evaluate_entry_timing(candidates: Iterable[TimingCandidate], *, policy: str,
                          max_gap_seconds: int, deadline_policy: str) -> list[dict[str, Any]]:
    """Evaluate one frozen policy without filling a missing entry or re-entry."""
    if policy not in POLICIES:
        raise ExitStudyError(f"unknown timing policy: {policy}")
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in sorted(candidates, key=lambda item: (item.signal_at, item.candidate_id)):
        _validate(candidate)
        identity = (candidate.ticker.upper(), candidate.thesis_id, candidate.state_id)
        if identity in seen:
            rows.append({"candidate_id": candidate.candidate_id, "ticker": candidate.ticker,
                         "state": "REENTRY_DUPLICATE_STATE", "entry": None})
            continue
        seen.add(identity)
        entry_at, entry_value, path = _entry(candidate, policy)
        if entry_at is None:
            rows.append({"candidate_id": candidate.candidate_id, "ticker": candidate.ticker,
                         "state": entry_value, "entry": None})
            continue
        entry = StudyEntry(entry_id=candidate.candidate_id, admission_key=None, source_ref=candidate.source_ref,
                           ticker=candidate.ticker.upper(), entry_at=entry_at, entry_price=float(entry_value),
                           stop_loss_initial=candidate.stop_loss, target_1=candidate.target_1, shares=candidate.shares,
                           atr_14_at_entry=None, vwap_at_entry=None, regime_at_entry=None)
        valid, issue = _validated_quote_path(entry, path, max_gap_seconds, deadline_policy=deadline_policy)
        if issue:
            rows.append({"candidate_id": candidate.candidate_id, "ticker": candidate.ticker,
                         "state": "PATH_UNAVAILABLE", "reason": issue, "entry": {"at": entry_at.isoformat(), "price": entry_value}})
            continue
        result = _simulate(entry, valid, "current_momentum_exit_evaluator_v1")
        rows.append({"candidate_id": candidate.candidate_id, "ticker": candidate.ticker,
                     "state": "COMPLETE" if result["status"] == "CLOSED" else "UNRESOLVED",
                     "entry": {"at": entry_at.isoformat(), "price": entry_value}, "outcome": result})
    return rows


def _fingerprint() -> str:
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for name in _SOURCE_MODULES:
        raw = (root / name).read_bytes().replace(b"\r\n", b"\n")
        digest.update(name.encode() + b"\0" + hashlib.sha256(raw).digest())
    return f"sha256:{digest.hexdigest()}"


def freeze_timing_manifest(*, experiment_id: str, max_gap_seconds: int, deadline_policy: str,
                           frozen_at: datetime) -> dict[str, Any]:
    if not experiment_id or frozen_at.tzinfo is None or not 1 <= int(max_gap_seconds) <= 300:
        raise ExitStudyError("invalid timing freeze terms")
    if deadline_policy not in (DEADLINE_EXACT, DEADLINE_FIRST_WITHIN_GAP):
        raise ExitStudyError("invalid timing deadline policy")
    return {"schema": MANIFEST_SCHEMA, "experiment_id": experiment_id, "policies": list(POLICIES),
            "max_gap_seconds": int(max_gap_seconds), "deadline_policy": deadline_policy,
            "evaluator_settings": deepcopy({name: getattr(settings, name) for name in _POLICY_SETTINGS}),
            "zone_rule": deepcopy(ZONE_RULE),
            "cost_schedule": equity_intraday_cost_snapshot(),
            "source_fingerprint": _fingerprint(), "frozen_at": frozen_at.isoformat(),
            "holdout_rule": "only signals strictly after frozen_at are HOLDOUT"}


def build_timing_report(candidates: Sequence[TimingCandidate], manifest: Mapping[str, Any]) -> dict[str, Any]:
    if manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("policies") != list(POLICIES):
        raise ExitStudyError("invalid timing manifest")
    if manifest.get("source_fingerprint") != _fingerprint():
        raise ExitStudyError("FROZEN_POLICY_MISMATCH: source fingerprint differs")
    expected = {"evaluator_settings": {name: getattr(settings, name) for name in _POLICY_SETTINGS},
                "cost_schedule": equity_intraday_cost_snapshot(), "zone_rule": ZONE_RULE}
    for field, current in expected.items():
        if manifest.get(field) != current:
            raise ExitStudyError(f"FROZEN_POLICY_MISMATCH: {field} differs")
    if manifest.get("deadline_policy") not in (DEADLINE_EXACT, DEADLINE_FIRST_WITHIN_GAP):
        raise ExitStudyError("invalid timing deadline policy")
    try:
        frozen_at = datetime.fromisoformat(str(manifest["frozen_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise ExitStudyError("invalid timing frozen_at") from exc
    if frozen_at.tzinfo is None:
        raise ExitStudyError("invalid timing frozen_at")
    def section(items: Sequence[TimingCandidate]) -> dict[str, Any]:
        return {policy: evaluate_entry_timing(items, policy=policy, max_gap_seconds=int(manifest["max_gap_seconds"]),
                                              deadline_policy=str(manifest["deadline_policy"])) for policy in POLICIES}
    return {"schema": SCHEMA, "manifest": dict(manifest), "development": section([c for c in candidates if c.signal_at <= frozen_at]),
            "holdout": section([c for c in candidates if c.signal_at > frozen_at]), "qualification": "NOT_ASSESSED",
            "authorization_effect": "NONE", "warning": "Timing research is not an entry-policy authorization."}


def timing_candidates_from_db(db_path: str) -> dict[str, Any]:
    """Build timing candidates only from immutable admission evidence (S7b R5).

    Read-only.  Uses opened and capital-skipped admissions whose passive path
    verifies (packet bytes, envelope columns, clocks, gaps, closing quote) via
    the same adapter as the exit study.  Identity: ``thesis_id`` is the
    accepted signal key and ``state_id`` the sealed source-packet hash, so a
    re-entry is only a recorded re-opening and a repeated state is rejected.
    The completed-bar decision is the admission clock; continuation enters at
    the recorded close.  Missing VWAP/stop/target evidence makes a candidate
    unavailable; nothing is guessed.
    """
    from datetime import timedelta
    import sqlite3
    from momentum_paper_path_adapter import _entry_path, _timestamp
    path = Path(db_path)
    if not path.is_file():
        return {"candidates": [], "unavailable": [{"reason": "database_unavailable_or_missing"}],
                "deadline_policy": DEADLINE_FIRST_WITHIN_GAP}
    con = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    candidates, unavailable = [], []
    try:
        columns = {row[1] for row in con.execute("PRAGMA table_info(momentum_paper_path_subscriptions)")}
        if not columns:
            return {"candidates": [], "unavailable": [{"reason": "passive_path_schema_unavailable"}],
                    "deadline_policy": DEADLINE_FIRST_WITHIN_GAP}
        rows = con.execute(
            "SELECT a.id,a.admission_key,a.signal_key,a.ticker,a.outcome,a.recorded_at,a.entry_economics_json,"
            "a.admission_economics_json,a.source_packet_json,a.source_packet_sha256,s.entry_at,"
            "s.study_deadline_at,s.original_shares FROM momentum_paper_admission_outcomes a "
            "JOIN momentum_paper_path_subscriptions s ON s.admission_key=a.admission_key "
            "WHERE a.outcome IN ('opened','zero_shares') ORDER BY a.recorded_at,a.id").fetchall()
        max_gap = max(1, min(300, int(settings.MOMENTUM_PAPER_PATH_MAX_GAP_SECONDS)))
        prior_state: dict[str, tuple[str, str]] = {}
        for row in rows:
            built = _entry_path(con, row, max_gap)
            if isinstance(built, str):
                unavailable.append({"admission_key": row["admission_key"], "reason": built})
                continue
            entry, quotes = built
            try:
                close = _finite(entry["entry_price"])
                stop = _finite(entry["stop_loss_initial"])
                target = _finite(entry["target_1"])
            except ExitStudyError:
                unavailable.append({"admission_key": row["admission_key"], "reason": "entry_terms_unavailable"})
                continue
            risk = close - stop
            vwap = entry.get("vwap_at_entry")
            floor = float(vwap) if isinstance(vwap, (int, float)) and vwap > 0 else \
                close - ZONE_RULE["pullback_depth_r_without_vwap"] * risk
            floor = max(floor, stop + ZONE_RULE["floor_min_above_stop_r"] * risk)
            cap = close + ZONE_RULE["no_chase_cap_r"] * risk
            decided_at = _timestamp(row["recorded_at"])
            thesis_id, state_id = str(row["signal_key"]), str(row["source_packet_sha256"])
            reentry_of = prior_state.get(thesis_id) if ":reopen:" in str(row["admission_key"]) else None
            if reentry_of == (thesis_id, state_id):
                # Same recorded state again: not a new thesis.  Leave it to the
                # evaluator to mark REENTRY_DUPLICATE_STATE, not abort the report.
                reentry_of = None
            prior_state[thesis_id] = (thesis_id, state_id)
            candidates.append(TimingCandidate(
                candidate_id=str(row["admission_key"]), ticker=str(row["ticker"]), thesis_id=thesis_id,
                state_id=state_id,
                signal_at=decided_at, continuation_at=decided_at, continuation_price=close,
                pullback_floor=min(floor, cap), no_chase_cap=cap, stop_loss=stop, target_1=target,
                shares=int(entry["shares"]), source_ref=str(entry["source_ref"]),
                quotes=tuple(Quote(observed_at=datetime.fromisoformat(q["observed_at"]), ltp=float(q["ltp"]))
                             for q in quotes),
                reentry_of=reentry_of,
                pullback_deadline=decided_at + timedelta(seconds=ZONE_RULE["pullback_max_wait_seconds"]),
            ))
    finally:
        con.close()
    return {"candidates": candidates, "unavailable": unavailable, "deadline_policy": DEADLINE_FIRST_WITHIN_GAP}
