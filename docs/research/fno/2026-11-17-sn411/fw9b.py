"""SN411 A: fw9a on fw7c (frozen Nov 17, 2026, before any forward P&L). fw9a's rule exactly (fresh IV, the previous
exchange session, ROLL block, the verdict trigger) with each session's trade taken from fw7c.session instead of
fw7b.session; written to results-sn411-fw9b.json and published with fw9 / fw9a.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "2026-11-17-sn396"))
import fw7c  # noqa: E402
import fw9a  # noqa: E402

fw9a.OUT = HERE / "results-sn411-fw9b.json"
fw9a.fw7b = types.SimpleNamespace(session=fw7c.session)      # the only change: fw7c's trade


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verdict":
        fw9a.verdict()
    else:
        raise SystemExit("usage: fw9b.py verdict")
