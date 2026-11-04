"""Round 1 record: execution and fee economics with the shipped selection (development windows)."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from arms import run
out = {}
for panel, s, e in (("kite", "2025-07-01", "2026-09-30"), ("yahoo", "2023-01-01", "2026-10-30")):
    for model in ("E25", "E36", "PC", "E60"):
        for compound in (True, False):
            r = run(panel, s, e, ["BASE", "THREE_EQ", "TWO_EQ", "ONE_EQ", "TWO_RISK", "BASE_MIN5K", "BASE_PESS_PH"], model, compound=compound)
            out[f"{panel}|{model}|{'compound' if compound else 'fixed'}"] = {k: v["summary"] for k, v in r.items()}
(HERE / "results/round1.json").write_text(json.dumps(out, indent=1))
print(len(out), "tables")
