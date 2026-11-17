"""EN series base: imports the round-8 lab unchanged and defines the E03.2 control exactly as frozen
(2026-11-03-expiry-round8/final_checks.py: replace(E031, put_mult=2, chase=.08, flat=914)).
NIFTY 2024 + 2025 expiry chains are SEEN (in-sample). NIFTY 2023 is never read here."""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-03-expiry-round8"))
import r8b_lab as R  # noqa: E402
L, X, E = R.L, R.X, R.E
E032 = replace(R.E031, put_mult=2., chase=.08, flat=914)
_T = {}
def tapes():
    if not _T:
        T = L.tapes()
        for y, ts in T.items():
            assert all(t.day.startswith(str(y)) for t in ts) and y in (2024, 2025)
        _T.update(T)
    return _T
