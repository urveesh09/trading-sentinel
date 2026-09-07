"""Versioned entry/execution economics for SHADOW research only."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import aiosqlite

from proactive_intelligence import ShadowProposal, _SHADOW_ENTRY_PROFILES, _SHADOW_EXIT_PROFILES, simulate_shadow_research_trial

_SCENARIOS = {
    "NORMAL_V1": {"fee_rate": .0010, "slippage_bps": 5, "cost_model_version": "EQUITY_CASH_ESTIMATE_V1"},
    "STRESSED_V1": {"fee_rate": .0025, "slippage_bps": 20, "cost_model_version": "EQUITY_CASH_ESTIMATE_V1"},
}


async def persist_execution_sensitivity(db_path: str, *, research_run_id: str, proposals: list[ShadowProposal], future_bars: dict[str, list[dict]], cash: float) -> list[dict]:
    """Freeze normal/stressed entry results; no-fill remains an observation."""
    payload={"proposals":[(p.opportunity_id,p.policy_id,p.instrument,p.entry,p.stop,p.target) for p in proposals],"future_bars":future_bars,"cash":cash,"scenarios":_SCENARIOS}
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,default=str,separators=(",",":")).encode()).hexdigest()
    async with aiosqlite.connect(db_path) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS proactive_execution_research_runs (research_run_id TEXT PRIMARY KEY,input_sha256 TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL)")
        row=await (await db.execute("SELECT input_sha256,result_json FROM proactive_execution_research_runs WHERE research_run_id=?",(research_run_id,))).fetchone()
        if row:
            if row[0]!=digest: raise ValueError("execution research manifest conflicts with existing evidence")
            return json.loads(row[1])
    groups=[]
    for scenario, assumptions in _SCENARIOS.items():
        for entry_profile in sorted(_SHADOW_ENTRY_PROFILES):
            values=[]; reasons={}; fills=0
            for proposal in proposals:
                # One exit profile fixes the exit mechanics while this experiment
                # isolates entry timing and execution costs.
                result=simulate_shadow_research_trial(proposal,future_bars.get(proposal.instrument,[]),cash=cash,entry_profile_id=entry_profile,exit_profile_id="STOP_TARGET_TIME_V1",fee_rate=assumptions["fee_rate"],slippage_bps=assumptions["slippage_bps"])
                reasons[result.reason]=reasons.get(result.reason,0)+1
                if result.status=="CLOSED" and result.net_pnl is not None: values.append(float(result.net_pnl)); fills+=1
                elif result.status=="OPEN": fills+=1
            groups.append({"scenario":scenario,"entry_profile_id":entry_profile,"cost_model_version":assumptions["cost_model_version"],"fee_rate":assumptions["fee_rate"],"slippage_bps":assumptions["slippage_bps"],"opportunities":len(proposals),"closed_outcomes":len(values),"filled_or_open":fills,"no_fill":sum(count for reason,count in reasons.items() if "NO_" in reason or "LIMIT" in reason or "GAP_" in reason),"net_pnl":round(sum(values),4) if values else None,"net_expectancy":round(sum(values)/len(values),4) if values else None,"reasons":reasons})
    async with aiosqlite.connect(db_path) as db:
        await db.execute("INSERT INTO proactive_execution_research_runs VALUES (?,?,?,?)",(research_run_id,digest,json.dumps(groups,sort_keys=True),datetime.now(timezone.utc).isoformat())); await db.commit()
    return groups


async def execution_sensitivity_report(db_path: str, research_run_id: str | None=None) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS proactive_execution_research_runs (research_run_id TEXT PRIMARY KEY,input_sha256 TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL)")
        query="SELECT research_run_id,result_json FROM proactive_execution_research_runs"+(" WHERE research_run_id=?" if research_run_id else "")+" ORDER BY research_run_id"
        rows=await (await db.execute(query,(research_run_id,) if research_run_id else ())).fetchall()
    return [{"research_run_id":run_id,"research_only":True,"can_place_orders":False,"authorization_effect":"NONE","comparisons":json.loads(payload)} for run_id,payload in rows]
