from dataclasses import replace

import pytest

from shock_repair import FIRST, START, VolumeBar, decision, shock_signal


def bars():
    history = [VolumeBar(25000, 25004, 24996, 25000 + (i % 2), 100) for i in range(13)]
    return [*history, VolumeBar(25000, 25000, 24968, 24970, 500),
            VolumeBar(24970, 24985, 24969, 24978, 120)]


def test_long_and_short_use_symmetric_geometry():
    tape = bars()
    long = shock_signal(tape, FIRST)
    mirror = [VolumeBar(50000 - bar.open, 50000 - bar.low, 50000 - bar.high, 50000 - bar.close, bar.volume)
              for bar in tape]
    short = shock_signal(mirror, FIRST)
    assert (long.direction, long.close, long.stop, long.target) == ("LONG", 24978, 24967.95, 25000)
    assert (short.direction, short.close, short.stop, short.target) == ("SHORT", 25022, 25032.05, 25000)


@pytest.mark.parametrize(("index", "field", "value"), [
    (-2, "volume", 199),
    (-2, "close", 24986),
    (-1, "close", 24975),
    (-1, "close", 24981),
    (-1, "close", 24983),
    (-1, "low", 24967),
])
def test_refuses_weak_shock_exhausted_target_and_new_extreme(index, field, value):
    tape = bars()
    tape[index] = replace(tape[index], **{field: value})
    assert shock_signal(tape, FIRST) is None


def test_first_signal_uses_only_completed_minutes_and_valid_prefix():
    tape = {START + block * 5 + minute: replace(bar, volume=bar.volume / 5)
            for block, bar in enumerate(bars()) for minute in range(5)}
    result = decision(tape)
    assert result[0] == "signal" and result[1].minute == FIRST
    tape[FIRST] = VolumeBar(0, 0, 0, 0, 0)
    assert decision(tape) == result
    tape.pop(FIRST - 1)
    assert decision(tape) == ("missing_or_invalid_clock", None)
