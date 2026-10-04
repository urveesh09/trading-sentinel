"""Pre-registered Penny trader comparison on archived Yahoo minute data.

python scripts/run_penny_trader_oos.py freeze --out docs/research/yahoo/2026-10-04-penny-trader-oos
python scripts/run_penny_trader_oos.py run    --out docs/research/yahoo/2026-10-04-penny-trader-oos

`freeze` binds source hashes, the validated snapshot, the windows, every policy
and the decision rule before any untouched window is scored. `run` refuses to
start if any bound input changed, scores each policy once per window and
writes receipts. No network, broker, order or Production access.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-engine"))
from backtest_cli import _atomic_json_new, run as run_backtest, verify_snapshot  # noqa: E402

SNAPSHOT = ROOT / "docs/research/yahoo/2026-10-04-penny-trader-window/_local/validated-yahoo.sqlite"
RECEIPT_CONFIG = ROOT / ("docs/research/yahoo/2026-10-04-q3-review-final/_local/"
                         "penny-mis-recent-diagnostic-gap-sensitivity-report.json")
SOURCES = ("python-engine/adaptive_penny_policy.py", "python-engine/penny_lifecycle_replay.py",
           "python-engine/penny_engine_breakout.py", "python-engine/penny_risk.py",
           "python-engine/penny_shadow.py", "python-engine/cost_schedules.py", "python-engine/config.py",
           "scripts/run_penny_trader_oos.py")
POLICIES = ("BASELINE", "PEN_TRADER_V1", "PEN_TRADER_V1_THESIS", "PEN_BASE_THESIS", "PEN_TRADER_V2")
WINDOWS = {
    # Sep 24-30 shaped round 2; it is development data and never qualification.
    "development": [("2026-09-24", "2026-09-30")],
    # Untouched by any candidate design: Sep 7-23 and Oct 1 (Oct 2 holiday).
    "untouched": [("2026-09-07", "2026-09-23"), ("2026-10-01", "2026-10-01")],
}
DECISION_RULE = {
    "candidate": "PEN_TRADER_V2",
    "window": "untouched",
    "promising_if_all": [
        "net_pnl > 0",
        "net_excluding_best_winner > 0",
        "net_pnl > BASELINE net_pnl",
        "max_drawdown <= max(1.5 * BASELINE max_drawdown, 50.0)",
    ],
    "if_promising": "continue broker-free shadow/forward collection; NOT qualified, no live activation",
    "otherwise": "hypothesis not supported; candidate stays OFF and the failure is recorded",
    "round_1_and_base_thesis": "reported for attribution; no promotion decision",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound_inputs() -> dict:
    return {
        "sources": {rel: _sha(ROOT / rel) for rel in SOURCES},
        "snapshot": verify_snapshot(str(SNAPSHOT)),
        "receipt_config_sha256": _sha(RECEIPT_CONFIG),
    }


def _config() -> dict:
    return json.loads(RECEIPT_CONFIG.read_text())["request"]["config"]


def freeze(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=False)
    _atomic_json_new(str(out / "freeze.json"), {
        "schema": "penny_trader_oos_freeze_v1", "source": "ARCHIVED_YAHOO_ONLY",
        "bound": _bound_inputs(), "config": _config(), "policies": list(POLICIES),
        "windows": WINDOWS, "decision_rule": DECISION_RULE,
        "can_place_orders": False, "qualification": "NOT_ASSESSED",
    })
    print("frozen:", out / "freeze.json")


def _combine(reports: list[dict]) -> dict:
    closed = [t for r in reports for t in r["result"]["trades"] if t["status"] == "CLOSED"]
    trades = [t for r in reports for t in r["result"]["trades"]]
    net = [t["net_pnl"] for t in closed]
    running = peak = drawdown = 0.0
    for trade in sorted(closed, key=lambda t: (t["exit_fill_ts"], t["ticker"])):
        running += trade["net_pnl"]
        peak = max(peak, running)
        drawdown = max(drawdown, peak - running)
    per_day = Counter()
    for trade in closed:
        per_day[trade["trading_date"]] += trade["net_pnl"]
    best = max(net) if net else 0.0
    return {
        "entries": len(trades), "closed": len(closed),
        "unresolved": sum(t["status"] == "UNRESOLVED" for t in trades),
        "net_pnl": round(sum(net), 4), "gross_pnl": round(sum(t["gross_pnl"] for t in closed), 4),
        "costs": round(sum(t["costs"] for t in closed), 4),
        "win_rate_pct": round(100 * sum(x > 0 for x in net) / len(net), 2) if net else None,
        "profit_factor": (round(sum(x for x in net if x > 0) / abs(sum(x for x in net if x < 0)), 4)
                          if any(x < 0 for x in net) else None),
        "max_drawdown": round(drawdown, 4),
        "net_excluding_best_winner": round(sum(net) - best, 4) if best > 0 else round(sum(net), 4),
        "adverse_fill_bound_net": round(sum(t["adverse_fill_bound_net"] for t in closed), 4),
        "sessions_with_trades": len(per_day), "positive_sessions": sum(v > 0 for v in per_day.values()),
        "per_day": {day: round(value, 4) for day, value in sorted(per_day.items())},
        "exit_reasons": dict(sorted(Counter(t.get("exit_reason") for t in trades).items())),
        "entry_kinds": dict(sorted(Counter(str(t.get("entry_kind")) for t in trades).items())),
        "baseline_status": dict(sorted(Counter(str(t.get("baseline_status")) for t in trades).items())),
    }


def _decide(results: dict) -> dict:
    window = DECISION_RULE["window"]
    cand, base = results[window][DECISION_RULE["candidate"]], results[window]["BASELINE"]
    checks = {
        "net_pnl > 0": cand["net_pnl"] > 0,
        "net_excluding_best_winner > 0": cand["net_excluding_best_winner"] > 0,
        "net_pnl > BASELINE net_pnl": cand["net_pnl"] > base["net_pnl"],
        "max_drawdown <= max(1.5 * BASELINE max_drawdown, 50.0)":
            cand["max_drawdown"] <= max(1.5 * base["max_drawdown"], 50.0),
    }
    verdict = "PROMISING_CONTINUE_SHADOW" if all(checks.values()) else "NOT_SUPPORTED_STAYS_OFF"
    return {"checks": checks, "verdict": verdict, "qualification": "NOT_ASSESSED"}


def run(out: Path) -> None:
    frozen = json.loads((out / "freeze.json").read_text())
    if frozen["bound"] != _bound_inputs():
        raise SystemExit("bound inputs changed since freeze; refusing to score")
    local = out / "_local"
    local.mkdir(exist_ok=True)
    results: dict = {}
    for window, ranges in WINDOWS.items():
        results[window] = {}
        for policy in POLICIES:
            reports = []
            for start, end in ranges:
                target = local / f"{window}-{policy.lower()}-{start}.json"
                if target.exists():
                    raise SystemExit(f"{target} exists; a frozen window is scored once")
                run_backtest(SimpleNamespace(
                    snapshot=str(SNAPSHOT), strategy="penny_breakout_mis_lifecycle_1m", start=start, end=end,
                    config=json.dumps({**frozen["config"], "candidate_policy": policy}),
                    holdout_from=None, holdout_to=None, qualification_registry=None, qualification_id=None,
                    out=str(target)))
                reports.append(json.loads(target.read_text()))
            results[window][policy] = _combine(reports)
            print(window, policy, json.dumps({k: results[window][policy][k] for k in (
                "closed", "net_pnl", "net_excluding_best_winner", "max_drawdown", "win_rate_pct")}), flush=True)
    decision = _decide(results)
    _atomic_json_new(str(out / "results.json"), {
        "schema": "penny_trader_oos_results_v1", "freeze_sha256": _sha(out / "freeze.json"),
        "results": results, "decision": decision, "can_place_orders": False,
    })
    print("decision:", json.dumps(decision))


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("freeze", "run"))
    cli.add_argument("--out", type=Path, required=True)
    args = cli.parse_args()
    (freeze if args.action == "freeze" else run)(args.out.resolve())


if __name__ == "__main__":
    main()
