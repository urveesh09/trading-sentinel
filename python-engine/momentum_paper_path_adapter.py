"""Read-only adapter from passive momentum-paper quote receipts to a study packet.

It has no scheduler and no market-data client.  A caller may export only a
fully verifiable, exact-admission path; otherwise the exact missing evidence is
returned and no synthetic study input is produced.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any

from config import settings
from momentum_exit_study import DEADLINE_FIRST_WITHIN_GAP, INPUT_SCHEMA
from momentum_path_envelope import PathEnvelopeError, verify_path_quote_envelope


SOURCE = "MOMENTUM_PAPER"


def _unavailable(reason: str) -> dict[str, Any]:
    return {"schema": "momentum_paper_path_adapter_v1", "status": "INSUFFICIENT_EVIDENCE",
            "reason": reason, "packet": None}


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _packet_hash(raw: object) -> str | None:
    if isinstance(raw, str):
        try:
            json.loads(raw)
        except json.JSONDecodeError:
            return None
        raw = raw.encode("utf-8")
    if not isinstance(raw, bytes) or not raw:
        return None
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


# Opened positions carry their admitted shares; capital-skipped candidates
# (S7a) carry the shares the fixed-pool rule would have sized with free capital.
_ECONOMICS_SHARE_FIELD = {
    "momentum_paper_entry_economics_v1": "shares",
    "momentum_paper_candidate_economics_v1": "unconstrained_benchmark_shares",
}


def build_allocation_candidates(db_path: str) -> dict[str, Any]:
    """Opened and capital-skipped candidates with complete verified paths (S7a).

    Read-only.  The exit-study packet above still uses opened admissions only.
    """
    from momentum_allocation_research import Candidate
    from momentum_exit_study import Quote, _entry_from_json
    empty = {"candidates": [], "unavailable_candidates": [], "deadline_quote_policy": DEADLINE_FIRST_WITHIN_GAP}
    path = Path(db_path)
    if not path.is_file():
        return {**empty, "unavailable_candidates": [{"reason": "database_unavailable_or_missing"}]}
    con = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"momentum_paper_admission_outcomes", "momentum_paper_path_subscriptions",
                "momentum_paper_path_observations"}.issubset(tables):
            return {**empty, "unavailable_candidates": [{"reason": "passive_path_schema_unavailable"}]}
        columns = {row[1] for row in con.execute("PRAGMA table_info(momentum_paper_path_subscriptions)")}
        kind = "s.subscription_kind" if "subscription_kind" in columns else "'OPENED'"
        rows = con.execute(
            "SELECT a.id,a.admission_key,a.ticker,a.outcome,a.recorded_at,a.entry_economics_json,"
            "a.admission_economics_json,a.source_packet_json,a.source_packet_sha256,s.entry_at,"
            f"s.study_deadline_at,s.original_shares,{kind} AS subscription_kind "
            "FROM momentum_paper_admission_outcomes a JOIN momentum_paper_path_subscriptions s "
            "ON s.admission_key=a.admission_key WHERE a.outcome IN ('opened','zero_shares') "
            "ORDER BY a.recorded_at,a.id"
        ).fetchall()
        max_gap = max(1, min(300, int(settings.MOMENTUM_PAPER_PATH_MAX_GAP_SECONDS)))
        candidates, unavailable, arrival = [], [], {}
        for row in rows:
            built = _entry_path(con, row, max_gap)
            if isinstance(built, str):
                unavailable.append({"admission_key": row["admission_key"], "reason": built})
                continue
            try:
                risk_pct = float(json.loads(row["admission_economics_json"])["risk_pct"])
                if not math.isfinite(risk_pct) or risk_pct <= 0:
                    raise ValueError
            except (TypeError, ValueError, KeyError, json.JSONDecodeError):
                unavailable.append({"admission_key": row["admission_key"],
                                    "reason": f"risk_pct_unavailable:{row['admission_key']}"})
                continue
            entry_row, quotes = built
            batch_at = _timestamp(row["recorded_at"])
            economics = json.loads(row["admission_economics_json"])
            recorded_batch = economics.get("admission_batch_id")
            recorded_index = economics.get("arrival_index")
            if isinstance(recorded_batch, str) and recorded_batch and isinstance(recorded_index, int):
                batch_id, arrival_index = recorded_batch, recorded_index
            else:
                # Legacy admission: group by its exact recorded clock (no rounding).
                arrival[batch_at] = arrival.get(batch_at, -1) + 1
                batch_id, arrival_index = "", arrival[batch_at]
            candidates.append(Candidate(
                admission_key=row["admission_key"], kind=str(row["subscription_kind"]),
                batch_at=batch_at, arrival_index=arrival_index, batch_id=batch_id,
                entry=_entry_from_json(entry_row), risk_pct=risk_pct,
                quotes=tuple(Quote(observed_at=datetime.fromisoformat(q["observed_at"]).astimezone(
                    _entry_from_json(entry_row).entry_at.tzinfo), ltp=float(q["ltp"])) for q in quotes),
            ))
        return {"candidates": candidates, "unavailable_candidates": unavailable,
                "deadline_quote_policy": DEADLINE_FIRST_WITHIN_GAP}
    finally:
        con.close()


def _entry_path(con, row, max_gap: int):
    """Return (entry, quotes) for one exact lifecycle, or the reason it is unavailable.

    The closing quote is the first observation at or after the 15:15 IST study
    deadline within ``max_gap`` seconds, with its real provider time; later
    observations are ignored.  No timestamp is rewritten.
    """
    key = row["admission_key"]
    admission_hash = _packet_hash(row["source_packet_json"])
    if admission_hash is None or admission_hash != row["source_packet_sha256"]:
        return f"source_packet_identity_mismatch:{key}"
    try:
        entry = json.loads(row["entry_economics_json"])
    except (TypeError, json.JSONDecodeError):
        return f"entry_economics_unavailable:{key}"
    share_field = _ECONOMICS_SHARE_FIELD.get(entry.get("schema")) if isinstance(entry, dict) else None
    if share_field is None or entry.get("ticker") != row["ticker"]:
        return f"entry_economics_mismatch:{key}"
    if entry.get(share_field) != row["original_shares"]:
        return f"original_quantity_mismatch:{key}"
    entry_at, deadline = _timestamp(row["entry_at"]), _timestamp(row["study_deadline_at"])
    if entry_at is None or deadline is None:
        return f"path_clock_unavailable:{key}"
    observed = con.execute(
        "SELECT ticker,provider_observed_at,receipt_at,ltp,deadline_observation,source_packet,source_packet_sha256 "
        "FROM momentum_paper_path_observations WHERE admission_key=? ORDER BY provider_observed_at,id",
        (key,),
    ).fetchall()
    if not observed:
        return f"no_quotes:{key}"
    quotes = []
    previous = None
    saw_deadline = False
    for quote in observed:
        observed_at, receipt_at = _timestamp(quote["provider_observed_at"]), _timestamp(quote["receipt_at"])
        if (quote["ticker"] != row["ticker"] or observed_at is None or receipt_at is None
                or observed_at < entry_at or receipt_at < observed_at):
            return f"invalid_quote_clock_or_ticker:{key}"
        if observed_at > deadline and (observed_at - deadline).total_seconds() > max_gap:
            break  # first post-deadline observation is outside the closing window
        if (receipt_at - observed_at).total_seconds() > max_gap:
            return f"quote_receipt_delay_exceeds_declared_maximum:{key}"
        if not isinstance(quote["ltp"], (int, float)) or not math.isfinite(quote["ltp"]) or quote["ltp"] <= 0:
            return f"invalid_quote_price:{key}"
        if _packet_hash(quote["source_packet"]) != quote["source_packet_sha256"]:
            return f"quote_packet_identity_mismatch:{key}"
        try:
            verify_path_quote_envelope(bytes(quote["source_packet"]), ticker=row["ticker"],
                                       ltp=float(quote["ltp"]), provider_observed_at=observed_at)
        except PathEnvelopeError:
            return f"quote_packet_column_mismatch:{key}"
        if previous is not None and (observed_at <= previous or (observed_at - previous).total_seconds() > max_gap):
            return f"quote_gap_or_order_invalid:{key}"
        if previous is None and (observed_at - entry_at).total_seconds() > max_gap:
            return f"initial_quote_gap_exceeds_declared_maximum:{key}"
        previous = observed_at
        quotes.append({"entry_id": key, "observed_at": observed_at.isoformat(), "ltp": float(quote["ltp"])})
        if observed_at >= deadline:
            saw_deadline = True
            break
    if not saw_deadline:
        return f"no_quote_within_gap_at_or_after_1515_ist:{key}"
    return ({
        "entry_id": key, "admission_key": key,
        "source_ref": admission_hash, "ticker": entry["ticker"], "entry_at": entry["entry_at"],
        "entry_price": entry["entry_price"], "stop_loss_initial": entry["stop_loss_initial"],
        "target_1": entry["target_1"], "shares": entry[share_field],
        "atr_14_at_entry": entry.get("atr_14_at_entry"), "vwap_at_entry": entry.get("vwap_at_entry"),
        "regime_at_entry": entry.get("regime_at_entry"),
    }, quotes)


def build_momentum_paper_exit_study_packet(db_path: str, *, study_id: str = "momentum-paper-passive-paths") -> dict[str, Any]:
    """Build an in-memory S1 input packet only when every receipt is exact.

    Packet identities are recomputed from database bytes.  This specifically
    rejects a row whose claimed hash was forged or whose stored packet was later
    changed, rather than treating the ``sha256:`` prefix as verification.
    """
    path = Path(db_path)
    if not path.is_file():
        return _unavailable("database_unavailable_or_missing")
    try:
        con = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
    except sqlite3.Error:
        return _unavailable("database_unavailable_or_missing")
    try:
        required = {
            "momentum_paper_admission_outcomes", "momentum_paper_path_subscriptions",
            "momentum_paper_path_observations",
        }
        names = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not required.issubset(names):
            return _unavailable("passive_path_schema_unavailable")
        rows = con.execute(
            "SELECT a.admission_key,a.ticker,a.entry_economics_json,a.source_packet_json,"
            "a.source_packet_sha256,s.entry_at,s.study_deadline_at,s.original_shares "
            "FROM momentum_paper_admission_outcomes a JOIN momentum_paper_path_subscriptions s "
            "ON s.admission_key=a.admission_key WHERE a.outcome='opened' ORDER BY a.recorded_at,a.admission_key"
        ).fetchall()
        if not rows:
            return _unavailable("no_passive_paper_paths")
        max_gap = max(1, min(300, int(settings.MOMENTUM_PAPER_PATH_MAX_GAP_SECONDS)))
        entries, quotes, unavailable = [], [], []
        for row in rows:
            built = _entry_path(con, row, max_gap)
            if isinstance(built, str):
                # One incomplete lifecycle is reported, never allowed to block
                # every other exact path (S4 wiring correction).
                unavailable.append({"admission_key": row["admission_key"], "reason": built})
                continue
            entry_row, entry_quotes = built
            entries.append(entry_row)
            quotes.extend(entry_quotes)
        if not entries:
            first = unavailable[0]["reason"]
            return {**_unavailable(first), "unavailable_entries": unavailable}
        return {"schema": "momentum_paper_path_adapter_v1", "status": "COMPLETE", "reason": None,
                "unavailable_entries": unavailable,
                "packet": {"schema": INPUT_SCHEMA, "study_id": study_id, "max_quote_gap_seconds": max_gap,
                           "deadline_quote_policy": DEADLINE_FIRST_WITHIN_GAP,
                           "entries": entries, "quotes": quotes}}
    except sqlite3.Error:
        return _unavailable("database_query_unavailable")
    finally:
        con.close()
