"""The 2024 sheet's checks: the frozen books are the declared ones, and its verdict applies the frozen rule."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import exam_r as E  # noqa: E402


def _trades(net_each: float, n: int = 50) -> list:
    return [{"entry_time": f"2024-03-{1 + i % 28:02d}T10:{i % 60:02d}:00+05:30", "exit_time": f"2024-03-{1 + i % 28:02d}T10:{i % 60:02d}:30+05:30",
             "entry_premium": 100.0, "entry_qty": 65, "lots_at_exit": 1, "net_pnl": net_each if i else -500.0} for i in range(n)]


def test_books_are_the_declared_ones():
    b = E.books()
    assert set(b) == set(E.BOOKS) and b[E.PICK]["skip"] == 0.5 and b[E.PICK]["cost"] == [200.0, 5.0]
    assert b["LIVE|SHIPPED|COST"]["cfg"] == {} and "skip" not in b["LIVE|SHIPPED|COST"]


def test_verdict_holds_only_when_the_pick_earns_and_beats_today():
    sets = {n: _trades(10.0) for n in E.BOOKS}
    sets[E.PICK] = _trades(100.0)
    assert E.verdict(sets)["pick_holds"]
    sets["LIVE|SHIPPED|COST"] = _trades(200.0)
    assert not E.verdict(sets)["pick_holds"], "must beat today's book"
    sets = {n: _trades(10.0) for n in E.BOOKS}
    sets[E.PICK] = _trades(-1.0)
    assert not E.verdict(sets)["pick_holds"], "must earn"
    sets[E.PICK] = _trades(100.0, n=30)
    assert not E.verdict(sets)["pick_holds"], "needs 40 trades"


def test_level_is_judged_per_rupee_of_fall():
    sets = {n: _trades(10.0) for n in E.BOOKS}
    sets[E.PICK] = _trades(100.0)
    sets["TPB+rule|R5|OFF|COST"] = _trades(50.0)
    assert E.verdict(sets)["level_confirmed"]
    sets["TPB+rule|R5|OFF|COST"] = _trades(200.0)
    assert not E.verdict(sets)["level_confirmed"]
