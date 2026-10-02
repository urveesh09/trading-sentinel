"""Shared summary arithmetic for the inert paired exit experiments (S6).

Pure functions over already-settled result rows; used by the equity
(``momentum_exit_experiment``) and single-leg F&O (``fno_exit_experiment``)
studies.  No I/O and no runtime caller.
"""
from __future__ import annotations

import statistics
from typing import Any, Sequence


def policy_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    closed = [row for row in rows if row.get("status") == "CLOSED"]
    if not closed:
        return {"complete": 0, "unresolved": len(rows)}
    return {
        "complete": len(closed),
        "unresolved": len(rows) - len(closed),
        "net_pnl": round(sum(float(row["net_pnl"]) for row in closed), 6),
        "net_pnl_cost_stressed": {
            key: round(sum(float(row["net_pnl_cost_stressed"][key]) for row in closed), 6)
            for key in closed[0]["net_pnl_cost_stressed"]
        },
        "mean_r": round(statistics.fmean(float(row["r_multiple"]) for row in closed), 8),
        "worst_r": round(min(float(row["r_multiple"]) for row in closed), 8),
        "mean_giveback_r": round(statistics.fmean(float(row["giveback_r"]) for row in closed), 8),
        "mean_minutes_exposed": round(statistics.fmean(float(row["minutes_exposed"]) for row in closed), 4),
    }


def paired_deltas(pairs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    complete = [pair for pair in pairs
                if pair["baseline"].get("status") == "CLOSED" and pair["candidate"].get("status") == "CLOSED"]
    deltas = [float(pair["candidate"]["net_pnl"]) - float(pair["baseline"]["net_pnl"]) for pair in complete]
    if not deltas:
        return {"complete_pairs": 0}
    stressed = {
        key: round(sum(float(pair["candidate"]["net_pnl_cost_stressed"][key])
                       - float(pair["baseline"]["net_pnl_cost_stressed"][key]) for pair in complete), 6)
        for key in complete[0]["candidate"]["net_pnl_cost_stressed"]
    }
    ordered = sorted(deltas)
    return {
        "complete_pairs": len(deltas),
        "candidate_better": sum(1 for delta in deltas if delta > 0),
        "candidate_worse": sum(1 for delta in deltas if delta < 0),
        "ties": sum(1 for delta in deltas if delta == 0),
        "sum_net_delta": round(sum(deltas), 6),
        "mean_net_delta": round(statistics.fmean(deltas), 6),
        "median_net_delta": round(statistics.median(deltas), 6),
        "worst_net_delta": round(ordered[0], 6),
        "sum_net_delta_excluding_best": round(sum(ordered[:-1]), 6),
        "sum_net_delta_cost_stressed": stressed,
    }


__all__ = ["paired_deltas", "policy_summary"]
