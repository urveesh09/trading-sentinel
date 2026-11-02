"""N11: N10's trades with a smarter second lot. Research only; no application module imports this file.

Run through driver.py so Windows workers import this module exactly once. N08_YEAR chooses the year.

    N08_YEAR=<year> python driver.py screen --jobs 3
"""
from __future__ import annotations

import argparse
import bisect
import copy
import json
import sys
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())
sys.path[:0] = [str(HERE), str(HERE.parent / "2026-11-02-fno-n101")]
import n101_lab as U  # noqa: E402
import n11_rules as R  # noqa: E402
from config import settings  # noqa: E402
from fno_costs import calc_fno_costs  # noqa: E402

B, T, M, Z, Y, X = U.B, U.T, U.M, U.Z, U.Y, U.X
replay = Y.replay
YEAR, YEARS = U.YEAR, U.YEARS
LOCAL = HERE / "_local"
U.LOCAL = B.LOCAL = T.LOCAL = M.LOCAL = X.LOCAL = LOCAL
Y.EVALS = LOCAL / "evals"
Y.EVALS.mkdir(parents=True, exist_ok=True)
Y.KEEP = tuple(dict.fromkeys((*Y.KEEP, "n11_entry", "exit_underlying")))
FLAT_RISK = 5000.0

# ---- the paper reading ------------------------------------------------------------------------------------------------


@lru_cache(maxsize=1)
def paper_stream() -> tuple:
    rows = U.paper_rows()
    return tuple(at for at, _t in rows), tuple(float(t["net_pnl"]) for _at, t in rows)


def evidence_now(now) -> bool:
    at, nets = paper_stream()
    return R.evidence_positive(nets[:bisect.bisect_left(at, now)])


def vol_up(now) -> bool:
    return Z.R.vol_lots(*Z.vol_table().get(now.date().isoformat(), (None, None))) >= 2


def vol_at(now, ratio: float = 1.0) -> bool:
    """The same reading with the line moved, for the neighbour tests. At 1.0 it is exactly vol_up."""
    atr, usual = Z.vol_table().get(now.date().isoformat(), (None, None))
    return Z.R.vol_lots(atr, None if usual is None else usual * ratio) >= 2


# ---- the ceiling: how large this trade may be, before the budget is asked -------------------------------------------------

_route = Y.BookReplay.route


def paper_before(now) -> tuple:
    at, nets = paper_stream()
    return nets[:bisect.bisect_left(at, now)]


def route(self, frame, regime, now):
    cfg = self.book.get("n11")
    sig = _route(self, frame, regime, now)
    if cfg and cfg.get("stand") and sig.direction is not None and R.stand_aside(vol_at(now, float(cfg.get("stand_ratio", 1.0))), paper_before(now), int(cfg["stand"])):
        self.notes["n11_stood_aside"] += 1
        return X.G.MomSignal(bar_ts=sig.bar_ts, reject_reason="n11:stand_aside")
    if cfg and cfg.get("evidence") and sig.direction is not None:
        lots = 2 if vol_up(now) or evidence_now(now) else 1      # Z.route's reading is off for these books: n09.vol_size is False
        settings.FNO_MAX_LOTS = min(settings.FNO_MAX_LOTS, lots)
        settings.FNO_MAX_LOTS_PROVEN = min(settings.FNO_MAX_LOTS_PROVEN, lots)
    return sig


Y.BookReplay.route = route


def realised_today(book, now) -> float:
    today = now.date()
    return sum(pnl for at, pnl, _kind in book.closes if at.date() == today and at <= now)


# ---- the planner: same gates, a truer charge per lot --------------------------------------------------------------------

_native = T._planner


def planner(sig, snap, regime, now, state):
    engine = T.ENGINE["now"]
    cfg = (engine.book.get("n11") or None) if engine is not None else None
    if cfg is None:
        return _native(sig, snap, regime, now, state)
    engine._n11_last = None
    saved = settings.FNO_MAX_LOTS, settings.FNO_MAX_LOTS_PROVEN, settings.FNO_STOP_PREMIUM_PCT
    try:
        stop_points = abs(float(snap.forward) - float(sig.stop_underlying))
        one = (cfg.get("loss_one") and realised_today(engine._n10_book, now) < 0) or (cfg.get("conc_one") and state.open_positions > 0) \
            or (cfg.get("noise_atr") and R.noise_stop(stop_points, float(sig.atr), float(cfg["noise_atr"])))
        if one:
            settings.FNO_MAX_LOTS, settings.FNO_MAX_LOTS_PROVEN = 1, 1
        out = _native(sig, snap, regime, now, state)
        ceiling = min(settings.FNO_MAX_LOTS, settings.FNO_MAX_LOTS_PROVEN)
        if not cfg.get("true_risk") or not out.accepted or out.lots >= ceiling:
            return out
        cost = engine.book.get("cost")
        limit = R.budget(state.pool, float(settings.FNO_MAX_RISK_PCT), float(settings.FNO_MAX_LOSS_PER_TRADE), float(cfg.get("flat", FLAT_RISK)), float(state.risk_multiplier))
        lots, points = R.true_risk_lots(out.lots, ceiling, out.quote.ask, out.delta, stop_points, out.lot_size, limit, float(cfg["k"]), float(saved[2]),
                                        calc_fno_costs, lambda n: T.R.extra_cost(cost, n))
        if points is None:
            return out
        settings.FNO_STOP_PREMIUM_PCT = points / out.quote.ask
        settings.FNO_MAX_LOTS, settings.FNO_MAX_LOTS_PROVEN = lots, lots
        again = _native(sig, snap, regime, now, state)
        if again.accepted and again.lots == lots:
            engine._n11_last = {"native": out.lots, "lots": lots, "points": points, "limit": limit, "stop_points": stop_points, "delta": out.delta}
            return again
        return out
    finally:
        settings.FNO_MAX_LOTS, settings.FNO_MAX_LOTS_PROVEN, settings.FNO_STOP_PREMIUM_PCT = saved


T._planner = planner

# ---- the entry: a raised trade's backstop sits where the budget says ---------------------------------------------------------

_entry = Y.BookReplay._entry


def entry(self, book, obs, frame, day, now):
    cfg = self.book.get("n11")
    if cfg is None:
        return _entry(self, book, obs, frame, day, now)
    self._n11_last = None
    before = book.next_id
    _entry(self, book, obs, frame, day, now)
    if book.next_id == before:
        return None
    leg = book.open[before]
    last = self._n11_last
    info = {"vol_up": vol_up(now), "evidence": evidence_now(now), "lots": leg.lots, "stop_points": abs(leg.entry_underlying - leg.stop_underlying), "atr": leg.atr_at_entry}
    if last is not None:
        assert last["lots"] == leg.lots, (last, leg.lots)
        wanted = R.stop_price(leg.entry_premium, last["points"])
        info.update(raised_from=last["native"], native_stop=leg.premium_stop, limit=round(last["limit"], 2), points=round(last["points"], 4))
        leg.premium_stop = max(leg.premium_stop, wanted)
        info["premium_stop"] = leg.premium_stop
        self.notes["n11_raised"] += 1
    leg._n11 = info
    return None


Y.BookReplay._entry = entry
_close = replay._close_record


def close_record(leg, *args, **kwargs):
    record, net = _close(leg, *args, **kwargs)
    info = getattr(leg, "_n11", None)
    if info is not None:
        record["n11_entry"] = info
    return record, net


replay._close_record = close_record

# ---- a one-lot trade on a volatile day may earn its second lot ---------------------------------------------------------------

_maybe_add = T.maybe_add


def honest_add(self, book, leg, obs, now, mode: str):
    """The same earned-lot path, with an honest charge: what the held lots are expected to lose at their current stop, plus the new lot's whole backstop.
    The add is decided afresh at each observation, so 'keeps trying' is the written rule here, not a side effect."""
    state = T.state_of(leg)
    quote = obs.options.get(leg.token)
    if state is None or quote is None or quote.ask <= 0 or quote.bid <= 0:
        return _maybe_add(self, book, leg, obs, now)
    cost = self.book.get("cost")
    stop_pct = float(settings.FNO_STOP_PREMIUM_PCT)
    child = R.child_full_loss(quote.ask, stop_pct, leg.lot_size, T.R.extra_cost(cost, 1), calc_fno_costs)
    locked = T.R.trail_locked(leg.direction, leg.entry_underlying, leg.trail_active, leg.trail_stop_underlying)
    if mode == "LOCK" and not locked:
        return T.refuse(self, state, "n11_not_locked")
    if mode == "HOUSE" and R.open_net(leg.entry_premium, quote.bid, leg.qty, T.R.extra_cost(cost, leg.lots), calc_fno_costs) < child:
        return T.refuse(self, state, "n11_not_house_money")
    level = leg.trail_stop_underlying if leg.trail_active and leg.trail_stop_underlying is not None else leg.stop_underlying
    parent = R.parent_loss_at_stop(leg.direction, obs.future.ltp, quote.bid, leg.delta_at_entry, level, leg.entry_premium, leg.premium_stop, leg.qty, T.R.extra_cost(cost, leg.lots), calc_fno_costs)
    usual = T.R.parent_risk, T.R.child_risk
    T.R.parent_risk = lambda *_a, **_k: parent
    T.R.child_risk = lambda *_a, **_k: child
    try:
        return _maybe_add(self, book, leg, obs, now)
    finally:
        T.R.parent_risk, T.R.child_risk = usual


def maybe_add(self, book, leg, obs, now):
    cfg = self.book.get("n11")
    if cfg and cfg.get("add"):
        n10 = self.book["n10"]
        saved = n10.get("parent_min")
        if cfg.get("add_any") and T.R.trail_locked(leg.direction, leg.entry_underlying, leg.trail_active, leg.trail_stop_underlying):
            n10["parent_min"] = 1
        try:
            return honest_add(self, book, leg, obs, now, cfg["add"])
        finally:
            n10["parent_min"] = saved
    if cfg and cfg.get("earn_vol") and leg.lots == 1 and vol_up(now):
        n10 = self.book["n10"]
        saved = n10.get("parent_min")
        n10["parent_min"] = 1
        try:
            return _maybe_add(self, book, leg, obs, now)
        finally:
            n10["parent_min"] = saved
    return _maybe_add(self, book, leg, obs, now)


T.maybe_add = maybe_add

# ---- books --------------------------------------------------------------------------------------------------------------


def base(label: str, third: bool = True, **cfg) -> dict:
    b = copy.deepcopy(B.r2(f"N11|{label}", third, B.WATCH))
    b["label"] = f"N11|{label}"
    b["n101"] = {"contract": "v1", "mode": "WATCH_FLAT"}
    b["n11"] = {"contract": "v1", **cfg}
    if cfg.get("evidence"):
        b["n09"]["vol_size"] = False
    return b


def screen_books() -> dict:
    """Development screen, all on seen years. It chooses what gets frozen; it is not a verdict."""
    return {
        "NOOP": base("NOOP"),
        "TR10": base("TR10", true_risk=True, k=1.0),
        "TR15": base("TR15", true_risk=True, k=1.5),
        "TR20": base("TR20", true_risk=True, k=2.0),
        "TR15_ALONE": base("TR15_ALONE", third=False, true_risk=True, k=1.5),
        "TR15_LOSS": base("TR15_LOSS", true_risk=True, k=1.5, loss_one=True),
        "EV": base("EV", evidence=True),
        "TR15_EV": base("TR15_EV", true_risk=True, k=1.5, evidence=True),
        "TR15_EV_LOSS": base("TR15_EV_LOSS", true_risk=True, k=1.5, evidence=True, loss_one=True),
        "NOISE": base("NOISE", noise_atr=1.25),
        "TR15_NOISE": base("TR15_NOISE", true_risk=True, k=1.5, noise_atr=1.25),
        "TR15_EV_LOSS_NOISE": base("TR15_EV_LOSS_NOISE", true_risk=True, k=1.5, evidence=True, loss_one=True, noise_atr=1.25),
    }


def screen2_books() -> dict:
    """Second development screen, from what the first showed."""
    core = dict(true_risk=True, k=1.5, loss_one=True)
    return {
        "STAND_ONLY": base("STAND_ONLY", stand=20),
        "STAND": base("STAND", stand=20, **core),
        "STAND10": base("STAND10", stand=10, **core),
        "STAND30": base("STAND30", stand=30, **core),
        "EARNV": base("EARNV", earn_vol=True, **core),
        "STAND_EARNV": base("STAND_EARNV", stand=20, earn_vol=True, **core),
        "STAND_EV": base("STAND_EV", stand=20, evidence=True, **core),
        "STAND_EV_EARNV": base("STAND_EV_EARNV", stand=20, evidence=True, earn_vol=True, **core),
    }


def screen3_books() -> dict:
    """Third development screen: nearby settings, what each part adds, and whether the reserve still earns its place."""
    core = dict(true_risk=True, k=1.5, loss_one=True, stand=20)
    out = {f"K{str(k).replace('.', '')}": base(f"K{k}", **{**core, "k": k}) for k in (1.0, 1.25, 1.75, 2.0)}
    out.update({f"NEED{n}": base(f"NEED{n}", **{**core, "stand": n}) for n in (15, 25)})
    out.update({f"RATIO{r}": base(f"RATIO{r}", **core, stand_ratio=r) for r in (0.9, 1.1)})
    out["NO_TR"] = base("NO_TR", stand=20, loss_one=True)
    out["NO_LOSS"] = base("NO_LOSS", stand=20, true_risk=True, k=1.5)
    out["NO_THIRD"] = base("NO_THIRD", third=False, **core)
    strict = base("STRICT", **core)
    strict["n10"]["no_retry"] = True
    out["STRICT"] = strict
    double = base("DOUBLE", **core)
    double["cost"] = [400.0, 10.0]
    out["DOUBLE"] = double
    clock = copy.deepcopy(M.candidates()["VOL_CLOCK"])
    clock["label"] = "N11|VCLOCK"
    clock["n10"] = {**T.n10_cfg("NATIVE", T.scaled(1.0), "RISK", False, 3), "parent_min": 2, "flat_risk": B.FLAT_RISK}
    clock["n11"] = {"contract": "v1", **core}
    out["VCLOCK"] = clock
    n08 = copy.deepcopy(Z.n08())
    n08["label"] = "N11|N08_STAND"
    n08["n10"] = T.n10_cfg("NATIVE", [], "RISK", False, 2)
    n08["n11"] = {"contract": "v1", "stand": 20}
    out["N08_STAND"] = n08
    flat = base("NOADAPT", **core)
    flat["cfg"] = {**flat.get("cfg", {}), "FNO_ADAPTIVE_RISK_ENABLED": False}
    out["NOADAPT"] = flat
    return out


def clock_book(label: str, third: bool = True, x: float = 1.0, **cfg) -> dict:
    """N08's trades, size by volatility, today's native 15% stop: no reserve above a floor, no floor that comes down."""
    b = copy.deepcopy(M.candidates()["VOL_CLOCK"])
    b["label"] = f"N11|{label}"
    b["n10"] = {**T.n10_cfg("NATIVE", T.scaled(x), "RISK", False, 3), "parent_min": 2, "flat_risk": B.FLAT_RISK} if third else T.n10_cfg("NATIVE", [], "RISK", False, 2)
    b["n11"] = {"contract": "v1", **cfg}
    return b


def screen4_books() -> dict:
    """Fourth development screen, on the native stop: what each part adds, and the map around the stand-aside's two readings."""
    core = dict(loss_one=True, stand=20)
    out = {"C0": clock_book("C0", **core),
           "C_NOLOSS": clock_book("C_NOLOSS", stand=20),
           "C_NOSTAND": clock_book("C_NOSTAND", loss_one=True),
           "C_NOTHIRD": clock_book("C_NOTHIRD", third=False, **core),
           "C_TR15": clock_book("C_TR15", true_risk=True, k=1.5, **core),
           "C_X075": clock_book("C_X075", x=0.75, **core),
           "C_X125": clock_book("C_X125", x=1.25, **core)}
    strict = clock_book("C_STRICT", **core)
    strict["n10"]["no_retry"] = True
    out["C_STRICT"] = strict
    double = clock_book("C_DOUBLE", **core)
    double["cost"] = [400.0, 10.0]
    out["C_DOUBLE"] = double
    for ratio in (0.8, 0.85, 0.9, 0.95, 1.05):
        out[f"R{ratio}"] = clock_book(f"R{ratio}", **core, stand_ratio=ratio)
    for need in (10, 15, 25, 30, 40):
        out[f"N{need}"] = clock_book(f"N{need}", **{**core, "stand": need})
    for need in (15, 25, 30):
        out[f"R0.9N{need}"] = clock_book(f"R0.9N{need}", **{**core, "stand": need}, stand_ratio=0.9)
    return out


def screen5_books() -> dict:
    """Fifth development screen: the earned lot with a written, honest charge in place of N10's retry on a proxy."""
    core = dict(loss_one=True, stand=20, stand_ratio=0.9)
    return {
        "R9": clock_book("R9", **core),
        "HONEST": clock_book("HONEST", add="HONEST", **core),
        "LOCK": clock_book("LOCK", add="LOCK", **core),
        "HOUSE": clock_book("HOUSE", add="HOUSE", **core),
        "LOCK_ANY": clock_book("LOCK_ANY", add="LOCK", add_any=True, **core),
        "HONEST_X075": clock_book("HONEST_X075", x=0.75, add="HONEST", **core),
        "HONEST_X125": clock_book("HONEST_X125", x=1.25, add="HONEST", **core),
        "LOCK_X075": clock_book("LOCK_X075", x=0.75, add="LOCK", **core),
        "LOCK_X125": clock_book("LOCK_X125", x=1.25, add="LOCK", **core),
    }


# ---- the frozen book, its neighbours, its parts ------------------------------------------------------------------------------

CORE = {"loss_one": True, "stand": 20, "stand_ratio": 0.9, "add": "HONEST"}


def n11_book(label: str = "N11", x: float = 1.0, **change) -> dict:
    cfg = {**CORE, **change}
    third = cfg.pop("third", True)
    cfg = {k: v for k, v in cfg.items() if v is not None}
    return clock_book(label, third=third, x=x, **cfg)


def control_books() -> dict:
    """Every N11 path on, nothing changed: each must equal its saved parent, trade for trade."""
    n08 = copy.deepcopy(Z.n08())
    n08["label"] = "N11|CTRL|N08"
    n08["n10"] = T.n10_cfg("NATIVE", [], "RISK", False, 2)
    n08["n11"] = {"contract": "v1"}
    return {"N08": n08, "VOL_CLOCK": clock_book("CTRL|VOL_CLOCK", third=False), "N10": base("CTRL|N10")}


def panel_books() -> dict:
    out = {"N11": n11_book(),
           "R0.85": n11_book("R0.85", stand_ratio=0.85), "R0.95": n11_book("R0.95", stand_ratio=0.95),
           "N15": n11_book("N15", stand=15), "N25": n11_book("N25", stand=25),
           "X0.75": n11_book("X0.75", x=0.75), "X1.25": n11_book("X1.25", x=1.25),
           "NO_STAND": n11_book("NO_STAND", stand=None, stand_ratio=None), "NO_LOSS": n11_book("NO_LOSS", loss_one=None),
           "NO_ADD": n11_book("NO_ADD", third=False, add=None), "NO_VOL": no_vol()}
    double = n11_book("DOUBLE")
    double["cost"] = [400.0, 10.0]
    out["DOUBLE"] = double
    return out


def no_vol() -> dict:
    """N11 with N08's own sizes: what size by volatility adds."""
    b = n11_book("NO_VOL")
    b["n09"]["vol_size"] = False
    return b


COSTS = {"195": [195.0, 5.0], "198": [198.0, 5.0], "199": [199.0, 5.0], "200": [200.0, 5.0], "201": [201.0, 5.0], "202": [202.0, 5.0], "205": [205.0, 5.0], "180": [180.0, 4.5], "220": [220.0, 5.5], "400": [400.0, 10.0]}


def carry_books() -> dict:
    """One account from January 2023: no reset, no deposit. N10 retry's matching ends are in the N10 and N10.1 studies."""
    earlier = YEARS[:YEARS.index(YEAR)]
    out = {}
    for tag, cost in COSTS.items():
        b = n11_book()
        b["cost"] = cost
        b["label"] = f"N091|CARRY|N11|{tag}"
        if earlier:
            saved = [json.loads((LOCAL / f"keys-carry-{y}.json").read_text(encoding="utf-8"))[tag] for y in earlier]
            b["carry"] = saved
            b["n091"]["state_from"] = saved[-1].rsplit("_", 1)[-1]
        out[tag] = b
    return out


def random_books() -> dict:
    """The first 10 random books, one lot, brakes off: plain, with the honest add, and with the stand-aside on their own market reading."""
    out = {}
    for i, source in enumerate(Y.null_fixed()[:10]):
        for tag, cfg, steps in (("BASE", {}, []), ("ADD", {"add": "HONEST"}, T.FIRST), ("STAND", {"stand": 20, "stand_ratio": 0.9}, [])):
            b = T.B.W.X.book(f"N11|RANDOM|{i:02d}|{tag}", members=[{**m, "gate": "ALWAYS"} for m in source["members"]], cfg=dict(T.B.W.S.RAW), cost=True)
            b["n10"] = {**T.n10_cfg("NATIVE", steps, "RISK", False, 2), "parent_min": 1, "flat_risk": B.FLAT_RISK}
            b["n11"] = {"contract": "v1", **cfg}
            out[f"RANDOM|{i:02d}|{tag}"] = b
    return out


PHASES = {"screen": screen_books, "screen2": screen2_books, "screen3": screen3_books, "screen4": screen4_books, "screen5": screen5_books,
          "controls": control_books, "panel": panel_books, "carry": carry_books, "random": random_books}
FROZEN = ("panel", "carry", "random")
SOURCES = ("n11_rules.py", "n11_lab.py", "PLAN.md", "driver.py", "test_n11.py", "EXAM_2022_N11.md")


def freeze() -> None:
    target = HERE / "freeze.json"
    assert not target.exists(), "already frozen"
    X.write(target, {"schema": "n11_freeze_v1", "sources": {s: T.sha(HERE / s) for s in SOURCES},
                     "books": {"controls": control_books(), "panel": panel_books(), "random": random_books()}, "core": CORE,
                     "note": "Written after five development screens on the four seen years, and before any frozen phase runs. Discipline, not an exam."})


def require_freeze() -> None:
    target = HERE / "freeze.json"
    assert json.loads(T.committed(target)) == json.loads(target.read_text(encoding="utf-8")), "freeze.json is not committed"
    for name, value in json.loads(target.read_text(encoding="utf-8"))["sources"].items():
        assert T.sha(HERE / name) == value, f"{name} changed after the freeze"


ECONOMIC = ("entry_time", "tradingsymbol", "entry_premium", "exit_time", "exit_premium", "exit_reason", "net_pnl", "entry_qty")


def parity() -> dict:
    """The saved parents, read from their own studies. A failed assert here means nothing else in this study counts."""
    k = {n: Y.task_key(b, "year", B.C.WINDOW) for n, b in control_books().items()}
    mine = {n: T.load(key) for n, key in k.items()}
    saved_n08 = json.loads((Z.LOCAL / f"keys-diag-{YEAR}.json").read_text(encoding="utf-8"))["N08"]
    saved_clock = json.loads((M.HERE / "_local" / f"keys-primary-{YEAR}.json").read_text(encoding="utf-8"))["VOL_CLOCK"]
    saved_n10 = json.loads((T.HERE / "_local" / f"keys-panel2-{YEAR}.json").read_text(encoding="utf-8"))["R2_THIRD_CW"]
    assert T.economics(mine["N08"]) == T.economics(T.load(saved_n08, Z.LOCAL / f"evals-{YEAR}")), "N08 differs"
    assert T.economics(mine["VOL_CLOCK"]) == T.economics(T.load(saved_clock, M.HERE / "_local" / "evals")), "VOL_CLOCK differs"
    assert T.economics(mine["N10"]) == T.economics(T.load(saved_n10, T.HERE / "_local" / "evals")), "N10 retry differs"
    out = {"year": YEAR, "identical": True, **{n: {"trades": len(v), "net": round(sum(t["net_pnl"] for t in v), 2)} for n, v in mine.items()}}
    X.write(HERE / f"parity-{YEAR}.json", out)
    return out


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
    if a.phase == "controls":
        print("PARITY OK", json.dumps(parity()), flush=True)
    print("DONE", a.phase, YEAR, len(books), flush=True)
