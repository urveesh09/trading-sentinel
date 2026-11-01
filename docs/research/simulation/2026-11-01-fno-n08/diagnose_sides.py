"""N08 diagnosis, step 3: the day's known readings for each development session. Seen years only; never opens 2023."""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
assert os.environ.get("N08_YEAR") in ("2024", "2025", "2026"), "this diagnosis never reads 2023"
import n08_lab as N  # noqa: E402
import sides_w as W  # noqa: E402

manifest = json.loads((N.Y.YEAR / "manifest.json").read_text(encoding="utf-8"))
days = manifest["sessions"]
sides = W.daily_sides(N.F.daily_bars(), days)
dte = W.dte_sides(days, manifest["option_expiries"])
out = {d: {**sides.get(d, {}), **dte.get(d, {})} for d in days}
N.X.write(N.LOCAL / f"sides-{N.YEAR}.json", out)
print(N.YEAR, len(out), list(next(iter(out.values())).keys()))
