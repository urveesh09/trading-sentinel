from datetime import datetime, timedelta, timezone

import pytest

from proactive_execution_research import persist_execution_sensitivity
from proactive_intelligence import ShadowProposal


@pytest.mark.asyncio
async def test_execution_sensitivity_retains_gap_rejection_and_stressed_costs(db_path):
    at=datetime(2026,1,1,tzinfo=timezone.utc)
    proposal=ShadowProposal("entry","trend_pullback_v1","NSE:ENTRY",100,95,110,at+timedelta(minutes=30),1.01,100,"test",at,at,at+timedelta(minutes=30),at+timedelta(hours=1))
    bars={"NSE:ENTRY":[{"timestamp":(at+timedelta(minutes=1)).isoformat(),"open":120,"high":121,"low":119,"close":120}]}
    rows=await persist_execution_sensitivity(db_path,research_run_id="costs",proposals=[proposal],future_bars=bars,cash=1000)
    assert {row["scenario"] for row in rows}=={"NORMAL_V1","STRESSED_V1"}
    assert all(row["cost_model_version"]=="EQUITY_CASH_ESTIMATE_V1" for row in rows)
    assert any("GAP_INVALIDATES_ENTRY_GEOMETRY" in row["reasons"] for row in rows)
