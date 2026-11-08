"""Reconcile the finished Nov 6 F&O paper ledger against its read-only export."""

import argparse
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3


DAY = "2026-11-06"
IST = timezone(timedelta(hours=5, minutes=30))
SOURCES = ("fno_book.py", "fno_n11.py", "fno_orchestrator.py", "fno_exit_rules.py", "fno_costs.py")
CANDIDATE = "2758869"


def day_rows(uri: str) -> dict:
    with closing(sqlite3.connect(uri, uri=True, timeout=3)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        def rows(query, args=()):
            return [dict(row) for row in db.execute(query, args)]

        def positions(table, fields, opened, closed):
            return rows(
                f"SELECT {fields} FROM {table} WHERE source='FNO_PAPER' AND ("
                f"substr({opened},1,10)=? OR substr({closed},1,10)=? OR "
                f"(substr({opened},1,10)<? AND ({closed} IS NULL OR substr({closed},1,10)>=?))) "
                "ORDER BY id", (DAY,) * 4,
            )

        single = positions(
            "fno_positions", "id,underlying,tradingsymbol,strategy,entry_time,exit_time,lots,qty,pnl,status",
            "entry_time", "exit_time",
        )
        spreads = positions(
            "fno_dr_positions", "id,kind,opened_at,closed_at,lots,lot_size,pnl,costs,gross_pnl,model_pnl,cash_pnl,"
            "max_loss_rs,entry_cost_rs,exit_reason,status,settlement_state,pricing_policy,legs_json",
            "opened_at", "closed_at",
        )
        signals = rows(
            "SELECT underlying,leg,accepted,reject_reason,COUNT(*) AS rows,COUNT(DISTINCT bar_ts) AS bars,"
            "MIN(evaluated_at) AS first,MAX(evaluated_at) AS last FROM fno_signals "
            "WHERE substr(evaluated_at,1,10)=? AND leg IN ('FNO_PAPER','ENGINE') "
            "GROUP BY underlying,leg,accepted,reject_reason ORDER BY underlying,leg,accepted,reject_reason", (DAY,),
        )
        for spread in spreads:
            spread["legs"] = json.loads(spread.pop("legs_json"))
        ledger = None
        columns = {row["name"] for row in rows("PRAGMA table_info(bankroll_ledger)")}
        if columns:
            filter_source = "AND source='FNO_PAPER'" if "source" in columns else ""
            ledger = {str(spread["id"]): rows(
                "SELECT origin_ref,pnl FROM bankroll_ledger WHERE origin_ref=? " + filter_source,
                (f"fno_dr_structure:{spread['id']}",),
            ) for spread in spreads}
    return {"directional": single, "spreads": spreads, "signals": signals, "spread_ledger": ledger}


def production_reserves(spreads: list[dict]) -> dict:
    with closing(sqlite3.connect("file:/data/cache.db?mode=ro", uri=True, timeout=3)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        return {str(spread["id"]): [dict(row) for row in db.execute(
            "SELECT book,position_ref,worst_case_cash_rs,state FROM fno_risk_reservations "
            "WHERE source='FNO_PAPER' AND position_ref=?",
            (f"fno_dr_position:{spread['id']}",),
        )] for spread in spreads}


def runtime() -> dict:
    from config import settings

    report = day_rows("file:/data/cache.db?mode=ro")
    report["spread_reserves"] = production_reserves(report["spreads"])
    report["read_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["release_sha"] = os.getenv("SENTINEL_RELEASE_SHA")
    report["sources"] = {name: hashlib.sha256(Path(name).read_text(encoding="utf-8").encode()).hexdigest()
                         for name in SOURCES}
    keys = ("FNO_BOOK", "FNO_N11_TOLERANCE_ENABLED", "FNO_PAPER_BANKROLL",
            "FNO_TRADING_UNDERLYINGS", "FNO_EXIT_PATH_RECORDING", "FNO_DR_EXIT_PATH_RECORDING")
    report["settings"] = {key: getattr(settings, key, None) for key in keys}
    return report


def verify_export(export: Path) -> tuple[dict, dict]:
    manifest = json.loads((export / "manifest.json").read_bytes())
    extracted_at = datetime.fromisoformat(manifest["exported_at_utc"]).astimezone(IST)
    if (manifest["source"] != "SENTINEL_DATA_VOLUME_READ_ONLY" or
            extracted_at.date() != date.fromisoformat(DAY) or
            extracted_at.hour * 60 + extracted_at.minute < 15 * 60 + 50):
        raise ValueError("expected a finished-session Production export")
    sources = manifest["files_sha256"]
    paths = ["fno-replay.sqlite", *(name for name in sources if
             name.startswith(f"quotes/{DAY}/") or name in
             (f"fno_exit_paths/{DAY}.jsonl", f"fno_dr_exit_paths/{DAY}.jsonl"))]
    checked = {}
    for name in paths:
        with (export / name).open("rb") as handle:
            checked[name] = hashlib.file_digest(handle, "sha256").hexdigest()
        if checked[name] != sources[name]:
            raise ValueError(f"changed export file: {name}")
    return manifest, checked


def reconcile(export: Path, observed: dict) -> dict:
    manifest, hashes = verify_export(export)
    rows = day_rows((export / "fno-replay.sqlite").resolve().as_uri() + "?mode=ro")
    if any(value != observed[key] for key, value in rows.items() if key != "spread_ledger"):
        raise ValueError("export and Production evidence differ")
    if rows["spread_ledger"] is not None and rows["spread_ledger"] != observed["spread_ledger"]:
        raise ValueError("export and Production evidence differ")
    if rows["directional"] or any(row["accepted"] for row in rows["signals"]):
        raise ValueError("directional activity requires the native held-path comparison")
    for spread in rows["spreads"]:
        ledger, = observed["spread_ledger"][str(spread["id"])]
        reserve, = observed["spread_reserves"][str(spread["id"])]
        if (reserve["book"] != "DEFINED_RISK" or reserve["state"] != "CONSUMED" or
                round(spread["max_loss_rs"] + spread["entry_cost_rs"], 2) != reserve["worst_case_cash_rs"]):
            raise ValueError(f"spread reserve differs from position: {spread['id']}")
        if (spread["status"] != "CLOSED" or spread["settlement_state"] != "SETTLED"
                or spread["pnl"] != spread["cash_pnl"] or spread["pnl"] != ledger["pnl"]
                or round(spread["gross_pnl"] - spread["costs"], 2) != spread["cash_pnl"]):
            raise ValueError(f"spread cash differs from ledger: {spread['id']}")
    return {
        "session": DAY, "export": export.name, "exported_at_utc": manifest["exported_at_utc"],
        "unsealed_quote_journal": DAY in manifest["unsealed_days"], "export_files_sha256": hashes,
        "production": {key: observed[key] for key in ("release_sha", "read_at_utc", "sources", "settings")},
        "directional_trades": 0, "directional_observed_net_rs": 0.0,
        "spread_observed_net_rs": round(sum(row["cash_pnl"] for row in rows["spreads"]), 2),
        "spreads": rows["spreads"], "directional_signal_logs": rows["signals"],
        "spread_ledger_source": "PRODUCTION_READ_ONLY",
        "spread_ledger_present_in_export": rows["spread_ledger"] is not None,
        "spread_ledger": observed["spread_ledger"], "spread_reserves": observed["spread_reserves"],
        "n012_a": {"frozen_at": CANDIDATE, "eligible_observed_entries": 0,
                   "paired_net_rs": None, "status": "NO_DIRECTIONAL_OPPORTUNITY"},
        "spread_replay": "UNAVAILABLE_EXACT_EXIT_QUOTES",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", action="store_true")
    parser.add_argument("--export", type=Path)
    parser.add_argument("--production-evidence", type=Path)
    args = parser.parse_args()
    if args.runtime:
        out = runtime()
    else:
        if args.export is None or args.production_evidence is None:
            parser.error("archive reconciliation requires an export and Production evidence")
        out = reconcile(args.export, json.loads(args.production_evidence.read_bytes()))
    print(json.dumps(out, indent=2, sort_keys=True))
