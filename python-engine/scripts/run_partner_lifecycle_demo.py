"""Run the isolated partner fixture lifecycle demo and print evidence JSON."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from partner_lifecycle_demo import run_partner_lifecycle_demo


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Dev-only partner fixture lifecycle demonstration")
    parser.add_argument("--db", required=True, help="New SQLite path for isolated synthetic evidence")
    args = parser.parse_args()
    result = asyncio.run(run_partner_lifecycle_demo(str(Path(args.db).resolve())))
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
