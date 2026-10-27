"""O27h: the runtime shadow FNO_TREND_PULLBACK and its replay arm trade exactly as the O27f lab's FINAL pick."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab  # noqa: E402
import fno_policy_replay as replay  # noqa: E402

FINAL = {"family": "TREND_PULLBACK", "tp_trend": 1.5, "tp_side": 0.75, "tp_anchor": "VWAP", "tp_touch": 0.5,
         "tp_from": 690, "rvol": 0.0, "htf": "OFF", "xidx": "OFF", "window": "ALL", "stop_atr": 1.5, "target_r": 3.0,
         "exit": "RUN", "vwap_exit": "OFF", "delta": 0.55, "expiry": "NEAR"}
STUDY = lab.EVALS / f"{lab.digest(FINAL)}.json"
needs = pytest.mark.skipif(not ((lab.DATA / "manifest.json").is_file() and STUDY.is_file()),
                           reason="private read-only export or the O27f run outputs absent")
KEYS = ("bar_ts", "tradingsymbol", "direction", "entry_time", "entry_premium", "exit_time", "exit_premium",
        "exit_reason", "gross_pnl", "net_pnl")   # the lab kept no stop level; equal exits imply it


def test_the_replay_arm_carries_the_genome_exits():
    policy = replay.resolve_policy("FNO_SIG_TREND_PULLBACK")
    assert policy.signal_variant == "FNO_TREND_PULLBACK" and policy.manage_every_observation
    assert policy.exit_overrides == tuple(sorted(lab.EXITS[FINAL["exit"]].items()))


@needs
def test_replay_arm_reproduces_the_lab_trades_over_the_whole_archive():
    import run_fno_consistency_grid as grid
    lab.CACHE.mkdir(parents=True, exist_ok=True)
    data = grid.CachedReplayData(lab.DATA, lab.CACHE)
    shipped = replay.SingleLegReplay(data, replay.resolve_policy("FNO_SIG_TREND_PULLBACK")).run(*lab.FULL)
    study = json.loads(STUDY.read_text(encoding="utf-8"))["trades"]
    assert len(study) == 14 and round(sum(t["net_pnl"] for t in study), 2) == 17347.49
    assert [{k: t.get(k) for k in KEYS} for t in shipped["trades"]] == [{k: t.get(k) for k in KEYS} for t in study]
