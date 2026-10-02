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
from momentum_exit_study import INPUT_SCHEMA
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
        entries, quotes = [], []
        for row in rows:
            admission_hash = _packet_hash(row["source_packet_json"])
            if admission_hash is None or admission_hash != row["source_packet_sha256"]:
                return _unavailable(f"source_packet_identity_mismatch:{row['admission_key']}")
            try:
                entry = json.loads(row["entry_economics_json"])
            except (TypeError, json.JSONDecodeError):
                return _unavailable(f"entry_economics_unavailable:{row['admission_key']}")
            if not isinstance(entry, dict) or entry.get("schema") != "momentum_paper_entry_economics_v1" or entry.get("ticker") != row["ticker"]:
                return _unavailable(f"entry_economics_mismatch:{row['admission_key']}")
            if entry.get("shares") != row["original_shares"]:
                return _unavailable(f"original_quantity_mismatch:{row['admission_key']}")
            entry_at, deadline = _timestamp(row["entry_at"]), _timestamp(row["study_deadline_at"])
            if entry_at is None or deadline is None:
                return _unavailable(f"path_clock_unavailable:{row['admission_key']}")
            observed = con.execute(
                "SELECT ticker,provider_observed_at,receipt_at,ltp,deadline_observation,source_packet,source_packet_sha256 "
                "FROM momentum_paper_path_observations WHERE admission_key=? ORDER BY provider_observed_at,id",
                (row["admission_key"],),
            ).fetchall()
            if not observed:
                return _unavailable(f"no_quotes:{row['admission_key']}")
            previous = None
            saw_deadline = False
            for quote in observed:
                observed_at, receipt_at = _timestamp(quote["provider_observed_at"]), _timestamp(quote["receipt_at"])
                if (quote["ticker"] != row["ticker"] or observed_at is None or receipt_at is None
                        or observed_at < entry_at or observed_at > deadline or receipt_at < observed_at):
                    return _unavailable(f"invalid_quote_clock_or_ticker:{row['admission_key']}")
                if (receipt_at - observed_at).total_seconds() > max_gap:
                    return _unavailable(f"quote_receipt_delay_exceeds_declared_maximum:{row['admission_key']}")
                if not isinstance(quote["ltp"], (int, float)) or not math.isfinite(quote["ltp"]) or quote["ltp"] <= 0:
                    return _unavailable(f"invalid_quote_price:{row['admission_key']}")
                if _packet_hash(quote["source_packet"]) != quote["source_packet_sha256"]:
                    return _unavailable(f"quote_packet_identity_mismatch:{row['admission_key']}")
                try:
                    verify_path_quote_envelope(bytes(quote["source_packet"]), ticker=row["ticker"],
                                               ltp=float(quote["ltp"]), provider_observed_at=observed_at)
                except PathEnvelopeError:
                    return _unavailable(f"quote_packet_column_mismatch:{row['admission_key']}")
                if previous is not None and (observed_at <= previous or (observed_at - previous).total_seconds() > max_gap):
                    return _unavailable(f"quote_gap_or_order_invalid:{row['admission_key']}")
                if previous is None and (observed_at - entry_at).total_seconds() > max_gap:
                    return _unavailable(f"initial_quote_gap_exceeds_declared_maximum:{row['admission_key']}")
                if observed_at == deadline:
                    saw_deadline = True
                previous = observed_at
                quotes.append({"entry_id": row["admission_key"], "observed_at": observed_at.isoformat(), "ltp": float(quote["ltp"])})
            if not saw_deadline:
                return _unavailable(f"exact_1515_ist_quote_missing:{row['admission_key']}")
            entries.append({
                "entry_id": row["admission_key"], "admission_key": row["admission_key"],
                "source_ref": admission_hash, "ticker": entry["ticker"], "entry_at": entry["entry_at"],
                "entry_price": entry["entry_price"], "stop_loss_initial": entry["stop_loss_initial"],
                "target_1": entry["target_1"], "shares": entry["shares"],
                "atr_14_at_entry": entry.get("atr_14_at_entry"), "vwap_at_entry": entry.get("vwap_at_entry"),
                "regime_at_entry": entry.get("regime_at_entry"),
            })
        return {"schema": "momentum_paper_path_adapter_v1", "status": "COMPLETE", "reason": None,
                "packet": {"schema": INPUT_SCHEMA, "study_id": study_id, "max_quote_gap_seconds": max_gap,
                           "entries": entries, "quotes": quotes}}
    except sqlite3.Error:
        return _unavailable("database_query_unavailable")
    finally:
        con.close()
