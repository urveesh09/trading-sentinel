"""Frozen, read-only paired experiments for single-leg F&O exits (S6b).

The baseline replays the *live* ladder (``fno_exit_rules.evaluate_single_leg_exit``)
over paired futures/option observations, settling exactly as the paper path
does: fill at the exit basis (best bid, else LTP), live option charges and live R
(net / entry premium x FNO_STOP_PREMIUM_PCT x quantity).  One frozen candidate
is compared on the identical path.  A read-only adapter builds packets from the
research quote archive.

Inert research: no database writes, broker, HTTP, scheduler, order or message
dependency and no runtime caller.  Equity momentum studies and defined-risk
spreads are separate (different R denominators).  Qualification is never
assessed; a positive sample authorizes nothing.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, time, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from config import settings
from cost_schedules import options_cost_snapshot
from fno_exit_rules import evaluate_single_leg_exit, live_single_leg_exit_params
from exit_experiment_metrics import paired_deltas as _paired_deltas, policy_summary as _policy_summary
from momentum_exit_study import ExitStudyError, _canonical_bytes, write_study_report_once

IST = ZoneInfo("Asia/Kolkata")
INPUT_SCHEMA = "fno_single_leg_exit_study_input_v1"
MANIFEST_SCHEMA = "fno_single_leg_exit_experiment_manifest_v1"
REPORT_SCHEMA = "fno_single_leg_exit_experiment_report_v1"
BASELINE_POLICY = "live_single_leg_exit_ladder_v1"
PARTIAL_POLICY = "fno_partial_at_target_v1"
EXTENSION_POLICY = "fno_confirmed_time_extension_v1"
COST_MULTIPLIERS = (1.0, 1.5, 2.0)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_PACKET_BYTES = 16 * 1024 * 1024
_MAX_ENTRIES = 500
_MAX_OBSERVATIONS = 250_000
_SOURCE_MODULES = ("fno_exit_rules.py", "fno_exit_experiment.py", "fno_costs.py", "exit_experiment_metrics.py", "cost_schedules.py")

CANDIDATE_POLICIES: dict[str, dict[str, Any]] = {
    PARTIAL_POLICY: {
        "description": "bank floor(lots/2) lots at the bid when the target arms the trail",
        "bank_fraction_of_lots": 0.5,
        "fewer_than_two_lots": "identical_to_baseline",
    },
    EXTENSION_POLICY: {
        "description": "defer a live time stop while the underlying thesis is not failing",
        "min_underlying_progress_r": 0.0,
        "max_pullback_from_best_r": 0.5,
        "min_basis_over_premium_stop": 1.10,
        "other_exits": "unchanged_live_ladder",
    },
}


class FnoExitStudyError(ExitStudyError):
    """The input cannot support an honest F&O exit study."""


@dataclass(frozen=True)
class FnoEntry:
    entry_id: str
    position_ref: str | None
    source_ref: str
    tradingsymbol: str
    option_token: int
    direction: str
    quantity: int
    lot_size: int
    entry_time: datetime
    entry_premium: float
    entry_underlying: float
    stop_underlying: float
    target_underlying: float
    premium_stop: float
    atr_at_entry: float | None


@dataclass(frozen=True)
class Observation:
    observed_at: datetime
    fut_price: float | None
    exit_basis: float


def _stamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise FnoExitStudyError(f"{field} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FnoExitStudyError(f"{field} must be a valid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FnoExitStudyError(f"{field} must include a timezone offset")
    return parsed.astimezone(IST)


def _positive(value: object, field: str) -> float:
    if isinstance(value, bool):
        raise FnoExitStudyError(f"{field} must be finite and positive")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FnoExitStudyError(f"{field} must be finite and positive") from exc
    if not math.isfinite(number) or number <= 0:
        raise FnoExitStudyError(f"{field} must be finite and positive")
    return number


def _int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FnoExitStudyError(f"{field} must be a positive integer")
    return value


def _entry(raw: object) -> FnoEntry:
    if not isinstance(raw, dict):
        raise FnoExitStudyError("entry must be an object")
    entry_id = str(raw.get("entry_id") or "").strip()
    if not entry_id or len(entry_id) > 160:
        raise FnoExitStudyError("entry.entry_id must be a non-empty <=160-character string")
    source_ref = raw.get("source_ref")
    if not isinstance(source_ref, str) or not _SHA256.fullmatch(source_ref):
        raise FnoExitStudyError("entry.source_ref must be a sha256: provenance reference")
    direction = raw.get("direction")
    if direction not in ("LONG", "SHORT"):
        raise FnoExitStudyError("entry.direction must be LONG or SHORT")
    quantity, lot_size = _int(raw.get("quantity"), "entry.quantity"), _int(raw.get("lot_size"), "entry.lot_size")
    if quantity % lot_size:
        raise FnoExitStudyError("entry.quantity must be a whole number of lots")
    entry_u = _positive(raw.get("entry_underlying"), "entry.entry_underlying")
    stop_u = _positive(raw.get("stop_underlying"), "entry.stop_underlying")
    target_u = _positive(raw.get("target_underlying"), "entry.target_underlying")
    long_view = direction == "LONG"
    if (stop_u >= entry_u or target_u <= entry_u) if long_view else (stop_u <= entry_u or target_u >= entry_u):
        raise FnoExitStudyError("entry stop/target geometry does not match direction")
    premium = _positive(raw.get("entry_premium"), "entry.entry_premium")
    premium_stop = _positive(raw.get("premium_stop"), "entry.premium_stop")
    if premium_stop >= premium:
        raise FnoExitStudyError("entry.premium_stop must be below entry.entry_premium")
    atr = raw.get("atr_at_entry")
    symbol = str(raw.get("tradingsymbol") or "").strip()
    if not symbol or len(symbol) > 64:
        raise FnoExitStudyError("entry.tradingsymbol is required")
    position_ref = raw.get("position_ref")
    return FnoEntry(
        entry_id=entry_id, position_ref=str(position_ref) if position_ref is not None else None,
        source_ref=source_ref, tradingsymbol=symbol,
        option_token=_int(raw.get("option_token"), "entry.option_token"), direction=direction,
        quantity=quantity, lot_size=lot_size, entry_time=_stamp(raw.get("entry_time"), "entry.entry_time"),
        entry_premium=premium, entry_underlying=entry_u, stop_underlying=stop_u, target_underlying=target_u,
        premium_stop=premium_stop, atr_at_entry=_positive(atr, "entry.atr_at_entry") if atr is not None else None,
    )


def load_fno_exit_packet(path: str | os.PathLike[str]) -> tuple[dict, list[FnoEntry], dict[str, list[Observation]], str]:
    """Read and validate a bounded immutable packet; return its byte digest."""
    try:
        raw_bytes = Path(path).read_bytes()
    except OSError as exc:
        raise FnoExitStudyError(f"study input is unreadable: {exc}") from exc
    if not raw_bytes or len(raw_bytes) > _MAX_PACKET_BYTES:
        raise FnoExitStudyError("study input must be non-empty and within 16 MiB")
    try:
        packet = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FnoExitStudyError("study input must be UTF-8 JSON") from exc
    if not isinstance(packet, dict) or packet.get("schema") != INPUT_SCHEMA:
        raise FnoExitStudyError(f"study input schema must be {INPUT_SCHEMA}")
    if not str(packet.get("study_id") or "").strip():
        raise FnoExitStudyError("study_id is required")
    gap = packet.get("max_observation_gap_seconds")
    if isinstance(gap, bool) or not isinstance(gap, int) or not 1 <= gap <= 300:
        raise FnoExitStudyError("max_observation_gap_seconds must be an integer from 1 through 300")
    entries_raw = packet.get("entries")
    if not isinstance(entries_raw, list) or not entries_raw or len(entries_raw) > _MAX_ENTRIES:
        raise FnoExitStudyError("entries must be a non-empty bounded array")
    entries = [_entry(item) for item in entries_raw]
    if len({entry.entry_id for entry in entries}) != len(entries):
        raise FnoExitStudyError("entry_id values must be unique")
    observations_raw = packet.get("observations")
    if not isinstance(observations_raw, list) or len(observations_raw) > _MAX_OBSERVATIONS:
        raise FnoExitStudyError("observations must be a bounded array")
    grouped: dict[str, list[Observation]] = {entry.entry_id: [] for entry in entries}
    for row in observations_raw:
        if not isinstance(row, dict) or row.get("entry_id") not in grouped:
            raise FnoExitStudyError("observation must reference a declared entry")
        fut = row.get("fut_price")
        basis = row.get("exit_basis")
        if isinstance(basis, bool) or not isinstance(basis, (int, float)) or not math.isfinite(basis) or basis < 0:
            raise FnoExitStudyError("observation.exit_basis must be a finite non-negative number")
        grouped[row["entry_id"]].append(Observation(
            observed_at=_stamp(row.get("observed_at"), "observation.observed_at"),
            fut_price=_positive(fut, "observation.fut_price") if fut is not None else None,
            exit_basis=float(basis),
        ))
    return packet, entries, grouped, f"sha256:{hashlib.sha256(raw_bytes).hexdigest()}"


def _hard_flat_at(entry: FnoEntry) -> datetime:
    minute = int(settings.FNO_HARD_FLAT_MIN)
    return datetime.combine(entry.entry_time.date(), time(minute // 60, minute % 60), tzinfo=IST)


def _validated_path(entry: FnoEntry, observations: Sequence[Observation], max_gap: int) -> tuple[list[Observation], str | None]:
    hard_flat = _hard_flat_at(entry)
    if entry.entry_time >= hard_flat:
        return [], "entry_at_or_after_hard_flat"
    path: list[Observation] = []
    previous: Observation | None = None
    reached_hard_flat = False
    for item in observations:
        if item.observed_at.date() != entry.entry_time.date():
            return [], "observation_crosses_session"
        if item.observed_at <= entry.entry_time:
            return [], "observation_not_after_entry"
        if previous is not None:
            if item.observed_at <= previous.observed_at:
                return [], "observation_clock_not_strictly_increasing"
            if (item.observed_at - previous.observed_at).total_seconds() > max_gap:
                return [], "observation_gap_exceeds_declared_maximum"
        previous = item
        path.append(item)
        if item.observed_at >= hard_flat:
            reached_hard_flat = True
            break
    if not path:
        return [], "no_observations"
    if (path[0].observed_at - entry.entry_time).total_seconds() > max_gap:
        return [], "initial_observation_gap_exceeds_declared_maximum"
    if not reached_hard_flat:
        return [], "no_observation_at_or_after_hard_flat"
    return path, None


COST_MODEL = "fno_split_entry_once_exit_per_leg_v1"


def _side_cost(premium: float, quantity: int, *, side: str) -> float:
    """One order's charges from the frozen options schedule.

    ``calc_fno_costs`` charges a whole round trip (two flat orders plus buy
    stamp duty).  A scaled exit has one entry order and several exit orders,
    so entry-side charges are applied once and exit-side charges per exit
    order.  For a single full exit the two sides sum exactly to
    ``calc_fno_costs`` (proved by a regression), so baseline accounting is
    unchanged.
    """
    rates = options_cost_snapshot()["rates"]
    value = premium * quantity
    brokerage = float(rates["brokerage_flat_per_order"])
    exchange = float(rates["exchange_pct"]) * value
    sebi = float(rates["sebi_pct"]) * value
    ipft = float(rates.get("ipft_pct", 0.0)) * value
    gst = float(rates["gst_pct"]) * (brokerage + exchange + sebi + ipft)
    if side == "BUY":
        return brokerage + exchange + sebi + ipft + gst + float(rates["stamp_duty_buy_pct"]) * value
    return brokerage + exchange + sebi + ipft + gst + float(rates["stt_sell_pct"]) * value


def _leg(entry: FnoEntry, quantity: int, price: float, reason: str, at: datetime,
         *, include_entry_order: bool) -> dict[str, Any]:
    gross = (price - entry.entry_premium) * quantity
    costs = _side_cost(price, quantity, side="SELL")
    if include_entry_order:
        # The single entry order (full quantity) is charged on the first exit leg only.
        costs += _side_cost(entry.entry_premium, entry.quantity, side="BUY")
    return {"at": at.isoformat(), "reason": reason, "quantity": quantity, "exit_price": round(price, 6),
            "gross_pnl": round(gross, 6), "costs": round(costs, 6), "net_pnl": round(gross - costs, 6)}


def _position(entry: FnoEntry) -> SimpleNamespace:
    return SimpleNamespace(
        direction=entry.direction, entry_underlying=entry.entry_underlying,
        stop_underlying=entry.stop_underlying, target_underlying=entry.target_underlying,
        atr_at_entry=entry.atr_at_entry, entry_premium=entry.entry_premium,
        premium_stop=entry.premium_stop, entry_time=entry.entry_time.isoformat(),
        trail_active=0, trail_stop_underlying=None, best_underlying=None,
    )


def _extension_confirmed(entry: FnoEntry, obs: Observation, best: float, params: Mapping[str, Any]) -> bool:
    if obs.fut_price is None:
        return False
    sign = 1.0 if entry.direction == "LONG" else -1.0
    r_points = abs(entry.entry_underlying - entry.stop_underlying)
    progress = sign * (obs.fut_price - entry.entry_underlying)
    pullback = sign * (best - obs.fut_price)
    return (progress >= float(params["min_underlying_progress_r"]) * r_points
            and pullback <= float(params["max_pullback_from_best_r"]) * r_points
            and obs.exit_basis >= float(params["min_basis_over_premium_stop"]) * entry.premium_stop)


def simulate(entry: FnoEntry, path: Sequence[Observation], policy: str) -> dict[str, Any]:
    """Replay the live ladder (baseline) or one frozen candidate on ``path``."""
    params = live_single_leg_exit_params(settings)
    position = _position(entry)
    remaining = entry.quantity
    legs: list[dict[str, Any]] = []
    banked = False
    replaced: list[dict[str, str]] = []
    hard_flat = _hard_flat_at(entry)
    for obs in path:
        decision = evaluate_single_leg_exit(
            position, now_ist=obs.observed_at, fut_price=obs.fut_price,
            exit_px_basis=obs.exit_basis, hard_flat=obs.observed_at >= hard_flat, params=params,
        )
        reason = decision.exit_reason
        if (policy == PARTIAL_POLICY and decision.trail_newly_armed and not banked
                and not reason and obs.exit_basis > 0):
            lots = entry.quantity // entry.lot_size
            bank_lots = int(lots * float(CANDIDATE_POLICIES[PARTIAL_POLICY]["bank_fraction_of_lots"]))
            if lots >= 2 and bank_lots >= 1:
                sold = bank_lots * entry.lot_size
                legs.append(_leg(entry, sold, obs.exit_basis, "partial_at_target", obs.observed_at,
                                     include_entry_order=not legs))
                remaining -= sold
                banked = True
        if policy == EXTENSION_POLICY and reason == "time_stop":
            best = decision.best_underlying if decision.best_underlying is not None else entry.entry_underlying
            if _extension_confirmed(entry, obs, best, CANDIDATE_POLICIES[EXTENSION_POLICY]):
                if not replaced:
                    replaced.append({"at": obs.observed_at.isoformat(), "exit_replaced": "time_stop"})
                position = replace_trail(position, decision)
                continue
        if reason:
            if obs.exit_basis <= 0:
                return {"policy": policy, "status": "UNRESOLVED", "reason": "exit_basis_unavailable",
                        "attempted_exit": reason, "at": obs.observed_at.isoformat(), "legs": legs}
            legs.append(_leg(entry, remaining, obs.exit_basis, reason, obs.observed_at,
                            include_entry_order=not legs))
            return _finalise(entry, policy, legs, reason, obs.observed_at, replaced)
        if decision.persist_trail:
            position = replace_trail(position, decision)
    return {"policy": policy, "status": "UNRESOLVED", "reason": "path_ended_before_exit", "legs": legs}


def replace_trail(position: SimpleNamespace, decision) -> SimpleNamespace:
    """Carry trail state forward exactly as the orchestrator persists it."""
    return SimpleNamespace(**{**vars(position), "trail_active": 1 if decision.trail_active else 0,
                              "trail_stop_underlying": decision.trail_stop,
                              "best_underlying": decision.best_underlying})


def _finalise(entry: FnoEntry, policy: str, legs: list[dict[str, Any]], reason: str,
              exit_at: datetime, replaced: list[dict[str, str]]) -> dict[str, Any]:
    gross = sum(float(leg["gross_pnl"]) for leg in legs)
    costs = sum(float(leg["costs"]) for leg in legs)
    net = gross - costs
    risk = entry.entry_premium * float(settings.FNO_STOP_PREMIUM_PCT) * entry.quantity
    return {"policy": policy, "status": "CLOSED", "reason": reason, "exit_at": exit_at.isoformat(),
            "gross_pnl": round(gross, 6), "costs": round(costs, 6), "net_pnl": round(net, 6),
            "r_multiple": round(net / risk, 8) if risk > 0 else None, "legs": legs,
            "exits_replaced": replaced}


def _exposure(entry: FnoEntry, path: Sequence[Observation], result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") != "CLOSED":
        return result
    exit_at = datetime.fromisoformat(result["exit_at"])
    risk_per_unit = entry.entry_premium * float(settings.FNO_STOP_PREMIUM_PCT)
    bases = [obs.exit_basis for obs in path if obs.observed_at <= exit_at and obs.exit_basis > 0]
    mfe = (max(bases) - entry.entry_premium) / risk_per_unit if bases else 0.0
    mae = (min(bases) - entry.entry_premium) / risk_per_unit if bases else 0.0
    gross_r = float(result["gross_pnl"]) / (risk_per_unit * entry.quantity)
    gross, costs = float(result["gross_pnl"]), float(result["costs"])
    return {**result, "mfe_r": round(max(0.0, mfe), 8), "mae_r": round(min(0.0, mae), 8),
            "giveback_r": round(max(0.0, mfe) - gross_r, 8),
            "minutes_exposed": round((exit_at - entry.entry_time).total_seconds() / 60.0, 4),
            "net_pnl_cost_stressed": {f"{m:g}x": round(gross - m * costs, 6) for m in COST_MULTIPLIERS}}


def _source_fingerprint() -> str:
    here = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for name in _SOURCE_MODULES:
        data = (here / name).read_bytes().replace(b"\r\n", b"\n")
        digest.update(name.encode("utf-8") + b"\0" + hashlib.sha256(data).digest())
    return f"sha256:{digest.hexdigest()}"


def _live_settings() -> dict[str, Any]:
    return {**live_single_leg_exit_params(settings),
            "FNO_HARD_FLAT_MIN": int(settings.FNO_HARD_FLAT_MIN),
            "FNO_STOP_PREMIUM_PCT": float(settings.FNO_STOP_PREMIUM_PCT)}


def freeze_manifest(*, experiment_id: str, candidate_policy: str,
                    frozen_at: datetime | None = None) -> dict[str, Any]:
    experiment_id = (experiment_id or "").strip()
    if not experiment_id or len(experiment_id) > 160:
        raise FnoExitStudyError("experiment_id must be a non-empty <=160-character string")
    if candidate_policy not in CANDIDATE_POLICIES:
        raise FnoExitStudyError(f"unknown candidate policy: {candidate_policy}")
    frozen_at = frozen_at or datetime.now(timezone.utc)
    if frozen_at.tzinfo is None:
        raise FnoExitStudyError("frozen_at must be timezone-aware")
    return {"schema": MANIFEST_SCHEMA, "experiment_id": experiment_id, "baseline_policy": BASELINE_POLICY,
            "candidate_policy": candidate_policy, "candidate_parameters": deepcopy(CANDIDATE_POLICIES[candidate_policy]),
            "live_settings": _live_settings(), "cost_model": COST_MODEL,
            "cost_schedule": options_cost_snapshot(),
            "cost_multipliers": list(COST_MULTIPLIERS), "source_fingerprint": _source_fingerprint(),
            "frozen_at": frozen_at.astimezone(timezone.utc).isoformat(),
            "holdout_rule": "only entries strictly after frozen_at are HOLDOUT"}


def verify_manifest(manifest: Mapping[str, Any]) -> datetime:
    if not isinstance(manifest, Mapping) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise FnoExitStudyError(f"manifest schema must be {MANIFEST_SCHEMA}")
    policy = manifest.get("candidate_policy")
    if policy not in CANDIDATE_POLICIES:
        raise FnoExitStudyError("FROZEN_POLICY_MISMATCH: unknown candidate policy")
    expected = {"baseline_policy": BASELINE_POLICY, "candidate_parameters": CANDIDATE_POLICIES[policy],
                "cost_model": COST_MODEL,
                "cost_schedule": options_cost_snapshot(),
                "live_settings": _live_settings(), "cost_multipliers": list(COST_MULTIPLIERS),
                "source_fingerprint": _source_fingerprint()}
    for field, current in expected.items():
        if _canonical_bytes({"v": manifest.get(field)}) != _canonical_bytes({"v": current}):
            raise FnoExitStudyError(f"FROZEN_POLICY_MISMATCH: {field} differs from the frozen manifest")
    try:
        frozen_at = datetime.fromisoformat(str(manifest.get("frozen_at")).replace("Z", "+00:00"))
    except ValueError as exc:
        raise FnoExitStudyError("manifest frozen_at is invalid") from exc
    if frozen_at.tzinfo is None:
        raise FnoExitStudyError("manifest frozen_at must be timezone-aware")
    return frozen_at


RECONCILIATION_TOLERANCE_RS = 1.0


def reconcile_single_leg(raw_entry: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    """Compare the replayed baseline with the position row's settlement and ledger.

    Only a database-bound entry whose closed row, ledger cash and replayed
    baseline agree (same exit reason, net within tolerance) is usable for
    paired comparison.  Archive cadence differs from management ticks, so a
    mismatch is reported, not forced.
    """
    if raw_entry.get("evidence_kind") != "FNO_POSITIONS_ROW":
        return {"state": "UNBOUND_CALLER_ENTRY", "usable": False}
    settlement = raw_entry.get("settlement") if isinstance(raw_entry.get("settlement"), Mapping) else {}
    if settlement.get("status") != "CLOSED":
        return {"state": "UNSETTLED", "usable": False}
    ledger, row_net = settlement.get("ledger_net_pnl"), settlement.get("position_net_pnl")
    if ledger is None or row_net is None or abs(float(ledger) - float(row_net)) > RECONCILIATION_TOLERANCE_RS:
        return {"state": "LEDGER_MISMATCH_OR_MISSING", "usable": False}
    if baseline.get("status") != "CLOSED":
        return {"state": "BASELINE_NOT_CLOSED", "usable": False}
    same_reason = settlement.get("exit_reason") == baseline.get("reason")
    delta = float(baseline["net_pnl"]) - float(ledger)
    usable = same_reason and abs(delta) <= RECONCILIATION_TOLERANCE_RS
    return {"state": "RECONCILED" if usable else "BASELINE_DIFFERS_FROM_SETTLEMENT", "usable": usable,
            "ledger_net_pnl": float(ledger), "baseline_minus_ledger": round(delta, 6),
            "exit_reason_matches": same_reason}


def build_fno_exit_experiment(packet_path: str | os.PathLike[str], manifest: Mapping[str, Any]) -> dict[str, Any]:
    frozen_at = verify_manifest(manifest)
    packet, entries, grouped, input_fingerprint = load_fno_exit_packet(packet_path)
    policy = str(manifest["candidate_policy"])
    max_gap = int(packet["max_observation_gap_seconds"])
    pairs = []
    raw_entries = {str(item.get("entry_id")): item for item in packet["entries"]}
    for entry in sorted(entries, key=lambda item: item.entry_id):
        sample = "HOLDOUT" if entry.entry_time > frozen_at else "DEVELOPMENT"
        raw = raw_entries.get(entry.entry_id, {})
        base = {"entry_id": entry.entry_id, "position_ref": entry.position_ref,
                "tradingsymbol": entry.tradingsymbol, "source_ref": entry.source_ref, "sample_class": sample,
                "entry_evidence": raw.get("evidence_kind", "CALLER_SUPPLIED_UNVERIFIED")}
        path, issue = _validated_path(entry, sorted(grouped[entry.entry_id], key=lambda o: o.observed_at), max_gap)
        if issue is not None:
            unresolved = {"status": "INSUFFICIENT_EVIDENCE", "reason": issue, "legs": []}
            pairs.append({**base, "status": "INSUFFICIENT_EVIDENCE", "reason": issue,
                          "baseline": {"policy": BASELINE_POLICY, **unresolved},
                          "candidate": {"policy": policy, **unresolved},
                          "reconciliation": {"state": "PATH_INSUFFICIENT", "usable": False}})
            continue
        baseline = _exposure(entry, path, simulate(entry, path, BASELINE_POLICY))
        pairs.append({**base, "status": "COMPLETE", "baseline": baseline,
                      "candidate": _exposure(entry, path, simulate(entry, path, policy)),
                      "reconciliation": reconcile_single_leg(raw, baseline)})

    def section(sample: str | None) -> dict[str, Any]:
        chosen = [pair for pair in pairs if sample is None or pair["sample_class"] == sample]
        usable = [pair for pair in chosen if pair["reconciliation"]["usable"]]
        return {"pairs": len(chosen), "reconciled_usable": len(usable),
                "baseline": _policy_summary([pair["baseline"] for pair in chosen]),
                "candidate": _policy_summary([pair["candidate"] for pair in chosen]),
                "paired": _paired_deltas(chosen),
                # Deltas only over baselines that reproduce persisted settlement cash.
                "paired_reconciled": _paired_deltas(usable)}

    report = {
        "schema": REPORT_SCHEMA, "experiment_id": manifest["experiment_id"], "study_id": packet["study_id"],
        "input_fingerprint": input_fingerprint,
        "manifest_fingerprint": f"sha256:{hashlib.sha256(_canonical_bytes(dict(manifest))).hexdigest()}",
        "manifest": dict(manifest),
        "evidence_contract": {"timezone": "Asia/Kolkata", "max_observation_gap_seconds": max_gap,
                              "fill": "paper exit at basis (best bid, else LTP)",
                              "r_denominator": "entry_premium x FNO_STOP_PREMIUM_PCT x quantity",
                              "missing_or_ambiguous_path": "INSUFFICIENT_EVIDENCE",
                              "holdout": "entries strictly after manifest.frozen_at",
                              "outcomes_are": "paper_research_only"},
        "pairs": pairs,
        "summary": {"all": section(None), "holdout": section("HOLDOUT"),
                    "development": section("DEVELOPMENT"), "qualification": "NOT_ASSESSED",
                    "warning": ("A paired replay is not evidence of an edge or authority to change "
                                "live or paper F&O exits; promotion requires a reviewed holdout.")},
    }
    report["report_fingerprint"] = f"sha256:{hashlib.sha256(_canonical_bytes(report)).hexdigest()}"
    return report


# --------------------------------------------------------------------------
# Read-only research-archive adapter
# --------------------------------------------------------------------------

def _raw_digest(raw: Mapping[str, Any]) -> str:
    """The collector's raw-packet digest (``research_quote_collector.normalise_quote``)."""
    return hashlib.sha256(json.dumps(dict(raw), sort_keys=True, default=str,
                                     separators=(",", ":")).encode()).hexdigest()


def _raw_price(raw: Mapping[str, Any], *path: Any) -> float | None:
    value: Any = raw
    for key in path:
        if isinstance(key, int):
            value = value[key] if isinstance(value, list) and len(value) > key else None
        else:
            value = value.get(key) if isinstance(value, Mapping) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return None
    return float(value)


def _column_price(levels: Any) -> float | None:
    first = levels[0] if isinstance(levels, list) and levels and isinstance(levels[0], Mapping) else {}
    value = first.get("price")
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) and value > 0 else None


@dataclass(frozen=True)
class VerifiedQuote:
    token: int
    ltp: float | None
    bid: float | None
    ask: float | None
    provider_at: datetime
    receipt_at: datetime

    @property
    def exit_basis(self) -> float:
        """Live paper exit basis for a long: best bid, else LTP."""
        return self.bid if self.bid is not None else (self.ltp or 0.0)

    @property
    def mid(self) -> float | None:
        """``ContractQuote.mid``: bid/ask midpoint, else LTP."""
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2.0
        return self.ltp


def verify_archive_event(event: Mapping[str, Any], *, token: int, symbol: str | None,
                         max_age_seconds: int) -> tuple[VerifiedQuote | None, str | None]:
    """Re-derive every used field of one archived event from its raw bytes.

    Integrity faults (digest, token/identity, price or clock columns that
    disagree with the raw provider packet) raise: the archive is not trusted
    to be partially right.  A missing, future or stale provider clock is not
    an integrity fault but makes the observation unusable; it is returned as
    an exclusion reason and counted by the caller.
    """
    from research_quote_collector import _provider_timestamp

    raw = event.get("raw_packet")
    if not isinstance(raw, Mapping):
        raise FnoExitStudyError("archive event lacks its raw provider packet")
    if event.get("raw_sha256") != _raw_digest(raw):
        raise FnoExitStudyError("archive event raw_sha256 does not match its raw packet")
    contract = event.get("contract") if isinstance(event.get("contract"), Mapping) else {}
    if str(contract.get("instrument_token")) != str(token):
        raise FnoExitStudyError("archive event contract token does not match the requested leg")
    if raw.get("instrument_token") not in (None, token, str(token)):
        raise FnoExitStudyError("raw provider packet token does not match the requested leg")
    if symbol is not None and contract.get("tradingsymbol") != symbol:
        raise FnoExitStudyError("archived contract identity does not match the entry tradingsymbol")
    ltp, bid, ask = _raw_price(raw, "last_price"), _raw_price(raw, "depth", "buy", 0, "price"), \
        _raw_price(raw, "depth", "sell", 0, "price")
    column_ltp = event.get("ltp")
    if (ltp or 0.0) != (float(column_ltp) if isinstance(column_ltp, (int, float)) else 0.0):
        raise FnoExitStudyError("archive event ltp column does not match its raw packet")
    if bid != _column_price(event.get("buy_depth")):
        raise FnoExitStudyError("archive event bid column does not match its raw packet")
    if ask != _column_price(event.get("sell_depth")):
        raise FnoExitStudyError("archive event ask column does not match its raw packet")
    mode = str(event.get("mode") or "")
    raw_clock = raw.get("timestamp") if mode.startswith("KITE_REST") else raw.get("exchange_timestamp")
    derived = _provider_timestamp(raw_clock)[1]
    if derived != event.get("provider_timestamp_utc"):
        raise FnoExitStudyError("archive event provider clock column does not match its raw packet")
    receipt = _event_clock(event.get("received_at_utc"))
    provider = _event_clock(derived)
    if receipt is None:
        return None, "receipt_clock_invalid"
    if provider is None:
        return None, "provider_clock_unavailable"
    if provider > receipt:
        return None, "provider_clock_after_receipt"
    if (receipt - provider).total_seconds() > max_age_seconds:
        return None, "provider_quote_older_than_declared_maximum"
    return VerifiedQuote(token=int(token), ltp=ltp, bid=bid, ask=ask,
                         provider_at=provider, receipt_at=receipt), None


def _event_clock(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def index_archive_events(events: Iterable[Mapping[str, Any]], tokens: Iterable[int]) -> dict[int, dict[str, Mapping[str, Any]]]:
    """Group events by token and receipt; exact duplicates are idempotent."""
    wanted = {int(token) for token in tokens}
    by_token: dict[int, dict[str, Mapping[str, Any]]] = {token: {} for token in wanted}
    for event in events:
        contract = event.get("contract") if isinstance(event.get("contract"), Mapping) else {}
        try:
            token = int(contract.get("instrument_token"))
        except (TypeError, ValueError):
            continue
        received = event.get("received_at_utc")
        if token not in by_token or not isinstance(received, str):
            continue
        prior = by_token[token].get(received)
        if prior is not None and prior.get("raw_sha256") != event.get("raw_sha256"):
            raise FnoExitStudyError(f"conflicting archive events for token {token} at {received}")
        by_token[token][received] = event
    return by_token


def build_packet_from_archive_events(
    events: Iterable[Mapping[str, Any]], *, entry: Mapping[str, Any], future_token: int,
    study_id: str, max_observation_gap_seconds: int = 120,
) -> dict[str, Any]:
    """Pair verified futures and exact-option events captured at one receipt.

    Both packets are verified from raw bytes (digest, token, identity, price
    and provider-clock columns) and both provider clocks must be present, not
    after receipt and within the declared gap: a stale futures packet next to
    a fresh option is excluded and counted.  ``source_ref`` binds the packet
    to the archived digests and to the entry's own evidence reference; it is
    not external provenance.
    """
    option_token = int(entry["option_token"])
    symbol = str(entry["tradingsymbol"])
    indexed = index_archive_events(events, (future_token, option_token))
    futures, options = indexed[int(future_token)], indexed[option_token]
    for event in futures.values():
        if (event.get("contract") or {}).get("instrument_type") not in (None, "FUT"):
            raise FnoExitStudyError("future_token does not identify a futures contract")
    observations, digests, excluded = [], [], {}
    for received in sorted(set(futures) & set(options)):
        fut, fut_reason = verify_archive_event(futures[received], token=int(future_token), symbol=None,
                                               max_age_seconds=max_observation_gap_seconds)
        opt, opt_reason = verify_archive_event(options[received], token=option_token, symbol=symbol,
                                               max_age_seconds=max_observation_gap_seconds)
        reason = opt_reason or fut_reason
        if reason is not None:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        observations.append({"entry_id": entry["entry_id"], "observed_at": received,
                             "fut_price": fut.ltp, "exit_basis": opt.exit_basis})
        digests += [str(futures[received]["raw_sha256"]), str(options[received]["raw_sha256"])]
    binding = str(entry.get("evidence_ref") or "unbound-caller-entry")
    source_ref = "sha256:" + hashlib.sha256("\n".join([binding, *digests]).encode("utf-8")).hexdigest()
    return {"schema": INPUT_SCHEMA, "study_id": study_id,
            "max_observation_gap_seconds": max_observation_gap_seconds,
            "provenance": {"kind": "derived_from_archived_raw_packet_digests",
                           "entry_evidence": entry.get("evidence_kind", "CALLER_SUPPLIED_UNVERIFIED"),
                           "verified_external_provenance": False,
                           "excluded_observations": dict(sorted(excluded.items()))},
            "entries": [{**dict(entry), "source_ref": source_ref}], "observations": observations}


def entry_from_position_row(db_path: str, position_id: int) -> dict[str, Any]:
    """Bind a study entry to one persisted ``fno_positions`` row and its ledger cash.

    Read-only.  Economics come from the stored row (never caller JSON); the
    settlement is the sum of that position's ledger events.  ``evidence_ref``
    hashes the canonical row fields used, so a later edit is detectable.
    """
    import sqlite3
    path = Path(db_path)
    if not path.is_file():
        raise FnoExitStudyError("database unavailable")
    con = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute("SELECT * FROM fno_positions WHERE id=?", (int(position_id),)).fetchone()
        if row is None:
            raise FnoExitStudyError(f"fno_positions row {position_id} not found")
        try:
            ledger = con.execute(
                "SELECT COALESCE(SUM(pnl),0), COUNT(*) FROM bankroll_ledger WHERE origin_ref=? "
                "AND event_type IN ('TRADE_PARTIAL','TRADE_CLOSED')", (f"fno_position:{int(position_id)}",),
            ).fetchone()
        except sqlite3.Error:
            ledger = (None, 0)
    finally:
        con.close()
    fields = {key: row[key] for key in (
        "id", "source", "tradingsymbol", "token", "direction", "qty", "lot_size", "entry_time",
        "entry_premium", "entry_underlying", "stop_underlying", "target_underlying", "premium_stop",
        "atr_at_entry")}
    evidence = json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)
    entry = {
        "entry_id": f"fno_position:{row['id']}", "position_ref": str(row["id"]),
        "tradingsymbol": row["tradingsymbol"], "option_token": row["token"], "direction": row["direction"],
        "quantity": row["qty"], "lot_size": row["lot_size"], "entry_time": row["entry_time"],
        "entry_premium": row["entry_premium"], "entry_underlying": row["entry_underlying"],
        "stop_underlying": row["stop_underlying"], "target_underlying": row["target_underlying"],
        "premium_stop": row["premium_stop"], "atr_at_entry": row["atr_at_entry"],
        "evidence_kind": "FNO_POSITIONS_ROW",
        "evidence_ref": "sha256:" + hashlib.sha256(evidence.encode("utf-8")).hexdigest(),
        # Until archive digests are bound in by the packet builder, the row's
        # own evidence hash is the entry's source reference.
        "source_ref": "sha256:" + hashlib.sha256(evidence.encode("utf-8")).hexdigest(),
        "settlement": {"status": row["status"], "exit_reason": row["exit_reason"], "exit_time": row["exit_time"],
                       "position_net_pnl": row["pnl"],
                       "ledger_net_pnl": None if ledger[1] == 0 else float(ledger[0]),
                       "ledger_events": int(ledger[1])},
    }
    _entry(entry)  # same validation the evaluator applies
    return entry


def _read_json(path: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FnoExitStudyError(f"unreadable JSON: {path}") from exc
    if not isinstance(value, dict):
        raise FnoExitStudyError(f"JSON root must be an object: {path}")
    return value


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Frozen read-only single-leg F&O exit experiment")
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--experiment-id", required=True)
    freeze.add_argument("--candidate", required=True, choices=sorted(CANDIDATE_POLICIES))
    freeze.add_argument("--output", required=True)
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--manifest", required=True)
    evaluate.add_argument("--input", required=True)
    evaluate.add_argument("--output", required=True)
    packet = sub.add_parser("build-packet", help="pair archived futures/option events for one position")
    packet.add_argument("--archive-root", required=True)
    packet.add_argument("--day", required=True, help="archive session day YYYY-MM-DD")
    source = packet.add_mutually_exclusive_group(required=True)
    source.add_argument("--position-id", type=int, help="bind the entry to this fno_positions row (with --db)")
    source.add_argument("--entry", help="caller JSON entry; labelled CALLER_SUPPLIED_UNVERIFIED, never usable")
    packet.add_argument("--db", help="engine SQLite holding fno_positions (opened read-only)")
    packet.add_argument("--future-token", required=True, type=int)
    packet.add_argument("--study-id", required=True)
    packet.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "freeze":
            value = freeze_manifest(experiment_id=args.experiment_id, candidate_policy=args.candidate)
        elif args.command == "evaluate":
            value = build_fno_exit_experiment(args.input, _read_json(args.manifest))
        else:
            from intraday_spread_archive_adapter import read_archived_quote_events
            events = read_archived_quote_events(args.archive_root, days=[args.day])
            if args.position_id is not None:
                if not args.db:
                    raise FnoExitStudyError("--position-id requires --db")
                entry = entry_from_position_row(args.db, args.position_id)
            else:
                entry = {**_read_json(args.entry), "evidence_kind": "CALLER_SUPPLIED_UNVERIFIED"}
            value = build_packet_from_archive_events(events, entry=entry,
                                                     future_token=args.future_token, study_id=args.study_id)
        write_study_report_once(value, args.output)
    except (ExitStudyError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(_main())
