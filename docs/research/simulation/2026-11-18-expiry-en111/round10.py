"""Round-10 path setup: round 9 (en96), round 8 (en86) and round 7 (en71) imported read-only, round 8's network denial."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
R9 = HERE.parent / "2026-11-18-expiry-en96"
if str(R9) not in sys.path:
    sys.path.insert(0, str(R9))
import round8  # noqa: E402,F401  (adds en86/en71, activates offline8)
