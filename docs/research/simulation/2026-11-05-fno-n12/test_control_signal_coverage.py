from datetime import date, timedelta
from types import SimpleNamespace

import control_signal_coverage as coverage
from fno_models import FnoDirection


DAY = date(2026, 10, 28)


def test_regime_cannot_reach_back_before_its_receipt(monkeypatch):
    seen = []
    monkeypatch.setattr(coverage.fno_book, "with_participation", lambda own, _: own)
    monkeypatch.setattr(coverage, "evaluate_fno_mom", lambda *_args, **_kwargs: None)

    def route(_frame, regime, at, **_kwargs):
        seen.append((at, regime))
        return SimpleNamespace(direction=FnoDirection.LONG, strategy="N11_EFF", bar_ts="bar")

    monkeypatch.setattr(coverage.fno_book, "n11_signal", route)
    first = coverage.clock(DAY, 585, 20)
    fired, missing = coverage.native_signals(DAY, "NIFTY", None, None, "HIGH", ([first], ["KNOWN"]))
    assert 585 in missing
    assert seen[0] == (coverage.clock(DAY, 590, 1), "KNOWN")
    assert fired[0]["minute"] == 590
    assert not fired[0]["retest_context_complete"]


def test_first_usable_clock_cannot_skip_a_missing_ladder(monkeypatch):
    signal = {"at": coverage.clock(DAY, 585, 1).isoformat(), "minute": 585, "direction": "LONG"}
    monkeypatch.setattr(coverage.quotes, "ladder_snapshot", lambda _name, _at, _m, packet: packet)
    early = coverage.clock(DAY, 585)
    first = coverage.clock(DAY, 585, 5)
    later = coverage.clock(DAY, 585, 30)
    result = coverage.first_entry(signal, "NIFTY", {}, {
        ("NIFTY", early): (object(), True),
        ("NIFTY", first): (None, False),
        ("NIFTY", later): (object(), True),
    })
    assert result == {"status": "incomplete_verified_ladder", "receipt": first.isoformat()}


def test_held_depth_requires_same_batch_and_exposes_gap_to_flat():
    start = coverage.clock(DAY, 15 * 60 + 8, 25)
    next_mark = start + timedelta(seconds=60)
    flat = start + timedelta(seconds=120)
    entry = {"receipt": start.isoformat(), "option_token": 1, "front_token": 2}
    option = SimpleNamespace(bid=5, bid_quantity=40, contract=SimpleNamespace(lot_size=20))
    future = SimpleNamespace(ltp=100)
    packets = {("SENSEX", 1): {start: option, next_mark: option, flat: option},
               ("SENSEX", 2): {start: future, next_mark: future, flat: future}}
    path = coverage.summarize_held("SENSEX", entry, packets, 2)
    assert path["flat_bid"] and path["sampled_90sec_path"]
    assert path["max_gap_sec"] == 60
    assert not path["native_10sec_path"]
    packets["SENSEX", 2].pop(next_mark)
    path = coverage.summarize_held("SENSEX", entry, packets, 2)
    assert path["max_gap_sec"] == 120
    assert not path["sampled_90sec_path"]
