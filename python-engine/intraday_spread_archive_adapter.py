"""Read immutable quote archives into explicit two-leg chronological evidence."""
from __future__ import annotations

import gzip
import hashlib
import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any, Iterable, Mapping

from intraday_spread_chronological import SpreadObservation
from intraday_spread_replay import LegQuote, ReplayInputError
from intraday_spread_signal_artifact import artifact_scores_by_receipt, load_signal_artifact


@dataclass(frozen=True)
class SpreadContractIdentity:
    token: int
    symbol: str
    underlying: str
    exchange: str
    option_type: str
    strike: float
    expiry: str
    lot_size: int


@dataclass(frozen=True)
class ArchiveObservationBuild:
    observations: tuple[SpreadObservation, ...]
    partial_batches: tuple[dict[str, Any], ...]
    ignored_events: int
    signal_provenance_sha256: str | None


def _stamp(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReplayInputError(f"{field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReplayInputError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def read_archived_quote_events(archive_root: str | Path, *, days: Iterable[str]) -> list[dict[str, Any]]:
    """Read finalized and open quote journals without changing archive state."""
    root = Path(archive_root) / "quotes"
    events: list[dict[str, Any]] = []
    for day in sorted(set(days)):
        base = root / day
        candidates = [base / "quotes.jsonl.open", *sorted(base.glob("quotes-*.jsonl.gz"))]
        for path in candidates:
            if not path.exists():
                continue
            opener = gzip.open if path.suffix == ".gz" else open
            try:
                with opener(path, "rt", encoding="utf-8") as handle:
                    for line in handle:
                        item = json.loads(line)
                        if isinstance(item, dict):
                            events.append(item)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ReplayInputError(f"quote archive segment is unreadable: {path.name}") from exc
    return events


def _leg(event: Mapping[str, Any], identity: SpreadContractIdentity, master_sha256: str) -> LegQuote | None:
    contract = event.get("contract")
    if not isinstance(contract, Mapping):
        return None
    try:
        matches = (str(contract.get("instrument_token")) == str(identity.token)
                   and str(contract.get("tradingsymbol")) == identity.symbol
                   and str(contract.get("underlying")).upper() == identity.underlying
                   and str(contract.get("exchange")).upper() == identity.exchange
                   and str(contract.get("instrument_type")).upper() == identity.option_type
                   and str(contract.get("expiry"))[:10] == identity.expiry
                   and float(contract.get("strike")) == identity.strike
                   and int(contract.get("lot_size")) == identity.lot_size)
    except (TypeError, ValueError):
        return None
    if not matches:
        return None
    raw = event.get("raw_packet")
    if not isinstance(raw, Mapping):
        return None
    digest = hashlib.sha256(json.dumps(dict(raw), sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
    if digest != event.get("raw_sha256") or str(raw.get("instrument_token")) != str(identity.token):
        return None
    received = _stamp(event.get("received_at_utc"), "received_at_utc")
    # Missing provider time remains unavailable for execution-quality replay.
    provider_time = event.get("provider_timestamp_utc") or event.get("exchange_timestamp_utc")
    if provider_time is None:
        return None  # Receipt alone cannot establish execution-quality freshness.
    observed = _stamp(provider_time, "observed_at")
    raw_time = raw.get("timestamp") if str(event.get("mode", "KITE_REST")).startswith("KITE_REST") else raw.get("exchange_timestamp")
    if raw_time is None:
        raw_time = raw.get("exchange_timestamp")
    try:
        parsed_raw_time = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
        if parsed_raw_time.tzinfo is None:
            parsed_raw_time = parsed_raw_time.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        if parsed_raw_time.astimezone(timezone.utc) != observed or observed > received:
            return None
    except (TypeError, ValueError):
        return None
    bids, asks = event.get("buy_depth"), event.get("sell_depth")
    if not isinstance(bids, list) or not isinstance(asks, list) or not bids or not asks:
        return None
    try:
        raw_depth = raw["depth"]
        for normalized, source in ((bids[0], raw_depth["buy"][0]), (asks[0], raw_depth["sell"][0])):
            if float(normalized["price"]) != float(source["price"]) or int(normalized["quantity"]) != int(source["quantity"]):
                return None
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    bid, ask = bids[0], asks[0]
    if not isinstance(bid, Mapping) or not isinstance(ask, Mapping):
        return None
    try:
        return LegQuote(identity.symbol, "BUY", identity.exchange, identity.lot_size,
                        float(bid["price"]), float(ask["price"]), int(bid["quantity"]), int(ask["quantity"]),
                        observed, received, token=identity.token, option_type=identity.option_type, strike=identity.strike,
                        expiry=identity.expiry, quantity=identity.lot_size, master_sha256=master_sha256)
    except (KeyError, TypeError, ValueError) as exc:
        raise ReplayInputError("quote depth is malformed") from exc


def _master_proves_contract(archive_root: str | Path, identity: SpreadContractIdentity, master_sha256: str) -> bool:
    for manifest_path in Path(archive_root).glob("contract-masters/**/manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if str(manifest.get("raw_sha256", "")).lower() != master_sha256.lower():
                continue
            raw = (manifest_path.parent / "raw.csv").read_bytes()
            canonical = (manifest_path.parent / "contracts.jsonl").read_bytes()
            if (hashlib.sha256(raw).hexdigest() != master_sha256.lower()
                    or hashlib.sha256(canonical).hexdigest() != manifest.get("canonical_sha256")):
                continue
            raw_matches = [row for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
                           if str(row.get("instrument_token")) == str(identity.token)]
            if len(raw_matches) != 1:
                continue
            source = raw_matches[0]
            if not (source.get("tradingsymbol") == identity.symbol
                    and str(source.get("name", "")).upper() == identity.underlying
                    and str(source.get("exchange") or manifest.get("segment", "")).upper() == identity.exchange
                    and source.get("instrument_type") == identity.option_type
                    and str(source.get("expiry", ""))[:10] == identity.expiry
                    and float(source.get("strike", "nan")) == identity.strike
                    and int(source.get("lot_size", "0")) == identity.lot_size):
                continue
            for line in canonical.decode("utf-8").splitlines():
                contract = json.loads(line)
                if (str(contract.get("instrument_token")) == str(identity.token)
                        and str(contract.get("tradingsymbol")) == identity.symbol
                        and str(contract.get("underlying")).upper() == identity.underlying
                        and str(contract.get("exchange")).upper() == identity.exchange
                        and str(contract.get("instrument_type")).upper() == identity.option_type
                        and str(contract.get("expiry"))[:10] == identity.expiry
                        and float(contract.get("strike")) == identity.strike
                        and int(contract.get("lot_size")) == identity.lot_size):
                    return True
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return False


def build_spread_observations(*, events: Iterable[Mapping[str, Any]], long_contract: SpreadContractIdentity,
                               short_contract: SpreadContractIdentity, master_sha256: str,
                               archive_root: str | Path,
                               signal_artifact_path: str | Path | None = None,
                               policy_id: str | None = None,
                               session_date: str | None = None) -> ArchiveObservationBuild:
    """Pair same-receipt records; report partial packets rather than omitting them.

    Scores are optional because an archive of quote facts is not automatically a
    strategy signal.  A nonzero score can only originate in an immutable,
    verified evaluator artifact; callers cannot supply a score dictionary.
    """
    if len(master_sha256) != 64 or len(long_contract.underlying) == 0 or long_contract.underlying != short_contract.underlying:
        raise ReplayInputError("two same-underlying contracts and a master digest are required")
    if not (_master_proves_contract(archive_root, long_contract, master_sha256)
            and _master_proves_contract(archive_root, short_contract, master_sha256)):
        raise ReplayInputError("archived master does not prove both spread contracts")
    if (signal_artifact_path is None) != (policy_id is None or session_date is None):
        raise ReplayInputError("signal artifact path, policy_id and session_date must be supplied together")
    scores: dict[str, float] = {}
    signal_provenance_sha256: str | None = None
    if signal_artifact_path is not None:
        artifact = load_signal_artifact(signal_artifact_path, underlying=long_contract.underlying,
                                        policy_id=policy_id, session_date=session_date, source_root=archive_root)
        scores = artifact_scores_by_receipt(artifact)
        signal_provenance_sha256 = artifact["artifact_sha256"]
    batches: dict[str, list[Mapping[str, Any]]] = {}
    ignored = 0
    for event in events:
        try:
            key = _stamp(event.get("received_at_utc"), "received_at_utc").isoformat()
        except (AttributeError, ReplayInputError):
            ignored += 1; continue
        batches.setdefault(key, []).append(event)
    observations: list[SpreadObservation] = []
    partial: list[dict[str, Any]] = []
    for key in sorted(batches):
        long_event = next((item for item in batches[key] if _leg(item, long_contract, master_sha256) is not None), None)
        short_event = next((item for item in batches[key] if _leg(item, short_contract, master_sha256) is not None), None)
        if long_event is None or short_event is None:
            partial.append({"received_at": key, "state": "PARTIAL_LEG_OBSERVATION",
                            "missing": [name for name, item in (("long", long_event), ("short", short_event)) if item is None]})
            continue
        received = _stamp(key, "received_at")
        long = _leg(long_event, long_contract, master_sha256)
        short = _leg(short_event, short_contract, master_sha256)
        assert long is not None and short is not None
        # Side is a property of the declared spread, not the incoming packet.
        long = LegQuote(**{**long.__dict__, "side": "BUY"})
        short = LegQuote(**{**short.__dict__, "side": "SELL"})
        score = float(scores.get(key, 0.0))
        observations.append(SpreadObservation(min(long.observed_at, short.observed_at), received, score, (long, short)))
    return ArchiveObservationBuild(tuple(observations), tuple(partial), ignored, signal_provenance_sha256)
