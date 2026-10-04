"""Pre-registered candidate-vs-baseline studies on archived Yahoo snapshots.

python scripts/run_preregistered_study.py list
python scripts/run_preregistered_study.py freeze STUDY --out docs/research/yahoo/<dated-folder>
python scripts/run_preregistered_study.py run    STUDY --out docs/research/yahoo/<dated-folder>

``freeze`` writes ``freeze.json`` binding the source-file hashes, the validated
snapshot, the configuration, every arm, window and book, and the decision rule.
Commit it *before* ``run``. ``run`` refuses to start if any bound input
changed, scores every (window, book, arm) exactly once into ``_local/``, and
writes ``results.json`` with the verdict. No network, broker or Production.
See docs/RESEARCH_TESTING_METHOD.md for the method and how to add a study.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-engine"))
from backtest_cli import _atomic_json_new, run as run_backtest, verify_snapshot  # noqa: E402

YAHOO = ROOT / "docs/research/yahoo"
KITE = ROOT / "docs/research/kite"
REVIEW = YAHOO / "2026-10-04-q3-review-final/_local"
Q3_SNAPSHOT = YAHOO / "2026-10-04-q3-review-baseline/_local/validated-yahoo.sqlite"
COMMON_SOURCES = ("python-engine/config.py", "python-engine/backtest_lab.py", "scripts/run_preregistered_study.py")


@dataclass(frozen=True)
class Study:
    """One frozen comparison. Arms are config overrides; books vary capital."""
    strategy: str
    snapshot: Path
    base_config: Callable[[], dict]
    sources: tuple[str, ...]
    windows: dict[str, tuple[tuple[str, str], ...]]
    arms: dict[str, dict]
    candidate: str
    decision_window: str
    drawdown_key: str
    drawdown_floor: float
    metrics: str                       # "trades", "portfolio" or "fno" (replay summary)
    books: dict[str, dict] = field(default_factory=lambda: {"default": {}})
    runner: str = "backtest_cli"       # or "fno_replay" (archived F&O quotes, snapshot is a dataset folder)
    decision_book: str = "default"
    hypothesis: str = ""


def _config_from(report: str, **overrides) -> Callable[[], dict]:
    return lambda: {**json.loads((REVIEW / report).read_text())["request"]["config"], **overrides}


STUDIES: dict[str, Study] = {
    "penny-smart-t4": Study(
        strategy="penny_breakout_mis_lifecycle_1m",
        snapshot=YAHOO / "2026-10-04-penny-trader-window/_local/validated-yahoo.sqlite",
        base_config=_config_from("penny-mis-recent-diagnostic-gap-sensitivity-report.json",
                                 stop_policy="NOISE_FLOOR",benchmark_ticker=None),
        sources=("python-engine/adaptive_penny_policy.py", "python-engine/penny_lifecycle_replay.py",
                 "python-engine/penny_engine_breakout.py", "python-engine/penny_risk.py",
                 "python-engine/penny_shadow.py", "python-engine/cost_schedules.py",
                 "python-engine/penny_smart_policy.py", "python-engine/penny_smart_book.py",
                 "python-engine/penny_smart_shadow.py", "python-engine/penny_scanner.py",
                 "python-engine/main.py", "python-engine/backtest_cli.py"),
        windows={"seen_short": (("2026-09-24", "2026-09-30"),),
                 "seen_broader": (("2026-09-07", "2026-10-01"),)},
        arms={name:{"candidate_policy":name} for name in (
            "BASELINE","PEN_STRENGTH_RANK","PEN_SMART_EXIT","PEN_SMART_ENTRY","PEN_SMART_TRADER")},
        books={"owner_2000":{"bankroll":2000.}},decision_book="owner_2000",
        candidate="PEN_SMART_TRADER",decision_window="seen_broader",
        drawdown_key="max_drawdown",drawdown_floor=20.,metrics="trades",
        hypothesis="Frozen strength/timing/winner management improves owner-budget Penny economics; "
                   "both windows are previously examined diagnostics, never untouched qualification."),
    "penny-trader-t1": Study(
        strategy="penny_breakout_mis_lifecycle_1m",
        snapshot=YAHOO / "2026-10-04-penny-trader-window/_local/validated-yahoo.sqlite",
        base_config=_config_from("penny-mis-recent-diagnostic-gap-sensitivity-report.json"),
        sources=("python-engine/adaptive_penny_policy.py", "python-engine/penny_lifecycle_replay.py",
                 "python-engine/penny_engine_breakout.py", "python-engine/penny_risk.py",
                 "python-engine/penny_shadow.py", "python-engine/cost_schedules.py"),
        windows={"development": (("2026-09-24", "2026-09-30"),),
                 "untouched": (("2026-09-07", "2026-09-23"), ("2026-10-01", "2026-10-01"))},
        arms={name: {"candidate_policy": name} for name in (
            "BASELINE", "PEN_TRADER_V1", "PEN_TRADER_V1_THESIS", "PEN_BASE_THESIS", "PEN_TRADER_V2")},
        candidate="PEN_TRADER_V2", decision_window="untouched",
        drawdown_key="max_drawdown", drawdown_floor=50.0, metrics="trades",
        hypothesis="Day-high structure, participation and thesis exits beat the shipped Penny MIS entry."),
    "edge-trader-t1": Study(
        strategy="penny_edge_portfolio_replay", snapshot=Q3_SNAPSHOT,
        base_config=lambda: json.loads((YAHOO / "2026-10-04-review-candidates/_local/edge-next-open-proxy-report.json")
                                       .read_text())["request"]["config"],
        sources=("python-engine/daily_portfolio.py", "python-engine/edge_portfolio_replay.py",
                 "python-engine/penny_edge_live.py", "python-engine/penny_edge_engine.py", "python-engine/penny_risk.py"),
        windows={"development": (("2026-07-01", "2026-09-30"),), "untouched": (("2026-01-01", "2026-06-30"),)},
        arms={"BASELINE": {"policy": "BASELINE"}, "EDGE_TRADER_V1": {"policy": "EDGE_TRADER_V1"}},
        books={"paper_100k": {"bankroll": 100000.0}, "owner_3000": {"bankroll": 3000.0}}, decision_book="paper_100k",
        candidate="EDGE_TRADER_V1", decision_window="untouched",
        drawdown_key="max_marked_drawdown_pct", drawdown_floor=5.0, metrics="portfolio",
        hypothesis="Separate MR/MO thesis entries and exits beat shipped EDGE execution."),
    "edge-overnight-t1": Study(
        strategy="penny_edge_portfolio_replay", snapshot=Q3_SNAPSHOT,
        base_config=lambda: {**json.loads((YAHOO / "2026-10-04-review-candidates/_local/edge-next-open-proxy-report.json")
                                          .read_text())["request"]["config"], "cost_model": "CNC_FULL"},
        sources=("python-engine/daily_portfolio.py", "python-engine/edge_portfolio_replay.py",
                 "python-engine/penny_edge_live.py", "python-engine/penny_edge_engine.py", "python-engine/penny_risk.py"),
        windows={"development": (("2026-01-01", "2026-09-30"),), "untouched": (("2024-03-01", "2025-12-31"),)},
        arms={"BASELINE": {"policy": "BASELINE"}, "EDGE_OVERNIGHT": {"policy": "EDGE_OVERNIGHT"},
              "EDGE_OVERNIGHT_S60": {"policy": "EDGE_OVERNIGHT", "min_strength": 0.6}},
        books={"paper_25k": {"bankroll": 25000.0}, "paper_100k": {"bankroll": 100000.0},
               "owner_3000": {"bankroll": 3000.0}}, decision_book="paper_25k",
        candidate="EDGE_OVERNIGHT", decision_window="untouched",
        drawdown_key="max_marked_drawdown_pct", drawdown_floor=5.0, metrics="portfolio",
        hypothesis="The shipped EDGE signals earn their move overnight (Jan-Sep 2026 event study): buying at the "
                   "signal close (15:20 proxy, +25 bps) and selling at the next open beats buying at the next open, "
                   "after full CNC costs (buy STT and DP charge) and a 1% liquidity cap."),
    "range-trader-t2": Study(
        strategy="range_reversion_portfolio_replay", snapshot=Q3_SNAPSHOT,
        base_config=lambda: {"tickers": json.loads((REVIEW / "range-report.json").read_text())["request"]["config"]["tickers"],
                             "calendar_ticker": "NIFTY 50", "bankroll": 100000.0},
        sources=("python-engine/daily_portfolio.py", "python-engine/range_portfolio_replay.py",
                 "python-engine/range_reversion.py", "python-engine/engine.py"),
        windows={"development": (("2026-07-01", "2026-09-30"),), "untouched": (("2026-01-01", "2026-06-30"),)},
        arms={name: {"policy": name} for name in ("BASELINE", "RANGE_RECLAIM_ENTRY", "RANGE_TRADER_V1")},
        candidate="RANGE_TRADER_V1", decision_window="untouched",
        drawdown_key="max_marked_drawdown_pct", drawdown_floor=5.0, metrics="portfolio",
        hypothesis="Arming on the touch and entering on stabilization, with thesis exits, beats buying every touch."),
    "swing-trader-t2": Study(
        strategy="swing_regime_portfolio_replay", snapshot=Q3_SNAPSHOT,
        base_config=_config_from("swing-report.json"),
        sources=("python-engine/daily_portfolio.py", "python-engine/swing_portfolio_replay.py",
                 "python-engine/research_daily_decision_replay.py", "python-engine/engine.py",
                 "python-engine/regime.py"),
        windows={"development": (("2026-07-01", "2026-09-30"),), "untouched": (("2026-01-01", "2026-06-30"),)},
        arms={name: {"policy": name} for name in ("BASELINE", "SWING_PULLBACK_ENTRY", "SWING_TRADER_V1")},
        books={"system_4500": {"bankroll": 4500.0}, "owner_1000": {"bankroll": 1000.0}}, decision_book="system_4500",
        candidate="SWING_TRADER_V1", decision_window="untouched",
        drawdown_key="max_marked_drawdown_pct", drawdown_floor=5.0, metrics="portfolio",
        hypothesis="Waiting for a pullback when extended and letting trend winners run beats the tracker exits."),
    "fno-trader-v1": Study(
        strategy="fno_policy_replay.single_leg",
        snapshot=ROOT / "docs/research/fno/2026-10-04-archive/_local",
        base_config=lambda: {},
        sources=("python-engine/fno_policy_replay.py", "python-engine/fno_entry_plan.py",
                 "python-engine/fno_engine_mom.py", "python-engine/fno_chain.py", "python-engine/fno_gates.py",
                 "python-engine/fno_risk.py", "python-engine/fno_exit_rules.py", "python-engine/fno_costs.py",
                 "python-engine/fno_shared_risk.py", "python-engine/options_math.py",
                 "python-engine/fno_exit_experiment.py", "python-engine/intraday_spread_archive_adapter.py"),
        windows={"development": (("2026-09-10", "2026-09-23"),), "untouched": (("2026-09-24", "2026-10-01"),)},
        arms={name: {"policy": name} for name in (
            "BASELINE", "FNO_FAST_EXIT", "FNO_PARTIAL_TRAIL", "FNO_HOUSE_MONEY_PYRAMID", "FNO_TREND_DAY",
            "FNO_TRADER_V1")},
        candidate="FNO_TRADER_V1", decision_window="untouched",
        drawdown_key="max_drawdown", drawdown_floor=5000.0, metrics="fno", runner="fno_replay",
        hypothesis="A faster exit loop, banking half at target, house-money pyramiding and trading only "
                   "compressed-open days beat the shipped single-leg F&O book (component arms are attribution)."),
    "momentum-thesis-t2": Study(
        strategy="momentum_intraday_15m_replay",
        snapshot=YAHOO / "2026-10-04-momentum-window/_local/validated-yahoo.sqlite",
        base_config=_config_from("momentum-recent-diagnostic-report.json", entry_clock="NEXT_BAR_OPEN"),
        sources=("python-engine/momentum_replay.py", "python-engine/momentum_exits.py", "python-engine/engine.py",
                 "python-engine/momentum_shadow.py"),
        windows={"development": (("2026-09-24", "2026-09-30"),),
                 "untouched": (("2026-08-10", "2026-09-23"), ("2026-10-01", "2026-10-01"))},
        arms={"BASELINE": {"exit_model": "LIVE_EXIT_LIFECYCLE"}, "MOM_THESIS_EXIT": {"exit_model": "THESIS_EXIT"}},
        candidate="MOM_THESIS_EXIT", decision_window="untouched",
        drawdown_key="max_drawdown", drawdown_floor=50.0, metrics="trades",
        hypothesis="A thesis exit (T1 half, breakeven, trail, VWAP failure, stall) beats shipped Momentum exits "
                   "at identical executable next-bar entries."),
    # Round 3 (declared 2026-10-04). Untouched data: Kite history Jan–Jul 2026,
    # never used by any study (scripts/acquire_kite_history.py). Development was
    # the seen Yahoo windows (docs/2026-10-04-momentum-penny-smarter-slice.md).
    "momentum-smart-t3": Study(
        strategy="momentum_intraday_15m_replay",
        snapshot=KITE / "2026-10-05-momentum-h1/_local/validated-kite.sqlite",
        base_config=lambda: {**_config_from("momentum-recent-diagnostic-report.json", entry_clock="NEXT_BAR_OPEN")(),
                             "index_ticker": "NIFTY 50"},
        sources=("python-engine/momentum_replay.py", "python-engine/momentum_selective.py",
                 "python-engine/momentum_exits.py", "python-engine/engine.py", "python-engine/momentum_shadow.py"),
        windows={"untouched": (("2026-01-01", "2026-07-31"),)},
        arms={"BASELINE": {"variants": ["MOM_BASE"], "exit_model": "LIVE_EXIT_LIFECYCLE"},
              "MOM_SELECTIVE": {"variants": ["MOM_SELECTIVE"], "exit_model": "LIVE_EXIT_LIFECYCLE"},
              "MOM_SELECTIVE_RUNNER": {"variants": ["MOM_SELECTIVE"], "exit_model": "RUNNER_EXIT"}},
        books={"paper_50k": {"bankroll": 50000.0, "momentum_pool": 50000.0}},
        decision_book="paper_50k", candidate="MOM_SELECTIVE", decision_window="untouched",
        drawdown_key="max_drawdown", drawdown_floor=1000.0, metrics="trades",
        hypothesis="Taking shipped Momentum signals only when NIFTY is up, the stock leads NIFTY by >=0.3% "
                   "and trades above yesterday's high beats the shipped Momentum book (shipped exits). "
                   "MOM_SELECTIVE_RUNNER (runner exit) is attribution: on development the runner exit lost "
                   "more than the shipped exits on shipped entries."),
    "penny-noise-t3": Study(
        strategy="penny_breakout_mis_lifecycle_1m",
        snapshot=KITE / "2026-10-05-penny-h1/_local/validated-kite.sqlite",
        base_config=_config_from("penny-mis-recent-diagnostic-gap-sensitivity-report.json"),
        sources=("python-engine/penny_lifecycle_replay.py", "python-engine/penny_engine_breakout.py",
                 "python-engine/penny_risk.py", "python-engine/penny_shadow.py", "python-engine/cost_schedules.py"),
        windows={"untouched": (("2026-01-01", "2026-07-31"),)},
        arms={name: {"candidate_policy": name, "stop_policy": "BAR_LOW" if name == "BASELINE" else "NOISE_FLOOR"}
              for name in ("BASELINE", "PEN_NOISE_STOP", "PEN_NOISE_STOP_BE")},
        books={"paper_100k": {"bankroll": 100000.0}, "owner_2000": {"bankroll": 2000.0}},
        decision_book="owner_2000",
        candidate="PEN_NOISE_STOP", decision_window="untouched",
        drawdown_key="max_drawdown", drawdown_floor=50.0, metrics="trades",
        hypothesis="Moving the shipped Penny stop out of one-minute noise (>=1.5% and >=Rs0.03 under entry, "
                   "same rupee risk) beats the shipped breakout-bar-low stop; _BE adds breakeven at +1R."),
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_dataset(folder: Path) -> dict:
    """Re-hash every file the F&O dataset manifest lists; any drift fails."""
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    for rel, digest in manifest["files_sha256"].items():
        if _sha(folder / rel) != digest:
            raise SystemExit(f"dataset file changed: {rel}")
    return {"manifest_sha256": _sha(folder / "manifest.json"), "quote_days": manifest["quote_days"],
            "unsealed_days": manifest.get("unsealed_days", [])}


def _bound(study: Study) -> dict:
    snapshot = _verify_dataset(study.snapshot) if study.runner == "fno_replay" else verify_snapshot(str(study.snapshot))
    bound = {"sources": {rel: _sha(ROOT / rel) for rel in (*study.sources, *COMMON_SOURCES)}, "snapshot": snapshot}
    if study.strategy == "penny_breakout_mis_lifecycle_1m":
        from penny_lifecycle_replay import settings_snapshot
        from penny_shadow import _execution_snapshot
        bound["penny_effective_settings"] = {book: settings_snapshot(book) for book in ("PENNY_PAPER", "PENNY")}
        bound["penny_execution_costs"] = _execution_snapshot("PREREGISTRATION")
        bound["sources"]["python-engine/penny_prices.py"] = _sha(ROOT / "python-engine/penny_prices.py")
        bound["sources"]["python-engine/penny_executor.py"] = _sha(ROOT / "python-engine/penny_executor.py")
    return bound


def _trade_metrics(reports: list[dict]) -> dict:
    """Realised-curve metrics for trade-list replays (Penny MIS, Momentum)."""
    trades = [t for r in reports for t in r["result"]["trades"]]
    closed = sorted((t for t in trades if t["status"] == "CLOSED"),
                    key=lambda t: (t.get("exit_fill_ts") or t.get("exit_bar_ts"), t["ticker"]))
    net = [t["net_pnl"] for t in closed]
    running = peak = drawdown = 0.0
    sessions: Counter = Counter()
    for trade in closed:
        running += trade["net_pnl"]
        peak, drawdown = max(peak, running), max(drawdown, peak - running)
        sessions[trade["trading_date"]] += trade["net_pnl"]
    best = max(net) if net else 0.0
    return {
        "entries": sum(t["status"] != "NO_FILL" for t in trades), "closed": len(closed),
        "unresolved": sum(t["status"] in ("UNRESOLVED", "OPEN") for t in trades),
        "net_pnl": round(sum(net), 4), "net_excluding_best_winner": round(sum(net) - max(best, 0.0), 4),
        "max_drawdown": round(drawdown, 4),
        "win_rate_pct": round(100 * sum(x > 0 for x in net) / len(net), 2) if net else None,
        "profit_factor": (round(sum(x for x in net if x > 0) / abs(sum(x for x in net if x < 0)), 4)
                          if any(x < 0 for x in net) else None),
        "sessions_with_trades": len(sessions), "positive_sessions": sum(v > 0 for v in sessions.values()),
        "exit_reasons": dict(sorted(Counter(str(t.get("exit_reason") or t["status"]) for t in trades).items())),
    }


def _portfolio_metrics(reports: list[dict]) -> dict:
    if len(reports) != 1:
        raise SystemExit("portfolio studies score one contiguous range per window")
    result = reports[0]["result"]
    return {**result["summary"], "admission_outcomes": result["admission_outcomes"]}


def _fno_metrics(reports: list[dict]) -> dict:
    if len(reports) != 1:
        raise SystemExit("F&O studies score one contiguous range per window")
    result = reports[0]["result"]
    return {**result["summary"], "funnel": result["funnel"], "notes": result["notes"],
            "parity_vs_live": {k: result["parity_vs_live"][k] for k in ("live_trades", "replayed_trades",
                                                                         "live_only", "replay_only")}}


def _execute(study: Study, frozen: dict, start: str, end: str, overrides: dict, target: Path) -> dict:
    """Score one (window range, book, arm) once and return its report."""
    if study.runner == "fno_replay":
        from fno_policy_replay import run_replay
        result = run_replay(study.snapshot, start=start, end=end, policy=overrides["policy"])
        _atomic_json_new(str(target), {"state": "SUCCEEDED", "result": result})
    else:
        run_backtest(SimpleNamespace(
            snapshot=str(study.snapshot), strategy=study.strategy, start=start, end=end,
            config=json.dumps({**frozen["config"], **overrides}),
            holdout_from=None, holdout_to=None, qualification_registry=None, qualification_id=None,
            out=str(target)))
    return json.loads(target.read_text())


def decide(study: Study, results: dict) -> dict:
    """The same four pre-declared checks for every study."""
    scope = results[study.decision_window][study.decision_book]
    cand, base = scope[study.candidate], scope["BASELINE"]
    dd = study.drawdown_key
    checks = {
        "net_pnl > 0": cand["net_pnl"] > 0,
        "net_excluding_best_winner > 0": cand["net_excluding_best_winner"] > 0,
        "net_pnl > BASELINE net_pnl": cand["net_pnl"] > base["net_pnl"],
        f"{dd} <= max(1.5 * BASELINE {dd}, {study.drawdown_floor})":
            cand[dd] <= max(1.5 * base[dd], study.drawdown_floor),
    }
    return {"checks": checks, "verdict": "PROMISING_CONTINUE_SHADOW" if all(checks.values())
            else "NOT_SUPPORTED_STAYS_OFF", "qualification": "NOT_ASSESSED"}


def freeze(name: str, out: Path) -> None:
    study = STUDIES[name]
    out.mkdir(parents=True, exist_ok=False)
    _atomic_json_new(str(out / "freeze.json"), {
        "schema": "preregistered_study_freeze_v1", "study": name, "strategy": study.strategy,
        "hypothesis": study.hypothesis, "bound": _bound(study), "config": study.base_config(),
        "arms": study.arms, "books": study.books, "windows": study.windows,
        "decision_rule": {"candidate": study.candidate, "window": study.decision_window, "book": study.decision_book,
                          "drawdown_key": study.drawdown_key, "drawdown_floor": study.drawdown_floor,
                          "if_promising": "continue broker-free shadow; NOT qualified; no live activation",
                          "otherwise": "hypothesis not supported; candidate stays OFF"},
        "can_place_orders": False, "qualification": "NOT_ASSESSED"})
    print("frozen:", out / "freeze.json")


def _execute_task(task: tuple) -> dict:
    """Process-pool entry point: one (window range, book, arm) score."""
    name, frozen, start, end, overrides, target = task
    return _execute(STUDIES[name], frozen, start, end, overrides, Path(target))


def run(name: str, out: Path, jobs: int = 1) -> None:
    study = STUDIES[name]
    frozen = json.loads((out / "freeze.json").read_text())
    if frozen["study"] != name or frozen["bound"] != _bound(study):
        raise SystemExit("bound inputs changed since freeze; refusing to score")
    local = out / "_local"
    local.mkdir(exist_ok=True)
    combine = {"trades": _trade_metrics, "portfolio": _portfolio_metrics, "fno": _fno_metrics}[study.metrics]
    tasks = {}
    for window, ranges in study.windows.items():
        for book, book_overrides in study.books.items():
            for arm, arm_overrides in study.arms.items():
                for start, end in ranges:
                    target = local / f"{window}-{book}-{arm.lower()}-{start}.json"
                    if target.exists():
                        raise SystemExit(f"{target} exists; a frozen window is scored once")
                    tasks[(window, book, arm, start)] = (name, frozen, start, end,
                                                         {**book_overrides, **arm_overrides}, str(target))
    # Every score is independent and writes its own report, so they may run in
    # parallel; results are combined in the declared order either way.
    if jobs > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            reports_by_task = dict(zip(tasks, pool.map(_execute_task, tasks.values())))
    else:
        reports_by_task = {key: _execute_task(task) for key, task in tasks.items()}
    if frozen["bound"] != _bound(study):
        raise SystemExit("bound inputs changed during scoring; reports invalid, refusing results/verdict")
    results: dict = {}
    for window, ranges in study.windows.items():
        for book in study.books:
            for arm in study.arms:
                reports = []
                for start, _ in ranges:
                    report = reports_by_task[(window, book, arm, start)]
                    if report.get("state") != "SUCCEEDED":
                        raise SystemExit(f"{window}-{book}-{arm}-{start}: {report.get('state')} "
                                         f"{report.get('reason') or report.get('error')}")
                    reports.append(report)
                metrics = combine(reports)
                results.setdefault(window, {}).setdefault(book, {})[arm] = metrics
                print(window, book, arm, json.dumps({k: metrics.get(k) for k in (
                    "closed", "net_pnl", "net_excluding_best_winner", study.drawdown_key, "win_rate_pct")}), flush=True)
    decision = decide(study, results)
    _atomic_json_new(str(out / "results.json"), {"schema": "preregistered_study_results_v1", "study": name,
                                                 "freeze_sha256": _sha(out / "freeze.json"),
                                                 "results": results, "decision": decision,
                                                 "bound_verified_after_scoring":True})
    print("decision:", json.dumps(decision))


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("action", choices=("list", "freeze", "run"))
    cli.add_argument("study", nargs="?", choices=sorted(STUDIES))
    cli.add_argument("--out", type=Path)
    cli.add_argument("--jobs", type=int, default=1, help="run: score independent arms in parallel processes")
    args = cli.parse_args()
    if args.action == "list":
        for name, study in STUDIES.items():
            print(f"{name:22} {study.strategy:36} candidate={study.candidate}  {study.hypothesis}")
        return
    if not args.study or not args.out:
        cli.error("freeze/run need STUDY and --out")
    if args.action == "freeze":
        freeze(args.study, args.out.resolve())
    else:
        run(args.study, args.out.resolve(), max(1, args.jobs))


if __name__ == "__main__":
    main()
