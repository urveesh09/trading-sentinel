from datetime import datetime,timezone
import pytest
from proactive_diagnostics import proactive_owner_diagnostics

@pytest.mark.asyncio
async def test_diagnostics_are_observation_only_when_no_source_exists(db_path):
    result=await proactive_owner_diagnostics(db_path,now=datetime(2026,9,7,tzinfo=timezone.utc))
    assert result["can_place_orders"] is False and result["authorization_effect"]=="NONE"
