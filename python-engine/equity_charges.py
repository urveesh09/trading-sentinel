"""[S23-COST1 2026-10-23] Which Zerodha equity schedule a round trip pays.

The Oct 23 audit found two settlement paths charging the same EDGE book
differently: the daily tracker used the engine's old CNC branch, the confirmed
EDGE exit the delivery schedule. Neither asked the question that decides the
real charge: were the shares held overnight?

Zerodha charges a CNC buy that is sold in the same session as an intraday
trade (0.03% or Rs 20 brokerage per order, 0.025% sell-side STT, intraday
stamp duty, no DP charge; support.zerodha.com, "brokerage charged for partial
delivery", read 2026-10-23). Only shares held past the session pay delivery
charges (no brokerage, 0.1% STT on both legs, 0.015% buy stamp duty and the
DP charge on the sell day). MIS is always intraday.

Example (Oct 22 EDGE_PAPER DCMSRIND, 873 shares 54.30 -> 51.5424, same day):
intraday Rs 48.84; the tracker booked Rs 82.58 and the delivery schedule
would have charged Rs 118.31.

Known limit: when only part of a CNC buy is sold the same day Zerodha may
charge intraday brokerage on the whole buy order; the books charge per sold
quantity.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import pytz

IST = pytz.timezone("Asia/Kolkata")


def session_date(value) -> Optional[date]:
    """The IST trading date of a date, datetime or ISO string; ``None`` when unreadable."""
    if value is None:
        return None
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, date):
        return value
    else:
        try:
            moment = datetime.fromisoformat(str(value).strip())
        except ValueError:
            return None
    return moment.astimezone(IST).date() if moment.tzinfo else moment.date()


def charged_as_intraday(product_type, entry_date, exit_date, *, default_product: str = "MIS") -> bool:
    """True when the round trip pays intraday charges.

    MIS (or any non-CNC product) is intraday. CNC is intraday only when it is
    sold in the session it was bought; an unreadable date keeps the delivery
    schedule, as before this rule."""
    product = str(product_type or default_product).strip().upper()
    if product != "CNC":
        return True
    bought, sold = session_date(entry_date), session_date(exit_date)
    return bought is not None and sold is not None and bought == sold
