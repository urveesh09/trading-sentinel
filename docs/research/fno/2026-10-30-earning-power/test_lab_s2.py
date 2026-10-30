"""O30s Tier 2 checks: a stretched signal is passed over, an unstretched or opposite one is kept, books are as declared."""
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab_s2 as T  # noqa: E402


def _route(limit, stretch, direction="LONG"):
    from collections import Counter
    sig = T.G.MomSignal(bar_ts="2026-03-02 10:00:00")
    sig.direction = SimpleNamespace(value=direction)
    book = SimpleNamespace(book={"skip": limit} if limit is not None else {}, warm=False, notes=Counter())
    before_route, before_stretch = T._prev_route, T.S.stretch_at
    T._prev_route = lambda self, frame, regime, now: sig
    T.S.stretch_at = lambda frame, now, d: stretch
    try:
        return T.route(book, None, "", None), book.notes
    finally:
        T._prev_route, T.S.stretch_at = before_route, before_stretch


def test_stretched_signal_is_passed_over():
    out, notes = _route(0.5, 0.5)
    assert out.direction is None and out.reject_reason == "o30s2:stretched" and notes["o30s2_stretched"] == 1


def test_near_signal_is_kept():
    out, notes = _route(0.5, 0.49)
    assert out.direction is not None and not notes["o30s2_stretched"]


def test_no_reading_keeps_the_signal():
    assert _route(0.5, None)[0].direction is not None


def test_books_without_the_rule_are_untouched():
    assert _route(None, 9.9)[0].direction is not None


def test_books():
    shipped, raw = T.books("shipped"), T.books("raw")
    assert shipped["LIVE|skip"]["skip"] == 0.5 and "skip" not in shipped["LIVE"]
    assert {shipped[f"TPB|skip{k}"]["skip"] for k in (25, 75)} == {0.25, 0.75}
    assert sum(n.startswith("NULL") for n in raw) == 20 and all(v["skip"] == 0.5 for v in raw.values())
    assert [m["gate"] for m in shipped["BEST"]["members"]] == [T.C.ADX, T.C.ADX, T.C.ADX, "ALWAYS"]
