"""Immutable, offline-only predeclared G/C strategy comparison evidence.

This module deliberately has no live imports or side effects.  A favourable
report is research evidence only, never an authorization or promotion input.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from datetime import datetime, time, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import aiosqlite

from proactive_intelligence import (ShadowProposal, _research_proposal_manifest,
                                    _shadow_implementation_identity,
                                    simulate_shadow_research_trial)

_IST = ZoneInfo("Asia/Kolkata")
_ENTRY = {"NEXT_EXECUTABLE_OPEN_V1", "BOUNDED_PULLBACK_LIMIT_V1",
          "COMPLETED_BAR_CONFIRMATION_V1", "RANGE_REVERSION_V1"}
_EXIT = {"STOP_TARGET_TIME_V1", "BOUNDED_TIME_EXIT_60M_V1", "TRAILING_STOP_V1"}
_AUTHORITY = {"can_place_orders": False, "can_qualify": False,
              "authorization_effect": "NONE", "research_only": True,
              "approval_usable": False}


def _json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("protocol input must be JSON-serializable and finite") from exc


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _clock(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        try:
            result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("protocol clocks must be timezone-aware ISO timestamps") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("protocol clocks must be timezone-aware")
    return result.astimezone(timezone.utc)


def _date_sessions(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty list of ISO dates")
    try:
        result = sorted({datetime.fromisoformat(f"{x}T00:00:00").date().isoformat() for x in value})
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be ISO dates") from exc
    if len(result) != len(value):
        raise ValueError(f"{name} must not contain duplicates")
    return result


def _finite(value: Any, label: str, *, positive: bool = False, nonnegative: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(result) or (positive and result <= 0) or (nonnegative and result < 0):
        raise ValueError(f"{label} is invalid")
    return result


def _alternatives(value: Any) -> list[dict]:
    if not isinstance(value, list) or not 1 <= len(value) <= 6:
        raise ValueError("alternatives must contain 1 through 6 declared profiles")
    out, names, pairs = [], set(), set()
    for item in value:
        if not isinstance(item, Mapping): raise ValueError("alternative is malformed")
        name = item.get("name")
        entry = item.get("entry_profile_id", item.get("entry"))
        exit_ = item.get("exit_profile_id", item.get("exit"))
        if not isinstance(name, str) or not name.strip() or name in names or (entry, exit_) in pairs or entry not in _ENTRY or exit_ not in _EXIT:
            raise ValueError("alternatives require unique names and supported named entry/exit profiles")
        names.add(name); pairs.add((entry, exit_)); out.append({"name": name, "entry_profile_id": entry, "exit_profile_id": exit_})
    return sorted(out, key=lambda x: x["name"])


def _canonical_manifest(manifest: Mapping[str, Any], now: datetime) -> dict:
    if not isinstance(manifest, Mapping): raise ValueError("manifest must be an object")
    protocol_id = manifest.get("protocol_id")
    account = manifest.get("account_id")
    revision = manifest.get("code_revision")
    if not all(isinstance(x, str) and x.strip() for x in (protocol_id, account, revision)):
        raise ValueError("protocol_id, account_id, and explicit code_revision are required")
    train, hold = _date_sessions(manifest.get("training_sessions"), "training_sessions"), _date_sessions(manifest.get("holdout_sessions"), "holdout_sessions")
    if set(train) & set(hold) or train[-1] >= hold[0]: raise ValueError("training sessions must be sorted, disjoint, and all precede holdout")
    declared = _clock(manifest.get("frozen_at"))
    if declared > now: raise ValueError("frozen_at cannot be in the future")
    boundary = datetime.combine(datetime.fromisoformat(hold[0]).date(), time(), _IST).astimezone(timezone.utc)
    if now >= boundary: raise ValueError("protocol must be frozen before first holdout midnight IST; no backdated freeze")
    costs = manifest.get("cost_snapshot")
    stress = manifest.get("cost_stress")
    thresholds = manifest.get("thresholds")
    if not isinstance(costs, Mapping) or not isinstance(stress, Mapping) or not isinstance(thresholds, Mapping):
        raise ValueError("cost_snapshot, cost_stress and thresholds are required objects")
    fee = _finite(costs.get("fee_rate"), "cost_snapshot.fee_rate", nonnegative=True)
    slip = _finite(costs.get("slippage_bps"), "cost_snapshot.slippage_bps", nonnegative=True)
    stress_fee = _finite(stress.get("fee_multiplier"), "cost_stress.fee_multiplier", positive=True)
    stress_slip = _finite(stress.get("additional_slippage_bps"), "cost_stress.additional_slippage_bps", nonnegative=True)
    required_thresholds = {"minimum_closed_outcomes", "minimum_complete_sessions", "maximum_drawdown_pct", "minimum_net_expectancy", "minimum_paired_delta", "confidence_level", "bootstrap_samples"}
    if set(thresholds) != required_thresholds:
        raise ValueError("thresholds must declare every predeclared research gate")
    for key, value in thresholds.items(): _finite(value, f"thresholds.{key}")
    if (int(thresholds["minimum_closed_outcomes"]) != thresholds["minimum_closed_outcomes"] or int(thresholds["minimum_closed_outcomes"]) < 1
            or int(thresholds["minimum_complete_sessions"]) != thresholds["minimum_complete_sessions"] or int(thresholds["minimum_complete_sessions"]) < 1
            or not 0 <= float(thresholds["maximum_drawdown_pct"]) <= 1
            or not .5 < float(thresholds["confidence_level"]) < 1
            or int(thresholds["bootstrap_samples"]) != thresholds["bootstrap_samples"] or not 100 <= int(thresholds["bootstrap_samples"]) <= 10000):
        raise ValueError("threshold gates are out of permitted bounds")
    alts = _alternatives(manifest.get("alternatives"))
    baseline = manifest.get("baseline")
    if baseline not in {x["name"] for x in alts}: raise ValueError("baseline must name one declared alternative")
    return {"format": "proactive-predeclared-comparison-v1", "protocol_id": protocol_id,
            "account_id": account, "code_revision": revision, "implementation_sha256": {
                "protocol": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "primary_evaluator": _shadow_implementation_identity()}, "frozen_at": declared.isoformat(),
            "recorded_at": now.isoformat(), "training_sessions": train, "holdout_sessions": hold,
            "alternatives": alts, "baseline": baseline, "cash": _finite(manifest.get("cash"), "cash", positive=True),
            "cost_snapshot": {**copy.deepcopy(dict(costs)), "fee_rate": fee, "slippage_bps": slip},
            "cost_stress": {"fee_multiplier": stress_fee, "additional_slippage_bps": stress_slip},
            "thresholds": {k: int(v) if k in {"minimum_closed_outcomes", "minimum_complete_sessions", "bootstrap_samples"} else float(v) for k, v in thresholds.items()}, "provenance": "DIAGNOSTIC_ONLY_NOT_INDEPENDENT_SOURCE_PROOF",
            **_AUTHORITY}


async def _schema(db: aiosqlite.Connection) -> None:
    await db.execute("CREATE TABLE IF NOT EXISTS proactive_comparison_protocols (protocol_id TEXT PRIMARY KEY, manifest_json TEXT NOT NULL, manifest_sha256 TEXT NOT NULL, created_at TEXT NOT NULL)")
    await db.execute("CREATE TABLE IF NOT EXISTS proactive_comparison_reports (protocol_id TEXT NOT NULL, report_id TEXT NOT NULL, input_sha256 TEXT NOT NULL, report_json TEXT NOT NULL, report_sha256 TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(protocol_id,report_id))")
    for table in ("proactive_comparison_protocols", "proactive_comparison_reports"):
        await db.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_immutable_update BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, 'immutable'); END")
        await db.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_immutable_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, 'immutable'); END")


async def freeze_comparison_protocol(db_path: str, manifest: Mapping[str, Any], *, now: Any = None) -> dict:
    """Freeze a protocol atomically before its first declared holdout date."""
    frozen_now = _clock(now) if now is not None else datetime.now(timezone.utc)
    canonical = _canonical_manifest(copy.deepcopy(manifest), frozen_now)
    text = _json(canonical); digest = _hash(canonical)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("BEGIN IMMEDIATE"); await _schema(db)
        row = await (await db.execute("SELECT manifest_json,manifest_sha256 FROM proactive_comparison_protocols WHERE protocol_id=?", (canonical["protocol_id"],))).fetchone()
        if row:
            existing = json.loads(row[0])
            if _hash(existing) != row[1]: await db.rollback(); raise ValueError("stored protocol manifest hash is corrupt")
            comparable_existing, comparable_new = dict(existing), dict(canonical)
            comparable_existing.pop("recorded_at", None); comparable_new.pop("recorded_at", None)
            if comparable_existing != comparable_new: await db.rollback(); raise ValueError("protocol manifest conflicts with existing immutable evidence")
            await db.commit(); existing["manifest_sha256"] = row[1]; return existing
        await db.execute("INSERT INTO proactive_comparison_protocols VALUES (?,?,?,?)", (canonical["protocol_id"], text, digest, frozen_now.isoformat()))
        await db.commit()
    canonical["manifest_sha256"] = digest
    return canonical


def _coverage(value: Any, manifest: dict) -> dict[tuple[str, str], str]:
    required = {(a["name"], day) for a in manifest["alternatives"] for day in manifest["holdout_sessions"]}
    out: dict[tuple[str, str], str] = {}
    if value is None: raise ValueError("session_coverage is required")
    if not isinstance(value, (list, Mapping)): raise ValueError("session_coverage must be a list or mapping")
    if isinstance(value, Mapping) and any(not isinstance(p, str) or not isinstance(dates, Mapping) for p, dates in value.items()): raise ValueError("nested session coverage is malformed")
    rows = value if isinstance(value, list) else [{"profile": p, "session": d, "status": s} for p, dates in value.items() for d, s in dates.items()]
    if not isinstance(rows, list): raise ValueError("session_coverage must explicitly map profile/session statuses")
    for row in rows:
        if not isinstance(row, Mapping): raise ValueError("session coverage is malformed")
        key = (row.get("profile", row.get("alternative")), row.get("session", row.get("session_date"))); status = row.get("status")
        if key not in required or status not in {"COMPLETE", "MISSING"} or key in out: raise ValueError("session coverage must be unique and declared")
        out[key] = status
    if set(out) != required: raise ValueError("session coverage must explicitly retain every declared profile/session")
    return out


def _proposal_session(p: ShadowProposal) -> str:
    return _clock(p.data_cutoff or p.signal_at or p.valid_until).astimezone(_IST).date().isoformat()


def _summarise(rows: list[dict], baseline_rows: list[dict], *, cash: float, confidence: float, samples: int) -> dict:
    closed = sorted((x for x in rows if x["status"] == "CLOSED"), key=lambda x: (x["exit_at"] or "", x["opportunity_id"]))
    equity = peak = drawdown = 0.0
    for row in closed:
        equity += row["net_pnl"] or 0.; peak = max(peak, equity); drawdown = min(drawdown, equity - peak)
    base = {x["opportunity_id"]: x for x in baseline_rows}
    paired = [(x["net_pnl"] or 0.) - (base[x["opportunity_id"]]["net_pnl"] or 0.) for x in rows if x["opportunity_id"] in base and x["status"] in {"CLOSED", "NO_FILL"} and base[x["opportunity_id"]]["status"] in {"CLOSED", "NO_FILL"}]
    # Deterministic session-cluster pseudo-bootstrap: clusters, not variants, are samples.
    clusters: dict[str, list[float]] = {}
    for x in rows:
        if x["opportunity_id"] in base and x["status"] in {"CLOSED", "NO_FILL"} and base[x["opportunity_id"]]["status"] in {"CLOSED", "NO_FILL"}: clusters.setdefault(x["session"], []).append((x["net_pnl"] or 0.) - (base[x["opportunity_id"]]["net_pnl"] or 0.))
    cluster_means = [mean(v) for _, v in sorted(clusters.items())]
    if cluster_means:
        rng = random.Random(_hash(cluster_means))
        draws = sorted(mean(rng.choice(cluster_means) for _ in cluster_means) for _ in range(samples))
        alpha = (1 - confidence) / 2
        ci = [draws[max(0, int(alpha * samples))], draws[min(samples - 1, int((1 - alpha) * samples) - 1)]]
    else: ci = [None, None]
    net = sum(x["net_pnl"] or 0. for x in closed)
    return {"independent_opportunity_count": len({x["opportunity_id"] for x in rows}), "closed": len(closed), "no_fill": sum(x["status"] == "NO_FILL" for x in rows), "open": sum(x["status"] == "OPEN" for x in rows), "invalid": sum(x["status"] == "INVALID" for x in rows), "net_pnl": net, "net_expectancy": net / len(closed) if closed else None, "ordered_realised_drawdown": drawdown, "ordered_realised_drawdown_pct_initial_cash": abs(drawdown) / cash, "turnover": sum(x["quantity"] for x in rows if x["status"] == "CLOSED"), "capacity_cash": cash, "paired_baseline_delta": mean(paired) if paired else None, "paired_session_cluster_bootstrap_ci": ci, "bootstrap_cluster_count": len(cluster_means), "open_or_invalid_blocks_inference": any(x["status"] in {"OPEN", "INVALID"} for x in rows)}


async def evaluate_comparison_protocol(db_path: str, *, protocol_id: str, report_id: str, proposals: list[ShadowProposal], future_bars: Mapping[str, list[dict]], session_coverage: Any, now: Any = None) -> dict:
    """Evaluate exactly one frozen basket; retains missing and zero sessions."""
    if not isinstance(protocol_id, str) or not protocol_id or not isinstance(report_id, str) or not report_id: raise ValueError("protocol_id and report_id are required")
    snapshot_proposals, snapshot_bars, snapshot_coverage = copy.deepcopy(list(proposals)), copy.deepcopy(future_bars), copy.deepcopy(session_coverage)
    if not all(isinstance(p, ShadowProposal) for p in snapshot_proposals) or not isinstance(snapshot_bars, Mapping): raise ValueError("proposals and future_bars are malformed")
    now_clock = _clock(now) if now is not None else datetime.now(timezone.utc)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("BEGIN IMMEDIATE"); await _schema(db)
        row = await (await db.execute("SELECT manifest_json FROM proactive_comparison_protocols WHERE protocol_id=?", (protocol_id,))).fetchone()
        if not row: await db.rollback(); raise ValueError("frozen protocol not found")
        manifest = json.loads(row[0]); coverage = _coverage(snapshot_coverage, manifest)
        if _hash(manifest) != (await (await db.execute("SELECT manifest_sha256 FROM proactive_comparison_protocols WHERE protocol_id=?", (protocol_id,))).fetchone())[0]: await db.rollback(); raise ValueError("stored protocol manifest hash is corrupt")
        identities = manifest["implementation_sha256"]
        if (identities["primary_evaluator"] != _shadow_implementation_identity() or identities["protocol"] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()): await db.rollback(); raise ValueError("frozen implementation identity no longer matches protocol")
        if now_clock < _clock(manifest["recorded_at"]): await db.rollback(); raise ValueError("evaluation clock precedes frozen protocol")
        ids = [p.opportunity_id for p in snapshot_proposals]
        if len(ids) != len(set(ids)) or any(not x for x in ids): await db.rollback(); raise ValueError("opportunity identities must be unique")
        if any(_proposal_session(p) not in manifest["holdout_sessions"] for p in snapshot_proposals): await db.rollback(); raise ValueError("every proposal must belong to declared holdout")
        for bars in snapshot_bars.values():
            if not isinstance(bars, list): await db.rollback(); raise ValueError("future bars must be lists")
            for bar in bars:
                if not isinstance(bar, Mapping) or _clock(bar.get("timestamp")) > now_clock: await db.rollback(); raise ValueError("evaluation cannot publish future bar outcomes")
        inputs = {"protocol_manifest_sha256": _hash(manifest), "proposals": [_research_proposal_manifest(p) for p in snapshot_proposals], "future_bars": snapshot_bars, "session_coverage": snapshot_coverage}
        input_hash = _hash(inputs)
        old = await (await db.execute("SELECT input_sha256,report_json FROM proactive_comparison_reports WHERE protocol_id=? AND report_id=?", (protocol_id, report_id))).fetchone()
        if old:
            if old[0] != input_hash: await db.rollback(); raise ValueError("report identity conflicts with immutable inputs")
            await db.commit(); return json.loads(old[1])
        all_profiles: dict[str, dict[str, list[dict]]] = {a["name"]: {"baseline": [], "stress": []} for a in manifest["alternatives"]}
        for a in manifest["alternatives"]:
            for p in snapshot_proposals:
                bars = snapshot_bars.get(p.opportunity_id, snapshot_bars.get(p.instrument, [])); session = _proposal_session(p)
                for label, fee, slip in (("baseline", manifest["cost_snapshot"]["fee_rate"], manifest["cost_snapshot"]["slippage_bps"]), ("stress", manifest["cost_snapshot"]["fee_rate"] * manifest["cost_stress"]["fee_multiplier"], manifest["cost_snapshot"]["slippage_bps"] + manifest["cost_stress"]["additional_slippage_bps"])):
                    r = simulate_shadow_research_trial(p, bars, cash=manifest["cash"], entry_profile_id=a["entry_profile_id"], exit_profile_id=a["exit_profile_id"], fee_rate=fee, slippage_bps=slip)
                    all_profiles[a["name"]][label].append({"opportunity_id": p.opportunity_id, "session": session, "status": r.status, "reason": r.reason, "quantity": r.quantity, "net_pnl": r.net_pnl, "entry_at": r.entry_at.isoformat() if r.entry_at else None, "exit_at": r.last_bar_at.isoformat() if r.status == "CLOSED" and r.last_bar_at else None})
        baseline = manifest["baseline"]; results = []
        adjusted_confidence = 1 - (1 - manifest["thresholds"]["confidence_level"]) / len(manifest["alternatives"])
        for name, coords in all_profiles.items(): results.append({"name": name, "coverage": [{"session": d, "status": coverage[name, d]} for d in manifest["holdout_sessions"]], "baseline": _summarise(coords["baseline"], all_profiles[baseline]["baseline"], cash=manifest["cash"], confidence=adjusted_confidence, samples=manifest["thresholds"]["bootstrap_samples"]), "stress": _summarise(coords["stress"], all_profiles[baseline]["stress"], cash=manifest["cash"], confidence=adjusted_confidence, samples=manifest["thresholds"]["bootstrap_samples"]), "outcomes": coords, "family_wise_confidence": adjusted_confidence, "semantic_limitation": "RANGE_REVERSION_V1 is a confirmation alias, not an independent range hypothesis" if next(a for a in manifest["alternatives"] if a["name"] == name)["entry_profile_id"] == "RANGE_REVERSION_V1" else None})
        # Thresholds are gates, never an authorization mechanism.
        base_profile = next(x for x in results if x["name"] == baseline); base = base_profile["baseline"]; stress_summary = base_profile["stress"]; thresholds = manifest["thresholds"]
        complete = sum(coverage[baseline, d] == "COMPLETE" for d in manifest["holdout_sessions"]); missing = len(manifest["holdout_sessions"]) - complete
        rejection = ((base["net_expectancy"] is not None and base["net_expectancy"] < thresholds["minimum_net_expectancy"]) or base["ordered_realised_drawdown_pct_initial_cash"] > thresholds["maximum_drawdown_pct"] or stress_summary["ordered_realised_drawdown_pct_initial_cash"] > thresholds["maximum_drawdown_pct"])
        uncertain = (missing > 0 or complete < thresholds["minimum_complete_sessions"] or base["closed"] < thresholds["minimum_closed_outcomes"] or base["open_or_invalid_blocks_inference"] or base["paired_baseline_delta"] is None or base["paired_session_cluster_bootstrap_ci"][0] is None or base["paired_session_cluster_bootstrap_ci"][0] < thresholds["minimum_paired_delta"])
        baseline_entry = next(a for a in manifest["alternatives"] if a["name"] == baseline)["entry_profile_id"]
        if baseline_entry == "RANGE_REVERSION_V1": uncertain = True
        # Each challenger receives its own predeclared gate result.  Baseline
        # has no meaningful paired delta against itself, so its paired gate is
        # explicitly N/A rather than silently treated as a win.
        for profile in results:
            summary, stressed = profile["baseline"], profile["stress"]
            complete_profile = sum(coverage[profile["name"], d] == "COMPLETE" for d in manifest["holdout_sessions"])
            profile_reasons = []
            failed = ((summary["net_expectancy"] is not None and summary["net_expectancy"] < thresholds["minimum_net_expectancy"])
                      or (stressed["net_expectancy"] is not None and stressed["net_expectancy"] < thresholds["minimum_net_expectancy"])
                      or summary["ordered_realised_drawdown_pct_initial_cash"] > thresholds["maximum_drawdown_pct"]
                      or stressed["ordered_realised_drawdown_pct_initial_cash"] > thresholds["maximum_drawdown_pct"])
            incomplete = (complete_profile < thresholds["minimum_complete_sessions"] or summary["closed"] < thresholds["minimum_closed_outcomes"] or summary["open_or_invalid_blocks_inference"] or stressed["open_or_invalid_blocks_inference"])
            if profile["name"] != baseline and (summary["paired_session_cluster_bootstrap_ci"][0] is None or summary["paired_session_cluster_bootstrap_ci"][0] < thresholds["minimum_paired_delta"]): incomplete = True
            if profile["semantic_limitation"]: incomplete = True
            profile["disposition"] = "REJECTED" if failed else "UNCERTAIN" if incomplete else "SUPPORTS_FURTHER_RESEARCH"
            if failed: profile_reasons.append("baseline or stress economic/drawdown gate breached")
            if incomplete: profile_reasons.append("insufficient complete independent session evidence or paired uncertainty")
            if profile["name"] == baseline: profile_reasons.append("paired baseline delta gate is not applicable to baseline itself")
            profile["reasons"] = profile_reasons
        disposition = "REJECTED" if rejection else "UNCERTAIN" if uncertain else "SUPPORTS_FURTHER_RESEARCH"
        reasons = ["declared gate breach" if rejection else "incomplete or insufficient independent session evidence" if uncertain else "all predeclared research gates passed; no live promotion", "input provenance is diagnostic-only, not independent source proof"]
        report = {"format": "proactive-predeclared-comparison-report-v1", "protocol_id": protocol_id, "report_id": report_id, "evaluated_at": now_clock.isoformat(), "input_sha256": input_hash, "manifest_sha256": _hash(manifest), "profiles": results, "disposition": disposition, "reasons": reasons, "provenance": manifest["provenance"], **_AUTHORITY}
        report["report_sha256"] = _hash(report)
        await db.execute("INSERT INTO proactive_comparison_reports VALUES (?,?,?,?,?,?)", (protocol_id, report_id, input_hash, _json(report), report["report_sha256"], now_clock.isoformat()))
        await db.commit(); return report
