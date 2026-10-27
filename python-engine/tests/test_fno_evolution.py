"""scripts/run_fno_evolution.py (O27b): genomes, the shipped genome's parity, breeding and the frozen fitness."""
import json
from pathlib import Path
import random
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import run_fno_evolution as evo  # noqa: E402
from config import settings  # noqa: E402
from tests.test_fno_policy_replay import DAY, _write_dataset  # noqa: E402


def test_the_shipped_genome_is_the_live_book_and_seeds_keep_only_pool_alleles():
    shipped = evo.policy(evo.SHIPPED)
    exits = dict(shipped.exit_overrides)
    assert exits["FNO_TIME_STOP_MIN"] == settings.FNO_TIME_STOP_MIN
    assert exits["FNO_TRAIL_ATR_MULT"] == settings.FNO_TRAIL_ATR_MULT
    assert exits["FNO_PROFIT_LOCK_ARM_R"] == settings.FNO_PROFIT_LOCK_ARM_R
    variant = shipped.signal_variant
    assert (variant.opening_range_minutes, variant.freshness, variant.ema_filter, variant.ema_spans) == (
        settings.FNO_OR_MINUTES, "crossing", True, None)
    assert (variant.buffer_atr, variant.min_rvol, variant.stop_atr_mult, variant.target_r) == (
        settings.FNO_OR_BUFFER_ATR, settings.FNO_MIN_RVOL, settings.FNO_STOP_ATR_MULT, settings.FNO_TARGET_R)
    assert variant.latest_entry_min is None and not (variant.vwap_side or variant.gap_align or variant.or_bias)
    assert evo._settings_check()["current_arm"] == "OR30|LOCK_LIVE|T45|TR1.0"
    seeded = evo.seeds({"decision": {"rank": ["OR20_NOEMA|LOCK_LATE|T75|TR1.5", "OR30|LOCK_LIVE|T30|TR1.0",
                                              "CONT|LOCK_OFF|T45|TR0.6", "OR30|LOCK_LIVE|T45|TR1.0"]}})
    assert seeded == [(20, "crossing", "off", *evo.SHIPPED[3:13], "LOCK_LATE", 75, 0.5, 1.5), evo.SHIPPED]


def test_breeding_stays_inside_the_gene_pool_and_is_reproducible():
    rng = random.Random(1)
    a, b = evo.random_genome(rng), evo.random_genome(rng)
    child = evo.mutate(evo.crossover(a, b, rng), rng, force=True)
    assert all(value in evo.ALLELES[name] for name, value in zip(evo.NAMES, child))
    again = random.Random(1)
    a2, b2 = evo.random_genome(again), evo.random_genome(again)
    assert evo.mutate(evo.crossover(a2, b2, again), again, force=True) == child
    near = evo.neighbours(evo.SHIPPED)
    assert len(near) == sum(1 + (0 < alleles.index(v) < len(alleles) - 1)
                            for (_, alleles), v in zip(evo.GENES, evo.SHIPPED))
    assert all(sum(x != y for x, y in zip(n, evo.SHIPPED)) == 1 for n in near)
    assert 30 not in evo.ALLELES["time_stop"] and "crossing_or_pullback" not in evo.ALLELES["freshness"]


def _trade(day, pnl):
    return {"entry_time": f"{day}T10:00:00+05:30", "exit_time": f"{day}T11:00:00+05:30", "net_pnl": pnl,
            "lots_at_exit": 1, "exit_reason": "x"}


def test_fitness_needs_eight_trades_discounts_the_best_day_and_a_losing_half():
    days = ["2026-09-10", "2026-09-11", "2026-09-28", "2026-09-29"]
    few = [_trade("2026-09-10", 100)] * 4
    assert evo.fitness(few, days)[0] == pytest.approx(-5 + 4 / 8)
    trades = [_trade("2026-09-10", 3000), *[_trade("2026-09-11", -200)] * 3,
              *[_trade("2026-09-28", 500)] * 2, *[_trade("2026-09-29", -100)] * 2]
    value, metrics = evo.fitness(trades, days)
    # net 3,200; best day 3,000; drawdown 600 -> floor 1,000; both halves positive
    assert metrics["net_pnl"] == 3200 and metrics["halves"] == [2400, 800]
    assert value == pytest.approx((3200 - 3000) / 1000)
    losing_second_half = trades[:4] + [_trade("2026-09-28", -300)] * 4
    assert evo.fitness(losing_second_half, days)[0] == pytest.approx((1200 - 3000) / 1800 - 0.5)


def test_run_evolves_on_a_and_checks_finalists_on_b_once(tmp_path, monkeypatch):
    data = _write_dataset(tmp_path / "data")
    (tmp_path / "seeds.json").write_text(json.dumps({"decision": {
        "rank": ["OR30|LOCK_LIVE|T45|TR1.0", "OR20|LOCK_LATE|T75|TR1.5"], "recommended": "OR20|LOCK_LATE|T75|TR1.5"}}))
    day = (DAY.isoformat(), DAY.isoformat())
    monkeypatch.setattr(evo, "ROOT", tmp_path)
    monkeypatch.setattr(evo, "DATASET", "data")
    monkeypatch.setattr(evo, "SEEDS_FROM", "seeds.json")
    for name in ("FULL", "A", "B"):
        monkeypatch.setattr(evo, name, day)
    monkeypatch.setattr(evo, "A_HALVES", (day, day))
    monkeypatch.setattr(evo, "GA", {**evo.GA, "population": 4, "generations": 1, "elites": 1, "immigrants": 1,
                                     "finalists": 1})
    every_neighbour = evo.neighbours
    monkeypatch.setattr(evo, "neighbours", lambda genome: every_neighbour(genome)[:2])
    bound = {"sources": {}, "dataset": {"manifest_sha256": "e" * 64, "quote_days": [DAY.isoformat()]},
             "seeds_from_sha256": "s", "settings": {}}
    monkeypatch.setattr(evo, "_bound", lambda: bound)
    out = tmp_path / "evo"
    evo.freeze(out)
    assert len(json.loads((out / "freeze.json").read_text())["seed_genomes"]) == 2
    evo.run(out, jobs=1)
    results = json.loads((out / "results.json").read_text())
    assert results["decision"]["shipped_genome_equals_current_on_A"] is True
    assert results["decision"]["verdict"] == "NONE_PASSED_KEEP_SHIPPED"        # one session: too few trades
    assert evo.key(evo.SHIPPED) in results["holdout"] and results["history"][-1]["generation"] == 1
    with pytest.raises(SystemExit, match="exists"):
        evo.run(out, jobs=1)
