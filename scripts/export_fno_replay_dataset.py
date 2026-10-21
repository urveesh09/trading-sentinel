"""Export a read-only F&O replay dataset from a Sentinel data volume.

Run inside a throwaway container with the data volume mounted READ-ONLY and a
Dev output folder mounted writable, for example:

    docker run --rm -v production_trading-sentinel_trading_data:/data:ro \
        -v "<dev>/docs/research/fno/<dated>/_local:/out" -v "<dev>/scripts:/scripts:ro" \
        --entrypoint python production_trading-sentinel-python-engine:latest \
        /scripts/export_fno_replay_dataset.py --data /data --out /out

What it copies (nothing in /data is modified; SQLite is opened mode=ro):

* ``research/quotes/<day>/`` finalized segments and manifests, byte-for-byte —
  the observed NIFTY/SENSEX futures + option quotes with raw provider packets.
  A past session's still-open journal (the collector seals a day only when a
  later session runs) is copied too and listed under ``unsealed_days``; the
  active day's journal is never copied;
* from ``cache.db``: the cached candles (every interval, tagged) of every
  futures token the archive identifies as a NIFTY or SENSEX future, the ``fno_signals`` evaluation log (point-in-
  time regime and live accept/reject decisions) and the single-leg / defined-
  risk paper positions (for replay parity checks);
* ``manifest.json`` with source, SHA-256 of every copied file, row counts and
  ``option_expiries`` (per underlying, every option expiry the archive quoted).

Standard library only, so it runs inside the engine image without the repo.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

TABLES = ("fno_signals", "fno_positions", "fno_dr_positions")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _scan_contracts(quote_root: Path) -> tuple[dict[int, str], dict[str, list[str]]]:
    """Archived index contracts (NIFTY, SENSEX): futures token -> tradingsymbol,
    and per underlying every option expiry ever quoted (the replay's dated
    expiry calendar; one batch may omit a series, the archive as a whole not)."""
    tokens: dict[int, str] = {}
    expiries: dict[str, set[str]] = {}
    for segment in sorted([*quote_root.glob("*/quotes-*.jsonl.gz"), *quote_root.glob("*/quotes.jsonl.open")]):
        opener = gzip.open if segment.suffix == ".gz" else open
        with opener(segment, "rt", encoding="utf-8") as handle:
            for line in handle:
                contract = json.loads(line).get("contract") or {}
                underlying, kind = contract.get("underlying"), contract.get("instrument_type")
                if underlying not in {"NIFTY", "SENSEX"}:
                    continue
                if kind == "FUT":
                    tokens[int(contract["instrument_token"])] = contract["tradingsymbol"]
                elif kind in ("CE", "PE") and contract.get("expiry"):
                    expiries.setdefault(underlying, set()).add(str(contract["expiry"]))
    return tokens, {name: sorted(values) for name, values in sorted(expiries.items())}


def export(data: Path, out: Path) -> dict:
    quote_root = data / "research" / "quotes"
    if not quote_root.is_dir():
        raise SystemExit(f"no research quote archive under {data}")
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise SystemExit(f"{out} is not empty; exports are written once")
    files, unsealed = {}, []
    today = datetime.now(timezone.utc).date().isoformat()
    for segment in sorted([*quote_root.glob("*/quotes-*.jsonl.*"), *quote_root.glob("*/quotes.jsonl.open")]):
        if segment.name.endswith(".open"):
            if segment.parent.name >= today:
                continue  # the active session is still being written
            unsealed.append(segment.parent.name)
        target = out / "quotes" / segment.parent.name / segment.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(segment, target)
        files[str(target.relative_to(out)).replace("\\", "/")] = _sha(target)

    # [SX-F1] The exit loop's own looks at each held option (fno_exit_paths.py),
    # for replaying exit rules at the live clock. Finished sessions only (the
    # files are named by IST date; the exit loop stops at the 15:30 close).
    ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    for path in sorted((data / "research" / "fno_exit_paths").glob("*.jsonl")):
        if path.stem > ist.date().isoformat() or (path.stem == ist.date().isoformat()
                                                   and ist.hour * 60 + ist.minute < 15 * 60 + 35):
            continue
        target = out / "fno_exit_paths" / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        files[str(target.relative_to(out)).replace("\\", "/")] = _sha(target)

    futures, option_expiries = _scan_contracts(quote_root)
    source = sqlite3.connect(f"file:{data / 'cache.db'}?mode=ro", uri=True)
    replay_db = out / "fno-replay.sqlite"
    target = sqlite3.connect(replay_db)
    counts = {}
    try:
        target.execute("CREATE TABLE fut_candles (instrument_token INTEGER, tradingsymbol TEXT, interval TEXT,"
                       " datetime TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, oi REAL,"
                       " PRIMARY KEY (instrument_token, interval, datetime))")
        rows = [(token, futures[token], *row) for token in sorted(futures) for row in source.execute(
            "SELECT interval, datetime, open, high, low, close, volume, oi FROM intraday_cache_by_token "
            "WHERE instrument_token=? ORDER BY datetime", (token,))]
        target.executemany("INSERT INTO fut_candles VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
        counts["fut_candles"] = len(rows)
        for table in TABLES:
            columns = [row[1] for row in source.execute(f"PRAGMA table_info({table})")]
            if not columns:
                counts[table] = None
                continue
            target.execute(f"CREATE TABLE {table} ({', '.join(columns)})")
            data_rows = source.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
            target.executemany(f"INSERT INTO {table} VALUES ({', '.join('?' * len(columns))})", data_rows)
            counts[table] = len(data_rows)
        target.commit()
    finally:
        source.close()
        target.close()
    files["fno-replay.sqlite"] = _sha(replay_db)
    manifest = {"schema": "sentinel_fno_replay_dataset_v1", "source": "SENTINEL_DATA_VOLUME_READ_ONLY",
                "exported_at_utc": datetime.now(timezone.utc).isoformat(),
                "quote_days": sorted({path.split("/")[1] for path in files if path.startswith("quotes/")}),
                "unsealed_days": unsealed,
                "nifty_future_tokens": {str(k): v for k, v in sorted(futures.items())},
                "option_expiries": option_expiries,
                "row_counts": counts, "files_sha256": files}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("--data", type=Path, required=True, help="mounted data volume (read-only)")
    cli.add_argument("--out", type=Path, required=True, help="empty output directory")
    args = cli.parse_args()
    manifest = export(args.data, args.out)
    print(json.dumps({k: manifest[k] for k in ("quote_days", "unsealed_days", "nifty_future_tokens", "row_counts")},
                     indent=2))


if __name__ == "__main__":
    main()
