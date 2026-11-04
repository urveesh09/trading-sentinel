"""Public Yahoo daily acquisition for the broad penny-band universe (research only).

Universe: every non-SME ticker whose Kite daily close was in [4, 60] at least
once between 2025-07-01 and 2026-10-01 in the stopped-Production cache copy
(docs/research/2026-10-03-current-system/_local/stopped-production/cache.db),
mapped to its base NSE symbol (-BE twins collapse onto the base symbol).
No Breeze, broker or Production call. Raw replies are kept under _local/yahoo/raw.
"""
from __future__ import annotations
import json, sqlite3, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "python-engine"))
from backtest_all_yahoo import fetch_chart  # noqa: E402

CACHE = ROOT / "docs/research/2026-10-03-current-system/_local/stopped-production/cache.db"

def universe():
    c = sqlite3.connect(CACHE.as_uri() + "?mode=ro", uri=True)
    names = [t for (t,) in c.execute(
        "SELECT DISTINCT ticker FROM ohlcv_cache WHERE date BETWEEN '2025-07-01' AND '2026-10-01' AND close BETWEEN 4 AND 60")]
    keep = set()
    for t in names:
        if t.endswith(("-SM", "-ST")):
            continue
        base, _, suffix = t.partition("-")
        if suffix and suffix != "BE":
            continue
        keep.add(base)
    return sorted(keep)

def main():
    local = HERE / "_local" / "yahoo"
    local.mkdir(parents=True, exist_ok=True)
    target = local / "yahoo.sqlite"
    if target.exists():
        raise SystemExit("acquisition output exists; evidence is immutable")
    names = universe() + ["NIFTYBEES"]
    (HERE / "universe-yahoo.json").write_text(json.dumps({"source": str(CACHE.relative_to(ROOT)), "rule": __doc__.strip(), "symbols": names}, indent=1))
    con = sqlite3.connect(target)
    con.execute("CREATE TABLE ohlcv_cache(ticker TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,PRIMARY KEY(ticker,date))")
    receipts = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = {pool.submit(fetch_chart, local, s, s + ".NS", "1d", "2019-01-01", "2026-11-03"): s for s in names}
        for f in as_completed(futs):
            s = futs[f]
            try:
                rows, receipt = f.result()
                con.executemany("INSERT OR IGNORE INTO ohlcv_cache VALUES (?,?,?,?,?,?,?)", rows); con.commit()
            except Exception as exc:
                receipt = {"symbol": s, "state": "FAILED", "reason": repr(exc)}
            receipts.append(receipt)
            if len(receipts) % 50 == 0:
                print(f"acquired {len(receipts)}/{len(names)}", flush=True)
    con.close()
    (HERE / "_local" / "yahoo-acquisition.json").write_text(json.dumps({"as_of": datetime.now(timezone.utc).isoformat(), "breeze_calls": 0, "broker_calls": 0, "requests": len(names), "receipts": receipts}, indent=1, default=str))
    ok = sum(r.get("state") == "AVAILABLE" for r in receipts)
    print(f"done {ok}/{len(names)} available", flush=True)

if __name__ == "__main__":
    main()
