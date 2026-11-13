"""SN194 - the stacked ensemble (PLAN.md). SN191's out-of-sample LightGBM and LSTM probabilities (CE, PE) plus the
day's HAR forecast / implied ratio at 10:00 (fold HAR, fitted without the year), combined by a logistic regression per
side fitted on the EARLIER folds' out-of-sample rows only (2025 on 2024; 2026 on 2024-25). Same policy, theta grid and
matched null as SN191 on Gold's empty days of 2025 and 2026 (2024 has no earlier fold to fit on)."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pe  # noqa: E402
import sn191  # noqa: E402

pw, p3 = pe.pw, pe.p3
FOLDS = ("2025", "2026")

if __name__ == "__main__":
    out_path = HERE / "results-sn194.json"
    if out_path.exists():
        raise SystemExit("SN194 is scored once")
    from sklearn.linear_model import LogisticRegression
    data = sn191.build()
    saved = pickle.loads((pe.LOCAL / "sn191_test.pkl").read_bytes())
    PL, PG = saved["P_lstm_oos"], saved["P_lgbm_oos"]
    year = np.array([d[:4] for d in data["day"]])
    allss = pw.dev_sessions()
    har = p3.HAR(allss)
    rho = {}
    for y in ("2024", "2025", "2026"):
        rho.update({d: v for d, v in p3.rho_table(har, allss, lambda d, y=y: d[:4] != y).items() if d[:4] == y})
    rv = np.array([rho.get(d, 1.0) for d in data["day"]], dtype=np.float32)
    P = np.full(PL.shape, np.nan, dtype=np.float32)
    for fy in FOLDS:
        tr = (year >= "2024") & (year < fy) & (data["day"] < pw.TEST_FROM)
        te = (year == fy) & (data["day"] < pw.TEST_FROM)
        for a in range(2):
            Z = np.stack([PL[:, a], PG[:, a], rv], axis=1)
            ok = tr & ~np.isnan(data["Y"][:, a]) & ~np.isnan(Z).any(axis=1)
            m = LogisticRegression(max_iter=1000).fit(Z[ok], data["Y"][ok, a])
            ok2 = te & ~np.isnan(Z).any(axis=1)
            P[ok2, a] = m.predict_proba(Z[ok2])[:, 1]
    empty = {S.day for S in pe.empty_sessions()}
    per = {}
    for fy in FOLDS:
        per[fy] = {str(t): sn191.policy(data, P, {d for d in empty if d[:4] == fy}, t)[0] for t in sn191.THETAS}
    loyo, taken = {}, {}
    for fy in FOLDS:
        other = [o for o in FOLDS if o != fy]
        th = max(sn191.THETAS, key=lambda t: sum(sum(per[o][str(t)].values()) for o in other))
        dn = per[fy][str(th)]
        loyo[fy] = {"theta": th, "net": round(sum(dn.values())), "trade_days": len(dn)}
        taken.update(sn191.policy(data, P, {d for d in empty if d[:4] == fy}, th)[1])
    rng = np.random.default_rng(194)
    nulls = [sum(sn191.null_policy(data, taken, rng).values()) for _ in range(300)]
    total = sum(v["net"] for v in loyo.values())
    res = {"loyo": loyo, "total": total, "null_mean": round(float(np.mean(nulls))), "null_p95": round(float(np.percentile(nulls, 95)))}
    res["dev_pass_partial"] = bool(total > 0 and all(v["net"] > 0 for v in loyo.values()) and total > res["null_p95"])
    print("SN194", json.dumps(res), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
