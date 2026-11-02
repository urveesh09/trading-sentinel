"""Copy the index's one-minute candles for the study's sessions into a private file, in one short read-only query.

The shared history is opened read-only and never written. No ICICI call. Run once.
"""
import json
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = Path(r"C:\Users\Urveesh\sentinel-operations\breeze-history-20261029\data\breeze-history.sqlite")
DAYS = ["2026-09-08", "2026-09-15", "2026-09-22", "2026-09-29", "2026-10-06", "2026-10-13", "2026-10-19", "2026-10-27"]
target = HERE / "_local/index-minutes.json"
assert not target.exists()
c = sqlite3.connect(SRC.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
out = {}
for day in DAYS:
    out[day] = c.execute("select datetime, open, high, low, close from candles where kind='index' and underlying='NIFTY' and interval='1minute' "
                         "and datetime between ? and ? order by datetime", (day + " 09:15:00", day + " 15:30:00")).fetchall()
    print(day, len(out[day]))
c.close()
target.write_text(json.dumps(out) + "\n", encoding="utf-8")
