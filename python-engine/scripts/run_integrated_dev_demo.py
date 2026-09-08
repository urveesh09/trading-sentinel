"""Write the deterministic integrated Dev evidence artifact to a fresh directory."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integrated_dev_demo import run_integrated_dev_demo


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", help="new directory for isolated SQLite fixture evidence")
    args = parser.parse_args()
    result = asyncio.run(run_integrated_dev_demo(args.output_dir))
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
