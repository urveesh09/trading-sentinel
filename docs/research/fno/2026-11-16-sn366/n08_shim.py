"""SN366: N08's lab with the 2022 / 2021L data points, without touching n08_lab.py on disk (N09.1's and N101's freezes hash
that file, and the frozen labs must keep passing their own checks).

install() reads simulation/2026-11-01-fno-n08/n08_lab.py, applies exactly three textual additions (the two allowed-year
tuples and the two POINTS entries below), asserts each anchor occurs once, and executes the result as the module
"n08_lab" with the original __file__, so every path inside it is unchanged. No rule, book, threshold or function differs.
Call install() before anything imports n08_lab (the chain's labs import it by name).
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

N08 = Path(__file__).resolve().parents[2] / "simulation" / "2026-11-01-fno-n08" / "n08_lab.py"
ANCHOR = '                 "daily": HERE.parent / "2026-10-31-fno-complements/_local/daily-2025.json"},\n}'
POINTS = '''                 "daily": HERE.parent / "2026-10-31-fno-complements/_local/daily-2025.json"},
    "2022": {"year": "2022", "dataset": FNO_STUDIES / "2026-11-16-sn366/_local/dataset-nifty-2022", "mirror": FNO_STUDIES / "2026-11-16-sn366/_local/mirror-2022.sqlite",
             "window": ("2022-01-01", "2022-12-31"), "cache": FNO_STUDIES / "2026-11-16-sn366/_local/observations-2022", "local": FNO_STUDIES / "2026-11-16-sn366/_local/y2022",
             "evals": FNO_STUDIES / "2026-11-16-sn366/_local/evals-2022", "daily": FNO_STUDIES / "2026-11-16-sn366/_local/daily-2022.json"},
    "2021L": {"year": "2021", "dataset": FNO_STUDIES / "2026-11-16-sn366/_local/dataset-nifty-2021L", "mirror": FNO_STUDIES / "2026-11-16-sn366/_local/mirror-2021L.sqlite",
              "window": ("2021-09-01", "2021-12-31"), "cache": FNO_STUDIES / "2026-11-16-sn366/_local/observations-2021L", "local": FNO_STUDIES / "2026-11-16-sn366/_local/y2021L",
              "evals": FNO_STUDIES / "2026-11-16-sn366/_local/evals-2021L", "daily": FNO_STUDIES / "2026-11-16-sn366/_local/daily-2021L.json"},
}'''
EDITS = (
    ('assert YEAR in ("2023", "2024", "2025", "2026", "TEST2025"), YEAR', 'assert YEAR in ("2023", "2024", "2025", "2026", "TEST2025", "2022", "2021L"), YEAR'),
    ('if YEAR in ("2023", "2024", "TEST2025"):', 'if YEAR in ("2023", "2024", "TEST2025", "2022", "2021L"):'),
    (ANCHOR, POINTS),
)


def install():
    if "n08_lab" in sys.modules:
        return sys.modules["n08_lab"]
    src = N08.read_text(encoding="utf-8")
    for old, new in EDITS:
        assert src.count(old) == 1, ("anchor", old[:60])
        src = src.replace(old, new)
    mod = types.ModuleType("n08_lab")
    mod.__file__ = str(N08)
    sys.modules["n08_lab"] = mod
    if str(N08.parent) not in sys.path:
        sys.path.insert(0, str(N08.parent))
    exec(compile(src, str(N08), "exec"), mod.__dict__)
    return mod
