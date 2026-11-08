"""Reproduce the compatible-book CSCV from saved daily strategy receipts."""

from datetime import date, timedelta
import json
from pathlib import Path
import sys

import numpy as np


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-01-fno-n09"))
from analyze_panel import cscv


def week(value):
    iso = value.isocalendar()
    return iso.year, iso.week


def main():
    audit = json.loads((HERE / "closeout-receipts.json").read_bytes())
    first, last = date(2022, 6, 3), date(2026, 10, 28)
    weeks = sorted({week(first + timedelta(days=i)) for i in range((last - first).days + 1)})
    index = {w: i for i, w in enumerate(weeks)}
    names, series, duplicates, seen = [], [], {}, {}
    candidates = [("N11T", "round30-YYYY.json", "N11T")]
    candidates.extend((f"{r['round']}:{r['arm']}", r["receipt"], r["arm"]) for r in audit["rows"]
                      if r["eligibility"] == "full_book")
    for label, receipt, arm in candidates:
        pnl = np.zeros(len(weeks))
        for year in range(2022, 2027):
            panel = json.loads((HERE / receipt.replace("YYYY", str(year))).read_bytes())[arm]
            for day, value in panel["daily"].items():
                pnl[index[week(date.fromisoformat(day))]] += value
        fingerprint = tuple(np.round(pnl, 2))
        if fingerprint in seen:
            duplicates[label] = seen[fingerprint]
            continue
        seen[fingerprint] = label
        names.append(label)
        series.append(pnl)
    result = cscv(np.asarray(series).T, blocks=16)
    result["picks"] = {names[int(index)]: count for index, count in result["picks"].items()}
    assert names == audit["subset_names"] and duplicates == audit["duplicates"]
    assert result == audit["subset_cscv"], result
    print(f"PBO {result['pbo']:.9f}, {result['books']} unique books, {result['weeks']} weeks, {result['combinations']} splits")


if __name__ == "__main__":
    main()
