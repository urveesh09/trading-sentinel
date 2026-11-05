"""Acquire the official equal-weight price series with private raw receipts."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import requests

from india_vol_data import BASE, periods, read_rows

HERE = Path(__file__).resolve().parent
RAW = HERE / "_local/breadth/quarters"
PAGE = f"{BASE}/reports-indices-historical-index-data"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    closes, receipts = {}, {}
    with requests.Session() as client:
        client.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/html,*/*", "Referer": PAGE})
        client.get(PAGE, timeout=15).raise_for_status()
        for first, last in periods():
            path = RAW / f"equal-{first}.json"
            if path.exists():
                raw = path.read_bytes()
            else:
                response = client.get(f"{BASE}/api/historicalOR/indicesHistory", timeout=15,
                                      params={"indexType": "NIFTY50 EQUAL WEIGHT", "from": first.strftime("%d-%m-%Y"),
                                              "to": last.strftime("%d-%m-%Y")})
                response.raise_for_status()
                raw = response.content
                time.sleep(.6)
            values, invalid = read_rows(raw, "NIFTY50 EQL WGT", first, last)
            if not path.exists():
                with path.open("xb") as handle:
                    handle.write(raw)
            dated = {d.isoformat(): close for d, close in values.items()}
            assert not (dated.keys() & closes.keys())
            closes.update(dated)
            receipts[path.name] = {"sha256": digest(raw), "count": len(values), "invalid_ohlc_dates": sorted(invalid)}
    benchmark = HERE / "_local/india-vix/india-vol-closes.json"
    benchmark_raw = benchmark.read_bytes()
    expected = json.loads((HERE / "india-vol-coverage.json").read_bytes())["normalized_sha256"]
    assert digest(benchmark_raw) == expected
    index = {d: row["nifty"] for d, row in json.loads(benchmark_raw)["closes"].items() if row["nifty"] is not None}
    source = {"equal": closes, "nifty": index}
    data = json.dumps(source, indent=2, sort_keys=True).encode() + b"\n"
    with (RAW.parent / "breadth-closes.json").open("xb") as handle:
        handle.write(data)
    coverage = {"source": "NSE index price history", "normalized_sha256": digest(data),
                "nifty_benchmark_sha256": expected, "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
                "raw": receipts, "equal_count": len(closes), "nifty_count": len(index),
                "common_count": len(closes.keys() & index.keys()), "common_first": min(closes.keys() & index.keys()),
                "common_last": max(closes.keys() & index.keys()), "only_equal": sorted(closes.keys() - index.keys()),
                "only_nifty": sorted(index.keys() - closes.keys())}
    with (HERE / "breadth-coverage.json").open("x", encoding="utf-8") as handle:
        json.dump(coverage, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print({k: v for k, v in coverage.items() if k != "raw"}, flush=True)


if __name__ == "__main__":
    main()
