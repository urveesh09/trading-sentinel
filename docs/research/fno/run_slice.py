"""Run one research command for a bounded foreground slice, then stop it and its worker processes cleanly.

    python-engine\\winvenv\\Scripts\\python.exe docs\\research\\fno\\run_slice.py --seconds 540 --env O30C_YEAR=2025 ^
        --log docs\\research\\fno\\<study>\\_local\\run-2025.log -- docs\\research\\fno\\<study>\\lab_x.py run --jobs 4

The year-data studies save every replay to its own file as it finishes, so repeated slices add up to one complete
run with identical results. Use it when a shell limits command time or stops idle background jobs (Claude Code: 10
minutes per command; its memory guard ends idle background shells). Workers are the study's own --jobs: 4 during
market hours (09:00-15:45 IST), up to 6 after. Prints a one-line JSON summary and the log's last lines of interest.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "python-engine/fno_policy_replay.py").is_file())
PY = ROOT / "python-engine/winvenv/Scripts/python.exe"
IST = timezone(timedelta(hours=5, minutes=30))
KEYS = ("DONE", "reused", "warm", "Traceback", "Error", "assert", "STOPPED")


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("--seconds", type=int, default=540)
    cli.add_argument("--env", action="append", default=[], help="NAME=VALUE for the child (repeatable)")
    cli.add_argument("--log", type=Path, default=None)
    cli.add_argument("command", nargs=argparse.REMAINDER, help="-- then the script and its arguments")
    a = cli.parse_args()
    command = a.command[1:] if a.command[:1] == ["--"] else a.command
    if not command:
        raise SystemExit("give the command after --")
    env = {**os.environ, **dict(item.split("=", 1) for item in a.env)}
    log_path = a.log or ROOT / "docs/research/fno/_slice.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(IST)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"--- slice {started:%Y-%m-%d %H:%M:%S} IST: {' '.join(command)}\n")
        log.flush()
        proc = subprocess.Popen([str(PY), "-u", *command], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env)
        deadline = time.time() + a.seconds
        while time.time() < deadline and proc.poll() is None:
            time.sleep(2)
        finished = proc.poll() is not None
        if not finished:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
            proc.wait(timeout=60)
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = [s.strip() for s in lines if any(k in s for k in KEYS) and "regime_transition" not in s][-5:]
    print(json.dumps({"finished": finished, "returncode": proc.returncode, "seconds": round(time.time() -
                      started.timestamp()), "log": str(log_path), "last": tail}, indent=1))


if __name__ == "__main__":
    main()
