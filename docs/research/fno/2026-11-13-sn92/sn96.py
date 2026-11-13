"""SN96 - what the stocks inside NIFTY say (2026 only, 15-minute bars; PLAN.md).

Panel: today's NIFTY 50 names (a pilot: membership is today's, not point-in-time). Weights: non-negative least squares of
NIFTY's 15-minute returns on the names' returns over January 2026 only. Data: the Oct 5 Kite snapshot (Jan 1 - Jul 31)
and Production's read-only 15-minute export (Aug 11 - Nov 6, bars to 14:30), both already on disk, nothing downloaded.
1. Information test: development Feb-Apr, test May-Oct (chronological), next-30 / next-15 minute index return, index-only
   features vs + component features; residual breadth's correlation with a day-clustered bootstrap interval.
2. Trading test on causal Gold-free days, scored once on May-Oct: `broad` (participation agrees with the day's move)
   and `diverge` (the index is up but the stocks are not, and the mirror), against the same rules built from the
   index's own block return, and a random side.
3. Exit description: Gold v5's 2026 trades, leaving when weighted agreement is against the position for 2 blocks."""
from __future__ import annotations

import csv
import gzip
import itertools
import json
import random
import sys
from pathlib import Path
from urllib.parse import quote

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402

M = C.M
SN96_NAMES = ("ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV",
              "BEL", "BHARTIARTL", "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL", "GRASIM", "HCLTECH", "HDFCBANK",
              "HDFCLIFE", "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDIGO", "INFY", "ITC", "JIOFIN", "JSWSTEEL", "KOTAKBANK",
              "LT", "M&M", "MARUTI", "MAXHEALTH", "NESTLEIND", "NTPC", "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SBIN",
              "SHRIRAMFIN", "SUNPHARMA", "TATACONSUM", "TMPV", "TATASTEEL", "TCS", "TECHM", "TITAN", "TRENT", "ULTRACEMCO",
              "WIPRO")
FIN = {"AXISBANK", "BAJFINANCE", "BAJAJFINSV", "HDFCBANK", "HDFCLIFE", "ICICIBANK", "JIOFIN", "KOTAKBANK", "SBILIFE", "SBIN",
       "SHRIRAMFIN"}
RAW = M.ROOT / "docs/research/kite/2026-10-05-momentum-h1/_local/raw"
PROD = M.ROOT / "docs/research/simulation/2026-11-08-momentum-m01/_local/prod_15m_aug_nov.csv.gz"
NB = 25
KS = range(2, 19)          # block ends 10:00 .. 14:00 (block k ends at minute 15k+14)
DEV = ("2026-02-01", "2026-04-30")
TEST_FROM = "2026-05-01"


def _k(stamp):
    hh, mm = int(stamp[11:13]), int(stamp[14:16])
    return (hh * 60 + mm - 555) // 15


def load_bars():
    bars = {s: {} for s in SN96_NAMES}
    for s in SN96_NAMES:
        for part in ("2026-01-01_2026-07-19", "2026-07-20_2026-07-31"):
            p = RAW / f"{quote(s, safe='-')}_15minute_{part}.json"
            if not p.exists():
                continue
            for st, o, h, l, c, v in json.loads(p.read_text(encoding="utf-8"))["data"]["candles"]:
                k = _k(st)
                if 0 <= k < NB:
                    bars[s].setdefault(st[:10], np.full((2, NB), np.nan))[:, k] = (o, c)
    want = set(SN96_NAMES)
    with gzip.open(PROD, "rt", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["kind"] != "I" or r["ticker"] not in want:
                continue
            st = r["stamp"]
            k = _k(st)
            if 0 <= k < NB:
                bars[r["ticker"]].setdefault(st[:10], np.full((2, NB), np.nan))[:, k] = (float(r["open"]), float(r["close"]))
    return bars


def nnls(A, y, iters=20000):
    w = np.zeros(A.shape[1])
    lip = np.linalg.eigvalsh(A.T @ A).max()
    AtA, Aty = A.T @ A, A.T @ y
    for _ in range(iters):
        w = np.maximum(0.0, w - (AtA @ w - Aty) / lip)
    return w


def build():
    Ys = C.years()
    sess = Ys["2026"].sessions
    bars = load_bars()
    names = [s for s in SN96_NAMES if bars[s]]
    days = sorted(d for d in sess if sum(d in bars[s] for s in names) >= 45)
    # weights from January only
    A, y = [], []
    for d in days:
        if d >= "2026-02-01":
            break
        c = sess[d].F["c"]
        for k in range(1, 22):
            rr = []
            for s in names:
                b = bars[s].get(d)
                rr.append(b[1, k] / b[1, k - 1] - 1 if b is not None and not np.isnan(b[1, k]) and not np.isnan(b[1, k - 1]) else 0.0)
            A.append(rr)
            y.append(c[15 * k + 14] / c[15 * (k - 1) + 14] - 1)
    w = nnls(np.array(A), np.array(y))
    W = dict(zip(names, w))
    rows = []
    for d in days:
        if d < "2026-02-01":
            continue
        S = sess[d]
        c, o = S.F["c"], S.F["o"]
        hist_br = []
        for k in KS:
            m = 15 * k + 14
            r, cum, ws = [], [], []
            for s in names:
                b = bars[s].get(d)
                if b is None or np.isnan(b[1, k]) or np.isnan(b[1, k - 1]) or np.isnan(b[0, 0]):
                    continue
                r.append(b[1, k] / b[1, k - 1] - 1)
                cum.append(b[1, k] / b[0, 0] - 1)
                ws.append((s, W[s]))
            if len(r) < 45:
                hist_br.append(np.nan)
                continue
            r, cum = np.array(r), np.array(cum)
            wv = np.array([x for _s, x in ws])
            fin = np.array([s in FIN for s, _x in ws])
            gross = float((wv * np.abs(r)).sum())
            br = float(np.mean(np.sign(r)))
            hist_br.append(br)
            rows.append({"day": d, "k": k, "m": m, "idx_r": float(c[m] / c[m - 15] - 1), "idx_cum": float(c[m] / o[0] - 1),
                         "br": br, "br_open": float(np.mean(np.sign(cum))),
                         "agree": float((wv * r).sum() / gross) if gross > 1e-5 else 0.0,
                         "bank": float(((wv * r)[fin].sum() - (wv * r)[~fin].sum()) / gross) if gross > 1e-5 else 0.0,
                         "top": float((wv * np.abs(r)).max() / gross) if gross > 1e-5 else 0.0,
                         "pers": float(np.nanmean(hist_br[-3:])),
                         "y30": float(c[min(m + 30, 374)] / c[m] - 1), "y15": float(c[min(m + 15, 374)] / c[m] - 1),
                         "weight_cover": float(wv.sum() / max(1e-12, sum(W.values())))})
    return rows, W, names


BASE_F = ("idx_r", "idx_cum")
COMP_F = ("br", "br_open", "agree", "bank", "top", "pers")


def ols(X, y):
    X1 = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(X1, y, rcond=None)
    return beta


def pred(beta, X):
    return np.column_stack([np.ones(len(X)), X]) @ beta


def info_test(rows):
    dev = [r for r in rows if DEV[0] <= r["day"] <= DEV[1]]
    test = [r for r in rows if r["day"] >= TEST_FROM]
    out = {"dev_obs": len(dev), "test_obs": len(test), "dev_days": len({r["day"] for r in dev}),
           "test_days": len({r["day"] for r in test})}
    rng = np.random.default_rng(96)
    tdays = sorted({r["day"] for r in test})
    by_day = {d: [i for i, r in enumerate(test) if r["day"] == d] for d in tdays}
    for tgt in ("y30", "y15"):
        Xb = np.array([[r[f] for f in BASE_F] for r in dev]); Xf = np.array([[r[f] for f in BASE_F + COMP_F] for r in dev])
        yd = np.array([r[tgt] for r in dev])
        bb, bf = ols(Xb, yd), ols(Xf, yd)
        Tb = np.array([[r[f] for f in BASE_F] for r in test]); Tf = np.array([[r[f] for f in BASE_F + COMP_F] for r in test])
        yt = np.array([r[tgt] for r in test])
        eb, ef = (pred(bb, Tb) - yt) ** 2, (pred(bf, Tf) - yt) ** 2
        # residual breadth: breadth not explained by the index's own move (fit on dev)
        rb = ols(Xb, np.array([r["br"] for r in dev]))
        res_t = np.array([r["br"] for r in test]) - pred(rb, Tb)
        res_d = np.array([r["br"] for r in dev]) - pred(rb, Xb)
        boots_mse, boots_ic = [], []
        for _ in range(1000):
            pick = np.concatenate([by_day[d] for d in rng.choice(tdays, len(tdays))])
            boots_mse.append(float(eb[pick].mean() - ef[pick].mean()))
            boots_ic.append(float(np.corrcoef(res_t[pick], yt[pick])[0, 1]))
        out[tgt] = {"test_mse_base": float(eb.mean()), "test_mse_with_components": float(ef.mean()),
                    "mse_gain_pct": round(100 * (1 - ef.mean() / eb.mean()), 3),
                    "mse_gain_95ci": [float(np.percentile(boots_mse, 2.5)), float(np.percentile(boots_mse, 97.5))],
                    "corr_base": float(np.corrcoef(pred(bb, Tb), yt)[0, 1]),
                    "corr_with_components": float(np.corrcoef(pred(bf, Tf), yt)[0, 1]),
                    "residual_breadth_ic_dev": float(np.corrcoef(res_d, yd)[0, 1]),
                    "residual_breadth_ic_test": float(np.corrcoef(res_t, yt)[0, 1]),
                    "residual_breadth_ic_test_95ci": [float(np.percentile(boots_ic, 2.5)), float(np.percentile(boots_ic, 97.5))],
                    "coef_with_components": dict(zip(("const",) + BASE_F + COMP_F, map(float, bf)))}
    return out, rb


def trading(rows, rb):
    dev = [r for r in rows if DEV[0] <= r["day"] <= DEV[1]]
    for r in rows:
        r["resid"] = r["br"] - float(pred(rb, np.array([[r[f] for f in BASE_F]]))[0])
    q80, q20 = np.quantile([r["resid"] for r in dev], 0.8), np.quantile([r["resid"] for r in dev], 0.2)
    i80, i20 = np.quantile([r["idx_r"] for r in dev], 0.8), np.quantile([r["idx_r"] for r in dev], 0.2)
    by = {}
    for r in rows:
        by.setdefault(r["day"], []).append(r)

    def make(kind, feat):
        hi, lo = (q80, q20) if feat == "resid" else (i80, i20)

        def f(S):
            rs = by.get(S.day)
            if not rs:
                return None
            s = np.zeros(len(S.F["c"]), np.int8)
            for r in rs:
                x, up = r[feat], r["idx_cum"] > 0
                d = 0
                if kind == "broad":
                    d = 1 if (x >= hi and up) else (-1 if (x <= lo and not up) else 0)
                else:
                    d = -1 if (x <= lo and up) else (1 if (x >= hi and not up) else 0)
                if d:
                    s[r["m"]] = d
                    break
            return s, {}
        return f
    EX = {"X30": {"stop_k": 4.0, "time": 30, "backstop": 0.25}, "Xtrail": {"stop_k": 3.0, "trail_k": 3.0, "backstop": 0.25}}
    real = {f"{kind} {en}": (make(kind, "resid"), ex) for kind, (en, ex) in itertools.product(("broad", "diverge"), EX.items())}
    idx_only = {f"{kind} {en}": (make(kind, "idx_r"), ex) for kind, (en, ex) in itertools.product(("broad", "diverge"), EX.items())}

    def null(f):
        def g(S):
            got = f(S)
            if got is None:
                return None
            s, x = got
            return (s * (1 if random.Random(f"96|{S.day}").random() < 0.5 else -1)).astype(np.int8), x
        return g
    out = {}
    for dname, ok in (("gold-free test days", lambda d: d >= TEST_FROM and C.gold_free(d)), ("all test days", lambda d: d >= TEST_FROM)):
        out[dname] = {}
        for grp_name, grp in (("components", real), ("index only", idx_only), ("NULL random side", {k: (null(f), ex) for k, (f, ex) in real.items()})):
            out[dname][grp_name] = {k: C.comp_table(f, ex, day_ok=ok, max_trades=1, last_entry=290)["2026"] for k, (f, ex) in grp.items()}
    return out, {"resid_q80": float(q80), "resid_q20": float(q20), "idx_q80": i80, "idx_q20": i20}


def exit_test(rows):
    agree = {(r["day"], r["m"]): r["agree"] for r in rows}
    C.RECORD[0] = True
    C.TRADES.clear()
    C.run(C.V5, wallets=(C.STD_WALLETS[0],))
    C.RECORD[0] = False
    Ys = C.years()
    out = {"trades": 0, "changed": 0, "delta": 0.0}
    for t in C.TRADES:
        if t["day"] < "2026-02-01" or (t["day"], 44) not in agree:
            continue
        S = Ys["2026"].sessions[t["day"]]
        rec = S.option(t["strike"], t["opt"])
        d = 1 if t["opt"] == "CE" else -1
        out["trades"] += 1
        bad, cut = 0, None
        for k in KS:
            m = 15 * k + 14
            if m <= t["i"] or m >= t["j"]:
                continue
            a = agree.get((t["day"], m))
            bad = bad + 1 if (a is not None and a * d < -0.3) else 0
            if bad >= 2:
                cut = m
                break
        if cut is None:
            continue
        qty = t["lots"] * M.LOT
        bid = float(rec[4][cut] if rec[6][cut] else rec[5][cut])
        alt = (bid - t["ask"]) * qty - M.charges(t["ask"], bid, qty) - 205.0 * t["lots"]
        act = (t["px"] - t["ask"]) * qty - M.charges(t["ask"], t["px"], qty) - 205.0 * t["lots"]
        out["changed"] += 1
        out["delta"] += alt - act
    out["delta"] = round(out["delta"])
    return out


if __name__ == "__main__":
    out_path = HERE / "results-sn96.json"
    if out_path.exists():
        raise SystemExit("SN96 is scored once")
    rows, W, names = build()
    top = sorted(W.items(), key=lambda kv: -kv[1])[:12]
    print("names", len(names), "rows", len(rows), "days", len({r['day'] for r in rows}), "fitted weights (top 12)",
          [(s, round(x, 3)) for s, x in top], "sum", round(sum(W.values()), 3), flush=True)
    info, rb = info_test(rows)
    print("INFORMATION TEST", json.dumps(info, indent=0)[:2500], flush=True)
    tr, thr = trading(rows, rb)
    for dn, groups in tr.items():
        for g, t in groups.items():
            for k, v in t.items():
                print(f"  {dn:20s} {g:18s} {k:16s} net {v['net']:>7} won/lost {v['green']}/{v['red']} trades {v['trades']}")
    ex = exit_test(rows)
    print("EXIT TEST (Gold v5 2026 trades at A)", ex, flush=True)
    passed = info["y30"]["mse_gain_95ci"][0] > 0 or info["y30"]["residual_breadth_ic_test_95ci"][0] > 0
    print("INFORMATION PASS (95% interval above zero):", passed)
    out_path.write_text(json.dumps({"names": names, "weights": W, "info": info, "thresholds": thr, "trading": tr,
                                    "exit_test": ex, "information_pass": passed}, indent=1, default=float), encoding="utf-8")
