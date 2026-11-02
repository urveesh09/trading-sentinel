"""N09's rules at their edges, and the volatility reading's dates. The replay parity check is `n09_lab.py parity`."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import n09_rules as R  # noqa: E402


def test_confirmed_long_needs_a_higher_close_and_an_untouched_stop():
    assert R.confirmed("LONG", 100.0, 101.0, 99.0, 102.0, 95.0, 0.1)
    assert not R.confirmed("LONG", 100.0, 100.0, 99.0, 102.0, 95.0, 0.1)      # equal is not further
    assert not R.confirmed("LONG", 100.0, 101.0, 95.0, 102.0, 95.0, 0.1)      # touched the stop


def test_confirmed_short_is_the_mirror():
    assert R.confirmed("SHORT", 100.0, 99.0, 98.0, 101.0, 105.0, 0.1)
    assert not R.confirmed("SHORT", 100.0, 100.0, 98.0, 101.0, 105.0, 0.1)
    assert not R.confirmed("SHORT", 100.0, 99.0, 98.0, 105.0, 105.0, 0.1)


def test_confirmed_refuses_a_stretched_move_and_allows_no_reading():
    assert not R.confirmed("LONG", 100.0, 101.0, 99.0, 102.0, 95.0, 0.5)
    assert R.confirmed("LONG", 100.0, 101.0, 99.0, 102.0, 95.0, 0.49)
    assert R.confirmed("LONG", 100.0, 101.0, 99.0, 102.0, 95.0, None)


def test_confirmed_refuses_bad_numbers():
    assert not R.confirmed("LONG", float("nan"), 101.0, 99.0, 102.0, 95.0, 0.1)


def test_target_is_measured_from_the_confirmed_price():
    assert R.target_from("LONG", 110.0, 100.0) == 128.0
    assert R.target_from("SHORT", 90.0, 100.0) == 72.0


def test_structure_needs_age_two_closes_and_no_progress():
    closes, vwaps = [101.0, 99.0, 98.0], [100.0, 100.0, 100.0]
    assert R.structure_broken("LONG", closes, vwaps, 20.0, False, 0.2)
    assert not R.structure_broken("LONG", closes, vwaps, 19.9, False, 0.2)                 # too young
    assert not R.structure_broken("LONG", closes, vwaps, 25.0, True, 0.2)                  # the trail is running
    assert not R.structure_broken("LONG", closes, vwaps, 25.0, False, 0.5)                 # working
    assert not R.structure_broken("LONG", [99.0, 101.0], [100.0, 100.0], 25.0, False, 0.2)  # only one close wrong
    assert R.structure_broken("SHORT", [101.0, 102.0], [100.0, 100.0], 25.0, False, 0.2)


def test_noise_sigma_needs_ten_sessions():
    assert R.noise_sigma([0.01] * 9) is None
    assert abs(R.noise_sigma([0.01] * 14) - 0.01) < 1e-12
    assert R.noise_sigma([0.01] * 9 + [float("nan")]) is None


def test_noise_bounds_widen_on_the_side_of_a_gap():
    up, low = R.noise_bounds(100.0, 102.0, 0.01)     # gap down: the upper boundary starts from yesterday's close
    assert abs(up - 103.02) < 1e-9 and abs(low - 99.0) < 1e-9
    up, low = R.noise_bounds(102.0, 100.0, 0.01)     # gap up: the lower boundary starts from yesterday's close
    assert abs(up - 103.02) < 1e-9 and abs(low - 99.0) < 1e-9


def test_noise_marks_are_thirty_minute_multiples_after_the_open():
    closes = [9 * 60 + 40, 10 * 60 + 10, 10 * 60 + 40, 14 * 60 + 40]      # bars closing 09:45, 10:15, 10:45, 14:45
    assert all(R.noise_mark(m) for m in closes)
    assert not any(R.noise_mark(m) for m in (9 * 60 + 45, 10 * 60, 10 * 60 + 15))


def test_noise_direction_is_outside_the_boundaries_only():
    assert R.noise_direction(104.0, 103.0, 99.0) == "LONG"
    assert R.noise_direction(98.0, 103.0, 99.0) == "SHORT"
    assert R.noise_direction(103.0, 103.0, 99.0) is None


def test_noise_trail_uses_the_tighter_of_boundary_and_vwap():
    assert R.noise_trail_hit("LONG", 102.0, 103.0, 99.0, 101.0)      # below the boundary
    assert R.noise_trail_hit("LONG", 103.5, 103.0, 99.0, 104.0)      # above the boundary, below VWAP
    assert not R.noise_trail_hit("LONG", 104.5, 103.0, 99.0, 104.0)
    assert R.noise_trail_hit("SHORT", 98.5, 103.0, 99.0, 98.0)
    assert not R.noise_trail_hit("SHORT", 97.5, 103.0, 99.0, 98.0)
    assert R.noise_trail_hit("LONG", 102.0, 103.0, 99.0, None)


def test_trailing_median_needs_history_and_uses_the_window():
    assert R.trailing_median([1.0] * 119) is None
    assert R.trailing_median([9.0] * 100 + [1.0] * 250) == 1.0


def test_vol_lots_never_refuses_and_defaults_to_one():
    assert R.vol_lots(1.0, 0.9) == 2
    assert R.vol_lots(0.9, 0.9) == 2
    assert R.vol_lots(0.8, 0.9) == 1
    assert R.vol_lots(None, 0.9) == 1
    assert R.vol_lots(1.0, None) == 1


def test_rearm_rules():
    assert R.rearm_annual(2023, 2024) and not R.rearm_annual(2023, 2023)
    assert not R.rearm_shadow([100.0] * 19)
    assert R.rearm_shadow([100.0] * 20)
    assert not R.rearm_shadow([100.0] * 30 + [-100.0] * 20)
    assert R.rearm_shadow([-100.0] * 30 + [100.0] * 20)
    assert not R.rearm_shadow([0.0] * 20)


def test_volatility_reading_never_reads_its_own_day():
    import json
    rows = {}
    for path in (HERE.parent / "2026-11-01-fno-n08/_local/daily-2023.json", HERE.parent / "2026-10-31-fno-complements/_local/daily-2026.json"):
        if not path.exists():
            return
        for row in json.loads(path.read_text(encoding="utf-8"))["rows"]:
            rows[row[0]] = row
    days = sorted(rows)
    assert days[0] == "2022-01-03" and days[-1] >= "2026-10-28"
    assert all(a < b for a, b in zip(days, days[1:]))
