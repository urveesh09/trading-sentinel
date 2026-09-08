import pytest

from integrated_dev_demo import run_integrated_dev_demo


@pytest.mark.asyncio
async def test_integrated_dev_demo_exercises_all_offline_consumers(tmp_path):
    result = await run_integrated_dev_demo(str(tmp_path / "integrated"))
    assert result["mode"] == "DEV_FIXTURE"
    assert result["can_place_orders"] is result["can_send"] is result["can_trade"] is False
    assert result["optional_ai"]["state"] == "OUTAGE_CIRCUIT_OPEN"
    assert all(result["assertions"].values())
    assert len(result["proactive"]["five_session_diagnostics"]["reports"]) >= 1
    assert result["partner"]["assertions"]["corporate_action_new_lifecycle"] is True
