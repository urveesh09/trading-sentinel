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
  - STT: 0.1% of premium on the SELL side (raised from 0.0625% on
    2024-10-01, Finance (No.2) Act 2024).
  - NSE exchange txn: 0.03503% of premium, both sides.
  - SEBI: Rs 10/crore (0.0001%) of premium, both sides.
  - Stamp duty: 0.003% of premium, BUY side only.
  - NSE IPFT: Rs 0.50/lakh (0.0005%) of premium, both sides.
  - GST: 18% on (brokerage + exchange txn + SEBI).
  - STT on EXERCISED ITM options is 0.125% of intrinsic (post-Sept-2019
    rule) -- moot here because P1 is intraday-only and the §7.1 rule
    says never let a long option expire ITM.

All rates live in config so a schedule change is an .env edit, not a
code change.
"""
from __future__ import annotations

from config import settings


def calc_fno_costs(entry_premium: float, exit_premium: float, qty: int) -> float:
    """Total round-trip transaction cost in rupees for a long option.

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

    brokerage = settings.FNO_BROKERAGE_FLAT * 2.0
    stt = settings.FNO_STT_SELL_PCT * sell_value
    exchange_txn = settings.FNO_EXCHANGE_TXN_PCT * turnover
    sebi = settings.FNO_SEBI_PCT * turnover
    stamp = settings.FNO_STAMP_DUTY_PCT * buy_value
    ipft = settings.FNO_IPFT_PCT * turnover
    gst = settings.FNO_GST_PCT * (brokerage + exchange_txn + sebi)

    return brokerage + stt + exchange_txn + sebi + stamp + ipft + gst


def breakeven_move_pct(premium: float, qty: int) -> float:
    """Fraction of premium the position must gain just to cover a flat
    round trip (exit == entry). Surfaced in the hourly report so the
    operator sees the cost drag, not just the gross curve."""
    if premium <= 0 or qty <= 0:
        return 0.0
    return calc_fno_costs(premium, premium, qty) / (premium * qty)
