import pytest
from dev_acceptance_harness import run_dev_acceptance_harness

@pytest.mark.asyncio
async def test_dev_harness_proves_ai_outage_does_not_authorize_orders(tmp_path):
    result=await run_dev_acceptance_harness(str(tmp_path / "harness"))
    assert result["ai_outage_state"] == "UNAVAILABLE"
    assert result["can_place_orders"] is False and result["scheduler"] == "NOT_STARTED_BY_DESIGN"
