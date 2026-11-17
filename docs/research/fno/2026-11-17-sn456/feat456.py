"""Shared readers for SN456 / SN471 / SN473 / SN475 (PLAN.md, frozen at 83e1b444; the definitions are the plan's).

poi_reports()  {date: {"share", "long_ratio", "total_long", "lm_ist", "valid", "why"}} re-parsed from _local/poi
               (tolerant title date, Indian thousands separators stripped, sum and balance re-checked)
futures()      the sealed futures npz (hash asserted) and per-session near-contract rows:
               {date: {"exp", "o", "h", "l", "c", "v" (390-arrays), "prev_close", "prev_prev_close", "close"}}
features()     per futures session t: y (10:00 -> 11:00, bp), the baseline features, x / z (primary), x2 / z2 (extra lag),
               the availability label of report t-1, and the horizon returns used by SN473
"""
from __future__ import annotations

import csv
import datetime as dt
import email.utils
import hashlib
import io
import json
import re
import sqlite3
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
LOC = HERE / "_local"
POI = LOC / "poi"
FUT_SHA = "d61db7570c1ce4337411c8269c9afd57749faca1cc19159907c874d3d0d24845"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
MON = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DB = "file:C:/Users/Urveesh/sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite?mode=ro"


def _num(s):
    return float(str(s).replace(",", "").strip())


def poi_reports():
    rec = json.loads((POI / "receipts.json").read_text(encoding="utf-8"))
    out = {}
    for d, e in sorted(rec.items()):
        if not e.get("sha256"):
            continue
        p = POI / f"poi-{d.replace('-', '')}.csv"
        b = p.read_bytes()
        assert hashlib.sha256(b).hexdigest() == e["sha256"], d
        text = b.decode("utf-8", errors="replace").replace("\r", "")
        lines = text.split("\n")
        r = {"valid": False, "why": None, "lm_ist": None}
        if e.get("last_modified"):
            r["lm_ist"] = email.utils.parsedate_to_datetime(e["last_modified"]).astimezone(IST)
        m = re.search(r"as on\s+([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2})[\s,\"]*(\d{4})", lines[0].replace('"', ' '))
        try:
            tdate = dt.date(int(m.group(3)), MON[m.group(1).lower()], int(m.group(2))) if m else None
        except (KeyError, ValueError):
            tdate = None
        if tdate != dt.date.fromisoformat(d):
            r["why"] = "title_date"
            out[d] = r
            continue
        rows = {}
        for row in csv.reader(io.StringIO("\n".join(lines[1:]))):
            if row and row[0].strip():
                rows[row[0].strip()] = [c.strip() for c in row]
        try:
            head = rows["Client Type"]
            il, ish = head.index("Future Index Long"), head.index("Future Index Short")
            v = {k: (_num(rows[k][il]), _num(rows[k][ish])) for k in ("Client", "DII", "FII", "Pro", "TOTAL")}
        except (KeyError, ValueError, IndexError):
            r["why"] = "rows"
            out[d] = r
            continue
        if not all(abs(sum(v[k][j] for k in ("Client", "DII", "FII", "Pro")) - v["TOTAL"][j]) < 0.5 for j in (0, 1)):
            r["why"] = "sum"
        elif abs(v["TOTAL"][0] - v["TOTAL"][1]) >= 0.5 or v["TOTAL"][0] <= 0:
            r["why"] = "balance"
        else:
            r.update(valid=True, share=(v["FII"][0] - v["FII"][1]) / v["TOTAL"][0],
                     long_ratio=v["FII"][0] / (v["FII"][0] + v["FII"][1]), total_long=v["TOTAL"][0])
        out[d] = r
    return out


def futures():
    p = LOC / "fut.npz"
    assert hashlib.sha256(p.read_bytes()).hexdigest() == FUT_SHA
    z = np.load(p)
    days, exps, a = [str(x) for x in z["days"]], z["expiries"], z["ohlcv"]
    slot = {}
    for t, d in enumerate(days):
        for b in range(exps.shape[1]):
            if exps[t, b]:
                slot[(d, str(exps[t, b]))] = b
    sess = {}
    for t, d in enumerate(days):
        best = None
        for b in range(exps.shape[1]):
            e = str(exps[t, b])
            if e and e >= d and np.sum(~np.isnan(a[t, b, :, 3])) >= 300:
                if best is None or e < best[0]:
                    best = (e, b)
        if best is None:
            continue
        e, b = best
        c = a[t, b, :, 3]

        def last_close(tt):
            if tt < 0:
                return None
            bb = slot.get((days[tt], e))
            if bb is None:
                return None
            cc = a[tt, bb, :376, 3]
            ok = ~np.isnan(cc)
            return float(cc[ok][-1]) if ok.any() else None
        cc = c[:376]
        ok = ~np.isnan(cc)
        sess[d] = {"exp": e, "o": a[t, b, :, 0], "h": a[t, b, :, 1], "l": a[t, b, :, 2], "c": c, "v": a[t, b, :, 4],
                   "prev_close": last_close(t - 1), "prev_prev_close": last_close(t - 2), "close": float(cc[ok][-1]) if ok.any() else None}
    return days, sess


def at(c, i, back=3):
    for k in range(i, i - back - 1, -1):
        if k >= 0 and not np.isnan(c[k]):
            return float(c[k])
    return None


def option_expiries():
    con = sqlite3.connect(DB, uri=True)
    return {r[0] for r in con.execute("SELECT DISTINCT expiry FROM candles WHERE kind='option' AND underlying='NIFTY'")}


def features(weekly=None):
    rep = poi_reports()
    days, sess = futures()
    weekly = option_expiries() if weekly is None else weekly
    exch = sorted(set(days) | {d for d, r in rep.items() if r["valid"]})
    pos = {d: k for k, d in enumerate(exch)}
    cal = [d for d in days if d in sess]
    ci = {d: k for k, d in enumerate(cal)}
    ret = {}
    for d in cal:
        s = sess[d]
        if s["close"] and s["prev_close"]:
            ret[d] = np.log(s["close"] / s["prev_close"])
    rows = {}
    for t, d in enumerate(cal):
        s = sess[d]
        c = s["c"]
        r = {"day": d, "exp": s["exp"]}
        f44, f104, f74, f359 = at(c, 44), at(c, 104), at(c, 74), at(c, 359)
        o0 = float(s["o"][0]) if not np.isnan(s["o"][0]) else None
        if f44 and f104:
            r["y"] = 1e4 * np.log(f104 / f44)
        if f44 and f74:
            r["y30"] = 1e4 * np.log(f74 / f44)
        if f104 and f359:
            r["late"] = 1e4 * np.log(f359 / f104)
        if o0 and s["prev_close"]:
            r["gap"] = 1e4 * np.log(o0 / s["prev_close"])
        if o0 and f44:
            r["openret"] = 1e4 * np.log(f44 / o0)
            hh, ll = np.nanmax(s["h"][:45]), np.nanmin(s["l"][:45])
            r["range"] = 1e4 * np.log(hh / ll) if ll > 0 else None
        if o0 and s["close"]:
            r["day_oc"] = 1e4 * np.log(s["close"] / o0)
        if s["prev_close"] and s["prev_prev_close"]:
            r["prevret"] = 1e4 * np.log(s["prev_close"] / s["prev_prev_close"])
        r["f44"] = f44
        past = [ret[cal[k]] for k in range(max(0, t - 20), t) if cal[k] in ret]
        r["vol20"] = 1e4 * float(np.std(past, ddof=1)) if len(past) == 20 else None
        r["monthly_expiry"] = float(s["exp"] == d)
        ke = ci.get(s["exp"])
        r["roll"] = float(ke is not None and 0 <= ke - t <= 2)
        r["weekly_expiry"] = float(d in weekly)
        # the participant pair (exchange sessions t-1, t-2, t-3)
        k = pos[d]
        p1, p2, p3 = (exch[k - 1] if k >= 1 else None), (exch[k - 2] if k >= 2 else None), (exch[k - 3] if k >= 3 else None)
        r1, r2, r3 = rep.get(p1), rep.get(p2), rep.get(p3)
        avail = None
        if r1 and r1["valid"]:
            lm = r1["lm_ist"]
            if lm is None or (lm.date() - dt.date.fromisoformat(p1)).days > 7:
                avail = "ASSUMED"
            else:
                avail = "ON_TIME" if lm <= dt.datetime.fromisoformat(d + "T10:00:00").replace(tzinfo=IST) else "LATE"
        r["avail"] = avail if r1 else "MISSING"
        if r1 and r1["valid"] and r2 and r2["valid"]:
            r["x_raw"] = r1["share"] - r2["share"]
            r["L1"] = r1["long_ratio"]
            r["mix_break"] = abs(r1["total_long"] / r2["total_long"] - 1) > 0.30
        if r2 and r2["valid"] and r3 and r3["valid"]:
            r["x2_raw"] = r2["share"] - r3["share"]
        if r1 and r1["valid"]:
            r["L1"] = r1["long_ratio"]
        r["month_end"] = False
        rows[d] = r
    # month-end +/- 2 sessions
    for t, d in enumerate(cal):
        if t + 1 < len(cal) and cal[t + 1][:7] != d[:7]:
            for k in range(max(0, t - 2), min(len(cal), t + 3)):
                rows[cal[k]]["month_end"] = True
    # standardise x on the previous 60 usable values (primary uses only on-time / assumed reports)
    for key, zkey in (("x_raw", "z"), ("x2_raw", "z2")):
        hist = []
        for d in cal:
            r = rows[d]
            ok = key in r and (key == "x2_raw" or r["avail"] in ("ON_TIME", "ASSUMED"))
            if ok and len(hist) >= 60:
                h = np.array(hist[-60:])
                sd = h.std(ddof=1)
                r[zkey] = float((r[key] - h.mean()) / sd) if sd > 0 else None
            if ok:
                hist.append(r[key])
    return cal, rows, rep
