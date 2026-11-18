"""Round-9 path setup: round-8 (en86) and round-7 (en71) modules are imported read-only, with round 8's offline guard."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
R8 = HERE.parent / "2026-11-18-expiry-en86"
R7 = HERE.parent / "2026-11-18-expiry-en71"
for p in (R7, R8):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import offline8  # noqa: E402,F401  process-scoped network denial
