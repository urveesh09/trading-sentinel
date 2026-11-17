"""SN441 fixture: a missing scheduled exit must be UNRESOLVED, never priced from an earlier mark (the auditor's
synthetic late-exit failure in SN428's trade())."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sn441  # noqa: E402


def _arrays():
    ask = np.full(386, np.nan)
    bid = np.full(386, np.nan)
    ask[45] = 100.0
    bid[50] = 101.0          # one bid at minute 5 after entry, nothing later
    return ask, bid


def test_old_rule_prices_from_minute_five():
    ask, bid = _arrays()
    v = sn441.sn428.trade(ask, bid, 45, 105, 205.0, False)
    assert v is not None      # the old rule's flaw: the 60-minute hold is priced at minute 5


def test_legal_rule_is_unresolved():
    ask, bid = _arrays()
    state, net, x, b = sn441.legal(ask, bid, 45, 105, 205.0)
    assert state == "UNRESOLVED" and net is None


def test_legal_rule_takes_first_bid_at_or_after_exit_within_grace():
    ask, bid = _arrays()
    bid[108] = 102.0
    state, net, x, b = sn441.legal(ask, bid, 45, 105, 205.0)
    assert state == "ENTERED" and x == 108 and b == 102.0
    bid2 = bid.copy()
    bid2[108] = np.nan
    bid2[111] = 102.0       # 6 minutes late: outside the grace
    assert sn441.legal(ask, bid2, 45, 105, 205.0)[0] == "UNRESOLVED"


def test_stop_uses_an_observed_bid():
    ask, bid = _arrays()
    bid[60] = 40.0           # (40 - 100) x 65 = -3,900 -> stop
    state, net, x, b = sn441.legal(ask, bid, 45, 105, 205.0)
    assert state == "ENTERED" and x == 60 and net <= -3000
