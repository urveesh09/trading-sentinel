"""[B0 2026-10-03] Honest catalogue of shipped strategies and their backtests.

Every shipped strategy appears once with the fidelity of the backtest that
exists for it today. ``validate_catalogue`` keeps this list and the Backtest
Lab registry in agreement, so an adapter cannot be added (or removed) without
the catalogue saying what it really replays.
"""
from __future__ import annotations

from typing import Iterable

STATUSES = ("LIFECYCLE", "EVALUATOR_ONLY", "PROXY_ONLY", "NOT_ADAPTED", "UNAVAILABLE",
            "EXCLUDED_BY_OWNER")
SCOPES = ("EVALUATOR", "LIFECYCLE", "FULL_PORTFOLIO", "PROXY", "UNAVAILABLE")

SHIPPED_STRATEGIES: tuple[dict, ...] = (
    {"strategy": "classic_penny_mis_breakout", "book": "PENNY_PAPER / PENNY", "product": "MIS",
     "live_gate": "PENNY_LIVE_TRADING (default False)",
     "adapters": ("penny_breakout_mis_lifecycle_1m", "penny_breakout_intraday_1m_replay"),
     "status": "LIFECYCLE", "next_step": "point-in-time universe/regime before FULL_PORTFOLIO"},
    {"strategy": "classic_penny_cnc_connors", "book": "PENNY_PAPER", "product": "CNC",
     "live_gate": "PENNY_LIVE_TRADING (default False); live rows have no exit management",
     "adapters": ("penny_cnc_connors_lifecycle_1d",),
     "status": "LIFECYCLE", "next_step": "real-data run once Production is up"},
    {"strategy": "penny_daily_proxy_research", "book": "research only", "product": "n/a",
     "live_gate": "never traded",
     "adapters": ("penny_breakout_daily_proxy", "penny_breakout_daily_proxy_walk_forward"),
     "status": "PROXY_ONLY", "next_step": "kept as research; not a shipped book"},
    {"strategy": "penny_edge_adaptive", "book": "EDGE_PAPER / EDGE", "product": "CNC",
     "live_gate": "PENNY_EDGE_DISABLE_LIVE (default True) + code hard block",
     "adapters": ("penny_edge_daily_evaluator",), "status": "EVALUATOR_ONLY",
     "next_step": "historical paper executor/exit/event evidence before LIFECYCLE"},
    {"strategy": "swing_regime", "book": "SYSTEM (manual EXEC)", "product": "CNC",
     "live_gate": "every EXEC tap is live",
     "adapters": ("swing_regime_daily", "swing_regime_daily_evaluator"), "status": "EVALUATOR_ONLY",
     "next_step": "historical scheduler/breadth, manual approval and portfolio lifecycle before FULL_PORTFOLIO"},
    {"strategy": "intraday_momentum", "book": "MOMENTUM (manual EXEC) / momentum paper",
     "product": "MIS", "live_gate": "every EXEC tap is live",
     "adapters": ("momentum_intraday_15m_replay",), "status": "EVALUATOR_ONLY",
     "next_step": "B6 report/holdout controls; historical manual admission before lifecycle claim"},
    {"strategy": "range_reversion", "book": "dispatcher (inspect in B4)", "product": "n/a",
     "live_gate": "research/shadow dispatcher; no order authority",
     "adapters": ("range_reversion_daily_evaluator",), "status": "EVALUATOR_ONLY",
     "next_step": "archived proposal/cutoff and shadow lifecycle evidence before a portfolio claim"},
    {"strategy": "fno_single_leg_momentum", "book": "FNO_PAPER / FNO_LIVE", "product": "MIS options",
     "live_gate": "FNO_LIVE_TRADING False, FNO_LIVE_BANKROLL 0",
     "adapters": ("fno_momentum_5m",), "status": "EXCLUDED_BY_OWNER",
     "next_step": "B5 excluded by owner; licensed option data required"},
    {"strategy": "fno_defined_risk", "book": "FNO_PAPER (paper only)", "product": "spreads",
     "live_gate": "no live path", "adapters": (), "status": "EXCLUDED_BY_OWNER",
     "next_step": "B5 excluded by owner"},
    {"strategy": "partner_advisory", "book": "advisory only", "product": "n/a",
     "live_gate": "can_place_orders False", "adapters": (), "status": "EXCLUDED_BY_OWNER",
     "next_step": "B5 excluded by owner; not a money book"},
)


def catalogue(registry=None) -> list[dict]:
    """Catalogue rows enriched with each adapter's declared scope and limitations."""
    if registry is None:
        from backtest_lab import STRATEGY_REGISTRY as registry
    rows = []
    for row in SHIPPED_STRATEGIES:
        adapters = []
        for adapter_id in row["adapters"]:
            meta = registry[adapter_id].metadata
            adapters.append({"strategy_id": adapter_id, "scope": meta.scope,
                             "timeframe": meta.timeframe, "limitations": list(meta.limitations)})
        rows.append({**row, "adapters": adapters})
    return rows


def validate_catalogue(registry=None) -> list[str]:
    """Problems that make the catalogue dishonest; empty when consistent."""
    if registry is None:
        from backtest_lab import STRATEGY_REGISTRY as registry
    problems = []
    named: list[str] = [a for row in SHIPPED_STRATEGIES for a in row["adapters"]]
    for adapter_id in named:
        if adapter_id not in registry:
            problems.append(f"catalogue names unknown adapter {adapter_id}")
    for adapter_id, adapter in registry.items():
        if adapter_id not in named:
            problems.append(f"registry adapter {adapter_id} is not catalogued")
        if adapter.metadata.scope not in SCOPES:
            problems.append(f"adapter {adapter_id} has undeclared scope {adapter.metadata.scope}")
    for row in SHIPPED_STRATEGIES:
        if row["status"] not in STATUSES:
            problems.append(f"{row['strategy']} has unknown status {row['status']}")
        scopes = {registry[a].metadata.scope for a in row["adapters"] if a in registry}
        if row["status"] == "LIFECYCLE" and "LIFECYCLE" not in scopes:
            problems.append(f"{row['strategy']} claims LIFECYCLE without a LIFECYCLE adapter")
    if len(set(named)) != len(named):
        problems.append("an adapter is catalogued twice")
    return problems


def family_prefixes(strategy_id: str) -> Iterable[str]:
    """Settings prefixes that define a strategy family's policy (for manifests)."""
    if strategy_id.startswith("penny"):
        return ("PENNY_",)
    if strategy_id.startswith("momentum"):
        return ("MOMENTUM_",)
    if strategy_id.startswith("fno"):
        return ("FNO_",)
    return ("RISK_", "STOP_", "TARGET", "REGIME_", "CHANDELIER_", "MAX_", "RS_", "HARD_CAP_")
