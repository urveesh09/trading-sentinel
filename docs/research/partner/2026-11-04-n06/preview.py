"""Render the N06 messages from Production's real Nov 4 rows (copied read-only), in Dev's code, on a temp DB."""
import asyncio
import json
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, r"C:\Users\Urveesh\Desktop\trading-sentinel\python-engine")
import pytz  # noqa: E402

from config import settings  # noqa: E402
import fno_positions as fpos  # noqa: E402
import partner_sentinel as ps  # noqa: E402
import partner_watch as pw  # noqa: E402

IST = pytz.timezone("Asia/Kolkata")
rows = json.loads(Path(sys.argv[1]).read_text())
db = str(Path(tempfile.mkdtemp()) / "preview.db")
settings.PARTNER_SENTINEL_ADVICE_ENABLED = True
asyncio.run(fpos.init_fno_positions_db(db))
with sqlite3.connect(db) as c:
    for r in rows:
        r = {k: v for k, v in r.items() if k != "id"} | {"id": r["id"]}
        c.execute(f"INSERT INTO fno_positions({','.join(r)}) VALUES({','.join('?' * len(r))})", tuple(r.values()))

entry = IST.localize(datetime(2026, 11, 4, 12, 42, 0))
for f in ps.events(db, "2026-11-04", entry):
    print(f[0]); print(f[2](32304.6)); print()
leave = IST.localize(datetime(2026, 11, 4, 13, 12, 30))
for f in ps.events(db, "2026-11-04", leave):
    print(f[0]); print(f[2](32304.6)); print()
print(ps.open_line(db, "2026-11-04", "SENSEX"))
# The 10:24 buy's PLAN with the Sentinel's lines (Nov 4 plan values, the records as scored on Production).
recs = {"UNUSUAL_SIZE": {"verdict": "SUPPORTED", "since": "2026-10-27", "warned": {"n": 57, "total": -38024.0},
                         "unwarned": {"n": 175, "total": -2130.0}},
        "AFTER_LOSS": {"verdict": "SUPPORTED", "since": "2026-10-27", "warned": {"n": 143, "total": -31721.0},
                       "unwarned": {"n": 89, "total": -8433.0}},
        "CHASED_SPIKE": {"verdict": "NOT_SUPPORTED", "since": "2026-10-27", "warned": {"n": 96, "total": 49703.0},
                         "unwarned": {"n": 132, "total": -94312.0}}}
ps._RECORDS[(db, "2026-11-05")] = recs
plan = pw.Plan(entry=598.75, qty=100, stop=499.9, stop_basis="SWING", swing=98.82, loss=10051.0, cash=80456.1,
               stop_index=77006.0, index_stop_option=501.05, target=784.95, target_index=77439.0, run_pct=0.08,
               run_from=554.1, trend="WITH")
size, notes = asyncio.run(pw._sentinel_notes(db, "2026-11-05", plan, lot=20, exchange="BFO", bought=100,
                                             bought_px=598.75, lots=5, usual=0.31,
                                             after_loss={"loss": 2957.0, "at": "10:23", "minutes": 1}))
print("PLAN 10:24 extra lines:"); print(size); print("\n".join(notes)); print()
print("WATCH_ON extra lines:"); print("\n".join(ps.morning_lines(recs)))
