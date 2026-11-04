"""Run declared arms on a panel window. Usage:
python arms.py <kite|yahoo> <start> <end> <ARM ...> [--model E25|E36|PC|E60] [--out file]

Refuses Yahoo windows before 2023-01-01 (the sealed exam) unless --exam <freeze.json>.
"""
from __future__ import annotations
import argparse, json, sys
from dataclasses import replace
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab  # noqa: E402

MODELS = {"E25": (25.0, 5.0), "E36": (36.0, 5.0), "PC": (0.0, 5.0), "E60": (60.0, 20.0)}
EXAM_START, EXAM_END = "2019-04-01", "2022-12-30"

ARMS: dict[str, lab.Arm] = {}


def arm(a: lab.Arm):
    ARMS[a.name] = a
    return a


# Round 1: execution and fee economics, shipped selection unchanged
arm(lab.Arm("BASE"))
arm(lab.Arm("THREE_EQ", sizing="equal"))
arm(lab.Arm("TWO_EQ", slots=2, sizing="equal"))
arm(lab.Arm("ONE_EQ", slots=1, sizing="equal"))
arm(lab.Arm("TWO_RISK", slots=2))
arm(lab.Arm("BASE_MIN5K", min_ticket=5000.0))
arm(lab.Arm("BASE_PESS_PH", placeholder="pess"))

_days_cache: dict = {}


def days_for(panel: str):
    if panel not in _days_cache:
        _days_cache[panel] = lab.load(HERE / f"_local/days-{panel}.pkl")
    return _days_cache[panel]


def guard(panel, start, end, exam):
    if panel == "yahoo" and start < "2023-01-01":
        if not exam:
            raise SystemExit("refused: Y-EXAM (2019-2022) is sealed; pass --exam <freeze.json>")
        freeze = json.loads(Path(exam).read_text())
        if not freeze.get("finalists"):
            raise SystemExit("refused: freeze lists no finalists")


def run(panel, start, end, names, model="E25", keep=False, extra: dict | None = None, compound=True):
    eb, xb = MODELS[model]
    days = days_for(panel)
    out = {}
    for n in names:
        a = (extra or {}).get(n) or ARMS[n]
        a = replace(a, entry_bps=eb, exit_bps=xb, compound=compound and a.compound)
        r = lab.run_book(days, a, start=start, end=end, keep_trades=keep)
        out[n] = r if keep else {"summary": r["summary"], "outcomes": r["outcomes"]}
    return out


def line(name, s):
    return (f"{name:16s} n={s['n']:4d} net={s['net']:>10,.0f} exbest={s['ex_best']:>10,.0f} "
            f"DD={s['dd_pct_peak']:5.1f}% pf={s['pf'] or 0:5.2f} win={s['win'] or 0:4.1f}% "
            f"mean={s['mean_pct'] or 0:+.2f}% med={s['median_pct'] or 0:+.2f}% "
            + " ".join(f"{y}:{v:,.0f}" for y, v in s["by_year"].items()))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("panel"); p.add_argument("start"); p.add_argument("end"); p.add_argument("arms", nargs="+")
    p.add_argument("--model", default="E25"); p.add_argument("--exam"); p.add_argument("--out")
    p.add_argument("--fixed", action="store_true", help="no compounding")
    a = p.parse_args()
    guard(a.panel, a.start, a.end, a.exam)
    res = run(a.panel, a.start, a.end, a.arms, a.model, compound=not a.fixed)
    print(f"[{a.panel} {a.start}..{a.end} model={a.model}{' fixed' if a.fixed else ''}]")
    for n, r in res.items():
        print(line(n, r["summary"]))
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
