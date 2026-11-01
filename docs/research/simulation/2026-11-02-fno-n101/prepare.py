"""Freeze all source, old evidence, cached prices and effective non-secret books BEFORE scoring."""
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
    assert not (HERE / "freeze.json").exists(), "preserve existing freeze"
    LOCAL.mkdir(exist_ok=True)
    bindings = {}
    old = HERE.parent / "2026-11-01-fno-n10" / "_local"
    old_manifest = json.loads((HERE.parent / "2026-11-01-fno-n091" / "freeze-v2.json").read_text())
    inputs = {r["path"]: r for r in old_manifest["inputs"]}
    def add(path):
        rel = path.relative_to(ROOT).as_posix()
        inputs[rel] = {"path": rel, "sha256": sha(path)}
    for year in YEARS:
        subprocess.check_call([sys.executable, str(HERE / "driver.py"), "describe"], cwd=ROOT, env={**os.environ, "N08_YEAR": year})
        path = LOCAL / f"binding-{year}.json"
        bindings[year] = json.loads(path.read_text())
        add(path)
        for local, phase, names in ((old, "panel2", ("R2_THIRD_CW", "R2_THIRD_CW|double")),
                                     (old, "strict-annual", ("STRICT",)),
                                     (HERE.parent / "2026-11-01-fno-n091" / "_local", "primary", ("CUSHION",))):
            path = local / f"keys-{phase}-{year}.json"
            add(path)
            keys = json.loads(path.read_text())
            for name in names:
                add(local / "evals" / f"{keys[name]}.json")
    for row in inputs.values():
        assert sha(ROOT / row["path"]) == row["sha256"], f"old input changed {row['path']}"
    tracked = subprocess.check_output(["git", "ls-files", "*.py"], cwd=ROOT).decode().splitlines()
    paths = {ROOT / p for p in tracked if (p.startswith("python-engine/") or p.startswith("docs/research/")) and "/_local/" not in p}
    paths.update(HERE.glob("*.py"))
    paths.add(HERE / "PLAN.md")
    # Snapshot actual settings after the same import graph used by every worker.
    sys.path.insert(0, str(HERE))
    import n101_lab as L
    from cost_schedules import options_cost_snapshot
    settings = {n: getattr(L.settings, n) for n in dir(L.settings) if n.startswith("FNO_") and
                not any(s in n for s in ("TOKEN", "KEY", "SECRET", "URL", "PASSWORD")) and
                isinstance(getattr(L.settings, n), (str, int, float, bool, type(None)))}
    configuration = {"schema": "n101_configuration_v1", "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
                     "as_of": "2026-11-02", "capital": 250000, "normalized_lot": 65, "all_data_seen": True,
                     "primary": list(L.NAMES), "executions": 80, "max_workers": 2, "settings": settings,
                     "fees": options_cost_snapshot("NFO"), "python": sys.version, "bindings": bindings,
                     "carry_costs": list(L.COSTS), "qualification": "none; 2022 not accessed"}
    L.X.write(HERE / "configuration.json", configuration)
    paths.add(HERE / "configuration.json")
    frozen = {"schema": "n101_freeze_v1", "base_commit": configuration["base_commit"],
              "sources": {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)},
              "inputs": list(inputs.values()), "all_data_seen": True, "planned_annuals": 80}
    L.X.write(HERE / "freeze.json", frozen)
    print("FROZEN", len(paths), "sources", len(inputs), "inputs", flush=True)


if __name__ == "__main__":
    main()
