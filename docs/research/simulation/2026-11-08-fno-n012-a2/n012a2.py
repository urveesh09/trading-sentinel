"""N012-A2: a frozen 27-arm neighbourhood of the N012-A trend-aware profit lock, run per seen NIFTY window.

Each arm changes only the three numbers of regular_rules.trend_params that can bind on N11T (native lock arm 0.40 R,
keep 0.50): the keep fraction while the 5-minute futures trend supports the trade (S), the keep fraction while it
opposes it (A), and the lock switched on at 1.0 R while a trail is active and the trend opposes it (T, OFF = never).
N012-A is S 0.35, A 0.65, T 0.60 (its ADVERSE arm cap min(0.60, 0.40) never binds). Everything else is the exact
Round 30 TrendReplay over N11T. Run with N12_YEAR set; resumable, one JSON per arm and window in _local.
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

from n012a2_grid import ARMS, CENTER, arm_name  # noqa: E402

r, Y = R.r, R.Y
OUT = HERE / "_local" / r.YEAR


def params_for(s, a, t):
    def chosen(params, position, trend):
        if params["FNO_PROFIT_LOCK_ENABLED"] and trend == "SUPPORT":
            return {**params, "FNO_PROFIT_LOCK_KEEP_FRACTION": s}
        if params["FNO_PROFIT_LOCK_ENABLED"] and trend == "ADVERSE":
            return {**params, "FNO_PROFIT_LOCK_ARM_R": min(.60, params["FNO_PROFIT_LOCK_ARM_R"]),
                    "FNO_PROFIT_LOCK_KEEP_FRACTION": a}
        if t is not None and position.trail_active and trend == "ADVERSE":
            return {**params, "FNO_PROFIT_LOCK_ENABLED": True, "FNO_PROFIT_LOCK_ARM_R": 1.,
                    "FNO_PROFIT_LOCK_KEEP_FRACTION": t}
        return params
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


def run_arm(name):
    model = R.books()[R.TREND]
    model["label"] = f"N12A2|{name}"
    ArmReplay.choose = staticmethod(params_for(*ARMS[name]))
    with Y.ROUTER.dispatch():
        raw = ArmReplay(Y.dataset("year"), model, Y.table("year"), "year").run(*r.WINDOW)
    for row in raw["trades"]:
        row.setdefault("status", "CLOSED" if row.get("net_pnl") is not None else "UNRESOLVED")
    out = r.metrics(raw)
    out["money_sha256"] = hashlib.sha256(json.dumps(r.money(raw), default=str).encode()).hexdigest()
    out["arm"] = name
    return out


def main(budget_sec=480.0):
    freeze = json.loads((HERE / "freeze.json").read_bytes())
    for name, expected in freeze["source_sha256"].items():
        got = hashlib.sha256((r.ROOT / name).read_bytes()).hexdigest()
        assert got == expected, (name, got)
    assert sorted(freeze["arms"]) == sorted(ARMS)
    r.verify_freeze()
    r.f.Z.N.B.O27F.deny_network()
    r.f.Z.N.B.L._init()
    OUT.mkdir(parents=True, exist_ok=True)
    start = time.time()
    order = [arm_name(*CENTER)] + [n for n in ARMS if n != arm_name(*CENTER)]
    for name in order:
        path = OUT / f"{name}.json"
        if path.exists():
            continue
        if time.time() - start > budget_sec:
            print(r.YEAR, "budget reached", flush=True)
            return
        t0 = time.time()
        result = run_arm(name)
        if name == arm_name(*CENTER):     # the centre must be N012-A exactly (Round 30 TREND_ONLY)
            saved = json.loads((N12 / f"round30-{r.YEAR}.json").read_bytes())[R.TREND]
            for key in ("net", "closed", "unresolved", "closed_drawdown", "worst_day", "daily"):
                assert result[key] == saved[key], (r.YEAR, key, result[key], saved[key])
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
        print(r.YEAR, name, result["net"], result["closed"], result["unresolved"], round(time.time() - t0), flush=True)
    print(r.YEAR, "all arms done", flush=True)


if __name__ == "__main__":
    main(float(os.environ.get("N12A2_BUDGET_SEC", "480")))
