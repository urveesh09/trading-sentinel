"""SN184 - the honest wage table (PLAN.md). Read from the saved results (nothing rescored): per wallet, what a daily
wage-earner would have had a month in development and on TEST from today's system, the wage day player and the
coin-flip wage trader; and SN177's salary account (smallest start that pays every session)."""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def j(n):
    p = HERE / f"results-{n}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def row(s):
    return {"wage_days_per_month": s["month"]["wage_days_mean"], "month_median": s["month"]["median"],
            "month_mean": s["month"]["mean"], "month_worst": s["month"]["worst"], "net": s["net"], "wage_share": s["wage_share"]}


if __name__ == "__main__":
    out_path = HERE / "results-sn184.json"
    if out_path.exists():
        raise SystemExit("SN184 is scored once")
    r161, r163, r176, r177, r181 = j("sn161"), j("sn163"), j("sn176"), j("sn177"), j("sn181")
    t = {"development (2023-01 .. 2026-08-19)": {}, "TEST (2026-08-20 .. 10-28)": {}}
    dev = t["development (2023-01 .. 2026-08-19)"]
    for key in ("Rs 15k", "Rs 30k growing (production)"):
        dev[f"Gold v5 {key}"] = row(r176[key]["Gold v5"])
        dev[f"wage day player {key}"] = row(r176[key]["+ passing companions"])
    c = r163["wage 1500 stop 1500 attempts 1"]
    dev["coin-flip wage trader Rs 15k"] = {"wage_days_per_month": c["wage_days_per_month"], "month_mean": c["month_mean"], "net": c["net_mean"]}
    te = t["TEST (2026-08-20 .. 10-28)"]
    for k, v in r181["reference"].items():
        te[k] = row(v) if "month" in v else v
    t["salary account (development): smallest start that pays every session"] = {
        k: {w: v[w]["min_start_never_short"] for w in v if w.startswith("wage")} for k, v in r177.items()}
    t["TEST candidates passing"] = r181["passing"]
    print("SN184", json.dumps(t, indent=1), flush=True)
    out_path.write_text(json.dumps(t, indent=1, default=float), encoding="utf-8")
