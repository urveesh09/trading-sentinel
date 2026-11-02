"""N11T: when may a trade plan to lose up to Rs 7,500 instead of Rs 5,000? The owner allows 50% tolerance under conditions the agent chooses. Research only.

Run through driver.py so Windows workers import this module exactly once. N08_YEAR chooses the year.

    N08_YEAR=<year> python driver.py screen --jobs 3
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())
sys.path[:0] = [str(HERE), str(HERE.parent / "2026-11-02-fno-n11")]
import n11_lab as L  # noqa: E402
import n11_rules as R  # noqa: E402
from config import settings  # noqa: E402
from fno_costs import calc_fno_costs  # noqa: E402

U, B, T, M, Z, Y, X = L.U, L.B, L.T, L.M, L.Z, L.Y, L.X
YEAR, YEARS = L.YEAR, L.YEARS
LOCAL = HERE / "_local"
L.LOCAL = U.LOCAL = B.LOCAL = T.LOCAL = M.LOCAL = X.LOCAL = LOCAL
Y.EVALS = LOCAL / "evals"
Y.EVALS.mkdir(parents=True, exist_ok=True)
TOLERANT = 7500.0

# ---- is this the kind of trade that may plan to lose more? ----------------------------------------------------------------


def allowed(engine, sig, state, now, cfg: dict) -> bool:
    """Every condition is known at entry. None reads the trade's result, and none is a date or a side chosen from one year."""
    when = cfg["when"]
    if "NEVER_ENTRY" in when:
        return False
    if "VOL" in when and not L.vol_up(now):
        return False
    if "EV" in when and not L.evidence_now(now):
        return False
    if "EV_NOT" in when and L.evidence_now(now):       # the control: second lots only on a losing record
        return False
    if "CALM" in when and (state.open_positions > 0 or L.realised_today(engine._n10_book, now) < 0):
        return False
    if "PUTS" in when and sig.direction.value != "SHORT":
        return False
    return True


# ---- the planner: the same gates, a larger budget for this trade only --------------------------------------------------------

_planner = T._planner


def second_lot(engine, cfg: dict, n11: dict, sig, snap, regime, now, state):
    """The tolerance's only job: a second lot on a trade N11 already takes at one lot, when both readings are good. It admits no new trade, moves no trade's limit down, and never
    takes a third lot at entry. The lot is charged what the trade's own stop is expected to cost; the backstop is tightened so the whole trade stays inside the limit."""
    flag = n11.get("true_risk")
    n11["true_risk"] = False
    try:
        first = _planner(sig, snap, regime, now, state)     # N11's own decision, unchanged
    finally:
        n11["true_risk"] = flag
    ceiling = min(settings.FNO_MAX_LOTS, settings.FNO_MAX_LOTS_PROVEN)
    if not first.accepted or first.lots >= ceiling or not allowed(engine, sig, state, now, cfg):
        return first
    saved = settings.FNO_MAX_RISK_PCT, settings.FNO_MAX_LOSS_PER_TRADE
    m = max(float(state.risk_multiplier), 1e-9)
    target = max(float(cfg["limit"]) * min(1.0, m), min(state.pool * float(saved[0]) * m, float(saved[1]) * m))
    try:
        settings.FNO_MAX_RISK_PCT = 0.99
        settings.FNO_MAX_LOSS_PER_TRADE = target / m
        n11["true_risk"] = True
        again = _planner(sig, snap, regime, now, state)
    finally:
        settings.FNO_MAX_RISK_PCT, settings.FNO_MAX_LOSS_PER_TRADE = saved
        n11["true_risk"] = flag
    if again.accepted and again.lots > first.lots:
        engine.notes["n11t_second_lots"] += 1
        return again
    engine._n11_last = None        # the second try's stop isn't this trade's
    return first


def planner(sig, snap, regime, now, state):
    engine = T.ENGINE["now"]
    cfg = (engine.book.get("n11t") or None) if engine is not None else None
    if cfg is None:
        return _planner(sig, snap, regime, now, state)
    n11 = engine.book["n11"]
    if cfg.get("clamp") == "SECOND_LOT":
        return second_lot(engine, cfg, n11, sig, snap, regime, now, state)
    if not allowed(engine, sig, state, now, cfg):
        saved_flag = n11.get("true_risk")
        n11["true_risk"] = False           # the tolerance's charge is for tolerated trades alone
        try:
            return _planner(sig, snap, regime, now, state)
        finally:
            n11["true_risk"] = saved_flag
    saved = settings.FNO_MAX_RISK_PCT, settings.FNO_MAX_LOSS_PER_TRADE
    limit = float(cfg.get("limit", TOLERANT))
    if not cfg.get("clamp"):
        try:      # the first screen's version: a winning streak's stance could scale this past the limit, so screen2 clamps it
            settings.FNO_MAX_RISK_PCT = float(saved[0]) * limit / 5000.0
            settings.FNO_MAX_LOSS_PER_TRADE = limit
            return _planner(sig, snap, regime, now, state)
        finally:
            settings.FNO_MAX_RISK_PCT, settings.FNO_MAX_LOSS_PER_TRADE = saved
    m = max(float(state.risk_multiplier), 1e-9)
    try:
        # The planner's budget is min(pool x risk%, rupees) x the stance. These make it the limit x min(1, stance): a drawdown still cuts it, a winning streak never lifts it past the limit.
        target = limit * min(1.0, m)
        if cfg["clamp"] == "RAISE_ONLY":
            # What the proven stance already allows stays: this tolerance may only raise a trade's limit, never lower it.
            target = max(target, min(state.pool * float(saved[0]) * m, float(saved[1]) * m))
        settings.FNO_MAX_RISK_PCT = 0.99
        settings.FNO_MAX_LOSS_PER_TRADE = target / m
        return _planner(sig, snap, regime, now, state)
    finally:
        settings.FNO_MAX_RISK_PCT, settings.FNO_MAX_LOSS_PER_TRADE = saved


T._planner = planner

# ---- the earned lot's charge may use the same room, under the same conditions -----------------------------------------------

_honest = L.honest_add


def honest_add(self, book, leg, obs, now, mode):
    cfg = self.book.get("n11t")
    if not cfg or not cfg.get("add"):
        return _honest(self, book, leg, obs, now, mode)
    saved = self.book["n10"].get("flat_risk")
    usual_pct, usual_top = settings.FNO_MAX_RISK_PCT, settings.FNO_MAX_LOSS_PER_TRADE
    state = T.state_of(leg)
    good = state is not None and ("VOL" not in cfg["when"] or L.vol_up(now)) and ("EV" not in cfg["when"] or L.evidence_now(now)) and ("PUTS" not in cfg["when"] or leg.direction == "SHORT")
    if not good:
        return _honest(self, book, leg, obs, now, mode)
    limit = float(cfg.get("limit", TOLERANT))
    try:
        self.book["n10"]["flat_risk"] = limit
        settings.FNO_MAX_RISK_PCT = float(usual_pct) * limit / 5000.0
        settings.FNO_MAX_LOSS_PER_TRADE = limit
        return _honest(self, book, leg, obs, now, mode)
    finally:
        self.book["n10"]["flat_risk"] = saved
        settings.FNO_MAX_RISK_PCT, settings.FNO_MAX_LOSS_PER_TRADE = usual_pct, usual_top


L.honest_add = honest_add

# ---- books --------------------------------------------------------------------------------------------------------------


def tol(label: str, when: tuple, *, add: bool = False, limit: float = TOLERANT, **change) -> dict:
    b = L.n11_book(f"T|{label}", **change)
    b["n11t"] = {"contract": "v1", "when": list(when), "add": add, "limit": limit}
    return b


def screen_books() -> dict:
    """Development screen on seen years: which conditions, if any, turn the extra room into profit? It chooses what gets frozen. It is not a verdict."""
    return {
        "BASE": L.n11_book("T|BASE"),
        "ALWAYS": tol("ALWAYS", ()),
        "VOL": tol("VOL", ("VOL",)),
        "EV": tol("EV", ("EV",)),
        "VOL_EV": tol("VOL_EV", ("VOL", "EV")),
        "VOL_EV_CALM": tol("VOL_EV_CALM", ("VOL", "EV", "CALM")),
        "VOL_EV_PUTS": tol("VOL_EV_PUTS", ("VOL", "EV", "PUTS")),
        "VOL_PUTS": tol("VOL_PUTS", ("VOL", "PUTS")),
        "VOL_CALM": tol("VOL_CALM", ("VOL", "CALM")),
        "VOL_EV_ADD": tol("VOL_EV_ADD", ("VOL", "EV"), add=True),
        "VOL_EV_CALM_ADD": tol("VOL_EV_CALM_ADD", ("VOL", "EV", "CALM"), add=True),
        "ADD_ONLY": {**tol("ADD_ONLY", ("VOL", "EV"), add=True), "n11t": {"contract": "v1", "when": ["VOL", "EV", "NEVER_ENTRY"], "add": True, "limit": TOLERANT}},
    }


def charged(label: str, when: tuple, k: float, limit: float = TOLERANT) -> dict:
    """A lot is charged what the trade's own stop is expected to cost, capped at the limit, with the backstop tightened so the whole trade stays inside it. Only for tolerated trades."""
    b = L.n11_book(f"T2|{label}", true_risk=True, k=k, flat=limit)
    b["n11t"] = {"contract": "v2", "when": list(when), "add": False, "limit": limit, "clamp": True}
    return b


def screen2_books() -> dict:
    """Second development screen: the cap is really the cap, and the charge is the stop's, because the 25% rule still blocks every option above Rs 230."""
    ve = ("VOL", "EV")
    clamp = tol("CLAMP_VE", ve)
    clamp["n11t"]["clamp"] = True
    return {
        "BASE": L.n11_book("T|BASE"),
        "CLAMP_VE": clamp,
        "K10_VE": charged("K10_VE", ve, 1.0), "K125_VE": charged("K125_VE", ve, 1.25), "K15_VE": charged("K15_VE", ve, 1.5), "K175_VE": charged("K175_VE", ve, 1.75), "K20_VE": charged("K20_VE", ve, 2.0),
        "K15_V": charged("K15_V", ("VOL",), 1.5),
        "K15_VE_PUTS": charged("K15_VE_PUTS", (*ve, "PUTS"), 1.5),
        "K15_VE_CALM": charged("K15_VE_CALM", (*ve, "CALM"), 1.5),
        "K15_VE_6250": charged("K15_VE_6250", ve, 1.5, 6250.0),
    }


def screen3_books() -> dict:
    """Third development screen: the map of the cap and the charge, because the last screen showed a cliff below k = 1.5 and a better result at a lower cap."""
    ve = ("VOL", "EV")
    out = {"BASE": L.n11_book("T|BASE")}
    for limit in (5500.0, 6000.0, 6250.0, 6500.0, 7000.0, 7500.0):
        for k in (1.5, 2.0, 2.5):
            out[f"L{limit:.0f}_K{k}"] = charged(f"L{limit:.0f}_K{k}", ve, k, limit)
    return out


def raise_only(label: str, when: tuple, k: float, limit: float) -> dict:
    b = charged(label, when, k, limit)
    b["label"] = f"T4|{label}"
    b["n11t"]["clamp"] = "RAISE_ONLY"
    b["n11t"]["contract"] = "v3"
    return b


def screen4_books() -> dict:
    """Fourth development screen. Screen 3's cap also lowered what the proven stance allows, which caused its cliffs: a fault in the test. Here the tolerance only raises."""
    ve = ("VOL", "EV")
    out = {"BASE": L.n11_book("T|BASE")}
    for limit in (5500.0, 6000.0, 6250.0, 6500.0, 7000.0, 7500.0):
        for k in (1.5, 2.0):
            out[f"R{limit:.0f}_K{k}"] = raise_only(f"R{limit:.0f}_K{k}", ve, k, limit)
    out["R7500_K1.25"] = raise_only("R7500_K1.25", ve, 1.25, 7500.0)
    out["R7500_K1.75"] = raise_only("R7500_K1.75", ve, 1.75, 7500.0)
    out["R7500_K1.5_V"] = raise_only("R7500_K1.5_V", ("VOL",), 1.5, 7500.0)
    out["R7500_K1.5_E"] = raise_only("R7500_K1.5_E", ("EV",), 1.5, 7500.0)
    return out


def second(label: str, when: tuple, k: float, limit: float) -> dict:
    b = charged(label, when, k, limit)
    b["label"] = f"T5|{label}"
    b["n11t"]["clamp"] = "SECOND_LOT"
    b["n11t"]["contract"] = "v4"
    return b


def screen5_books() -> dict:
    """Fifth development screen. Screen 4's larger budget also admitted new one-lot trades on options up to Rs 420. Here the tolerance only adds a second lot to a trade N11 already takes."""
    ve = ("VOL", "EV")
    out = {"BASE": L.n11_book("T|BASE")}
    for limit in (5500.0, 6250.0, 7000.0, 7500.0):
        for k in (1.5, 1.75, 2.0):
            out[f"S{limit:.0f}_K{k}"] = second(f"S{limit:.0f}_K{k}", ve, k, limit)
    out["S7500_K1.25"] = second("S7500_K1.25", ve, 1.25, 7500.0)
    out["S7500_K1.75_NOEV"] = second("S7500_K1.75_NOEV", ("VOL",), 1.75, 7500.0)
    return out


# ---- the frozen book --------------------------------------------------------------------------------------------------------

LIMIT, K = 7500.0, 1.75
VE = ("VOL", "EV")


def n11t_book(label: str = "N11T", when: tuple = VE, k: float = K, limit: float = LIMIT) -> dict:
    b = second(label, when, k, limit)
    b["label"] = f"N11T|{label}"
    return b


def panel_books() -> dict:
    double = n11t_book("DOUBLE")
    double["cost"] = [400.0, 10.0]
    return {"N11T": n11t_book(), "N11": L.n11_book("T|BASE"), "K1.5": n11t_book("K1.5", k=1.5), "K2.0": n11t_book("K2.0", k=2.0), "L6250": n11t_book("L6250", limit=6250.0), "L7000": n11t_book("L7000", limit=7000.0),
            "NO_READING": n11t_book("NO_READING", when=("VOL",)), "REVERSED": n11t_book("REVERSED", when=("VOL", "EV_NOT")), "DOUBLE": double}


def carry_books() -> dict:
    earlier = YEARS[:YEARS.index(YEAR)]
    out = {}
    for tag, cost in L.COSTS.items():
        b = n11t_book()
        b["cost"] = cost
        b["label"] = f"N091|CARRY|N11T|{tag}"
        if earlier:
            saved = [json.loads((LOCAL / f"keys-carry-{y}.json").read_text(encoding="utf-8"))[tag] for y in earlier]
            b["carry"] = saved
            b["n091"]["state_from"] = saved[-1].rsplit("_", 1)[-1]
        out[tag] = b
    return out


PHASES = {"screen": screen_books, "screen2": screen2_books, "screen3": screen3_books, "screen4": screen4_books, "screen5": screen5_books, "panel": panel_books, "carry": carry_books}
FROZEN = ("panel", "carry")
SOURCES = ("n11t_lab.py", "PLAN.md", "driver.py", "test_n11t.py")


def freeze() -> None:
    target = HERE / "freeze.json"
    assert not target.exists(), "already frozen"
    X.write(target, {"schema": "n11t_freeze_v1", "sources": {s: T.sha(HERE / s) for s in SOURCES}, "books": {"panel": panel_books()}, "limit": LIMIT, "k": K, "conditions": list(VE),
                     "note": "Written after five development screens on the four seen years, and before any frozen phase runs. Discipline, not an exam."})


def require_freeze() -> None:
    target = HERE / "freeze.json"
    assert json.loads(T.committed(target)) == json.loads(target.read_text(encoding="utf-8")), "freeze.json is not committed"
    for name, value in json.loads(target.read_text(encoding="utf-8"))["sources"].items():
        assert T.sha(HERE / name) == value, f"{name} changed after the freeze"


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("phase", choices=(*PHASES, "freeze"))
    cli.add_argument("--jobs", type=int, default=3)
    a = cli.parse_args()
    assert 1 <= a.jobs <= 4, "Production comes first"
    if a.phase == "freeze":
        freeze()
        print("FROZEN", flush=True)
        return
    if a.phase in FROZEN:
        require_freeze()
    books = PHASES[a.phase]()
    Z.N.run_books(books, a.jobs)
    X.write(LOCAL / f"keys-{a.phase}-{YEAR}.json", {n: Y.task_key(b, "year", B.C.WINDOW) for n, b in books.items()})
    print("DONE", a.phase, YEAR, len(books), flush=True)
