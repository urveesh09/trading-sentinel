"""Round 7 packet work on the read-only TR01 exports (PLAN7.md).

1. The resting-bid fill estimator, version 2 (the audit's F1). Version 1 (pk6.rest, 'through') accepted a later
   packet's last-traded price as a fill witness without checking that the trade happened after our order arrived. A
   fresh quote can carry an old last trade. Version 2 needs post-arrival evidence and reports bounds, never one rate:
     LOWER  definite: after arrival a = s + LAT, a packet whose cumulative volume rose, whose last-trade second lies
            wholly at or after arrival (lt >= a; the stamp has whole-second precision) and whose LTP is strictly
            through our price (<= P - tick); or a fresh post-arrival best ask strictly through (<= P - tick). Price-time
            priority then exhausts every bid at P, ours included: a whole fill.
     QUEUE  the volume-at-bid estimate with post-arrival evidence only: volume rises at packets whose trade may be after
            arrival (lt + 1 > a) and whose LTP <= P, accumulated past the displayed queue ahead at P; whole lots,
            partial fills allowed. Cumulative volume at the latest LTP does not prove every intervening trade was at that
            price, so this is an estimate between the bounds.
     UPPER  possible: any post-arrival trade at <= P (lt + 1 > a, volume rose), or any fresh best ask <= P.
   Fills during the cancellation acknowledgement are labelled PASSIVE_RACE. Version 1's results stay as published.
2. EN58 recomputed with version 2 (the erratum), EN71's packet latency curve, EN75's synthetic-forward pilot and
   EN78's basis pilot (pilots: code and coverage, no verdict).
"""
from __future__ import annotations
import json, math, sys
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-18-expiry-en56"))
import pk6  # noqa: E402

L6, L4, E = pk6.L6, pk6.L4, pk6.E
LAT, FRESH, TICK_OPT = pk6.LAT, pk6.FRESH, .05
BOUNDS = ("LOWER", "QUEUE", "UPPER")


def lt_ist(bk, k):
    """Last-trade second (IST seconds since midnight) of packet k, or nan when the packet has none."""
    v = int(bk.a["lt"][k])
    return float(pk6.ist(v)) if v > 0 else math.nan


def rest2(bk, s, P, units, until, bound, lot=65):
    """Version-2 resting buy at P sent at s (arrival s + LAT). Returns (fill_time, filled_units) or None."""
    k0 = bk.at(s)
    if k0 is None:
        return None
    a = s + LAT
    q0 = int(bk.a["bq"][k0, 0]) if abs(bk.a["bp"][k0, 0] - P) < 1e-9 else 0
    if bk.a["bp"][k0, 0] > P + 1e-9:                     # bids above ours stand ahead of us too
        q0 += int(sum(q for p_, q in zip(bk.a["bp"][k0], bk.a["bq"][k0]) if np.isfinite(p_) and p_ > P + 1e-9))
    prev_v = int(bk.a["vol"][k0]); seen = 0
    for k in bk.after(s, until):
        v = int(bk.a["vol"][k]); dv = v - prev_v; prev_v = v
        if bk.s[k] < a - 1e-9:                            # received before our order could rest: volume baseline only
            continue
        lt = lt_ist(bk, k); ltp = float(bk.a["ltp"][k]); ask = float(bk.a["ap"][k, 0])
        sure_after = np.isfinite(lt) and lt >= a - 1e-9
        maybe_after = np.isfinite(lt) and lt + 1. > a + 1e-9
        if bound == "LOWER":
            if (dv > 0 and sure_after and ltp <= P - TICK_OPT + 1e-9) or ask <= P - TICK_OPT + 1e-9:
                return bk.s[k], units
        elif bound == "UPPER":
            if (dv > 0 and maybe_after and ltp <= P + 1e-9) or ask <= P + 1e-9:
                return bk.s[k], units
        else:
            if dv > 0 and maybe_after and ltp <= P + 1e-9:
                seen += dv
                got = min(units, max(0, seen - q0)) // lot * lot
                if got >= units:
                    return bk.s[k], units
            if (dv > 0 and sure_after and ltp <= P - TICK_OPT + 1e-9) or ask <= P - TICK_OPT + 1e-9:
                return bk.s[k], units                    # a definite fill is a fill under every estimate
    if bound == "QUEUE":
        got = min(units, max(0, seen - q0)) // lot * lot
        if got:
            return until, got                            # a partial whole-lot fill by the deadline
    return None


def _passive2(ob, s, B0, units, until, est, adv_winner):
    if est in BOUNDS:
        return rest2(ob, s, B0, units, until, est)
    lo, up = rest2(ob, s, B0, units, until, "LOWER"), rest2(ob, s, B0, units, until, "UPPER")
    if lo is not None:                                   # ADVERSARIAL: definite fills fill; ambiguous ones fill only losers
        return lo
    return None if (up is None or adv_winner) else up


def policy2(ob, fb, ib, s, d, units, limit, atr0, ustop, pol, est):
    """pk6.policy with the version-2 estimator (identical control flow; partial QUEUE fills are kept as partial)."""
    k0 = ob.at(s)
    if k0 is None:
        return dict(filled=False, how="STALE_QUOTE")
    B0, A0 = float(ob.a["bp"][k0, 0]), float(ob.a["ap"][k0, 0])
    mid0 = (A0 + B0) / 2
    k180 = ob.at(s + 180); adv_win = (k180 is not None and ob.mid(k180) > B0)
    intact = lambda tt: np.isfinite(pk6._idx(ib, tt)) and d * (pk6._idx(ib, tt) - ustop) > 0
    if pol == "P3":
        f0, f10 = pk6._fmid(fb, s), pk6._fmid(fb, s - 10)
        go = np.isfinite([f0, f10]).all() and d * (f0 - f10) > 0 and ob.micro(k0) > mid0
        pol = "P1" if go else "P3w"
    if pol == "P1":
        m = pk6.market(ob, s, "BUY", units, limit)
        return dict(filled=m is not None, t=m[0] if m else None, price=m[1] if m else None, how="MARKET", units=units)
    wait = 60. if pol == "P0" else 3.
    end = s + LAT + wait
    if pol == "P3w":
        f0 = pk6._fmid(fb, s)
        for k in fb.after(s + LAT, end):
            if np.isfinite(f0) and d * (fb.mid(k) - f0) <= -.10 * atr0:
                end = fb.s[k]; break
    got = _passive2(ob, s, B0, units, end + LAT, est, adv_win)
    if got is not None:
        tf, u = got
        return dict(filled=True, t=tf, price=B0, how="PASSIVE" if tf <= end else "PASSIVE_RACE", units=u)
    s_fb = end + LAT
    if pol == "P0":
        ok = np.isfinite([pk6._fmid(fb, s_fb), pk6._fmid(fb, s)]).all() and d * (pk6._fmid(fb, s_fb) - pk6._fmid(fb, s)) > 0
    else:
        ok = np.isfinite([pk6._fmid(fb, s_fb), pk6._fmid(fb, s_fb - 10)]).all() and d * (pk6._fmid(fb, s_fb) - pk6._fmid(fb, s_fb - 10)) > 0
    if not (ok and intact(s_fb)):
        return dict(filled=False, how="MISSED")
    m = pk6.market(ob, s_fb, "BUY", units, limit)
    return dict(filled=m is not None, t=m[0] if m else None, price=m[1] if m else None, how="FALLBACK" if m else "MISSED", units=units)


def outcome2(ob, s, r, hold=480.):
    """pk6.outcome on the filled units (a partial QUEUE fill is marked on what it bought)."""
    u = r.get("units") or 0
    return pk6.outcome(ob, s, u if r.get("filled") else 65, r, hold)


def intents_and_grid(T1, P):
    """The EN55 intent(s) and the 5-minute grid exactly as pk6.en58 forms them."""
    idx, fut, opts = pk6.tokens(); ib, fb = pk6.Book(P[idx]), pk6.Book(P[fut["token"]])
    books_ = {k: pk6.Book(P[v]) for k, v in opts.items() if v in P}
    L6.LOG_INTENTS = []
    L6.run_day6(T1, L6.ARMS["EN55"], "ordinary", 30000., L6.budget_of(L6.ARMS["EN55"]), details=True)
    intents = L6.LOG_INTENTS; L6.LOG_INTENTS = None
    jobs = []
    for x in intents:
        i, d, j = x["i"], x["d"], x["j"]; s = float(T1.minute[i]) * 60; K = float(T1.strikes[j]); kind = "CE" if T1.kinds[j] == 1 else "PE"
        a0 = float(T1.features[10][i, 4]); ob = books_.get((K, kind)); k0 = ob.at(s) if ob else None
        units = x["lots"] * L4.NIFTY.lot
        wa = ob.walk(k0, "BUY", units, 1e9) if k0 is not None else None
        limit = min(x["limit"], E.down(1.04 * wa)) if wa else x["limit"]
        jobs.append(("EN55", s, d, K, kind, units, limit, a0, float(T1.close[i]) - d * 2 * a0))
    for m in range(780, 901, 5):
        i = L6.at(T1, m)
        if i >= T1.n or T1.minute[i] != m:
            continue
        s = m * 60.; c = float(T1.close[i]); a0 = float(T1.features[10][i, 4])
        for d in (1, -1):
            kind = "CE" if d > 0 else "PE"
            cand = sorted([K for (K, kd) in books_ if kd == kind and d * (K - c) > 0], key=lambda K: d * K)
            for K in cand:
                ob = books_[(K, kind)]; k0 = ob.at(s)
                if k0 is None or not 5 <= ob.a["ap"][k0, 0] <= 20:
                    continue
                jobs.append(("GRID", s, d, K, kind, L4.NIFTY.lot, E.down(1.04 * float(ob.a["ap"][k0, 0])), a0, c - d * 2 * a0))
                break
    return intents, jobs, books_, fb, ib


def en58_v2(T1, P):
    """EN58's rows under version 1 (pk6, unchanged) and version 2 (LOWER / QUEUE / UPPER / ADVERSARIAL)."""
    intents, jobs, books_, fb, ib = intents_and_grid(T1, P)
    rows = []
    for tag, s, d, K, kind, units, limit, a0, ustop in jobs:
        ob = books_[(K, kind)]
        for pol in ("P0", "P2", "P3"):
            for est in ("v1_through", "v1_volume", "LOWER", "QUEUE", "UPPER", "ADVERSARIAL"):
                if est.startswith("v1_"):
                    r = pk6.policy(ob, fb, ib, s, d, units, limit, a0, ustop, pol, est[3:]); r["units"] = units
                else:
                    r = policy2(ob, fb, ib, s, d, units, limit, a0, ustop, pol, est)
                rows.append(dict(outcome2(ob, s, r), tag=tag, s=s, d=d, K=K, kind=kind, policy=pol, est=est))
        r = policy2(ob, fb, ib, s, d, units, limit, a0, ustop, "P1", "LOWER")
        rows.append(dict(outcome2(ob, s, r), tag=tag, s=s, d=d, K=K, kind=kind, policy="P1", est="MARKET"))
    return intents, rows


def _nm(xs):
    v = [float(x) for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return (round(float(np.mean(v)), 4) if v else None, len(v))


def summarize58(rows):
    g = defaultdict(list)
    for r in rows:
        g[(r["tag"], r["policy"], r["est"])].append(r)
    out = {}
    for (tag, pol, est), rs in sorted(g.items()):
        fl = [r for r in rs if r.get("filled")]
        out[f"{tag}|{pol}|{est}"] = dict(n=len(rs), filled=len(fl), how=dict(Counter(r["how"] for r in rs)),
                                         partial=sum(1 for r in fl if r.get("units", 0) < 65), cost_vs_mid=_nm([r.get("cost_vs_mid") for r in fl]),
                                         fill60=_nm([r.get("fill60") for r in fl]), fill180=_nm([r.get("fill180") for r in fl]),
                                         net_8min_sum=round(sum(r["net"] for r in rs), 2))
    # changed tickets: P0 grid rows whose fill status or time differs between v1 'through' and each v2 estimate
    key = lambda r: (r["tag"], r["s"], r["K"], r["kind"])
    v1 = {key(r): r for r in rows if r["policy"] == "P0" and r["est"] == "v1_through"}
    changed = []
    for r in rows:
        if r["policy"] != "P0" or r["est"] not in BOUNDS:
            continue
        o = v1[key(r)]
        if bool(o.get("filled")) != bool(r.get("filled")) or (o.get("filled") and abs((o.get("t") or 0) - (r.get("t") or 0)) > 1e-6) or o.get("how") != r.get("how"):
            changed.append(dict(tag=r["tag"], s=r["s"], K=r["K"], kind=r["kind"], est=r["est"], v1=[o.get("how"), o.get("t"), o.get("net")],
                                v2=[r.get("how"), r.get("t"), r.get("net")]))
    return out, changed


def synthetic_checks():
    """The audit's false-fill case and its mirror images, on synthetic packets (counts only)."""
    epoch = 1794871800

    def book(ltp, lt_off, vol, ask=10.1):
        raw = dict(recv=np.array([epoch, epoch + 2], np.int64) * 10 ** 9, exch=np.array([epoch, epoch + 2]),
                   lt=np.array([epoch + lt_off[0], epoch + lt_off[1]]), ltp=np.array(ltp, float), vol=np.array(vol),
                   oi=np.array([0, 0]), bp=np.array([[10.] * 5, [min(10., ask - .05)] * 5]), ap=np.array([[10.1] * 5, [ask] * 5]),
                   bq=np.full((2, 5), 100), aq=np.full((2, 5), 100))
        return pk6.Book(raw)
    out = {}
    b = book([9.9, 9.9], (-60, -60), [100, 100]); s = float(b.s[0])
    out["stale_trade_v1_through_fills"] = pk6.rest(b, s, 10., 65, s + 10, "through") is not None
    out["stale_trade_v2"] = {e: rest2(b, s, 10., 65, s + 10, e) is not None for e in BOUNDS}
    b = book([10.05, 9.9], (-60, 2), [100, 300]); s = float(b.s[0])
    out["fresh_tradethrough_v2"] = {e: rest2(b, s, 10., 65, s + 10, e) is not None for e in BOUNDS}
    b = book([10.05, 10.0], (-60, 2), [100, 130]); s = float(b.s[0])
    out["fresh_trade_at_price_small_v2"] = {e: rest2(b, s, 10., 65, s + 10, e) is not None for e in BOUNDS}
    b = book([10.05, 10.05], (-60, -60), [100, 100], ask=10.0); s = float(b.s[0])
    out["ask_touch_v2"] = {e: rest2(b, s, 10., 65, s + 10, e) is not None for e in BOUNDS}
    assert out["stale_trade_v1_through_fills"] and not any(out["stale_trade_v2"].values())
    assert all(out["fresh_tradethrough_v2"].values())
    assert out["fresh_trade_at_price_small_v2"] == dict(LOWER=False, QUEUE=False, UPPER=True)
    assert out["ask_touch_v2"] == dict(LOWER=False, QUEUE=False, UPPER=True)
    return out


def erratum():
    P = pk6.decode(); T1 = pk6.tape(); L6.KEEP6.append(T1)
    syn = synthetic_checks()
    intents, rows = en58_v2(T1, P)
    agg, changed = summarize58(rows)
    v1 = json.loads((HERE.parent / "2026-11-18-expiry-en56" / "results6.json").read_text())["diagnostics"]["EN58"]["policies"]
    same_v1 = {k: (agg.get(f"{k.split('|')[0]}|{k.split('|')[1]}|v1_{k.split('|')[2]}", {}).get("filled") == v["filled"])
               for k, v in v1.items() if k.split("|")[2] in ("through", "volume") and k.split("|")[1] != "P1"}
    assert all(same_v1.values()), same_v1
    return dict(synthetic=syn, intents=[dict(minute=int(T1.minute[x["i"]]), d=x["d"], lots=x["lots"]) for x in intents],
                v1_reproduced=same_v1, policies=agg, changed_p0_tickets=changed)


if __name__ == "__main__":
    out = erratum()
    (HERE / "erratum-en58-v2.json").write_text(json.dumps(out, indent=1, default=float) + "\n", encoding="utf-8")
    for k, v in out["policies"].items():
        if k.split("|")[1] in ("P0", "P1"):
            print(k, v["n"], v["filled"], v["how"], v["fill180"], v["net_8min_sum"])
    print("changed P0 tickets:", len(out["changed_p0_tickets"]))


# ---------------------------------------------------------------- pre-registration data facts (no rupees)
def fut_spread(day=pk6.DAY):
    """Median quoted spread of the NIFTY front future on the recorded session (fresh valid packets, 13:00-14:30)."""
    P = pk6.decode(day); idx, fut, opts = pk6.tokens(day); b = pk6.Book(P[fut["token"]])
    sp = [b.a["ap"][k, 0] - b.a["bp"][k, 0] for k in b.after(46800., 52200.)]
    return dict(day=day, packets=len(sp), median=round(float(np.median(sp)), 4), p90=round(float(np.percentile(sp, 90)), 4))


def oi_timing(day=pk6.DAY):
    """Does a Breeze minute candle's OI (bar k, labelled by start) equal the recorder's OI at that bar's end, or only a
    later one? For each (strike, side, bar): the first recorder second whose OI equals the candle's OI."""
    import sqlite3
    P = pk6.decode(day); idx, fut, opts = pk6.tokens(day)
    c = sqlite3.connect(pk6.BREEZE.resolve().as_uri() + "?mode=ro", uri=True)
    rows = c.execute("SELECT strike, opt, datetime, oi FROM candles WHERE kind='option' AND underlying='NIFTY' AND expiry=? AND interval='1minute' "
                     "AND datetime BETWEEN ? AND ?", (day, day + " 12:00:00", day + " 15:29:00")).fetchall()
    c.close()
    lag = Counter(); n = 0
    for K, o, dt, oi in rows:
        tok = opts.get((float(K), o))
        if tok is None or tok not in P or not oi:
            continue
        b = pk6.Book(P[tok]); end = ((int(dt[11:13]) * 60 + int(dt[14:16])) + 1) * 60.   # bar end, IST seconds
        e = b.e; ois = b.a["oi"]
        at_end = np.flatnonzero(e <= end)
        if not len(at_end):
            continue
        n += 1
        if int(ois[at_end[-1]]) == int(oi):
            lag["equals_oi_at_bar_end"] += 1; continue
        later = np.flatnonzero((e > end) & (ois == int(oi)))
        earlier = np.flatnonzero((e <= end) & (ois == int(oi)))
        if len(later) and (not len(earlier)):
            dt_ = e[later[0]] - end
            lag["first_seen_after_end_" + ("<=60s" if dt_ <= 60 else "<=180s" if dt_ <= 180 else ">180s")] += 1
        elif len(earlier):
            lag["seen_before_end_not_last"] += 1
        else:
            lag["never_seen"] += 1
    return dict(day=day, candles=n, **dict(lag))


def facts():
    cat = pk6.catalogue(); sx = [r for r in cat if r["underlying"] == "SENSEX" and r["type"] == "FUT"]
    return dict(nifty_future_spread=fut_spread(), oi_timing=oi_timing(), sensex_future_in_recorder=len(sx))


# ---------------------------------------------------------------- EN75 / EN78 packet pilots (Nov 17: code and coverage)
def _grid(lo=46800, hi=52200, step=1.):
    return np.arange(lo, hi, step)


def en75_pilot(day=pk6.DAY):
    """Per second 13:00-14:30: parity intervals from fresh executable quotes at the 5 strikes nearest the future mid,
    the prior-20-minute median basis removed; up/down seconds need >= 3 strikes outside the future's own quoted
    bid/ask + the basis MAD; an event is the first of 3 successive such seconds. Future mid move toward it at 30/60/180 s."""
    P = pk6.decode(day); idx, fut, opts = pk6.tokens(day); fb = pk6.Book(P[fut["token"]])
    books_ = {k: pk6.Book(P[v]) for k, v in opts.items() if v in P}; ks = sorted({k for k, _ in books_})
    S = _grid(46800 - 1200); base = np.full(len(S), np.nan); obs = []
    for n, s in enumerate(S):
        kf = fb.at(s)
        if kf is None:
            obs.append(None); continue
        fm = fb.mid(kf); fbid, fask = float(fb.a["bp"][kf, 0]), float(fb.a["ap"][kf, 0]); rows = []
        for K in sorted(ks, key=lambda k: abs(k - fm))[:5]:
            c, p = books_.get((K, "CE")), books_.get((K, "PE"))
            kc, kp = (c.at(s) if c else None), (p.at(s) if p else None)
            if kc is None or kp is None:
                continue
            rows.append((K + c.a["bp"][kc, 0] - p.a["ap"][kp, 0], K + c.a["ap"][kc, 0] - p.a["bp"][kp, 0]))
        if len(rows) >= 3:
            base[n] = float(np.median([(lo + hi) / 2 - fm for lo, hi in rows]))
        obs.append((fm, fbid, fask, rows))
    up = np.zeros(len(S), bool); dn = np.zeros(len(S), bool); cov = 0; tot = 0
    for n, s in enumerate(S):
        if s < 46800:
            continue
        tot += 1; o = obs[n]
        if o is None or len(o[3]) < 3:
            continue
        cov += 1; w = base[max(0, n - 1200):n]; w = w[np.isfinite(w)]
        if len(w) < 600:
            continue
        med = float(np.median(w)); mad = float(np.median(np.abs(w - med))); fm, fbid, fask, rows = o
        up[n] = sum(lo - med > fask + mad for lo, hi in rows) >= 3; dn[n] = sum(hi - med < fbid - mad for lo, hi in rows) >= 3
    ev = []
    for n in range(3, len(S)):
        for flag, d in ((up, 1), (dn, -1)):
            if flag[n] and flag[n - 1] and flag[n - 2] and not flag[n - 3]:
                e = dict(s=float(S[n]), d=d)
                k0 = fb.at(S[n])
                for h in (30, 60, 180):
                    k = fb.at(S[n] + h)
                    e[f"dF{h}"] = round(d * (fb.mid(k) - fb.mid(k0)), 2) if k is not None and k0 is not None else None
                ev.append(e)
    tw = lambda h: [e[f"dF{h}"] > 0 for e in ev if e.get(f"dF{h}") is not None]
    return dict(day=day, pilot=True, seconds=tot, seconds_with_3_fresh_pairs=cov, coverage=round(cov / max(1, tot), 4), events=len(ev),
                toward30=round(float(np.mean(tw(30))), 3) if tw(30) else None, toward180=round(float(np.mean(tw(180))), 3) if tw(180) else None,
                note="one recorded session: code and coverage only, no verdict")


def en78_pilot(day=pk6.DAY):
    """Per 2 seconds 13:00-14:30: basis = future mid - index; prior-60-minute median and MAD; events as EN78 (3 MAD and
    3 quoted future spreads on 3 successive observations); the 8-minute repair split into cash and future moves."""
    P = pk6.decode(day); idx, fut, opts = pk6.tokens(day); fb = pk6.Book(P[fut["token"]]); ib = pk6.Book(P[idx])
    S = _grid(46800 - 3600, 52200, 2.); b = np.full(len(S), np.nan); X = np.full(len(S), np.nan); Fm = np.full(len(S), np.nan); sp = np.full(len(S), np.nan)
    for n, s in enumerate(S):
        kf = fb.at(s); x = pk6._idx(ib, s)
        if kf is None or not np.isfinite(x):
            continue
        Fm[n] = fb.mid(kf); X[n] = x; b[n] = Fm[n] - x; sp[n] = fb.a["ap"][kf, 0] - fb.a["bp"][kf, 0]
    ev = []; armed = {1: True, -1: True}; e = np.full(len(S), np.nan); s_ = np.full(len(S), np.nan)
    for n in range(1800, len(S)):
        w = b[n - 1800:n]; w = w[np.isfinite(w)]
        if len(w) >= 1200 and np.isfinite(b[n]):
            m = float(np.median(w)); md = float(np.median(np.abs(w - m)))
            if md > 0:
                e[n] = b[n] - m; s_[n] = md
    for n in range(1802, len(S)):
        for sg in (1, -1):
            if np.isfinite(e[n]) and abs(e[n]) < s_[n]:
                armed[sg] = True
            big = lambda k: np.isfinite(e[k]) and sg * e[k] > max(3 * s_[k], 3 * (sp[k] if np.isfinite(sp[k]) else 4.4))
            if armed[sg] and big(n) and big(n - 1) and big(n - 2):
                armed[sg] = False; k = min(len(S) - 1, n + 240)
                if np.isfinite([X[k], X[n], Fm[k], Fm[n]]).all():
                    dX, dF = X[k] - X[n], Fm[k] - Fm[n]; rep = sg * (dX - dF)
                    ev.append(dict(s=float(S[n]), sg=sg, e=round(float(e[n]), 2), repair=round(float(rep), 2), dX=round(float(dX), 2), dF=round(float(dF), 2)))
    return dict(day=day, pilot=True, observations=int(np.isfinite(b[1800:]).sum()), events=len(ev),
                cash_led=round(float(np.mean([x["dX"] * x["sg"] > -x["dF"] * x["sg"] for x in ev])), 3) if ev else None, examples=ev[:5],
                note="one recorded session: code and coverage only, no verdict")
