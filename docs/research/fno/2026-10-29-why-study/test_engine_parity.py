"""O29h parity: the engine's trend gate (fno_book) reads exactly the research's ADX side on every O29g session."""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
sys.path[:0] = [str(ROOT / "python-engine"), str(HERE)]

pytestmark = pytest.mark.skipif(not (ROOT / "docs/research/fno/2026-10-29-year-genome/_local/dataset-nifty").is_dir(),
                                reason="needs the local O29f dataset and Breeze daily bars")


def _sessions():
    frozen = json.loads((ROOT / "docs/research/fno/2026-10-29-year-genome/freeze.json").read_text())
    return frozen["bindings"]["year_sessions"]


def test_the_engine_gate_equals_the_research_side_on_every_session():
    import features as F
    import fno_book
    import lab_g
    daily = F.daily_bars()
    table = lab_g.table("year")
    checked = 0
    for s in _sessions():
        side = (table.get(s) or {}).get("side", {}).get("adx_abs25")
        if side is None:
            continue
        day = date.fromisoformat(s)
        value, _last = fno_book.daily_adx(daily, day)
        assert value == pytest.approx(table[s]["features"]["adx14"], rel=1e-12)
        assert fno_book.adx_side(value, 25.0) == side
        # live reads only the last 420 calendar days: the side does not change
        window = daily[daily.index.date >= day - timedelta(days=fno_book.ADX_HISTORY_CALENDAR_DAYS)]
        live_value, _ = fno_book.daily_adx(window, day)
        assert fno_book.adx_side(live_value, 25.0) == side and abs(live_value - value) < 0.01
        checked += 1
    assert checked >= 200
