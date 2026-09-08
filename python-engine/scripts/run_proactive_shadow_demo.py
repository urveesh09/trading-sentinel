"""Run the isolated Dev SHADOW demonstration and print its evidence JSON."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from proactive_demo import run_proactive_shadow_demo


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the deterministic offline proactive SHADOW demo")
    parser.add_argument("--db", required=True, help="New SQLite path for isolated synthetic evidence")
    args = parser.parse_args()
    path = Path(args.db).resolve()
    result = asyncio.run(run_proactive_shadow_demo(str(path)))
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
