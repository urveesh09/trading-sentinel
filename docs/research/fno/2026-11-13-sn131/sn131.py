"""SN131 - is there anything to learn? (PLAN.md) Builds the dataset, runs the base walk-forward (CE/PE x 5/15/30/60,
quarterly, expanding) and reports out-of-sample rank correlation and realised net by prediction decile."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run  # noqa: E402
import sm  # noqa: E402


def rank(x):
    r = np.empty(len(x))
    r[np.argsort(x, kind="mergesort")] = np.arange(len(x))
    return r


def spearman(a, b):
    return float(np.corrcoef(rank(a), rank(b))[0, 1])


if __name__ == "__main__":
    out_path = HERE / "results-sn131.json"
    if out_path.exists():
        raise SystemExit("SN131 is scored once")
    data = sm.build()
    print("rows", len(data["day"]), "features", data["X"].shape[1], flush=True)
    pred, val = run.cached_wf("base", data, run.TARGETS)
    res = {"rows": int(len(data["day"])), "targets": {}}
    day = data["day"]
    for t in run.TARGETS:
        y = data["Y"][t]
        ok = ~np.isnan(pred[t]) & ~np.isnan(y)
        e = {"n": int(ok.sum()), "ic_all": spearman(pred[t][ok], y[ok]), "mean_label": round(float(y[ok].mean()))}
        for yr in ("2024", "2025", "2026"):
            m = ok & (np.char.startswith(day.astype(str), yr))
            e[f"ic_{yr}"] = spearman(pred[t][m], y[m])
        edges = np.quantile(pred[t][ok], np.linspace(0, 1, 11))
        dec = []
        for k in range(10):
            m = ok & (pred[t] >= edges[k]) & (pred[t] <= edges[k + 1])
            dec.append({"decile": k + 1, "n": int(m.sum()), "mean_pred": round(float(pred[t][m].mean())), "mean_net": round(float(y[m].mean()))})
        e["deciles"] = dec
        top = ok & (pred[t] >= np.quantile(pred[t][ok], 0.99))
        e["top_1pct_mean_net"] = round(float(y[top].mean()))
        e["pred_above_0_share"] = round(float((pred[t][ok] > 0).mean()), 4)
        e["pred_above_0_mean_net"] = round(float(y[ok & (pred[t] > 0)].mean())) if (ok & (pred[t] > 0)).any() else None
        res["targets"][t] = e
        print(f"{t:5s} IC {e['ic_all']:+.3f} (24 {e['ic_2024']:+.3f} 25 {e['ic_2025']:+.3f} 26 {e['ic_2026']:+.3f}) mean {e['mean_label']:>6} "
              f"| top decile net {dec[-1]['mean_net']:>6} | top 1% {e['top_1pct_mean_net']:>6} | pred>0 share {e['pred_above_0_share']} net {e['pred_above_0_mean_net']}", flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
