"""Bounded sequential orchestration; the pool inside each child has <=3 workers."""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("phase", choices=("controls", "primary", "costs", "carry"))
    cli.add_argument("--year", choices=("2023", "2024", "2025", "2026"))
    a = cli.parse_args()
    for year in ((a.year,) if a.year else ("2023", "2024", "2025", "2026")):
        command = [sys.executable, str(HERE / "driver.py"), a.phase, "--jobs", "3"]
        started = time.monotonic()
        log = HERE / "_local" / f"command-{a.phase}-{year}.log"
        assert not log.exists(), f"preserve earlier attempts: {log}"
        with log.open("w", encoding="utf-8") as output:
            child = subprocess.run(command, cwd=ROOT, env={**os.environ, "N08_YEAR": year}, stdout=output, stderr=subprocess.STDOUT)
        receipt = {"command": command, "env": {"N08_YEAR": year}, "exit_code": child.returncode,
                   "seconds": round(time.monotonic() - started, 2), "log": str(log.relative_to(HERE))}
        (log.with_suffix(".json")).write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(a.phase, year, receipt["exit_code"], receipt["seconds"], flush=True)
        if child.returncode:
            print(log.read_text(encoding="utf-8")[-7000:], flush=True)
            raise SystemExit(child.returncode)


if __name__ == "__main__":
    main()
