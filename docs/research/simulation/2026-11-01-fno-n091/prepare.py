"""Pre-score source, old-receipt and cached-input bindings. No market replay."""
from __future__ import annotations
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())
LOCAL = HERE / "_local"
YEARS = ("2023", "2024", "2025", "2026")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not (HERE / "freeze.json").exists(), "never silently replace a freeze"
    LOCAL.mkdir(exist_ok=True)
    bindings = {}
    inputs = {}
    def add(path):
        rel = path.relative_to(ROOT).as_posix()
        inputs[rel] = {"path": rel, "sha256": sha(path)}
    for year in YEARS:
        env = {**os.environ, "N08_YEAR": year}
        subprocess.check_call([sys.executable, str(HERE / "driver.py"), "describe"], env=env, cwd=ROOT)
        path = LOCAL / f"bindings-{year}.json"
        bindings[year] = json.loads(path.read_text())
        add(path)
        cache = ROOT / bindings[year]["cache"]
        for item in sorted(cache.rglob("*")):
            if item.is_file():
                add(item)
        old = HERE.parent / "2026-11-01-fno-n09" / "_local"
        for keyfile in (old / f"keys-diag-{year}.json", old / f"keys-panel-{year}.json"):
            add(keyfile)
            names = ("N08", "DIAG") if "diag" in keyfile.name else ("CASH|S_VOL",)
            keys = json.loads(keyfile.read_text())
            for name in names:
                add(old / f"evals-{year}" / f"{keys[name]}.json")
    for path in (HERE.parent / "2026-11-01-fno-n08/_local/daily-2023.json", HERE.parent / "2026-10-31-fno-complements/_local/daily-2026.json",
                 HERE.parent / "2026-11-01-fno-n08/data-binding-2023.json", HERE.parent / "2026-11-01-fno-n09/results-stress.json"):
        add(path)
    tracked = subprocess.check_output(["git", "ls-files", "*.py"], cwd=ROOT).decode().splitlines()
    paths = {ROOT / p for p in tracked if (p.startswith("python-engine/") or p.startswith("docs/research/")) and "/_local/" not in p}
    paths.update(HERE.glob("*.py"))
    paths.add(HERE / "PLAN.md")
    sources = {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)}
    config = {"schema": "n091_config_v1", "as_of": "2026-11-01", "capital": 250000., "normalized_lot": 65,
              "primary": ["VOL_CLOCK", "CUSHION"], "all_data_seen": True, "rearm": False,
              "max_lots": 2, "full_premium_floor": "85% of closed high water, never lower, cash-backed",
              "bindings": bindings, "planned_annual_runs": 60,
              "fidelity": "BAR_LIFECYCLE", "market_coverage": "PARTIAL",
              "limits": ["modeled spreads/current fees/normalized lot", "52 previously clipped requests unrepaired", "no 2022 access", "no broker fills"]}
    (HERE / "configuration.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    sources[(HERE / "configuration.json").relative_to(ROOT).as_posix()] = sha(HERE / "configuration.json")
    freeze = {"schema": "n091_freeze_v1", "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
              "sources": sources, "inputs": list(inputs.values()), "all_data_seen": True,
              "primary_count": 2, "planned_annual_runs": 60,
              "qualification": "none; fixed-hypothesis seen-data research"}
    (HERE / "freeze.json").write_text(json.dumps(freeze, indent=2) + "\n", encoding="utf-8")
    print("FROZEN", len(sources), "sources", len(inputs), "cached inputs/receipts")


if __name__ == "__main__":
    main()
