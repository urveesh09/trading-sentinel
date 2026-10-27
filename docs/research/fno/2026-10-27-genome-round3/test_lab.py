"""O27f lab checks: causality, the copied entry path, genome operators and metric arithmetic."""
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab  # noqa: E402
import fno_policy_replay as replay  # noqa: E402

DAY = "2026-10-01"
HAVE_DATA = (lab.DATA / "fno-replay.sqlite").is_file()
needs_data = pytest.mark.skipif(not HAVE_DATA, reason="private read-only export not present")


def _data():
    import run_fno_consistency_grid as grid
    lab.CACHE.mkdir(parents=True, exist_ok=True)
    return grid.CachedReplayData(lab.DATA, lab.CACHE)


def _frame(day=DAY):
    data = _data()
    obs, _ = data.observations(day)
    return data.futures_frame(obs[0].future.contract.token, date.fromisoformat(day))


@needs_data
def test_features_and_every_family_are_prefix_invariant():
    """A bar's features and signals never change when later bars are removed (no look-ahead)."""
    frame = _frame()
    day = date.fromisoformat(DAY)
    full = lab.day_features(frame, day)
    cut_at = pd.Timestamp(f"{DAY} 12:00:00")
    short = lab.day_features(frame[frame.index <= cut_at], day)
    cols = ["atr", "ema20", "vwap", "vsd", "rvol", "hi4", "lo4", "er4", "body", "above", "below"]
    pd.testing.assert_frame_equal(full["t"].loc[:cut_at, cols], short["t"][cols])
    rng = random.Random(3)
    genomes = [lab.random_genome(f, rng) for f in (*lab.REAL_FAMILIES, "NULL_RANDOM") for _ in range(6)]
    genomes += lab.seeds()
    n = len(short["t"])
    for g in genomes:
        assert list(lab.family_directions(g, full)[:n]) == list(lab.family_directions(g, short)), g


@needs_data
def test_binary_search_bar_matches_the_replay_rule():
    frame = _frame()
    f = lab.day_features(frame, date.fromisoformat(DAY))
    start = replay.IST.localize(datetime.fromisoformat(f"{DAY} 09:15:00"))
    for k in range(0, 6 * 60 * 60, 37):
        now = start + timedelta(seconds=k)
        assert lab.last_closed_bar(f, now) == replay._last_closed_bar(frame, now)


@needs_data
def test_passthrough_entry_copy_trades_exactly_as_the_shipped_book():
    data = _data()
    window = ("2026-10-01", "2026-10-05")
    shipped = replay.SingleLegReplay(data, replay.resolve_policy("CURRENT")).run(*window)
    copied = lab.LabReplay(data, replay.resolve_policy("CURRENT"), None).run(*window)
    keys = ("bar_ts", "tradingsymbol", "entry_time", "entry_premium", "exit_time", "exit_premium", "net_pnl")
    assert shipped["trades"], "the window must hold a shipped trade"
    assert [{k: t.get(k) for k in keys} for t in copied["trades"]] == \
           [{k: t.get(k) for k in keys} for t in shipped["trades"]]


def _fake_features():
    idx = pd.date_range(f"{DAY} 09:15", periods=40, freq="5min")
    rising = pd.Series(range(40), index=idx, dtype=float) * 10 + 25000
    t = pd.DataFrame({"open": rising - 4, "high": rising + 6, "low": rising - 6, "close": rising,
                      "volume": 1000.0}, index=idx)
    t["atr"], t["ema20"], t["vwap"], t["vsd"], t["rvol"] = 10.0, rising - 30, rising - 50, 20.0, 1.5
    t["hi4"] = t["high"].shift(1).rolling(4).max()
    t["lo4"] = t["low"].shift(1).rolling(4).min()
    t["er4"], t["body"], t["above"], t["below"] = 1.0, 0.66, 1.0, 0.0
    t["green"], t["red"] = 1, 0
    t["minute"] = [s.hour * 60 + s.minute for s in idx]
    return {"day": date.fromisoformat(DAY), "t": t, "pdh": 25100.0, "pdl": 24800.0, "pdc": 24950.0, "htf_up": True,
            "complete_open": True, "day_open": 24996.0, "orh": 25036.0, "orl": 24994.0,
            "stamps": list(idx.strftime("%Y-%m-%d %H:%M:%S"))}


def _mirror(f):
    m = dict(f)
    t = f["t"].copy()
    for col in ("open", "high", "low", "close", "ema20", "vwap", "hi4", "lo4"):
        t[col] = -f["t"][col]
    t["high"], t["low"] = -f["t"]["low"], -f["t"]["high"]
    t["hi4"], t["lo4"] = -f["t"]["lo4"], -f["t"]["hi4"]
    t["above"], t["below"], t["green"], t["red"] = f["t"]["below"], f["t"]["above"], f["t"]["red"], f["t"]["green"]
    m.update(t=t, pdh=-f["pdl"], pdl=-f["pdh"], day_open=-f["day_open"], orh=-f["orl"], orl=-f["orh"])
    return m


def test_every_sub_signal_is_direction_symmetric():
    f = _fake_features()
    for name in lab.SUBS:
        up = lab.sub_signal(name, f, lab.SUB_DEFAULTS)
        down = lab.sub_signal(name, _mirror(f), lab.SUB_DEFAULTS)
        assert list(down) == [-v for v in up], name
    assert (lab.sub_signal("ORB20", f, lab.SUB_DEFAULTS) == 1).any()


def test_null_family_is_deterministic_and_seed_dependent():
    f = _fake_features()
    a = {"family": "NULL_RANDOM", "nr_p": 0.08, "nr_seed": 1}
    assert list(lab.family_directions(a, f)) == list(lab.family_directions(dict(a), f))
    assert list(lab.family_directions(a, f)) != list(lab.family_directions({**a, "nr_seed": 2}, f))


def test_genome_operators_stay_inside_the_declared_space():
    rng = random.Random(7)
    for _ in range(300):
        a = lab.random_genome(rng.choice((*lab.REAL_FAMILIES, "NULL_RANDOM")), rng)
        b = lab.random_genome(rng.choice((*lab.REAL_FAMILIES, "NULL_RANDOM")), rng)
        for g in (lab.mutate(lab.crossover(a, b, rng), rng), *lab.neighbours(a)):
            assert g == lab.canonical(g)
            for k, alleles in {**lab.FAMILY_GENES[g["family"]], **lab.SHARED_GENES}.items():
                if k == "en_members":
                    assert len(g[k]) >= 2 and set(g[k]) <= set(lab.SUBS)
                else:
                    assert g[k] in alleles, (k, g[k])
    g = lab.seeds()[0]
    assert all(sum(n[k] != g[k] for k in g) == 1 for n in lab.neighbours(g))
    assert lab.pool("REAL") == lab.pool("REAL") and len(lab.pool("NULL")) == lab.POOL["per_family"]


def test_metrics_and_fitness_arithmetic():
    days = ["2026-10-05", "2026-10-06", "2026-10-12"]
    trades = [
        {"entry_time": "2026-10-05T10:00:00+05:30", "exit_time": "2026-10-05T10:30:00+05:30", "net_pnl": 1000.0,
         "gross_pnl": 1100.0, "entry_qty": 65, "exit_reason": "TARGET"},
        {"entry_time": "2026-10-06T10:00:00+05:30", "exit_time": "2026-10-06T10:30:00+05:30", "net_pnl": -400.0,
         "gross_pnl": -300.0, "entry_qty": 65, "exit_reason": "STOP"},
        {"entry_time": "2026-10-12T10:00:00+05:30", "exit_time": "2026-10-12T10:30:00+05:30", "net_pnl": 300.0,
         "gross_pnl": 400.0, "entry_qty": 65, "exit_reason": "TARGET"},
        {"entry_time": "2026-10-13T10:00:00+05:30", "exit_time": "2026-10-13T10:30:00+05:30", "net_pnl": 9e9,
         "gross_pnl": 9e9, "entry_qty": 65, "exit_reason": "OUTSIDE"},
    ]
    m = lab.metrics(trades, days)
    assert (m["trades"], m["net"], m["best_day"], m["dd"], m["charges"]) == (3, 900.0, 1000.0, 400.0, 300.0)
    assert m["stressed"] == pytest.approx(900 - 3 * 130 - 75)
    assert (m["weeks"], m["green_weeks"], m["red_weeks"], m["green_days"], m["red_days"]) == (2, 2, 0, 2, 1)
    assert lab.fitness(m) == pytest.approx(-5 + 3 / 6)
    many = {**m, "trades": 6}
    assert lab.fitness(many) == pytest.approx((900 - 1000) / 1000 + 1.0)
