"""SN171 - the volatility forecast (PLAN.md). HAR-RV: the rest-of-day per-minute variance (10:00-15:10) from
yesterday's, last week's and last month's daily Parkinson variance and this morning's realised variance (OLS on logs).
rho = forecast sigma / the straddle's implied sigma at 10:00. Variants: kappa in {1.0, 1.1, 1.2, 1.3, 1.5} x exit
{hold to 15:10, wage lock at +10% of the wallet} for Rs 15k (1-OTM strangle, room Rs 3,000) and Rs 30k (ATM straddle,
room Rs 6,000). All days (not only hot days). Leave-one-year-out: for each held-out year the HAR is fitted without it,
the variant chosen on the other years, the year scored. Matched null: as many random affordable days per year.
The final forecast (all development) and the variant best on all development are written for SN181."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import p3  # noqa: E402
import pml  # noqa: E402
import pw  # noqa: E402

KAPPAS = (1.0, 1.1, 1.2, 1.3, 1.5)
EXITS = ("hold", "wage")
WALLETS = {"Rs 15k strangle": (15000.0, "strangle1", 3000.0), "Rs 30k straddle": (30000.0, "straddle", 6000.0)}

if __name__ == "__main__":
    out_path = HERE / "results-sn171.json"
    if out_path.exists():
        raise SystemExit("SN171 is scored once")
    ss = pw.dev_sessions()
    har = p3.HAR(ss)
    beta_all, _s2 = har.fit(lambda d: True)
    res = {"har_days": len(har.rows), "beta_all_dev": [round(float(b), 4) for b in beta_all]}
    folds = {y: p3.rho_table(har, ss, lambda d, y=y: d[:4] != y) for y in p3.YEARS}
    for wname, (wallet, kind, room) in WALLETS.items():
        nets = {}
        for ex in EXITS:
            tgt = 0.10 * wallet if ex == "wage" else None
            nets[ex] = {S.day: p3.structure(S, p3.I1000, kind, wallet, room, tgt) for S in ss}
        out = {"variants_in_sample": {}, "loyo": {}}
        for y in p3.YEARS:
            rho = folds[y]
            vn = {}
            for k, ex in itertools.product(KAPPAS, EXITS):
                vn[f"kappa {k} {ex}"] = {d: n for d, n in nets[ex].items() if n is not None and rho.get(d, 0) >= k}
            ch, _t, _p = p3.loyo({v: {d: n for d, n in dn.items()} for v, dn in vn.items()})
            out["loyo"][y] = ch[y]
        total = sum(v["net"] for v in out["loyo"].values())
        pos = sum(v["net"] > 0 for v in out["loyo"].values())
        counts = {y: out["loyo"][y]["trades"] for y in p3.YEARS}
        pool = {y: [n for d, n in nets["hold"].items() if n is not None and d[:4] == y] for y in p3.YEARS}
        nmean, n95 = p3.random_days_null(pool, counts)
        rho_all = p3.rho_table(har, ss, lambda d: True)
        for k, ex in itertools.product(KAPPAS, EXITS):
            dn = {d: n for d, n in nets[ex].items() if n is not None and rho_all.get(d, 0) >= k}
            out["variants_in_sample"][f"kappa {k} {ex}"] = pml.summary(dn, [S.day for S in ss], wallet, 0.10 * wallet)
        best = max(out["variants_in_sample"], key=lambda v: out["variants_in_sample"][v]["net"])
        out.update({"loyo_total": total, "years_positive": pos, "null_mean": nmean, "null_p95": n95,
                    "final_variant": best, "dev_pass": bool(total > 0 and pos >= 3 and total > n95)})
        res[wname] = out
        print(f"SN171 {wname}: LOYO {json.dumps(out['loyo'])} total {total} years+ {pos} null {nmean}/{n95} final {best} "
              f"pass {out['dev_pass']}", flush=True)
    pml.save("sn171_final.pkl", {"beta": beta_all, "s2": _s2, "finals": {w: res[w]["final_variant"] for w in WALLETS}})
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
