"""After the verdict, a diagnostic that changes no verdict: how often is an account stuck when the assumed cost moves by a few rupees?

The same three books as the cliff test, at extra costs of 195, 198, 199, 201, 202 and 205 per lot (2.5% and less). One account from January 2023.

    N08_YEAR=<year> python cliff_map.py --jobs 6     (the years in order, 2023 first)
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import n10b_lab as B  # noqa: E402

T, Y, YEAR, YEARS, LOCAL = B.T, B.Y, B.YEAR, B.YEARS, B.LOCAL
RATES = (195.0, 198.0, 199.0, 201.0, 202.0, 205.0)


def books() -> dict:
    base = {"CUSHION": B.base_cushion("CUSHION"), "R2_THIRD_C": B.r2("R2_THIRD_C", True, None), "R2_THIRD_CW": B.r2("R2_THIRD_CW", True, B.WATCH)}
    earlier = YEARS[:YEARS.index(YEAR)]
    out = {}
    for name, book in base.items():
        for rate in RATES:
            tag = f"{name}|{int(rate)}"
            b = copy.deepcopy(book)
            b["cost"] = [rate, 5.0]
            b["label"] = f"N091|CARRY|N10C|{tag}"
            if earlier:
                saved = [json.loads((LOCAL / f"keys-cliff-{y}.json").read_text(encoding="utf-8"))[tag] for y in earlier]
                b["carry"] = saved
                b["n091"]["state_from"] = saved[-1].rsplit("_", 1)[-1]
            out[tag] = b
    return out


def report() -> None:
    out = {}
    for name in ("CUSHION", "R2_THIRD_C", "R2_THIRD_CW"):
        row = {}
        for rate in RATES:
            tag = f"{name}|{int(rate)}"
            net = {y: sum(float(t["net_pnl"]) for t in json.loads((Y.EVALS / f"{json.loads((LOCAL / f'keys-cliff-{y}.json').read_text(encoding='utf-8'))[tag]}.json").read_text(encoding="utf-8"))["trades"]) for y in YEARS}
            row[int(rate)] = {"end": round(250000 + sum(net.values())), "by_year": {y: round(v) for y, v in net.items()}}
        ends = [r["end"] for r in row.values()]
        out[name] = {"by_cost": row, "lowest": min(ends), "highest": max(ends), "stuck_below_2_5_lakh": sum(e < 250000 for e in ends), "runs": len(ends)}
    T.X.write(HERE / "cliff-map.json", out)
    print(json.dumps(out), flush=True)


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("--jobs", type=int, default=6)
    cli.add_argument("--report", action="store_true")
    a = cli.parse_args()
    if a.report:
        report()
    else:
        B.require_freeze()
        T.run_phase("cliff", books(), a.jobs)


if __name__ == "__main__":
    main()
