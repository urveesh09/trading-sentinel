"""SN251 - the owner's first question (PLAN.md): WK-H with bought wings instead of the futures hedge. WK-H's timing
(k = M: the first 15:15 after the last weekend / holiday before expiry), held to settlement, no futures, on the five WK
samples (wk3, unchanged). Per option lot: net, positive months, worst month, worst week, the structure's largest
possible loss, and whether one lot fits 20% of Rs 30,000. References: the same straddle unhedged, WK-H band 0.6 (Gold
v6) and band 0.8 (Gold v7)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-15-sn231"))
import led  # noqa: E402
import wk4  # noqa: E402

wk3 = led.wk3
STRUCTS = ("IF 0.5", "IF 1.0", "IF 2.0", "IC 0.5/0.5", "IC 0.5/1.0", "IC 0.5/1.5")
REFS = ("STRADDLE unhedged", "WK-H band 0.6 (Gold v6)", "WK-H band 0.8 (Gold v7)")
FIT = 0.20 * 30000.0


def stats(trades, lots):
    s = led.wk_month_stats(trades, lots)
    nets = np.array([t["net"] / lots for t in trades]) if trades else np.zeros(0)
    ml = [t.get("max_loss") for t in trades if t.get("max_loss") is not None]
    s.update(weeks=len(trades), worst_week=round(float(nets.min())) if len(nets) else 0,
             win_pct=round(100.0 * float((nets > 0).mean()), 1) if len(nets) else 0.0,
             per_week=round(float(nets.mean()), 1) if len(nets) else 0.0,
             max_loss_median=round(float(np.median(ml))) if ml else None,
             max_loss_p90=round(float(np.percentile(ml, 90))) if ml else None,
             clamped_share=round(float(np.mean([t.get("wing_clamped", 0) for t in trades])), 3) if trades else None)
    return s


if __name__ == "__main__":
    out_path = HERE / "results-sn251.json"
    if out_path.exists():
        raise SystemExit("SN251 is run once")
    res = {"structures": {}, "references": {}}
    samples = {n: led.sample(n) for n in led.WK_SAMPLES}
    for st in STRUCTS:
        row = {n: stats(wk3.book3(samples[n], st, "M", "settle", "none", "none"), 1) for n in led.WK_SAMPLES}
        row["positive_samples"] = sum(row[n]["net"] > 0 for n in led.WK_SAMPLES)
        row["total_per_lot"] = sum(row[n]["net"] for n in led.WK_SAMPLES)
        meds = [row[n]["max_loss_median"] for n in led.WK_SAMPLES if row[n]["max_loss_median"] is not None]
        row["fits_20pct_of_30k"] = bool(meds) and max(meds) <= FIT
        row["candidate"] = row["positive_samples"] >= 4
        res["structures"][st] = row
        print("SN251", f"{st:12s}", " | ".join(f"{n} {row[n]['net']:>8} ({row[n]['months_positive']}/{row[n]['months']}, wm {row[n]['worst_month']}, "
                                              f"ww {row[n]['worst_week']}, maxloss {row[n]['max_loss_median']})" for n in led.WK_SAMPLES),
              "| positive", row["positive_samples"], "total", row["total_per_lot"], flush=True)
    for name in REFS:
        row = {}
        for n in led.WK_SAMPLES:
            if name.startswith("STRADDLE"):
                tr, lots = wk3.book3(samples[n], "STRADDLE", "M", "settle", "none", "none"), 1
            elif "0.6" in name:
                tr, lots = wk3.book3(samples[n], "STRADDLE", "M", "settle", "H15x2", "none"), 2
            else:
                tr, lots = wk4.book4(samples[n], "STRADDLE", "M", "settle", {"band": 0.8}), 2
            row[n] = stats(tr, lots)
        row["positive_samples"] = sum(row[n]["net"] > 0 for n in led.WK_SAMPLES)
        row["total_per_lot"] = sum(row[n]["net"] for n in led.WK_SAMPLES)
        res["references"][name] = row
        print("SN251 REF", f"{name:26s}", " | ".join(f"{n} {row[n]['net']:>8} ({row[n]['months_positive']}/{row[n]['months']}, wm {row[n]['worst_month']}, "
                                                    f"ww {row[n]['worst_week']})" for n in led.WK_SAMPLES),
              "| positive", row["positive_samples"], "total", row["total_per_lot"], flush=True)
    res["verdict"] = {"candidates": [s for s, r in res["structures"].items() if r["candidate"]]}
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print("SN251 verdict", res["verdict"], flush=True)
