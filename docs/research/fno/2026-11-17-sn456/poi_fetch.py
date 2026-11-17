"""SN456 data acquisition (separate from scoring): NSE's public participant-wise open interest archive.

Source template (public, static, no cookies): https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_DDMMYYYY.csv
Every weekday from 2019-02-18 to 2026-10-28 (the last NIFTY futures minute in the Breeze history) is requested once; a 404 is
recorded (holiday or not published) and never retried. Each file is saved under _local/poi with a receipt in
_local/poi/receipts.json: url, http status, sha256, size, the archive's Last-Modified header (the publication clock, assumed
availability), the fetch clock in UTC (first receipt, historical), and parse checks:
  title_date_ok   the "as on <date>" in the title equals the requested date
  rows_ok         Client, DII, FII, Pro and TOTAL are present with Future Index Long / Short
  sum_ok          the four participants sum to TOTAL in both columns
  balance_ok      TOTAL Future Index Long == TOTAL Future Index Short
Generic client identity only. Resumable: runs at most ~8.5 minutes per call and is re-run until it prints DONE.
No price data is read here.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
POI = HERE / "_local" / "poi"
REC = POI / "receipts.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
LO, HI = dt.date(2019, 2, 18), dt.date(2026, 10, 28)
BUDGET_S = 510
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def parse(text, d):
    out = {"title_date_ok": False, "rows_ok": False, "sum_ok": False, "balance_ok": False}
    lines = text.replace("\r", "").split("\n")
    m = re.search(r"as on\s+([A-Za-z]{3})[a-z]*\s+(\d{1,2}),\s*(\d{4})", lines[0]) if lines else None
    if m:
        try:
            out["title_date_ok"] = dt.date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2))) == d
        except (KeyError, ValueError):
            pass
    rows = {}
    for r in csv.reader(io.StringIO("\n".join(lines[1:]))):
        if r and r[0].strip():
            rows[r[0].strip()] = [c.strip() for c in r]
    head = rows.get("Client Type")
    if not head:
        return out, None
    try:
        il, ish = head.index("Future Index Long"), head.index("Future Index Short")
        vals = {k: (int(float(rows[k][il])), int(float(rows[k][ish]))) for k in ("Client", "DII", "FII", "Pro", "TOTAL")}
    except (KeyError, ValueError, IndexError):
        return out, None
    out["rows_ok"] = True
    out["sum_ok"] = all(sum(vals[k][j] for k in ("Client", "DII", "FII", "Pro")) == vals["TOTAL"][j] for j in (0, 1))
    out["balance_ok"] = vals["TOTAL"][0] == vals["TOTAL"][1]
    return out, vals


def main():
    POI.mkdir(parents=True, exist_ok=True)
    rec = json.loads(REC.read_text(encoding="utf-8")) if REC.exists() else {}
    t0 = time.time()
    d = LO
    todo = []
    while d <= HI:
        if d.weekday() < 5 and d.isoformat() not in rec:
            todo.append(d)
        d += dt.timedelta(days=1)
    for n, d in enumerate(todo):
        if time.time() - t0 > BUDGET_S:
            break
        url = f"https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_{d:%d%m%Y}.csv"
        p = POI / f"poi-{d:%Y%m%d}.csv"
        hdr = POI / "_hdr.txt"
        r = subprocess.run(["curl", "-s", "-m", "40", "-A", UA, "-D", str(hdr), "-o", str(p), "-w", "%{http_code}", url],
                           capture_output=True, text=True)
        code = r.stdout.strip()
        lm = None
        if hdr.exists():
            for line in hdr.read_text(encoding="latin-1").splitlines():
                if line.lower().startswith("last-modified:"):
                    lm = line.split(":", 1)[1].strip()
        e = {"url": url, "http": code, "fetched_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "last_modified": lm}
        if code == "200" and p.exists() and p.stat().st_size > 200:
            b = p.read_bytes()
            e["sha256"], e["size"] = hashlib.sha256(b).hexdigest(), len(b)
            chk, vals = parse(b.decode("utf-8", errors="replace"), d)
            e.update(chk)
            e["parsed"] = vals is not None
        else:
            e["sha256"] = None
            if p.exists():
                p.unlink()
            if code not in ("404",):
                e["retry"] = True
        if e.get("retry"):
            print("transient", d, code)
        else:
            rec[d.isoformat()] = e
        if n % 25 == 0:
            REC.write_text(json.dumps(rec, indent=0, sort_keys=True), encoding="utf-8")
        time.sleep(0.25)
    REC.write_text(json.dumps(rec, indent=0, sort_keys=True), encoding="utf-8")
    left = sum(1 for x in todo if x.isoformat() not in rec)
    ok = sum(1 for v in rec.values() if v.get("sha256"))
    print(f"{len(rec)} receipts, {ok} files, {len(rec) - ok} missing, {left} left", "DONE" if left == 0 else "MORE")


if __name__ == "__main__":
    sys.exit(main())
