"""Bind the calendar sleeve to public reports issued before each session."""
import argparse
from bisect import bisect_left
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile

from anatomy import DATASETS, read

HERE = Path(__file__).resolve().parent
LOCAL = HERE / "_local/round9"
BSE = "https://www.bseindia.com/download/Bhavcopy/Derivative/MS_{date}-01.csv"
NSE = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{date}_F_0000.csv.zip"


def targets():
    rows = read(HERE / "cross-index-coverage.json")["history"]["potential_calendar_sleeve_days"]
    calendar = sorted({day for year in ("2025", "2026")
                       for day in read(DATASETS[year] / "manifest.json")["sessions"]})
    out = {}
    for day in rows:
        index = bisect_left(calendar, day)
        assert index > 0 and calendar[index] == day
        out[day] = calendar[index - 1]
    return out


def relative(exchange, previous):
    return f"exchange/{exchange}-{previous}.raw"


def get(job):
    exchange, previous = job
    path = LOCAL / relative(exchange, previous)
    url = {"BSE": BSE, "NSE": NSE}[exchange].format(date=previous.replace("-", ""))
    if path.exists():
        return exchange, previous, "cached"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0",
                                                  "Referer": url.split("/download", 1)[0]})
        with urllib.request.urlopen(req, timeout=20) as response:
            body = response.read(6_000_000)
        if exchange == "NSE" and not body.startswith(b"PK\x03\x04"):
            raise ValueError("not an NSE ZIP")
        if exchange == "BSE" and not body.startswith(b"Market Summary Date,"):
            raise ValueError("not a BSE market-summary CSV")
        with path.open("xb") as handle:
            handle.write(body)
        return exchange, previous, "saved"
    except (OSError, ValueError) as exc:
        return exchange, previous, type(exc).__name__ + " " + str(exc)


def collect():
    (LOCAL / "exchange").mkdir(parents=True, exist_ok=True)
    jobs = [(exchange, day) for day in sorted(set(targets().values())) for exchange in ("BSE", "NSE")]
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(get, jobs))
    with (LOCAL / "acquisition.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(results) + "\n")
    print("exchange reports", len(results), "available", sum(row[-1] in ("saved", "cached") for row in results))


def parse(exchange, path, date):
    raw = path.read_bytes()
    if exchange == "NSE":
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
            assert len(names) == 1
            text = archive.read(names[0]).decode("utf-8-sig")
    else:
        text = raw.decode("utf-8-sig")
    option_dates, future_dates = set(), set()
    for row in csv.DictReader(io.StringIO(text)):
        if exchange == "NSE":
            if row["TckrSymb"] != "NIFTY":
                continue
            assert row["TradDt"] == date
            expiry = row["FininstrmActlXpryDt"] or row["XpryDt"]
            if row["OptnTp"] in ("PE", "CE"):
                option_dates.add(expiry)
        else:
            if row["Asset Code"].strip() != "BSX":
                continue
            assert datetime.strptime(row["Market Summary Date"].strip(), "%d %b %Y").date().isoformat() == date
            expiry = datetime.strptime(row["Expiry Date"].strip(), "%d %b %Y").date().isoformat()
            if row["Product Type"].strip() == "IO":
                option_dates.add(expiry)
            elif row["Product Type"].strip() == "IF":
                future_dates.add(expiry)
    return hashlib.sha256(raw).hexdigest(), sorted(option_dates), sorted(future_dates)


def catalogue():
    dates = {}
    for day, previous in targets().items():
        out = dates[day] = {"previous": previous, "sources": {}}
        for exchange in ("NSE", "BSE"):
            path = LOCAL / relative(exchange, previous)
            if path.is_file():
                sha, opt, fut = parse(exchange, path, previous)
                out["sources"][exchange] = {"sha256": sha, "options": opt, "futures": fut}
        nse = out["sources"].get("NSE", {})
        bse = out["sources"].get("BSE", {})
        expected_sensex = next((e for e in bse.get("options", ()) if e >= day), None)
        future = next((e for e in bse.get("futures", ()) if e >= day), None)
        if day not in nse.get("options", ()):
            out["status"] = "NIFTY_DATE_UNCONFIRMED"
        elif expected_sensex is None or future is None:
            out["status"] = "SENSEX_IDENTITY_UNCONFIRMED"
        elif expected_sensex == day:
            out["status"] = "SENSEX_INELIGIBLE"
        else:
            out.update(status="DATED_REGULAR", option_expiry=expected_sensex, future_expiry=future)
    with (LOCAL / "catalogue.json").open("x", encoding="utf-8") as handle:
        json.dump(dates, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print("verified regular SENSEX contract dates", sum(d["status"] == "DATED_REGULAR" for d in dates.values()))


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=("collect", "catalogue"))
    action = cli.parse_args().action
    {"collect": collect, "catalogue": catalogue}[action]()
