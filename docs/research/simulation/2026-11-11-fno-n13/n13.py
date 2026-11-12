"""N13: is the paper main book's profit lock worth keeping, on the five seen NIFTY windows (Round 30 lab over N11T)?

Forward motive (Production, Nov 5): OR20's native lock (arm 0.80 R, keep 0.50), looking every 10 s, sold a NIFTY call
at 12:03 for +Rs 1,029 on a 10-second dip under its floor; the one-lot paper record, looking once a minute like these
replays, held the same contract on its trail to 14:22 for +Rs 6,095. One case decides nothing; this tests switching
the lock off, per strategy and in full, on every seen window. Each arm is N012-A's exact Round 30 TrendReplay with the
locks of a set of strategies off (n13_grid). Run with N12_YEAR set; resumable, one JSON per arm and window in _local.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
N12 = HERE.parent / "2026-11-05-fno-n12"
sys.path[:0] = [str(HERE), str(N12)]
os.chdir(N12)
import round30 as R  # noqa: E402  (installs the Round 30 / N11T lab chain for N12_YEAR)
from regular_rules import trend_params  # noqa: E402  (N012-A's frozen rule)

from n13_grid import ARMS, CENTER, LINE  # noqa: E402

r, Y = R.r, R.Y
OUT = HERE / "_local" / r.YEAR


def strategy_of(params):
    """Which native lock a look's parameters carry: OR20 (0.80 R), SHIPPED (the global 0.40 R) or none."""
    if not params.get("FNO_PROFIT_LOCK_ENABLED"):
        return None
    arm = round(float(params.get("FNO_PROFIT_LOCK_ARM_R", 0.0)), 6)
    return {0.8: "OR20", 0.4: "SHIPPED"}.get(arm, "OTHER")


def params_for(off):
    every = "ALL" in off

    def chosen(params, position, trend):
        if every:                                         # LOCK_OFF: no profit lock, native or trend-made
            return {**params, "FNO_PROFIT_LOCK_ENABLED": False}
        if strategy_of(params) in off:                    # this strategy's native and trend-made lock both off
            return {**params, "FNO_PROFIT_LOCK_ENABLED": False}
        return trend_params(params, position, trend)
    return chosen


@contextmanager
def dispatch(choose):
    previous = r.exits.evaluate_single_leg_exit

    def evaluate(position, *, params, **kwargs):
        return previous(position, params=choose(params, position, getattr(position, "round30_status", "UNKNOWN")),
                        **kwargs)

    r.exits.evaluate_single_leg_exit = evaluate
    try:
        yield
    finally:
        r.exits.evaluate_single_leg_exit = previous


class ArmReplay(R.TrendReplay):
    choose = None

    def _manage(self, book, obs, now):
        for leg in book.open.values():
            if not hasattr(leg, "round30_trend"):
                leg.round30_trend = R.Trend()
            leg.round30_status = leg.round30_trend.update(now, obs.future.ltp, leg.direction)
        with dispatch(self.choose):
            return Y.BookReplay._manage(self, book, obs, now)


def by_strategy(raw):
    out = {}
    for t in raw["trades"]:
        if t.get("status") != "CLOSED":
            continue
        k = str(t.get("strategy") or t.get("source") or "?")
        row = out.setdefault(k, {"n": 0, "net": 0.0, "lock_exits": 0})
        row["n"] += 1
        row["net"] = round(row["net"] + t["net_pnl"], 2)
        row["lock_exits"] += t.get("exit_reason") == "profit_lock"
    return out


def run_arm(name):
    model = R.books()[R.TREND]
    model["label"] = f"N13|{name}"
    ArmReplay.choose = staticmethod(params_for(ARMS[name]))
    with Y.ROUTER.dispatch():
        raw = ArmReplay(Y.dataset("year"), model, Y.table("year"), "year").run(*r.WINDOW)
    for row in raw["trades"]:
        row.setdefault("status", "CLOSED" if row.get("net_pnl") is not None else "UNRESOLVED")
    out = r.metrics(raw)
    out["money_sha256"] = hashlib.sha256(json.dumps(r.money(raw), default=str).encode()).hexdigest()
    out["arm"] = name
    out["by_strategy"] = by_strategy(raw)
    out["exit_reasons"] = {}
    for t in raw["trades"]:
        k = str(t.get("exit_reason"))
        out["exit_reasons"][k] = out["exit_reasons"].get(k, 0) + 1
    return out


def main(budget_sec=480.0):
    freeze = json.loads((HERE / "freeze.json").read_bytes())
    for name, expected in freeze["source_sha256"].items():
        got = hashlib.sha256((r.ROOT / name).read_bytes()).hexdigest()
        assert got == expected, (name, got)
    assert sorted(freeze["arms"]) == sorted(LINE) and all(freeze["arms"][k] == list(ARMS[k]) for k in LINE)
    r.verify_freeze()
    r.f.Z.N.B.O27F.deny_network()
    r.f.Z.N.B.L._init()
    OUT.mkdir(parents=True, exist_ok=True)
    start = time.time()
    for name in [CENTER] + [n for n in LINE if n != CENTER]:
        path = OUT / f"{name}.json"
        if path.exists():
            continue
        if time.time() - start > budget_sec:
            print(r.YEAR, "budget reached", flush=True)
            return
        t0 = time.time()
        result = run_arm(name)
        if name == CENTER:     # the centre must be N012-A exactly (Round 30 TREND_ONLY)
            saved = json.loads((N12 / f"round30-{r.YEAR}.json").read_bytes())[R.TREND]
            for key in ("net", "closed", "unresolved", "closed_drawdown", "worst_day", "daily"):
                assert result[key] == saved[key], (r.YEAR, key, result[key], saved[key])
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
        print(r.YEAR, name, result["net"], result["closed"], result["unresolved"], round(time.time() - t0), flush=True)
    print(r.YEAR, "all arms done", flush=True)


if __name__ == "__main__":
    main(float(os.environ.get("N13_BUDGET_SEC", "480")))
