"""Deterministic, Dev-only partner fixture lifecycle demonstration.

This proves the real fixture adapter's create -> close -> reopen behaviour and
the portfolio-revision supersession that retires old hedge review evidence.
It uses a new isolated SQLite database and never contacts a broker or delivery
transport.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from config import settings
from hedge_advisory import _record_shadow_evaluation, load_partner_hedge_cards
from hedge_analytics import load_partner_evaluation_input, load_partner_positions
from partner_fixture_adapter import apply_fixture_account


async def run_partner_lifecycle_demo(db_path: str) -> dict:
    """Create immutable lifecycle evidence in a new database, or fail closed."""
    target = Path(db_path)
    if target.exists():
        raise FileExistsError("demo database already exists; choose a new path")
    target.parent.mkdir(parents=True, exist_ok=True)
    base = datetime(2026, 9, 7, 4, 0, tzinfo=timezone.utc)
    account_id = "demo-partner-account"
    position = {
        "external_position_id": "nifty-core", "instrument_type": "EQUITY",
        "underlying": "NIFTY", "tradingsymbol": "NIFTYBEES", "quantity": 100,
        "entry_price": 250, "current_price": 255, "underlying_price": 255,
    }

    def fixture(snapshot_id: str, sequence: int, observed_at: datetime, positions: list[dict]) -> dict:
        return {
            "source": "fixture", "account_id": account_id, "snapshot_id": snapshot_id,
            "sequence": sequence, "complete": True, "observed_at": observed_at.isoformat(),
            "positions": positions,
        }

    # The adapter's configured source/account binding is deliberately scoped to
    # this offline run and restored even if an assertion fails.
    with patch.object(settings, "PARTNER_HEDGE_INPUT_EXPECTED_SOURCE", "fixture"), patch.object(
        settings, "PARTNER_HEDGE_INPUT_EXPECTED_ACCOUNT_ID", account_id,
    ):
        created = await apply_fixture_account(
            str(target), fixture("open-1", 1, base, [position]), received_at=base,
        )
        before = await load_partner_evaluation_input(str(target))
        await _record_shadow_evaluation(
            str(target), phase="phase2", kind="covered_call_recommendation",
            dedup_key="demo-lifecycle-advice", text="Synthetic hedge review: NIFTY coverage.",
            detail={
                "account_id": account_id, "underlying": "NIFTY",
                "contracts": ["NIFTY-DEMO-CE"], "snapshot_id": "open-1",
                "portfolio_revision": before.portfolio_revision,
                "reason": "SHADOW_DEMO_ONLY",
            }, now=base,
        )
        closed = await apply_fixture_account(
            str(target), fixture("close-2", 2, base + timedelta(minutes=1), []),
            received_at=base + timedelta(minutes=1),
        )
        reopened = await apply_fixture_account(
            str(target), fixture("reopen-3", 3, base + timedelta(minutes=2), [position]),
            received_at=base + timedelta(minutes=2),
        )
        adjusted_position = {
            **position, "quantity": 200, "entry_price": 125, "current_price": 127.5,
            "corporate_action": {
                "event_id": "demo-nifty-2-for-1", "type": "SPLIT", "factor": 2,
                "effective_at": (base + timedelta(minutes=3)).isoformat(),
            },
        }
        corporate_action = await apply_fixture_account(
            str(target), fixture("split-4", 4, base + timedelta(minutes=3), [adjusted_position]),
            received_at=base + timedelta(minutes=3),
        )

    after = await load_partner_evaluation_input(str(target))
    positions = await load_partner_positions(str(target), include_closed=True)
    cards = await load_partner_hedge_cards(str(target))
    if not created["accepted"] or not closed["accepted"] or not reopened["accepted"] or not corporate_action["accepted"]:
        raise RuntimeError("fixture lifecycle was not accepted")
    if len(positions) != 3 or sum(row.status == "OPEN" for row in positions) != 1:
        raise RuntimeError("fixture reopen did not create exactly one new open lifecycle")
    current = next(row for row in positions if row.status == "OPEN")
    if (current.signed_quantity, current.entry_price) != (200, 125):
        raise RuntimeError("corporate action did not retain provider-adjusted lifecycle economics")
    if before.portfolio_revision >= after.portfolio_revision:
        raise RuntimeError("fixture lifecycle did not advance portfolio revision")
    if len(cards["cards"]) != 1 or not cards["cards"][0]["is_superseded"]:
        raise RuntimeError("older hedge review evidence was not marked superseded")
    if cards["cards"][0]["can_send"] or cards["cards"][0]["can_trade"]:
        raise RuntimeError("demonstration accidentally granted authority")
    return {
        "mode": "SHADOW", "fixture_only": True, "can_send": False,
        "can_trade": False, "authorization_effect": "NONE", "account_id": account_id,
        "snapshots": {"created": created, "closed": closed, "reopened": reopened,
                      "corporate_action": corporate_action},
        "lifecycle": {
            "position_count": len(positions), "open_positions": sum(row.status == "OPEN" for row in positions),
            "closed_positions": sum(row.status == "CLOSED" for row in positions),
            "revision_before": before.portfolio_revision, "revision_after": after.portfolio_revision,
        },
        "cards": cards,
        "assertions": {
            "complete_snapshot_close": True, "reopen_new_lifecycle": True,
            "corporate_action_new_lifecycle": True,
            "old_advice_superseded": True, "no_delivery_or_trade_authority": True,
        },
    }
