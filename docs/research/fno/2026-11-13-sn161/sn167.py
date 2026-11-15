"""SN167 - the wage classifier (PLAN.md). Per action (ATM CE, ATM PE, 2-OTM CE, 2-OTM PE at Rs 15k): LightGBM
P(+Rs 1,500 comes before -Rs 1,500) from SN131's 44 causal features + minutes left, OR30 width, a volatility forecast
ratio (half today's realised / implied, half yesterday's ATR / implied), the action's ask and lots. ('The day's realised
net so far' from PLAN is constant on single-trade labels and is dropped.) Walk-forward inside development (quarterly
blocks from 2024, one-session purge); theta from {0.40 ... 0.60} by the development out-of-sample net of the policy
(highest P action at each flat minute 09:30-14:30 if >= theta; stop after a wage or two trades). Matched random null on
the same days. The final models (all development but the last session) write TEST predictions to _local for SN181;
nothing here reads a TEST label.

ML analog of pass rule 5: development out-of-sample net > 0, >= 2 of 3 scored years (2024, 2025, 2026 dev) positive,
and above the matched null's 95th percentile."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pml  # noqa: E402
import pw  # noqa: E402

if __name__ == "__main__":
    out_path = HERE / "results-sn167.json"
    if out_path.exists():
        raise SystemExit("SN167 is scored once")
    d131, bar, s_idx, k_idx, base, names = pml.load()
    days = d131["day"]
    n_sess = len(bar["days"])
    P_dev = np.full((n_sess, 4, pml.NK), np.nan, dtype=np.float32)
    P_test = np.full((n_sess, 4, pml.NK), np.nan, dtype=np.float32)
    importance = {}
    for a, name in enumerate(bar["actions"]):
        Xa = pml.action_matrix(base, bar, s_idx, k_idx, a)
        lab = bar["label"][s_idx, a, k_idx]
        ok = ~np.isnan(bar["net"][s_idx, a, k_idx])
        y = (lab == 1)
        oos = pml.walk_forward(Xa, y, ok, days)
        P_dev[:, a, :] = pml.to_grid(oos, s_idx, k_idx, n_sess)
        tp, model = pml.final_test_pred(Xa, y, ok, days)
        P_test[:, a, :] = pml.to_grid(tp, s_idx, k_idx, n_sess)
        gain = model.feature_importance("gain")
        cols = names + ["ask_a", "lots_a"]
        importance[name] = [cols[i] for i in np.argsort(gain)[::-1][:10]]
        print(f"SN167 {name}: trained; top features {importance[name][:6]}", flush=True)
    dev_scored = [s for s, d in enumerate(bar["days"]) if "2024-01-01" <= d < pw.TEST_FROM]
    cal = [bar["days"][s] for s in dev_scored]
    res = {"importance": importance, "thetas": {}}
    for th in pml.THETAS:
        dn, ntr = pml.policy(P_dev, bar, dev_scored, th)
        res["thetas"][str(th)] = {**pml.summary(dn, cal), "trades": ntr}
        print(f"SN167 theta {th}: {json.dumps(res['thetas'][str(th)])}", flush=True)
    best = max(pml.THETAS, key=lambda t: res["thetas"][str(t)]["net"])
    taken = pml.trades_per_day(P_dev, bar, dev_scored, best)
    null = pml.matched_null(bar, taken)
    res["chosen_theta"] = best
    res["null"] = pml.null_summary(null, cal)
    ch = res["thetas"][str(best)]
    yrs = [v for v in ch["by_year"].values()]
    res["dev_pass_ml_analog"] = bool(ch["net"] > 0 and sum(v > 0 for v in yrs) >= 2 and ch["net"] > res["null"]["net_p95"])
    print(f"SN167 chosen theta {best}: {json.dumps(ch)} | null {json.dumps(res['null'])} | dev pass {res['dev_pass_ml_analog']}",
          flush=True)
    pml.save("sn167_test.pkl", {"P_test": P_test, "theta": best, "days": bar["days"]})
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
