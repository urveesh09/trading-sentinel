"""SN400: does option flow lead futures or follow it? The strict-signing companion of fw8 (frozen Nov 17, 2026, before
any forward session is read; PLAN.md section 1 at 00693405). fw8 stays as frozen and its verdict is still produced.

Strict signing (per option packet whose cumulative volume rose), signed only if ALL hold, else UNSIGNED with a reason:
  FRESH      the prior two-sided quote of this contract was received <= FRESH_Q = 2.0 s before (the Nov 16 p99 option
             inter-packet gap was 1.25 s; the same formula as fw9a)
  NONCROSSED the prior quote had 0 < bid < ask
  ONE TRADE  the volume increment equals the packet's last traded quantity (else it spans several trades)
  CAUSAL     the packet's exchange last-trade time is not before the prior quote's exchange time
then BUY if last price >= the prior ask, SELL if <= the prior bid, else UNSIGNED (inside the spread). Everything else is
fw8's: ATM +- 2 strikes, 600 s window, calibration on the first 5 sessions, the event rule and controls, fw2 execution.
Forward judgement (once, fw8's 20 sessions; sessions 6-20 scored):
  (1) the event rule of fw8 on STRICT flow (arms SIGNED / UNSIGNED / SHIFTED / COIN), fw8's PASS rule;
  (2) incremental prediction: pooled whole-minute rows 09:30 - 14:30, OLS of the next-15-minute futures mid return (bp)
      on standardized strict signed flow, the prior 10-minute futures return, the prior 10-minute ATM CE-minus-PE mid
      revision and unsigned flow; date-clustered standard errors. Flow "leads" only if its t > 2 with the controls in.
  (3) by date: the original and strict signable shares.
Amendment A1 (Nov 17, from the Nov 16 plumbing copy only, before any forward session): Kite sends about one packet a
second per contract and each volume increment bundles a median of ~198 trades (increment / last traded quantity: p10 23,
p50 198, p90 888); only 184 of 46,676 increments (0.4%) are single trades, so strict signing labels 0.0% of volume (fw8:
91.7%, which is the sign of the LAST print of each bundle). The strict event arm is kept as specified (it will be
INSUFFICIENT by construction). The incremental OLS therefore tests fw8's LAST-PRINT flow (signed_orig, labelled as such)
with the same controls, and the strict flow only when it is not degenerate (std > 0). flow_leads refers to LAST-PRINT.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn381"))
import fw8  # noqa: E402

FRESH_Q = 2.0
OUT = HERE / "results-sn400-fw8a.json"
REASONS = ("stale_quote", "crossed_or_missing", "multi_trade", "noncausal", "inside_spread")


# ---- pure rule (tested in test_fw8a.py) -------------------------------------------------------------------------------
def strict_sign(row, prev_v, prev_quote):
    """row: the packet (recv_ns, volume, last_qty, last_trade_ts, ltp); prev_quote: (recv_s, bid, ask, exchange_ts) or None.
    -> (sign, units, reason): sign +1 / -1 / 0; units = the volume increment (0 when there is none)."""
    v = row.get("volume")
    if v is None or prev_v is None or v <= prev_v:
        return 0, 0.0, None
    dv = float(v - prev_v)
    if prev_quote is None:
        return 0, dv, "crossed_or_missing"
    q_t, bid, ask, q_ex = prev_quote
    if row["recv_ns"] / 1e9 - q_t > FRESH_Q:
        return 0, dv, "stale_quote"
    if not (0 < bid < ask):
        return 0, dv, "crossed_or_missing"
    if row.get("last_qty") is None or float(row["last_qty"]) != dv:
        return 0, dv, "multi_trade"
    if (row.get("last_trade_ts") or 0) < (q_ex or 0):
        return 0, dv, "noncausal"
    if row["ltp"] >= ask:
        return 1, dv, None
    if row["ltp"] <= bid:
        return -1, dv, None
    return 0, dv, "inside_spread"


def flows_strict(meta, acc, t0, front):
    out, signed_v, all_v = {}, 0.0, 0.0
    why = {r: 0.0 for r in REASONS}
    for tok, rows in acc.items():
        m = meta.get(tok, {})
        if m.get("type") not in ("CE", "PE") or m.get("expiry") != front:
            continue
        rows.sort(key=lambda r: r["recv_ns"])
        lot = float(m.get("lot_size") or 65)
        ev, pv, pq = [], None, None
        for r in rows:
            sgn, dv, reason = strict_sign(r, pv, pq)
            if dv > 0:
                ev.append((r["recv_ns"] / 1e9 - t0, sgn * dv / lot, dv / lot))
                all_v += dv / lot
                if sgn != 0:
                    signed_v += dv / lot
                elif reason:
                    why[reason] += dv / lot
            pv = r.get("volume") if r.get("volume") is not None else pv
            b, a = r.get("bids"), r.get("asks")
            if b and a:
                pq = (r["recv_ns"] / 1e9, b[0]["price"], a[0]["price"], r.get("exchange_ts") or 0)
        out[tok] = (m["type"], int(round(m["strike"])), np.array(ev) if ev else np.zeros((0, 3)))
    return out, (signed_v / all_v if all_v else None), {k: (round(v / all_v, 4) if all_v else None) for k, v in why.items()}


def minute_series_strict(folder):
    got = fw8.load_light(folder)
    if got is None:
        return None
    meta, acc, t0, front, fut, idx = got
    fl, share, why = flows_strict(meta, acc, t0, front)
    fl0, share0 = fw8.flows(meta, acc, t0, front)
    fr = sorted(acc.get(fut, []), key=lambda r: r["recv_ns"])
    ft = np.array([r["recv_ns"] / 1e9 - t0 for r in fr])
    fm = np.array([0.5 * (r["bids"][0]["price"] + r["asks"][0]["price"]) if r.get("bids") and r["bids"][0]["price"] > 0 else r["ltp"] for r in fr])
    ir = sorted(acc.get(idx, []), key=lambda r: r["recv_ns"])
    it, il = np.array([r["recv_ns"] / 1e9 - t0 for r in ir]), np.array([r["ltp"] for r in ir])
    mids = {}
    for tok, rows in acc.items():
        m = meta.get(tok, {})
        if m.get("type") in ("CE", "PE") and m.get("expiry") == front:
            rr = [r for r in sorted(rows, key=lambda r: r["recv_ns"]) if r.get("bids") and r.get("asks") and 0 < r["bids"][0]["price"] < r["asks"][0]["price"]]
            mids[(m["type"], int(round(m["strike"])))] = (np.array([r["recv_ns"] / 1e9 - t0 for r in rr]), np.array([0.5 * (r["bids"][0]["price"] + r["asks"][0]["price"]) for r in rr]))

    def mid_at(typ, k, t):
        x = mids.get((typ, k))
        if x is None or not len(x[0]):
            return None
        j = np.searchsorted(x[0], t, side="right") - 1
        return None if j < 0 or t - x[0][j] > 60 else float(x[1][j])
    rows = []
    for t in np.arange(900.0, 19500.0 + 1, 60.0):
        k = np.searchsorted(it, t, side="right") - 1
        j, j0, j1 = np.searchsorted(ft, t, side="right") - 1, np.searchsorted(ft, t - 600, side="right") - 1, np.searchsorted(ft, t + 900, side="right") - 1
        if k < 0 or j < 0 or j0 < 0:
            continue
        atm = int(round(il[k] / 50.0) * 50)
        c1, p1, c0, p0 = mid_at("CE", atm, t), mid_at("PE", atm, t), mid_at("CE", atm, t - 600), mid_at("PE", atm, t - 600)
        rows.append({"t": float(t), "atm": atm, "fut": float(fm[j]), "r10": float(fm[j] / fm[j0] - 1.0),
                     "fwd15_bp": None if j1 <= j or ft[j1] < t + 840 else 1e4 * float(fm[j1] / fm[j] - 1.0),
                     "mid_rev": None if None in (c1, p1, c0, p0) else (c1 - p1) - (c0 - p0),
                     "signed": fw8.flow_at(fl, t, atm, 1), "unsigned": fw8.flow_at(fl, t, atm, 2), "signed_orig": fw8.flow_at(fl0, t, atm, 1)})
    return {"day": Path(folder).name[-10:], "rows": rows, "signable_share": share, "signable_share_original": share0, "unsigned_reasons": why, "ft": ft, "fm": fm}


def clustered_ols(y, X, groups):
    y, X = np.asarray(y, float), np.column_stack([np.ones(len(y))] + [np.asarray(c, float) for c in X])
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    e = y - X @ b
    XtX = np.linalg.inv(X.T @ X)
    meat = np.zeros((X.shape[1], X.shape[1]))
    for g in set(groups):
        idx = [i for i, x in enumerate(groups) if x == g]
        s = X[idx].T @ e[idx]
        meat += np.outer(s, s)
    G = len(set(groups))
    cov = XtX @ meat @ XtX * (G / max(1, G - 1))
    se = np.sqrt(np.diag(cov))
    return b, se


def verdict():
    import fw5
    if OUT.exists():
        raise SystemExit("fw8a is scored once")
    days = sorted(p.name for p in fw5.ARCH.iterdir() if p.is_dir() and p.name >= fw5.START) if fw5.ARCH.exists() else []
    series = []
    for d in days:
        rc = fw5.REC / f"{d}.json"
        q = json.loads(rc.read_text(encoding="utf-8")).get("qualify", {}) if rc.exists() else {}
        if not q.get("ok") or q.get("expiry_day"):
            continue
        ms = minute_series_strict(fw5.ARCH / d)
        if ms is not None and ms["rows"]:
            series.append(ms)
        if len(series) == fw8.N_SESS:
            break
    if len(series) < fw8.N_SESS:
        raise SystemExit(f"{len(series)} of {fw8.N_SESS} sessions; the verdict waits")
    evs = []
    for k, ms in enumerate(series):
        if k < fw8.CAL:
            continue
        prior = [r for m in series[:k] for r in m["rows"]]
        s1, s2 = float(np.std([r["signed"] for r in prior])), float(np.std([r["unsigned"] for r in prior]))
        evs.append(fw8.evaluate(fw5.ARCH / ms["day"], ms, s1, s2))
    res = {"sessions": [m["day"] for m in series], "signable_share_strict": [m["signable_share"] for m in series],
           "signable_share_original": [m["signable_share_original"] for m in series], "unsigned_reasons": [m["unsigned_reasons"] for m in series]}
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
    pool = [(ms["day"], r) for ms in series[fw8.CAL:] for r in ms["rows"] if r["fwd15_bp"] is not None and r["mid_rev"] is not None]
    if len(pool) > 50:
        z = lambda xs: (np.asarray(xs, float) - np.mean(xs)) / (np.std(xs) or 1.0)  # noqa: E731
        y = [r["fwd15_bp"] for _d, r in pool]
        X = [z([r["signed_orig"] for _d, r in pool]), z([r["r10"] for _d, r in pool]), z([r["mid_rev"] for _d, r in pool]), z([r["unsigned"] for _d, r in pool])]
        names = ["intercept", "last_print_flow", "r10", "mid_rev", "unsigned"]
        if np.std([r["signed"] for _d, r in pool]) > 0:
            X.append(z([r["signed"] for _d, r in pool]))
            names.append("strict_flow")
        b, se = clustered_ols(y, X, [d for d, _r in pool])
        res["incremental_ols"] = {n: {"coef_bp_per_sd": round(float(b[i]), 3), "t": round(float(b[i] / se[i]), 2) if se[i] > 0 else None} for i, n in enumerate(names)}
        res["incremental_ols"]["rows"] = len(pool)
        res["flow_leads"] = bool(se[1] > 0 and b[1] / se[1] > 2)
    res["events"] = evs
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "events"}, indent=1, default=float))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "dev":
        ms = minute_series_strict(Path(sys.argv[2]))
        print(json.dumps({"minutes": len(ms["rows"]) if ms else 0, "signable_share_strict": None if not ms else round(ms["signable_share"] or 0, 3),
                          "signable_share_original": None if not ms else round(ms["signable_share_original"] or 0, 3), "unsigned_reasons": None if not ms else ms["unsigned_reasons"]}))
    elif len(sys.argv) > 1 and sys.argv[1] == "verdict":
        verdict()
    else:
        raise SystemExit("usage: fw8a.py dev FOLDER | verdict")
