"""N08's rules at their edges, and that nothing in them can look ahead. Run with the repo's venv: pytest test_n08.py -q."""
import ast
import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import n08_rules as R  # noqa: E402


@pytest.mark.parametrize("age,bid,progress,trail,expected", [
    (59.9, 100, 0.0, False, 120),        # before half the clock: native
    (60.0, 100, 0.0, False, 60),         # at half the clock, no gain, no progress: stalled
    (60.0, 100.05, 0.0, False, 120),     # the option is above what was paid: keep it
    (60.0, 100, 0.5, False, 120),        # the underlying made the required progress: keep it
    (60.0, 100, 0.49, False, 60),
    (60.0, 90, 0.0, True, 120),          # a trailed trade is never on the time stop
    (120.0, 90, 0.0, False, 120),        # at the native clock the native rule takes over
    (60.0, 0, 0.0, False, 120),          # no bid: no decision
])
def test_half_clock_stall(age, bid, progress, trail, expected):
    assert R.half_clock_stall(age, 120.0, trail, bid, 100.0, progress) == expected


def test_half_clock_stall_ignores_bad_numbers():
    assert R.half_clock_stall(float("nan"), 120.0, False, 100, 100, 0) == 120.0
    assert R.half_clock_stall(70, 120.0, False, float("inf"), 100, 0) == 120.0


@pytest.mark.parametrize("eligible,bid,progress,expected", [
    (False, 90, -1, False),      # never outside N04's own eligibility
    (True, 100, 0.3, True),      # no gain in the option: N07's rule
    (True, 101, 0.3, False),     # gain and progress: keep it
    (True, 101, 0.0, True),      # gain but no progress at all
    (True, 101, -0.2, True),
    (True, None, -1, False),     # no bid: no decision
    (True, 0, -1, False),
])
def test_no_progress_cut(eligible, bid, progress, expected):
    assert R.no_progress_cut(eligible, bid, 100.0, progress) == expected


@pytest.mark.parametrize("minute,last,expected", [(839, 840, True), (840, 840, False), (900, None, True)])
def test_late_low_day_entries(minute, last, expected):
    assert R.low_day_time_allowed(minute, last) == expected


@pytest.mark.parametrize("minute,before,expected", [(719, 720, 2), (720, 720, 1), (690, None, 1), (900, 720, 1)])
def test_low_day_lots(minute, before, expected):
    assert R.low_day_lots(minute, before) == expected


@pytest.mark.parametrize("mode,direction,di_up,expected", [
    ("PUTS", "SHORT", True, True), ("PUTS", "LONG", True, False), ("PUTS", "SHORT", None, True),
    ("PUTS_UNLESS_UP", "SHORT", True, False), ("PUTS_UNLESS_UP", "SHORT", False, True), ("PUTS_UNLESS_UP", "LONG", False, False), ("PUTS_UNLESS_UP", "SHORT", None, False),
    ("WITH_TREND", "LONG", True, True), ("WITH_TREND", "SHORT", True, False), ("WITH_TREND", "LONG", False, False), ("WITH_TREND", "SHORT", False, True), ("WITH_TREND", "SHORT", None, True),
])
def test_low_day_direction(mode, direction, di_up, expected):
    assert R.low_day_direction_allowed(mode, direction, di_up) == expected


def test_unknown_direction_mode_is_an_error():
    with pytest.raises(ValueError):
        R.low_day_direction_allowed("ANY", "SHORT", True)


def test_rules_take_no_data_source():
    """Each rule is a pure function of values handed to it: no imports beyond math, no frames, no dates."""
    tree = ast.parse(inspect.getsource(R))
    imports = {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)} | {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imports <= {"math", "__future__"}


def run_lab(code: str, year: str = "2025") -> str:
    env = {"N08_YEAR": year, "PYTHONDONTWRITEBYTECODE": "1", **{k: v for k, v in __import__("os").environ.items() if k in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA")}}
    out = subprocess.run([sys.executable, "-B", "-c", f"import sys; sys.path.insert(0, r'{HERE}')\nimport n08_lab as N\n{code}"], capture_output=True, text=True, timeout=240, env=env)
    assert out.returncode == 0, out.stderr[-1500:]
    return out.stdout.strip().splitlines()[-1]


def test_n08_is_exactly_what_it_says():
    got = json.loads(run_lab("import json; b=N.n08_book(); print(json.dumps({'n08': b['n08'], 'cfg': b['cfg'], 'mode': b['n07_mode'], 'cost': b['cost'], 'profile': b['n02_profile']}))"))
    assert got["mode"] == "PREMIUM_STALL"
    assert got["profile"] == "TPB_ONE"
    assert got["cost"] == [200.0, 5.0]
    assert got["cfg"] == {"FNO_MAX_LOTS": 2, "FNO_MAX_LOTS_PROVEN": 2}
    assert got["n08"]["low_two_lots_before"] == 720 and got["n08"]["low_last_minute"] == 840
    assert got["n08"]["exits"] == {"EFF": {"FNO_TRAIL_ATR_MULT": 2.0}, "OR20": {"FNO_TRAIL_ATR_MULT": 2.0}}
    assert set(got["n08"]) == {"contract", "exits", "low_two_lots_before", "low_last_minute"}


def test_2023_is_refused_outside_the_exam():
    out = subprocess.run([sys.executable, "-B", str(HERE / "n08_lab.py"), "screen"], capture_output=True, text=True, timeout=240, env={**__import__("os").environ, "N08_YEAR": "2023", "PYTHONDONTWRITEBYTECODE": "1"})
    assert out.returncode != 0
    assert "2023 is reached only through the sealed exam" in out.stderr


def test_no_development_script_can_read_2023():
    for name in ("diagnose_context.py", "diagnose_sides.py"):
        text = (HERE / name).read_text(encoding="utf-8")
        assert 'never' in text and '"2023"' not in text.split("assert")[1].split("\n")[0], name
