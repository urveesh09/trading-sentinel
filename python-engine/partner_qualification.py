"""Causal research adapter for the deployed intraday partner policy.

This module intentionally composes the same signal, candidate builder and
validation functions used by the advisory path.  It creates research facts;
it cannot write qualifications, dispatch advice, or place orders.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
from zoneinfo import ZoneInfo

from config import settings
from fno_chain import ChainSnapshot
from fno_engine_mom import MomSignal, evaluate_fno_mom
from fno_instruments import FnoInstruments
from partner_manual_advisory import (
    AdvisoryCandidate, AdvisoryScope, PartnerAdvisoryProfile, StrategyEvidence,
    build_directional_debit_spread, validate_candidate, validate_profile,
)


FULL_POLICY_EVALUATOR = "partner_manual_intraday_full_policy_v1"


def load_candidate_evidence(value: Mapping[str, Any], *, underlying: str, decision_at: datetime,
                            archive_root=None, master_sha256=None):
    """Decode an offline chain/profile bundle. Never fetch or persist instruments."""
    from fno_models import Contract, ContractQuote
    name = underlying.upper()
    expected_segment = {"NIFTY": "NFO", "SENSEX": "BFO"}.get(name)
    if value.get("underlying") != name or value.get("segment") != expected_segment:
        raise ValueError("candidate evidence index/segment mismatch")
    received = datetime.fromisoformat(str(value["received_at"]))
    if _clock(received, "chain received_at") > _clock(decision_at, "decision_at"):
        raise ValueError("chain evidence unavailable at decision time")
    if value.get("decision_clock") is not None:
        from partner_decision_clock import validate_clock_payload
        clocks = validate_clock_payload(value["decision_clock"]).payload()
        if (clocks.get("underlying") != name
                or clocks.get("chain_received_at") != received.isoformat()
                or datetime.fromisoformat(str(clocks.get("candidate_constructed_at"))) > decision_at):
            raise ValueError("candidate decision clock mismatch")
    contracts = []
    for raw in value["contracts"]:
        item = dict(raw)
        item["expiry"] = date.fromisoformat(item["expiry"])
        contract = Contract(**item)
        if contract.name != name or contract.token <= 0 or contract.lot_size <= 0:
            raise ValueError("invalid candidate evidence contract")
        contracts.append(contract)
    if not contracts or len({c.token for c in contracts}) != len(contracts):
        raise ValueError("candidate evidence contracts must be nonempty and unique")
    if len({(c.expiry, c.strike, c.instrument_type) for c in contracts}) != len(contracts):
        raise ValueError("duplicate candidate contract terms")
    if archive_root is not None:
        from intraday_spread_archive_adapter import SpreadContractIdentity, _master_proves_contract
        if not isinstance(master_sha256, str) or len(master_sha256) != 64:
            raise ValueError("archive verification requires a master digest")
        for contract in contracts:
            identity = SpreadContractIdentity(contract.token, contract.tradingsymbol, name, expected_segment,
                contract.instrument_type, contract.strike, contract.expiry.isoformat(), contract.lot_size)
            if not _master_proves_contract(archive_root, identity, master_sha256):
                raise ValueError("archived master does not prove candidate contract")
    by_token = {c.token: c for c in contracts}
    book = FnoInstruments(name, segment=expected_segment)
    book._load_contracts(contracts)
    snap_raw = value["snapshot"]
    taken = _clock(datetime.fromisoformat(snap_raw["taken_at"]), "chain taken_at")
    if taken > received:
        raise ValueError("chain observation follows receipt")
    quotes = {}
    for raw in snap_raw["quotes"]:
        item = dict(raw)
        contract = by_token[item.pop("token")]
        stamp = item.get("last_trade_time")
        if stamp is not None:
            item["last_trade_time"] = _clock(datetime.fromisoformat(stamp), "quote timestamp")
            if item["last_trade_time"] > received:
                raise ValueError("quote timestamp follows receipt")
        key = (contract.strike, contract.instrument_type)
        if key in quotes:
            raise ValueError("duplicate candidate quote")
        quotes[key] = ContractQuote(contract=contract, **item)
    future = None
    if snap_raw.get("future_quote") is not None:
        item = dict(snap_raw["future_quote"])
        contract = by_token[item.pop("token")]
        if contract.instrument_type != "FUT":
            raise ValueError("future quote must identify a futures contract")
        if item.get("last_trade_time") is not None:
            item["last_trade_time"] = _clock(datetime.fromisoformat(item["last_trade_time"]), "future quote timestamp")
            if item["last_trade_time"] > received:
                raise ValueError("future quote timestamp follows receipt")
        future = ContractQuote(contract=contract, **item)
    requested_tokens = tuple(int(token) for token in snap_raw.get("requested_tokens", ()))
    received_tokens = tuple(int(token) for token in snap_raw.get("received_tokens", ()))
    if received_tokens and not set(received_tokens).issubset(set(requested_tokens)):
        raise ValueError("candidate snapshot receipt coverage is invalid")
    snapshot = ChainSnapshot(taken, date.fromisoformat(snap_raw["expiry"]), snap_raw["forward"],
                             snap_raw.get("parity_forward"), snap_raw["lot_size"], future, quotes,
                             requested_tokens, received_tokens)
    profile_value = dict(value["profile"])
    for field in ("enabled_scopes", "instruments", "permitted_structures"):
        if field in profile_value:
            if not isinstance(profile_value[field], (list, tuple)):
                raise ValueError(f"profile {field} must be a sequence")
            profile_value[field] = tuple(profile_value[field])
    profile = PartnerAdvisoryProfile(**profile_value)
    return book, snapshot, profile


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _clock(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value


def _signal_payload(signal: MomSignal) -> dict[str, Any]:
    value = asdict(signal)
    value["direction"] = signal.direction.value if signal.direction else None
    return value


def _bars_payload(bars: pd.DataFrame) -> list[dict[str, Any]]:
    if bars is None or bars.empty:
        return []
    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(bars.columns):
        raise ValueError("full policy bars are missing OHLCV columns")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.hasnans or not bars.index.is_unique:
        raise ValueError("full policy bars require unique valid datetime starts")
    if not bars.index.is_monotonic_increasing:
        raise ValueError("full policy bars must be chronological")
    for _, row in bars.iterrows():
        values = {field: float(row[field]) for field in required}
        if not all(math.isfinite(value) for value in values.values()):
            raise ValueError("full policy OHLCV must be finite")
        if (min(values[field] for field in ("open", "high", "low", "close")) <= 0
                or values["volume"] < 0
                or values["low"] > min(values["open"], values["close"])
                or values["high"] < max(values["open"], values["close"])):
            raise ValueError("full policy OHLCV is inconsistent")
    return [{"bar_start": str(index), **{field: float(row[field]) for field in sorted(required)}}
            for index, row in bars.sort_index().iterrows()]


def _causal_provenance(value: Mapping[str, Any], decision_at: datetime) -> dict[str, Any]:
    """Normalize event, receipt and retrieval clocks without hindsight repair."""
    if not isinstance(value, Mapping):
        raise ValueError("bar provenance is required")
    state = str(value.get("state", "")).upper()
    if state not in {"CONTEMPORANEOUS", "ACQUIRED_AFTER_FROZEN_CUTOFF", "RETROSPECTIVE", "MISSING"}:
        raise ValueError("bar provenance state is invalid")
    normalized = {"state": state, "source": str(value.get("source", "")).strip()}
    if not normalized["source"]:
        raise ValueError("bar provenance source is required")
    for key in ("event_at", "received_at", "retrieved_at"):
        raw = value.get(key)
        if raw is None:
            normalized[key] = None
            continue
        parsed = _clock(raw, f"bar provenance {key}")
        normalized[key] = parsed.isoformat()
    if state == "CONTEMPORANEOUS":
        received = value.get("received_at")
        if received is None or _clock(received, "bar provenance received_at") > decision_at:
            raise ValueError("contemporaneous bar evidence was unavailable at decision time")
        event_at = value.get("event_at")
        if event_at is not None and _clock(event_at, "bar provenance event_at") > decision_at:
            raise ValueError("contemporaneous bar event is after decision time")
    if state == "ACQUIRED_AFTER_FROZEN_CUTOFF":
        received = value.get("received_at")
        if received is None or _clock(received, "bar provenance received_at") > decision_at:
            raise ValueError("frozen-cutoff bar evidence was unavailable at decision time")
    if state == "MISSING" and any(value.get(key) is not None for key in ("event_at", "received_at")):
        raise ValueError("missing bar evidence cannot claim event or receipt timestamps")
    return normalized


def policy_manifest(*, underlying: str, structure_kind: str, bars: pd.DataFrame,
                    regime: str, decision_at: datetime, bar_provenance: Mapping[str, Any],
                    contract_master_sha256: str | None = None,
                    profile: PartnerAdvisoryProfile | None = None,
                    evaluation_cutoff_at: datetime | None = None,
                    decision_clock: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Freeze code/config/input identity for one full-policy decision."""
    now = _clock(decision_at, "decision_at").astimezone(ZoneInfo("Asia/Kolkata"))
    cutoff = _clock(evaluation_cutoff_at or now, "evaluation_cutoff_at").astimezone(ZoneInfo("Asia/Kolkata"))
    if cutoff > now:
        raise ValueError("evaluation cutoff cannot follow decision time")
    name = underlying.upper()
    if name not in {"NIFTY", "SENSEX"} or structure_kind != "DIRECTIONAL_DEBIT_SPREAD":
        raise ValueError("only NIFTY/SENSEX directional debit-spread policy is supported")
    if contract_master_sha256 is not None and (len(contract_master_sha256) != 64 or any(c not in "0123456789abcdef" for c in contract_master_sha256.lower())):
        raise ValueError("contract_master_sha256 must be a SHA-256 digest")
    if decision_clock is not None:
        from partner_decision_clock import CLOCK_POLICY, validate_clock_payload
        decision_clock = validate_clock_payload(decision_clock).payload()
        if (decision_clock.get("policy") != CLOCK_POLICY
                or decision_clock.get("underlying") != name
                or decision_clock.get("evaluation_cutoff_at") != cutoff.isoformat()
                or decision_clock.get("candidate_constructed_at") != now.isoformat()
                or not decision_clock.get("run_id") or not decision_clock.get("account_id")):
            raise ValueError("decision clock scope or identity mismatch")
        for field in ("public_received_at", "chain_received_at"):
            if decision_clock.get(field) is None or _clock(datetime.fromisoformat(decision_clock[field]), field) > now:
                raise ValueError("decision clock source receipt is missing or late")
    config = {key: getattr(settings, key) for key in (
        "FNO_OR_MINUTES", "FNO_ATR_LEN", "FNO_EMA_FAST", "FNO_EMA_SLOW", "FNO_RVOL_LOOKBACK_DAYS",
        "FNO_OR_BUFFER_ATR", "FNO_STOP_ATR_MULT", "FNO_TARGET_R", "FNO_MIN_RVOL",
        "PARTNER_MANUAL_ADVISORY_QUOTE_TTL_SEC", "PARTNER_MANUAL_ADVISORY_MAX_QUOTE_AGE_SEC",
        "PARTNER_MANUAL_ADVISORY_MAX_SPREAD_PCT", "PARTNER_MANUAL_ADVISORY_MIN_OI",
        "PARTNER_MANUAL_ADVISORY_MIN_VOLUME", "PARTNER_MANUAL_ADVISORY_MIN_DEPTH_UNITS",
        # [WORKFLOW-A4 2026-09-20] Cost / fee / exit semantics drive
        # full-policy economics. Including them in the identity
        # means a fee-model change invalidates old evidence. Keys
        # not present in a particular deployment are dropped with
        # a sentinel so the identity hash is still computable.
        "FNO_TICK_SIZE", "FNO_STOP_PREMIUM_PCT",
        "FNO_SLIPPAGE_BPS", "FNO_FEE_RATE",
        "MOMENTUM_STOP_PCT", "MOMENTUM_TARGET_R",
        "PENNY_STOP_PCT", "PENNY_FEE_RATE",
        "PARTNER_VERIFY_RESEARCH_ARTIFACTS",
    ) if hasattr(settings, key)}
    bar_rows = _bars_payload(bars)
    provenance = _causal_provenance(bar_provenance, now)
    if provenance.get("event_at") and datetime.fromisoformat(provenance["event_at"]) > cutoff:
        raise ValueError("bar event is after frozen evaluation cutoff")
    # Whole-module fingerprints include helper changes, not just the top-level
    # signal function. Inputs/master dates stay in the decision evidence below.
    # [WORKFLOW-A4 2026-09-20] The identity MUST include the
    # chronological fill/exit/replay modules because they drive
    # full-policy economics. Without them, a delayed-fill or fee
    # change can leave the frozen identity unchanged.
    source_names = (
        # Original signal / advisory core.
        "fno_engine_mom.py", "partner_manual_advisory.py", "fno_chain.py",
        "fno_instruments.py", "options_math.py", "partner_qualification.py",
        "partner_thesis.py", "partner_decision_clock.py",
        # Chronological execution + replay (A4: previously omitted).
        "intraday_spread_chronological.py",
        "intraday_spread_replay.py",
        "intraday_spread_holdout.py",
        "intraday_spread_research.py",
        "intraday_spread_research_verify.py",
        # Exit / cost / quality (A4: previously omitted).
        "momentum_exits.py",
        "fno_costs.py",
        "exit_quality.py",
        "cost_audit.py",
        # Full-policy replay (A4: previously omitted).
        "partner_full_policy_replay.py",
    )
    source_hashes = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                     for name in source_names}
    frozen_config = {key: value for key, value in settings.model_dump().items()
                     if key.startswith(("FNO_", "PARTNER_MANUAL_ADVISORY_"))
                     and not any(word in key for word in ("TOKEN", "SECRET", "PASSWORD", "KEY"))}
    strategy = {"format": "partner_frozen_policy_v1", "evaluator": FULL_POLICY_EVALUATOR,
                "underlying": name, "structure_kind": structure_kind, "source_sha256": source_hashes,
                "configuration": frozen_config, "profile": asdict(profile) if profile is not None else None}
    strategy["manifest_sha256"] = _sha(strategy)
    # [WORKFLOW-A4 2026-09-20] Economic-model manifest: separated
    # from the policy manifest so a data-only change (a new bar
    # capture timestamp) does NOT invalidate the economic
    # fingerprint. The economic_model_manifest field is the
    # authoritative binding for fill/exit/replay/cost code; the
    # outer manifest_sha256 still binds everything for
    # end-to-end integrity.
    economic_model = {
        "format": "partner_economic_model_v1",
        "evaluator": FULL_POLICY_EVALUATOR,
        "underlying": name,
        "structure_kind": structure_kind,
        "source_sha256": source_hashes,
        "config": config,
        "config_sha256": _sha(config),
    }
    economic_model_sha256 = _sha(economic_model)
    deterministic = {
        "format": "partner_full_policy_manifest_v1", "evaluator": FULL_POLICY_EVALUATOR,
        "evaluator_source_sha256": hashlib.sha256(inspect.getsource(evaluate_fno_mom).encode()).hexdigest(),
        "underlying": name, "structure_kind": structure_kind, "regime": str(regime),
        "decision_at": now.isoformat(), "evaluation_cutoff_at": cutoff.isoformat(),
        "clock_policy": (decision_clock or {}).get("policy", "LEGACY_DECISION_EQUALS_CUTOFF_V1"),
        "decision_clock": dict(decision_clock) if decision_clock is not None else None,
        "config": config, "config_sha256": _sha(config),
        "bars_sha256": _sha(bar_rows), "bar_count": len(bar_rows), "bar_provenance": provenance,
        "contract_master_sha256": contract_master_sha256,
        "frozen_policy": strategy, "policy_sha256": strategy["manifest_sha256"],
        # A4: economic-model manifest lives inside the deterministic
        # manifest so its fingerprint is part of the end-to-end
        # binding. Downstream callers can match
        # ``manifest["economic_model_sha256"]`` to a stored value
        # without recomputing the policy fingerprint.
        "economic_model": economic_model,
        "economic_model_sha256": economic_model_sha256,
    }
    return {**deterministic, "manifest_sha256": _sha(deterministic)}


@dataclass(frozen=True)
class FullPolicyDecision:
    decision_id: str
    state: str
    reason: str
    signal: MomSignal
    candidate: AdvisoryCandidate | None
    validation_reasons: tuple[str, ...]
    manifest: dict[str, Any]
    can_qualify: bool = False


def evaluate_deployed_full_policy(*, underlying: str, bars: pd.DataFrame, regime: str,
                                  decision_at: datetime, bar_provenance: Mapping[str, Any],
                                  book: FnoInstruments | None = None,
                                  snapshot: ChainSnapshot | None = None,
                                  profile: PartnerAdvisoryProfile | None = None,
                                  contract_master_sha256: str | None = None,
                                  evaluation_cutoff_at: datetime | None = None,
                                  decision_clock: Mapping[str, Any] | None = None) -> FullPolicyDecision:
    """Reproduce deployed signal -> candidate -> profile/quote validation.

    A no-setup is a retained decision, not a missing row.  Historical bars
    retrieved after the fact remain labelled RETROSPECTIVE and cannot qualify
    a policy even when their deterministic decision matches production code.
    """
    now = _clock(decision_at, "decision_at").astimezone(ZoneInfo("Asia/Kolkata"))
    cutoff = _clock(evaluation_cutoff_at or now, "evaluation_cutoff_at").astimezone(ZoneInfo("Asia/Kolkata"))
    # The deployed evaluator explicitly consumes naive IST bar starts.
    # Convert aware input without changing the represented instants.
    if bars is not None and isinstance(bars.index, pd.DatetimeIndex) and bars.index.tz is not None:
        bars = bars.copy()
        bars.index = bars.index.tz_convert("Asia/Kolkata").tz_localize(None)
    manifest = policy_manifest(underlying=underlying, structure_kind="DIRECTIONAL_DEBIT_SPREAD", bars=bars,
                               regime=regime, decision_at=now, bar_provenance=bar_provenance,
                               contract_master_sha256=contract_master_sha256, profile=profile,
                               evaluation_cutoff_at=cutoff, decision_clock=decision_clock)
    if snapshot is not None:
        # Tuple-keyed quote maps are normalized before canonical JSON hashing.
        quote_rows = [asdict(quote) for _, quote in sorted(snapshot.quotes.items())]
        manifest["chain_evidence_sha256"] = _sha({"taken_at": snapshot.taken_at,
            "expiry": snapshot.expiry, "forward": snapshot.forward, "parity_forward": snapshot.parity_forward,
            "lot_size": snapshot.lot_size, "quotes": quote_rows,
            "future_quote": asdict(snapshot.fut_quote) if snapshot.fut_quote is not None else None})
        manifest["manifest_sha256"] = _sha({key: value for key, value in manifest.items() if key != "manifest_sha256"})
    signal = evaluate_fno_mom(bars, regime, cutoff)
    base = {"manifest": manifest["manifest_sha256"], "signal": _signal_payload(signal)}
    if signal.direction is None:
        return FullPolicyDecision(_sha(base), "NO_SETUP", signal.reject_reason or "no_direction", signal,
                                  None, (), manifest, False)
    if book is None or snapshot is None:
        return FullPolicyDecision(_sha(base), "REJECTED", "candidate_input_missing", signal,
                                  None, ("candidate_input_missing",), manifest, False)
    trigger = signal.or_high + settings.FNO_OR_BUFFER_ATR * signal.atr if signal.direction.value == "LONG" else signal.or_low - settings.FNO_OR_BUFFER_ATR * signal.atr
    candidate = build_directional_debit_spread(
        snapshot, book, signal.direction, now, evidence=StrategyEvidence.RESEARCH_ONLY,
        quote_ttl_seconds=settings.PARTNER_MANUAL_ADVISORY_QUOTE_TTL_SEC,
        thesis_id=f"{underlying.upper()}:{signal.direction.value}:{signal.bar_ts}", trigger_level=trigger,
        invalidation_level=signal.stop_underlying, target_level=signal.target_underlying,
    )
    if candidate is None:
        return FullPolicyDecision(_sha(base), "REJECTED", "candidate_construction_failed", signal,
                                  None, ("candidate_construction_failed",), manifest, False)
    validation = validate_candidate(
        candidate, now, max_quote_age_seconds=settings.PARTNER_MANUAL_ADVISORY_MAX_QUOTE_AGE_SEC,
        max_spread_pct=settings.PARTNER_MANUAL_ADVISORY_MAX_SPREAD_PCT,
        min_oi=settings.PARTNER_MANUAL_ADVISORY_MIN_OI,
        min_volume=settings.PARTNER_MANUAL_ADVISORY_MIN_VOLUME,
        min_depth_units=settings.PARTNER_MANUAL_ADVISORY_MIN_DEPTH_UNITS,
    )
    reasons = list(validation.reasons)
    if profile is not None:
        reasons.extend(validate_profile(profile, candidate, now))
        if not profile.permits(AdvisoryScope.MARKET_SETUP, candidate.underlying):
            reasons.append("profile_scope_not_permitted")
    else:
        reasons.append("profile_input_missing")
    reasons = tuple(sorted(set(reasons)))
    state = "ACCEPTED" if not reasons else "REJECTED"
    base["candidate"] = asdict(candidate)
    base["profile"] = asdict(profile) if profile is not None else None
    return FullPolicyDecision(_sha(base), state, "accepted" if state == "ACCEPTED" else reasons[0], signal,
                              candidate, reasons, manifest, False)


def write_full_policy_decision(path: str | Path, decision: FullPolicyDecision) -> dict[str, Any]:
    """Atomically persist a research decision; never a qualification record."""
    candidate = decision.candidate
    payload = {
        "format": "partner_full_policy_decision_v1", "decision_id": decision.decision_id,
        "state": decision.state, "reason": decision.reason, "signal": _signal_payload(decision.signal),
        "validation_reasons": list(decision.validation_reasons), "manifest": decision.manifest,
        "candidate": None if candidate is None else {
            "thesis_id": candidate.thesis_id, "direction": candidate.direction,
            "net_debit_rs": candidate.net_debit_rs, "max_loss_rs": candidate.max_loss_rs,
            "max_profit_rs": candidate.max_profit_rs, "estimated_round_trip_cost_rs": candidate.estimated_round_trip_cost_rs,
            "trigger_level": candidate.trigger_level, "invalidation_level": candidate.invalidation_level,
            "target_level": candidate.target_level, "management_deadline": candidate.management_deadline.isoformat()
            if candidate.management_deadline else None,
            "selected_legs": [{"side": leg.side, "exchange": candidate.segment, "token": leg.instrument_token,
                                "symbol": leg.tradingsymbol, "expiry": leg.expiry, "strike": leg.strike,
                                "option_type": leg.option_type, "lot_size": leg.lot_size}
                              for leg in candidate.legs],
        },
        "can_qualify": False, "can_place_orders": False,
        "limitations": ["A deterministic research decision is not a strategy qualification or advice delivery authority."],
    }
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False).encode()
    fd, temporary = tempfile.mkstemp(prefix=".decision-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            # Atomic create-if-absent, never replace an existing experiment.
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != encoded:
                raise ValueError("decision output already contains different immutable evidence")
    finally:
        os.unlink(temporary)
    return payload
