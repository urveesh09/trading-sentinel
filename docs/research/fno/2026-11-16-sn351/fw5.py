"""SN353 (c): the forward queue-pressure arm, and the SN353 (b) post-hoc mid-gap watch, on recorder sessions (PLAN.md
section 1 with amendment A2). Frozen before the first forward session (Nov 17) is scored. Nothing here is scored before
the verdict; `dev` prints plumbing only.

Data: sn301's verified archive copies (_local/archive/<day>, made by the nightly `fwd2.py collect`); only the chunks that
start before 10:20 IST are decoded (memory). Sessions: from Nov 17, NIFTY weekly expiry days skipped, in order; the verdict
uses the first 20 sessions with an archive copy whose SN300a receipt says qualified (the SN300a window) and whose near
future has pre-open quantities.

Per session (times are receipt times; t = seconds after 09:15:00 IST):
  I(c) = (buy - sell) / (buy + sell) of the future's last packet at or before c, c = 09:05:00 and 09:06:00.
  C0 = the packet's `close` (previous close); IEP = its `open` at 09:06 (indicative price); A = the matched price: the
  last price of the first packet after 09:08:00 and before 09:15:00 whose last-trade time is on this day's pre-open,
  else the first last price at or after 09:15:00 (counted); g = A / C0 - 1.
  ARM (queue pressure): persistent = same sign at both clocks and |I| >= 0.20 at both; accepted = the futures mid at
  09:16:00 is on I's side of A; abstain if that mid is already >= 0.15% beyond A in I's direction. Trade: the front-weekly
  ATM option (index at 09:16:00) on I's side, fw2's SN302 execution decided at 09:16:00, held 20 minutes with fw2's
  Rs 3,000 stop; 5 and 60 minutes as diagnostics. Controls on the same sessions: OPPOSITE (the other side) and PRICE_CONT
  (the side of g).
  WATCH_MID (post-hoc in SN353 (b), registered here for unseen sessions only): every session with 0.2% <= |g| <= 0.5%,
  the side of g, the same execution and 20-minute hold.
  Diagnostics: I(09:06) and the futures mid return 09:16:00 -> 09:36:00 (rank correlation at the verdict); the IEP gap
  at 09:06 against g.
Verdict (once): ARM PASS = >= 15 trades, sum net at Rs 205 and Rs 400 > 0, mean net at Rs 205 above OPPOSITE's and
PRICE_CONT's on the same sessions, and > 0 without the best day; < 15 trades = INSUFFICIENT (the arm keeps collecting);
otherwise FAIL. WATCH_MID: the same test against its own opposite side.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pytz

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn301"))
sys.path.insert(0, str(FNO / "2026-11-16-sn286"))
import fw2  # noqa: E402
import tk  # noqa: E402

IST = pytz.timezone("Asia/Kolkata")
ARCH = FNO / "2026-11-16-sn301" / "_local" / "archive"
REC = FNO / "2026-11-16-sn301" / "_local" / "receipts"
START, N_SESSIONS = "2026-11-17", 20
OUT = HERE / "results-sn353c.json"
T05, T06, TDEC = -600.0, -540.0, 60.0
THR, CAP = 0.20, 0.0015
HOLD, DIAG = 1200.0, (300.0, 3600.0)


def load_open(folder, until="102000"):
    folder = Path(folder)
    meta = tk.instruments(folder)
    acc = {}
    for ch in sorted(folder.glob("chunk-*.bin.xz")):
        if ch.name[6:12] >= until:
            continue
        for r in tk.read_chunk(ch):
            acc.setdefault(r["token"], []).append(r)
    t0 = IST.localize(dt.datetime.fromisoformat(folder.name[-10:] + "T09:15:00")).timestamp()
    out = {}
    for tok, rows in acc.items():
        rows.sort(key=lambda r: r["recv_ns"])
        ep = np.array([r["recv_ns"] / 1e9 for r in rows])
        d = {"t": ep - t0, "ltp": np.array([r["ltp"] for r in rows]),
             "lag": ep - np.array([float(r.get("exchange_ts") or 0) for r in rows])}
        if "bids" in rows[0]:
            z5 = [{"price": 0, "qty": 0}] * 5
            bp = np.array([[lv["price"] for lv in r.get("bids", z5)] for r in rows]).T
            ap = np.array([[lv["price"] for lv in r.get("asks", z5)] for r in rows]).T
            bq = np.array([[lv["qty"] for lv in r.get("bids", z5)] for r in rows], dtype=float).T
            aq = np.array([[lv["qty"] for lv in r.get("asks", z5)] for r in rows], dtype=float).T
            d.update(bids=bp, asks=ap, bidq=bq, askq=aq, bid=bp[0], ask=ap[0], bq=bq[0], aq=aq[0], b5=bq.sum(0), a5=aq.sum(0))
        if meta.get(tok, {}).get("type") == "FUT":
            for f in ("buy_qty", "sell_qty", "open", "close", "volume", "last_trade_ts"):
                d[f] = np.array([float(r.get(f) or 0) for r in rows])
        out[tok] = d
    return meta, out


def last_at(d, t, lo=-900.0):
    k = int(np.searchsorted(d["t"], t, side="right")) - 1
    return k if k >= 0 and d["t"][k] >= lo else None


def mid_at(day, tok, t):
    d = day.D[tok]
    k = int(np.searchsorted(d["t"], t, side="right")) - 1
    while k >= 0 and not d["ok"][k]:
        k -= 1
    return None if k < 0 else 0.5 * (d["bid"][k] + d["ask"][k])


def trade_set(day, side, strike):
    tok = day.opt.get((day.front, strike, side))
    if tok is None:
        return {"missed": True, "why": "no_contract"}
    row = fw2.trade(day, tok, TDEC, HOLD)
    if not row.get("missed"):
        row["diag"] = {str(int(h)): fw2.trade(day, tok, TDEC, h).get("net205") for h in DIAG}
    row["side"], row["strike"] = side, strike
    return row


def session(folder):
    day = fw2.Day(folder, load_open(folder))
    out = {"day": day.day, "expiry_day": bool(day.expiry_day)}
    if day.expiry_day:
        out["skip"] = "expiry_day"
        return out
    f = day.D.get(day.fut)
    if f is None or "buy_qty" not in f:
        out["skip"] = "no_future"
        return out
    k5, k6 = last_at(f, T05), last_at(f, T06)
    if k5 is None or k6 is None or f["buy_qty"][k6] + f["sell_qty"][k6] <= 0 or f["buy_qty"][k5] + f["sell_qty"][k5] <= 0:
        out["skip"] = "no_preopen_quantities"
        return out
    I5 = (f["buy_qty"][k5] - f["sell_qty"][k5]) / (f["buy_qty"][k5] + f["sell_qty"][k5])
    I6 = (f["buy_qty"][k6] - f["sell_qty"][k6]) / (f["buy_qty"][k6] + f["sell_qty"][k6])
    C0, IEP = float(f["close"][k6]), float(f["open"][k6])
    pre0 = IST.localize(dt.datetime.fromisoformat(day.day + "T09:00:00")).timestamp()
    A, how = None, None
    for k in range(len(f["t"])):
        if -420.0 <= f["t"][k] < 0 and f["last_trade_ts"][k] >= pre0:
            A, how = float(f["ltp"][k]), "match_packet"
            break
    if A is None:
        k = int(np.searchsorted(f["t"], 0.0, side="left"))
        if k < len(f["t"]):
            A, how = float(f["ltp"][k]), "first_0915"
    if A is None or C0 <= 0:
        out["skip"] = "no_auction_price"
        return out
    g = A / C0 - 1.0
    m16, m36 = mid_at(day, day.fut, TDEC), mid_at(day, day.fut, TDEC + 1200.0)
    strike = day.atm(TDEC)
    out.update(I05=round(float(I5), 4), I06=round(float(I6), 4), C0=C0, IEP06=IEP, A=A, how=how, g=g, iep_gap=IEP / C0 - 1.0,
               mid0916=m16, fut_ret_20m=None if (m16 is None or m36 is None) else m36 / m16 - 1.0, strike=strike)
    sgn = 1 if I6 > 0 else -1
    persistent = (np.sign(I5) == np.sign(I6)) and abs(I5) >= THR and abs(I6) >= THR
    accepted = m16 is not None and (m16 - A) * sgn > 0
    capped = m16 is not None and (m16 - A) / A * sgn >= CAP
    out.update(persistent=bool(persistent), accepted=bool(accepted), capped=bool(capped))
    if strike is not None and persistent and accepted and not capped:
        side = "CE" if sgn > 0 else "PE"
        opp = "PE" if side == "CE" else "CE"
        pside = "CE" if g > 0 else "PE"
        out["ARM"] = trade_set(day, side, strike)
        out["OPPOSITE"] = trade_set(day, opp, strike)
        out["PRICE_CONT"] = trade_set(day, pside, strike)
    if strike is not None and 0.002 <= abs(g) <= 0.005:
        pside = "CE" if g > 0 else "PE"
        out["WATCH_MID"] = trade_set(day, pside, strike)
        out["WATCH_MID_OPP"] = trade_set(day, "PE" if pside == "CE" else "CE", strike)
    return out


def plumbing(r):
    """What dev prints: no rupees."""
    keep = {k: r.get(k) for k in ("day", "skip", "I05", "I06", "C0", "IEP06", "A", "how", "persistent", "accepted", "capped", "strike")}
    for k in ("ARM", "OPPOSITE", "PRICE_CONT", "WATCH_MID", "WATCH_MID_OPP"):
        if k in r:
            keep[k] = {x: r[k].get(x) for x in ("missed", "why", "side", "latency", "status")}
    keep["g_pct"] = None if r.get("g") is None else round(100 * r["g"], 3)
    return keep


def judge(rows, arm, controls):
    tr = [(r["day"], r[arm]) for r in rows if arm in r and not r[arm].get("missed")]
    n = len(tr)
    out = {"trades": n, "decisions": sum(1 for r in rows if arm in r), "missed": sum(1 for r in rows if arm in r and r[arm].get("missed"))}
    if n == 0:
        out["verdict"] = "INSUFFICIENT"
        return out
    n205 = np.array([x["net205"] for _d, x in tr])
    n400 = np.array([x["net400"] for _d, x in tr])
    by_day = {}
    for d, x in tr:
        by_day[d] = by_day.get(d, 0.0) + x["net205"]
    out.update(net205=round(float(n205.sum())), net400=round(float(n400.sum())), per_trade205=round(float(n205.mean()), 1),
               without_best_day=round(float(n205.sum() - max(by_day.values()))),
               diag={h: round(float(np.nanmean([x["diag"].get(h) if x["diag"].get(h) is not None else np.nan for _d, x in tr])), 1) for h in ("300", "3600")})
    beats = {}
    for c in controls:
        cs = [r[c]["net205"] for r in rows if arm in r and not r[arm].get("missed") and c in r and not r[c].get("missed")]
        beats[c] = {"n": len(cs), "per_trade205": round(float(np.mean(cs)), 1) if cs else None,
                    "beaten": bool(cs) and float(n205.mean()) > float(np.mean(cs))}
    out["controls"] = beats
    if n < 15:
        out["verdict"] = "INSUFFICIENT"
    else:
        ok = n205.sum() > 0 and n400.sum() > 0 and all(b["beaten"] for b in beats.values()) and out["without_best_day"] > 0
        out["verdict"] = "PASS" if ok else "FAIL"
    return out


def spearman(x, y):
    if len(x) < 3:
        return None
    rx, ry = np.argsort(np.argsort(x)), np.argsort(np.argsort(y))
    return round(float(np.corrcoef(rx, ry)[0, 1]), 3)


def verdict():
    if OUT.exists():
        raise SystemExit("SN353 (c) is scored once")
    days = sorted(p.name for p in ARCH.iterdir() if p.is_dir() and p.name >= START) if ARCH.exists() else []
    rows = []
    for d in days:
        rc = REC / f"{d}.json"
        q = json.loads(rc.read_text(encoding="utf-8")).get("qualify", {}) if rc.exists() else {}
        if not q.get("ok"):
            continue
        r = session(ARCH / d)
        if r.get("skip"):
            continue
        rows.append(r)
        if len(rows) == N_SESSIONS:
            break
    if len(rows) < N_SESSIONS:
        raise SystemExit(f"{len(rows)} of {N_SESSIONS} sessions so far; the verdict waits")
    res = {"sessions": [r["day"] for r in rows], "ARM": judge(rows, "ARM", ("OPPOSITE", "PRICE_CONT")),
           "WATCH_MID": judge(rows, "WATCH_MID", ("WATCH_MID_OPP",)),
           "persistent_sessions": sum(r["persistent"] for r in rows),
           "I06_abs_median": round(float(np.median([abs(r["I06"]) for r in rows])), 4)}
    pairs = [(r["I06"], r["fut_ret_20m"]) for r in rows if r.get("fut_ret_20m") is not None]
    res["rank_corr_I06_vs_fut_20m"] = spearman([a for a, _b in pairs], [b for _a, b in pairs])
    res["rank_corr_iep_gap_vs_g"] = spearman([r["iep_gap"] for r in rows], [r["g"] for r in rows])
    res["rows"] = rows
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "dev":
        print(json.dumps(plumbing(session(Path(sys.argv[2]))), default=float))
    elif len(sys.argv) > 1 and sys.argv[1] == "verdict":
        verdict()
    else:
        raise SystemExit("usage: fw5.py dev FOLDER | verdict")
