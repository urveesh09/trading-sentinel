"""[SX-P2 2026-10-21] PEN_SMART_V2: the Smart Penny policy with room to breathe.

Declared on 2026-10-21 from PEN_SMART_V1's own Production paper record
(Oct 5-21: 68 closes, 9 wins, 59 losses, -Rs 163 on Rs 2,000):
  - its stop sat a median 0.86% under the entry (noise allowance
    max(1 x 1-minute ATR, 0.4% of the anchor, 3 ticks)), inside the quoted
    spread and one-tick moves of a Rs 3-50 stock, so many trades were stopped
    within 0.4-2 minutes;
  - 33 of 68 exits were SMART_THESIS_FAILED after two 1-minute closes under
    the anchor, most within 15 minutes;
  - the 9 wins came only from trades that lived long enough to trail.

V2 changes exactly three numbers and nothing else (same code, scanner clock,
universe, quotes, costs, sizing caps and bankroll as V1):
  noise_atr_mult        1.0   -> 1.5    stop 1.5 x 1-minute ATR under the anchor
  min_noise_pct         0.004 -> 0.012  ... and at least 1.2% under it
  failed_breakout_closes 2    -> 3      a thesis fails on three closes under the anchor
Position size still comes from the frozen risk and per-stock caps, so a wider
stop buys fewer shares, not more risk per rupee of book.

It runs beside V1 (which stays byte-identical and hash-bound) as its own
paper book, scored only on sessions after this declaration. Promotion over
V1 needs at least 30 V2 closes and the research method's four checks.
"""
from dataclasses import replace

from penny_smart_policy import SMART_PARAMS

SMART_V2_VERSION = "PEN_SMART_V2"
SMART_V2_DECLARED = "2026-10-21"
SMART_V2_PARAMS = replace(
    SMART_PARAMS,
    policy_version=SMART_V2_VERSION,
    noise_atr_mult=1.5,
    min_noise_pct=0.012,
    failed_breakout_closes=3,
)
