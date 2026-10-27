"""O27g forward panel B (research only): the O27f FINAL pick and the O27e efficiency break replayed beside the
shipped book on every session from Oct 28 to Nov 27. Same export, cache, metrics and rule as panel A (O27c).

python docs/research/fno/2026-10-28-forward-panel-b/panel_b.py freeze
python docs/research/fno/2026-10-28-forward-panel-b/panel_b.py run [--jobs 3]

Neither candidate is traded. Each run takes a fresh read-only export of the Production research archive (panel A's
exporter, ``--include-finished-today``), replays every arm from the window's first session to the newest exported
one, and writes ``_local/latest.json``, ``_local/REPORT.md`` and a line in ``_local/history.jsonl``.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
sys.path[:0] = [str(ROOT / "python-engine"), str(ROOT / "scripts")]
import fno_policy_replay as replay  # noqa: E402
import run_fno_consistency_grid as grid  # noqa: E402
import run_fno_forward_panel as panel_a  # noqa: E402

O27F_LAB = ROOT / "docs/research/fno/2026-10-27-genome-round3/lab.py"
O27E_LAB = ROOT / "docs/research/simulation/2026-10-27-fno-novel-families/lab.py"
SOURCES = (*panel_a.SOURCES, "docs/research/fno/2026-10-27-genome-round3/lab.py",
           "docs/research/simulation/2026-10-27-fno-novel-families/lab.py",
           "docs/research/fno/2026-10-28-forward-panel-b/panel_b.py")
START, END = panel_a.START, panel_a.END
SHIPPED = "SHIPPED"

NULL = "NULL_CONTROL"
# Arm -> (kind, genome). Provenance: README (O27f results.json, O27e selection), frozen before Oct 28.
PANEL: dict = {
    SHIPPED: ("SHIPPED", None),
    # O27f FINAL pick (frozen rule: best plateau of the five best fitness genomes over all 29 seen sessions)
    "O27F_TREND_PULLBACK": ("O27F", {
        "family": "TREND_PULLBACK", "tp_trend": 1.5, "tp_side": 0.75, "tp_anchor": "VWAP", "tp_touch": 0.5,
        "tp_from": 690, "rvol": 0.0, "htf": "OFF", "xidx": "OFF", "window": "ALL", "stop_atr": 1.5, "target_r": 3.0,
        "exit": "RUN", "vwap_exit": "OFF", "delta": 0.55, "expiry": "NEAR"}),
    # O27f best fitness over all 29 sessions (a different family; its plateau is lower)
    "O27F_ENSEMBLE_EFF_MOMO": ("O27F", {
        "family": "ENSEMBLE", "en_members": ["EFF", "MOMO"], "en_k": 2, "en_window": 3, "rvol": 0.8, "htf": "OFF",
        "xidx": "OFF", "window": "AM", "stop_atr": 2.0, "target_r": 2.4, "exit": "LOOSE", "vwap_exit": "OFF",
        "delta": 0.55, "expiry": "NEAR"}),
    # O27e efficiency break finalist (selected on Sep 10 - Oct 9 by the O27e study; never forward-tested)
    "O27E_EFFICIENCY_BREAK": ("O27E", {
        "family": "EFFICIENCY_BREAK", "lookback": 4, "efficiency": 0.35, "buffer": 0.2, "body": 0.55, "vwap": False,
        "compression": 3.0, "rvol": 1.2, "stop": 2.0, "target": 1.8, "exit": "LOOSE"}),
    # Control: the O27f NULL track's FINAL pick - random entries chosen by the same search. A candidate that cannot
    # beat it forward has shown no entry skill.
    NULL: ("O27F", {
        "family": "NULL_RANDOM", "nr_p": 0.04, "nr_seed": 3, "rvol": 0.8, "htf": "WITH", "xidx": "OFF",
        "window": "PM", "stop_atr": 2.0, "target_r": 1.8, "exit": "LATE", "vwap_exit": "ON", "delta": 0.55,
        "expiry": "NEAR"}),
}
RULE = {**panel_a.RULE, "panel": "B (O27g): O27f picks and the O27e efficiency break, with a random-entry control",
        "promising": panel_a.RULE["promising"] + ", and net > NULL_CONTROL net (the random-entry control)"}


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _bound() -> dict:
    return {"sources": {rel: grid._sha(ROOT / rel) for rel in SOURCES}, "fno_settings_sha256": panel_a._settings_hash()}


def freeze() -> None:
    grid._write_new(HERE / "freeze.json", {
        "schema": "fno_forward_panel_b_freeze_v1", "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "bound": _bound(), "window": [START, END], "rule": RULE,
        "panel": {arm: {"kind": kind, "genome": genome} for arm, (kind, genome) in PANEL.items()},
        "export": {"volume": panel_a.VOLUME, "image": panel_a.IMAGE, "mode": "read-only throwaway container"},
        "can_place_orders": False, "qualification": "NOT_ASSESSED"})
    print("frozen forward panel B:", HERE / "freeze.json")


def _replay(task: tuple):
    arm, kind, genome, folder, cache, start, end = task
    data = panel_a.SessionCache(Path(folder), Path(cache))
    if kind == "SHIPPED":
        result = replay.SingleLegReplay(data, replay.resolve_policy("CURRENT")).run(start, end)
    elif kind == "O27F":
        lab = _load(O27F_LAB, "o27f_lab")
        lab.DATA = Path(folder)  # the SENSEX confirmation reads the same export
        result = lab.LabReplay(data, lab.policy_for(genome), genome).run(start, end)
    elif kind == "O27E":
        o27e = _load(O27E_LAB, "o27e_lab")
        with o27e.research_dispatch():
            result = replay.SingleLegReplay(data, o27e.policy(genome)).run(start, end)
    else:
        raise ValueError(kind)
    notes = {k: v for k, v in result["notes"].items() if not k.startswith(("regime_", "grid_"))}
    return arm, result["trades"], notes


def decide(metrics: dict, complete: bool) -> dict:
    """Panel A's frozen checks over this panel's arms, plus: beat the random-entry control."""
    saved = panel_a.PANEL
    panel_a.PANEL = {arm: None for arm in PANEL}
    try:
        decision = panel_a.decide(metrics, complete=complete)
    finally:
        panel_a.PANEL = saved
    for arm, verdict in decision["arms"].items():
        if arm == NULL:
            verdict["promising"] = False
            verdict["control"] = True
            continue
        verdict["checks"]["beats_null_control"] = metrics[arm]["net_pnl"] > metrics[NULL]["net_pnl"]
        verdict["promising"] = all(verdict["checks"].values())
    return decision


def run(jobs: int) -> dict:
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    if frozen["bound"] != _bound():
        raise SystemExit("bound inputs changed since freeze; refusing to run (sources or effective F&O settings)")
    if {arm: {"kind": k, "genome": g} for arm, (k, g) in PANEL.items()} != frozen["panel"]:
        raise SystemExit("panel differs from the frozen panel; refusing to run")
    local = HERE / "_local"
    exports, cache = local / "exports", local / "observations"
    cache.mkdir(parents=True, exist_ok=True)
    folder = exports / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    panel_a._export(folder)
    manifest = panel_a._verify(folder)
    sessions = [d for d in manifest["quote_days"] if START <= d <= END]
    ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    state = {"schema": "fno_forward_panel_b_state_v1", "ran_at_ist": ist_now.strftime("%Y-%m-%d %H:%M"),
             "window": [START, END], "export": folder.name, "sessions": sessions,
             "unsealed": [d for d in manifest.get("unsealed_days", []) if d in sessions],
             "freeze_sha256": grid._sha(HERE / "freeze.json")}
    if sessions:
        tasks = [(arm, kind, genome, str(folder), str(cache), START, sessions[-1])
                 for arm, (kind, genome) in PANEL.items()]
        with ProcessPoolExecutor(max_workers=max(1, jobs)) as pool:
            results = list(pool.map(_replay, tasks))
        state["metrics"] = {arm: panel_a.forward_metrics(trades, sessions) for arm, trades, _ in results}
        state["unresolved"] = {arm: state["metrics"][arm]["unresolved"] for arm, _, _ in results}
        state["notes"] = {arm: notes for arm, _, notes in results}
        state["trades"] = {arm: trades for arm, trades, _ in results}
        complete = sessions[-1] >= END or ist_now.date().isoformat() > END
        state["decision"] = decide(state["metrics"], complete)
    if frozen["bound"] != _bound():
        raise SystemExit("bound inputs changed during the run; refusing results")
    (local / "latest.json").write_text(json.dumps(state, indent=1, default=str), encoding="utf-8")
    report = panel_a._report(state).replace("# F&O forward panel", "# F&O forward panel B (O27g)", 1)
    report = "\n".join(line.replace("| not yet |", "| random-entry control |") if line.startswith(f"| {NULL} |")
                       else line for line in report.split("\n")).replace(panel_a.RULE["promising"], RULE["promising"])
    (local / "REPORT.md").write_text(report, encoding="utf-8")
    with (local / "history.jsonl").open("a", encoding="utf-8") as history:
        history.write(json.dumps({"ran_at_ist": state["ran_at_ist"], "sessions": len(sessions),
                                  "net": {arm: m["net_pnl"] for arm, m in state.get("metrics", {}).items()},
                                  "status": state.get("decision", {}).get("status")}) + "\n")
    for old in sorted(p for p in exports.iterdir() if p.is_dir() and p.name != folder.name):
        shutil.rmtree(old)
    print(f"forward panel B: {len(sessions)} session(s); report {local / 'REPORT.md'}")
    return state


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("action", choices=("freeze", "run"))
    cli.add_argument("--jobs", type=int, default=3)
    args = cli.parse_args()
    freeze() if args.action == "freeze" else run(args.jobs)
