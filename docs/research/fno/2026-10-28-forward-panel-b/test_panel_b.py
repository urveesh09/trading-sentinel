"""Panel B: every arm kind replays through the same book as its study (shipped, O27f lab, O27e lab)."""
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import panel_b  # noqa: E402

DATASET = panel_b.ROOT / "docs/research/fno/2026-10-27-consistency-grid/_local/dataset"
O27E_FULL = panel_b.ROOT / "docs/research/simulation/2026-10-27-fno-novel-families/_local/FULL/ed0d136bdd80ee89.json"
WINDOW = ("2026-09-10", "2026-09-30")
needs_data = pytest.mark.skipif(not (DATASET / "manifest.json").is_file(), reason="private read-only export absent")
KEYS = ("bar_ts", "tradingsymbol", "entry_time", "entry_premium", "exit_time", "exit_premium", "net_pnl")


def _first(trades, end):
    return [{k: t.get(k) for k in KEYS} for t in trades if t["entry_time"][:10] <= end]


@needs_data
def test_every_frozen_arm_replays_as_its_study(tmp_path):
    shipped = json.loads((panel_b.ROOT / "docs/research/fno/2026-10-27-consistency-grid/_local/arms/"
                                         "OR30__LOCK_LIVE__T45__TR1.0.json").read_text(encoding="utf-8"))["trades"]
    for arm, (kind, genome) in panel_b.PANEL.items():
        _, trades, _ = panel_b._replay((arm, kind, genome, str(DATASET), str(tmp_path), *WINDOW))
        if kind == "SHIPPED":
            assert _first(trades, WINDOW[1]) == _first(shipped, WINDOW[1])
        elif kind == "O27E" and O27E_FULL.is_file():
            study = json.loads(O27E_FULL.read_text(encoding="utf-8"))["trades"]
            assert _first(trades, WINDOW[1]) == _first(study, WINDOW[1])
        elif kind == "O27F":
            lab = panel_b._load(panel_b.O27F_LAB, "o27f_lab")
            study = json.loads((lab.EVALS / f"{lab.digest(genome)}.json").read_text(encoding="utf-8"))["trades"]
            assert _first(trades, WINDOW[1]) == _first(study, WINDOW[1])


def test_panel_is_frozen_before_the_window_and_matches_the_freeze():
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    assert frozen["frozen_at_utc"] < "2026-10-28T03:45:00"  # before the first forward session opens (09:15 IST)
    assert frozen["panel"] == {arm: {"kind": k, "genome": g} for arm, (k, g) in panel_b.PANEL.items()}
    assert frozen["window"] == ["2026-10-28", "2026-11-27"] and frozen["can_place_orders"] is False
    assert {k for k, _ in panel_b.PANEL.values()} == {"SHIPPED", "O27F", "O27E"}


def test_a_candidate_must_also_beat_the_random_entry_control():
    base = {"trades": 6, "net_pnl": 5000.0, "net_excluding_best_day": 1000.0, "max_drawdown": 1000.0}
    metrics = {arm: dict(base) for arm in panel_b.PANEL}
    metrics[panel_b.SHIPPED] = {**base, "net_pnl": 100.0}
    metrics[panel_b.NULL] = {**base, "net_pnl": 6000.0}
    decision = panel_b.decide(metrics, complete=True)
    assert decision["status"] == "FINAL"
    assert decision["arms"][panel_b.NULL] == {**decision["arms"][panel_b.NULL], "promising": False, "control": True}
    candidates = [arm for arm in panel_b.PANEL if arm not in (panel_b.SHIPPED, panel_b.NULL)]
    assert all(not decision["arms"][a]["promising"] and not decision["arms"][a]["checks"]["beats_null_control"]
               for a in candidates)
    metrics[panel_b.NULL]["net_pnl"] = 4000.0
    assert all(panel_b.decide(metrics, complete=False)["arms"][a]["promising"] for a in candidates)
