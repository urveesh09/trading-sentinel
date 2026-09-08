"""Common-cash SHADOW basket replay and chronological policy research.

Neither function consumes a broker, changes a scheduler, nor selects a live
strategy.  They turn the existing proposal/simulator evidence into a retained
portfolio and walk-forward comparison with explicit insufficient outcomes.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
import aiosqlite

from proactive_intelligence import ShadowProposal, size_shadow_allocations, simulate_shadow_trade
from walk_forward import generate_folds, walk_forward


def _at(proposal: ShadowProposal) -> datetime:
    value = proposal.signal_at or proposal.data_cutoff or proposal.valid_until
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("proposal timing must be timezone-aware")
    return value


def _outcome(proposal, bars, cash, allocation=None):
    return simulate_shadow_trade(proposal, bars, cash=cash, allocation=allocation)


def replay_common_cash_basket(
    proposals: list[ShadowProposal], future_bars: dict[str, list[dict]], *, capital: float,
    method: str, fee_rate: float = .001, slippage_bps: float = 5,
) -> dict:
    """Replay one shared cash book, releasing cash only at observed closes.

    ``RISK_BUDGET_V1`` calls the production SHADOW allocator. ``FIXED_EQUAL_V1``
    is a deliberately simple equal-cash baseline; it is not a challenger that
    can silently reuse capital across same-clock opportunities.
    """
    if method not in {"RISK_BUDGET_V1", "FIXED_EQUAL_V1"} or not math.isfinite(capital) or capital <= 0:
        raise ValueError("invalid portfolio replay assumptions")
    groups = defaultdict(list)
    for proposal in proposals:
        groups[_at(proposal)].append(proposal)
    cash, peak, drawdown, realized = float(capital), float(capital), 0.0, 0.0
    active, decisions = [], []
    for clock in sorted(groups):
        still_active = []
        for release_at, reserve, net in active:
            if release_at <= clock:
                cash += reserve + net; realized += net; peak = max(peak, cash); drawdown = max(drawdown, peak-cash)
            else: still_active.append((release_at, reserve, net))
        active = still_active
        candidates = groups[clock]
        if method == "RISK_BUDGET_V1":
            allocations, reasons = size_shadow_allocations(candidates, capital=cash, fee_rate=fee_rate, slippage_bps=slippage_bps)
            by_id = {item.opportunity_id: item for item in allocations}
        else:
            # Each same-clock candidate receives one equal slice, so the
            # baseline cannot spend the complete cash book repeatedly.
            slice_cash = cash / len(candidates)
            allocations, reasons, by_id = [], {}, {}
            for proposal in sorted(candidates, key=lambda item: (item.policy_id, item.instrument, item.opportunity_id)):
                result = _outcome(proposal, future_bars.get(proposal.instrument, []), slice_cash)
                if result.status in {"CLOSED", "OPEN"} and result.entry_price is not None:
                    reserve = result.entry_price * result.quantity * (1 + fee_rate)
                    by_id[proposal.opportunity_id] = None; reasons[proposal.opportunity_id] = "SELECTED_FIXED_EQUAL"
                else: reasons[proposal.opportunity_id] = result.reason
        for proposal in candidates:
            allocation = by_id.get(proposal.opportunity_id, "absent")
            if allocation == "absent":
                decisions.append({"opportunity_id": proposal.opportunity_id, "policy_id": proposal.policy_id, "state": "NOT_SELECTED", "reason": reasons.get(proposal.opportunity_id)})
                continue
            budget = cash if allocation is not None else cash / len(candidates)
            result = _outcome(proposal, future_bars.get(proposal.instrument, []), budget, allocation if allocation is not None else None)
            if result.status not in {"CLOSED", "OPEN"} or result.entry_price is None:
                decisions.append({"opportunity_id": proposal.opportunity_id, "policy_id": proposal.policy_id, "state": result.status, "reason": result.reason}); continue
            reserve = (allocation.reserved_capital if allocation is not None else result.entry_price * result.quantity * (1 + fee_rate))
            cash -= reserve
            if result.status == "CLOSED" and result.last_bar_at:
                active.append((result.last_bar_at, reserve, float(result.net_pnl or 0)))
            decisions.append({"opportunity_id": proposal.opportunity_id, "policy_id": proposal.policy_id, "state": result.status, "reason": result.reason, "reserved": round(reserve, 4), "net_pnl": result.net_pnl})
    locked = sum(item[1] for item in active)
    return {"method": method, "initial_capital": capital, "free_cash": round(cash, 4), "locked_capital": round(locked, 4), "realized_net_pnl": round(realized, 4), "max_drawdown": round(drawdown, 4), "decisions": decisions, "research_only": True, "can_place_orders": False, "authorization_effect": "NONE"}


def chronological_policy_research(proposals: list[ShadowProposal], future_bars: dict[str, list[dict]], *, train_days: int, test_days: int) -> dict:
    """Choose policies on prior dates only and retain every fold outcome."""
    if not proposals: return {"verdict": "insufficient_data", "folds": [], "reason": "NO_PROPOSALS"}
    dates = sorted({_at(item).date().isoformat() for item in proposals})
    if len(dates) < 2:
        return {"verdict": "insufficient_data", "folds": [], "reason": "INSUFFICIENT_CHRONOLOGICAL_DATES", "research_only": True, "can_place_orders": False, "authorization_effect": "NONE", "policy_count": len({item.policy_id for item in proposals}), "proposal_count": len(proposals)}
    folds = generate_folds(dates[0], dates[-1], train_days, test_days)
    policies = sorted({item.policy_id for item in proposals})
    def score(policy, start, end):
        values=[]
        for item in proposals:
            if item.policy_id != policy or not start <= _at(item).date().isoformat() <= end: continue
            result = _outcome(item, future_bars.get(item.instrument, []), 10_000)
            if result.status == "CLOSED" and result.net_pnl is not None: values.append(float(result.net_pnl))
        return sum(values) / len(values) if values else None
    result = walk_forward(policies, folds, score)
    result.update({"research_only": True, "can_place_orders": False, "authorization_effect": "NONE", "policy_count": len(policies), "proposal_count": len(proposals)})
    return result


async def persist_portfolio_and_fold_research(db_path: str, *, research_run_id: str, proposals: list[ShadowProposal], future_bars: dict[str, list[dict]], capital: float) -> dict:
    """Freeze W3/W4 results alongside the existing immutable trial run."""
    payload = {"proposals": [(p.opportunity_id, p.policy_id, _at(p).isoformat()) for p in proposals], "future_bars": future_bars, "capital": capital}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
    result = {"risk_budget": replay_common_cash_basket(proposals, future_bars, capital=capital, method="RISK_BUDGET_V1"), "fixed_equal": replay_common_cash_basket(proposals, future_bars, capital=capital, method="FIXED_EQUAL_V1"), "chronological_folds": chronological_policy_research(proposals, future_bars, train_days=20, test_days=5)}
    async with aiosqlite.connect(db_path) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS proactive_portfolio_research_runs (research_run_id TEXT PRIMARY KEY, input_sha256 TEXT NOT NULL, result_json TEXT NOT NULL, created_at TEXT NOT NULL)")
        row=await (await db.execute("SELECT input_sha256,result_json FROM proactive_portfolio_research_runs WHERE research_run_id=?", (research_run_id,))).fetchone()
        if row and row[0] != digest: raise ValueError("portfolio research manifest conflicts with existing evidence")
        if not row:
            await db.execute("INSERT INTO proactive_portfolio_research_runs VALUES (?,?,?,?)", (research_run_id,digest,json.dumps(result,sort_keys=True),datetime.now(timezone.utc).isoformat())); await db.commit()
        elif row: result=json.loads(row[1])
    return result


async def portfolio_research_report(db_path: str, research_run_id: str | None = None) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS proactive_portfolio_research_runs (research_run_id TEXT PRIMARY KEY, input_sha256 TEXT NOT NULL, result_json TEXT NOT NULL, created_at TEXT NOT NULL)")
        query="SELECT research_run_id,result_json FROM proactive_portfolio_research_runs" + (" WHERE research_run_id=?" if research_run_id else "") + " ORDER BY research_run_id"
        rows=await (await db.execute(query, (research_run_id,) if research_run_id else ())).fetchall()
    return [{"research_run_id": row[0], **json.loads(row[1])} for row in rows]
