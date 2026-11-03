"""Exactly two mechanisms, chosen from Jan-Jun 2026 only. No parameter sweep.

They are research arms; neither changes expiry_paper.py or a paper book.
All numbers are inherited from A/AL/C, not optimized against the new prices.
"""
from dataclasses import replace
import arms as M
import e011_lab as L

EP=L.EP
CANDIDATES={
    # A gives an idle breakout eight minutes to show at least +40%.
    "E012_IDLE8":replace(M.ARMS["E011"],time_stop=(8*60,.40)),
    # AL keeps half the peak gain; start at A's +40% bank trigger.
    "E012_LOCK40":M.ARMS["E011"],
}


def lock40(pos,policy,bid,now,structure_broken=False):
    peak=max(pos["peak"],bid)
    entry=pos["entry_price"]
    if peak>=entry*1.4:
        pos["stop"]=max(pos["stop"],round(entry+.5*(peak-entry),2))
    return L._bank_manager(M.ARMS["E011"])(pos,policy,bid,now,structure_broken)


MANAGERS={"E012_LOCK40":lock40}
