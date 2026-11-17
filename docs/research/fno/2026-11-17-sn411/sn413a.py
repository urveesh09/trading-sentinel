"""SN413 A: which other index can take the wallet - an end-of-day screen (PLAN.md section 1, frozen at e5cc95b7; details
fixed here before any number). Public NSE reports only; no credentials, no account data.

  fetch   every NSE session Aug 3 - Nov 13, 2026 (weekdays minus market_calendar's 2026 holidays): the F&O bhavcopy
          (BhavCopy_NSE_FO_0_0_0_<YYYYMMDD>_F_0000.csv.zip) and the official index closes (ind_close_all_<DDMMYYYY>.csv)
          from nsearchives.nseindia.com, saved under _local/nse with their sha256 in _local/nse/fetch.json; a missing
          file is recorded, never guessed
  score   for BANKNIFTY, FINNIFTY, MIDCPNIFTY and NIFTY (reference): the front expiry (first strictly after the date) and
          the next; the strike nearest the official close (ATM), 1-ITM and 2-ITM for CE and PE (listed strikes);
          PASS = contracts traded > 0 and close premium x the dated lot (NewBrdLotQty) <= Rs 15,000 (before fees).
          Reported by sessions-to-expiry bucket (1-5, 6-10, 11-20, > 20), for the front and next expiry, on NIFTY's
          expiry days (a NIFTY option expiring that day), with the median trades executed and open interest; and the
          share of dates where at least one of ATM / 1-ITM passes on BOTH sides (a direction-free trade is affordable).
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
NSE = HERE / "_local" / "nse"
OUT = HERE / "results-sn413a.json"
sys.path.insert(0, str(HERE.parent / "2026-11-17-sn396"))
import fw9a  # noqa: E402  (the 2026 NSE holiday list, checked against market_calendar in test_fw9a)

LO, HI = dt.date(2026, 8, 3), dt.date(2026, 11, 13)
INDEX = {"NIFTY": "Nifty 50", "BANKNIFTY": "Nifty Bank", "FINNIFTY": "Nifty Financial Services", "MIDCPNIFTY": "NIFTY Midcap Select"}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
ROOM = 15000.0


def sessions():
    d, out = LO, []
    while d <= HI:
        if d.weekday() < 5 and d.isoformat() not in fw9a.HOLIDAYS:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def fetch():
    NSE.mkdir(parents=True, exist_ok=True)
    log = json.loads((NSE / "fetch.json").read_text(encoding="utf-8")) if (NSE / "fetch.json").exists() else {}
    for d in sessions():
        for name, url in ((f"fo-{d:%Y%m%d}.zip", f"https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"),
                          (f"idx-{d:%Y%m%d}.csv", f"https://nsearchives.nseindia.com/content/indices/ind_close_all_{d:%d%m%Y}.csv")):
            if name in log and log[name].get("sha256"):
                continue
            p = NSE / name
            r = subprocess.run(["curl", "-s", "-m", "60", "-A", UA, "-o", str(p), "-w", "%{http_code}", url], capture_output=True, text=True)
            ok = r.stdout.strip() == "200" and p.exists() and p.stat().st_size > 1000
            log[name] = {"url": url, "http": r.stdout.strip(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest() if ok else None}
            if not ok and p.exists():
                p.unlink()
        (NSE / "fetch.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
    print(sum(1 for v in log.values() if v["sha256"]), "files,", sum(1 for v in log.values() if not v["sha256"]), "missing")


def load(d):
    fo, ix = NSE / f"fo-{d:%Y%m%d}.zip", NSE / f"idx-{d:%Y%m%d}.csv"
    if not fo.exists() or not ix.exists():
        return None, None
    closes = {}
    for r in csv.DictReader(io.StringIO(ix.read_text(encoding="utf-8", errors="replace"))):
        try:
            closes[r["Index Name"].strip()] = float(r["Closing Index Value"])
        except (KeyError, ValueError):
            pass
    z = zipfile.ZipFile(fo)
    rows = list(csv.DictReader(io.StringIO(z.read(z.namelist()[0]).decode("utf-8", errors="replace"))))
    return rows, closes


def bucket(n):
    return "1-5" if n <= 5 else "6-10" if n <= 10 else "11-20" if n <= 20 else ">20"


def score():
    if OUT.exists():
        raise SystemExit("SN413 A is scored once")
    cal = sessions()
    obs, missing = [], []
    nifty_exp = set()
    for d in cal:
        rows, closes = load(d)
        if rows is None:
            missing.append(d.isoformat())
            continue
        for und in INDEX:
            opts = [r for r in rows if r.get("TckrSymb") == und and r.get("FinInstrmTp") == "IDO"]
            exps = sorted({r["XpryDt"] for r in opts})
            if und == "NIFTY" and exps and exps[0] == d.isoformat():
                nifty_exp.add(d.isoformat())
            later = [e for e in exps if e > d.isoformat()]
            S = closes.get(INDEX[und])
            if S is None or not later:
                continue
            for rank, e in enumerate(later[:2]):
                ed = dt.date.fromisoformat(e)
                dte = sum(1 for x in cal if d < x <= ed) if ed <= HI else len([x for x in cal if x > d]) + max(0, np.busday_count(HI + dt.timedelta(days=1), ed + dt.timedelta(days=1)))
                ks = sorted({float(r["StrkPric"]) for r in opts if r["XpryDt"] == e})
                if not ks:
                    continue
                atm = min(ks, key=lambda k: abs(k - S))
                ai = ks.index(atm)
                for side in ("CE", "PE"):
                    for dep in (0, 1, 2):
                        j = ai - dep if side == "CE" else ai + dep
                        if not 0 <= j < len(ks):
                            continue
                        r = next((x for x in opts if x["XpryDt"] == e and float(x["StrkPric"]) == ks[j] and x["OptnTp"] == side), None)
                        if r is None:
                            continue
                        lot = int(float(r.get("NewBrdLotQty") or 0) or 0)
                        px = float(r.get("ClsPric") or 0)
                        vol = float(r.get("TtlTradgVol") or 0)
                        obs.append({"day": d.isoformat(), "und": und, "rank": "front" if rank == 0 else "next", "expiry": e, "dte": int(dte), "side": side,
                                    "depth": dep, "lot": lot, "close": px, "cost": px * lot, "traded": vol, "trades": float(r.get("TtlNbOfTxsExctd") or 0),
                                    "oi": float(r.get("OpnIntrst") or 0), "pass": bool(vol > 0 and lot > 0 and px * lot <= ROOM)})
    res = {"sessions": len(cal), "missing_files": missing, "nifty_expiry_days": sorted(nifty_exp)}
    for und in INDEX:
        u = [o for o in obs if o["und"] == und]
        lots = sorted({o["lot"] for o in u})
        block = {"lots_seen": lots, "observations": len(u)}
        for rank in ("front", "next"):
            for dep in (0, 1, 2):
                xs = [o for o in u if o["rank"] == rank and o["depth"] == dep]
                block[f"{rank} depth{dep}"] = {"n": len(xs), "pass_share": round(float(np.mean([o["pass"] for o in xs])), 3) if xs else None,
                                               "median_cost": round(float(np.median([o["cost"] for o in xs])), 0) if xs else None,
                                               "median_trades": round(float(np.median([o["trades"] for o in xs])), 0) if xs else None,
                                               "by_dte": {b: round(float(np.mean([o["pass"] for o in xs if bucket(o["dte"]) == b])), 3)
                                                          for b in ("1-5", "6-10", "11-20", ">20") if any(bucket(o["dte"]) == b for o in xs)}}
        both, both_ne = [], []
        for d in sorted({o["day"] for o in u}):
            f = [o for o in u if o["day"] == d and o["rank"] == "front" and o["depth"] in (0, 1)]
            ok = any(o["pass"] for o in f if o["side"] == "CE") and any(o["pass"] for o in f if o["side"] == "PE")
            both.append(ok)
            if d in nifty_exp:
                both_ne.append(ok)
        block["dates_both_sides_affordable_front_atm_or_1itm"] = round(float(np.mean(both)), 3) if both else None
        block["on_nifty_expiry_days"] = {"days": len(both_ne), "share": round(float(np.mean(both_ne)), 3) if both_ne else None}
        res[und] = block
    res["observations"] = obs
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "observations"}, indent=1))


if __name__ == "__main__":
    {"fetch": fetch, "score": score}[sys.argv[1]]()
