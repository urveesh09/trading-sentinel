"""SN331 (why the breaks failed, and is the reversal tradable?) and SN345 (the reversal with the partner's 5-second
confirmation), PLAN.md frozen at 95287d3f before any number.

One-second data (both windows, seen): SN319's events (30-second breaks of the 3-minute level, sn316/sn319_322.py). The
failure = the first completed 5-second bar closing back inside the level within 300 s of the break. At the failure second f:
the index's move in the reversal direction over +60 / +120 / +300 s; buying the opposite-side opening-ATM option at f + 1
(modelled ask), held 300 s (and 120 s), Rs 3,000 stop, at Rs 0 / 205 / 400; and the split into the option's mid move,
the spread paid and charges. SN345: the next completed 5-second bar closing further in the reversal direction than the
failure bar's close (within 60 s), entering at the next second; same exit and costs.
Minute real-quote archive (41 days, real walked asks / bids): one-minute futures-mid break of the 3-minute range, failure =
a later minute's mid back inside within 5 minutes; buy the opposite ATM option at the next minute's walked ask; sell at the
walked bid 5 and 15 minutes later.
Advance (SN331): the 300-s reversal's net per trade at Rs 205 > 0 on both one-second windows. SN345 passes if its net > 0 at
Rs 205 and Rs 400 on both windows with >= 30 trades."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path[:0] = [str(FNO / "2026-11-16-sn316"), str(FNO / "2026-11-16-sn286"), str(FNO / "2026-11-13-sn101"), str(FNO / "2026-11-16-sn251")]
import sn319_322 as S  # noqa: E402

M, N, LOT = S.M, S.N, S.LOT


def failure(D, e):
    s, lvl, te = e["s"], e["lvl"], e["te"]
    q = (te + 1 + 4) // 5
    while True:
        end = q * 5 + 4
        if end >= N or end > te + 300:
            return None
        if s * (D.c[end] - lvl) < 0:
            return end
        q += 1


def confirm(D, e, f):
    s = e["s"]
    q = (f + 1) // 5
    while True:
        end = q * 5 + 4
        if end >= N or end > f + 60:
            return None
        if end > f and -s * (D.c[end] - D.c[f]) > 0:
            return end + 1
        q += 1


def split(D, side, s0, hold):
    """(option mid move, spread paid, charges) per lot for a buy at s0 held `hold` seconds (no stop), or None."""
    o = D.opt[side]
    k = s0
    while k < min(N, s0 + 6) and not o["ok"][k]:
        k += 1
    if k >= min(N, s0 + 6):
        return None
    j = min(N - 1, k + hold)
    while j > k and not o["ok"][j]:
        j -= 1
    m0, m1 = float(o["c"][k]), float(o["c"][j])
    a, b = S.ask_of(m0), M.bid_of(m1)
    return (m1 - m0) * LOT, ((a - m0) + (m1 - b)) * LOT, M.charges(a, b, LOT)


def study(raw):
    rows = []
    for d in sorted(raw):
        r = raw[d]
        if not all(k in r["series"] and k in r["meta"] for k in ("CE", "PE")):
            continue
        D = S.Day(d, r)
        if D.expiry:
            continue
        for e in S.events(D):
            f = failure(D, e)
            if f is None:
                continue
            side = "PE" if e["s"] > 0 else "CE"
            if abs(D.c[f] - D.strike[side]) > 100:
                continue
            row = {"day": d, "gold_free": D.gold_free, "f_delay": f - e["te"],
                   **{f"rev{h}": float(-e["s"] * (D.c[min(N - 1, f + h)] - D.c[f])) for h in (60, 120, 300)}}
            for st in (0.0, 205.0, 400.0):
                row[f"R300_{int(st)}"] = S.trade(D, side, f + 1, st)
            old = S.HOLD
            S.HOLD = 120
            row["R120_205"] = S.trade(D, side, f + 1, 205.0)
            S.HOLD = old
            c = confirm(D, e, f)
            for st in (205.0, 400.0):
                row[f"C_{int(st)}"] = S.trade(D, side, c, st) if c is not None else None
            sp = split(D, side, f + 1, 300)
            if sp:
                row["mid_move"], row["spread"], row["charges"] = sp
            rows.append(row)
    return rows


def summarise(rows):
    def per(key):
        v = [r[key] for r in rows if r.get(key) is not None]
        return {"n": len(v), "net": round(sum(v)), "per_trade": round(sum(v) / len(v), 1) if v else None}
    out = {"failures": len(rows), "sessions": len({r["day"] for r in rows}),
           "f_delay_median_s": float(np.median([r["f_delay"] for r in rows])) if rows else None}
    for h in (60, 120, 300):
        v = np.array([r[f"rev{h}"] for r in rows])
        out[f"index_reversal_{h}s"] = {"mean_pts": round(float(v.mean()), 2), "median_pts": round(float(np.median(v)), 2),
                                       "share_over_9pts": round(float((v > 9).mean()), 3)} if len(v) else None
    for k in ("R300_0", "R300_205", "R300_400", "R120_205", "C_205", "C_400"):
        out[k] = per(k)
    sp = [r for r in rows if "mid_move" in r]
    out["split_per_lot"] = {"option_mid_move": round(float(np.mean([r["mid_move"] for r in sp])), 1),
                            "spread_paid": round(float(np.mean([r["spread"] for r in sp])), 1),
                            "charges": round(float(np.mean([r["charges"] for r in sp])), 1)} if sp else None
    return out


def archive():
    import qa
    import sn290
    rows = []
    days = sorted(x.stem.replace("quotes-", "") for x in qa.LOCAL.glob("quotes-*.pkl"))
    for day in days:
        try:
            q = qa.load(day)
        except Exception:
            continue
        if day in {k[1] for k in q["opt"] if k[0] == "NIFTY"}:
            continue
        e = sn290.front(q, day)
        fut = qa.front_fut(q, "NIFTY")
        if e is None or fut is None:
            continue
        lot = q["lot"]["NIFTY"]
        mids = np.array([sn290.mid(fut, i) if sn290.mid(fut, i) is not None else np.nan for i in range(qa.NM)])
        last = -99
        for i in range(18, 300):
            w = mids[i - 3:i]
            if np.isnan(w).any() or np.isnan(mids[i]) or i - last < 10:
                continue
            hi, lo = np.max(w), np.min(w)
            s = 1 if mids[i] > hi else (-1 if mids[i] < lo else 0)
            if s == 0:
                continue
            lvl = hi if s > 0 else lo
            fail = next((k for k in range(i + 1, i + 6) if not np.isnan(mids[k]) and s * (mids[k] - lvl) < 0), None)
            if fail is None:
                continue
            last = i
            K = int(round(mids[fail] / 50.0) * 50)
            rec = q["opt"].get(("NIFTY", e, K, "PE" if s > 0 else "CE"))
            if rec is None:
                continue
            a = sn290.real_px(rec, fail + 1, "buy", lot)
            if a is None:
                continue
            row = {"day": day}
            for h in (5, 15):
                b = sn290.real_px(rec, fail + 1 + h, "sell", lot)
                row[f"net{h}_205"] = None if b is None else (b - a) * lot - M.charges(a, b, lot) - 205.0
                row[f"gross{h}"] = None if b is None else (b - a) * lot - M.charges(a, b, lot)
            rows.append(row)
    out = {"events": len(rows), "sessions": len({r["day"] for r in rows})}
    for k in ("gross5", "net5_205", "gross15", "net15_205"):
        v = [r[k] for r in rows if r.get(k) is not None]
        out[k] = {"n": len(v), "per_trade": round(sum(v) / len(v), 1) if v else None}
    return out


if __name__ == "__main__":
    out_path = HERE / "results-sn331-345.json"
    if out_path.exists():
        raise SystemExit("SN331 / SN345 are run once")
    res = {}
    for name, loader in (("dev Apr-Nov 2026", S.dev_days), ("Jan-Apr 2026", S.test_days)):
        rows = study(loader())
        res[name] = {"all": summarise(rows), "gold_free": summarise([r for r in rows if r["gold_free"]])}
        print("SN331", name, json.dumps(res[name]["all"]), flush=True)
    res["archive_real_quotes"] = archive()
    print("SN331 archive", json.dumps(res["archive_real_quotes"]), flush=True)
    w = [res[n]["all"] for n in ("dev Apr-Nov 2026", "Jan-Apr 2026")]
    res["SN331_advance"] = all(x["R300_205"]["per_trade"] is not None and x["R300_205"]["per_trade"] > 0 for x in w)
    res["SN345_verdict"] = "PASS" if all(x["C_205"]["net"] > 0 and x["C_400"]["net"] > 0 and x["C_205"]["n"] >= 30 for x in w) else "FAIL"
    print("SN331 advance", res["SN331_advance"], "SN345", res["SN345_verdict"], flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
