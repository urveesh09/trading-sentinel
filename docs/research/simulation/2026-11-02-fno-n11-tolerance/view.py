"""Print any phase's books beside N11 and the earlier strategies, from saved replays only. A development view: it decides nothing."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-02-fno-n11"))
import screen_view as V  # noqa: E402

V.LOCAL = HERE / "_local"
YEARS = V.YEARS


def planned_over(rows, limit=5000.0):
    """How many entries planned to lose more than the limit at the 25% backstop."""
    return sum(1 for y in YEARS for t in rows[y] if t["entry_premium"] * 0.25 * t["entry_qty"] > limit)


def main(phase: str) -> None:
    print(f"{'book':<22}" + "".join(f"{y:>9}" for y in YEARS) + f"{'SUM':>10}{'wDay':>8}{'fall':>7}{'wTrade':>8}{'noTop5':>9}{'n':>5}{'2lot':>5}{'rais':>5}{'kid':>4}{'>5k':>5}")
    for name, rows in V.refs().items():
        print(V.line(name, rows))
    names = list(json.loads((V.LOCAL / f"keys-{phase}-{YEARS[0]}.json").read_text()))
    for name in names:
        rows = {y: V.load(V.LOCAL, phase, y, name)["trades"] for y in YEARS}
        print(V.line(name, rows) + f"{planned_over(rows):>5}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "screen")
