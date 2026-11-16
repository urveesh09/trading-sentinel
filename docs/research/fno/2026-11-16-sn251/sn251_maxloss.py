"""SN251 supplement (disclosed): sn251.py printed the largest possible loss as None, because wk3.trade3's output does not
carry wk.trade's max_loss field. This reads it from wk3.base_trade (the same entry, legs and fills) for every winged
structure at k = M. Reporting only; no number in results-sn251.json changes."""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-15-sn231"))
import led  # noqa: E402
import sn251  # noqa: E402

wk3 = led.wk3
out = {}
for st in sn251.STRUCTS:
    out[st] = {}
    for n in led.WK_SAMPLES:
        s = led.sample(n)
        ml, cr = [], []
        for e, days in s.weeks:
            t = wk3.base_trade(s, e, days, st, "M")
            if t and t.get("max_loss") is not None:
                ml.append(t["max_loss"])
                cr.append(t["credit_pts"] * s.mk["lot"])
        out[st][n] = {"weeks": len(ml), "max_loss_median": round(float(np.median(ml))), "max_loss_p90": round(float(np.percentile(ml, 90))),
                      "credit_median_rs": round(float(np.median(cr))), "fits_20pct_of_30k_share": round(float(np.mean(np.array(ml) <= sn251.FIT)), 3)}
    print(st, json.dumps(out[st]), flush=True)
(HERE / "results-sn251-maxloss.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
