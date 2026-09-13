"""Conservative matched exit-policy research for SHADOW proposals only."""
from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
from datetime import datetime, timezone

import aiosqlite

from proactive_intelligence import ShadowProposal, ShadowSimulation, _normalise_shadow_bars, _stamp, _simulate_shadow_trailing_stop, simulate_shadow_trade, _research_proposal_manifest, _shadow_implementation_identity


async def _init_exit_research_schema(db):
    await db.execute("CREATE TABLE IF NOT EXISTS proactive_exit_research_runs (research_run_id TEXT PRIMARY KEY,input_sha256 TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL)")
    await db.execute("CREATE TABLE IF NOT EXISTS proactive_exit_research_manifests (research_run_id TEXT PRIMARY KEY,manifest_json TEXT NOT NULL)")


def _matching_exit_result(row, digest, manifest_json):
    if row is None:
        return None
    if row[0] != digest or row[2] != manifest_json:
        raise ValueError("exit research manifest conflicts with existing evidence; create a new research_run_id")
    return json.loads(row[1])


def simulate_partial_target_trail(proposal: ShadowProposal, bars: list[dict], *, cash: float, fee_rate: float=.001, slippage_bps: float=5) -> ShadowSimulation:
    """Exit half at target, then trail the balance; ambiguous bars fail closed.

    A stop that trades in the same OHLC bar as the first target is processed
    first. A newly raised trailing stop applies only from the following bar,
    avoiding a fabricated favourable intrabar sequence.
    """
    normalised=_normalise_shadow_bars(bars)
    cutoff=_stamp(proposal.data_cutoff or proposal.signal_at or proposal.valid_until)
    deadline=_stamp(proposal.entry_deadline or proposal.valid_until); holding=_stamp(proposal.holding_deadline or proposal.valid_until)
    if normalised is None or cash<=0 or proposal.stop<=0 or proposal.entry<=proposal.stop or proposal.target<=proposal.entry:
        return ShadowSimulation("INVALID",0,None,None,None,None,None,"INVALID_EXIT_RESEARCH_INPUT")
    slip=slippage_bps/10_000; entry=None; entry_at=None; quantity=0; remaining=0; partial_done=False; trailing=proposal.stop; proceeds=0.; fees=0.; last=None
    for stamp,open_,high,low,_close in normalised:
        if entry is None:
            if stamp<=cutoff or stamp>deadline: continue
            entry=open_*(1+slip); entry_at=stamp; quantity=math.floor(cash/(entry*(1+fee_rate)))
            if quantity<1: return ShadowSimulation("NO_FILL",0,None,None,None,None,None,"INSUFFICIENT_CASH_AFTER_FEES")
            if entry<=proposal.stop or entry>=proposal.target: return ShadowSimulation("NO_FILL",0,None,None,None,None,None,"GAP_INVALIDATES_ENTRY_GEOMETRY")
            remaining=quantity; fees+=entry*quantity*fee_rate
        last=stamp
        # A gap/open or intrabar protective stop is always resolved before a
        # target in the same bar. This is deliberately pessimistic.
        if stamp>holding or low<=trailing:
            exit_price=(open_ if stamp>holding else min(open_,trailing))*(1-slip)
            proceeds+=exit_price*remaining; fees+=exit_price*remaining*fee_rate; remaining=0
            gross=proceeds-entry*quantity
            return ShadowSimulation("CLOSED",quantity,round(entry,4),round(proceeds/quantity,4),round(gross,4),round(fees,4),round(gross-fees,4),"HOLDING_DEADLINE" if stamp>holding else "TRAILING_STOP" if partial_done else "STOP",entry_at,stamp)
        if not partial_done and high>=proposal.target:
            partial=max(1, quantity//2); partial=min(partial,remaining)
            price=proposal.target*(1-slip); proceeds+=price*partial; fees+=price*partial*fee_rate; remaining-=partial; partial_done=True
        if partial_done and remaining:
            # The previous trailing stop, not this bar's high, governed the
            # stop decision above. The new level begins with the next candle.
            trailing=max(trailing,high-(entry-proposal.stop))
        if remaining==0:
            gross=proceeds-entry*quantity
            return ShadowSimulation("CLOSED",quantity,round(entry,4),round(proceeds/quantity,4),round(gross,4),round(fees,4),round(gross-fees,4),"PARTIAL_TARGET_COMPLETE",entry_at,stamp)
    return ShadowSimulation("OPEN",quantity,round(entry,4) if entry else None,None,None,None,None,"DATA_END_OPEN_POSITION",entry_at,last) if entry else ShadowSimulation("NO_FILL",0,None,None,None,None,None,"NO_EXECUTABLE_BAR_AFTER_SIGNAL")


async def persist_exit_policy_comparison(db_path: str, *, research_run_id: str, proposals: list[ShadowProposal], future_bars: dict[str,list[dict]], cash: float, fee_rate: float=.001, slippage_bps: float=5) -> list[dict]:
    if not isinstance(research_run_id, str) or not research_run_id.strip():
        raise ValueError("research_run_id is required")
    if not all(math.isfinite(value) for value in (cash, fee_rate, slippage_bps)) or cash <= 0 or fee_rate < 0 or slippage_bps < 0:
        raise ValueError("invalid exit research assumptions")
    proposals = list(proposals)
    if len({p.opportunity_id for p in proposals}) != len(proposals):
        raise ValueError("exit research proposals require unique opportunity identities")
    if not isinstance(future_bars, dict):
        raise ValueError("future_bars must be a mapping")
    future_bars = deepcopy(future_bars)
    payload={"proposals":[_research_proposal_manifest(p) for p in proposals],"bars":future_bars,"cash":cash,"fee_rate":fee_rate,"slippage_bps":slippage_bps,"version":"matched-exit-evidence-v3","exit_profiles":["STOP_TARGET_TIME_V1","PARTIAL_TARGET_TRAIL_V1","TRAILING_STOP_V1"],"implementation_sha256":{"exit_research":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"primary_evaluator":_shadow_implementation_identity()}}
    manifest_json=json.dumps(payload,sort_keys=True,default=str,separators=(",",":"),allow_nan=False)
    digest=hashlib.sha256(manifest_json.encode()).hexdigest()
    async with aiosqlite.connect(db_path) as db:
        await db.execute("BEGIN IMMEDIATE")
        await _init_exit_research_schema(db)
        row=await (await db.execute("SELECT r.input_sha256,r.result_json,m.manifest_json FROM proactive_exit_research_runs r LEFT JOIN proactive_exit_research_manifests m ON m.research_run_id=r.research_run_id WHERE r.research_run_id=?",(research_run_id,))).fetchone()
        cached = _matching_exit_result(row, digest, manifest_json)
        await db.commit()
        if cached is not None:
            return cached
    rows=[]
    for name, runner in (("STOP_TARGET_TIME_V1",lambda p,b:simulate_shadow_trade(p,b,cash=cash,fee_rate=fee_rate,slippage_bps=slippage_bps)),("PARTIAL_TARGET_TRAIL_V1",lambda p,b:simulate_partial_target_trail(p,b,cash=cash,fee_rate=fee_rate,slippage_bps=slippage_bps)),("TRAILING_STOP_V1",lambda p,b:_simulate_shadow_trailing_stop(p,b,cash=cash,fee_rate=fee_rate,slippage_bps=slippage_bps))):
        outcomes=[runner(p,future_bars.get(p.instrument,[])) for p in proposals]; closed=[float(x.net_pnl) for x in outcomes if x.status=="CLOSED" and x.net_pnl is not None]
        rows.append({"exit_profile_id":name,"cost_model_version":"EQUITY_CASH_ESTIMATE_V1","trials":len(outcomes),"closed_outcomes":len(closed),"open_outcomes":sum(x.status=="OPEN" for x in outcomes),"no_fills":sum(x.status=="NO_FILL" for x in outcomes),"net_pnl":round(sum(closed),4) if closed else None,"net_expectancy":round(sum(closed)/len(closed),4) if closed else None,"reasons":{reason:sum(x.reason==reason for x in outcomes) for reason in sorted({x.reason for x in outcomes})}})
    async with aiosqlite.connect(db_path) as db:
        await db.execute("BEGIN IMMEDIATE")
        row=await (await db.execute("SELECT r.input_sha256,r.result_json,m.manifest_json FROM proactive_exit_research_runs r LEFT JOIN proactive_exit_research_manifests m ON m.research_run_id=r.research_run_id WHERE r.research_run_id=?",(research_run_id,))).fetchone()
        cached = _matching_exit_result(row, digest, manifest_json)
        if cached is not None:
            await db.commit()
            return cached
        await db.execute("INSERT INTO proactive_exit_research_runs (research_run_id,input_sha256,result_json,created_at) VALUES (?,?,?,?)",(research_run_id,digest,json.dumps(rows,sort_keys=True),datetime.now(timezone.utc).isoformat()))
        await db.execute("INSERT INTO proactive_exit_research_manifests (research_run_id,manifest_json) VALUES (?,?)",(research_run_id,manifest_json))
        await db.commit()
    return rows


async def exit_policy_report(db_path: str, research_run_id: str|None=None) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS proactive_exit_research_runs (research_run_id TEXT PRIMARY KEY,input_sha256 TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL)")
        query="SELECT research_run_id,result_json FROM proactive_exit_research_runs"+(" WHERE research_run_id=?" if research_run_id else "")+" ORDER BY research_run_id"; rows=await (await db.execute(query,(research_run_id,) if research_run_id else ())).fetchall()
    return [{"research_run_id":key,"research_only":True,"can_place_orders":False,"authorization_effect":"NONE","comparisons":json.loads(value)} for key,value in rows]
