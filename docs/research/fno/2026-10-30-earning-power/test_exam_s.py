"""The 2024 sheet's checks: the frozen books are the declared ones, and its verdict applies the frozen rule."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import exam_s as E  # noqa: E402


def _trade(day, net, lots=1, prem=100.0, stretch=None):
    return {"entry_time": f"{day}T10:00:00+05:30", "exit_time": f"{day}T10:30:00+05:30", "entry_premium": prem,
            "net_pnl": net, "lots_at_exit": lots, "stretch": stretch}


def _sets(skip_net, plain_net):
    shipped = {}
    for b in ("LIVE", "BEST", "TPB"):
        shipped[b] = [_trade("2024-03-04", plain_net)]
        shipped[f"{b}|skip"] = [_trade("2024-03-04", skip_net)]
    raw = {n: [_trade("2024-03-04", skip_net)] for n in ("TPB", "TPB|HOUSE", "TPB|skip", "BEST|skip", "LIVE|skip")}
    for i in range(20):
        raw[f"NULL{i:02d}"] = [_trade("2024-03-04", -500.0)]
        raw[f"NULL{i:02d}|skip"] = [_trade("2024-03-04", -300.0)]
    return shipped, raw


def test_rule_holds_when_it_beats_two_books_and_the_random_median():
    v = E.verdict(*_sets(1000.0, 100.0))
    assert v["stretch_rule_holds"] and v["rule_beat_on"] == ["LIVE", "BEST", "TPB"]
    assert v["TPB|skip"]["passes"] and v["TPB|skip"]["net_plus_200"] == 3 * 1000 - 3 * 200


def test_rule_fails_when_the_books_do_not_gain():
    v = E.verdict(*_sets(100.0, 1000.0))
    assert not v["stretch_rule_holds"] and not v["TPB|skip"]["passes"]


def test_rule_needs_the_random_control_too():
    shipped, raw = _sets(1000.0, 100.0)
    for i in range(20):
        raw[f"NULL{i:02d}|skip"] = [_trade("2024-03-04", -900.0)]
    assert not E.verdict(shipped, raw)["stretch_rule_holds"]


def test_frozen_books():
    shipped, raw = E.books("shipped"), E.books("raw")
    assert set(shipped) == set(E.SHIPPED)
    assert shipped["LIVE|skip"]["skip"] == 0.5 and "skip" not in shipped["LIVE"]
    assert raw["TPB|HOUSE"]["pyr"] == "HOUSE" and raw["TPB|skip"]["skip"] == 0.5
    assert sum(n.startswith("NULL") and "|" not in n for n in raw) == 20
    assert sum(n.startswith("NULL") and n.endswith("|skip") for n in raw) == 20
