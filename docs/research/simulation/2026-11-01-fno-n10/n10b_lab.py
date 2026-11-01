"""N10 round two: WATCH and THIRD, as PLAN2.md states them. Research only. Round one's frozen files are imported and never edited.

    N08_YEAR=<year> python driver2.py panel --jobs 6     (needs the committed freeze-2.json)
    N08_YEAR=<year> python driver2.py carry --jobs 6     (run the years in order, 2023 first)
"""
from __future__ import annotations

import argparse
import bisect
import copy
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import n10_lab as T  # noqa: E402
import n10b_rules as W  # noqa: E402
from config import settings  # noqa: E402

M, Z, Y, X, C, B, L, N, R = T.M, T.Z, T.Y, T.X, T.C, T.B, T.L, T.N, T.R
LOCAL, YEAR, YEARS = T.LOCAL, T.YEAR, T.YEARS
WATCH = {"need": 20, "slice": 0.05, "deepest": 0.75}
FLAT_RISK = 5000.0

# ---- THIRD: the earned lot only on a two-lot trade, within the owner's flat limit ----------------------------------------

_maybe_add = T.maybe_add


def maybe_add(self, book, leg, obs, now):
    cfg = self.book["n10"]
    state = T.state_of(leg)
    if state is None:
        return None
    if cfg.get("parent_min") and leg.lots < cfg["parent_min"]:
        return T.refuse(self, state, "parent_lots")
    flat = cfg.get("flat_risk")
    if not flat:
        return _maybe_add(self, book, leg, obs, now)
    usual = R.budget
    R.budget = lambda equity, pct, top, multiplier: min(usual(equity, pct, top, multiplier), flat * min(1.0, max(0.0, float(multiplier))))
    try:
        return _maybe_add(self, book, leg, obs, now)
    finally:
        R.budget = usual


T.maybe_add = maybe_add

# ---- WATCH ------------------------------------------------------------------------------------------------------------


def shadow_names() -> tuple:
    """N08's own rules on paper, one lot, brakes off: N09's saved trades, all years. Only exits strictly before now are ever read."""
    return tuple(f"evals-{y}/{json.loads((Z.LOCAL / f'keys-diag-{y}.json').read_text(encoding='utf-8'))['DIAG']}.json" for y in YEARS)


def refund(engine, equity: float, now) -> bool:
    """One slice off the floor, if the paper evidence allows it."""
    cfg = engine.book["n10"]["watch"]
    watch = engine._n10_watch
    watch["best"] = max(watch["best"], equity)
    at, nets = Z.shadow_trades(shadow_names())
    upto = bisect.bisect_left(at, now)
    last = watch["last_at"]
    since = upto - (bisect.bisect_right(at, datetime.fromisoformat(last)) if last else 0)
    if not W.evidence_ok(nets[:upto], since, cfg["need"]):
        return False
    budget = engine._n091_budget
    lower = W.lowered_floor(budget.floor, watch["best"], cfg["slice"], cfg["deepest"])
    if lower is None:
        return False
    watch["slices"].append({"at": now.isoformat(), "equity": round(equity, 2), "from": round(budget.floor, 2), "to": round(lower, 2), "best": round(watch["best"], 2),
                            "evidence": round(sum(nets[:upto][-cfg["need"]:]), 2), "paper_closed_since": since})
    watch["last_at"] = now.isoformat()
    engine._n091_budget = M.R.Budget(budget.anchor, equity, lower)    # the high-water mark restarts here, or the very next check would raise the floor straight back
    engine.notes["n10_watch_slices"] += 1
    return True


_plan = M.plan


def plan(sig, snap, regime, now, state):
    out = _plan(sig, snap, regime, now, state)
    engine = M.ACTIVE
    if engine is None or not (engine.book.get("n10") or {}).get("watch"):
        return out
    engine._n10_watch["best"] = max(engine._n10_watch["best"], state.pool)
    if not out.accepted and out.reject_reason == "n091:full_premium_reserve" and refund(engine, state.pool, now):
        return _plan(sig, snap, regime, now, state)
    return out


M.plan = plan                         # N09.1's entry installs whatever this name holds
_halts = Y.BookReplay._halts


def halts(self, book, now):
    active = _halts(self, book, now)
    if (self.book.get("n10") or {}).get("watch"):
        return tuple(a for a in active if not a.startswith("drawdown_halt"))   # WATCH's floor replaces it, for these books alone
    return active


Y.BookReplay._halts = halts
_run = Y.BookReplay.run


def run_book(self, start, end):
    n10 = self.book.get("n10") or {}
    if n10.get("watch"):
        prior = self.book["n091"].get("state_from")
        self._n10_watch = (json.loads((LOCAL / "states" / f"watch-{prior}.json").read_text(encoding="utf-8")) if prior else
                           {"best": float(settings.FNO_PAPER_BANKROLL), "last_at": None, "slices": []})
    result = _run(self, start, end)
    if n10.get("watch"):
        X.write(LOCAL / "states" / f"watch-{Y.digest(self.book)}.json", self._n10_watch)
    return result


Y.BookReplay.run = run_book

# ---- books ------------------------------------------------------------------------------------------------------------


def base_cushion(label: str) -> dict:
    b = copy.deepcopy(M.candidates()["CUSHION"])
    b["label"] = f"N10B|{label}"
    b["n10"] = T.n10_cfg("NATIVE", [], "RISK", False, 2)
    return b


def r2(label: str, third: bool, watch: dict | None, x: float = 1.0) -> dict:
    b = base_cushion(label)
    if third:
        b["n10"] = {**T.n10_cfg("NATIVE", T.scaled(x), "RISK", False, 3), "parent_min": 2, "flat_risk": FLAT_RISK}
    if watch:
        b["n10"]["watch"] = dict(watch)
    return b


def annual_books() -> dict:
    out = {"R2_CW": r2("R2_CW", False, WATCH), "R2_THIRD_C": r2("R2_THIRD_C", True, None), "R2_THIRD_CW": r2("R2_THIRD_CW", True, WATCH),
           "R2_THIRD_CW@0.75": r2("R2_THIRD_CW@0.75", True, WATCH, 0.75), "R2_THIRD_CW@1.25": r2("R2_THIRD_CW@1.25", True, WATCH, 1.25)}
    for name in ("R2_CW", "R2_THIRD_CW"):
        d = copy.deepcopy(out[name])
        d.update(cost=[400.0, 10.0], label=f"N10B|COST|{name}|double")
        out[f"{name}|double"] = d
    return out


SHIFTS = {"low": [180.0, 4.5], "high": [220.0, 5.5]}


def account_books() -> dict:
    """One account from January 2023, no deposit, the floor carried. The label keeps N09.1's prefix, which is what writes the carried state."""
    base = {"CUSHION": base_cushion("CUSHION"), "R2_CW": r2("R2_CW", False, WATCH), "R2_THIRD_C": r2("R2_THIRD_C", True, None), "R2_THIRD_CW": r2("R2_THIRD_CW", True, WATCH)}
    out = dict(base)
    for name in ("CUSHION", "R2_CW", "R2_THIRD_CW"):
        for tag, cost in SHIFTS.items():
            b = copy.deepcopy(base[name])
            b["cost"] = cost
            out[f"{name}|{tag}"] = b
    for tag, change in (("need10", {"need": 10}), ("need30", {"need": 30}), ("slice2.5", {"slice": 0.025}), ("slice10", {"slice": 0.10})):
        out[f"R2_THIRD_CW|{tag}"] = r2("R2_THIRD_CW", True, {**WATCH, **change})
    return out


def carry_books() -> dict:
    earlier = YEARS[:YEARS.index(YEAR)]
    out = {}
    for name, book in account_books().items():
        b = copy.deepcopy(book)
        b["label"] = f"N091|CARRY|N10B|{name}"
        if earlier:
            saved = [json.loads((LOCAL / f"keys-carry2-{y}.json").read_text(encoding="utf-8"))[name] for y in earlier]
            b["carry"] = saved
            b["n091"]["state_from"] = saved[-1].rsplit("_", 1)[-1]
        out[name] = b
    return out


SOURCES = ("n10b_rules.py", "n10b_lab.py", "PLAN2.md", "score2.py", "test_n10b.py", "driver2.py", "stress_watch.py")


def freeze() -> None:
    target = HERE / "freeze-2.json"
    assert not target.exists(), "already frozen"
    X.write(target, {"schema": "n10b_freeze_v1", "sources": {s: T.sha(HERE / s) for s in SOURCES}, "round_one": {s: T.sha(HERE / s) for s in T.SOURCES},
                     "books": {"annual": annual_books(), "account": account_books()},
                     "note": "Written after round one's verdict and before any round-two book is scored. All four years are seen."})


def require_freeze() -> None:
    target = HERE / "freeze-2.json"
    assert json.loads(T.committed(target)) == json.loads(target.read_text(encoding="utf-8")), "freeze-2.json is not committed"
    frozen = json.loads(target.read_text(encoding="utf-8"))
    for group in ("sources", "round_one"):
        for name, value in frozen[group].items():
            assert T.sha(HERE / name) == value, f"{name} changed after the freeze"


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=("freeze", "panel", "carry"))
    cli.add_argument("--jobs", type=int, default=6)
    a = cli.parse_args()
    if a.action == "freeze":
        freeze()
        print("FROZEN", flush=True)
        return
    require_freeze()
    if a.action == "panel":
        T.run_phase("panel2", annual_books(), a.jobs)
    else:
        T.run_phase("carry2", carry_books(), a.jobs)
