"""SN12 - the benchmark at different FIXED wallet sizes (refilled after a loss): lots = 1 per Rs 15,000 (and a 1-lot
variant), day loss limit 20% of the wallet, the OTM substitute only when the wallet cannot buy one lot. Descriptive."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "2026-11-12-sn03")]
import sn03 as B
out = {}
years = {y: B.Year(y) for y in B.YEARS}
for W in (15000, 20000, 25000, 30000, 45000, 60000):
    for lots_rule in ("1 lot", "1 lot per 15k"):
        lots = 1 if lots_rule == "1 lot" else max(1, W // 15000)
        if lots_rule == "1 lot per 15k" and lots == 1 and W != 15000:
            continue
        per = {y: B.year_result(years[y], {"lots": lots}, wallet=float(W)) for y in B.YEARS}
        tot = sum(per[y]["net"] for y in B.YEARS)
        key = f"W {W} | {lots_rule}"
        out[key] = per
        print(f"{key:24s}", " ".join(f"{per[y]['net']:>7}/{per[y]['refilled']:<6}" for y in B.YEARS), f"total {tot:>8}",
              "won/lost/none", sum(per[y]["green"] for y in B.YEARS), sum(per[y]["red"] for y in B.YEARS), sum(per[y]["none"] for y in B.YEARS),
              "worst", min(per[y]["worst"] for y in B.YEARS), f"per year on wallet {100*tot/3.8/W:.0f}%", flush=True)
(HERE / "results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
