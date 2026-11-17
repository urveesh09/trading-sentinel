"""SN408 (own): does a rich option at Gold's entry explain Gold's losses? (PLAN.md section 2, frozen at 00693405; details
fixed here before any SN408 number.)

Every Gold v5 DEPLOYED trade on the 2022-26 path (Rs 30k, Rs 205; SN403's cached log), matched to its N11 / R0.85 signal
(day, entry minute), gl range Apr 2022 on. Measures at the signal bar: sn404.measure (ask, time-value share, sessions to
expiry, ATM straddle IV, IV vs the same session's 09:16 and the previous 15:00, the 60-minute hurdle in points and over
ATR14). Outcome: Gold's net per lot at entry. Reported: Spearman of each measure with the outcome (all trades and by
expert); terciles of IV-vs-previous-15:00 (the overnight richness, fw9's idea) and of the ATM IV level with per-lot net
by year. Freeze a log-only forward field (no Gold change) only if the cheapest tercile beats the richest in >= 4 of 5
years with Spearman p < 0.05 (|t| >= 1.96).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import op  # noqa: E402
import sn404 as S4  # noqa: E402

P = S4.P
OUT = HERE / "results-sn408.json"
FEATS = ("ask", "tv_share", "dte", "atm_iv", "iv_vs_0916", "iv_vs_prev1500", "H_pts", "H_over_ATR")


def terciles(rows, key):
    rs = sorted([r for r in rows if r.get(key) is not None], key=lambda r: r[key])
    n = len(rs)
    parts = {"LOW": rs[: n // 3], "MID": rs[n // 3: 2 * n // 3], "HIGH": rs[2 * n // 3:]}
    out = {}
    for nm, sub in parts.items():
        out[nm] = {"n": len(sub), "net_per_lot_mean": op.per_session([r["net_per_lot"] for r in sub]),
                   "by_year": {y: op.per_session([r["net_per_lot"] for r in sub if r["day"][:4] == y]) for y in S4.YEARS},
                   "range": [round(sub[0][key], 3), round(sub[-1][key], 3)] if sub else None}
    yrs = [y for y in S4.YEARS if out["LOW"]["by_year"][y] is not None and out["HIGH"]["by_year"][y] is not None]
    out["years_low_beats_high"] = f"{sum(out['LOW']['by_year'][y] > out['HIGH']['by_year'][y] for y in yrs)} of {len(yrs)}"
    return out


def main():
    if OUT.exists():
        raise SystemExit("SN408 is run once")
    runs = json.loads(S4.RUNS.read_text(encoding="utf-8"))
    smp, _days, _au = op.setup()
    sig = {}
    for y in S4.YEARS:
        for b in ("N11", "R0.85"):
            for x in P.stream(y, b):
                sig.setdefault((x["day"], x["i"]), x)
    rows = []
    unmatched = 0
    for t in runs["2022-2026 DEPLOYED @205"]["log"]:
        sg = sig.get((t["day"], t["i"]))
        if sg is None:
            unmatched += 1
            continue
        m = S4.measure(smp, sg)
        if m is None:
            continue
        rows.append({"day": t["day"], "expert": t.get("expert") or sg["expert"], "net_per_lot": t["net"] / max(1, t["lots0"] or 1), **m})
    res = {"gold_trades": len(runs["2022-2026 DEPLOYED @205"]["log"]), "measured": len(rows), "unmatched": unmatched,
           "spearman_all": {f: S4.spearman([r.get(f) if r.get(f) is not None else np.nan for r in rows], [r["net_per_lot"] for r in rows]) for f in FEATS}}
    for e in sorted({r["expert"] for r in rows}):
        rs = [r for r in rows if r["expert"] == e]
        res[f"spearman {e} (n={len(rs)})"] = {f: S4.spearman([r.get(f) if r.get(f) is not None else np.nan for r in rs], [r["net_per_lot"] for r in rs]) for f in FEATS}
    res["terciles iv_vs_prev1500"] = terciles(rows, "iv_vs_prev1500")
    res["terciles atm_iv"] = terciles(rows, "atm_iv")
    res["terciles H_over_ATR"] = terciles(rows, "H_over_ATR")
    sp = res["spearman_all"]["iv_vs_prev1500"]
    t3 = res["terciles iv_vs_prev1500"]["years_low_beats_high"]
    res["freeze_forward_field"] = bool(sp.get("t") is not None and abs(sp["t"]) >= 1.96 and int(t3.split(" of ")[0]) >= 4)
    res["rows"] = rows
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1, default=float))


if __name__ == "__main__":
    main()
