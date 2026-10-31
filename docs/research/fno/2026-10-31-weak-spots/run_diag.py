"""O31e diagnosis replays: the four strategies with and without the rule on every day, one lot, brakes off. Research only.

Every patch is at module level, because Windows workers re-import this script.

    python ../run_slice.py --env O30F_YEAR=2024 -- <folder>/run_diag.py        # the same with O30C_YEAR=2025, O30C_YEAR=2026
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
sys.path.insert(0, str(ROOT / "docs/research/fno/2026-10-31-final-book"))
import lab_o2 as O  # noqa: E402

S, Y, L, C = O.S, O.Y, O.L, O.C
LOCAL = HERE / "_local"
Y.EVALS = LOCAL / "evals-diag"


def main() -> None:
    books = {f"DIAG|{name}": O.X.book(f"DIAG|{name}", members=O.X.gated("ALWAYS"), cfg=dict(S.RAW), skip=skip, cost=False)
             for name, skip in (("rule", 0.5), ("none", None))}
    O.O27F.deny_network()
    table = C.table("year")
    with ProcessPoolExecutor(max_workers=6, initializer=L._init) as ex:
        runner = Y.Runner(ex, 6)
        runner.run(list(books.values()), source="year", window=C.WINDOW)
    L._atomic(LOCAL / f"keys-diag-{O.YEAR}.json", {n: Y.task_key(b, "year", C.WINDOW) for n, b in books.items()})
    keep = ("dmi_dir", "ema_dir", "open_drive", "or_width", "rv20", "trend_regime", "gap", "nr", "trend5", "prev_range_rel")
    L._atomic(LOCAL / f"table-{O.YEAR}.json", {d: {k: (r.get("side") or {}).get(k) for k in keep} for d, r in table.items()})
    print("DONE", O.YEAR, flush=True)


if __name__ == "__main__":
    main()
