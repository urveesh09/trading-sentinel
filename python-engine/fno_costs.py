"""
[FNO-COSTS 2026-07-10] Round-trip cost model for NIFTY options (spec §10.2).

Written fresh, NOT copied from calc_penny_costs: flat fees punish small
premiums, which inverts the penny module's many-small-bets assumption.
The module must clear ~0.7% of premium movement before it earns a rupee.

There is deliberately NO bypass flag. Penny has PENNY_BROKERAGE_BYPASS for
paper-mode proactiveness measurement; F&O must not, because cost is a
first-order term in whether this strategy works at all, and hiding it
would make the paper leg lie (spec §10.2).

Rate provenance (VERIFY-4 / VERIFY-5, resolved 2026-07-10 against
Zerodha's published charge list):
  - Brokerage: flat Rs 20 per executed order for F&O.
  - STT: 0.15% of premium on the SELL side from 2026-04-01.
  - NSE exchange txn: 0.03553% of premium, both sides.
  - SEBI: Rs 10/crore (0.0001%) of premium, both sides.
  - Stamp duty: 0.003% of premium, BUY side only.
  - NSE IPFT: Rs 0.01/crore of premium, both sides.
  - GST: 18% on (brokerage + exchange txn + SEBI + IPFT).
  - STT on EXERCISED ITM options is 0.15% of intrinsic
    -- moot here because P1 is intraday-only and the §7.1 rule
    says never let a long option expire ITM.

All rates live in config so a schedule change is an .env edit, not a
code change.
"""
from __future__ import annotations

from cost_schedules import options_cost_snapshot


def calc_fno_costs_from_snapshot(
    entry_premium: float, exit_premium: float, qty: int, snapshot: dict,
) -> float:
    """Total round-trip cost from an immutable options schedule snapshot.

    qty is the total unit count (lots * lot_size). entry is the BUY,
    exit is the SELL. Returns 0.0 for degenerate inputs rather than
    raising -- the caller treats cost as a P&L subtraction, and a
    crash on a malformed row must not kill a scan tick.
    """
    if qty <= 0 or entry_premium < 0 or exit_premium < 0:
        return 0.0
    buy_value = entry_premium * qty
    sell_value = exit_premium * qty
    turnover = buy_value + sell_value

    rates = snapshot["rates"]
    brokerage = float(rates["brokerage_flat_per_order"]) * 2.0
    stt = float(rates["stt_sell_pct"]) * sell_value
    exchange_txn = float(rates["exchange_pct"]) * turnover
    sebi = float(rates["sebi_pct"]) * turnover
    stamp = float(rates["stamp_duty_buy_pct"]) * buy_value
    ipft = float(rates.get("ipft_pct", 0.0)) * turnover
    gst = float(rates["gst_pct"]) * (brokerage + exchange_txn + sebi + ipft)

    return brokerage + stt + exchange_txn + sebi + stamp + ipft + gst


def calc_fno_costs(entry_premium: float, exit_premium: float, qty: int) -> float:
    """Operational cost using the current versioned settings snapshot."""
    return calc_fno_costs_from_snapshot(
        entry_premium, exit_premium, qty, options_cost_snapshot(),
    )


def breakeven_move_pct(premium: float, qty: int) -> float:
    """Fraction of premium the position must gain just to cover a flat
    round trip (exit == entry). Surfaced in the hourly report so the
    operator sees the cost drag, not just the gross curve."""
    if premium <= 0 or qty <= 0:
        return 0.0
    return calc_fno_costs(premium, premium, qty) / (premium * qty)
