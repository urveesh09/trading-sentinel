"""O29b checks: the filters read only closed bars, the fades only closed bars, the November contract, and parity: on
the 29 sessions O28 replayed, this study's book reproduces O28's SHIPPED and UNION paths exactly."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("o29b_study", HERE / "study.py")
study = importlib.util.module_from_spec(spec)
sys.modules["o29b_study"] = study
spec.loader.exec_module(study)
router = study.router

READY = (study.DATA / "manifest.json").is_file() and study.SIGNALS.is_file()
O28_RAW = router.LOCAL / "results-raw.json"


def test_filters_read_as_declared():
    s = {"er": 0.25, "failed": True, "vx": 2, "used": 0.9, "drive": "LOW"}
    assert study.gate_ok("ALWAYS", None) and not study.gate_ok("NEVER", s) and not study.gate_ok("nofail", None)
    assert [study.gate_ok(r, s) for r in ("drive:HIGH", "drive:LOW", "nofail", "er:0.2", "er:0.3", "erlt:0.3",
                                          "vx:3", "vx:2", "used:0.8", "nofail+er:0.2")] == [
        False, True, False, True, False, True, True, False, False, False]
    assert study.gate_ok("used:0.8", {**s, "used": None}) is False


@pytest.mark.skipif(not READY, reason="study data not prepared on this machine")
def test_the_day_state_at_a_bar_reads_only_that_bar_and_earlier():
    bars = study.futures_bars()
    full = study.bar_states(bars)
    for day, cut in (("2026-10-28", "2026-10-28 10:20:00"), ("2026-10-08", "2026-10-08 11:00:00")):
        cut_at = study.pd.Timestamp(cut)
        short = study.bar_states({t: f[f.index <= cut_at] for t, f in bars.items()})
        assert short[day] == {k: v for k, v in full[day].items() if k <= cut}
    # Oct 28: up through the opening range at 09:45, back inside by 09:55, so "failed" from then on.
    states = full["2026-10-28"]
    assert not states["2026-10-28 09:45:00"]["failed"] and states["2026-10-28 10:20:00"]["failed"]
    assert states["2026-10-28 09:15:00"]["drive"] == "LOW"


@pytest.mark.skipif(not READY, reason="study data not prepared on this machine")
def test_a_fade_at_a_bar_is_the_same_with_the_later_bars_cut_off():
    data = study.grid.CachedReplayData(study.DATA, study.CACHE)
    frame = data.futures_frame(15736578, study.date(2026, 10, 28))     # what the replay hands the signal
    g = study.fade_genomes()[0]
    full = study.fade_table(g, study.O27F.day_features(frame, study.date(2026, 10, 28)))
    for stamp in list(full)[:3]:
        cut = frame[frame.index <= study.pd.Timestamp(stamp)]
        assert study.fade_table(g, study.O27F.day_features(cut, study.date(2026, 10, 28))).get(stamp) == full[stamp]


@pytest.mark.skipif(not READY, reason="study data not prepared on this machine")
def test_the_front_future_from_oct_28_is_the_november_contract():
    obs, _ = study.grid.CachedReplayData(study.DATA, study.CACHE).observations(study.TODAY)
    assert (obs[0].future.contract.token, str(obs[0].future.contract.expiry)) == (15736578, "2026-11-23")
    assert router.front_token(study.date(2026, 10, 28)) == 15736578


@pytest.mark.skipif(not (READY and O28_RAW.is_file()), reason="O28 results not on this machine")
def test_the_book_reproduces_o28_on_its_29_sessions():
    raw = json.loads(O28_RAW.read_text(encoding="utf-8"))
    study._worker_init()
    keys = (*router.PARITY_KEYS, "component")
    for mine, theirs in ((study.UNION, router.UNION), (study.single("SHIPPED"), router.single("SHIPPED", "ALWAYS"))):
        with router.dispatch():
            book = study.ChopReplay(study._DATA, mine, study._STATES, study._MEMO)
            got = book.run(*router.FULL)["trades"]
        want = raw["trades"][router.digest(theirs)]
        assert [{k: t.get(k) for k in keys} for t in got] == [{k: t.get(k) for k in keys} for t in want]
        assert book.notes.get("memo_miss", 0) == 0
