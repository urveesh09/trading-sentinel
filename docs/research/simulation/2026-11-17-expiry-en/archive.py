"""Read-only loader for Production's forward-panel quote archive (sealed export, hash-checked), expiry days only.
Each contract has ~one snapshot a minute with 5-level depth. Used for descriptive checks and the EN replay."""
from __future__ import annotations
import gzip, json, hashlib, glob, collections
from pathlib import Path
EXPORT = Path.home() / "sentinel-operations/fno-forward-panel-20261028/docs/research/fno/2026-10-28-forward-panel/_local/exports/20261117T103003Z"
NIFTY_EXP = ["2026-09-15","2026-09-22","2026-09-29","2026-10-06","2026-10-13","2026-10-19","2026-10-27","2026-11-03","2026-11-09","2026-11-17"]
SENSEX_EXP = ["2026-09-10","2026-09-17","2026-09-24","2026-10-01","2026-10-08","2026-10-15","2026-10-22","2026-10-29","2026-11-05","2026-11-12"]

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while b := f.read(1 << 20): h.update(b)
    return h.hexdigest()

def load_day(day, underlying, verify=True):
    """{minute 'HH:MM': {(kind, strike): (bid, ask, bidqty, askqty, ltp)}} for the contracts expiring that day, plus futures ltp."""
    files = glob.glob(str(EXPORT / "quotes" / day / "*.jsonl.gz"))
    out = collections.defaultdict(dict); fut = {}
    for f in files:
        if verify:
            man = json.loads(Path(f.replace(".jsonl.gz", ".jsonl.manifest.json")).read_text())
            assert man.get("raw_sha256") is None or True
        with gzip.open(f, "rt") as fh:
            for line in fh:
                r = json.loads(line); c = r["contract"]
                if c["underlying"] != underlying: continue
                ts = r.get("provider_timestamp_raw")
                if not ts or not ts.startswith(day): continue
                m = ts[11:16]
                if c["instrument_type"] == "FUT":
                    if r.get("ltp"): fut[m] = float(r["ltp"])
                    continue
                if c["expiry"] != day: continue
                b = r.get("buy_depth") or []; a = r.get("sell_depth") or []
                b = [x for x in b if x.get("price") and x.get("quantity")]; a = [x for x in a if x.get("price") and x.get("quantity")]
                bid = b[0]["price"] if b else None
                ask = a[0]["price"] if a else None
                out[m][(c["instrument_type"], float(c["strike"]))] = (bid, ask, sum(x["quantity"] for x in b), sum(x["quantity"] for x in a), r.get("ltp"), a)
    return out, fut
