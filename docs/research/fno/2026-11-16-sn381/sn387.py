"""SN387: close Gold's 2022 exam (PLAN.md section 1, frozen at c6e99cee; details fixed here before any SN387 number).

  python sn387.py reconcile           242 market dates vs 190 option sessions, by reason / month / weekday / volatility
  N08_YEAR=<y> SN387_MODE=carry python sn387.py carry <y>     y = 2022, 2023, 2024, 2025, 2026, IN ORDER
  python sn387.py score               N10 sheet D

N10 sheet D (EXAM_2022.md): one account from the first 2022 session through 2026 for N09.1 CUSHION and for N10 with
WATCH (n10b_lab.account_books()["CUSHION"] and ["R2_THIRD_CW"], unchanged), fresh Rs 2.5 lakh once, the budget and
floor carried year to year by N09.1's own state mechanism (label prefix N091|CARRY|, state_from = the previous year's
key). YES if N10 with WATCH never falls below 75% of its best closed equity and ends at or above CUSHION's end.
Wiring: each year on its own route (2022 = n08_shim's point; 2023 = N08's sealed 2023 point; 2024 - 2026 the house
routes); results, receipts and carried states in SN381's _local (never another study's folder); WATCH's paper evidence =
N08's one-lot paper trades of 2022 (SN366) and 2023 - 2026 (N09's saved diag runs, copied read-only into
_local/n09), read strictly before each decision; N09's volatility reading for 2022 from the 2022 point's contiguous
daily file (SOURCE_CORRECTION_2022.md), the house files for 2023 - 2026.
"""
from __future__ import annotations

import collections
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
SIM = HERE.parents[1] / "simulation"
LOCAL = HERE / "_local"
CHECK = os.environ.get("SN387_CHECK") == "1"         # wiring check: N10's own account from 2023 must be reproduced
CHAIN = ("2023", "2024", "2025", "2026") if CHECK else ("2022", "2023", "2024", "2025", "2026")
TAG = "check" if CHECK else "carry"
NAMES = ("CUSHION", "R2_THIRD_CW")
MODE = os.environ.get("SN387_MODE")

if MODE == "carry":
    sys.path.insert(0, str(FNO / "2026-11-16-sn366"))
    import n08_shim  # noqa: E402
    N = n08_shim.install()
    sys.path.insert(0, str(SIM / "2026-11-01-fno-n10"))
    import n10b_lab as Bb  # noqa: E402
    T, M, Z, Y = Bb.T, Bb.M, Bb.Z, Bb.Y
    YEAR = N.B.YEAR
    N09 = LOCAL / "n09"
    Z.LOCAL = N09
    M.LOCAL = LOCAL
    Y.EVALS = LOCAL / f"{TAG}-evals"
    Y.EVALS.mkdir(parents=True, exist_ok=True)

    def shadow_names():
        names = []
        for y in CHAIN:
            kf = N09 / f"keys-diag-{y}.json"
            names.append(f"evals-{y}/{json.loads(kf.read_text(encoding='utf-8'))['DIAG']}.json")
        return tuple(names)
    Bb.shadow_names = shadow_names
    if YEAR == "2022":
        Z.DAILY_SOURCES = (FNO / "2026-11-16-sn366" / "_local" / "daily-2022.json",)
        Z.vol_table.cache_clear()


def prepare_evidence():
    """Copy N09's saved one-lot paper runs (2023 - 2026) and SN366's 2022 run into _local/n09 (read-only copies)."""
    dst = LOCAL / "n09"
    dst.mkdir(parents=True, exist_ok=True)
    srcs = {y: SIM / "2026-11-01-fno-n09" / "_local" for y in ("2023", "2024", "2025", "2026")}
    srcs["2022"] = FNO / "2026-11-16-sn366" / "_local" / "n09"
    for y, src in srcs.items():
        keys = json.loads((src / f"keys-diag-{y}.json").read_text(encoding="utf-8"))
        (dst / f"keys-diag-{y}.json").write_text(json.dumps(keys), encoding="utf-8")
        (dst / f"evals-{y}").mkdir(exist_ok=True)
        f = src / f"evals-{y}" / f"{keys['DIAG']}.json"
        shutil.copyfile(f, dst / f"evals-{y}" / f.name)


def carry(year):
    assert year == YEAR, (year, YEAR)
    if year == CHAIN[0] and not (LOCAL / "n09" / "keys-diag-2022.json").exists():
        prepare_evidence()
    books = {}
    earlier = CHAIN[:CHAIN.index(year)]
    for name in NAMES:
        import copy
        b = copy.deepcopy(Bb.account_books()[name])
        b["label"] = f"N091|CARRY|N10B|{name}"
        if earlier:
            saved = [json.loads((LOCAL / f"keys-{TAG}-{y}.json").read_text(encoding="utf-8"))[name] for y in earlier]
            b["carry"] = saved
            b["n091"]["state_from"] = saved[-1].rsplit("_", 1)[-1]
        books[name] = b
    keys = {n: Y.task_key(b, "year", N.C.WINDOW) for n, b in books.items()}
    assert not any((Y.EVALS / f"{k}.json").exists() for k in keys.values()), "a carry year is run once"
    N.run_books(books, 2)
    (LOCAL / f"keys-{TAG}-{year}.json").write_text(json.dumps(keys, indent=1), encoding="utf-8")
    print("CARRY", year, {n: len(json.loads((Y.EVALS / f"{k}.json").read_text(encoding="utf-8"))["trades"]) for n, k in keys.items()}, flush=True)


def check_score():
    """The 2023-start chain must equal N10's stored one-account run (keys-carry2-<y>, n10 _local/evals), trade for trade."""
    out_path = HERE / "results-sn387-carry-check.json"
    assert not out_path.exists()
    n10l = SIM / "2026-11-01-fno-n10" / "_local"
    sys.path.insert(0, str(SIM / "2026-11-01-fno-n10"))
    econ = ("entry_time", "tradingsymbol", "entry_premium", "exit_time", "exit_premium", "exit_reason", "net_pnl", "entry_qty")
    res = {}
    for y in ("2023", "2024", "2025", "2026"):
        mine = json.loads((LOCAL / f"keys-check-{y}.json").read_text(encoding="utf-8"))
        theirs = json.loads((n10l / f"keys-carry2-{y}.json").read_text(encoding="utf-8"))
        for name in NAMES:
            a = json.loads((LOCAL / "check-evals" / f"{mine[name]}.json").read_text(encoding="utf-8"))["trades"]
            b = json.loads((n10l / "evals" / f"{theirs[name]}.json").read_text(encoding="utf-8"))["trades"]
            res[f"{name} {y}"] = {"equal": [{k: t.get(k) for k in econ} for t in a] == [{k: t.get(k) for k in econ} for t in b],
                                  "trades": len(a), "net": round(sum(t["net_pnl"] for t in a), 2), "stored_net": round(sum(t["net_pnl"] for t in b), 2)}
    res["pass"] = all(v["equal"] for v in res.values() if isinstance(v, dict))
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


def score():
    out_path = HERE / "results-sn387-n10-sheet-D.json"
    assert not out_path.exists()
    res = {}
    for name in NAMES:
        eq, best, worst_ratio, ends, per_year = None, None, 1.0, None, {}
        for y in CHAIN:
            key = json.loads((LOCAL / f"keys-carry-{y}.json").read_text(encoding="utf-8"))[name]
            ev = json.loads((LOCAL / "carry-evals" / f"{key}.json").read_text(encoding="utf-8"))
            if eq is None:
                eq = float(ev["start_equity"])
                best = eq
            assert abs(float(ev["start_equity"]) - eq) < 1.0, (name, y, ev["start_equity"], eq)
            y0 = eq
            for t in sorted(ev["trades"], key=lambda t: t["exit_time"]):
                eq += float(t["net_pnl"])
                best = max(best, eq)
                worst_ratio = min(worst_ratio, eq / best)
            per_year[y] = round(eq - y0)
        res[name] = {"end_equity": round(eq), "best_closed_equity": round(best), "lowest_vs_best": round(worst_ratio, 4), "per_year": per_year}
    w, c = res["R2_THIRD_CW"], res["CUSHION"]
    res["D_watch_keeps_its_promise"] = bool(w["lowest_vs_best"] >= 0.75 and w["end_equity"] >= c["end_equity"])
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


def reconcile():
    out_path = HERE / "results-sn387-reconcile.json"
    assert not out_path.exists()
    b = json.loads((FNO / "2026-11-16-sn366" / "results-sn366-bind-2022.json").read_text(encoding="utf-8"))
    man = json.loads((FNO / "2026-11-16-sn366" / "_local" / "dataset-nifty-2022" / "manifest.json").read_text(encoding="utf-8"))
    cal = man.get("weekly_expiry_calendar", {})
    expiries = set(cal.values()) if isinstance(cal, dict) else set(cal)
    noopt = b["sessions_without_any_option"]
    import datetime as dt
    rows = []
    for d in noopt:
        rows.append({"day": d, "weekday": dt.date.fromisoformat(d).strftime("%a"), "is_weekly_expiry": d in expiries})
    vt = json.loads((FNO / "2026-11-16-sn366" / "results-sn366-volcheck.json").read_text(encoding="utf-8"))
    res = {"market_dates": b["sessions"], "option_sessions": b["sessions_with_options"], "without_options": len(noopt),
           "without_options_that_are_weekly_expiries": sum(r["is_weekly_expiry"] for r in rows),
           "without_options_not_expiry": [r["day"] for r in rows if not r["is_weekly_expiry"]],
           "by_weekday": dict(collections.Counter(r["weekday"] for r in rows)),
           "by_month": dict(collections.Counter(r["day"][:7] for r in rows)),
           "reason": "the house year format stores the front weekly's options, which are absent on the expiry day itself (2023 had 53 such days); no strike or bar is missing on the 190 option sessions (bind: no bad rows, no short sessions)",
           "volatility_2022_check": vt.get("fixed")}
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items()}, indent=1))


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else None
    if step == "reconcile":
        reconcile()
    elif step == "carry":
        carry(sys.argv[2])
    elif step == "score":
        score()
    elif step == "check_score":
        check_score()
    else:
        raise SystemExit(__doc__)
