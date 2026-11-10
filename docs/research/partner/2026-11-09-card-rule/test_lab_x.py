"""N09c checks: the books are the declared ones and the card's exits reach the shipped exit ladder as declared."""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab_x as X  # noqa: E402

sys.path.insert(0, str(X.ROOT / "python-engine"))
from config import settings  # noqa: E402
from fno_exit_rules import evaluate_single_leg_exit, live_single_leg_exit_params  # noqa: E402


def test_books():
    b = X.books()
    assert sum(n.startswith("NULL") for n in b) == X.NULL_BOOKS == 20
    assert len({X.Y.digest(v) for k, v in b.items() if k.startswith("NULL")}) == 20
    card = b["CARD|shipped"]["members"]
    assert [(m["name"], m["gate"], m["exit"]) for m in card] == [("SHIPPED", "ALWAYS", "CARD")]
    assert [(m["name"], m["exit"]) for m in b["REF|shipped_book_exits"]["members"]] == [("SHIPPED", "OWN")]
    assert X.Y.digest(b["INFO|live_union_adx"]) == X.Y.digest(X.C.books()["BASE|UNION_ADX"])
    for k, v in b.items():
        if k.startswith("NULL"):
            g = v["members"][0]["genome"]
            assert g["family"] == "NULL_RANDOM" and g["exit"] == "CARD" and g["stop_atr"] == 1.5 and g["target_r"] == 1.8


def test_policy_carries_card_exit():
    pol = X.Y.member_policy(X.Y.named("SHIPPED", "ALWAYS", "CARD"))
    assert dict(pol.exit_overrides) == X.CARD_EXIT


def _pos(**kw):
    base = dict(direction="LONG", entry_underlying=100.0, stop_underlying=97.0, target_underlying=105.4, atr_at_entry=2.0,
                entry_premium=50.0, premium_stop=37.5, entry_time="2026-03-02T10:00:00+05:30", trail_active=False,
                trail_stop_underlying=None, best_underlying=None, best_premium=None)
    return SimpleNamespace(**{**base, **kw})


def _decide(pos, fut, minutes=30, premium=55.0):
    params = {**live_single_leg_exit_params(settings), **X.CARD_EXIT}
    now = datetime.fromisoformat("2026-03-02T10:00:00+05:30") + timedelta(minutes=minutes)
    return evaluate_single_leg_exit(pos, now_ist=now, fut_price=fut, exit_px_basis=premium, hard_flat=False,
                                    params=params).exit_reason


def test_card_exit_sells_at_the_target():
    assert _decide(_pos(), 105.5) == "trail_stop"          # zero-width trail: out on the target observation


def test_card_exit_has_no_time_stop_or_lock():
    assert _decide(_pos(), 100.2, minutes=300) == ""        # five hours, going nowhere: still held
    assert _decide(_pos(best_premium=80.0), 101.0, premium=52.0) == ""   # gave back most of a gain: no lock


def test_card_exit_keeps_the_index_stop():
    assert _decide(_pos(), 96.9) == "underlying_stop"
