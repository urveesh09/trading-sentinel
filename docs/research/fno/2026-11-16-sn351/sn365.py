"""SN365: the auction's information on Gold's own decisions (PLAN.md section 2, frozen before any SN365 number).

Gold v5's replay at Rs 205 (sn301/gw.py through sn339_350.install(), parity Rs 8,50,882), trades Dec 8, 2025 - Oct 28,
2026. Each trade is labelled AGREE when its side matches the price-only auction gap's sign (g from sn353b.auctions: CE and
g > 0, or PE and g < 0), else DISAGREE; a trade on a day without an auction price is NO_AUCTION (reported, not tested).
Measured: net per lot (trade net / its total lots), win rate, and a two-sided 10,000-shuffle permutation p-value of
mean(AGREE) - mean(DISAGREE) (seed 365). Size note (forward observation only) only if p < 0.10 and AGREE's net per lot is
> 0 and >= 2 x max(DISAGREE's, 0). Otherwise "no information".
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "2026-11-16-sn331"))
import sn339_350 as Q  # noqa: E402
import sn353b  # noqa: E402

OUT = HERE / "results-sn365.json"


def main():
    if OUT.exists():
        raise SystemExit("SN365 is run once")
    Q.install()
    row, days, log = Q.run(205.0)
    assert row["net"] == 850882, row["net"]
    trades = [x for x in log if sn353b.LO <= x["day"] < sn353b.HI]
    auc = sn353b.auctions(sorted({x["day"] for x in trades}))
    rows = []
    for x in trades:
        lots = sum(p[1] for p in x["pieces"]) or x["lots0"]
        a = auc.get(x["day"])
        if a is None or a["g"] == 0:
            lab = "NO_AUCTION"
        else:
            lab = "AGREE" if (x["opt"] == "CE") == (a["g"] > 0) else "DISAGREE"
        rows.append({"day": x["day"], "opt": x["opt"], "lots": lots, "net": round(x["net"], 2), "per_lot": x["net"] / lots,
                     "g": None if a is None else a["g"], "label": lab, "reason": x["reason"]})
    grp = {k: np.array([r["per_lot"] for r in rows if r["label"] == k]) for k in ("AGREE", "DISAGREE", "NO_AUCTION")}
    res = {"trades": len(rows), "by_label": {k: {"n": len(v), "per_lot": round(float(v.mean()), 1) if len(v) else None,
                                                  "win_pct": round(100 * float((v > 0).mean()), 1) if len(v) else None,
                                                  "total_net": round(sum(r["net"] for r in rows if r["label"] == k))}
                                              for k, v in grp.items()}}
    a, d = grp["AGREE"], grp["DISAGREE"]
    if len(a) and len(d):
        obs = float(a.mean() - d.mean())
        pool = np.concatenate([a, d])
        rng = random.Random(365)
        idx = list(range(len(pool)))
        hits = 0
        for _ in range(10000):
            rng.shuffle(idx)
            sa = pool[idx[:len(a)]].mean()
            sd = pool[idx[len(a):]].mean()
            hits += abs(sa - sd) >= abs(obs) - 1e-9
        p = hits / 10000
        note = p < 0.10 and a.mean() > 0 and a.mean() >= 2 * max(float(d.mean()), 0.0)
        res.update(diff_per_lot=round(obs, 1), p_two_sided=p, size_note=bool(note))
    res["rows"] = rows
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}))


if __name__ == "__main__":
    main()
