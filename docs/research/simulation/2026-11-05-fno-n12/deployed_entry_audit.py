"""Recompute observed N11 signal geometry and test decision-quote availability."""

import argparse
import ast
from contextlib import closing
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

import pandas as pd

from deployed_control_nov5 import DAYS, HERE, IDS, ROOT, digest
import fno_book
from config import settings
from fno_engine_mom import evaluate_fno_mom


IST = timezone(timedelta(hours=5, minutes=30))
REFERENCE = "398d44ad"
SOURCE = ("config.py", "fno_book.py", "fno_engine_mom.py", "fno_shadow.py", "fno_chain.py",
          "fno_entry_plan.py", "fno_models.py", "options_math.py")
NUMERIC = ("or_high", "or_low", "atr", "rvol", "stop_underlying", "target_underlying")


def signal_source(name, source):
    tree = ast.parse(source)
    if name == "fno_book.py":
        tree.body = [node for node in tree.body if not (
            isinstance(node, ast.AsyncFunctionDef) and node.name in {"_record", "drive_today"}
        )]
    if name == "config.py":
        cfg = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Settings")
        cfg.body = [node for node in cfg.body if not (
            isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in
            {"FNO_DR_EXIT_PATH_RECORDING", "PARTNER_WATCH_PROFIT_PROTECTION_ENABLED"}
        )]
    return ast.dump(tree)


def verify_sources():
    result = {}
    for name in SOURCE:
        path = f"python-engine/{name}"
        reference = subprocess.check_output(["git", "show", f"{REFERENCE}:{path}"], cwd=ROOT)
        local = (ROOT / path).read_bytes()
        if signal_source(name, reference) != signal_source(name, local):
            raise ValueError(f"Pure replay source differs from Production reference: {name}")
        result[name] = hashlib.sha256(reference).hexdigest()
    return result


def archived_quotes(folder, manifest, rows):
    result = {row["id"]: {} for row in rows}
    for day in DAYS:
        path, = [folder / name for name in manifest["files_sha256"]
                 if name.startswith(f"quotes/{day}/") and name.endswith((".gz", ".open"))]
        if digest(path) != manifest["files_sha256"][path.relative_to(folder).as_posix()]:
            raise ValueError(f"Changed quote segment: {day}")
        targets = [(row, datetime.fromisoformat(row["entry_time"])) for row in rows
                   if row["entry_date"] == day]
        opener = gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" else path.open(encoding="utf-8")
        with opener as stream:
            for line in stream:
                quote = json.loads(line)
                received = datetime.fromisoformat(quote["received_at_utc"])
                contract = quote["contract"]
                for row, entry in targets:
                    if received > entry or contract["underlying"] != row["underlying"]:
                        continue
                    kind = ("option" if str(contract["instrument_token"]) == str(row["token"]) else
                            "future" if contract["instrument_type"] == "FUT" and
                            quote["selection_reason"] == "underlying_future_reference" else None)
                    if kind is None or (kind in result[row["id"]] and received <= result[row["id"]][kind][0]):
                        continue
                    result[row["id"]][kind] = received, quote
    return result


def bars(db, symbol, scan):
    first = (scan - timedelta(days=21)).date().isoformat() + " 09:15:00"
    frame = pd.read_sql_query(
        "SELECT datetime,open,high,low,close,volume FROM fut_candles WHERE interval='5minute' "
        "AND tradingsymbol=? AND datetime BETWEEN ? AND ? ORDER BY datetime",
        db, params=(symbol, first, scan.replace(tzinfo=None).isoformat(" ")),
    )
    frame.index = pd.to_datetime(frame.pop("datetime"))
    return frame


def replay_signal(own, volume, row, scan):
    frame = fno_book.with_participation(own, volume)
    fno_book._RETEST.clear()
    earlier = [at.to_pydatetime().replace(tzinfo=IST) + timedelta(minutes=5, seconds=1)
               for at in own.index[own.index.date == scan.date()]]
    for clock in [*(at for at in earlier if at < scan), scan]:
        shipped = (evaluate_fno_mom(own, row["regime"], clock) if volume is None else
                   evaluate_fno_mom(own, row["regime"], clock, rvol_bars=volume))
        signal = fno_book.n11_signal(frame, row["regime"], clock, shipped=shipped,
                                     adx_side="HIGH", underlying=row["underlying"])
    return signal


def selected_reward_risk(row):
    ask, qty = row["premium"], row["initial_qty"]
    stop = abs(row["fut_price"] - row["stop_underlying"])
    target = abs(row["target_underlying"] - row["fut_price"])
    delta = abs(row["delta"])
    spread = row["spread_pct"] * ask * qty
    risk = min(delta * stop, ask * settings.FNO_STOP_PREMIUM_PCT) * qty
    return (delta * target * qty - spread) / (risk + spread)


def audit(folder):
    source_hashes = verify_sources()
    manifest_path, db_path = folder / "manifest.json", folder / "fno-replay.sqlite"
    manifest = json.loads(manifest_path.read_bytes())
    if digest(db_path) != manifest["files_sha256"]["fno-replay.sqlite"]:
        raise ValueError("Changed export database")
    with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(
            "SELECT p.*,s.scan_id,s.regime,s.atr,s.rvol,s.or_high,s.or_low,s.premium,s.delta,s.spread_pct,"
            "s.fut_price,s.max_loss_rupees AS logged_max_loss FROM fno_positions p JOIN fno_signals s "
            "ON p.bar_ts=s.bar_ts AND p.underlying=s.underlying AND p.tradingsymbol=s.tradingsymbol "
            "WHERE p.id BETWEEN 55 AND 59 AND p.source='FNO_PAPER' AND s.accepted=1 AND s.leg='FNO_PAPER' ORDER BY p.id"
        ).fetchall()
        if tuple(row["id"] for row in rows) != IDS or sorted({row["entry_date"] for row in rows}) != list(DAYS):
            raise ValueError("Unexpected position or accepted-signal selection")
        quotes = archived_quotes(folder, manifest, rows)
        result = []
        for row in rows:
            scan = datetime.strptime(row["scan_id"][4:19], "%Y%m%d-%H%M%S").replace(tzinfo=IST)
            entry = datetime.fromisoformat(row["entry_time"])
            packets = quotes[row["id"]]
            fut_at, future = packets["future"]
            option_at, option = packets["option"]
            if (option["contract"]["tradingsymbol"], option["contract"]["expiry"], option["contract"]["lot_size"]) != (
                row["tradingsymbol"], row["expiry"], row["lot_size"]
            ):
                raise ValueError(f"Archived contract identity differs for {row['id']}")
            symbol = future["contract"]["tradingsymbol"]
            own = bars(db, symbol, scan)
            borrowed = bars(db, "NIFTY26NOVFUT", scan) if row["underlying"] == "SENSEX" else None
            replay = replay_signal(own, borrowed, row, scan)
            direction = replay.direction.value if replay.direction else None
            deltas = {field: round(getattr(replay, field) - row[field], 8) for field in NUMERIC}
            matches = (direction, replay.strategy, replay.bar_ts) == (
                row["direction"], row["strategy"], row["bar_ts"]) and all(abs(value) <= 1e-7 for value in deltas.values())
            qty, ask = row["initial_qty"], row["premium"]
            if (ask != row["entry_premium"] or row["fut_price"] != row["entry_underlying"] or
                    qty != row["initial_lots"] * row["lot_size"] or abs(qty * ask - row["logged_max_loss"]) > .01 or
                    abs(qty * ask - row["initial_max_loss_rupees"]) > .01):
                raise ValueError(f"Recorded entry economics disagree for {row['id']}")
            recorded_ask = option["sell_depth"][0]["price"] if option["sell_depth"] else None
            result.append({
                "id": row["id"], "venue": row["underlying"], "strategy": replay.strategy,
                "direction": direction, "scan": scan.isoformat(), "bar": replay.bar_ts, "bar_rows": len(own),
                "signal_matches": matches, "signal_numeric_deltas": deltas,
                "selected_contract": row["tradingsymbol"], "initial_lots": row["initial_lots"],
                "lot_size": row["lot_size"], "full_premium_loss": round(qty * ask, 2),
                "recorded_ask": ask, "archived_pre_entry_ask": recorded_ask,
                "archive_option_age_at_entry_sec": round((entry - option_at).total_seconds(), 6),
                "recorded_forward": row["fut_price"], "archived_pre_entry_forward": future["ltp"],
                "archive_future_age_at_entry_sec": round((entry - fut_at).total_seconds(), 6),
                "reward_risk_from_recorded_terms": round(selected_reward_risk(row), 6),
            })
    return {"export_manifest_sha256": digest(manifest_path), "reference": REFERENCE,
            "reference_sources_sha256": source_hashes,
            "signal_assumptions": {"adx_side": "HIGH, implied by recorded route", "regime": "recorded entry regime",
                                   "earlier_evaluation": "one second after each closed five-minute bar"},
            "premium_stop_fraction": settings.FNO_STOP_PREMIUM_PCT,
            "independent_entry_planner_matches": None, "positions": result}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("export", type=Path)
    report = audit(parser.parse_args().export)
    output = HERE / "deployed-entry-audit.json"
    if output.is_file():
        if json.loads(output.read_bytes()) != report:
            raise ValueError("Recomputed entry evidence differs from the recorded audit")
    else:
        with output.open("x", encoding="utf-8") as file:
            json.dump(report, file, indent=2, sort_keys=True)
            file.write("\n")
    positions = report["positions"]
    print("signal geometry matches", sum(row["signal_matches"] for row in positions), "of", len(positions))


if __name__ == "__main__":
    main()
