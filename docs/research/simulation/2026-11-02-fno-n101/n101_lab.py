"""Frozen N10.1 research wrappers. Import through driver.py exactly once per worker."""
from __future__ import annotations

import argparse
import bisect
import copy
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())
OLD = HERE.parent / "2026-11-01-fno-n10"
sys.path[:0] = [str(HERE), str(OLD)]
import n10b_lab as B
import n101_rules as R
from fno_costs import calc_fno_costs
from config import settings

T, M, Z, Y, X = B.T, B.M, B.Z, B.Y, B.X
YEAR, YEARS = B.YEAR, B.YEARS
LOCAL = HERE / "_local"
# Module-level bindings are essential for fresh Windows worker imports.
B.LOCAL = T.LOCAL = M.LOCAL = X.LOCAL = LOCAL
Y.EVALS = LOCAL / "evals"
Y.EVALS.mkdir(parents=True, exist_ok=True)
MAX_EVENTS = 50000


def event(engine, row):
    rows = engine._n101_events
    if len(rows) >= MAX_EVENTS:
        raise RuntimeError("bounded decision receipt overflow; result unavailable")
    rows.append(row)


@lru_cache(maxsize=1)
def paper_rows():
    out = []
    for year in YEARS:
        key = json.loads((Z.LOCAL / f"keys-diag-{year}.json").read_text())["DIAG"]
        for t in json.loads((Z.LOCAL / f"evals-{year}" / f"{key}.json").read_text())["trades"]:
            out.append((datetime.fromisoformat(t["exit_time"]), t))
    return tuple(sorted(out, key=lambda r: (r[0], r[1]["entry_time"], r[1]["tradingsymbol"])))


_refund = B.refund


def refund(engine, equity, now):
    if not engine.book.get("n101"):
        return _refund(engine, equity, now)
    rows = paper_rows()
    prior = [t for at, t in rows if at < now]
    receipt = engine._n091_receipts[-1]
    current = receipt["full_reserves"][1]
    reserves = [M.full_reserve(t["entry_premium"], 65, 1, engine.book.get("cost")) for t in prior[-20:]]
    floor = engine._n091_budget.floor
    ok, typical = R.genuinely_stuck(equity, floor, len(engine._n091_book.open), current, reserves)
    changed = _refund(engine, equity, now) if ok else False
    event(engine, {"kind": "watch", "at": now.isoformat(), "equity": equity, "floor_before": floor,
                   "floor_after": engine._n091_budget.floor, "open_count": len(engine._n091_book.open),
                   "current_reserve": current, "typical_reserve": typical, "eligible": ok,
                   "released": changed, "prior_closed": len(prior),
                   "latest_evidence_exit": rows[len(prior)-1][0].isoformat() if prior else None})
    return changed


B.refund = refund
_maybe_add = T.maybe_add


def maybe_add(engine, book, leg, obs, now):
    if (engine.book.get("n101") or {}).get("mode") != "PREMIUM_LOCK":
        return _maybe_add(engine, book, leg, obs, now)
    state = T.state_of(leg)
    cfg = engine.book["n10"]
    if state is None or state["stopped"] or state["next"] >= len(cfg["steps"]):
        return
    if now.hour * 60 + now.minute >= settings.FNO_ENTRY_END_MIN or leg.lots < 2:
        return
    progress = T.R.progress_r(leg.direction, leg.entry_underlying, state["risk_points"], obs.future.ltp)
    if progress is None or progress < cfg["steps"][0][0]:
        return
    minute = now.replace(second=0, microsecond=0)
    if state.get("n101_last_attempt") == minute:
        return
    state["n101_last_attempt"] = minute
    row = {"kind": "add", "at": now.isoformat(), "parent_at": leg.entry_time, "symbol": leg.tradingsymbol,
           "progress": progress, "accepted": False, "parent_lots": leg.lots}

    def refuse(why):
        event(engine, {**row, "reason": why})
        return T.refuse(engine, state, f"n101_{why}")

    q = obs.options.get(leg.token)
    if q is None or not all(R.finite_positive(v) for v in (q.ask, q.bid)) or q.ask < q.bid:
        return refuse("no_quote")
    if leg.lots + len(state["children"]) + 1 > cfg["max_total"]:
        return refuse("max_total")
    stance = engine._stance(book, now)
    if engine._halts(book, now) or stance.single_leg_halted_today:
        return refuse("brake")
    qty = leg.lot_size
    premium = sum(x.entry_premium * x.qty for x in book.open.values()) + T.children_premium(book)
    if premium + q.ask * qty > float(settings.FNO_MAX_OPEN_PREMIUM_PCT) * book.equity:
        return refuse("premium_cap")
    child_stop = round(q.ask * (1.0 - float(settings.FNO_STOP_PREMIUM_PCT)), 2)
    child_risk = max(0.0, -R.net_at(q.ask, child_stop, qty, T.R.extra_cost(state["cost"], 1), calc_fno_costs))
    limit = min(T.R.budget(book.equity, float(settings.FNO_MAX_RISK_PCT),
                           float(settings.FNO_MAX_LOSS_PER_TRADE), stance.multiplier),
                B.FLAT_RISK * min(1.0, max(0.0, float(stance.multiplier))))
    row.update(ask=q.ask, bid=q.bid, child_stop=child_stop, child_risk=child_risk, limit=limit)
    if child_risk > limit:
        return refuse("risk")
    proposed = max(leg.premium_stop, R.funded_stop(leg.entry_premium, leg.qty,
                   T.R.extra_cost(state["cost"], leg.lots), child_risk, calc_fno_costs))
    row["proposed_parent_stop"] = proposed
    if proposed >= q.bid:
        return refuse("profit_unfunded")
    reserve = M.open_reserve(book, state["cost"])
    engine._n091_budget = M.R.advance(engine._n091_budget, book.equity, reserve, engine._n091_drawdown)
    row.update(equity=book.equity, floor=engine._n091_budget.floor, open_reserve=reserve,
               child_reserve=M.full_reserve(q.ask, qty, 1, state["cost"]))
    if row["floor"] + reserve + row["child_reserve"] > book.equity + 1e-8:
        return refuse("reserve")
    parent_net = R.net_at(leg.entry_premium, proposed, leg.qty,
                         T.R.extra_cost(state["cost"], leg.lots), calc_fno_costs)
    assert parent_net >= child_risk - 1e-7
    child = {"step": 0, "at": now.isoformat(), "ask": q.ask, "qty": qty, "future": obs.future.ltp,
             "progress": round(progress, 4), "level": leg.entry_underlying, "premium_stop": child_stop,
             "risk": child_risk, "planned_total": child_risk, "limit": limit, "exit_at": None,
             "n101_parent_stop_before": leg.premium_stop, "n101_parent_stop": proposed,
             "n101_parent_stop_net": parent_net, "n101_child_stop_net": -child_risk}
    state["children"].append(child)
    state["next"] += 1
    state["reference"] = q.ask
    leg.premium_stop = proposed
    engine.notes["n10_added"] += 1
    event(engine, {**row, "accepted": True, "reason": "", "parent_stop_net": parent_net})


T.maybe_add = maybe_add
_run = Y.BookReplay.run


def run_book(engine, start, end):
    engine._n101_events = []
    result = _run(engine, start, end)
    key = Y.task_key(engine.book, engine.source, (start, end))
    watch = getattr(engine, "_n10_watch", None)
    X.write(LOCAL / "decisions" / f"{key}.json", {"events": engine._n101_events, "watch_terminal": watch})
    # Original N10 writes a digest alias; this immutable window snapshot is the evidence.
    if watch is not None:
        X.write(LOCAL / "states" / f"watch-window-{key}.json", watch)
    return result


Y.BookReplay.run = run_book


def candidate(name):
    b = copy.deepcopy(B.r2(name, True, B.WATCH))
    b["label"] = f"N101|{name}"
    b["n101"] = {"contract": "v1", "mode": name}
    return b


def controls():
    strict = copy.deepcopy(B.r2("STRICT", True, B.WATCH))
    strict["n10"]["no_retry"] = True
    return {"N08": Z.n08(), "CUSHION": M.candidates()["CUSHION"],
            "N10": B.r2("CONTROL", True, B.WATCH), "STRICT": strict}


_refuse = T.refuse


def strict_refuse(engine, state, why):
    _refuse(engine, state, why)
    if engine.book["n10"].get("no_retry"):
        state["next"] = 99


T.refuse = strict_refuse
NAMES = ("WATCH_FLAT", "PREMIUM_LOCK")
COSTS = (199, 200, 202, 400)


def books(phase):
    if phase == "controls":
        return controls()
    if phase == "annual":
        out = {}
        for name in NAMES:
            for extra in (200, 400):
                b = candidate(name)
                b["label"] += f"|cost{extra}"
                b["cost"] = [float(extra), extra / 40.0]
                out[f"{name}|{extra}"] = b
        return out
    if phase == "carry":
        out = {}
        previous = YEARS[:YEARS.index(YEAR)]
        for name in ("N10", *NAMES):
            for extra in COSTS:
                b = B.r2("CONTROL", True, B.WATCH) if name == "N10" else candidate(name)
                title = f"{name}|{extra}"
                b["label"] = f"N091|CARRY|N101|{title}"
                b["cost"] = [float(extra), extra / 40.0]
                if previous:
                    saved = [json.loads((LOCAL / f"keys-carry-{y}.json").read_text())[title] for y in previous]
                    b["carry"] = saved
                    b["n091"]["state_from"] = saved[-1].rsplit("_", 1)[-1]
                out[title] = b
        return out
    raise ValueError(phase)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def verify():
    target = HERE / "freeze.json"
    frozen = json.loads(target.read_text())
    committed = subprocess.check_output(["git", "show", f"HEAD:{target.relative_to(ROOT).as_posix()}"], cwd=ROOT)
    assert json.loads(committed) == frozen, "freeze must be committed before replay"
    for name, expected in frozen["sources"].items():
        assert sha(ROOT / name) == expected, f"source changed {name}"
    for row in frozen["inputs"]:
        assert sha(ROOT / row["path"]) == row["sha256"], f"input changed {row['path']}"
    B.require_freeze()
    if YEAR == "2023":
        assert sys.modules["lab_gap"].DAILY.name == "daily-2023.json"
    return frozen


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("phase", choices=("describe", "controls", "annual", "carry"))
    cli.add_argument("--jobs", type=int, default=2)
    a = cli.parse_args()
    assert 1 <= a.jobs <= 2
    if a.phase == "describe":
        X.write(LOCAL / f"binding-{YEAR}.json", {"year": YEAR, "window": B.C.WINDOW,
                "cache": str(Y.CACHES["year"].relative_to(ROOT)), "books": {p: books(p) for p in ("controls", "annual")}})
        return
    verify()
    current = books(a.phase)
    Z.N.run_books(current, a.jobs)
    X.write(LOCAL / f"keys-{a.phase}-{YEAR}.json", {n: Y.task_key(b, "year", B.C.WINDOW) for n, b in current.items()})
    print("DONE", a.phase, YEAR, len(current), flush=True)
