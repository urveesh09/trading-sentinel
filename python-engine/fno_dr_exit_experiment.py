"""Frozen, evidence-bound defined-risk exit experiment (S6, R1 correction).

Every replayed fact is derived from persisted or archived evidence, never from
caller-supplied P&L, flags or bytes:

* **Entry** -- a canonical envelope built from one persisted
  ``fno_dr_positions`` row with exact bound legs.  Net premium, maximum
  profit/loss (``fno_defined_risk._profile``) and the round-trip entry cost
  (the live ``structure_round_trip_cost`` formula) are re-derived from the
  legs; any disagreement, a single-leg "structure", duplicate tokens or a
  non-finite number makes the entry unavailable.
* **Observations** -- research-archive quotes for *every* leg at one receipt,
  each verified from raw bytes (``fno_exit_experiment.verify_archive_event``)
  with present, non-future, in-gap provider clocks.  Square-off is derived from
  the observation clock, not supplied.
* **Baseline** -- the live ``fno_dr_book.evaluate_dr_exit`` on the live mid
  mark, settled with the live executable formula; an unpriced square-off is
  ``UNRESOLVED`` (no invented cash).  The baseline is reconciled to the
  persisted settlement and ledger before paired deltas are marked usable.
* **Candidate** -- ``defined_risk_target_hold_trail_v1`` holds a target and
  exits on a frozen giveback from the peak mark; stop and square-off unchanged.

Research only: read-only SQLite, no broker/HTTP/order/message path, no runtime
caller.  Qualification is never assessed.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from config import settings
from cost_schedules import options_cost_snapshot
from exit_experiment_metrics import paired_deltas, policy_summary
from fno_costs import calc_fno_costs
from fno_defined_risk import _profile
from fno_dr_book import (
    _bound_legs_from_row, _legs_from_json, _squareoff_min, _stop_frac, _target_frac,
    evaluate_dr_exit, structure_executable_pnl_rs, structure_mtm_rs,
)
from fno_exit_experiment import VerifiedQuote, index_archive_events, verify_archive_event
from momentum_exit_study import ExitStudyError, _canonical_bytes, write_study_report_once

BASELINE = "defined_risk_current_target_stop_flat_v1"
TRAIL = "defined_risk_target_hold_trail_v1"
ENVELOPE_SCHEMA = "fno_dr_entry_envelope_v1"
MANIFEST_SCHEMA = "fno_dr_exit_experiment_manifest_v2"
REPORT_SCHEMA = "fno_dr_exit_experiment_report_v2"
IST = ZoneInfo("Asia/Kolkata")
COST_MULTIPLIERS = (1.0, 1.5, 2.0)
_TOLERANCE_RS = 0.01
_SOURCE_MODULES = ("fno_dr_exit_experiment.py", "fno_dr_book.py", "fno_defined_risk.py", "fno_risk.py",
                   "fno_costs.py", "cost_schedules.py", "fno_exit_experiment.py", "exit_experiment_metrics.py")
CANDIDATE_PARAMETERS = {
    "description": "hold a target hit; exit when the mid mark gives back a fraction of max profit from its peak",
    "trail_giveback_fraction_of_max_profit": 0.5,
    "floor": "target_level",
    "stop_and_squareoff": "unchanged_live_rules",
}
RECONCILIATION_TOLERANCE_RS = 1.0


class DrStudyError(ExitStudyError):
    """Evidence cannot support an honest defined-risk replay."""


def _finite(value: Any, field: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise DrStudyError(f"{field} must be a finite number")
    if positive and value <= 0:
        raise DrStudyError(f"{field} must be positive")
    return float(value)


def entry_envelope(row: Mapping[str, Any]) -> bytes:
    """Canonical bytes of the persisted entry fields the replay depends on."""
    legs = _bound_legs_from_row(dict(row))
    if legs is None:
        raise DrStudyError("row lacks exact bound leg identities (legacy or invalid)")
    try:
        return _envelope_bytes(row, legs)
    except ValueError as exc:  # NaN/Infinity cannot be canonical evidence
        raise DrStudyError("entry row contains a non-finite number") from exc


def _envelope_bytes(row: Mapping[str, Any], legs: list) -> bytes:
    return _canonical_bytes({
        "schema": ENVELOPE_SCHEMA, "position_ref": f"fno_dr_positions:{int(row['id'])}",
        "source": row.get("source"), "kind": row.get("kind"), "opened_at": row.get("opened_at"),
        "lot_size": row.get("lot_size"), "lots": row.get("lots"), "legs": legs,
        "net_premium_rs": row.get("net_premium_rs"), "max_profit_rs": row.get("max_profit_rs"),
        "max_loss_rs": row.get("max_loss_rs"), "entry_cost_rs": row.get("entry_cost_rs"),
    })


@dataclass(frozen=True)
class DrEntry:
    position_ref: str
    source_ref: str
    envelope: bytes
    opened_at: datetime
    kind: str
    lot_size: int
    legs_row: Mapping[str, Any]
    leg_tokens: tuple[int, ...]
    leg_symbols: tuple[str, ...]
    max_profit: float
    max_loss: float
    entry_cost: float
    settlement: Mapping[str, Any]


def verify_entry(envelope: bytes, settlement: Mapping[str, Any] | None = None) -> DrEntry:
    """Rebuild and re-derive a defined-risk entry from its canonical envelope."""
    try:
        value = json.loads(envelope.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError) as exc:
        raise DrStudyError("entry envelope is not canonical JSON") from exc
    if not isinstance(value, dict) or value.get("schema") != ENVELOPE_SCHEMA:
        raise DrStudyError(f"entry envelope schema must be {ENVELOPE_SCHEMA}")
    if _canonical_bytes(value) != envelope:
        raise DrStudyError("entry envelope bytes are not canonical")
    legs_json = json.dumps(value.get("legs"))
    bound = _bound_legs_from_row({"legs_json": legs_json})
    if bound is None:
        raise DrStudyError("entry legs are not exact bound identities")
    if len(bound) < 2:
        raise DrStudyError("a defined-risk structure needs at least two legs")
    lot_size = int(_finite(value.get("lot_size"), "lot_size", positive=True))
    tokens = tuple(int(leg["contract"]["token"]) for leg in bound)
    if len(set(tokens)) != len(tokens):
        raise DrStudyError("duplicate leg token in structure")
    if {int(leg["contract"]["lot_size"]) for leg in bound} != {lot_size}:
        raise DrStudyError("leg lot sizes disagree with the structure lot size")
    if len({str(leg["contract"]["expiry"]) for leg in bound}) != 1:
        raise DrStudyError("structure legs span more than one expiry")
    legs = _legs_from_json(legs_json)
    net, max_profit, max_loss, _breakevens = _profile(legs, lot_size)
    for field, derived in (("net_premium_rs", round(net * lot_size, 2)), ("max_profit_rs", round(max_profit, 2)),
                           ("max_loss_rs", round(max_loss, 2))):
        stored = _finite(value.get(field), field)
        if abs(stored - derived) > _TOLERANCE_RS:
            raise DrStudyError(f"{field} does not reproduce from the bound legs")
    entry_cost = _finite(value.get("entry_cost_rs"), "entry_cost_rs")
    derived_cost = round(sum(calc_fno_costs(leg.premium, leg.premium, lot_size) for leg in legs), 2)
    if abs(entry_cost - derived_cost) > _TOLERANCE_RS:
        raise DrStudyError("entry_cost_rs does not reproduce from the bound legs and cost schedule")
    max_profit, max_loss = _finite(value["max_profit_rs"], "max_profit_rs", positive=True), \
        _finite(value["max_loss_rs"], "max_loss_rs", positive=True)
    try:
        opened_at = datetime.fromisoformat(str(value.get("opened_at")))
    except ValueError as exc:
        raise DrStudyError("opened_at is not a timestamp") from exc
    if opened_at.tzinfo is None:
        raise DrStudyError("opened_at must be timezone-aware")
    return DrEntry(
        position_ref=str(value["position_ref"]),
        source_ref="sha256:" + hashlib.sha256(envelope).hexdigest(), envelope=envelope,
        opened_at=opened_at, kind=str(value.get("kind")), lot_size=lot_size,
        legs_row={"legs_json": legs_json}, leg_tokens=tokens,
        leg_symbols=tuple(str(leg["contract"]["tradingsymbol"]) for leg in bound),
        max_profit=max_profit, max_loss=max_loss, entry_cost=entry_cost,
        settlement=dict(settlement or {}),
    )


@dataclass(frozen=True)
class DrObservation:
    observed_at: datetime
    quotes: Mapping[int, VerifiedQuote]


def observations_from_archive(events: Iterable[Mapping[str, Any]], entry: DrEntry, *,
                              max_age_seconds: int) -> tuple[list[DrObservation], dict[str, int]]:
    """Same-receipt verified quotes for every leg; anything less is excluded."""
    indexed = index_archive_events(events, entry.leg_tokens)
    receipts = set.intersection(*(set(indexed[token]) for token in entry.leg_tokens))
    observations, excluded = [], {}
    for received in sorted(receipts):
        quotes, reason = {}, None
        for token, symbol in zip(entry.leg_tokens, entry.leg_symbols):
            quote, issue = verify_archive_event(indexed[token][received], token=token, symbol=symbol,
                                                max_age_seconds=max_age_seconds)
            if issue is not None:
                reason = issue
                break
            quotes[token] = quote
        if reason is not None:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        observed_at = next(iter(quotes.values())).receipt_at
        if observed_at <= entry.opened_at:
            continue
        observations.append(DrObservation(observed_at=observed_at, quotes=quotes))
    return observations, excluded


def _lookups(entry: DrEntry, obs: DrObservation):
    by_key = {}
    legs = json.loads(entry.legs_row["legs_json"])
    for leg in legs:
        by_key[(float(leg["strike"]), str(leg["opt_type"]))] = obs.quotes[int(leg["contract"]["token"])]

    def mid(opt_type, strike):
        quote = by_key.get((float(strike), opt_type.value))
        value = quote.mid if quote is not None else None
        return value if value is not None and math.isfinite(value) and value > 0 else None

    def executable(opt_type, strike, quantity):
        quote = by_key.get((float(strike), opt_type.value))
        if quote is None:
            return None
        price = quote.bid if quantity > 0 else quote.ask  # sell longs at bid, buy back shorts at ask
        return price if price is not None and math.isfinite(price) and price > 0 else None
    return mid, executable


def simulate(entry: DrEntry, observations: Sequence[DrObservation], policy: str, *,
             max_gap_seconds: int) -> dict[str, Any]:
    if policy not in (BASELINE, TRAIL):
        raise DrStudyError("unknown defined-risk policy")
    legs = _legs_from_json(entry.legs_row["legs_json"])
    target = _target_frac() * entry.max_profit
    giveback = float(CANDIDATE_PARAMETERS["trail_giveback_fraction_of_max_profit"]) * entry.max_profit
    previous, peak, held = entry.opened_at, -math.inf, False
    if not observations:
        return {"policy": policy, "status": "INSUFFICIENT_EVIDENCE", "reason": "no_observations"}
    for obs in observations:
        if (obs.observed_at - previous).total_seconds() > max_gap_seconds:
            return {"policy": policy, "status": "INSUFFICIENT_EVIDENCE", "reason": "observation_gap_exceeds_declared_maximum"}
        previous = obs.observed_at
        now_ist = obs.observed_at.astimezone(IST)  # square-off is an IST wall-clock rule
        mid, executable = _lookups(entry, obs)
        mark = structure_mtm_rs(legs, entry.lot_size, mid)
        should_exit, reason = evaluate_dr_exit({"max_profit_rs": entry.max_profit, "max_loss_rs": entry.max_loss},
                                               mark, now_ist)
        if mark is not None:
            peak = max(peak, mark)
        if policy == TRAIL and reason == "target":
            held, should_exit = True, False
        if policy == TRAIL and held and not should_exit and mark is not None \
                and mark <= max(target, peak - giveback):
            should_exit, reason = True, "trail_giveback"
        if not should_exit:
            continue
        cash = structure_executable_pnl_rs(legs, entry.lot_size, executable)
        if mark is None or cash is None:
            if reason == "squareoff":
                return {"policy": policy, "status": "UNRESOLVED", "reason": "squareoff_unpriced",
                        "at": obs.observed_at.isoformat()}
            continue  # live behaviour: an unpriced target/stop is not exited
        if not math.isfinite(cash) or not math.isfinite(mark):
            raise DrStudyError("non-finite structure valuation")
        net = cash - entry.entry_cost
        return {"policy": policy, "status": "CLOSED", "reason": reason, "exit_at": obs.observed_at.isoformat(),
                "model_gross_pnl": round(mark, 6), "gross_pnl": round(cash, 6), "costs": round(entry.entry_cost, 6),
                "net_pnl": round(net, 6), "r_multiple": round(net / entry.max_loss, 8),
                "giveback_r": round((max(peak, mark) - mark) / entry.max_loss, 8),
                "minutes_exposed": round((obs.observed_at - entry.opened_at).total_seconds() / 60.0, 4),
                "net_pnl_cost_stressed": {f"{m:g}x": round(cash - m * entry.entry_cost, 6) for m in COST_MULTIPLIERS},
                "target_hold_activated": held}
    return {"policy": policy, "status": "INSUFFICIENT_EVIDENCE", "reason": "no_squareoff_observation"}


def reconcile(entry: DrEntry, baseline: Mapping[str, Any]) -> dict[str, Any]:
    """Compare the replayed baseline with the persisted settlement and ledger."""
    settlement = entry.settlement
    if settlement.get("status") != "CLOSED" or settlement.get("settlement_state") != "SETTLED":
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


def _source_fingerprint() -> str:
    here = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for name in _SOURCE_MODULES:
        data = (here / name).read_bytes().replace(b"\r\n", b"\n")
        digest.update(name.encode("utf-8") + b"\0" + hashlib.sha256(data).digest())
    return f"sha256:{digest.hexdigest()}"


def _frozen_terms() -> dict[str, Any]:
    return {"baseline_policy": BASELINE, "candidate_policy": TRAIL,
            "candidate_parameters": deepcopy(CANDIDATE_PARAMETERS),
            "live_settings": {"FNO_DR_TARGET_FRAC": _target_frac(), "FNO_DR_STOP_FRAC": _stop_frac(),
                              "FNO_DR_SQUAREOFF_MIN": _squareoff_min()},
            "cost_schedule": options_cost_snapshot(), "cost_multipliers": list(COST_MULTIPLIERS),
            "reconciliation_tolerance_rs": RECONCILIATION_TOLERANCE_RS,
            "max_gap_seconds": max(1, min(300, int(getattr(settings, "FNO_DR_STUDY_MAX_GAP_SECONDS", 180)))),
            "source_fingerprint": _source_fingerprint()}


def freeze_manifest(*, experiment_id: str, frozen_at: datetime | None = None) -> dict[str, Any]:
    experiment_id = (experiment_id or "").strip()
    if not experiment_id or len(experiment_id) > 160:
        raise DrStudyError("experiment_id must be a non-empty <=160-character string")
    frozen_at = frozen_at or datetime.now(timezone.utc)
    if frozen_at.tzinfo is None:
        raise DrStudyError("frozen_at must be timezone-aware")
    return {"schema": MANIFEST_SCHEMA, "experiment_id": experiment_id, **_frozen_terms(),
            "frozen_at": frozen_at.astimezone(timezone.utc).isoformat(),
            "holdout_rule": "only entries strictly after frozen_at are HOLDOUT"}


def verify_manifest(manifest: Mapping[str, Any]) -> datetime:
    if not isinstance(manifest, Mapping) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise DrStudyError(f"manifest schema must be {MANIFEST_SCHEMA}")
    for field, current in _frozen_terms().items():
        if _canonical_bytes({"v": manifest.get(field)}) != _canonical_bytes({"v": current}):
            raise DrStudyError(f"FROZEN_POLICY_MISMATCH: {field} differs from the frozen manifest")
    try:
        frozen_at = datetime.fromisoformat(str(manifest.get("frozen_at")).replace("Z", "+00:00"))
    except ValueError as exc:
        raise DrStudyError("manifest frozen_at is invalid") from exc
    if frozen_at.tzinfo is None:
        raise DrStudyError("manifest frozen_at must be timezone-aware")
    return frozen_at


def build_report(items: Sequence[tuple[DrEntry, Sequence[DrObservation], Mapping[str, int]]],
                 manifest: Mapping[str, Any], *, unavailable: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    frozen = verify_manifest(manifest)
    gap = int(manifest["max_gap_seconds"])
    seen, pairs = set(), []
    for entry, observations, excluded in items:
        if entry.position_ref in seen:
            raise DrStudyError(f"duplicate entry identity: {entry.position_ref}")
        seen.add(entry.position_ref)
        baseline = simulate(entry, observations, BASELINE, max_gap_seconds=gap)
        candidate = simulate(entry, observations, TRAIL, max_gap_seconds=gap)
        reconciliation = reconcile(entry, baseline)
        pairs.append({"position_ref": entry.position_ref, "source_ref": entry.source_ref, "kind": entry.kind,
                      "sample_class": "HOLDOUT" if entry.opened_at > frozen else "DEVELOPMENT",
                      "excluded_observations": dict(excluded), "baseline": baseline, "candidate": candidate,
                      "reconciliation": reconciliation})

    def section(sample: str) -> dict[str, Any]:
        chosen = [pair for pair in pairs if pair["sample_class"] == sample]
        usable = [pair for pair in chosen if pair["reconciliation"]["usable"]]
        return {"pairs": len(chosen), "reconciled_usable": len(usable),
                "baseline": policy_summary([pair["baseline"] for pair in usable]),
                "candidate": policy_summary([pair["candidate"] for pair in usable]),
                "paired": paired_deltas(usable)}

    report = {"schema": REPORT_SCHEMA, "experiment_id": manifest["experiment_id"],
              "manifest_fingerprint": "sha256:" + hashlib.sha256(_canonical_bytes(dict(manifest))).hexdigest(),
              "manifest": dict(manifest), "unavailable_entries": list(unavailable), "pairs": pairs,
              "holdout": section("HOLDOUT"), "development": section("DEVELOPMENT"),
              "qualification": "NOT_ASSESSED", "authorization_effect": "NONE",
              "warning": ("Paired deltas use only entries whose baseline replay reconciles to persisted "
                          "settlement and ledger cash. Paper research is not authority to alter DR exits.")}
    report["report_fingerprint"] = "sha256:" + hashlib.sha256(_canonical_bytes(report)).hexdigest()
    return report


def entries_from_db(db_path: str) -> tuple[list[DrEntry], list[dict[str, Any]]]:
    """Read-only: every bound DR row with its settlement and ledger cash."""
    import sqlite3
    path = Path(db_path)
    if not path.is_file():
        return [], [{"reason": "database_unavailable_or_missing"}]
    con = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    entries, unavailable = [], []
    try:
        rows = con.execute("SELECT * FROM fno_dr_positions ORDER BY id").fetchall()
        for row in rows:
            ref = f"fno_dr_positions:{row['id']}"
            try:
                envelope = entry_envelope(dict(row))
                try:
                    ledger = con.execute("SELECT SUM(pnl), COUNT(*) FROM bankroll_ledger WHERE origin_ref=?",
                                         (f"fno_dr_structure:{row['id']}",)).fetchone()
                except sqlite3.Error:
                    ledger = (None, 0)
                settlement = {"status": row["status"], "settlement_state": row["settlement_state"],
                              "exit_reason": row["exit_reason"], "position_net_pnl": row["pnl"],
                              "ledger_net_pnl": None if not ledger[1] else float(ledger[0])}
                entries.append(verify_entry(envelope, settlement))
            except DrStudyError as exc:
                unavailable.append({"position_ref": ref, "reason": str(exc)})
    finally:
        con.close()
    return entries, unavailable


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evidence-bound defined-risk exit experiment")
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--experiment-id", required=True)
    freeze.add_argument("--output", required=True)
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--db", required=True, help="engine SQLite (opened read-only)")
    evaluate.add_argument("--archive-root", required=True)
    evaluate.add_argument("--manifest", required=True)
    evaluate.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "freeze":
            value = freeze_manifest(experiment_id=args.experiment_id)
        else:
            from intraday_spread_archive_adapter import read_archived_quote_events
            manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
            entries, unavailable = entries_from_db(args.db)
            items = []
            for entry in entries:
                day = entry.opened_at.astimezone(entry.opened_at.tzinfo).date().isoformat()
                events = read_archived_quote_events(args.archive_root, days=[day])
                observations, excluded = observations_from_archive(
                    events, entry, max_age_seconds=int(manifest["max_gap_seconds"]))
                items.append((entry, observations, excluded))
            value = build_report(items, manifest, unavailable=unavailable)
        write_study_report_once(value, args.output)
    except (ExitStudyError, OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(_main())
