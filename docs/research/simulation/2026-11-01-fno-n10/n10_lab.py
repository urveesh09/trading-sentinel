"""N10: N08's signals and exits, the second lot earned at +1R. Research only; no application module imports this file.

Run through driver.py so Windows workers import this module exactly once. N08_YEAR chooses the year.

    N08_YEAR=<year> python driver.py parity --jobs 6
    python driver.py freeze
    N08_YEAR=<year> python driver.py panel --jobs 6     (needs the committed freeze)
    N08_YEAR=<year> python driver.py costs --jobs 6
    N08_YEAR=<year> python driver.py carry --jobs 6     (run the years in order, 2023 first)
    N08_YEAR=<year> python driver.py random --jobs 6
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())
sys.path[:0] = [str(HERE), str(HERE.parent / "2026-11-01-fno-n091")]
import n091_lab as M  # noqa: E402
import n10_rules as R  # noqa: E402
import fno_entry_plan as EP  # noqa: E402
from config import settings  # noqa: E402
from fno_costs import calc_fno_costs  # noqa: E402

Z = M.Z
Y, X, C, B, L, N = Z.Y, Z.X, Z.C, Z.B, Z.L, Z.N
replay = Y.replay
YEAR = Z.YEAR
YEARS = ("2023", "2024", "2025", "2026")
LOCAL = HERE / "_local"
Y.EVALS = LOCAL / "evals"
Y.EVALS.mkdir(parents=True, exist_ok=True)
X.LOCAL = LOCAL
M.LOCAL = LOCAL
Y.KEEP = tuple(dict.fromkeys((*Y.KEEP, "n10_children", "n10_native")))
ENGINE: dict = {"now": None}
FIRST = [[1.0, 0.0]]                 # (reach this many R, the earned lot's stop in R from entry)
LADDER = [[1.0, 0.0], [2.0, 1.0]]
OUT_OF_REACH = [[1e9, 0.0]]


def scaled(x: float, ladder: bool = False) -> list:
    """The neighbours: the first step moves, the stop stays at entry; a second step keeps its 1R spacing above the first."""
    return [[x, 0.0], [x + 1.0, x]] if ladder else [[x, 0.0]]


# ---- what an open trade holds -----------------------------------------------------------------------------------------


def state_of(leg):
    return getattr(leg, "_n10", None)


def open_children(leg) -> list:
    state = state_of(leg)
    return [c for c in state["children"] if c["exit_at"] is None] if state else []


def children_premium(book) -> float:
    return sum(c["ask"] * c["qty"] for leg in book.open.values() for c in open_children(leg))


def settle_child(leg, child: dict, at, bid: float, reason: str) -> None:
    """An earned lot's own round trip. Its cash reaches equity now, as a banked part of the same trade, so the brakes see one trade."""
    state = state_of(leg)
    qty = child["qty"]
    gross = (bid - child["ask"]) * qty
    extra = R.extra_cost(state["cost"], 1)
    net = gross - calc_fno_costs(child["ask"], bid, qty) - extra
    child.update(exit_at=at.isoformat(), bid=bid, reason=reason, gross=round(gross, 4), net=round(net, 4), extra=extra)
    leg.fills.append({"kind": "N10_EARNED", "at": at.isoformat(), "qty": qty, "price": bid, "entry_premium": leg.entry_premium,
                      "gross_pnl": round(gross, 4), "net_pnl": round(net, 4)})
    book = state["book"]
    book.equity += net
    book.closes.append((at, net, "SINGLE_LEG_PARTIAL"))


_close = replay._close_record


def close_record(leg, at, price, reason, fut):
    """Any close of the first lot takes the earned lots with it, at the same price."""
    state = state_of(leg)
    if state:
        for child in open_children(leg):
            settle_child(leg, child, at, price, f"with_first:{reason}")
    record, final = _close(leg, at, price, reason, fut)
    if state:
        record["n10_children"] = copy.deepcopy(state["children"])
        record["n10_native"] = state["native"]
    return record, final


replay._close_record = close_record

# ---- CUSHION sees the earned lots too ----------------------------------------------------------------------------------

_open_reserve = M.open_reserve


def open_reserve(book, cost):
    return _open_reserve(book, cost) + sum(M.full_reserve(c["ask"], c["qty"], 1, cost) for leg in book.open.values() for c in open_children(leg))


M.open_reserve = open_reserve

# ---- entries: the unchanged planner, then one lot ----------------------------------------------------------------------

_planner = EP.plan_single_leg_entry


def plan(sig, snap, regime, now, state):
    engine = ENGINE["now"]
    if engine is None:
        return _planner(sig, snap, regime, now, state)
    extra = children_premium(engine._n10_book)
    if extra:
        state = replace(state, open_premium=state.open_premium + extra)
    planned = _planner(sig, snap, regime, now, state)
    if not planned.accepted:
        return planned
    if engine._n10_native is None:
        engine._n10_native = planned.lots
    if engine.book["n10"]["entry"] == "ONE" and planned.lots > 1:
        saved = settings.FNO_MAX_LOTS, settings.FNO_MAX_LOTS_PROVEN
        try:
            settings.FNO_MAX_LOTS = settings.FNO_MAX_LOTS_PROVEN = 1
            planned = _planner(sig, snap, regime, now, state)
        finally:
            settings.FNO_MAX_LOTS, settings.FNO_MAX_LOTS_PROVEN = saved
        assert not planned.accepted or planned.lots == 1
    return planned


EP.plan_single_leg_entry = plan
M._plan = plan                       # N09.1's wrapper calls this and restores this
_entry = Y.BookReplay._entry


def entry(self, book, obs, frame, day, now):
    if not self.book.get("n10"):
        return _entry(self, book, obs, frame, day, now)
    assert ENGINE["now"] is None
    before = book.next_id
    self._n10_book, self._n10_native = book, None
    ENGINE["now"] = self
    try:
        _entry(self, book, obs, frame, day, now)
    finally:
        ENGINE["now"] = None
    if book.next_id != before:
        leg = book.open[before]
        leg._n10 = {"book": book, "cost": self.book.get("cost"), "native": self._n10_native, "risk_points": abs(leg.entry_underlying - leg.stop_underlying),
                    "children": [], "next": 0, "stopped": False, "reference": leg.entry_premium, "refused": set()}


Y.BookReplay._entry = entry

# ---- management: the earned lot's own stop, then the add ---------------------------------------------------------------


def refuse(self, state: dict, why: str) -> None:
    if why not in state["refused"]:
        state["refused"].add(why)
        self.notes[f"n10_refused_{why}"] += 1


def maybe_add(self, book, leg, obs, now) -> None:
    cfg = self.book["n10"]
    state = state_of(leg)
    steps = cfg["steps"]
    if state is None or state["stopped"] or state["next"] >= len(steps) or now.hour * 60 + now.minute >= settings.FNO_ENTRY_END_MIN:
        return
    reach, level_r = steps[state["next"]]
    progress = R.progress_r(leg.direction, leg.entry_underlying, state["risk_points"], obs.future.ltp)
    if progress is None or progress < reach:
        return
    quote = obs.options.get(leg.token)
    if quote is None or quote.ask <= 0 or quote.bid <= 0:
        return refuse(self, state, "no_quote")
    if leg.lots + len(state["children"]) + 1 > cfg["max_total"]:
        return refuse(self, state, "max_total")
    if cfg["eligibility"] == "NATIVE" and state["native"] < 2:
        return refuse(self, state, "native_one_lot")
    if cfg.get("vol") and Z.R.vol_lots(*Z.vol_table().get(now.date().isoformat(), (None, None))) < 2:
        return refuse(self, state, "vol")
    stance = self._stance(book, now)
    if self._halts(book, now) or stance.single_leg_halted_today:
        return refuse(self, state, "brake")
    qty = leg.lot_size
    open_premium = sum(x.entry_premium * x.qty for x in book.open.values()) + children_premium(book)
    if open_premium + quote.ask * qty > float(settings.FNO_MAX_OPEN_PREMIUM_PCT) * book.equity:
        return refuse(self, state, "premium_cap")
    stop_pct = float(settings.FNO_STOP_PREMIUM_PCT)
    planned = R.parent_risk(leg.entry_premium, stop_pct, leg.qty, R.trail_locked(leg.direction, leg.entry_underlying, leg.trail_active, leg.trail_stop_underlying))
    planned += sum(c["risk"] for c in open_children(leg))
    risk = R.child_risk(quote.ask, quote.bid, state["reference"], stop_pct, qty)
    limit = R.budget(book.equity, float(settings.FNO_MAX_RISK_PCT), float(settings.FNO_MAX_LOSS_PER_TRADE), stance.multiplier)
    if planned + risk > limit:
        return refuse(self, state, "risk")
    if (self.book.get("n091") or {}).get("mode") == "CUSHION":
        reserve = M.open_reserve(book, self.book.get("cost"))
        self._n091_budget = M.R.advance(self._n091_budget, book.equity, reserve, self._n091_drawdown)
        if self._n091_budget.floor + reserve + M.full_reserve(quote.ask, qty, 1, self.book.get("cost")) > book.equity + 1e-8:
            return refuse(self, state, "reserve")
    state["children"].append({
        "step": state["next"], "at": now.isoformat(), "ask": quote.ask, "qty": qty, "future": obs.future.ltp, "progress": round(progress, 4),
        "level": R.level_at(leg.direction, leg.entry_underlying, state["risk_points"], level_r), "premium_stop": round(quote.ask * (1.0 - stop_pct), 2),
        "risk": risk, "planned_total": round(planned + risk, 2), "limit": round(limit, 2), "exit_at": None})
    state["next"] += 1
    state["reference"] = quote.ask
    self.notes["n10_added"] += 1


_manage = Y.BookReplay._manage


def manage(self, book, obs, now):
    if not self.book.get("n10"):
        return _manage(self, book, obs, now)
    for ident in sorted(book.open):
        leg = book.open[ident]
        quote = obs.options.get(leg.token)
        for child in open_children(leg):
            if quote is None or quote.bid <= 0:
                self.notes["n10_child_unpriced"] += 1
                continue
            why = R.child_out(leg.direction, obs.future.ltp, child["level"], quote.bid, child["premium_stop"])
            if why:
                settle_child(leg, child, now, quote.bid, why)
                state_of(leg)["stopped"] = True
    _manage(self, book, obs, now)
    for ident in sorted(book.open):
        maybe_add(self, book, book.open[ident], obs, now)


Y.BookReplay._manage = manage

# ---- books ------------------------------------------------------------------------------------------------------------


def n10_cfg(entry_mode: str, steps: list, eligibility: str = "RISK", vol: bool = False, max_total: int = 2) -> dict:
    return {"contract": "v1", "entry": entry_mode, "steps": steps, "eligibility": eligibility, "vol": vol, "max_total": max_total}


def earn(label: str, steps: list = FIRST, eligibility: str = "RISK", vol: bool = False, cushion: bool = False, max_total: int = 2) -> dict:
    b = copy.deepcopy(Z.n08())
    b["label"] = f"N10|{label}"
    b["n10"] = n10_cfg("ONE", steps, eligibility, vol, max_total)
    if cushion:
        b["n091"] = {"contract": "v1", "mode": "CUSHION"}
    return b


def hybrid(label: str, steps: list = FIRST) -> dict:
    b = copy.deepcopy(M.candidates()["CUSHION"])
    b["label"] = f"N10|{label}"
    b["n10"] = n10_cfg("NATIVE", steps, "RISK", False, 3)
    return b


def control_books() -> dict:
    noop_cushion = copy.deepcopy(M.candidates()["CUSHION"])
    noop_cushion["label"] = "N10|NOOP_CUSHION"
    noop_cushion["n10"] = n10_cfg("NATIVE", [])
    noop = copy.deepcopy(Z.n08())
    noop["label"] = "N10|NOOP"
    noop["n10"] = n10_cfg("NATIVE", [])
    one = copy.deepcopy(Z.n08())
    one["label"] = "N10|ONE"
    one["cfg"] = {**one.get("cfg", {}), **Z.ONE_LOT}
    return {"NOOP": noop, "NOOP_CUSHION": noop_cushion, "ONE": one, "INF": earn("INF", OUT_OF_REACH)}


def cushion_books(x: float = 1.0, suffix: str = "") -> dict:
    return {
        f"EARN_WC{suffix}": earn(f"EARN_WC{suffix}", scaled(x), cushion=True),
        f"EARN_WVC{suffix}": earn(f"EARN_WVC{suffix}", scaled(x), vol=True, cushion=True),
        f"LADDER_WC{suffix}": earn(f"LADDER_WC{suffix}", scaled(x, ladder=True), cushion=True, max_total=3),
        f"HYBRID_C{suffix}": hybrid(f"HYBRID_C{suffix}", scaled(x)),
    }


CUSHION_NAMES = ("EARN_WC", "EARN_WVC", "LADDER_WC", "HYBRID_C")


def primary_books() -> dict:
    return {"EARN_N": earn("EARN_N", eligibility="NATIVE"), "EARN_W": earn("EARN_W"), "EARN_WV": earn("EARN_WV", vol=True), **cushion_books()}


def neighbour_books() -> dict:
    return {**cushion_books(0.75, "@0.75"), **cushion_books(1.25, "@1.25")}


def nobrake_books() -> dict:
    out = {}
    source = {"N08": Z.n08(), "ONE": control_books()["ONE"], "EARN_W": primary_books()["EARN_W"], "EARN_WV": primary_books()["EARN_WV"]}
    for name, book in source.items():
        b = copy.deepcopy(book)
        b["cfg"] = {**b.get("cfg", {}), **L.BRAKES_OFF}
        b["label"] = f"N10|NOBRAKE|{name}"
        out[f"NOBRAKE|{name}"] = b
    return out


def panel_books() -> dict:
    return {**primary_books(), **neighbour_books(), **nobrake_books()}


def cost_books() -> dict:
    out = {}
    for name, book in cushion_books().items():
        for tag, cost in (("none", [0.0, 0.0]), ("double", [400.0, 10.0])):
            b = copy.deepcopy(book)
            b.update(cost=cost, label=f"N10|COST|{name}|{tag}")
            out[f"COST|{name}|{tag}"] = b
    return out


def carry_books() -> dict:
    """One account from January 2023: no reset, the floor carried. The label keeps N09.1's prefix, which is what writes the carried state."""
    out = {}
    earlier = YEARS[:YEARS.index(YEAR)]
    for name, book in cushion_books().items():
        b = copy.deepcopy(book)
        b["label"] = f"N091|CARRY|N10|{name}"
        if earlier:
            saved = [json.loads((LOCAL / f"keys-carry-{y}.json").read_text(encoding="utf-8"))[name] for y in earlier]
            b["carry"] = saved
            b["n091"]["state_from"] = saved[-1].rsplit("_", 1)[-1]
        out[name] = b
    return out


def random_books() -> dict:
    """The first 10 random books, one lot, brakes off, the usual extra cost, with and without the +1R add."""
    out = {}
    for i, base in enumerate(Y.null_fixed()[:10]):
        for tag, steps in (("BASE", []), ("EARN", FIRST)):
            b = B.W.X.book(f"N10|RANDOM|{i:02d}|{tag}", members=[{**m, "gate": "ALWAYS"} for m in base["members"]], cfg=dict(B.W.S.RAW), cost=True)
            b["n10"] = n10_cfg("NATIVE", steps)
            out[f"RANDOM|{i:02d}|{tag}"] = b
    return out


def keys(books: dict) -> dict:
    return {n: Y.task_key(b, "year", C.WINDOW) for n, b in books.items()}


# ---- the freeze -------------------------------------------------------------------------------------------------------

SOURCES = ("n10_rules.py", "n10_lab.py", "PLAN.md", "score.py", "test_n10.py", "driver.py", "n091_lab_free.py")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(bytes([13, 10]), bytes([10]))).hexdigest()


def committed(path: Path) -> bytes:
    return subprocess.check_output(["git", "show", f"HEAD:{path.relative_to(ROOT).as_posix()}"], cwd=ROOT)


def freeze() -> None:
    target = HERE / "freeze.json"
    assert not target.exists(), "already frozen"
    X.write(target, {"schema": "n10_freeze_v1", "sources": {s: sha(HERE / s) for s in SOURCES},
                     "books": {"controls": control_books(), "panel": panel_books(), "costs": cost_books(), "random": random_books()},
                     "note": "Written before any N10 book is scored. All four years are seen, so this is discipline, not an exam."})


def require_freeze() -> None:
    target = HERE / "freeze.json"
    assert json.loads(committed(target)) == json.loads(target.read_text(encoding="utf-8")), "freeze.json is not committed"
    frozen = json.loads(target.read_text(encoding="utf-8"))
    for name, value in frozen["sources"].items():
        assert sha(HERE / name) == value, f"{name} changed after the freeze"


def run_phase(name: str, books: dict, jobs: int) -> None:
    N.run_books(books, jobs)
    X.write(LOCAL / f"keys-{name}-{YEAR}.json", keys(books))
    print("DONE", name, YEAR, len(books), flush=True)


ECONOMIC = ("entry_time", "tradingsymbol", "entry_premium", "exit_time", "exit_premium", "exit_reason", "net_pnl", "entry_qty")


def economics(trades: list) -> list:
    return [{k: t.get(k) for k in ECONOMIC} for t in trades]


def load(key: str, folder: Path = None) -> list:
    return json.loads(((folder or Y.EVALS) / f"{key}.json").read_text(encoding="utf-8"))["trades"]


def parity(jobs: int) -> None:
    """Saved N08 and N09.1 CUSHION come back trade for trade with every N10 path on and nothing changed; one lot equals N10 with the add out of reach."""
    books = control_books()
    run_phase("controls", books, jobs)
    k = keys(books)
    n08_key = json.loads((Z.LOCAL / f"keys-diag-{YEAR}.json").read_text(encoding="utf-8"))["N08"]
    n091_key = json.loads((M.HERE / "_local" / f"keys-primary-{YEAR}.json").read_text(encoding="utf-8"))["CUSHION"]
    n08 = load(n08_key, Z.LOCAL / f"evals-{YEAR}")
    n091 = load(n091_key, M.HERE / "_local" / "evals")
    assert economics(load(k["NOOP"])) == economics(n08), "NOOP differs from saved N08"
    assert economics(load(k["NOOP_CUSHION"])) == economics(n091), "NOOP_CUSHION differs from saved N09.1 CUSHION"
    assert economics(load(k["INF"])) == economics(load(k["ONE"])), "the add out of reach differs from one lot"
    out = {"year": YEAR, "N08": {"trades": len(n08), "net": round(sum(t["net_pnl"] for t in n08), 2)}, "CUSHION": {"trades": len(n091), "net": round(sum(t["net_pnl"] for t in n091), 2)},
           "ONE": {"trades": len(load(k["ONE"])), "net": round(sum(t["net_pnl"] for t in load(k["ONE"])), 2)}, "identical": True}
    X.write(HERE / f"parity-{YEAR}.json", out)
    print("PARITY OK", json.dumps(out), flush=True)


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=("parity", "freeze", "panel", "costs", "carry", "random"))
    cli.add_argument("--jobs", type=int, default=6)
    a = cli.parse_args()
    if a.action == "parity":
        parity(a.jobs)
    elif a.action == "freeze":
        freeze()
        print("FROZEN", flush=True)
    else:
        require_freeze()
        run_phase(a.action, {"panel": panel_books, "costs": cost_books, "carry": carry_books, "random": random_books}[a.action](), a.jobs)
