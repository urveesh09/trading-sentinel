"""Pre-registered consistency grid for the NIFTY single-leg F&O book (research only, O27).

python scripts/run_fno_consistency_grid.py freeze --data <replay dataset folder> --out docs/research/fno/<dated>
python scripts/run_fno_consistency_grid.py run --out docs/research/fno/<dated> --jobs 6

The owner's question (Oct 27): of many entry x exit combinations, which is the most CONSISTENT, not the most
earning. Every arm is the whole live book (fno_policy_replay: entry plan, sizing, loss brakes, the exit ladder
at fast-exit cadence, bid/ask fills, costs) with one entry signal and one exit setting changed.

``freeze`` binds the grid, the windows, the source and dataset hashes, the effective F&O settings and the
selection rule into ``freeze.json``; commit it before ``run``. ``run`` refuses if anything bound changed,
replays every arm once over the whole window (parsed sessions cached under ``_local/``), splits each arm's
trades by entry date into the declared windows, applies the frozen rule and writes ``results.json``.
No network, broker or Production. A recommendation authorizes a forward shadow only.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import pickle
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-engine"))
from fno_policy_replay import ReplayData, ReplayPolicy, run_replay  # noqa: E402

SOURCES = tuple(f"python-engine/{name}.py" for name in (
    "config", "fno_policy_replay", "fno_shadow", "fno_engine_mom", "fno_entry_plan", "fno_exit_rules",
    "fno_chain", "fno_costs", "cost_schedules", "fno_adaptive_risk", "fno_shared_risk", "fno_exit_experiment",
    "intraday_spread_archive_adapter", "fno_risk", "fno_models", "options_math")) + (
    "scripts/run_fno_consistency_grid.py",)

FULL = ("2026-09-10", "2026-10-26")
WINDOWS = {"A_select": ("2026-09-10", "2026-10-09"), "B_check": ("2026-10-12", "2026-10-26")}

# Exit axes, each in neighbour order. Locks run from the earliest arming to never (OFF).
LOCKS = {
    "LOCK_TIGHT": {"FNO_PROFIT_LOCK_ENABLED": True, "FNO_PROFIT_LOCK_ARM_R": 0.25,
                   "FNO_PROFIT_LOCK_FLOOR_R": 0.10, "FNO_PROFIT_LOCK_KEEP_FRACTION": 0.6},
    "LOCK_LIVE": {"FNO_PROFIT_LOCK_ENABLED": True, "FNO_PROFIT_LOCK_ARM_R": 0.40,
                  "FNO_PROFIT_LOCK_FLOOR_R": 0.10, "FNO_PROFIT_LOCK_KEEP_FRACTION": 0.5},
    "LOCK_LATE": {"FNO_PROFIT_LOCK_ENABLED": True, "FNO_PROFIT_LOCK_ARM_R": 0.80,
                  "FNO_PROFIT_LOCK_FLOOR_R": 0.10, "FNO_PROFIT_LOCK_KEEP_FRACTION": 0.5},
    "LOCK_OFF": {"FNO_PROFIT_LOCK_ENABLED": False},
}
TIME_STOPS = (30, 45, 75)
TRAILS = (0.6, 1.0, 1.5)
CURRENT_ARM = "OR30|LOCK_LIVE|T45|TR1.0"
PARITY_ARM = "PARITY_OR30_GENERIC|LOCK_LIVE|T45|TR1.0"

RULE = {
    "metric_cs": "net_excluding_best_winner / max(max_drawdown, 1000), on the arm's trades in the window",
    "eligible": {"window": "A_select", "min_trades": 8, "net_pnl_gt": 0, "net_excluding_best_winner_gt": 0},
    "score": "plateau_cs: the median CS on A_select of the arm and its exit neighbours (same entry; one step on "
             "exactly one axis: lock TIGHT-LIVE-LATE-OFF, time stop 30-45-75, trail 0.6-1.0-1.5)",
    "rank": "eligible arms by plateau_cs desc, then green_week_share desc, then red_days asc, then name",
    "check": {"window": "B_check", "net_pnl_ge": 0,
              "max_drawdown_le": "max(1.5 * CURRENT max_drawdown on B_check, 5000)"},
    "recommend": "the first ranked arm that passes the check; if none passes, keep CURRENT",
    "if_recommended": "broker-free live shadow + nightly replay on sessions after the freeze; no paper or live "
                      "change in the proving week; promotion is the owner's call on forward evidence",
    "cs_drawdown_floor": 1000, "check_drawdown_floor": 5000, "min_trades": 8,
}


def entries() -> dict:
    """Entry name -> signal variant (None = the shipped evaluator). Each family with and without the EMA check."""
    from fno_shadow import VARIANTS
    families = {"OR30": VARIANTS["FNO_BASE"], "OR20": VARIANTS["FNO_OR_20"], "OR45": VARIANTS["FNO_OR_45"],
                "CONFIRM1": VARIANTS["FNO_CONFIRM_1"], "CONT": VARIANTS["FNO_CONTINUATION"]}
    out = {}
    for family, variant in families.items():
        out[family] = None if family == "OR30" else variant
        out[f"{family}_NOEMA"] = replace(variant, name=f"GRID_{family}_NOEMA", ema_filter=False)
    return out


def exits() -> dict:
    return {f"{lock}|T{minutes}|TR{trail}": {**LOCKS[lock], "FNO_TIME_STOP_MIN": float(minutes),
                                              "FNO_TRAIL_ATR_MULT": float(trail)}
            for lock in LOCKS for minutes in TIME_STOPS for trail in TRAILS}


def arms() -> dict:
    """Arm name -> ReplayPolicy. Fast-exit management, as live. Plus the parity arm (not ranked): the shipped
    break evaluated by the variant code path, which must trade exactly as CURRENT."""
    from fno_shadow import VARIANTS
    out = {}
    signals = {**entries(), "PARITY_OR30_GENERIC": replace(VARIANTS["FNO_BASE"], name="GRID_OR30_GENERIC")}
    for entry, variant in signals.items():
        for exit_name, params in exits().items():
            name = f"{entry}|{exit_name}"
            if entry.startswith("PARITY") and name != PARITY_ARM:
                continue
            out[name] = ReplayPolicy(name=name, manage_every_observation=True,
                                     exit_overrides=tuple(sorted(params.items())), signal_variant=variant)
    return out


def neighbours(arm: str) -> list[str]:
    entry, lock, minutes, trail = arm.split("|")
    axes = [(list(LOCKS), lock, lambda v: f"{entry}|{v}|{minutes}|{trail}"),
            ([f"T{m}" for m in TIME_STOPS], minutes, lambda v: f"{entry}|{lock}|{v}|{trail}"),
            ([f"TR{t}" for t in TRAILS], trail, lambda v: f"{entry}|{lock}|{minutes}|{v}")]
    out = []
    for order, value, name in axes:
        i = order.index(value)
        out += [name(order[j]) for j in (i - 1, i + 1) if 0 <= j < len(order)]
    return out


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_dataset(folder: Path) -> dict:
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    for rel, digest in manifest["files_sha256"].items():
        if _sha(folder / rel) != digest:
            raise SystemExit(f"dataset file changed: {rel}")
    if manifest.get("unsealed_days"):
        raise SystemExit(f"dataset has unsealed sessions {manifest['unsealed_days']}; export again")
    return {"manifest_sha256": _sha(folder / "manifest.json"), "quote_days": manifest["quote_days"]}


def _settings_check() -> dict:
    """The live values the CURRENT arm stands for; the grid's CURRENT must be the shipped book."""
    from config import settings
    live = {"FNO_FAST_EXIT_ENABLED": bool(settings.FNO_FAST_EXIT_ENABLED),
            "FNO_TIME_STOP_MIN": float(settings.FNO_TIME_STOP_MIN),
            "FNO_TRAIL_ATR_MULT": float(settings.FNO_TRAIL_ATR_MULT),
            **{k: type(v)(getattr(settings, k)) for k, v in LOCKS["LOCK_LIVE"].items()}}
    expected = {"FNO_FAST_EXIT_ENABLED": True, "FNO_TIME_STOP_MIN": 45.0, "FNO_TRAIL_ATR_MULT": 1.0,
                **LOCKS["LOCK_LIVE"]}
    if live != expected:
        raise SystemExit(f"live settings no longer match the CURRENT arm: {live} != {expected}")
    snapshot = {k: repr(v) for k, v in sorted(settings.model_dump().items()) if k.startswith("FNO_")}
    return {"current_arm": CURRENT_ARM, "fno_settings_sha256": hashlib.sha256(
        json.dumps(snapshot, sort_keys=True).encode()).hexdigest(), "fno_settings_count": len(snapshot)}


def _bound(dataset: Path) -> dict:
    return {"sources": {rel: _sha(ROOT / rel) for rel in SOURCES}, "dataset": _verify_dataset(dataset),
            "settings": _settings_check()}


def _write_new(path: Path, payload) -> None:
    if path.exists():
        raise SystemExit(f"{path} exists; a frozen grid is scored once")
    part = path.with_name(path.name + f".{os.getpid()}.part")
    part.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    os.replace(part, path)


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def _policy_record(policy: ReplayPolicy) -> dict:
    return json.loads(json.dumps(asdict(policy), default=str))


def freeze(dataset: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    grid = arms()
    _write_new(out / "freeze.json", {
        "schema": "fno_consistency_grid_freeze_v1", "dataset_folder": _relative(dataset), "bound": _bound(dataset),
        "full_window": FULL, "windows": WINDOWS, "rule": RULE, "current_arm": CURRENT_ARM, "parity_arm": PARITY_ARM,
        "axes": {"entries": list(entries()), "locks": LOCKS, "time_stops": TIME_STOPS, "trails": TRAILS},
        "arm_count": len(grid), "arms": {name: _policy_record(policy) for name, policy in grid.items()},
        "can_place_orders": False, "qualification": "NOT_ASSESSED"})
    print(f"frozen {len(grid)} arms:", out / "freeze.json")


class CachedReplayData(ReplayData):
    """ReplayData whose parsed sessions are pickled once per dataset (research-local cache)."""

    def __init__(self, root: Path, cache: Path):
        super().__init__(root)
        self.cache = cache

    def observations(self, day: str):
        path = self.cache / f"{day}.pkl"
        if path.is_file():
            return pickle.loads(path.read_bytes())
        parsed = super().observations(day)
        part = path.with_name(f"{day}.{os.getpid()}.part")
        part.write_bytes(pickle.dumps(parsed, protocol=pickle.HIGHEST_PROTOCOL))
        os.replace(part, path)
        return parsed


def _warm(task: tuple) -> str:
    dataset, cache, day = task
    CachedReplayData(Path(dataset), Path(cache)).observations(day)
    return day


def _arm_file(local: Path, arm: str) -> Path:
    return local / "arms" / (arm.replace("|", "__") + ".json")


def _run_arm(task: tuple) -> str:
    arm, policy, dataset, cache, target = task
    data = CachedReplayData(Path(dataset), Path(cache))
    result = run_replay(dataset, start=FULL[0], end=FULL[1], policy=policy, data=data)
    keep = {k: result[k] for k in ("window", "sessions", "start_equity", "trades", "summary", "funnel", "notes",
                                   "archive_exclusions", "expiry_calendar")}
    keep["policy"] = _policy_record(policy)
    keep["parity_vs_live"] = {k: result["parity_vs_live"][k] for k in ("live_trades", "replayed_trades",
                                                                        "live_only", "replay_only")}
    _write_new(Path(target), keep)
    return arm


def window_metrics(trades: list[dict], sessions: list[str]) -> dict:
    """Consistency metrics of the trades entered in one window (``sessions``: that window's archived days)."""
    days = set(sessions)
    mine = [t for t in trades if t["entry_time"][:10] in days]
    closed = sorted((t for t in mine if "net_pnl" in t), key=lambda t: t["exit_time"])
    net = [float(t["net_pnl"]) for t in closed]
    running = peak = drawdown = 0.0
    by_day: dict = defaultdict(float)
    for trade in closed:
        running += trade["net_pnl"]
        peak, drawdown = max(peak, running), max(drawdown, peak - running)
        by_day[trade["entry_time"][:10]] += trade["net_pnl"]
    weeks: dict = {date.fromisoformat(d).isocalendar()[:2]: 0.0 for d in sessions}
    for day, pnl in by_day.items():
        weeks[date.fromisoformat(day).isocalendar()[:2]] += pnl
    best = max(net, default=0.0)
    ex_best = sum(net) - max(best, 0.0)
    wins, losses = [x for x in net if x > 0], [x for x in net if x < 0]
    return {
        "trades": len(closed), "unresolved": len(mine) - len(closed), "net_pnl": round(sum(net), 2),
        "net_excluding_best_winner": round(ex_best, 2), "max_drawdown": round(drawdown, 2),
        "cs": round(ex_best / max(drawdown, RULE["cs_drawdown_floor"]), 4),
        "win_rate_pct": round(100 * len(wins) / len(net), 1) if net else None,
        "profit_factor": round(sum(wins) / -sum(losses), 3) if losses else None,
        "net_per_lot": round(sum(float(t["net_pnl"]) / max(1, int(t.get("lots_at_exit") or 1)) for t in closed), 2),
        "sessions": len(sessions), "trade_days": len(by_day), "green_days": sum(v > 0 for v in by_day.values()),
        "red_days": sum(v < 0 for v in by_day.values()), "worst_day": round(min(by_day.values(), default=0.0), 2),
        "best_day": round(max(by_day.values(), default=0.0), 2),
        "weeks": len(weeks), "green_weeks": sum(v > 0 for v in weeks.values()),
        "red_weeks": sum(v < 0 for v in weeks.values()),
        "green_week_share": round(sum(v > 0 for v in weeks.values()) / len(weeks), 4) if weeks else 0.0,
        "exit_reasons": dict(sorted(Counter(t["exit_reason"] for t in closed).items())),
    }


def decide(metrics: dict) -> dict:
    """The frozen rule over {arm: {window: metrics}} (the parity arm is not ranked)."""
    ranked_arms = [a for a in metrics if not a.startswith("PARITY")]
    cs_a = {a: metrics[a]["A_select"]["cs"] for a in ranked_arms}
    plateau = {a: statistics.median([cs_a[a], *[cs_a[n] for n in neighbours(a)]]) for a in ranked_arms}
    eligible = [a for a in ranked_arms if metrics[a]["A_select"]["trades"] >= RULE["min_trades"]
                and metrics[a]["A_select"]["net_pnl"] > 0 and metrics[a]["A_select"]["net_excluding_best_winner"] > 0]
    order = sorted(eligible, key=lambda a: (-plateau[a], -metrics[a]["A_select"]["green_week_share"],
                                            metrics[a]["A_select"]["red_days"], a))
    current_b_dd = metrics[CURRENT_ARM]["B_check"]["max_drawdown"]
    dd_limit = max(1.5 * current_b_dd, RULE["check_drawdown_floor"])
    checks = {a: {"net_pnl_ge_0": metrics[a]["B_check"]["net_pnl"] >= 0,
                  "max_drawdown_within": metrics[a]["B_check"]["max_drawdown"] <= dd_limit} for a in order}
    passed = [a for a in order if all(checks[a].values())]
    return {"plateau_cs": {a: round(v, 4) for a, v in plateau.items()}, "eligible_count": len(eligible),
            "rank": order, "checks": checks, "b_drawdown_limit": round(dd_limit, 2),
            "current_rank": order.index(CURRENT_ARM) + 1 if CURRENT_ARM in order else None,
            "recommended": passed[0] if passed else CURRENT_ARM,
            "verdict": ("CURRENT_IS_THE_MOST_CONSISTENT" if passed and passed[0] == CURRENT_ARM else
                        "SHADOW_CANDIDATE" if passed else "NONE_PASSED_KEEP_CURRENT"),
            "qualification": "NOT_ASSESSED"}


def run(out: Path, jobs: int) -> None:
    frozen = json.loads((out / "freeze.json").read_text(encoding="utf-8"))
    dataset = ROOT / frozen["dataset_folder"]
    if frozen["bound"] != _bound(dataset):
        raise SystemExit("bound inputs changed since freeze; refusing to score")
    grid = arms()
    if sorted(grid) != sorted(frozen["arms"]) or any(_policy_record(grid[a]) != frozen["arms"][a] for a in grid):
        raise SystemExit("grid differs from the frozen arms; refusing to score")
    local = out / "_local"
    cache = local / "observations" / frozen["bound"]["dataset"]["manifest_sha256"][:16]
    (local / "arms").mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    days = [d for d in frozen["bound"]["dataset"]["quote_days"] if FULL[0] <= d <= FULL[1]]
    tasks = [(a, grid[a], str(dataset), str(cache), str(_arm_file(local, a))) for a in grid
             if not _arm_file(local, a).exists()]   # a crash resumes; an arm file is written once and never rescored
    from concurrent.futures import ProcessPoolExecutor
    pool = ProcessPoolExecutor(max_workers=jobs) if jobs > 1 else None
    mapper = pool.map if pool else map
    try:
        for _ in mapper(_warm, [(str(dataset), str(cache), d) for d in days]):
            pass
        print(f"cache warm: {len(days)} sessions; arms to run: {len(tasks)} of {len(grid)}", flush=True)
        for done, arm in enumerate(mapper(_run_arm, tasks), 1):
            if done % 10 == 0 or done == len(tasks):
                print(f"  {done}/{len(tasks)} {arm}", flush=True)
    finally:
        if pool:
            pool.shutdown()
    if frozen["bound"] != _bound(dataset):
        raise SystemExit("bound inputs changed during scoring; refusing results")
    sessions = {w: [d for d in days if lo <= d <= hi] for w, (lo, hi) in {**WINDOWS, "FULL": FULL}.items()}
    metrics, parity = {}, {}
    for arm in grid:
        report = json.loads(_arm_file(local, arm).read_text(encoding="utf-8"))
        metrics[arm] = {w: window_metrics(report["trades"], s) for w, s in sessions.items()}
        metrics[arm]["funnel_accepted"] = report["funnel"].get("accepted", 0)
        metrics[arm]["notes"] = {k: v for k, v in report["notes"].items() if not k.startswith(("regime_", "grid_"))}
        if arm in (CURRENT_ARM, PARITY_ARM):
            parity[arm] = [(t["bar_ts"], t["tradingsymbol"], t["entry_time"], t.get("exit_reason"), t.get("net_pnl"))
                           for t in report["trades"]]
    decision = decide(metrics)
    decision["parity_generic_path_equals_current"] = parity[PARITY_ARM] == parity[CURRENT_ARM]
    _write_new(out / "results.json", {"schema": "fno_consistency_grid_results_v1",
                                      "freeze_sha256": _sha(out / "freeze.json"), "sessions": sessions,
                                      "metrics": metrics, "decision": decision,
                                      "bound_verified_after_scoring": True})
    print(json.dumps({k: decision[k] for k in ("eligible_count", "current_rank", "recommended", "verdict",
                                               "b_drawdown_limit", "parity_generic_path_equals_current")}))
    for i, arm in enumerate(decision["rank"][:15], 1):
        a, b = metrics[arm]["A_select"], metrics[arm]["B_check"]
        print(f"{i:3} {arm:40} plateau={decision['plateau_cs'][arm]:6.2f} A {a['trades']:3}t {a['net_pnl']:9.0f} "
              f"dd {a['max_drawdown']:7.0f} | B {b['trades']:3}t {b['net_pnl']:9.0f} dd {b['max_drawdown']:7.0f} "
              f"{'PASS' if all(decision['checks'][arm].values()) else 'fail'}")


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("action", choices=("freeze", "run"))
    cli.add_argument("--data", type=Path, help="freeze: the exported replay dataset folder")
    cli.add_argument("--out", type=Path, required=True)
    cli.add_argument("--jobs", type=int, default=4)
    args = cli.parse_args()
    if args.action == "freeze":
        if not args.data:
            cli.error("freeze needs --data")
        freeze(args.data.resolve(), args.out.resolve())
    else:
        run(args.out.resolve(), max(1, args.jobs))


if __name__ == "__main__":
    main()
