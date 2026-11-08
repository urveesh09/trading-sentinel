"""Snapshot only already available SENSEX minute candles, read-only source."""
from collections import Counter
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3

from anatomy import read
from round9_data import LOCAL, HERE

SOURCE = Path.home() / "sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite"
DEST = LOCAL / "breeze.sqlite"
COLS = "kind,expiry,strike,opt,datetime,open,high,low,close,volume,oi"
MINUTES = {f"{i//60:02d}:{i%60:02d}" for i in range(555, 912)}
EXIT_MINUTE = "15:10"


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    if DEST.exists():
        raise FileExistsError(DEST)
    catalogue = read(LOCAL / "catalogue.json")
    covered = {d: v for d, v in catalogue.items() if v["status"] == "DATED_REGULAR"}
    first, last = min(covered), max(covered)
    warm = (date.fromisoformat(first) - timedelta(days=30)).isoformat()
    after = (date.fromisoformat(last) + timedelta(days=1)).isoformat()
    report = {}
    with sqlite3.connect(SOURCE.resolve().as_uri() + "?mode=ro", uri=True, timeout=20) as source, sqlite3.connect(DEST) as out:
        source.execute("BEGIN")
        out.execute("""CREATE TABLE candles (kind TEXT, expiry TEXT, strike REAL, opt TEXT,
                    datetime TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, oi REAL,
                    PRIMARY KEY (kind,expiry,strike,opt,datetime))""")
        insert = "INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?)"
        for expiry in sorted({v["future_expiry"] for v in covered.values()}):
            rows = source.execute(
                f"""SELECT {COLS} FROM candles WHERE underlying='SENSEX' AND interval='1minute'
                AND kind='future' AND expiry=? AND datetime>=? AND datetime<? AND close>0
                AND substr(datetime,12,5) BETWEEN '09:15' AND '15:29'""",
                (expiry, warm, after),
            )
            out.executemany(insert, rows)
        for day, identity in covered.items():
            regular = day + " 09:15:00"
            end = day + " 15:30:00"
            rows = source.execute(
                f"""SELECT {COLS} FROM candles WHERE underlying='SENSEX' AND interval='1minute'
                AND kind='option' AND expiry=? AND datetime>=? AND datetime<?
                AND close>0 AND volume>0 AND opt IN ('CE','PE')""",
                (identity["option_expiry"], regular, end),
            )
            out.executemany(insert, rows)
            future = out.execute("""SELECT datetime FROM candles WHERE kind='future'
                                 AND expiry=? AND datetime>=? AND datetime<?""",
                                 (identity["future_expiry"], regular, end)).fetchall()
            seen = {t[0][11:16] for t in future}
            option = out.execute("""SELECT opt,count(*),count(distinct substr(datetime,12,5)),min(datetime),max(datetime)
                                 FROM candles WHERE kind='option' AND expiry=? AND datetime>=? AND datetime<?
                                 GROUP BY opt""", (identity["option_expiry"], regular, end)).fetchall()
            covered_open = all(f"09:{minute:02d}" in seen for minute in range(15, 45))
            report[day] = {
                "future_minutes": len(seen & MINUTES), "future_missing": sorted(MINUTES - seen),
                "opening_complete": covered_open, "hard_flat_minute_present": EXIT_MINUTE in seen,
                "option_counts": option,
                "status": "OBSERVED" if future and option else "MISSING_MARKET_INPUT",
            }
        out.execute("CREATE INDEX candles_clock ON candles(kind,expiry,datetime)")
    spreads = read(HERE / "cross-index-coverage.json")["spread"]["quotes_by_premium_bin"]
    bfo = {k.split(":")[-1]: v for k, v in spreads.items() if k.startswith("SENSEX:")}
    manifest = {
        "underlying": "SENSEX", "lot_size": 20, "sessions": sorted(covered),
        "weekly_expiry_calendar": sorted({v["option_expiry"] for v in covered.values()}),
        "future_expiries": sorted({v["future_expiry"] for v in covered.values()}),
        "logged_regimes": {}, "catalogue_sha256": digest(LOCAL / "catalogue.json"),
        "data_sha256": digest(DEST), "source": "historical existing provider candles; exchange prior-file identity",
        "day_contracts": {d: {"option": v["option_expiry"], "future": v["future_expiry"]} for d, v in covered.items()},
        "coverage": report, "spread": bfo,
    }
    with (LOCAL / "manifest.json").open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print("tape coverage", dict(Counter(v["status"] for v in report.values())),
          "complete futures 09:15–15:11", sum(not v["future_missing"] for v in report.values()))
    for day, row in report.items():
        if row["status"] != "OBSERVED" or not row["opening_complete"] or not row["hard_flat_minute_present"]:
            print(day, row["status"], row["future_minutes"], row["opening_complete"], row["hard_flat_minute_present"])


if __name__ == "__main__":
    main()
