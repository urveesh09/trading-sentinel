"""[WORKFLOW-B.3 2026-09-17] Selected-leg persistence verifier.

Per Workstream B in NEXT_AGENT_PLAN.md:
> Preserve all selected legs through the advice lifecycle
> and management horizon. Verify shared-token accounting,
> terminal registrations, restarts and expiry changes.

This module exposes a pure verifier that checks a
qualification record's ``selected_legs`` against the
``fno_chain_oi`` chain snapshot table:

  - ``verify_selected_legs(...)`` -- returns a list of
    ``SelectedLegFinding`` records (one per leg + an
    aggregate row). PASS / WARN / FAIL classification.
  - ``SelectedLegFinding`` -- per-leg result with
    ``leg_token``, ``leg_symbol``, ``has_chain_snapshot``,
    ``has_quote_at_decision``, ``survives_until``,
    ``shared_token_consistent``.
  - ``SelectedLegsReport`` -- aggregate with the
    findings + an overall status.

The verifier is pure: callers pass the chain snapshot
data + the qualification record. It does not open any
DB connections itself, which keeps the test isolated
from the live store.

Read-only. No DB writes. No DB reads (the caller passes
the data in).
"""
from __future__ import annotations

import dataclasses
import enum
from datetime import datetime, timedelta
from typing import Iterable, Optional


class LegStatus(str, enum.Enum):
    """Status of a single selected leg."""
    PASS = "PASS"  # leg has chain + quote, token unique.
    WARN = "WARN"  # soft gap (e.g. quote missing but chain present).
    FAIL = "FAIL"  # hard gap (e.g. token missing, chain missing).


@dataclasses.dataclass(frozen=True)
class SelectedLegFinding:
    """Per-leg verification result.

    Attributes:
        leg_index: index in the qualification's
            ``selected_legs`` list.
        leg_token: the leg's instrument token.
        leg_symbol: the leg's tradingsymbol (for reporting).
        leg_expiry: the leg's expiry date (ISO).
        has_chain_snapshot: True iff the chain snapshot
            table contains a row for this token at the
            decision time.
        has_quote_at_decision: True iff a quote exists at
            or near the decision timestamp.
        chain_snapshot_count: number of chain rows for this
            token around the decision time.
        shared_token_consistent: True iff this token is
            not registered to multiple (token, expiry,
            strike, option_type) tuples -- i.e. the token
            uniquely identifies the leg.
        status: aggregate LegStatus.
        notes: human-readable notes for the audit log.
    """
    leg_index: int
    leg_token: int
    leg_symbol: str
    leg_expiry: str
    has_chain_snapshot: bool
    has_quote_at_decision: bool
    chain_snapshot_count: int
    shared_token_consistent: bool
    status: LegStatus
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "leg_index": self.leg_index,
            "leg_token": self.leg_token,
            "leg_symbol": self.leg_symbol,
            "leg_expiry": self.leg_expiry,
            "has_chain_snapshot": self.has_chain_snapshot,
            "has_quote_at_decision": self.has_quote_at_decision,
            "chain_snapshot_count": self.chain_snapshot_count,
            "shared_token_consistent": self.shared_token_consistent,
            "status": self.status.value,
            "notes": list(self.notes),
        }


@dataclasses.dataclass(frozen=True)
class SelectedLegsReport:
    """Aggregate selected-legs verification report.

    Attributes:
        qualification_path: source qualification record.
        decision_at: when the decision was made.
        findings: tuple of per-leg findings.
        overall_status: LegStatus -- the worst case across
            all legs.
    """
    qualification_path: str
    decision_at: str
    findings: tuple[SelectedLegFinding, ...]

    @property
    def overall_status(self) -> LegStatus:
        """The worst-case status across all legs."""
        if not self.findings:
            return LegStatus.WARN  # no legs is itself a soft warning.
        worst_order = {
            LegStatus.PASS: 0,
            LegStatus.WARN: 1,
            LegStatus.FAIL: 2,
        }
        return max(self.findings,
                    key=lambda f: worst_order[f.status]).status

    @property
    def fail_count(self) -> int:
        return sum(1 for f in self.findings if f.status == LegStatus.FAIL)

    @property
    def warn_count(self) -> int:
        return sum(1 for f in self.findings if f.status == LegStatus.WARN)

    @property
    def pass_count(self) -> int:
        return sum(1 for f in self.findings if f.status == LegStatus.PASS)

    def to_dict(self) -> dict:
        return {
            "qualification_path": self.qualification_path,
            "decision_at": self.decision_at,
            "overall_status": self.overall_status.value,
            "pass_count": self.pass_count,
            "warn_count": self.warn_count,
            "fail_count": self.fail_count,
            "findings": [f.to_dict() for f in self.findings],
        }


def _leg_token(leg: dict) -> int:
    return int(leg.get("token", 0))


def _check_unique_tokens(legs: list[dict]) -> set[int]:
    """Return the set of tokens that appear more than once
    in the legs list. Shared tokens are a hint of an
    upstream bug (the same instrument_token on multiple
    legs)."""
    counts: dict[int, int] = {}
    for leg in legs:
        token = _leg_token(leg)
        counts[token] = counts.get(token, 0) + 1
    return {t for t, c in counts.items() if c > 1}


def verify_selected_legs(
    *,
    qualification: dict,
    chain_snapshots_by_token: dict[int, list[datetime]],
    quotes_by_token: dict[int, list[datetime]],
    quote_window: timedelta = timedelta(minutes=5),
    decision_at: Optional[datetime] = None,
    qualification_path: str = "<unknown>",
) -> SelectedLegsReport:
    """Verify the selected legs in a qualification record.

    Args:
        qualification: the qualification payload (the dict
            loaded from the qualification decision file).
            Must contain ``candidate.selected_legs`` and
            ``decision_at`` (or ``decision_at`` passed
            directly).
        chain_snapshots_by_token: maps instrument_token ->
            list of chain-snapshot timestamps for that token.
            The caller is responsible for populating this
            from ``fno_chain_oi`` (or the chain archive).
        quotes_by_token: maps instrument_token -> list of
            quote timestamps.
        quote_window: how close to ``decision_at`` a quote
            must be to count as "quote at decision".
        decision_at: override the decision timestamp. If
            None, falls back to ``qualification["decision_at"]``.
        qualification_path: source path for reporting.

    Returns:
        A ``SelectedLegsReport`` with one finding per leg.

    Raises:
        ValueError: if the qualification record is
            malformed.
    """
    candidate = qualification.get("candidate")
    if not isinstance(candidate, dict):
        raise ValueError(
            "qualification must have a 'candidate' dict"
        )
    if "selected_legs" not in candidate:
        raise ValueError(
            "candidate must have a 'selected_legs' list (even if empty)"
        )
    legs = candidate.get("selected_legs")
    if not isinstance(legs, list):
        raise ValueError(
            "candidate.selected_legs must be a list"
        )
    if decision_at is None:
        decision_at_raw = qualification.get("decision_at")
        if decision_at_raw is None:
            raise ValueError(
                "decision_at is required (qualification.decision_at "
                "or kwarg)"
            )
        decision_at = datetime.fromisoformat(str(decision_at_raw))

    duplicate_tokens = _check_unique_tokens(legs)
    findings: list[SelectedLegFinding] = []
    for i, leg in enumerate(legs):
        if not isinstance(leg, dict):
            findings.append(SelectedLegFinding(
                leg_index=i, leg_token=0,
                leg_symbol="?",
                leg_expiry="?",
                has_chain_snapshot=False,
                has_quote_at_decision=False,
                chain_snapshot_count=0,
                shared_token_consistent=False,
                status=LegStatus.FAIL,
                notes=(f"leg {i} is not a dict",),
            ))
            continue
        token = _leg_token(leg)
        symbol = str(leg.get("symbol", "?"))
        expiry = str(leg.get("expiry", "?"))
        notes: list[str] = []

        if token <= 0:
            notes.append("leg has no positive instrument_token")
            findings.append(SelectedLegFinding(
                leg_index=i, leg_token=token,
                leg_symbol=symbol, leg_expiry=expiry,
                has_chain_snapshot=False,
                has_quote_at_decision=False,
                chain_snapshot_count=0,
                shared_token_consistent=token not in duplicate_tokens,
                status=LegStatus.FAIL,
                notes=tuple(notes),
            ))
            continue

        chain_ts = chain_snapshots_by_token.get(token, [])
        quote_ts = quotes_by_token.get(token, [])

        # Has a chain snapshot at or near decision_at?
        chain_in_window = [
            t for t in chain_ts
            if abs((t - decision_at).total_seconds()) <= quote_window.total_seconds()
        ]
        has_chain = len(chain_in_window) > 0

        # Has a quote at or near decision_at?
        quote_in_window = [
            t for t in quote_ts
            if abs((t - decision_at).total_seconds()) <= quote_window.total_seconds()
        ]
        has_quote = len(quote_in_window) > 0

        shared_token_ok = token not in duplicate_tokens

        # Classify.
        if not has_chain:
            notes.append(
                "no chain snapshot within "
                f"{int(quote_window.total_seconds())}s of decision"
            )
            status = LegStatus.FAIL
        elif not has_quote:
            notes.append(
                "chain present but no quote within window"
            )
            status = LegStatus.WARN
        elif not shared_token_ok:
            notes.append(
                f"token {token} appears in multiple legs"
            )
            status = LegStatus.WARN
        else:
            status = LegStatus.PASS

        findings.append(SelectedLegFinding(
            leg_index=i, leg_token=token,
            leg_symbol=symbol, leg_expiry=expiry,
            has_chain_snapshot=has_chain,
            has_quote_at_decision=has_quote,
            chain_snapshot_count=len(chain_in_window),
            shared_token_consistent=shared_token_ok,
            status=status,
            notes=tuple(notes),
        ))

    return SelectedLegsReport(
        qualification_path=qualification_path,
        decision_at=decision_at.isoformat(),
        findings=tuple(findings),
    )


__all__ = [
    "LegStatus",
    "SelectedLegFinding",
    "SelectedLegsReport",
    "verify_selected_legs",
]
