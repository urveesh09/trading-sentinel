"""Archive and validate official NSE index closes without looking at strategy outcomes."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import time

import requests

HERE = Path(__file__).resolve().parent
RAW = HERE / "_local/india-vix/quarters"
BASE = "https://www.nseindia.com"
FIRST = date(2021, 1, 1)
LAST = date(2026, 11, 4)
SERIES = {"vix": ("INDIA VIX", "reports-indices-historical-vix", "vixhistory", {}),
          "nifty": ("NIFTY 50", "reports-indices-historical-index-data", "indicesHistory", {"indexType": "NIFTY 50"})}


def periods():
    first = FIRST
    while first <= LAST:
        boundary = date(first.year + int(first.month == 10), (first.month + 2) % 12 + 1, 1)
        yield first, min(LAST, boundary - timedelta(days=1))
        first = boundary


def read_rows(raw, index, first, last):
    values, seen, invalid = {}, set(), []
    rows = json.loads(raw)["data"]
    for row in rows:
        session = datetime.strptime(row["EOD_TIMESTAMP"], "%d-%b-%Y").date()
        if row["EOD_INDEX_NAME"].strip().upper() != index or session in seen or not first <= session <= last:
            raise ValueError(f"unexpected or duplicate {index} date {session}")
        seen.add(session)
        opened, high, low, close = (float(row[f"EOD_{key}_INDEX_VAL"] or 0) for key in ("OPEN", "HIGH", "LOW", "CLOSE"))
        if not all(math.isfinite(v) and v > 0 for v in (opened, high, low, close)) or (
            low > min(opened, close) or high < max(opened, close)
        ):
            invalid.append(session.isoformat())
            continue
        values[session] = close
    if not values or min(seen) > first + timedelta(days=8) or max(seen) < last - timedelta(days=8):
        raise ValueError(f"truncated {index} history for {first} through {last}")
    return values, invalid


def archive(session, name, first, last):
    index, referer, endpoint, extra = SERIES[name]
    page = f"{BASE}/{referer}"
    path = RAW / f"{name}-{first}.json"
    if path.exists():
        raw = path.read_bytes()
    else:
        response = session.get(f"{BASE}/api/historicalOR/{endpoint}", timeout=15, headers={"Referer": page},
                               params={**extra, "from": first.strftime("%d-%m-%Y"), "to": last.strftime("%d-%m-%Y")})
        response.raise_for_status()
        raw = response.content
        time.sleep(0.6)
    values, invalid = read_rows(raw, index, first, last)
    if not path.exists():
        with path.open("xb") as handle:
            handle.write(raw)
    return values, {"file": path.name, "sha256": hashlib.sha256(raw).hexdigest(), "count": len(values),
                    "invalid_ohlc_dates": sorted(invalid), "first": min(values).isoformat(), "last": max(values).isoformat()}


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    data, receipts = {name: {} for name in SERIES}, {}
    with requests.Session() as session:
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/html,*/*"})
        session.get(f"{BASE}/reports-indices-historical-vix", timeout=15).raise_for_status()
        for first, last in periods():
            for name in SERIES:
                values, receipt = archive(session, name, first, last)
                assert not (data[name].keys() & values.keys())
                data[name].update(values)
                receipts[receipt["file"]] = receipt
    output = {"source": "NSE public historical index series", "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
              "requested": [FIRST.isoformat(), LAST.isoformat()], "response_receipts": receipts,
              "only_nifty": [d.isoformat() for d in sorted(data["nifty"].keys() - data["vix"].keys())],
              "only_vix": [d.isoformat() for d in sorted(data["vix"].keys() - data["nifty"].keys())],
              "closes": {d.isoformat(): {name: series.get(d) for name, series in data.items()}
                         for d in sorted(set().union(*(x.keys() for x in data.values())))}}
    with (HERE / "india-vol-closes.json").open("x", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print("NSE coverage", {name: len(values) for name, values in data.items()},
          "missing matches", len(output["only_nifty"]), len(output["only_vix"]), flush=True)


if __name__ == "__main__":
    main()
