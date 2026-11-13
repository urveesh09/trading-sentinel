"""SN192 - the LSTM volatility forecast (PLAN.md). The morning sequence (minutes 0-45, seq.py features) plus HAR's
static inputs (log Parkinson RV yesterday / week / month) -> log rest-of-day realised variance (SN171's target).
Per year-fold, trained on earlier development years only; HAR fitted on the same earlier years. Out-of-sample R2 by
year for both. If the LSTM beats HAR in >= 2 of 3 folds, SN171's rule (forecast / implied >= 1.1 -> 10:00 1-OTM
strangle Rs 15k / ATM straddle Rs 30k, held) is scored with the LSTM forecast on the same folds beside HAR's."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pe  # noqa: E402
import seq  # noqa: E402

pw, p3, C = pe.pw, pe.p3, pe.C
FOLDS = ("2024", "2025", "2026")


def r2(y, f):
    return 1.0 - float(np.sum((y - f) ** 2)) / float(np.sum((y - y.mean()) ** 2))


if __name__ == "__main__":
    out_path = HERE / "results-sn192.json"
    if out_path.exists():
        raise SystemExit("SN192 is scored once")
    ss = pw.dev_sessions()
    har = p3.HAR(ss)
    rows = []
    for S in ss:
        r = har.rows.get(S.day)
        if r is None:
            continue
        f = seq.session_feats(S)
        x = np.zeros((46, seq.NF), dtype=np.float32)
        x[:] = f[:46]
        rows.append((S, x, r[0][1:4], r[1]))
    days = np.array([r[0].day for r in rows])
    X = np.stack([r[1] for r in rows])
    ST = np.array([r[2] for r in rows], dtype=np.float32)
    y = np.array([r[3] for r in rows], dtype=np.float32)
    year = np.array([d[:4] for d in days])
    res = {"days": len(rows), "folds": {}}
    sig_lstm, sig_har = {}, {}
    for fy in FOLDS:
        tr, te = year < fy, year == fy
        mu, sd = X[tr].reshape(-1, seq.NF).mean(0), X[tr].reshape(-1, seq.NF).std(0) + 1e-6
        smu, ssd = ST[tr].mean(0), ST[tr].std(0) + 1e-6
        ymu, ysd = y[tr].mean(), y[tr].std() + 1e-6
        net = seq.train_regressor((X[tr] - mu) / sd, (y[tr] - ymu) / ysd, (ST[tr] - smu) / ssd)
        f_lstm = seq.predict_reg(net, (X[te] - mu) / sd, (ST[te] - smu) / ssd) * ysd + ymu
        beta, s2 = har.fit(lambda d, fy=fy: d[:4] < fy)
        f_har = np.array([float(har.rows[d][0] @ beta) for d in days[te]])
        res["folds"][fy] = {"r2_lstm": round(r2(y[te], f_lstm), 4), "r2_har": round(r2(y[te], f_har), 4), "days": int(te.sum())}
        resid = float(np.mean((y[tr] - (seq.predict_reg(net, (X[tr] - mu) / sd, (ST[tr] - smu) / ssd) * ysd + ymu)) ** 2))
        for d, fl, fh in zip(days[te], f_lstm, f_har):
            sig_lstm[d] = math.sqrt(math.exp(float(fl) + 0.5 * resid) / 375.0)
            sig_har[d] = math.sqrt(math.exp(float(fh) + 0.5 * s2) / 375.0)
        print(f"SN192 fold {fy}: {json.dumps(res['folds'][fy])}", flush=True)
    wins = sum(v["r2_lstm"] > v["r2_har"] for v in res["folds"].values())
    res["lstm_beats_har_folds"] = wins
    trade = {}
    sess = {r[0].day: r[0] for r in rows}
    empty = {S.day for S in pe.empty_sessions()}
    for name, sig in (("LSTM", sig_lstm), ("HAR", sig_har)):
        for wname, (wallet, kind, room) in (("Rs 15k strangle", (15000.0, "strangle1", 3000.0)), ("Rs 30k straddle", (30000.0, "straddle", 6000.0))):
            dn = {}
            for d, s_ in sig.items():
                S = sess[d]
                si = C.sigma_imp(S, p3.I1000)
                if d in empty and si and s_ / si >= 1.1:
                    n = p3.structure(S, p3.I1000, kind, wallet, room)
                    if n is not None:
                        dn[d] = n
            trade[f"{name} {wname}"] = {"net": round(sum(dn.values())), "trades": len(dn),
                                        "by_year": {fy: round(sum(v for d, v in dn.items() if d[:4] == fy)) for fy in FOLDS}}
    res["sn171_rule_on_empty_days_oos"] = trade
    res["dev_pass"] = bool(wins >= 2 and all(trade[f"LSTM {w}"]["net"] > max(0, trade[f"HAR {w}"]["net"]) for w in ("Rs 15k strangle", "Rs 30k straddle")))
    print("SN192", json.dumps(res), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
