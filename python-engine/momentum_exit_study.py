"""Read-only paired research for momentum-paper exit policies.

This module deliberately has no database, broker, HTTP, scheduler, order, or
message dependency.  It replays already captured timestamped LTP observations
and compares the production pure exit evaluator with one fixed paper-only
target-hold/trail alternative.  It is not imported by any runtime manager.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, time
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from config import settings
from engine import calc_zerodha_costs
from momentum_exits import (
    ACTION_EXIT,
    ACTION_SCALE_OUT,
    ACTION_TRAIL,
    evaluate_momentum_exit,
)


IST = ZoneInfo("Asia/Kolkata")
INPUT_SCHEMA = "momentum_exit_study_input_v1"
REPORT_SCHEMA = "momentum_exit_study_report_v1"
BASELINE_POLICY = "current_momentum_exit_evaluator_v1"
ALTERNATIVE_POLICY = "target_hold_trail_v1"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_PACKET_BYTES = 16 * 1024 * 1024
_MAX_ENTRIES = 500
_MAX_QUOTES = 250_000
_POLICY_SETTINGS = (
    "MOMENTUM_USE_SCALE_OUT",
    "MOMENTUM_SCALE_OUT_R",
    "MOMENTUM_SCALE_OUT_FRAC",
    "MOMENTUM_BREAKEVEN_R",
    "MOMENTUM_USE_TRAIL",
    "MOMENTUM_TRAIL_ATR_MULT",
    "MOMENTUM_TIME_STOP_FAST_MIN",
    "MOMENTUM_TIME_STOP_FAST_R",
    "MOMENTUM_TIME_STOP_MIN",
    "MOMENTUM_TIME_STOP_MIN_R",
    "MOMENTUM_TIME_STOP_R1_MULT",
    "MOMENTUM_TIME_STOP_R2_MULT",
    "MOMENTUM_TIME_STOP_R3_MULT",
    "MOMENTUM_FAST_STOP_USES_THESIS",
)


class ExitStudyError(ValueError):
    """The input packet cannot support an honest study."""


@dataclass(frozen=True)
class StudyEntry:
    entry_id: str
    source_ref: str
    ticker: str
    entry_at: datetime
    entry_price: float
    stop_loss_initial: float
    target_1: float
    shares: int
    atr_14_at_entry: float | None
    vwap_at_entry: float | None
    regime_at_entry: str | None


@dataclass(frozen=True)
class Quote:
    observed_at: datetime
    ltp: float


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _parse_timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ExitStudyError(f"{field} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExitStudyError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExitStudyError(f"{field} must include a timezone offset")
    return parsed.astimezone(IST)


def _finite_positive(value: object, field: str) -> float:
    if isinstance(value, bool):
        raise ExitStudyError(f"{field} must be a finite positive number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ExitStudyError(f"{field} must be a finite positive number") from exc
    if not math.isfinite(number) or number <= 0:
        raise ExitStudyError(f"{field} must be a finite positive number")
    return number


def _optional_positive(value: object, field: str) -> float | None:
    if value is None:
        return None
    return _finite_positive(value, field)


def _entry_from_json(raw: object) -> StudyEntry:
    if not isinstance(raw, dict):
        raise ExitStudyError("entry must be an object")
    entry_id_raw = raw.get("entry_id")
    entry_id = entry_id_raw.strip() if isinstance(entry_id_raw, str) else ""
    if not entry_id or len(entry_id) > 160:
        raise ExitStudyError("entry.entry_id must be a non-empty <=160-character string")
    source_ref = raw.get("source_ref") if isinstance(raw.get("source_ref"), str) else ""
    if not _SHA256.fullmatch(source_ref):
        raise ExitStudyError("entry.source_ref must be a sha256: archive reference")
    ticker_raw = raw.get("ticker")
    ticker = ticker_raw.strip().upper() if isinstance(ticker_raw, str) else ""
    if not ticker or len(ticker) > 64:
        raise ExitStudyError("entry.ticker must be a non-empty <=64-character string")
    shares_raw = raw.get("shares")
    if isinstance(shares_raw, bool) or not isinstance(shares_raw, int):
        raise ExitStudyError("entry.shares must be a positive integer")
    shares = shares_raw
    if shares <= 0:
        raise ExitStudyError("entry.shares must be a positive integer")
    entry_price = _finite_positive(raw.get("entry_price"), "entry.entry_price")
    stop = _finite_positive(raw.get("stop_loss_initial"), "entry.stop_loss_initial")
    target = _finite_positive(raw.get("target_1"), "entry.target_1")
    if stop >= entry_price:
        raise ExitStudyError("entry.stop_loss_initial must be below entry.entry_price")
    if target <= entry_price:
        raise ExitStudyError("entry.target_1 must exceed entry.entry_price")
    return StudyEntry(
        entry_id=entry_id,
        source_ref=source_ref,
        ticker=ticker,
        entry_at=_parse_timestamp(raw.get("entry_at"), "entry.entry_at"),
        entry_price=entry_price,
        stop_loss_initial=stop,
        target_1=target,
        shares=shares,
        atr_14_at_entry=_optional_positive(raw.get("atr_14_at_entry"), "entry.atr_14_at_entry"),
        vwap_at_entry=_optional_positive(raw.get("vwap_at_entry"), "entry.vwap_at_entry"),
        regime_at_entry=(str(raw["regime_at_entry"]).strip() if raw.get("regime_at_entry") is not None else None),
    )


def _quotes_from_json(raw: object, entry_ids: set[str]) -> dict[str, list[Quote]]:
    if not isinstance(raw, list) or len(raw) > _MAX_QUOTES:
        raise ExitStudyError("quotes must be an array within the study limit")
    grouped: dict[str, list[Quote]] = {entry_id: [] for entry_id in entry_ids}
    for row in raw:
        if not isinstance(row, dict):
            raise ExitStudyError("quote must be an object")
        raw_entry_id = row.get("entry_id")
        entry_id = raw_entry_id if isinstance(raw_entry_id, str) else ""
        if entry_id not in grouped:
            raise ExitStudyError("quote.entry_id does not identify a declared entry")
        grouped[entry_id].append(Quote(
            observed_at=_parse_timestamp(row.get("observed_at"), "quote.observed_at"),
            ltp=_finite_positive(row.get("ltp"), "quote.ltp"),
        ))
    return grouped


def load_exit_study_packet(path: str | os.PathLike[str]) -> tuple[dict[str, Any], list[StudyEntry], dict[str, list[Quote]], str]:
    """Read and validate a bounded immutable JSON study packet.

    The returned digest identifies the exact bytes that were evaluated.  The
    reader never writes to the packet or to any database/cache.
    """
    packet_path = Path(path)
    try:
        raw_bytes = packet_path.read_bytes()
    except OSError as exc:
        raise ExitStudyError(f"study input is unreadable: {exc}") from exc
    if not raw_bytes or len(raw_bytes) > _MAX_PACKET_BYTES:
        raise ExitStudyError("study input must be non-empty and within 16 MiB")
    try:
        packet = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExitStudyError("study input must be UTF-8 JSON") from exc
    if not isinstance(packet, dict) or packet.get("schema") != INPUT_SCHEMA:
        raise ExitStudyError(f"study input schema must be {INPUT_SCHEMA}")
    study_id = str(packet.get("study_id") or "").strip()
    if not study_id or len(study_id) > 160:
        raise ExitStudyError("study_id must be a non-empty <=160-character string")
    max_gap = packet.get("max_quote_gap_seconds")
    if isinstance(max_gap, bool) or not isinstance(max_gap, int) or not 1 <= max_gap <= 300:
        raise ExitStudyError("max_quote_gap_seconds must be an integer from 1 through 300")
    entries_raw = packet.get("entries")
    if not isinstance(entries_raw, list) or not entries_raw or len(entries_raw) > _MAX_ENTRIES:
        raise ExitStudyError("entries must be a non-empty array within the study limit")
    entries = [_entry_from_json(item) for item in entries_raw]
    entry_ids = [entry.entry_id for entry in entries]
    if len(entry_ids) != len(set(entry_ids)):
        raise ExitStudyError("entry_id values must be unique")
    quotes = _quotes_from_json(packet.get("quotes"), set(entry_ids))
    return packet, entries, quotes, f"sha256:{hashlib.sha256(raw_bytes).hexdigest()}"


def _policy_snapshot() -> dict[str, Any]:
    snapshot = {name: getattr(settings, name) for name in _POLICY_SETTINGS}
    return {
        "baseline": BASELINE_POLICY,
        "alternative": {
            "name": ALTERNATIVE_POLICY,
            "activation": "when_baseline_would_exit_target_hit",
            "trail_distance_r": 0.5,
            "initial_stop_unchanged": True,
            "current_time_stops_unchanged": True,
            "deadline": "15:15 Asia/Kolkata",
        },
        "evaluator_settings": snapshot,
        "cost_model": "engine.calc_zerodha_costs_intraday",
    }


def _deadline(entry: StudyEntry) -> datetime:
    return datetime.combine(entry.entry_at.date(), time(15, 15), tzinfo=IST)


def _validated_quote_path(entry: StudyEntry, quotes: Sequence[Quote],
                          max_gap_seconds: int) -> tuple[list[Quote], str | None]:
    if entry.entry_at.time() >= time(15, 15):
        return [], "entry_at_or_after_intraday_deadline"
    deadline = _deadline(entry)
    if not quotes:
        return [], "no_quotes"
    previous: Quote | None = None
    normalised: list[Quote] = []
    deadline_quote = False
    for quote in quotes:
        if quote.observed_at.date() != entry.entry_at.date():
            return [], "quote_crosses_intraday_session"
        if quote.observed_at < entry.entry_at:
            return [], "quote_precedes_entry"
        if previous is not None:
            if quote.observed_at < previous.observed_at:
                return [], "quote_clock_not_strictly_increasing"
            if quote.observed_at == previous.observed_at:
                if quote.ltp != previous.ltp:
                    return [], "conflicting_quote_clock"
                continue  # Exact duplicate preservation packet; idempotent.
        if quote.observed_at <= deadline and previous is not None and (
            quote.observed_at - previous.observed_at
        ).total_seconds() > max_gap_seconds:
            return [], "quote_gap_exceeds_declared_maximum"
        previous = quote
        if quote.observed_at <= deadline:
            normalised.append(quote)
        if quote.observed_at == deadline:
            deadline_quote = True
    if not normalised:
        return [], "no_quotes_at_or_before_intraday_deadline"
    if (normalised[0].observed_at - entry.entry_at).total_seconds() > max_gap_seconds:
        return [], "initial_quote_gap_exceeds_declared_maximum"
    if not deadline_quote:
        return [], "exact_1515_ist_quote_missing"
    return normalised, None


def _position(entry: StudyEntry) -> dict[str, Any]:
    return {
        "ticker": entry.ticker,
        "entry_date": entry.entry_at.isoformat(),
        "entry_price": entry.entry_price,
        "stop_loss_initial": entry.stop_loss_initial,
        "trailing_stop_current": entry.stop_loss_initial,
        "target_1": entry.target_1,
        "shares": entry.shares,
        "atr_14_at_entry": entry.atr_14_at_entry,
        "vwap_at_entry": entry.vwap_at_entry,
        "regime_at_entry": entry.regime_at_entry,
        "t1_fired": False,
    }


def _leg(entry: StudyEntry, quantity: int, exit_price: float, reason: str, at: datetime) -> dict[str, Any]:
    gross = (exit_price - entry.entry_price) * quantity
    costs = calc_zerodha_costs(entry.entry_price, exit_price, quantity, is_intraday=True)
    return {
        "at": at.isoformat(),
        "reason": reason,
        "quantity": quantity,
        "exit_price": round(exit_price, 6),
        "gross_pnl": round(gross, 6),
        "costs": round(costs, 6),
        "net_pnl": round(gross - costs, 6),
    }


def _finalise(entry: StudyEntry, variant: str, state: dict[str, Any],
              observed_prices: Sequence[float]) -> dict[str, Any]:
    legs = state["legs"]
    if not state["closed"]:
        return {
            "policy": variant,
            "status": "UNRESOLVED",
            "reason": state.get("reason", "path_ended_before_close"),
            "legs": legs,
        }
    gross = sum(float(leg["gross_pnl"]) for leg in legs)
    costs = sum(float(leg["costs"]) for leg in legs)
    net = sum(float(leg["net_pnl"]) for leg in legs)
    initial_risk = (entry.entry_price - entry.stop_loss_initial) * entry.shares
    max_observed = max(observed_prices)
    observed_mfe_cash = max(0.0, max_observed - entry.entry_price) * entry.shares
    capture = None
    if observed_mfe_cash > 0:
        capture = max(0.0, gross) / observed_mfe_cash
    return {
        "policy": variant,
        "status": "CLOSED",
        "reason": state["reason"],
        "exit_at": state["exit_at"].isoformat(),
        "gross_pnl": round(gross, 6),
        "costs": round(costs, 6),
        "net_pnl": round(net, 6),
        "r_multiple": round(net / initial_risk, 8),
        "max_observed_ltp": round(max_observed, 6),
        "observed_mfe_cash": round(observed_mfe_cash, 6),
        "gross_capture_ratio": round(capture, 8) if capture is not None else None,
        "legs": legs,
        "target_hold_activated_at": state.get("target_hold_activated_at"),
    }


def _close(entry: StudyEntry, state: dict[str, Any], price: float,
           reason: str, at: datetime) -> None:
    quantity = int(state["position"]["shares"])
    state["legs"].append(_leg(entry, quantity, price, reason, at))
    state.update({"closed": True, "reason": reason, "exit_at": at})


def _apply_current_decision(entry: StudyEntry, state: dict[str, Any], quote: Quote,
                            *, suppress_target: bool, hold_target: bool) -> str | None:
    position = state["position"]
    current_stop = float(position["trailing_stop_current"])
    # Live momentum protection is a broker SL-M; a read-only LTP replay must
    # represent the first observed trigger rather than silently ignoring stops.
    if quote.ltp <= current_stop:
        _close(entry, state, quote.ltp, "protective_stop_observed", quote.observed_at)
        return "closed"
    decision_position = dict(position)
    if suppress_target:
        decision_position["target_1"] = None
    decision = evaluate_momentum_exit(decision_position, quote.ltp, quote.observed_at)
    action = decision.get("action")
    if action == ACTION_EXIT:
        if hold_target and decision.get("reason") == "target_hit":
            return "target_hit"
        _close(entry, state, quote.ltp, str(decision.get("reason") or "exit"), quote.observed_at)
        return "closed"
    if action == ACTION_SCALE_OUT:
        sold = int(decision.get("scale_shares") or 0)
        remaining = int(position["shares"]) - sold
        if not 0 < sold < int(position["shares"]) or remaining < 1:
            state["reason"] = "invalid_scale_out_decision"
            return "invalid"
        state["legs"].append(_leg(entry, sold, quote.ltp, str(decision.get("reason") or "scale_out"), quote.observed_at))
        position["shares"] = remaining
        position["t1_fired"] = True
        position["trailing_stop_current"] = float(decision["new_stop"])
    elif action == ACTION_TRAIL and decision.get("new_stop") is not None:
        position["trailing_stop_current"] = max(
            float(position["trailing_stop_current"]), float(decision["new_stop"]),
        )
    return None


def _simulate(entry: StudyEntry, quotes: Sequence[Quote], variant: str) -> dict[str, Any]:
    state: dict[str, Any] = {"position": _position(entry), "legs": [], "closed": False}
    observed_prices = [quote.ltp for quote in quotes if quote.observed_at <= _deadline(entry)]
    r_per_share = entry.entry_price - entry.stop_loss_initial
    for quote in quotes:
        if quote.observed_at > _deadline(entry) or state["closed"]:
            continue
        suppress_target = variant == ALTERNATIVE_POLICY and bool(state.get("target_hold_activated_at"))
        result = _apply_current_decision(
            entry, state, quote,
            suppress_target=suppress_target,
            hold_target=(variant == ALTERNATIVE_POLICY and not suppress_target),
        )
        if state["closed"] or result == "invalid":
            continue
        if result == "target_hit":
            # Target handling is the only intentional behavioural difference:
            # current evaluator reached target at this exact observation, but
            # the study holds with a fixed 0.5R trail instead of closing.
            state["target_hold_activated_at"] = quote.observed_at.isoformat()
            state["position"]["target_1"] = None
            state["position"]["t1_fired"] = True
            state["position"]["trailing_stop_current"] = max(
                float(state["position"]["trailing_stop_current"]),
                quote.ltp - (0.5 * r_per_share),
            )
        if variant == ALTERNATIVE_POLICY and state.get("target_hold_activated_at"):
            state["position"]["trailing_stop_current"] = max(
                float(state["position"]["trailing_stop_current"]),
                quote.ltp - (0.5 * r_per_share),
            )
    if not state["closed"]:
        deadline_quote = next(quote for quote in quotes if quote.observed_at == _deadline(entry))
        _close(entry, state, deadline_quote.ltp, "intraday_deadline", deadline_quote.observed_at)
    return _finalise(entry, variant, state, observed_prices)


def _insufficient_pair(entry: StudyEntry, issue: str) -> dict[str, Any]:
    evidence = {
        "entry_id": entry.entry_id,
        "ticker": entry.ticker,
        "source_ref": entry.source_ref,
        "status": "INSUFFICIENT_EVIDENCE",
        "reason": issue,
    }
    return {
        **evidence,
        "baseline": {"policy": BASELINE_POLICY, "status": "INSUFFICIENT_EVIDENCE", "reason": issue, "legs": []},
        "alternative": {"policy": ALTERNATIVE_POLICY, "status": "INSUFFICIENT_EVIDENCE", "reason": issue, "legs": []},
    }


def _summary(results: Sequence[dict[str, Any]], key: str) -> dict[str, Any]:
    closed = [row[key] for row in results if row[key]["status"] == "CLOSED"]
    ordered = sorted(closed, key=lambda row: (row["exit_at"], row["policy"]))
    equity = peak = max_drawdown = 0.0
    for row in ordered:
        equity += float(row["net_pnl"])
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    captures = [float(row["gross_capture_ratio"]) for row in closed if row["gross_capture_ratio"] is not None]
    return {
        "complete_pairs": len(closed),
        "unresolved_pairs": len(results) - len(closed),
        "net_pnl": round(equity, 6) if closed else None,
        "costs": round(sum(float(row["costs"]) for row in closed), 6) if closed else None,
        "avg_r_multiple": round(sum(float(row["r_multiple"]) for row in closed) / len(closed), 8) if closed else None,
        "max_drawdown": round(max_drawdown, 6) if closed else None,
        "mean_gross_capture_ratio": round(sum(captures) / len(captures), 8) if captures else None,
    }


def build_momentum_exit_study(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Build a deterministic paired report without changing any application state."""
    packet, entries, grouped_quotes, input_fingerprint = load_exit_study_packet(path)
    max_gap = int(packet["max_quote_gap_seconds"])
    pairs = []
    for entry in sorted(entries, key=lambda item: item.entry_id):
        quotes, issue = _validated_quote_path(entry, grouped_quotes[entry.entry_id], max_gap)
        if issue is not None:
            pairs.append(_insufficient_pair(entry, issue))
            continue
        pairs.append({
            "entry_id": entry.entry_id,
            "ticker": entry.ticker,
            "source_ref": entry.source_ref,
            "status": "COMPLETE",
            "baseline": _simulate(entry, quotes, BASELINE_POLICY),
            "alternative": _simulate(entry, quotes, ALTERNATIVE_POLICY),
        })
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "study_id": packet["study_id"],
        "input_fingerprint": input_fingerprint,
        "policy": _policy_snapshot(),
        "evidence_contract": {
            "timezone": "Asia/Kolkata",
            "max_quote_gap_seconds": max_gap,
            "deadline": "15:15",
            "missing_or_ambiguous_path": "INSUFFICIENT_EVIDENCE",
            "outcomes_are": "paper_research_only",
        },
        "pairs": pairs,
        "summary": {
            "baseline": _summary(pairs, "baseline"),
            "alternative": _summary(pairs, "alternative"),
            "qualification": "NOT_ASSESSED",
            "warning": "This paired replay is not evidence of a profitable edge or authority to change live exits.",
        },
    }
    canonical_without_fingerprint = _canonical_bytes(report)
    report["report_fingerprint"] = f"sha256:{hashlib.sha256(canonical_without_fingerprint).hexdigest()}"
    return report


def write_study_report_once(report: Mapping[str, Any], output_path: str | os.PathLike[str]) -> None:
    """Write canonical evidence once; never replace an existing report."""
    payload = _canonical_bytes(dict(report)) + b"\n"
    path = os.fspath(output_path)
    fd: int | None = None
    created = False
    complete = False
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        offset = 0
        while offset < len(payload):
            written = os.write(fd, payload[offset:])
            if written <= 0:
                raise OSError("exclusive report write made no progress")
            offset += written
        os.fsync(fd)
        complete = True
    except OSError as exc:
        raise ExitStudyError(f"report write failed without overwrite: {exc}") from exc
    finally:
        if fd is not None:
            os.close(fd)
        if created and not complete:
            try:
                os.unlink(path)
            except OSError:
                pass


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only momentum exit comparison")
    parser.add_argument("--input", required=True, help="immutable JSON input packet")
    parser.add_argument("--output", help="new report path; fails if it already exists")
    args = parser.parse_args(argv)
    try:
        report = build_momentum_exit_study(args.input)
        if args.output:
            write_study_report_once(report, args.output)
        else:
            print(_canonical_bytes(report).decode("utf-8"))
    except ExitStudyError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(_main())
