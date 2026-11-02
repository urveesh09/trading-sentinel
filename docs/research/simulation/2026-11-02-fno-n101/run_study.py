"""Sequential child phases, two workers only, immutable command logs and real exit codes."""
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
    cli.add_argument("phase", choices=("controls", "annual", "carry"))
    cli.add_argument("--year", choices=("2023", "2024", "2025", "2026"))
    a = cli.parse_args()
    for year in ((a.year,) if a.year else ("2023", "2024", "2025", "2026")):
        log = HERE / "_local" / f"command-{a.phase}-{year}.log"
        assert not log.exists(), "retain original attempts"
        command = [sys.executable, str(HERE / "driver.py"), a.phase, "--jobs", "2"]
        started = time.monotonic()
        with log.open("w", encoding="utf-8") as output:
            child = subprocess.run(command, cwd=ROOT, env={**os.environ, "N08_YEAR": year}, stdout=output, stderr=subprocess.STDOUT)
        receipt = {"command": command, "year": year, "exit_code": child.returncode, "seconds": round(time.monotonic()-started, 2), "log": log.name}
        log.with_suffix(".json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(json.dumps(receipt), flush=True)
        if child.returncode:
            print(log.read_text()[-6000:], flush=True)
            raise SystemExit(child.returncode)


if __name__ == "__main__":
    main()
