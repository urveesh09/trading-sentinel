"""Pure, conservative standard metrics for archived backtest reports."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import hashlib
import math
import random
from statistics import mean


def validate_holdout(start: str, end: str, holdout_from: str | None, holdout_to: str | None) -> dict | None:
    if bool(holdout_from) != bool(holdout_to):
        raise ValueError("holdout requires both --holdout-from and --holdout-to")
    if not holdout_from:
        return None
    dev_start, dev_end = date.fromisoformat(start), date.fromisoformat(end)
    held_start, held_end = date.fromisoformat(holdout_from), date.fromisoformat(holdout_to)
    if held_start > held_end:
        raise ValueError("holdout start must be on or before holdout end")
    if held_start <= dev_end:
        raise ValueError("holdout must start strictly after the development window")
    return {"development_window": [dev_start.isoformat(), dev_end.isoformat()],
            "holdout_window": [held_start.isoformat(), held_end.isoformat()],
            "status": "DECLARED_UNVERIFIED",
            "untouched_verified": False,
            "reason": "Non-overlapping dates only; no prospective policy freeze or prior-use audit is archived."}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def report_holdout(holdout: dict | None) -> dict | None:
    """Clarify old date declarations without rewriting the archived report."""
    if isinstance(holdout, dict) and holdout.get("status") == "DECLARED_UNTOUCHED":
        return {**holdout, "archived_status": holdout["status"],
                "status": "DECLARED_UNVERIFIED", "untouched_verified": False,
                "reason": "Legacy date declaration; no prospective policy freeze or prior-use audit is archived."}
    return holdout


def _bootstrap(values: list[float], fingerprint: str) -> dict | None:
    if len(values) < 2:
        return None
    seed = int(hashlib.sha256((fingerprint + "|bootstrap-v1").encode()).hexdigest()[:16], 16)
    rng, n = random.Random(seed), len(values)
    samples = sorted(sum(rng.choice(values) for _ in range(n)) / n for _ in range(2000))
    return {"method": "iid_trade_bootstrap_v1", "replicates": 2000, "seed_sha256": hashlib.sha256(str(seed).encode()).hexdigest(),
            "mean_net_pnl": round(mean(values), 6), "ci_95": [round(samples[49], 6), round(samples[1949], 6)],
            "warning": "Trade-level IID uncertainty ignores dependence, overlap and selection; it is not a profitability verdict."}


def standard_metrics(report: dict) -> dict:
    """Return only metrics evidenced by the archived result; unknown remains null."""
    result = report.get("result") if isinstance(report.get("result"), dict) else {}
    has_trade_evidence = isinstance(result.get("trades"), list)
    raw = result.get("trades") if has_trade_evidence else []
    trades = [t for t in raw if isinstance(t, dict) and t.get("status") == "CLOSED"]
    net = [float(t["net_pnl"]) for t in trades if _number(t.get("net_pnl"))]
    gross = [float(t["gross_pnl"]) for t in trades if _number(t.get("gross_pnl"))]
    costs = [float(t["costs"]) for t in trades if _number(t.get("costs"))]
    holding = [float(t["holding_minutes"]) for t in trades if _number(t.get("holding_minutes"))]
    mfe = [float(t["mfe_r"]) for t in trades if _number(t.get("mfe_r"))]
    mae = [float(t["mae_r"]) for t in trades if _number(t.get("mae_r"))]
    turnover = []
    for t in trades:
        quantity = t.get("quantity", t.get("shares"))
        entry = t.get("entry_fill", t.get("entry_price"))
        exit_ = t.get("exit_fill", t.get("exit_price"))
        if all(_number(v) for v in (quantity, entry, exit_)):
            turnover.append(float(quantity) * (float(entry) + float(exit_)))
    by_month = defaultdict(float)
    monthly_count = 0
    for t in trades:
        stamp = str(t.get("exit_bar_ts") or t.get("exit_date") or t.get("trading_date") or "")
        try:
            month = date.fromisoformat(stamp[:10]).isoformat()[:7]
        except ValueError:
            continue
        if _number(t.get("net_pnl")):
            by_month[month] += float(t["net_pnl"])
            monthly_count += 1
    complete = lambda values: bool(trades) and len(values) == len(trades)
    best_excluded = sum(net) - max(0.0, max(net)) if complete(net) else None
    coverage = {key: {"present": count, "closed_trades": len(trades),
                      "complete": bool(trades) and count == len(trades)}
                for key, count in (("net_pnl", len(net)), ("gross_pnl", len(gross)),
                                   ("costs", len(costs)), ("holding_minutes", len(holding)),
                                   ("mfe_r", len(mfe)), ("mae_r", len(mae)),
                                   ("turnover", len(turnover)), ("monthly_net_pnl", monthly_count))}
    equity = result.get("equity") if isinstance(result.get("equity"), list) else []
    valid_clock = bool(equity) and all(isinstance(x, dict) and x.get("timestamp") and _number(x.get("equity")) for x in equity)
    return {
        "closed_trades": len(trades) if has_trade_evidence else None,
        "trade_evidence": "ARCHIVED" if has_trade_evidence else "ABSENT",
        "field_coverage": coverage,
        "gross_pnl": round(sum(gross), 6) if len(gross) == len(trades) and trades else None,
        "net_pnl": round(sum(net), 6) if len(net) == len(trades) and trades else None,
        "fees_and_costs": round(sum(costs), 6) if len(costs) == len(trades) and trades else None,
        "slippage": "embedded_or_not_separately_evidenced", "turnover": round(sum(turnover), 6) if len(turnover) == len(trades) and trades else None,
        "exposure_minutes": round(sum(holding), 6) if complete(holding) else None,
        "win_loss": {"wins": sum(v > 0 for v in net), "losses": sum(v < 0 for v in net), "breakeven": sum(v == 0 for v in net)} if complete(net) else None,
        "holding_minutes": {"mean": round(mean(holding), 6), "max": max(holding)} if complete(holding) else None,
        "mfe_r_mean": round(mean(mfe), 6) if complete(mfe) else None, "mae_r_mean": round(mean(mae), 6) if complete(mae) else None,
        "monthly_net_pnl": dict(sorted((k, round(v, 6)) for k, v in by_month.items())) if trades and monthly_count == len(trades) else None,
        "net_excluding_best_winner": round(best_excluded, 6) if best_excluded is not None else None,
        "uncertainty": _bootstrap(net, str(report.get("dataset_fingerprint") or report.get("snapshot", {}).get("rows_sha256") or "unknown")) if complete(net) else None,
        "risk_adjusted": None, "risk_adjusted_reason": "valid marked equity clock with an initial capital base is not archived" if valid_clock else "no valid marked equity clock",
    }
