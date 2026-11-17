"""SN471 post-hoc diagnostic (added AFTER SN471's verdict, disclosed; it cannot change that verdict): is the 2023-26 split
driven by Gold's few largest trades? The same AGREE - DISAGREE statistic without the best 5 / 10 trades of the pooled set,
by period, and the number of AGREE among Gold's 10 largest winners. Writes results-sn471-posthoc.json once.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "2026-11-17-sn411"))
import feat456 as F  # noqa: E402
import gold  # noqa: E402
import sn471  # noqa: E402

OUT = HERE / "results-sn471-posthoc.json"


def main():
    if OUT.exists():
        raise SystemExit("once")
    cal, rows, _ = F.features()
    zmap = {d: rows[d]["z"] for d in cal if rows[d].get("z") is not None}
    res = {}
    for name, years in (("2022", gold.Y22), ("2023-26", gold.Y2326)):
        _d, log, _ = gold.run(years, gold.DEPLOYED, 205.0)
        tr = [{"day": x["day"], "opt": x["opt"], "net": float(x["net"])} for x in log if x["day"] in zmap]
        top = sorted(tr, key=lambda t: -t["net"])
        agree = lambda t: (t["opt"] == "CE") == (zmap[t["day"]] > 0)  # noqa: E731
        res[name] = {"all": round(sn471.stat(tr, zmap)[0], 1)}
        for k in (5, 10):
            keep = top[k:]
            res[name][f"without_best_{k}"] = round(sn471.stat(keep, zmap)[0], 1)
        res[name]["agree_among_top10_winners"] = sum(agree(t) for t in top[:10])
        res[name]["agree_share_all"] = round(float(np.mean([agree(t) for t in tr])), 3)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
