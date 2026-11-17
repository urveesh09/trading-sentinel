"""EN15 constituent breadth, signal study (PLAN3.md). Kite 15-minute bars, Jan-Jul 2026 (the Momentum study's Oct 5
snapshot, validated-kite.sqlite, read-only). No minute-level constituent data exists, so this asks only whether
basket breadth leads the index at the 15-minute horizon in the afternoon; it never trades.

Bars are labelled by their start. Event bars start 12:45 .. 14:30; the next bar must exist (start + 15 minutes).
Return of a bar = its close over the previous bar's close. B = (up - down) / present over the frozen basket below
(the NIFTY 50 as of 2026, whichever names the snapshot holds; at least 40 present per bar)."""
from __future__ import annotations
import sqlite3
from collections import defaultdict
from datetime import date
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
DB = HERE.parents[1] / "kite/2026-10-05-momentum-h1/_local/validated-kite.sqlite"
BASKET = ("ADANIENT ADANIPORTS APOLLOHOSP ASIANPAINT AXISBANK BAJAJ-AUTO BAJFINANCE BAJAJFINSV BEL BHARTIARTL CIPLA "
          "COALINDIA DRREDDY EICHERMOT ETERNAL GRASIM HCLTECH HDFCBANK HDFCLIFE HINDALCO HINDUNILVR ICICIBANK INDIGO INFY "
          "ITC JIOFIN JSWSTEEL KOTAKBANK LT M&M MARUTI MAXHEALTH NESTLEIND NTPC ONGC POWERGRID RELIANCE SBILIFE SBIN "
          "SHRIRAMFIN SUNPHARMA TATACONSUM TMPV TATASTEEL TCS TECHM TITAN TRENT ULTRACEMCO WIPRO").split()
INDEX = "NIFTY 50"
EVENT = ("12:45", "13:00", "13:15", "13:30", "13:45", "14:00", "14:15", "14:30")


def load():
    c = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True)
    q = f"SELECT ticker, datetime, close FROM intraday_cache WHERE interval='15minute' AND ticker IN ({','.join('?' * (len(BASKET) + 1))})"
    px = defaultdict(dict)
    for tk, dt, cl in c.execute(q, (*BASKET, INDEX)):
        if cl is not None and cl > 0:
            px[tk][dt[:16]] = float(cl)
    c.close()
    return px


def nxt(stamp):
    h, m = int(stamp[11:13]), int(stamp[14:16]) + 15
    return f"{stamp[:11]}{h + m // 60:02d}:{m % 60:02d}"


def prv(stamp):
    h, m = int(stamp[11:13]), int(stamp[14:16]) - 15
    if m < 0:
        h, m = h - 1, m + 60
    return f"{stamp[:11]}{h:02d}:{m:02d}"


def expiry_days(sessions):
    """NIFTY weekly expiry = Tuesday, or the trading day before it when Tuesday is not a session."""
    s = sorted(sessions); out = set()
    for d in s:
        y, mo, dd = map(int, d.split("-"))
        if date(y, mo, dd).weekday() == 1:
            out.add(d)
    by_week = defaultdict(list)
    for d in s:
        y, mo, dd = map(int, d.split("-")); by_week[date(y, mo, dd).isocalendar()[:2]].append(d)
    for wk, ds in by_week.items():
        if not any(d in out for d in ds):
            earlier = [d for d in ds if date(*map(int, d.split("-"))).weekday() < 1]
            if earlier:
                out.add(max(earlier))
    return out


def events(px):
    idx = px[INDEX]; names = [n for n in BASKET if n in px]
    sessions = sorted({k[:10] for k in idx})
    exp = expiry_days(sessions); rows = []
    for d in sessions:
        for hm in EVENT:
            t = f"{d}T{hm}"; t1, t0 = nxt(t), prv(t)
            if not all(k in idx for k in (t, t1, t0)):
                continue
            ups = downs = present = 0
            for n in names:
                p = px[n]
                if t in p and t0 in p:
                    present += 1; r = p[t] / p[t0] - 1; ups += r > 0; downs += r < 0
            if present < 40:
                continue
            B = (ups - downs) / present
            rows.append(dict(day=d, t=hm, B=round(B, 4), r_idx=idx[t] / idx[t0] - 1, r_next=idx[t1] / idx[t] - 1, expiry=d in exp))
    return rows, len(names), len(sessions), len(exp)


def stats(rows):
    ev = [r for r in rows if abs(r["B"]) >= .6 and r["r_next"] != 0]
    hb = [np.sign(r["r_next"]) == np.sign(r["B"]) for r in ev]
    hi = [np.sign(r["r_next"]) == np.sign(r["r_idx"]) for r in ev if r["r_idx"] != 0]
    dis = [r for r in ev if r["r_idx"] != 0 and np.sign(r["r_idx"]) == -np.sign(r["B"])]
    hd = [np.sign(r["r_next"]) == np.sign(r["B"]) for r in dis]
    return dict(n=len(ev), breadth_hit=round(float(np.mean(hb)), 4) if hb else None, index_only_hit=round(float(np.mean(hi)), 4) if hi else None,
                disagreements=len(dis), disagreement_breadth_hit=round(float(np.mean(hd)), 4) if hd else None,
                mean_next_signed_bp=round(float(np.mean([np.sign(r["B"]) * r["r_next"] for r in ev]) * 1e4), 3) if ev else None)


def score():
    rows, names, sessions, exp = events(load())
    allv, expv = stats(rows), stats([r for r in rows if r["expiry"]])
    ok = allv["n"] >= 100 and allv["breadth_hit"] >= .56 and allv["breadth_hit"] - allv["index_only_hit"] >= .03 \
        and allv["disagreements"] >= 30 and allv["disagreement_breadth_hit"] > .5
    return dict(names_present=names, sessions=sessions, expiry_sessions=exp, bars=len(rows), all=allv, expiry_days=expv,
                verdict="PASS" if ok else "FAIL")


def check():
    rows, names, sessions, exp = events(load())
    assert names >= 45 and sessions >= 120 and exp >= 25, (names, sessions, exp)
    print("CHECK_OK breadth:", names, "basket names present,", sessions, "sessions,", exp, "expiry sessions,", len(rows), "afternoon bars,",
          sum(abs(r["B"]) >= .6 for r in rows), "events")


if __name__ == "__main__":
    check()
