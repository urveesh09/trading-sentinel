"""After the freeze: the frozen code let a second lot reach two lots by the larger budget alone, with its 25% backstop, so fees and stress sat on top of Rs 7,500. PLAN.md says they are inside it.
This is the plan's wording, as a separate book. The frozen files aren't edited and the frozen result stays on record. N08_YEAR=<year> python n11t_strict.py --jobs 3
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import n11t_lab as Q  # noqa: E402
from fno_costs import calc_fno_costs  # noqa: E402

L, T, Y, Z, X, B = Q.L, Q.T, Q.Y, Q.Z, Q.X, Q.B
R = L.R
_second = Q.second_lot


def second_lot(engine, cfg, n11, sig, snap, regime, now, state):
    before = engine.notes["n11t_second_lots"]
    out = _second(engine, cfg, n11, sig, snap, regime, now, state)
    engine._n11t_limit = float(cfg["limit"]) * min(1.0, max(float(state.risk_multiplier), 1e-9)) if engine.notes["n11t_second_lots"] > before else None
    return out


Q.second_lot = second_lot
_entry = Y.BookReplay._entry


def entry(self, book, obs, frame, day, now):
    self._n11t_limit = None
    before = book.next_id
    _entry(self, book, obs, frame, day, now)
    if not (self.book.get("n11t") or {}).get("strict") or book.next_id == before or self._n11t_limit is None:
        return
    leg = book.open[before]
    points = R.backstop_points(self._n11t_limit, leg.entry_premium, leg.qty, T.R.extra_cost(self.book.get("cost"), leg.lots), calc_fno_costs)
    if points is not None:
        leg.premium_stop = max(leg.premium_stop, R.stop_price(leg.entry_premium, points))
        self.notes["n11t_strict_stops"] += 1


Y.BookReplay._entry = entry


def books() -> dict:
    strict = copy.deepcopy(Q.n11t_book("STRICT"))
    strict["n11t"]["strict"] = True
    double = copy.deepcopy(strict)
    double["label"] = "N11T|STRICT|DOUBLE"
    double["cost"] = [400.0, 10.0]
    return {"STRICT": strict, "STRICT|DOUBLE": double}


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("--jobs", type=int, default=3)
    a = cli.parse_args()
    current = books()
    Z.N.run_books(current, a.jobs)
    X.write(Q.LOCAL / f"keys-strict-{Q.YEAR}.json", {n: Y.task_key(b, "year", B.C.WINDOW) for n, b in current.items()})
    print("DONE strict", Q.YEAR, flush=True)
