"""Frozen N09.1 wrappers around native planning; never imported by the application.

Run through driver.py so Windows workers import this module exactly once.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())
sys.path[:0] = [str(HERE), str(HERE.parent / "2026-11-01-fno-n09")]
import n09_lab as Z
import n091_rules as R
import fno_entry_plan as EP
from config import settings
from fno_costs import calc_fno_costs

Y, X, C = Z.Y, Z.X, Z.C
YEAR = Z.YEAR
YEARS = ("2023", "2024", "2025", "2026")
LOCAL = HERE / "_local"
Y.EVALS = LOCAL / "evals"
X.LOCAL = LOCAL
Z.B.O27F.deny_network()
ACTIVE = None


def write(path, value):
    X.write(path, value)


def full_reserve(premium: float, qty: int, lots: int, cost) -> float:
    """Full premium plus loss-side fee upper bound and declared extra stress.

    Current fees are increasing in exit premium. Fees at exit==entry conservatively
    cover every losing exit; profitable-exit surplus covers its incremental fees.
    N08 has no partial exits/pyramids. Audits refuse those unsupported lifecycles.
    """
    a, b = (200., 5.) if cost is None else cost
    return premium * qty + calc_fno_costs(premium, premium, qty) + (a + b * lots) * lots


def open_reserve(book, cost):
    return sum(full_reserve(leg.entry_premium, leg.qty, leg.lots, cost) for leg in book.open.values())


_plan = EP.plan_single_leg_entry


def plan(sig, snap, regime, now, state):
    original = _plan(sig, snap, regime, now, state)
    engine = ACTIVE
    if engine is None or not original.accepted:
        return original
    cfg = engine.book["n091"]
    current = engine._n091_book
    reserve = open_reserve(current, engine.book.get("cost"))
    budget = engine._n091_budget
    costs = {n: full_reserve(original.quote.ask, original.lot_size * n, n, engine.book.get("cost"))
             for n in range(1, original.lots + 1)}
    allowed = original.lots
    if cfg["mode"] == "CUSHION":
        budget = R.advance(budget, state.pool, reserve, engine._n091_drawdown)
        engine._n091_budget = budget
        allowed = R.affordable(original.lots, state.pool, budget.floor, reserve, costs)
    result = original
    if allowed == 0:
        result = replace(original, accepted=False, reject_reason="n091:full_premium_reserve",
                         log_fields={**original.log_fields, "n091_floor": budget.floor, "n091_open_reserve": reserve})
    elif allowed < original.lots:
        saved = settings.FNO_MAX_LOTS, settings.FNO_MAX_LOTS_PROVEN
        try:
            settings.FNO_MAX_LOTS = min(saved[0], allowed)
            settings.FNO_MAX_LOTS_PROVEN = min(saved[1], allowed)
            result = _plan(sig, snap, regime, now, state)
        finally:
            settings.FNO_MAX_LOTS, settings.FNO_MAX_LOTS_PROVEN = saved
        assert not result.accepted or result.lots <= allowed
    engine._n091_receipts.append({
        "at": now.isoformat(), "bar_ts": sig.bar_ts, "direction": sig.direction.value,
        "symbol": original.quote.contract.tradingsymbol, "token": original.quote.contract.token,
        "ask": original.quote.ask, "lot_size": original.lot_size, "native_lots": original.lots,
        "final_lots": result.lots if result.accepted else 0, "accepted": result.accepted,
        "reason": result.reject_reason, "pool": state.pool, "open_reserve": reserve,
        "floor": budget.floor if cfg["mode"] == "CUSHION" else None,
        "peak": budget.peak, "full_reserves": costs,
        "stop": sig.stop_underlying, "target": sig.target_underlying,
        "native_gate_context": asdict(original.gate_context),
        "native_reward_risk": original.reward_risk,
    })
    return result


_entry = Y.BookReplay._entry


def entry(self, book, obs, frame, day, now):
    global ACTIVE
    if not self.book.get("n091"):
        return _entry(self, book, obs, frame, day, now)
    assert ACTIVE is None
    self._n091_book = book
    reserve = open_reserve(book, self.book.get("cost"))
    if self.book["n091"]["mode"] == "CUSHION":
        self._n091_budget = R.advance(self._n091_budget, book.equity, reserve, self._n091_drawdown)
    before, count = book.next_id, len(self._n091_receipts)
    ACTIVE = self
    EP.plan_single_leg_entry = plan
    try:
        _entry(self, book, obs, frame, day, now)
        if book.next_id != before:
            assert len(self._n091_receipts) > count
            leg = book.open[before]
            receipt = self._n091_receipts[-1]
            assert receipt["accepted"] and receipt["final_lots"] == leg.lots
            leg._n02_metadata["n091_entry"] = copy.deepcopy(receipt)
            receipt["admission_id"] = leg._n02_metadata["admission_id"]
    finally:
        EP.plan_single_leg_entry = _plan
        ACTIVE = None


Y.BookReplay._entry = entry
Y.KEEP = tuple(dict.fromkeys((*Y.KEEP, "n091_entry")))
_run = Y.BookReplay.run


def run_book(self, start, end):
    cfg = self.book.get("n091")
    if cfg:
        self._n091_drawdown = float(settings.FNO_MAX_DRAWDOWN_PCT)
        prior = cfg.get("state_from")
        state = json.loads((LOCAL / "states" / f"{prior}.json").read_text()) if prior else None
        capital = float(settings.FNO_PAPER_BANKROLL)
        self._n091_budget = R.Budget(**state["budget"]) if state else R.Budget(capital, capital, capital * (1 - self._n091_drawdown))
        self._n091_receipts = []
    result = _run(self, start, end)
    key = Y.task_key(self.book, self.source, (start, end))
    write(LOCAL / "receipts" / f"{key}.json", {"decisions": self.decisions, "admissions": getattr(self, "_n091_receipts", [])})
    if cfg:
        assert all(t.get("net_pnl") is not None for t in result["trades"]), "unresolved trade: do not publish a complete result"
        end_equity = result["start_equity"] + sum(t["net_pnl"] for t in result["trades"])
        if cfg["mode"] == "CUSHION":
            self._n091_budget = R.advance(self._n091_budget, end_equity, 0., self._n091_drawdown)
        write(LOCAL / "states" / f"{Y.digest(self.book)}.json", {
            "budget": asdict(self._n091_budget), "end_equity": end_equity,
            "start_equity": result["start_equity"], "drawdown": self._n091_drawdown,
            "previous": cfg.get("state_from"), "window": [start, end],
        })
    return result


Y.BookReplay.run = run_book


def candidates():
    out = {}
    for mode in ("VOL_CLOCK", "CUSHION"):
        b = Z.with_n09(Z.n08(), f"N091|{mode}", vol_size=True)
        b["n091"] = {"contract": "v1", "mode": mode}
        out[mode] = b
    return out


def books(phase):
    if phase == "controls":
        return {**Z.diag_books(), "S_VOL": Z.cash_books()["CASH|S_VOL"]}
    if phase == "primary":
        return candidates()
    if phase == "costs":
        out = {}
        for name, book in {"N08": Z.n08(), **candidates()}.items():
            for label, cost in (("none", [0., 0.]), ("double", [400., 10.])):
                b = copy.deepcopy(book)
                b.update(cost=cost, label=f"N091|COST|{name}|{label}")
                out[f"{name}|{label}"] = b
        return out
    if phase == "carry":
        out = {"N08": Z.n08(), "S_VOL": Z.cash_books()["CASH|S_VOL"], **candidates()}
        earlier = YEARS[:YEARS.index(YEAR)]
        for name, book in out.items():
            book["label"] = f"N091|CARRY|{name}"
            if earlier:
                saved = [json.loads((LOCAL / f"keys-carry-{y}.json").read_text())[name] for y in earlier]
                book["carry"] = saved
                if "n091" in book:
                    book["n091"]["state_from"] = saved[-1].rsplit("_", 1)[-1]
        return out
    raise ValueError(phase)


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    freeze = json.loads((HERE / "freeze.json").read_text())
    committed = subprocess.check_output(["git", "show", "HEAD:" + (HERE / "freeze.json").relative_to(ROOT).as_posix()], cwd=ROOT)
    assert json.loads(committed) == freeze, "freeze must be committed before replay"
    for name, expected in freeze["sources"].items():
        assert file_hash(ROOT / name) == expected, f"source changed: {name}"
    for item in freeze["inputs"]:
        assert file_hash(ROOT / item["path"]) == item["sha256"], f"input changed: {item['path']}"
    if YEAR == "2023":
        daily = sys.modules["lab_gap"].DAILY
        assert daily.name == "daily-2023.json", "2023 daily binding regression"
    return freeze


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("phase", choices=("describe", "controls", "primary", "costs", "carry"))
    cli.add_argument("--jobs", type=int, default=3)
    a = cli.parse_args()
    assert 1 <= a.jobs <= 3
    if a.phase == "describe":
        write(LOCAL / f"bindings-{YEAR}.json", {"year": YEAR, "window": C.WINDOW,
            "cache": str(Y.CACHES["year"].relative_to(ROOT)),
            "books": {p: books(p) for p in ("controls", "primary", "costs")}})
        print("BINDINGS", YEAR)
        return
    verify()
    b = books(a.phase)
    Z.N.run_books(b, a.jobs)
    write(LOCAL / f"keys-{a.phase}-{YEAR}.json", {n: Y.task_key(v, "year", C.WINDOW) for n, v in b.items()})
    print("DONE", a.phase, YEAR, len(b), flush=True)
