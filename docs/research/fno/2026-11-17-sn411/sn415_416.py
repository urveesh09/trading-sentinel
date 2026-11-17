"""SN415 / SN416 feasibility (PLAN.md section 1, frozen at e5cc95b7): what data on this PC could test a company-results
second move (SN415) or a USDINR lead (SN416)? Checked programmatically, read only; no download, no strategy number.

  Breeze history DB     the distinct underlyings and intervals of its candles
  real-quote archive    the distinct underlyings and instrument types in the sealed export's quote files (manifest-hashed)
  recorder copy         the Nov 16 copy's instruments.jsonl (what TR01 records)
  Kite 15-minute bars   the symbols and date range on disk (cash only; no filing timestamps travel with them)
  filings               any local file whose name mentions announcements / results / filings / XBRL
Writes results-sn415-416.json with the inventory and the exact samples each slot would need.
"""
from __future__ import annotations

import collections
import gzip
import json
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
OUT = HERE / "results-sn415-416.json"
HIST = Path(r"C:/Users/Urveesh/sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite")
EXPORT = Path(r"C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\docs\research\fno\2026-10-28-forward-panel"
              r"\_local\exports\20261116T103002Z")
REC = FNO / "2026-11-16-sn351" / "_local" / "rec-2026-11-16-open" / "instruments.jsonl"
KITE = FNO.parent / "kite" / "2026-10-05-momentum-h1" / "_local" / "raw"


def main():
    if OUT.exists():
        raise SystemExit("SN415 / SN416 feasibility is run once")
    con = sqlite3.connect(f"file:{HIST.as_posix()}?mode=ro", uri=True)
    breeze = [list(r) for r in con.execute("SELECT underlying, kind, interval, COUNT(*) FROM candles GROUP BY underlying, kind, interval")]
    arch = collections.Counter()
    day = sorted(p.name for p in (EXPORT / "quotes").iterdir() if p.is_dir())[-2]
    for f in (EXPORT / "quotes" / day).glob("*.jsonl.gz"):
        for line in gzip.decompress(f.read_bytes()).decode("utf-8").splitlines()[:200000]:
            c = json.loads(line)["contract"]
            arch[(c["underlying"], c["instrument_type"])] += 1
    rec = collections.Counter()
    for line in REC.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        rec[(r.get("underlying"), r.get("type"))] += 1
    syms = sorted({p.name.split("_")[0] for p in KITE.glob("*_15minute_*.json")})
    filings = [str(p) for p in FNO.parent.rglob("*") if p.is_file() and any(w in p.name.lower() for w in ("announcement", "filing", "xbrl", "corporate_results", "board_meeting"))][:20]
    res = {"breeze_underlyings": breeze, "archive_day_checked": day, "archive_underlyings_types": {f"{a}|{b}": n for (a, b), n in arch.items()},
           "recorder_nov16_underlyings_types": {f"{a}|{b}": n for (a, b), n in rec.items()}, "kite_15min_symbols": len(syms),
           "kite_has_usdinr": any("USDINR" in s for s in syms), "local_filing_files": filings}
    res["SN415"] = {"feasible_here": False,
                    "missing": ["exchange dissemination timestamps of results filings for a roster (NSE corporate announcements)",
                                "intraday stock prices around those timestamps at <= 1-minute resolution (the Kite bars are 15-minute, Jan - Jul 2026)",
                                "stock-option bid / ask with depth for the roster (none on this PC)"],
                    "sample_needed": ">= 40 results announcements across >= 15 F&O stocks with timestamps, 1-minute stock data and option quotes; "
                                     "stock options settle physically: intraday unwind before the broker's delivery-margin window",
                    "verdict": "CLOSED on data until the owner approves a filings source and option quotes"}
    res["SN416"] = {"feasible_here": not (False),
                    "missing": ["USDINR futures prices with exchange timestamps (Breeze, the archive and the recorder hold none)"],
                    "sample_needed": ">= 40 sessions of USDINR front-future ticks or 1-minute bars with exchange times beside NIFTY on the same clock",
                    "verdict": "CLOSED at feasibility (no FX data)"}
    res["SN416"]["feasible_here"] = False
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("kite_15min_symbols",)}, indent=1)[:4000])


if __name__ == "__main__":
    main()
