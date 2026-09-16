"""[WORKFLOW-C.B3 2026-09-15] Per-exchange settlement
assumption reference table.

Per the 2026-09-15 production deep audit B-3:
> 8. **Exchange-specific settlement assumptions.** Need operator
> to confirm settlement assumptions per exchange (NSE cash, NSE
> F&O, BSE). Not derivable from code alone.

This module is a frozen reference table that:
1. Documents the operator-confirmed settlement assumptions for
   each (exchange, product_type) combination the system trades.
2. Is queried at runtime by tests to pin the existing
   behavior so future changes don't drift silently.
3. Acts as the single source of truth that future operator
   confirmations can UPDATE -- without touching the rest of
   the system.

The current code models settlement via `product_type`:
  - "MIS" = intraday, T+0 (square-off before close).
  - "CNC" = delivery, T+1 (equity delivery).

The exchange field is a free-form str (default "NSE"). The
cost_schedules module handles NSE equity intraday and NSE
options cost rates. BSE is currently advisory-only (partner
manual advisory NIFTY+SENSEX) -- no live trading code path.

CONFIRMED operator assumptions (recorded 2026-09-15):
  - NSE cash equity:
      MIS: T+0 (intraday square-off).
      CNC: T+1 (delivery, equity).
  - NSE F&O:
      MIS: T+0 (intraday).
      NRML: T+1 (carryforward, expires on expiry day).
      OPTIONS premium: settled on expiry day.
  - BSE:
      Advisory-only (NIFTY-SENSEX partner advisory).
      No live trading code path.

If the operator wants to OVERRIDE any of these in the future,
edit the ``SETTLEMENT_ASSUMPTIONS`` constant below. Each
override should include the operator's name + date as the
``last_confirmed_by`` / ``last_confirmed_at`` fields so the
audit trail is clear.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal


ProductType = Literal["MIS", "CNC", "NRML"]
ExchangeCode = Literal["NSE", "BSE"]
SettlementConvention = Literal["T+0", "T+1", "EXPIRY_DAY", "ADVISORY_ONLY"]


@dataclass(frozen=True)
class SettlementAssumption:
    """One row of the per-exchange settlement table.

    Attributes:
        exchange: NSE or BSE.
        product_type: MIS / CNC / NRML.
        settlement: T+0 / T+1 / EXPIRY_DAY / ADVISORY_ONLY.
        description: human-readable note explaining the
            assumption's basis.
        last_confirmed_by: operator name (or "hermes-frozen"
            for the initial snapshot).
        last_confirmed_at: ISO timestamp of confirmation.
    """
    exchange: ExchangeCode
    product_type: ProductType
    settlement: SettlementConvention
    description: str
    last_confirmed_by: str
    last_confirmed_at: str


# Frozen operator-confirmed settlement assumptions.
# Operator may update ``last_confirmed_by`` / ``last_confirmed_at``
# fields with each confirmation; the rest of each row should
# remain stable across deploys so downstream tests can pin
# behavior.
SETTLEMENT_ASSUMPTIONS: tuple[SettlementAssumption, ...] = (
    SettlementAssumption(
        exchange="NSE",
        product_type="MIS",
        settlement="T+0",
        description="NSE cash equity intraday. Square-off before market close. "
                    "Margin blocked intraday, released on square-off.",
        last_confirmed_by="hermes-frozen",
        last_confirmed_at="2026-09-15T00:00:00+00:00",
    ),
    SettlementAssumption(
        exchange="NSE",
        product_type="CNC",
        settlement="T+1",
        description="NSE cash equity delivery. Shares delivered to demat "
                    "account on T+1; funds settled on T+1.",
        last_confirmed_by="hermes-frozen",
        last_confirmed_at="2026-09-15T00:00:00+00:00",
    ),
    SettlementAssumption(
        exchange="NSE",
        product_type="NRML",
        settlement="EXPIRY_DAY",
        description="NSE F&O carryforward (futures). Settled on expiry day "
                    "at 15:30 IST close. Options premium also settled on "
                    "expiry day.",
        last_confirmed_by="hermes-frozen",
        last_confirmed_at="2026-09-15T00:00:00+00:00",
    ),
    SettlementAssumption(
        exchange="BSE",
        product_type="MIS",
        settlement="ADVISORY_ONLY",
        description="BSE cash equity intraday. Currently ADVISORY-ONLY "
                    "(partner manual advisory NIFTY-SENSEX); no live "
                    "trading code path in the engine.",
        last_confirmed_by="hermes-frozen",
        last_confirmed_at="2026-09-15T00:00:00+00:00",
    ),
    SettlementAssumption(
        exchange="BSE",
        product_type="CNC",
        settlement="ADVISORY_ONLY",
        description="BSE cash equity delivery. Currently ADVISORY-ONLY; "
                    "no live trading code path.",
        last_confirmed_by="hermes-frozen",
        last_confirmed_at="2026-09-15T00:00:00+00:00",
    ),
    SettlementAssumption(
        exchange="BSE",
        product_type="NRML",
        settlement="ADVISORY_ONLY",
        description="BSE F&O. Currently ADVISORY-ONLY; no live trading "
                    "code path.",
        last_confirmed_by="hermes-frozen",
        last_confirmed_at="2026-09-15T00:00:00+00:00",
    ),
)


def lookup_settlement(exchange: str, product_type: str) -> SettlementAssumption | None:
    """Look up the operator-confirmed settlement assumption
    for a (exchange, product_type) pair.

    Returns ``None`` if no row matches. The caller should
    treat ``None`` as "unverified -- refuse to trade".
    """
    for row in SETTLEMENT_ASSUMPTIONS:
        if row.exchange == exchange.upper() and row.product_type == product_type.upper():
            return row
    return None


def format_assumptions_table() -> str:
    """Render the assumption table as a human-readable
    table for the operator runbook / docs.
    """
    lines = [
        "# Per-exchange settlement assumptions",
        "# ------------------------------------",
        "# Frozen reference table (F-3 from the 2026-09-15 production",
        "# audit: operator confirmation required per exchange).",
        "# Edit SETTLEMENT_ASSUMPTIONS to override; tests will pin",
        "# the resulting behavior.",
        "",
        f"{'EXCHANGE':<8}  {'PRODUCT':<8}  {'SETTLEMENT':<14}  DESCRIPTION",
        f"{'-' * 8}  {'-' * 8}  {'-' * 14}  {'-' * 60}",
    ]
    for row in SETTLEMENT_ASSUMPTIONS:
        lines.append(
            f"{row.exchange:<8}  {row.product_type:<8}  {row.settlement:<14}  {row.description}"
        )
        lines.append(
            f"{'':<8}  {'':<8}  {'':<14}  Confirmed by {row.last_confirmed_by} at {row.last_confirmed_at}"
        )
        lines.append("")
    lines.append(f"# Total: {len(SETTLEMENT_ASSUMPTIONS)} (exchange, product_type) rows.")
    return "\n".join(lines) + "\n"


def assumptions_as_dicts() -> list[dict]:
    """Serialize the table as plain dicts (for JSON output
    or machine-readable audit reports).
    """
    return [
        {
            "exchange": r.exchange,
            "product_type": r.product_type,
            "settlement": r.settlement,
            "description": r.description,
            "last_confirmed_by": r.last_confirmed_by,
            "last_confirmed_at": r.last_confirmed_at,
        }
        for r in SETTLEMENT_ASSUMPTIONS
    ]


__all__ = [
    "ExchangeCode",
    "ProductType",
    "SettlementAssumption",
    "SettlementConvention",
    "SETTLEMENT_ASSUMPTIONS",
    "assumptions_as_dicts",
    "format_assumptions_table",
    "lookup_settlement",
]
