"""After the verdict, a diagnostic that changes no verdict. PLAN.md says the lot is earned when the move "first reaches" +1R, but the frozen code tries again
at later minutes while the trade stays at or above +1R, if the first try was refused. This reads the plan strictly: one try only.

    N08_YEAR=<year> python no_retry.py annual --jobs 3
    N08_YEAR=<year> python no_retry.py carry --jobs 3     (the years in order, 2023 first)
    python no_retry.py report
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
_refuse = T.refuse


def refuse(self, state, why):
    """One try: any refusal at or above +1R ends this trade's chance of an earned lot."""
    _refuse(self, state, why)
    if self.book["n10"].get("no_retry"):
        state["next"] = 99


T.refuse = refuse


def strict(label: str) -> dict:
    b = copy.deepcopy(B.r2(label, True, B.WATCH))
    b["n10"]["no_retry"] = True
    return b


def annual() -> dict:
    d = strict("R2_THIRD_CW_STRICT")
    d.update(cost=[400.0, 10.0], label="N10B|COST|STRICT|double")
    return {"STRICT": strict("R2_THIRD_CW_STRICT"), "STRICT|double": d}


def carry() -> dict:
    b = strict("STRICT")
    b["label"] = "N091|CARRY|N10B|STRICT"
    earlier = YEARS[:YEARS.index(YEAR)]
    if earlier:
        saved = [json.loads((LOCAL / f"keys-strict-carry-{y}.json").read_text(encoding="utf-8"))["STRICT"] for y in earlier]
        b["carry"] = saved
        b["n091"]["state_from"] = saved[-1].rsplit("_", 1)[-1]
    return {"STRICT": b}


def report() -> None:
    sys.path.insert(0, str(HERE))        # N09.1's folder holds a score.py too; this study's own comes first
    sys.modules.pop("score", None)
    import score as S
    rows = {y: S.trades_of("strict-annual", y, "STRICT") for y in YEARS}
    fresh = {y: S.stats(rows[y]) for y in YEARS}
    account = S.CAPITAL + sum(float(t["net_pnl"]) for y in YEARS for t in S.trades_of("strict-carry", y, "STRICT"))
    out = {"fresh": {y: {k: round(fresh[y][k], 2) for k in ("net", "worst_day", "worst_trade", "fall_pct", "trades")} for y in YEARS}, "whole": {k: round(v, 2) for k, v in S.whole(fresh).items()}, "account": round(account),
           "double": round(sum(float(t["net_pnl"]) for y in YEARS for t in S.trades_of("strict-annual", y, "STRICT|double"))), "without_top_five": round(S.without_best(rows)), "earned": S.add_stats([t for y in YEARS for t in rows[y]])}
    (HERE / "results-strict.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out))


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=("annual", "carry", "report"))
    cli.add_argument("--jobs", type=int, default=3)
    a = cli.parse_args()
    if a.action == "report":
        report()
        return
    B.require_freeze()
    T.run_phase(f"strict-{a.action}", {"annual": annual, "carry": carry}[a.action](), a.jobs)


if __name__ == "__main__":
    main()
