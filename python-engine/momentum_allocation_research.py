"""Read-only allocation research for momentum-paper opportunities (S7a).

The paper book admits accepted signals in arrival order from a fixed pool
(``MOMENTUM_PAPER_FIXED_POOL_V1``); later signals can be skipped as
``capital_exhausted``.  This module replays the *same* candidates -- opened and
capital-skipped, each with a complete verified price path -- under frozen
allocation policies on one common cash book:

* ``FIRST_ARRIVAL_FIXED_POOL_V1`` -- the current rule, sized by the live
  ``momentum_paper.paper_position_size`` against undeployed notional;
* ``FIXED_EQUAL_V1`` -- each admission batch splits available notional equally;
* ``RISK_BUDGET_PROPORTIONAL_V1`` -- risk-sized shares scaled down together to
  fit available notional.

Exits replay the live evaluator through the v1 study simulator; deployed
notional is released leg by leg (partials included), exactly as the live
book's ``entry_price x remaining shares`` falls.  The benchmark is the fixed
configured pool, *not* drawdown-adjusted equity.  No database write, broker,
HTTP, order or message path; qualification is never assessed.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from config import settings
from cost_schedules import equity_intraday_cost_snapshot
from momentum_exit_study import (
    BASELINE_POLICY, DEADLINE_EXACT, ExitStudyError, Quote, StudyEntry, _POLICY_SETTINGS,
    _canonical_bytes, _simulate, _validated_quote_path, write_study_report_once,
)
from engine import calc_zerodha_costs
from momentum_paper import paper_position_size

MANIFEST_SCHEMA = "momentum_allocation_manifest_v1"
REPORT_SCHEMA = "momentum_allocation_report_v1"
FIRST_ARRIVAL = "FIRST_ARRIVAL_FIXED_POOL_V1"
FIXED_EQUAL = "FIXED_EQUAL_V1"
RISK_BUDGET = "RISK_BUDGET_PROPORTIONAL_V1"
POLICIES = (FIRST_ARRIVAL, FIXED_EQUAL, RISK_BUDGET)
# [S7 R5] Capital bases, always reported separately and never mixed:
#   FIXED_POOL       -- the configured paper benchmark (current live paper rule);
#   REALIZED_EQUITY  -- pool + realised net cash, minus deployed notional and
#                       fees reserved at entry (released at exit);
#   REAL_BUDGET      -- capacity at the operator-confirmed real budget only.
FIXED_POOL, REALIZED_EQUITY, REAL_BUDGET = "FIXED_POOL", "REALIZED_EQUITY", "REAL_BUDGET"
_SOURCE_MODULES = ("momentum_allocation_research.py", "momentum_paper.py", "momentum_exit_study.py",
                   "momentum_exits.py", "engine.py", "cost_schedules.py")


@dataclass(frozen=True)
class Candidate:
    """One accepted opportunity with a complete path (opened or capital-skipped)."""
    admission_key: str
    kind: str                 # OPENED | CAPITAL_SKIPPED
    batch_at: datetime        # admission clock; same clock = same competing batch
    arrival_index: int        # order within the original admission batch
    entry: StudyEntry         # shares field is ignored; each policy sizes
    risk_pct: float
    quotes: tuple[Quote, ...]
    batch_id: str = ""        # recorded at admission; "" = legacy clock grouping


def _risk_shares(candidate: Candidate, pool: float) -> int:
    """Uncapped risk-based shares, the same numerator the live rule uses."""
    risk = candidate.entry.entry_price - candidate.entry.stop_loss_initial
    if risk <= 0 or pool <= 0 or candidate.risk_pct <= 0:
        return 0
    return max(0, math.floor((pool * candidate.risk_pct) / risk))


def _size_batch(policy: str, batch: Sequence[Candidate], *, pool: float, available: float) -> dict[str, int]:
    """Return shares per admission key for one batch; never exceeds ``available``."""
    sizes: dict[str, int] = {}
    if policy == FIRST_ARRIVAL:
        remaining = available
        for candidate in sorted(batch, key=lambda item: item.arrival_index):
            shares = paper_position_size(candidate.entry.entry_price, candidate.entry.stop_loss_initial,
                                         pool, candidate.risk_pct, available_capital=remaining)
            sizes[candidate.admission_key] = shares
            remaining -= shares * candidate.entry.entry_price
        return sizes
    ordered = sorted(batch, key=lambda item: (item.entry.ticker, item.admission_key))  # order-invariant
    if policy == FIXED_EQUAL:
        slice_cash = available / len(ordered) if ordered else 0.0
        for candidate in ordered:
            sizes[candidate.admission_key] = max(0, min(
                _risk_shares(candidate, pool), math.floor(slice_cash / candidate.entry.entry_price)))
        return sizes
    if policy == RISK_BUDGET:
        wanted = {item.admission_key: _risk_shares(item, pool) for item in ordered}
        notional = sum(wanted[item.admission_key] * item.entry.entry_price for item in ordered)
        scale = 1.0 if notional <= available or notional <= 0 else available / notional
        for candidate in ordered:
            sizes[candidate.admission_key] = max(0, math.floor(wanted[candidate.admission_key] * scale))
        return sizes
    raise ExitStudyError(f"unknown allocation policy: {policy}")


def replay_allocation(candidates: Sequence[Candidate], *, policy: str, pool: float,
                      max_gap_seconds: int, deadline_policy: str = DEADLINE_EXACT,
                      basis: str = FIXED_POOL) -> dict[str, Any]:
    """Replay one policy on one common book; deterministic and read-only.

    Selection at a batch uses only facts known at that batch (prices, stops,
    risk and the book's capital after earlier releases); a candidate's own
    future path affects only its exit legs, never whether or how much it was
    sized.
    """
    if not math.isfinite(pool) or pool <= 0:
        raise ExitStudyError("pool must be finite and positive")
    if basis not in (FIXED_POOL, REALIZED_EQUITY, REAL_BUDGET):
        raise ExitStudyError(f"unknown capital basis: {basis}")
    outcomes: list[dict[str, Any]] = []
    paths: dict[str, list[Quote]] = {}
    usable: list[Candidate] = []
    for candidate in candidates:
        path, issue = _validated_quote_path(candidate.entry, candidate.quotes, max_gap_seconds, deadline_policy)
        if issue is not None:
            outcomes.append({"admission_key": candidate.admission_key, "ticker": candidate.entry.ticker,
                             "kind": candidate.kind, "state": "PATH_UNAVAILABLE", "reason": issue})
            continue
        paths[candidate.admission_key] = path
        usable.append(candidate)
    batches: dict[tuple[datetime, str], list[Candidate]] = {}
    for candidate in usable:
        batches.setdefault((candidate.batch_at, candidate.batch_id), []).append(candidate)

    # (at, seq, ticker, qty, entry, net, fee_reservation_released)
    releases: list[tuple[datetime, int, str, int, float, float, float]] = []
    sequence = 0
    deployed = peak_deployed = turnover = equity = peak_equity = max_drawdown = costs = 0.0
    reserved_fees = 0.0
    max_concurrent = 0
    max_single_share = 0.0
    held: dict[str, int] = {}
    position_notional: dict[str, float] = {}

    def release_until(clock: datetime | None) -> None:
        nonlocal deployed, equity, peak_equity, max_drawdown, reserved_fees
        while releases and (clock is None or releases[0][0] <= clock):
            _at, _seq, ticker, quantity, entry_price, net, fee_release = heapq.heappop(releases)
            deployed -= quantity * entry_price
            reserved_fees -= fee_release
            held[ticker] -= quantity
            position_notional[ticker] = held[ticker] * entry_price
            if held[ticker] <= 0:
                held.pop(ticker)
                position_notional.pop(ticker, None)
            equity += net
            peak_equity = max(peak_equity, equity)
            max_drawdown = max(max_drawdown, peak_equity - equity)

    for clock, _batch in sorted(batches):
        release_until(clock)
        batch, seen = [], set()
        for item in sorted(batches[(clock, _batch)], key=lambda candidate: candidate.arrival_index):
            # Mirror the live book: a ticker already open, or already earlier in
            # this batch, is not admitted again.
            if item.entry.ticker in held or item.entry.ticker in seen:
                outcomes.append({"admission_key": item.admission_key, "ticker": item.entry.ticker,
                                 "kind": item.kind, "state": "TICKER_ALREADY_HELD", "shares": 0})
                continue
            seen.add(item.entry.ticker)
            batch.append(item)
        # Capital known at this batch: the fixed benchmark, or realised equity
        # net of deployed notional and fees reserved for open positions.
        capital = pool + equity if basis == REALIZED_EQUITY else pool
        available = max(0.0, capital - deployed - (reserved_fees if basis == REALIZED_EQUITY else 0.0))
        sizes = _size_batch(policy, batch, pool=max(capital, 0.0), available=available)
        remaining_for_fees = available
        for candidate in sorted(batch, key=lambda item: item.arrival_index):
            shares = sizes[candidate.admission_key]
            if basis == REALIZED_EQUITY:
                # The position must also fund its own reserved entry fees.
                def _need(qty: int) -> float:
                    return qty * candidate.entry.entry_price + calc_zerodha_costs(
                        candidate.entry.entry_price, candidate.entry.entry_price, qty, is_intraday=True)
                while shares > 0 and _need(shares) > remaining_for_fees + 1e-9:
                    shares -= 1
                if shares > 0:
                    remaining_for_fees -= _need(shares)
            base = {"admission_key": candidate.admission_key, "ticker": candidate.entry.ticker,
                    "kind": candidate.kind, "shares": shares}
            if shares < 1:
                # Capital was binding when the risk rule alone wanted a share.
                state = "CAPITAL_UNAVAILABLE" if _risk_shares(candidate, pool) >= 1 else "ROUNDED_TO_ZERO"
                outcomes.append({**base, "state": state})
                continue
            result = _simulate(replace(candidate.entry, shares=shares), paths[candidate.admission_key], BASELINE_POLICY)
            if result.get("status") != "CLOSED":
                outcomes.append({**base, "state": "UNRESOLVED", "reason": result.get("reason")})
                continue
            notional = shares * candidate.entry.entry_price
            fee_reserve = (calc_zerodha_costs(candidate.entry.entry_price, candidate.entry.entry_price, shares,
                                              is_intraday=True) if basis == REALIZED_EQUITY else 0.0)
            deployed += notional
            reserved_fees += fee_reserve
            turnover += notional
            peak_deployed = max(peak_deployed, deployed)
            held[candidate.entry.ticker] = held.get(candidate.entry.ticker, 0) + shares
            position_notional[candidate.entry.ticker] = held[candidate.entry.ticker] * candidate.entry.entry_price
            max_concurrent = max(max_concurrent, len(held))
            if deployed > 0:
                max_single_share = max(max_single_share, max(position_notional.values()) / deployed)
            for leg in result["legs"]:
                sequence += 1
                quantity = int(leg["quantity"])
                heapq.heappush(releases, (datetime.fromisoformat(leg["at"]), sequence, candidate.entry.ticker,
                                          quantity, candidate.entry.entry_price, float(leg["net_pnl"]),
                                          fee_reserve * quantity / shares))
                costs += float(leg["costs"])
            outcomes.append({**base, "state": "SELECTED", "notional": round(notional, 4),
                             "net_pnl": result["net_pnl"], "exit_reason": result["reason"],
                             "exit_at": result["exit_at"]})
        if deployed > max(capital, 0.0) + 1e-6:  # invariant: the book can never overspend
            raise AssertionError("allocation replay overspent its capital")
    release_until(None)
    selected = [item for item in outcomes if item["state"] == "SELECTED"]
    return {
        "policy": policy, "pool_inr": pool, "capital_basis": basis,
        "pool_label": {FIXED_POOL: "FIXED_CONFIGURED_PAPER_POOL_NOT_DRAWDOWN_ADJUSTED",
                       REALIZED_EQUITY: "REALIZED_EQUITY_NET_OF_DEPLOYED_AND_RESERVED_FEES",
                       REAL_BUDGET: "OPERATOR_CONFIRMED_REAL_BUDGET_CAPACITY"}[basis],
        "max_concurrent_positions": max_concurrent,
        "max_single_position_share_of_deployed": round(max_single_share, 6),
        "candidates": len(candidates), "selected": len(selected),
        "net_pnl": round(equity, 6), "costs": round(costs, 6),
        "max_drawdown": round(max_drawdown, 6), "peak_deployed_inr": round(peak_deployed, 4),
        "turnover_inr": round(turnover, 4),
        "outcomes": sorted(outcomes, key=lambda item: item["admission_key"]),
    }


def _source_fingerprint() -> str:
    here = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for name in _SOURCE_MODULES:
        data = (here / name).read_bytes().replace(b"\r\n", b"\n")
        digest.update(name.encode("utf-8") + b"\0" + hashlib.sha256(data).digest())
    return f"sha256:{digest.hexdigest()}"


def _real_budget() -> float | None:
    value = getattr(settings, "MOMENTUM_REAL_BUDGET_INR", None)
    try:
        value = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return value if value is not None and math.isfinite(value) and value > 0 else None


def _frozen_terms() -> dict[str, Any]:
    return {"policies": list(POLICIES), "pool_inr": float(settings.MOMENTUM_PAPER_BANKROLL),
            "capital_bases": [FIXED_POOL, REALIZED_EQUITY, REAL_BUDGET],
            "real_budget_inr": _real_budget(),
            "evaluator_settings": {name: getattr(settings, name) for name in _POLICY_SETTINGS},
            "cost_schedule": equity_intraday_cost_snapshot(),
            "max_gap_seconds": max(1, min(300, int(settings.MOMENTUM_PAPER_PATH_MAX_GAP_SECONDS))),
            "source_fingerprint": _source_fingerprint()}


def freeze_allocation_manifest(*, experiment_id: str, frozen_at: datetime | None = None) -> dict[str, Any]:
    experiment_id = (experiment_id or "").strip()
    if not experiment_id or len(experiment_id) > 160:
        raise ExitStudyError("experiment_id must be a non-empty <=160-character string")
    frozen_at = frozen_at or datetime.now(timezone.utc)
    if frozen_at.tzinfo is None:
        raise ExitStudyError("frozen_at must be timezone-aware")
    return {"schema": MANIFEST_SCHEMA, "experiment_id": experiment_id, **deepcopy(_frozen_terms()),
            "frozen_at": frozen_at.astimezone(timezone.utc).isoformat(),
            "holdout_rule": "only batches strictly after frozen_at are HOLDOUT"}


def verify_allocation_manifest(manifest: Mapping[str, Any]) -> datetime:
    if not isinstance(manifest, Mapping) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise ExitStudyError(f"manifest schema must be {MANIFEST_SCHEMA}")
    for field, current in _frozen_terms().items():
        if _canonical_bytes({"v": manifest.get(field)}) != _canonical_bytes({"v": current}):
            raise ExitStudyError(f"FROZEN_POLICY_MISMATCH: {field} differs from the frozen manifest")
    try:
        frozen_at = datetime.fromisoformat(str(manifest.get("frozen_at")).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExitStudyError("manifest frozen_at is invalid") from exc
    if frozen_at.tzinfo is None:
        raise ExitStudyError("manifest frozen_at must be timezone-aware")
    return frozen_at


def build_allocation_report(candidates: Sequence[Candidate], manifest: Mapping[str, Any], *,
                            deadline_policy: str, unavailable: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Compare every frozen policy on identical candidates, split by holdout."""
    frozen_at = verify_allocation_manifest(manifest)
    pool, gap = float(manifest["pool_inr"]), int(manifest["max_gap_seconds"])

    real_budget = manifest.get("real_budget_inr")

    def basis_section(chosen: Sequence[Candidate], basis: str, capital: float) -> dict[str, Any]:
        runs = {policy: replay_allocation(chosen, policy=policy, pool=capital, max_gap_seconds=gap,
                                          deadline_policy=deadline_policy, basis=basis) for policy in POLICIES}
        base = runs[FIRST_ARRIVAL]["net_pnl"]
        return {"policies": runs,
                "net_delta_vs_first_arrival": {policy: round(runs[policy]["net_pnl"] - base, 6)
                                               for policy in POLICIES}}

    def section(chosen: Sequence[Candidate]) -> dict[str, Any]:
        fixed = basis_section(chosen, FIXED_POOL, pool)
        return {"candidates": len(chosen),
                # Backward-compatible top level: the fixed-pool benchmark.
                "policies": fixed["policies"], "net_delta_vs_first_arrival": fixed["net_delta_vs_first_arrival"],
                "bases": {
                    FIXED_POOL: fixed,
                    REALIZED_EQUITY: basis_section(chosen, REALIZED_EQUITY, pool),
                    REAL_BUDGET: (basis_section(chosen, REAL_BUDGET, float(real_budget)) if real_budget
                                  else {"state": "UNAVAILABLE_NO_OPERATOR_CONFIRMED_BUDGET"}),
                }}

    holdout = [item for item in candidates if item.batch_at > frozen_at]
    development = [item for item in candidates if item.batch_at <= frozen_at]
    report = {
        "schema": REPORT_SCHEMA, "experiment_id": manifest["experiment_id"],
        "manifest_fingerprint": f"sha256:{hashlib.sha256(_canonical_bytes(dict(manifest))).hexdigest()}",
        "manifest": dict(manifest), "deadline_quote_policy": deadline_policy,
        "unavailable_candidates": list(unavailable),
        "holdout": section(holdout), "development": section(development),
        "qualification": "NOT_ASSESSED", "authorization_effect": "NONE",
        "warning": ("Allocation replay on paper paths. A small or development sample is not evidence "
                    "of better returns; promotion needs a reviewed holdout and a versioned paper pilot."),
    }
    report["report_fingerprint"] = f"sha256:{hashlib.sha256(_canonical_bytes(report)).hexdigest()}"
    return report


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only momentum-paper allocation research")
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--experiment-id", required=True)
    freeze.add_argument("--output", required=True)
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--db", required=True, help="engine SQLite (opened read-only)")
    evaluate.add_argument("--manifest", required=True)
    evaluate.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "freeze":
            value = freeze_allocation_manifest(experiment_id=args.experiment_id)
        else:
            from momentum_paper_path_adapter import build_allocation_candidates
            manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
            built = build_allocation_candidates(args.db)
            value = build_allocation_report(built["candidates"], manifest,
                                            deadline_policy=built["deadline_quote_policy"],
                                            unavailable=built["unavailable_candidates"])
        write_study_report_once(value, args.output)
    except (ExitStudyError, OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(_main())
