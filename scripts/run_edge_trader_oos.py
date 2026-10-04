"""Pre-registered EDGE own-cash portfolio comparison on archived Yahoo daily data.

python scripts/run_edge_trader_oos.py freeze --out docs/research/yahoo/2026-10-04-edge-trader-oos
python scripts/run_edge_trader_oos.py run    --out docs/research/yahoo/2026-10-04-edge-trader-oos

Same discipline as the Penny script: bind sources, snapshot, windows, policies
and the decision rule first; score each window once. No network or broker.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-engine"))
from backtest_cli import _atomic_json_new, run as run_backtest, verify_snapshot  # noqa: E402

SNAPSHOT = ROOT / "docs/research/yahoo/2026-10-04-q3-review-baseline/_local/validated-yahoo.sqlite"
RECEIPT = ROOT / "docs/research/yahoo/2026-10-04-review-candidates/_local/edge-next-open-proxy-report.json"
SOURCES = ("python-engine/edge_portfolio_replay.py", "python-engine/penny_edge_live.py",
           "python-engine/penny_edge_engine.py", "python-engine/penny_risk.py", "python-engine/config.py",
           "scripts/run_edge_trader_oos.py")
POLICIES = ("BASELINE", "EDGE_TRADER_V1")
BANKROLLS = {"paper_100k": 100000.0, "owner_3000": 3000.0}
WINDOWS = {
    "development": ("2026-07-01", "2026-09-30"),   # seen by the review; not qualification
    "untouched": ("2026-01-01", "2026-06-30"),     # no EDGE candidate was designed on it
}
DECISION_RULE = {
    "candidate": "EDGE_TRADER_V1", "window": "untouched", "bankroll": "paper_100k",
    "promising_if_all": [
        "net_pnl > 0",
        "net_excluding_best_winner > 0",
        "net_pnl > BASELINE net_pnl",
        "max_marked_drawdown_pct <= max(1.5 * BASELINE max_marked_drawdown_pct, 5.0)",
    ],
    "if_promising": "continue broker-free shadow; NOT qualified; no EDGE live recovery bypass",
    "otherwise": "hypothesis not supported; candidate stays OFF",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound() -> dict:
    return {"sources": {rel: _sha(ROOT / rel) for rel in SOURCES}, "snapshot": verify_snapshot(str(SNAPSHOT)),
            "receipt_sha256": _sha(RECEIPT)}


def freeze(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=False)
    config = json.loads(RECEIPT.read_text())["request"]["config"]
    _atomic_json_new(str(out / "freeze.json"), {
        "schema": "edge_trader_oos_freeze_v1", "source": "ARCHIVED_YAHOO_ONLY", "bound": _bound(),
        "config": config, "policies": list(POLICIES), "bankrolls": BANKROLLS, "windows": WINDOWS,
        "decision_rule": DECISION_RULE, "can_place_orders": False, "qualification": "NOT_ASSESSED"})
    print("frozen:", out / "freeze.json")


def run(out: Path) -> None:
    frozen = json.loads((out / "freeze.json").read_text())
    if frozen["bound"] != _bound():
        raise SystemExit("bound inputs changed since freeze; refusing to score")
    local = out / "_local"
    local.mkdir(exist_ok=True)
    results: dict = {}
    for window, (start, end) in WINDOWS.items():
        for book, bankroll in BANKROLLS.items():
            for policy in POLICIES:
                target = local / f"{window}-{book}-{policy.lower()}.json"
                if target.exists():
                    raise SystemExit(f"{target} exists; a frozen window is scored once")
                run_backtest(SimpleNamespace(
                    snapshot=str(SNAPSHOT), strategy="penny_edge_portfolio_replay", start=start, end=end,
                    config=json.dumps({**frozen["config"], "bankroll": bankroll, "policy": policy}),
                    holdout_from=None, holdout_to=None, qualification_registry=None, qualification_id=None,
                    out=str(target)))
                report = json.loads(target.read_text())
                if report.get("state") != "SUCCEEDED":
                    raise SystemExit(f"{target.name}: {report.get('state')} {report.get('error')}")
                summary = report["result"]["summary"]
                results.setdefault(window, {}).setdefault(book, {})[policy] = {
                    **summary, "admission_outcomes": report["result"]["admission_outcomes"]}
                print(window, book, policy, json.dumps({k: summary[k] for k in (
                    "closed", "net_pnl", "net_excluding_best_winner", "max_marked_drawdown_pct",
                    "win_rate_pct", "marked_return_pct")}), flush=True)
    rule = DECISION_RULE
    cand = results[rule["window"]][rule["bankroll"]][rule["candidate"]]
    base = results[rule["window"]][rule["bankroll"]]["BASELINE"]
    checks = {
        "net_pnl > 0": cand["net_pnl"] > 0,
        "net_excluding_best_winner > 0": cand["net_excluding_best_winner"] > 0,
        "net_pnl > BASELINE net_pnl": cand["net_pnl"] > base["net_pnl"],
        "max_marked_drawdown_pct <= max(1.5 * BASELINE max_marked_drawdown_pct, 5.0)":
            cand["max_marked_drawdown_pct"] <= max(1.5 * base["max_marked_drawdown_pct"], 5.0),
    }
    decision = {"checks": checks, "verdict": "PROMISING_CONTINUE_SHADOW" if all(checks.values())
                else "NOT_SUPPORTED_STAYS_OFF", "qualification": "NOT_ASSESSED"}
    _atomic_json_new(str(out / "results.json"), {"schema": "edge_trader_oos_results_v1",
                                                 "freeze_sha256": _sha(out / "freeze.json"),
                                                 "results": results, "decision": decision})
    print("decision:", json.dumps(decision))


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("freeze", "run"))
    cli.add_argument("--out", type=Path, required=True)
    args = cli.parse_args()
    (freeze if args.action == "freeze" else run)(args.out.resolve())


if __name__ == "__main__":
    main()
