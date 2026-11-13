"""SN141 - the learning curve (PLAN.md): does the learner get better with more history? Test 2026 with training 2025 /
2024-25 / 2023-25; test 2025 with training 2024 / 2023-24. Per target: rank correlation on the test year; the
policy's net with theta nested on the training window's last 125 sessions."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pe  # noqa: E402

sm, run = pe.sm, pe.run
CONFIGS = (("2026", ("2025",)), ("2026", ("2024", "2025")), ("2026", ("2023", "2024", "2025")),
           ("2025", ("2024",)), ("2025", ("2023", "2024")))


def rank(x):
    r = np.empty(len(x))
    r[np.argsort(x, kind="mergesort")] = np.arange(len(x))
    return r


if __name__ == "__main__":
    out_path = HERE / "results-sn141.json"
    if out_path.exists():
        raise SystemExit("SN141 is scored once")
    data = sm.build()
    X, day = data["X"], data["day"]
    year = np.array([d[:4] for d in day])
    res = {}
    for ty, trs in CONFIGS:
        train = np.isin(year, trs)
        test = year == ty
        udays = np.unique(day[train])
        vstart = udays[-125]
        val, inner = train & (day >= vstart), train & (day < udays[-126])
        preds, vq, ic = {}, {}, {}
        for t in run.TARGETS:
            y = data["Y"][t]
            mi = sm._fit(X[inner], y[inner])
            vq[t] = (val, mi.predict(X[val]).astype(np.float32))
            m = sm._fit(X[train], y[train])
            p = np.full(len(day), np.nan, dtype=np.float32)
            p[test] = m.predict(X[test])
            preds[t] = p
            ok = test & ~np.isnan(y)
            ic[t] = round(float(np.corrcoef(rank(p[ok]), rank(y[ok]))[0, 1]), 4)
        th, _v = sm.choose_theta(data, vq)
        nets, trades = sm.simulate(data, preds, test, th)
        key = f"test {ty} | train {'+'.join(trs)}"
        res[key] = {"ic": ic, "mean_ic": round(float(np.mean(list(ic.values()))), 4), "theta": th,
                    "policy_net": round(sum(nets.values())), "trades": len(trades)}
        print(f"=== SN141 {key}: mean IC {res[key]['mean_ic']:+.4f} {ic} | theta {th} net {res[key]['policy_net']} trades {len(trades)}", flush=True)
    rises = {}
    for t in run.TARGETS:
        a = [res[f"test 2026 | train {x}"]["ic"][t] for x in ("2025", "2024+2025", "2023+2024+2025")]
        b = [res[f"test 2025 | train {x}"]["ic"][t] for x in ("2024", "2023+2024")]
        rises[t] = bool(a[0] < a[1] < a[2] and b[0] < b[1])
    res["rises_with_data"] = rises
    res["MORE_DATA_HELPS"] = sum(rises.values()) >= 5
    print("rises with every added year:", rises, "| more data helps:", res["MORE_DATA_HELPS"], flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
