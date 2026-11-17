"""SN272 - calls before a weekday holiday, a post-hoc pick (PLAN.md amendment): SN259's variant (b), run alone through
the slot runner (DEV, its same-budget null, G4) with one exam run. Disclosed: chosen after SN259's DEV table was seen."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import slot  # noqa: E402
import sn259  # noqa: E402

if __name__ == "__main__":
    v = [x for x in sn259.VARIANTS if x["name"].startswith("(b)")]
    res = slot.evaluate("SN272", v, seed=272, notes=["post-hoc pick from SN259's DEV table (not SN259's max-min pick)"])
    slot.save(HERE / "results-sn272.json", res)
