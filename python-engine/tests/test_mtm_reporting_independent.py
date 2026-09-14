"""Incomplete valuation must not be displayed as zero trading P&L."""
from datetime import datetime, timezone

import pytest

from mark_to_market import OpenMarkToMarket, PositionMark, QuoteStatus
from penny_hourly_report import PennyHourlyReport


@pytest.mark.parametrize("status", [QuoteStatus.STALE, QuoteStatus.UNAVAILABLE, QuoteStatus.UNSUPPORTED])
def test_incomplete_aggregate_is_unknown_even_when_partial_subtotal_is_zero(status):
    result = OpenMarkToMarket(marks=[PositionMark("FNO", "FNO_PAPER", "fixture", 5000,
                                                0, 0, status, None)])
    assert result.total_unrealised_pnl == 0  # Compatibility partial sum only.
    assert result.complete_unrealised_pnl is None


def test_fresh_flat_book_has_genuine_zero_valuation():
    assert OpenMarkToMarket().complete_unrealised_pnl == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("active", [False, True])
async def test_active_and_no_action_reports_label_unknown_valuation(tmp_path, active):
    report = await PennyHourlyReport(str(tmp_path / "fixture.db")).build_report(
        now=datetime(2026, 9, 14, 6, 0, tzinfo=timezone.utc), regime="FIXTURE",
        open_positions=[{"ticker": "FIXTURE"}], deployed_capital=5000,
        unrealised_pnl=None, kill_switch_active=active, circuit_blocks=0)
    assert "UNAVAILABLE" in report
    assert "Rs +0" not in report
