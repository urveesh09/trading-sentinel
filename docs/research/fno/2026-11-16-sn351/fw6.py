"""SN364: the new closing window from Dec 7, 2026 (NSE CAS 2.0), a frozen forward observation (PLAN.md section 2).
Frozen Nov 16, before any CAS session exists. Nothing is scored before 15 qualified CAS sessions; `dev` prints plumbing
only.

NEEDS the tick recorder to run to 15:46 from Dec 7 (SN329's tick_recorder change: in Dev, not deployed on Nov 16). A
session without futures packets at or after 15:44:30 is not qualified, and is counted.

Data: sn301's verified archive copies (_local/archive/<day>, the nightly collect), sessions >= 2026-12-07; only chunks
starting 14:55 - 15:47 are decoded. t = seconds after 09:15:00 IST (15:00 = 20700, 15:30 = 22500).
Per session:
  the front NIFTY future's mid at 15:00:00, 15:30:00, 15:30:30, 15:35:00, 15:40:00, 15:44:30;
  D = the sign of mid(15:30:00) - mid(15:00:00); the 15:30:00 -> 15:44:00 move's sign against D;
  the NIFTY 50 index's last price at or after 15:45:00 if recorded;
  TRADE: one lot of the ATM option (index at 15:31:00) of day.front (expiry > day: next week's on an expiry day) on D's
  side (CE if D > 0), fw2's SN302 execution decided at 15:31:00, held to 15:44:00 (780 s) with fw2's Rs 3,000 stop;
  CONTROL: the other side, same clock and hold.
Amendment B1 (Nov 16, before any CAS session exists; auditor): NIFTY expiry-day sessions fall outside the owner's expiry-day
clock (flat by 13:30), so their rows are kept as research evidence in "expiry_day_rows" and never count toward the 15
sessions, the trades, the controls or the pass rule.
Verdict (once, after 15 qualified non-expiry sessions): PASS = sum net at Rs 205 and Rs 400 > 0, mean net at Rs 205 above CONTROL's,
and > 0 without the best day. Otherwise FAIL. The trade sits after Gold's last exit (15:15), so no wallet conflict.
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
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FNO / "2026-11-16-sn301"))
sys.path.insert(0, str(FNO / "2026-11-16-sn286"))
import fw2  # noqa: E402
import tk  # noqa: E402
import fw5  # noqa: E402

IST = pytz.timezone("Asia/Kolkata")
ARCH = fw5.ARCH
START, N_SESSIONS = "2026-12-07", 15
OUT = HERE / "results-sn364.json"
CLK = {"15:00:00": 20700.0, "15:30:00": 22500.0, "15:30:30": 22530.0, "15:35:00": 22800.0, "15:40:00": 23100.0, "15:44:30": 23370.0}
TDEC, HOLD = 22560.0, 780.0


def _load(folder, names):
    meta = tk.instruments(folder)
    acc = {}
    for n in sorted(names):
        for r in tk.read_chunk(folder / n):
            acc.setdefault(r["token"], []).append(r)
    t0 = IST.localize(dt.datetime.fromisoformat(folder.name[-10:] + "T09:15:00")).timestamp()
    out = {}
    for tok, rows in acc.items():
        rows.sort(key=lambda r: r["recv_ns"])
        ep = np.array([r["recv_ns"] / 1e9 for r in rows])
        d = {"t": ep - t0, "ltp": np.array([r["ltp"] for r in rows]), "lag": ep - np.array([float(r.get("exchange_ts") or 0) for r in rows])}
        if "bids" in rows[0]:
            z5 = [{"price": 0, "qty": 0}] * 5
            bp = np.array([[lv["price"] for lv in r.get("bids", z5)] for r in rows]).T
            ap = np.array([[lv["price"] for lv in r.get("asks", z5)] for r in rows]).T
            bq = np.array([[lv["qty"] for lv in r.get("bids", z5)] for r in rows], dtype=float).T
            aq = np.array([[lv["qty"] for lv in r.get("asks", z5)] for r in rows], dtype=float).T
            d.update(bids=bp, asks=ap, bidq=bq, askq=aq, bid=bp[0], ask=ap[0], bq=bq[0], aq=aq[0], b5=bq.sum(0), a5=aq.sum(0))
        out[tok] = d
    return meta, out


def session(folder):
    folder = Path(folder)
    names = {p.name for p in folder.glob("chunk-*.bin.xz") if "145500" <= p.name[6:12] < "154700"}
    day = fw2.Day(folder, _load(folder, names))
    out = {"day": day.day, "expiry_day": bool(day.expiry_day)}
    f = day.D.get(day.fut)
    if f is None or "bid" not in f or not len(f["t"]) or f["t"][-1] < CLK["15:44:30"]:
        out["skip"] = "recording_ends_before_15:44:30"
        return out
    mids = {k: fw5.mid_at(day, day.fut, t) for k, t in CLK.items()}
    out["mids"] = mids
    if mids["15:00:00"] is None or mids["15:30:00"] is None:
        out["skip"] = "no_mid"
        return out
    D = 1 if mids["15:30:00"] > mids["15:00:00"] else -1
    out["D"] = D
    m44 = fw5.mid_at(day, day.fut, 23340.0)            # 15:44:00
    out["late_move_with_D"] = None if m44 is None else bool((m44 - mids["15:30:00"]) * D > 0)
    ix = day.D.get(day.idx)
    if ix is not None:
        k = np.flatnonzero(ix["t"] >= 23400.0)
        out["index_after_1545"] = float(ix["ltp"][k[-1]]) if len(k) else None
    strike = day.atm(TDEC)
    if strike is None:
        out["skip"] = "no_index"
        return out
    side = "CE" if D > 0 else "PE"
    for name, sd in (("TRADE", side), ("CONTROL", "PE" if side == "CE" else "CE")):
        tok = day.opt.get((day.front, strike, sd))
        out[name] = {"missed": True, "why": "no_contract"} if tok is None else fw2.trade(day, tok, TDEC, HOLD)
        out[name]["side"] = sd
    return out


def verdict():
    if OUT.exists():
        raise SystemExit("SN364 is scored once")
    days = sorted(p.name for p in ARCH.iterdir() if p.is_dir() and p.name >= START) if ARCH.exists() else []
    rows, skipped, expiry_rows = [], [], []
    for d in days:
        r = session(ARCH / d)
        if not r.get("skip") and r.get("expiry_day"):
            expiry_rows.append(r)                       # B1: research evidence only
            continue
        (skipped if r.get("skip") else rows).append(r if not r.get("skip") else {"day": d, "skip": r["skip"]})
        if len(rows) == N_SESSIONS:
            break
    if len(rows) < N_SESSIONS:
        raise SystemExit(f"{len(rows)} of {N_SESSIONS} CAS sessions so far ({len(skipped)} skipped); the verdict waits")
    tr = [r for r in rows if not r["TRADE"].get("missed")]
    n205 = np.array([r["TRADE"]["net205"] for r in tr])
    n400 = np.array([r["TRADE"]["net400"] for r in tr])
    ctl = [r["CONTROL"]["net205"] for r in tr if not r["CONTROL"].get("missed")]
    by_day = {r["day"]: r["TRADE"]["net205"] for r in tr}
    res = {"sessions": len(rows), "skipped": skipped, "trades": len(tr), "net205": round(float(n205.sum())), "net400": round(float(n400.sum())),
           "per_trade205": round(float(n205.mean()), 1) if len(n205) else None, "control_per_trade205": round(float(np.mean(ctl)), 1) if ctl else None,
           "without_best_day": round(float(n205.sum() - max(by_day.values()))) if by_day else None,
           "late_move_with_D_share": round(float(np.mean([r["late_move_with_D"] for r in rows if r.get("late_move_with_D") is not None])), 3)}
    res["expiry_day_rows"] = expiry_rows
    res["verdict"] = "PASS" if (len(tr) and n205.sum() > 0 and n400.sum() > 0 and ctl and n205.mean() > np.mean(ctl) and res["without_best_day"] > 0) else "FAIL"
    res["rows"] = rows
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "dev":
        r = session(Path(sys.argv[2]))
        print(json.dumps({k: r.get(k) for k in ("day", "skip", "D", "late_move_with_D")} | {k: {x: r[k].get(x) for x in ("missed", "why", "side", "status")} for k in ("TRADE", "CONTROL") if k in r}, default=float))
    elif len(sys.argv) > 1 and sys.argv[1] == "verdict":
        verdict()
    else:
        raise SystemExit("usage: fw6.py dev FOLDER | verdict")
