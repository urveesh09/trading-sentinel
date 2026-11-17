"""SN476 acquisition (read-only): Production's Gold / N11-paper tables and NIFTY N11 evaluations, for the live join (PLAN.md SN476 A).

Runs INSIDE a throwaway container with Production's data volume mounted READ-ONLY (export_fno_replay_dataset.py's pattern):

  docker run --rm -v production_trading-sentinel_trading_data:/data:ro -v <sn476>/_local:/out -v <sn476>:/s:ro \
      --entrypoint python production_trading-sentinel-python-engine:latest /s/sn476_pull.py

cache.db is opened with mode=ro; nothing in /data is written. Output: /out/prod-gold-<UTC stamp>.json (tables in full, the
fno_signals rows from 2026-11-02 on) and its sha256 beside it.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
from pathlib import Path

TABLES = ("fno_n11_paper", "fno_n11_gate", "sn_gold_positions", "sn_gold_days", "sn_gold_wallet", "sn_gold_skips", "sn_gold_bars")


def main():
    con = sqlite3.connect("file:/data/cache.db?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    have = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    out = {"pulled_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "source": "PRODUCTION_DATA_VOLUME_READ_ONLY:/data/cache.db"}
    for t in TABLES:
        out[t] = [dict(r) for r in con.execute(f'select * from "{t}"')] if t in have else None
    out["fno_signals"] = [dict(r) for r in con.execute("select * from fno_signals where evaluated_at >= '2026-11-02' order by evaluated_at")]
    blob = json.dumps(out, default=str, sort_keys=True).encode()
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    p = Path("/out") / f"prod-gold-{stamp}.json"
    p.write_bytes(blob)
    (p.with_suffix(".sha256")).write_text(hashlib.sha256(blob).hexdigest())
    print(p.name, hashlib.sha256(blob).hexdigest(), {t: (len(out[t]) if out[t] is not None else None) for t in TABLES}, len(out["fno_signals"]))


if __name__ == "__main__":
    main()
