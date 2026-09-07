from datetime import datetime, timedelta, timezone

import pytest

from proactive_intelligence import ShadowProposal
from proactive_portfolio_research import chronological_policy_research, replay_common_cash_basket


def _proposal(name, policy, at):
    return ShadowProposal(name, policy, "NSE:"+name, 100, 95, 110, at+timedelta(hours=1), 1.01, 100, "test", at, at, at+timedelta(hours=1), at+timedelta(hours=2))


def test_common_cash_replay_does_not_reuse_same_clock_cash():
    at=datetime(2026, 1, 1, tzinfo=timezone.utc); proposals=[_proposal("a","trend_pullback_v1",at),_proposal("b","contraction_breakout_v1",at)]
    bars={"NSE:a":[{"timestamp":(at+timedelta(minutes=1)).isoformat(),"open":100,"high":111,"low":99,"close":110}], "NSE:b":[{"timestamp":(at+timedelta(minutes=1)).isoformat(),"open":100,"high":111,"low":99,"close":110}]}
    result=replay_common_cash_basket(proposals,bars,capital=150,method="FIXED_EQUAL_V1",fee_rate=0,slippage_bps=0)
    selected=[item for item in result["decisions"] if item["state"]=="CLOSED"]
    assert len(selected)==0 or sum(item["reserved"] for item in selected)<=150.01
    assert result["can_place_orders"] is False


def test_chronological_research_retains_insufficient_folds_without_edge_claim():
    base=datetime(2026,1,1,tzinfo=timezone.utc)
    proposals=[_proposal(f"p{i}", "trend_pullback_v1" if i%2 else "range_reversion_v1", base+timedelta(days=i)) for i in range(4)]
    bars={item.instrument:[{"timestamp":(item.signal_at+timedelta(minutes=1)).isoformat(),"open":100,"high":111,"low":99,"close":110}] for item in proposals}
    result=chronological_policy_research(proposals,bars,train_days=2,test_days=1)
    assert result["verdict"]=="insufficient_data" and result["can_place_orders"] is False


@pytest.mark.asyncio
async def test_portfolio_research_is_persisted_with_immutable_input(db_path):
    from proactive_portfolio_research import persist_portfolio_and_fold_research, portfolio_research_report
    base=datetime(2026,1,1,tzinfo=timezone.utc); proposals=[_proposal("p", "trend_pullback_v1", base)]
    bars={"NSE:p":[{"timestamp":(base+timedelta(minutes=1)).isoformat(),"open":100,"high":111,"low":99,"close":110}]}
    await persist_portfolio_and_fold_research(db_path,research_run_id="frozen",proposals=proposals,future_bars=bars,capital=500)
    [report]=await portfolio_research_report(db_path,"frozen")
    assert report["risk_budget"]["can_place_orders"] is False
