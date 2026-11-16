"""SN386: signed option pressure from tick packets, frozen forward on the recorder before any forward session (PLAN.md
section 1). Nothing is scored before the verdict; `dev` prints plumbing only.

Per recorder session (sn301's nightly archive), decoding only the front future and the front-weekly CE / PE within
+-250 points of the 09:16 index (memory):
  signing  each option packet whose cumulative volume rose: BUY if its last price >= the previous packet's ask, SELL if
           <= the previous packet's bid, else UNSIGNED (kept out of the signed flow, counted). Sequencing by receipt.
  flow(t)  over ATM +- 2 strikes (ATM from the index at t): signed CE lots - signed PE lots in (t - 600 s, t]
  unsigned the same with every volume increment counted as +1 (control)
Calibration from EARLIER forward sessions only (>= 5): s = the std of flow at every whole minute 09:30 - 14:30.
Event (first per date, from the 6th session on): |flow| >= 1.5 s at a whole minute 09:30 - 14:30 while the future's mid
moved < 0.05% over the last 10 minutes. Prediction: flow > 0 -> up.
Measured: the future's mid 15 minutes later in the predicted direction (basis points); the front ATM option on the
predicted side through fw2's SN302 execution decided at the event, held 15 minutes, Rs 3,000 stop, with SN381's cash
rule (walked cost + charges <= Rs 15,000, else INADMISSIBLE).
Controls: UNSIGNED (the same rule on unsigned volume), SHIFTED (the event from the flow 30 minutes earlier), COIN
(same clock, seeded side).
Verdict once after 20 qualified non-expiry sessions (SN300a's list; the first 5 calibrate): PASS = follow-through > 0
with t > 2, option per-event net > 0 at Rs 205 and Rs 400, above every control, > 0 without the best date; otherwise FAIL
(or INSUFFICIENT below 10 events). Reported: the signable share of volume, events by date.
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FNO / "2026-11-16-sn351"))
sys.path.insert(0, str(FNO / "2026-11-16-sn301"))
sys.path.insert(0, str(FNO / "2026-11-16-sn286"))
import fw7a  # noqa: E402

OUT = HERE / "results-sn386-fw8.json"
CAL, N_SESS, HOLD = 5, 20, 900.0


def load_light(folder):
    import fw2
    import tk
    folder = Path(folder)
    meta = tk.instruments(folder)
    day = folder.name[-10:]
    futs = sorted((m["expiry"], t) for t, m in meta.items() if m["type"] == "FUT" and m["underlying"] == "NIFTY" and m["expiry"] > day)
    idx = next((t for t, m in meta.items() if m["tradingsymbol"] == "NIFTY 50"), None)
    exps = sorted({m["expiry"] for m in meta.values() if m["underlying"] == "NIFTY" and m["type"] in ("CE", "PE") and m["expiry"] > day})
    if not futs or idx is None or not exps:
        return None
    front = exps[0]
    acc, open_px = {}, None
    keep = {futs[0][1], idx}
    t0 = fw2.IST.localize(dt.datetime.fromisoformat(day + "T09:15:00")).timestamp()
    for ch in sorted(folder.glob("chunk-*.bin.xz")):
        if not ("091500" <= ch.name[6:12] < "143600"):
            continue
        for r in tk.read_chunk(ch):
            tok = r["token"]
            if open_px is None and tok == idx and r["recv_ns"] / 1e9 - t0 >= 60:
                open_px = r["ltp"]
                keep |= {t for t, m in meta.items() if m.get("expiry") == front and m["type"] in ("CE", "PE") and abs(m["strike"] - open_px) <= 250}
            if tok in keep:
                acc.setdefault(tok, []).append(r)
    return meta, acc, t0, front, futs[0][1], idx


def flows(meta, acc, t0, front):
    """Per option token: arrays of (t, signed lots, unsigned lots), and the signable share."""
    out, signed_v, all_v = {}, 0.0, 0.0
    for tok, rows in acc.items():
        m = meta.get(tok, {})
        if m.get("type") not in ("CE", "PE") or m.get("expiry") != front:
            continue
        rows.sort(key=lambda r: r["recv_ns"])
        lot = float(m.get("lot_size") or 65)
        ev, pv, pb, pa = [], None, None, None
        for r in rows:
            v = r.get("volume")
            bids, asks = r.get("bids"), r.get("asks")
            if v is not None and pv is not None and v > pv and pb is not None:
                dv = (v - pv) / lot
                sgn = 1.0 if r["ltp"] >= pa > 0 else -1.0 if 0 < r["ltp"] <= pb else 0.0
                ev.append((r["recv_ns"] / 1e9 - t0, sgn * dv, dv))
                all_v += dv
                signed_v += dv if sgn != 0 else 0.0
            pv = v if v is not None else pv
            if bids and asks and bids[0]["price"] > 0 and asks[0]["price"] > 0:
                pb, pa = bids[0]["price"], asks[0]["price"]
        out[tok] = (m["type"], int(round(m["strike"])), np.array(ev) if ev else np.zeros((0, 3)))
    return out, (signed_v / all_v if all_v else None)


def flow_at(fl, t, atm, col):
    tot = 0.0
    for typ, k, ev in fl.values():
        if abs(k - atm) > 100 or not len(ev):
            continue
        sel = ev[(ev[:, 0] > t - 600) & (ev[:, 0] <= t)]
        if len(sel):
            tot += (1 if typ == "CE" else -1) * float(sel[:, col].sum())
    return tot


def minute_series(folder):
    got = load_light(folder)
    if got is None:
        return None
    meta, acc, t0, front, fut, idx = got
    fl, share = flows(meta, acc, t0, front)
    fr = sorted(acc.get(fut, []), key=lambda r: r["recv_ns"])
    ft = np.array([r["recv_ns"] / 1e9 - t0 for r in fr])
    fm = np.array([0.5 * (r["bids"][0]["price"] + r["asks"][0]["price"]) if r.get("bids") and r["bids"][0]["price"] > 0 else r["ltp"] for r in fr])
    ir = sorted(acc.get(idx, []), key=lambda r: r["recv_ns"])
    it = np.array([r["recv_ns"] / 1e9 - t0 for r in ir])
    il = np.array([r["ltp"] for r in ir])
    rows = []
    for t in np.arange(900.0, 19500.0 + 1, 60.0):                 # 09:30 .. 14:40
        k = np.searchsorted(it, t, side="right") - 1
        j, j0 = np.searchsorted(ft, t, side="right") - 1, np.searchsorted(ft, t - 600, side="right") - 1
        if k < 0 or j < 0 or j0 < 0:
            continue
        atm = int(round(il[k] / 50.0) * 50)
        rows.append({"t": float(t), "atm": atm, "fut": float(fm[j]), "r10": float(fm[j] / fm[j0] - 1.0),
                     "signed": flow_at(fl, t, atm, 1), "unsigned": flow_at(fl, t, atm, 2)})
    return {"day": folder.name[-10:], "rows": rows, "signable_share": share, "ft": ft, "fm": fm}


def evaluate(folder, ms, s_signed, s_unsigned):
    out = {"day": ms["day"]}

    def fut_at(t):
        j = np.searchsorted(ms["ft"], t, side="right") - 1
        return None if j < 0 else float(ms["fm"][j])

    def first(key, s, shift=0.0):
        rr = {r["t"]: r for r in ms["rows"]}
        for r in ms["rows"]:
            if r["t"] > 19500.0 - 1 or abs(r["r10"]) >= 0.0005:
                continue
            src = rr.get(r["t"] - shift) if shift else r
            if src is None:
                continue
            if s > 0 and abs(src[key]) >= 1.5 * s:
                return r, (1 if src[key] > 0 else -1)
        return None, None
    for name, key, s, shift in (("SIGNED", "signed", s_signed, 0.0), ("UNSIGNED", "unsigned", s_unsigned, 0.0), ("SHIFTED", "signed", s_signed, 1800.0)):
        r, sgn = first(key, s, shift)
        if r is None:
            out[name] = None
            continue
        f0, f1 = fut_at(r["t"]), fut_at(r["t"] + 900.0)
        follow = None if f0 is None or f1 is None else 1e4 * (f1 / f0 - 1.0) * sgn
        out[name] = {"t": r["t"], "dir": sgn, "follow_bp": follow, "trade": option_trade(folder, r, sgn)}
    if out.get("SIGNED"):
        sgn = random.Random(f"sn386-{ms['day']}").choice((-1, 1))
        r = next(x for x in ms["rows"] if x["t"] == out["SIGNED"]["t"])
        f0, f1 = fut_at(r["t"]), fut_at(r["t"] + 900.0)
        out["COIN"] = {"t": r["t"], "dir": sgn, "follow_bp": None if f0 is None or f1 is None else 1e4 * (f1 / f0 - 1.0) * sgn, "trade": option_trade(folder, r, sgn)}
    return out


_DAYS = {}


def load_filtered(folder):
    """fw2's array format for the front future, the index and the front-weekly options within +-300 of the open (memory)."""
    import fw2
    import tk
    folder = Path(folder)
    meta = tk.instruments(folder)
    day = folder.name[-10:]
    exps = sorted({m["expiry"] for m in meta.values() if m["underlying"] == "NIFTY" and m["type"] in ("CE", "PE") and m["expiry"] > day})
    idx = next((t for t, m in meta.items() if m["tradingsymbol"] == "NIFTY 50"), None)
    acc, ref = {}, None
    for ch in sorted(folder.glob("chunk-*.bin.xz")):
        if not ("090000" <= ch.name[6:12] < "145000"):
            continue
        for r in tk.read_chunk(ch):
            m = meta.get(r["token"], {})
            if r["token"] == idx and ref is None and r.get("ltp"):
                ref = r["ltp"]
            if m.get("type") == "FUT" or r["token"] == idx or (exps and m.get("expiry") == exps[0] and ref is not None and abs(m.get("strike", 0) - ref) <= 300):
                acc.setdefault(r["token"], []).append(r)
    t0 = fw2.IST.localize(dt.datetime.fromisoformat(day + "T09:15:00")).timestamp()
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


def option_trade(folder, r, sgn):
    import fw2
    key = str(folder)
    if key not in _DAYS:
        _DAYS.clear()
        _DAYS[key] = fw2.Day(folder, load_filtered(folder))
    day = _DAYS[key]
    tok = day.opt.get((day.front, r["atm"], "CE" if sgn > 0 else "PE"))
    if tok is None:
        return {"state": "INADMISSIBLE"}
    d = day.D.get(tok)
    k = int(np.searchsorted(d["t"], r["t"], side="right")) - 1
    while k >= 0 and not d["ok"][k]:
        k -= 1
    if k < 0:
        return {"state": "MISSED"}
    ok, px, cost = fw7a.admissible(list(d["asks"][:, k]), list(d["askq"][:, k]), day.lot, fw7a.charges_buy)
    if not ok:
        return {"state": "INADMISSIBLE"}
    cap = fw7a.order_cap(float(d["ask"][k]), day.lot, fw7a.charges_buy)
    t = fw2.trade(day, tok, r["t"], HOLD, cap=cap)
    t["state"] = fw7a.state_of(t)
    return t


def verdict():
    import fw5
    if OUT.exists():
        raise SystemExit("fw8 is scored once")
    days = sorted(p.name for p in fw5.ARCH.iterdir() if p.is_dir() and p.name >= fw5.START) if fw5.ARCH.exists() else []
    series = []
    for d in days:
        rc = fw5.REC / f"{d}.json"
        q = json.loads(rc.read_text(encoding="utf-8")).get("qualify", {}) if rc.exists() else {}
        if not q.get("ok") or q.get("expiry_day"):
            continue
        ms = minute_series(fw5.ARCH / d)
        if ms is not None and ms["rows"]:
            series.append(ms)
        if len(series) == N_SESS:
            break
    if len(series) < N_SESS:
        raise SystemExit(f"{len(series)} of {N_SESS} sessions; the verdict waits")
    evs = []
    for k, ms in enumerate(series):
        if k < CAL:
            continue
        prior = [r for m in series[:k] for r in m["rows"]]
        s1, s2 = float(np.std([r["signed"] for r in prior])), float(np.std([r["unsigned"] for r in prior]))
        evs.append(evaluate(fw5.ARCH / ms["day"], ms, s1, s2))
    res = {"sessions": [m["day"] for m in series], "signable_share": [m["signable_share"] for m in series]}
    for arm in ("SIGNED", "UNSIGNED", "SHIFTED", "COIN"):
        e = [x[arm] for x in evs if x.get(arm)]
        fb = [x["follow_bp"] for x in e if x["follow_bp"] is not None]
        tr = [x["trade"] for x in e if x["trade"].get("state") in ("FILLED", "UNRESOLVED")]
        n205 = [t["net205"] for t in tr]
        res[arm] = {"events": len(e), "follow_mean_bp": round(float(np.mean(fb)), 2) if fb else None,
                    "follow_t": round(float(np.mean(fb) / (np.std(fb, ddof=1) / np.sqrt(len(fb)))), 2) if len(fb) > 2 and np.std(fb) > 0 else None,
                    "fills": len(tr), "net205": round(float(np.mean(n205)), 1) if tr else None, "net400": round(float(np.mean([t["net400"] for t in tr])), 1) if tr else None,
                    "without_best": round(float((sum(n205) - max(n205)) / max(1, len(n205) - 1)), 1) if len(n205) > 1 else None}
    a = res["SIGNED"]
    if a["events"] < 10:
        a["verdict"] = "INSUFFICIENT"
    else:
        ok = ((a["follow_t"] or 0) > 2 and (a["net205"] or -1) > 0 and (a["net400"] or -1) > 0 and (a["without_best"] or -1) > 0
              and all((a["net205"] or -1) > (res[c]["net205"] if res[c]["net205"] is not None else -1e9) for c in ("UNSIGNED", "SHIFTED", "COIN")))
        a["verdict"] = "PASS" if ok else "FAIL"
    res["events"] = evs
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "events"}, indent=1, default=float))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "dev":
        ms = minute_series(Path(sys.argv[2]))
        fl = [abs(r["signed"]) for r in ms["rows"]] if ms else []
        print(json.dumps({"minutes": len(ms["rows"]) if ms else 0, "signable_share": None if not ms else round(ms["signable_share"] or 0, 3),
                          "median_abs_signed_lots": round(float(np.median(fl)), 1) if fl else None}))
    elif len(sys.argv) > 1 and sys.argv[1] == "verdict":
        verdict()
    else:
        raise SystemExit("usage: fw8.py dev FOLDER | verdict")
