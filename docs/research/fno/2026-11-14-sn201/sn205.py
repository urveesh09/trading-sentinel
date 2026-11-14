"""SN205 - sell only when insurance is expensive: HAR timing on WK-S (PLAN.md SN204 rule, applied to WK-S by the
amendment). rho = HAR forecast holding sd (monthly walk-forward refit on all earlier days) / implied holding sd
(Q / 0.8 S). Rule A(kappa): trade only when rho <= kappa, kappa in {0.8, 0.9, 1.0, 1.1}, kappa chosen by LOYO. Rule B:
2 lots at rho <= 0.8, 1 lot at rho <= 1.1, skip above. Weeks without a forecast trade unfiltered. Null: a random skip
of the same per-year count (2,000 draws). The mechanism check: WK-S's mean net by rho quintile."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import feat  # noqa: E402
import wk  # noqa: E402

KAPPAS = (0.8, 0.9, 1.0, 1.1)


def null_p95(trades, keep, draws=2000, seed=205):
    """95th percentile of totals when the same number of weeks per year is skipped at random."""
    rng = np.random.default_rng(seed)
    by = {}
    for t, k in zip(trades, keep):
        by.setdefault(t["entry"][:4], []).append((t["net"], k))
    tots = []
    for _ in range(draws):
        s = 0.0
        for y, rows in by.items():
            x = np.array([n for n, _k in rows])
            m = sum(k for _n, k in rows)
            s += float(x[rng.choice(len(x), m, replace=False)].sum()) if m else 0.0
        tots.append(s)
    return round(float(np.percentile(tots, 95))), round(float(np.mean(tots)))


if __name__ == "__main__":
    out_path = HERE / "results-sn205.json"
    if out_path.exists():
        raise SystemExit("SN205 is run once")
    D = wk.dev_data()
    weeks = wk.split(wk.expiries(D), "dev")
    A = pickle.loads((wk.LOCAL / "sn204-picks.pkl").read_bytes())["WK-S"]
    tr = sorted(wk.book(wk.NIFTY, D, weeks, A), key=lambda t: t["entry"])
    dl = feat.Daily(D)
    rho = [dl.rho(t) for t in tr]
    res = {"variant": wk.vname(A), "weeks": len(tr), "with_forecast": sum(r is not None for r in rho),
           "unfiltered": wk.stats(tr)}
    have = [(t, r) for t, r in zip(tr, rho) if r is not None]
    qs = np.quantile([r for _t, r in have], [0.2, 0.4, 0.6, 0.8])
    res["rho_quintiles"] = [round(float(q), 3) for q in qs]
    res["net_by_rho_quintile"] = []
    for b in range(5):
        lo_, hi_ = (qs[b - 1] if b else -1), (qs[b] if b < 4 else 99)
        x = [t["net"] for t, r in have if lo_ < r <= hi_]
        res["net_by_rho_quintile"].append({"weeks": len(x), "mean": round(float(np.mean(x))), "win_pct": round(100 * float(np.mean(np.array(x) > 0)), 1)})
    table = {}
    for kap in KAPPAS:
        keep = [r is None or r <= kap for r in rho]
        table[str(kap)] = {y: round(sum(t["net"] for t, k in zip(tr, keep) if k and t["entry"][:4] == y)) for y in wk.YEARS}
    lo = wk.loyo(table)
    res["rule_A"] = {"by_kappa": table, "loyo": lo}
    keep_l = []
    for t, r in zip(tr, rho):
        kap = float(lo[t["entry"][:4]]["pick"])
        keep_l.append(r is None or r <= kap)
    (wk.LOCAL / "sn205-decisions.pkl").write_bytes(pickle.dumps({t["expiry"]: bool(k) for t, k in zip(tr, keep_l)}))
    p95, mean_null = null_p95(tr, keep_l)
    unf_sum = round(sum(t["net"] for t in tr))
    res["rule_A"].update(skipped=len(tr) - sum(keep_l), null_p95=p95, null_mean=mean_null, unfiltered_sum=unf_sum,
                         PASS=bool(lo["sum"] > unf_sum and lo["sum"] > p95))
    lots = [1 if r is None else (2 if r <= 0.8 else (1 if r <= 1.1 else 0)) for r in rho]
    xb = [t["net"] * n for t, n in zip(tr, lots)]
    by_b = {y: round(sum(x for t, x in zip(tr, xb) if t["entry"][:4] == y)) for y in wk.YEARS}
    res["rule_B"] = {"net": round(sum(xb)), "by_year": by_b, "worst": round(min(xb)), "two_lot_weeks": lots.count(2), "skipped": lots.count(0),
                     "PASS": bool(sum(xb) > unf_sum and all(v > 0 for v in by_b.values()))}
    full = dl.fit(next(i for i, d in enumerate(dl.day) if d >= wk.TEST_FROM))
    kap_final = max(KAPPAS, key=lambda k: sum(table[str(k)].values()))
    (wk.LOCAL / "sn205-har.pkl").write_bytes(pickle.dumps({"beta": full, "kappa": kap_final}))
    res["final"] = {"beta": [float(b) for b in full], "kappa_all_dev": kap_final}
    print("SN205", json.dumps({k: v for k, v in res.items() if k != "unfiltered"}), flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
