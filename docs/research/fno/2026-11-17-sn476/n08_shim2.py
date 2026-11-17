"""SN482: N08's lab with SN366's points (2022, 2021L) and this slot's (2020, 2021E), without touching n08_lab.py on disk (a copy
of SN366's n08_shim with two more POINTS entries and the two allowed-year tuples extended; nothing else differs).
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
    "2020": {"year": "2020", "dataset": FNO_STUDIES / "2026-11-17-sn476/_local/dataset-nifty-2020", "mirror": FNO_STUDIES / "2026-11-17-sn476/_local/mirror-2020.sqlite",
             "window": ("2020-01-01", "2020-12-31"), "cache": FNO_STUDIES / "2026-11-17-sn476/_local/observations-2020", "local": FNO_STUDIES / "2026-11-17-sn476/_local/y2020",
             "evals": FNO_STUDIES / "2026-11-17-sn476/_local/evals-2020", "daily": FNO_STUDIES / "2026-11-17-sn476/_local/daily-2020.json"},
    "2021E": {"year": "2021", "dataset": FNO_STUDIES / "2026-11-17-sn476/_local/dataset-nifty-2021E", "mirror": FNO_STUDIES / "2026-11-17-sn476/_local/mirror-2021E.sqlite",
              "window": ("2021-01-01", "2021-08-31"), "cache": FNO_STUDIES / "2026-11-17-sn476/_local/observations-2021E", "local": FNO_STUDIES / "2026-11-17-sn476/_local/y2021E",
              "evals": FNO_STUDIES / "2026-11-17-sn476/_local/evals-2021E", "daily": FNO_STUDIES / "2026-11-17-sn476/_local/daily-2021E.json"},
}'''
EDITS = (
    ('assert YEAR in ("2023", "2024", "2025", "2026", "TEST2025"), YEAR', 'assert YEAR in ("2023", "2024", "2025", "2026", "TEST2025", "2022", "2021L", "2020", "2021E"), YEAR'),
    ('if YEAR in ("2023", "2024", "TEST2025"):', 'if YEAR in ("2023", "2024", "TEST2025", "2022", "2021L", "2020", "2021E"):'),
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
