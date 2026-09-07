import pytest

from partner_lifecycle_demo import run_partner_lifecycle_demo


@pytest.mark.asyncio
async def test_partner_lifecycle_demo_proves_close_reopen_and_supersession(tmp_path):
    result = await run_partner_lifecycle_demo(str(tmp_path / "partner-lifecycle.db"))

    assert result["fixture_only"] is True
    assert result["can_send"] is result["can_trade"] is False
    assert result["lifecycle"]["position_count"] == 2
    assert result["lifecycle"]["open_positions"] == 1
    assert result["assertions"]["old_advice_superseded"] is True
    assert result["cards"]["cards"][0]["portfolio_state"] == "SUPERSEDED"
