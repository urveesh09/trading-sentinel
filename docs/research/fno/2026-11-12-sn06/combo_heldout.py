"""After the verdict (descriptive): the combination N11-days -> N11, other days -> SN06, with each year's SN06 pick
chosen WITHOUT that year (the fold's held-out pick). Fixed Rs 15,000 wallet, one lot, +Rs 205."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "2026-11-12-sn03")]
import sn06 as Z, sn03 as B
R = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
out = {}
for y in Z.YEARS:
    Y = B.Year(y); n11 = Y.sigs("N11"); g = R["loyo"][y]["real"]["genome"]
    rows = {"bench": [], "sn06_other_days": [], "combo": [], "sn06_on_n11_days": []}
    for S in Y.ordered():
        b = B.play_day(S, n11.get(S.day, []), {}, 15000.0, 3000.0)["net"]
        s = Z.run_day(S, g)["net"]
        rows["bench"].append(b)
        if S.day in n11:
            rows["combo"].append(b); rows["sn06_on_n11_days"].append(s)
        else:
            rows["combo"].append(s); rows["sn06_other_days"].append(s)
    out[y] = {k: {"net": round(sum(v)), "won": sum(x > 0 for x in v), "lost": sum(x < 0 for x in v),
                  "none": sum(x == 0 for x in v), "refilled": round(sum(-x for x in v if x < 0))} for k, v in rows.items()}
    print(y, {k: (v["net"], v["won"], v["lost"], v["none"], v["refilled"]) for k, v in out[y].items()}, flush=True)
tot = {k: sum(out[y][k]["net"] for y in Z.YEARS) for k in out["2023"]}
print("held-out totals", tot)
(HERE / "results-combo-heldout.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
