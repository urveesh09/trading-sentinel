#!/usr/bin/env python3
"""[WORKFLOW-E.3 2026-09-17] Hedge interpretation helper.

Per Workstream E in NEXT_AGENT_PLAN.md:
> Hedge-first must have an explicit interpretation.
> Conditional protection states the exposure assumption and
> coverage; market directional spreads are not automatically
> personalized hedges. Ask for exposure details only if
> personalized protection is requested. Do not describe an
> unconfirmed action as taken/closed.

This helper classifies a hedge message as one of three
buckets:

  PERSONALIZED_PROTECTION   The plan explicitly assumes the
                            operator holds the underlying and
                            is hedging that exposure
                            (ProtectivePut, Collar, CoveredCall).

  DIRECTIONAL_SPREAD        The plan is a market view expressed
                            as an option spread (BullPutSpread,
                            BearCallSpread, IronCondor) -- it is
                            NOT a hedge of an existing position.

  UNCLEAR                   Cannot be classified with the
                            available information. The partner
                            MUST ask for the exposure assumption
                            before acting.

Read-only. Never places orders. Never sends Telegram.

Usage:
    # Interpret a hedge message from a JSON file.
    python scripts/interpret_hedge_message.py path/to/hedge.json

    # JSON output for piping into the audit pipeline.
    python scripts/interpret_hedge_message.py hedge.json --json

    # Exit code: 0 (classified) / 2 (UNCLEAR -- partner must ask).
"""
from __future__ import annotations

import argparse
import dataclasses
import enum
import json
import sys
from pathlib import Path
from typing import Any


class Interpretation(str, enum.Enum):
    """Classification of a hedge message."""
    PERSONALIZED_PROTECTION = "PERSONALIZED_PROTECTION"
    DIRECTIONAL_SPREAD = "DIRECTIONAL_SPREAD"
    UNCLEAR = "UNCLEAR"

    def exit_code(self) -> int:
        # UNCLEAR means the partner MUST ask for exposure
        # before acting. That's a BLOCKER (exit 2) for the
        # dispatch pipeline.
        if self == Interpretation.UNCLEAR:
            return 2
        return 0


# Strategies that imply "operator holds the underlying" --
# they only make sense as personalized protection.
_PERSONAL_PROTECTION_STRATEGIES: frozenset[str] = frozenset({
    "ProtectivePutPlan",
    "CollarPlan",
    "CoveredCallPlan",
    "protective_put",
    "collar",
    "covered_call",
    "protective_put_plan",
    "collar_plan",
    "covered_call_plan",
})

# Strategies that are market-view expressions of direction.
# They are NOT automatic personalized hedges.
_DIRECTIONAL_STRATEGIES: frozenset[str] = frozenset({
    "BullPutSpreadPlan",
    "BearCallSpreadPlan",
    "IronCondorPlan",
    "LongStraddlePlan",
    "LongStranglePlan",
    "bull_put_spread",
    "bear_call_spread",
    "iron_condor",
    "long_straddle",
    "long_strangle",
    "bull_put_spread_plan",
    "bear_call_spread_plan",
    "iron_condor_plan",
    "long_straddle_plan",
    "long_strangle_plan",
})


@dataclasses.dataclass(frozen=True)
class InterpretationFinding:
    """One row of the interpretation report.

    Attributes:
        interpretation: PERSONALIZED_PROTECTION /
            DIRECTIONAL_SPREAD / UNCLEAR.
        strategy: the strategy name from the message (raw).
        hedge_ratio: the hedge_ratio field (if present) --
            for personalized protection, a ratio of 0 is
            suspicious (it would mean no protection).
        covered_units: units the operator already holds (if
            the message states them).
        protected_units: units the hedge covers (if stated).
        reason: short human-readable explanation.
        evidence_paths: which fields were used to classify.
        missing_fields: which fields would have helped but
            were absent.
    """
    interpretation: Interpretation
    strategy: str
    hedge_ratio: float | None
    covered_units: int | None
    protected_units: int | None
    reason: str
    evidence_paths: tuple[str, ...]
    missing_fields: tuple[str, ...] = ()


def _find_present(card: dict, *paths: str) -> Any:
    """Return the value at the first existing dotted path,
    or None if none exist. Treats ``_MISSING`` semantics
    by returning the first path whose get() returns something
    present (not None and not empty string)."""
    for p in paths:
        cur: Any = card
        ok = True
        for part in p.split("."):
            if "[" in part:
                field, rest = part.split("[", 1)
                idx_str = rest.rstrip("]")
                try:
                    idx = int(idx_str)
                except ValueError:
                    ok = False
                    break
                if field and cur is not None:
                    cur = cur.get(field) if isinstance(cur, dict) else None
                if not isinstance(cur, list) or idx >= len(cur):
                    ok = False
                    break
                cur = cur[idx]
            else:
                if not isinstance(cur, dict):
                    ok = False
                    break
                cur = cur.get(part)
            if cur is None:
                ok = False
                break
        if ok and cur is not None:
            return cur, p
    return None, None


def _strategy_name(card: dict) -> str:
    """Extract the strategy name from a hedge message.

    The plan doc and ``hedge_strategies.py`` show two naming
    conventions: PascalCase (e.g. ``ProtectivePutPlan``) and
    snake_case (e.g. ``protective_put_plan``). We accept both.
    """
    for path in ("strategy", "plan_strategy", "advisory.strategy",
                  "hedge_plan.strategy", "kind"):
        val, found = _find_present(card, path)
        if found:
            return str(val).strip()
    return ""


def _ratio(card: dict) -> float | None:
    """Pull the hedge_ratio (a 0.0-1.0 fraction) from the
    card. Used to detect 'personalized but no actual
    protection' (ratio = 0)."""
    val, found = _find_present(card, "hedge_ratio", "ratio",
                                  "coverage_ratio", "protected_fraction")
    if not found:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _units(card: dict, paths: tuple[str, ...]) -> int | None:
    """Pull an integer unit count from one of several paths."""
    val, found = _find_present(card, *paths)
    if not found:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def interpret_hedge(card: Any) -> InterpretationFinding:
    """Classify a hedge message.

    Classification rules (in order):
      1. If strategy is in PERSONAL_PROTECTION_STRATEGIES ->
         PERSONALIZED_PROTECTION.
      2. If strategy is in DIRECTIONAL_STRATEGIES ->
         DIRECTIONAL_SPREAD.
      3. If strategy is empty / unknown -> UNCLEAR.
      4. Even if the strategy is personalized, hedge_ratio==0
         is suspicious: the protection would have no effect.
         We surface this as DIRECTIONAL_SPREAD (it cannot be
         a meaningful hedge).
    """
    strategy = ""
    hedge_ratio: float | None = None
    covered_units: int | None = None
    protected_units: int | None = None
    evidence: list[str] = []
    missing: list[str] = []

    if not isinstance(card, dict):
        return InterpretationFinding(
            interpretation=Interpretation.UNCLEAR,
            strategy="",
            hedge_ratio=None,
            covered_units=None,
            protected_units=None,
            reason=(
                f"hedge message is not a dict (got "
                f"{type(card).__name__})"
            ),
            evidence_paths=(),
            missing_fields=("strategy", "hedge_ratio",
                             "covered_units", "protected_units"),
        )

    strategy = _strategy_name(card)
    if strategy:
        evidence.append("strategy")

    hedge_ratio = _ratio(card)
    if hedge_ratio is not None:
        evidence.append("hedge_ratio")

    covered_units = _units(card, ("covered_units", "held_units",
                                    "underlying_position_units",
                                    "exposure_units"))
    if covered_units is not None:
        evidence.append("covered_units")

    protected_units = _units(card, ("protected_units", "option_units",
                                      "hedge_units"))
    if protected_units is not None:
        evidence.append("protected_units")

    # Rule 1: Personalized protection strategies.
    if strategy in _PERSONAL_PROTECTION_STRATEGIES:
        # If hedge_ratio is 0, the protection has no effect.
        if hedge_ratio == 0.0:
            return InterpretationFinding(
                interpretation=Interpretation.DIRECTIONAL_SPREAD,
                strategy=strategy,
                hedge_ratio=hedge_ratio,
                covered_units=covered_units,
                protected_units=protected_units,
                reason=(
                    f"strategy '{strategy}' implies personalized "
                    f"protection, but hedge_ratio is 0.0 -- the "
                    f"protection has no effect; treat as a "
                    f"directional spread."
                ),
                evidence_paths=tuple(evidence),
                missing_fields=(),
            )
        # Check we have at least one of covered/protected units.
        if covered_units is None and protected_units is None:
            missing.append("covered_units OR protected_units")
        return InterpretationFinding(
            interpretation=Interpretation.PERSONALIZED_PROTECTION,
            strategy=strategy,
            hedge_ratio=hedge_ratio,
            covered_units=covered_units,
            protected_units=protected_units,
            reason=(
                f"strategy '{strategy}' is a personalized "
                f"protection: the operator holds the underlying "
                f"and this plan hedges that exposure."
            ),
            evidence_paths=tuple(evidence),
            missing_fields=tuple(missing),
        )

    # Rule 2: Directional spreads.
    if strategy in _DIRECTIONAL_STRATEGIES:
        if hedge_ratio is not None and hedge_ratio > 0.0:
            # Suspicious: a directional spread with hedge_ratio
            # > 0 doesn't make sense -- spreads don't hedge
            # a position, they express a view.
            return InterpretationFinding(
                interpretation=Interpretation.UNCLEAR,
                strategy=strategy,
                hedge_ratio=hedge_ratio,
                covered_units=covered_units,
                protected_units=protected_units,
                reason=(
                    f"strategy '{strategy}' is a directional "
                    f"spread, but hedge_ratio={hedge_ratio} > 0 "
                    f"suggests the operator believes it hedges a "
                    f"position. Clarify before treating as either."
                ),
                evidence_paths=tuple(evidence),
                missing_fields=("covered_units",),
            )
        return InterpretationFinding(
            interpretation=Interpretation.DIRECTIONAL_SPREAD,
            strategy=strategy,
            hedge_ratio=hedge_ratio,
            covered_units=covered_units,
            protected_units=protected_units,
            reason=(
                f"strategy '{strategy}' is a directional spread; "
                f"it expresses a market view, not a personalized "
                f"hedge of an existing position."
            ),
            evidence_paths=tuple(evidence),
            missing_fields=(),
        )

    # Rule 3: empty / unknown strategy -> UNCLEAR.
    if not strategy:
        missing.append("strategy")
    return InterpretationFinding(
        interpretation=Interpretation.UNCLEAR,
        strategy=strategy,
        hedge_ratio=hedge_ratio,
        covered_units=covered_units,
        protected_units=protected_units,
        reason=(
            "strategy is empty or unrecognized; cannot classify "
            "as personalized protection or directional spread. "
            "The partner MUST ask for the exposure assumption "
            "before acting."
        ),
        evidence_paths=tuple(evidence),
        missing_fields=tuple(missing),
    )


def finding_as_dict(f: InterpretationFinding) -> dict:
    """Serialize an InterpretationFinding to JSON."""
    return {
        "interpretation": f.interpretation.value,
        "strategy": f.strategy,
        "hedge_ratio": f.hedge_ratio,
        "covered_units": f.covered_units,
        "protected_units": f.protected_units,
        "reason": f.reason,
        "evidence_paths": list(f.evidence_paths),
        "missing_fields": list(f.missing_fields),
    }


def format_report(f: InterpretationFinding) -> str:
    """Render a single finding as human-readable text."""
    lines = [
        "# Hedge interpretation",
        "# -------------------",
        f"# interpretation: {f.interpretation.value}",
        f"# strategy:      {f.strategy or '<empty>'}",
        f"# hedge_ratio:   {f.hedge_ratio}",
        f"# covered_units: {f.covered_units}",
        f"# protected_units: {f.protected_units}",
        "",
        f.reason,
    ]
    if f.evidence_paths:
        lines.append("")
        lines.append(f"Evidence used: {', '.join(f.evidence_paths)}")
    if f.missing_fields:
        lines.append("")
        lines.append(
            f"Missing fields: {', '.join(f.missing_fields)} "
            "-- partner should ask for these before acting."
        )
    return "\n".join(lines) + "\n"


def _load_message(path_arg: str) -> Any:
    """Load a hedge message from a file path or stdin (``-``)."""
    if path_arg == "-":
        return json.loads(sys.stdin.read())
    path = Path(path_arg)
    if not path.is_file():
        print(
            f"interpret_hedge_message: not a file: {path}",
            file=sys.stderr,
        )
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(
            f"interpret_hedge_message: invalid JSON: {exc}",
            file=sys.stderr,
        )
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("card",
                        help="path to hedge message JSON, or '-' for stdin")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON to stdout")
    args = parser.parse_args(argv)
    card = _load_message(args.card)
    if card is None:
        return 2
    finding = interpret_hedge(card)
    if args.json:
        sys.stdout.write(json.dumps(finding_as_dict(finding), indent=2) + "\n")
    else:
        sys.stdout.write(format_report(finding))
    return finding.interpretation.exit_code()


__all__ = [
    "Interpretation",
    "InterpretationFinding",
    "interpret_hedge",
    "finding_as_dict",
    "format_report",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
