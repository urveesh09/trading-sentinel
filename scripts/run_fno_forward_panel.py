"""Forward-only panel: the best O27/O27b candidates replayed beside the shipped book on sessions after the freeze
(research only, O27c).

python scripts/run_fno_forward_panel.py freeze --out <study folder>
python scripts/run_fno_forward_panel.py run --out <study folder> [--jobs 3]

The owner's call (Oct 27): "integrate the best … test this in the upcoming month". No candidate passed a held-out
check on the 29 archived sessions, so they are not traded; each day they are replayed through the whole live book
(fno_policy_replay) on the newest sessions, which no study has seen. ``freeze`` binds the panel, the forward window,
the decision rule, the sources and the effective F&O settings before the first forward session exists. Each ``run``:

1. takes a fresh read-only export of the Production research archive (a throwaway container, the data volume
   mounted read-only, ``scripts/export_fno_replay_dataset.py --include-finished-today``: from 15:50 IST the day's
   own finished session is included) into ``_local/exports/<stamp>/``;
2. replays every panel arm from the window's first session to the newest exported one (parsed sessions cached per
   session content);
3. writes ``_local/latest.json``, ``_local/REPORT.md`` and a line in ``_local/history.jsonl``, and keeps only the
   newest export.

Interim reports are provisional; the frozen rule is read once the window has ended. No broker, order or Production
write; Production's own paper and live books are untouched.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import pickle
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-engine"))
sys.path.insert(0, str(ROOT / "scripts"))
import run_fno_consistency_grid as grid  # noqa: E402
import run_fno_evolution as evo  # noqa: E402
from fno_policy_replay import ReplayData, run_replay  # noqa: E402

SOURCES = evo.SOURCES + ("scripts/run_fno_forward_panel.py", "scripts/export_fno_replay_dataset.py")
START, END = "2026-10-28", "2026-11-27"
VOLUME = "production_trading-sentinel_trading_data"
IMAGE = "production_trading-sentinel-python-engine:latest"
SHIPPED = "SHIPPED"

# Arm -> genome (run_fno_evolution.GENES order). Provenance in the study README; tests tie each to its source.
PANEL = {
    SHIPPED: evo.SHIPPED,
    # O27b evolution finalist 1 by plateau: OR20, buffer 0.4, width <= 1.25x, stop 1.0 ATR, lock off, T75, trail 1.5
    "EVO_PLATEAU_1": (20, "crossing", "ema_21_50", 0.4, 1.2, False, None, False, 1.25, None, 885, 1.0, 1.8,
                      "LOCK_OFF", 75, 0.5, 1.5),
    # O27b best fitness (9.53): OR30, buffer 0.4, RVOL 1.0, with the gap, width <= 1.25x, lock off, T75, trail 1.5
    "EVO_BEST_FITNESS": (30, "crossing", "ema_21_50", 0.4, 1.0, False, None, True, 1.25, None, 885, 1.5, 1.8,
                         "LOCK_OFF", 75, 0.5, 1.5),
    # O27b finalists 4-5: OR20 with the let-it-run exits (lock off, T75 needing 0.25R, trail 1.5)
    "EVO_OR20_LET_RUN": (20, "crossing", "ema_21_50", 0.25, 1.2, False, None, False, None, None, 885, 1.5, 1.8,
                         "LOCK_OFF", 75, 0.25, 1.5),
    # O27 frozen pick: OR20|LOCK_LATE|T75|TR1.5
    "O27_PICK": (20, "crossing", "ema_21_50", 0.25, 1.2, False, None, False, None, None, 885, 1.5, 1.8,
                 "LOCK_LATE", 75, 0.5, 1.5),
    # O27 post hoc, regime-agnostic entry: OR20_NOEMA|LOCK_LATE|T75|TR1.5
    "O27_OR20_NOEMA": (20, "crossing", "off", 0.25, 1.2, False, None, False, None, None, 885, 1.5, 1.8,
                       "LOCK_LATE", 75, 0.5, 1.5),
}
RULE = {
    "window": [START, END],
    "promising": "forward trades >= 5, net > 0, net excluding its best day > 0, net > SHIPPED net, max drawdown <= "
                 "max(1.5 x SHIPPED max drawdown, 5000)",
    "min_trades": 5, "drawdown_floor": 5000,
    "interim": "reports before the window ends are provisional; nothing is promoted or stopped early on them",
    "if_promising": "the owner's call, through the normal Dev -> GitHub -> Production flow; never during a "
                    "proving week, and the real-money test keeps mirroring the paper book until the owner says",
}


def _settings_hash() -> str:
    from config import settings
    snapshot = {k: repr(v) for k, v in sorted(settings.model_dump().items()) if k.startswith("FNO_")}
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()


def _bound() -> dict:
    return {"sources": {rel: grid._sha(ROOT / rel) for rel in SOURCES}, "fno_settings_sha256": _settings_hash()}


def freeze(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    grid._write_new(out / "freeze.json", {
        "schema": "fno_forward_panel_freeze_v1", "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "bound": _bound(), "window": [START, END], "rule": RULE, "genes": evo.NAMES,
        "panel": {arm: {"genome": list(genome), "key": evo.key(genome)} for arm, genome in PANEL.items()},
        "export": {"volume": VOLUME, "image": IMAGE, "mode": "read-only throwaway container"},
        "can_place_orders": False, "qualification": "NOT_ASSESSED"})
    print("frozen forward panel:", out / "freeze.json")


def _export(folder: Path) -> None:
    folder.mkdir(parents=True)
    scripts = (ROOT / "scripts").resolve().as_posix()
    subprocess.run(["docker", "run", "--rm", "--memory", "1g", "-v", f"{VOLUME}:/data:ro",
                    "-v", f"{folder.resolve().as_posix()}:/out", "-v", f"{scripts}:/scripts:ro",
                    "--entrypoint", "python", IMAGE, "/scripts/export_fno_replay_dataset.py", "--data", "/data",
                    "--out", "/out", "--include-finished-today"], check=True, capture_output=True, text=True,
                   timeout=1800)


def _verify(folder: Path) -> dict:
    """Every exported file re-hashed; a finished but not yet sealed session (the newest) is accepted."""
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    for rel, digest in manifest["files_sha256"].items():
        if grid._sha(folder / rel) != digest:
            raise SystemExit(f"exported file changed: {rel}")
    return manifest


class SessionCache(ReplayData):
    """Parsed sessions pickled per session content (a session re-exported after sealing is parsed again)."""

    def __init__(self, root: Path, cache: Path):
        super().__init__(root)
        self.cache = cache

    def observations(self, day: str):
        files = sorted((k, v) for k, v in self.manifest["files_sha256"].items() if k.startswith(f"quotes/{day}/"))
        path = self.cache / f"{day}-{hashlib.sha256(json.dumps(files).encode()).hexdigest()[:12]}.pkl"
        if path.is_file():
            return pickle.loads(path.read_bytes())
        parsed = super().observations(day)
        part = path.with_name(path.name + f".{os.getpid()}.part")
        part.write_bytes(pickle.dumps(parsed, protocol=pickle.HIGHEST_PROTOCOL))
        os.replace(part, path)
        return parsed


def _replay(task: tuple) -> tuple[str, list[dict], dict]:
    arm, genome, folder, cache, start, end = task
    data = SessionCache(Path(folder), Path(cache))
    result = run_replay(folder, start=start, end=end, policy=evo.policy(tuple(genome)), data=data)
    return arm, result["trades"], {k: v for k, v in result["notes"].items() if not k.startswith(("regime_", "grid_"))}


def forward_metrics(trades: list[dict], sessions: list[str]) -> dict:
    m = grid.window_metrics(trades, sessions)
    by_day: dict = defaultdict(float)
    for t in trades:
        if "net_pnl" in t and t["entry_time"][:10] in sessions:
            by_day[t["entry_time"][:10]] += t["net_pnl"]
    m["net_excluding_best_day"] = round(m["net_pnl"] - max(max(by_day.values(), default=0.0), 0.0), 2)
    m["by_day"] = {d: round(by_day.get(d, 0.0), 2) for d in sessions}
    return m


def decide(metrics: dict, complete: bool) -> dict:
    ship = metrics[SHIPPED]
    limit = max(1.5 * ship["max_drawdown"], RULE["drawdown_floor"])
    arms = {}
    for arm in PANEL:
        if arm == SHIPPED:
            continue
        m = metrics[arm]
        checks = {"trades_ge_5": m["trades"] >= RULE["min_trades"], "net_gt_0": m["net_pnl"] > 0,
                  "net_excluding_best_day_gt_0": m["net_excluding_best_day"] > 0,
                  "beats_shipped": m["net_pnl"] > ship["net_pnl"], "drawdown_within": m["max_drawdown"] <= limit}
        arms[arm] = {"checks": checks, "promising": all(checks.values())}
    return {"status": "FINAL" if complete else "PROVISIONAL", "drawdown_limit": round(limit, 2), "arms": arms,
            "qualification": "NOT_ASSESSED"}


def _report(state: dict) -> str:
    days = state["sessions"]
    status = state["decision"]["status"] if state.get("decision") else "NO SESSIONS YET"
    lines = [f"# F&O forward panel — {state['window'][0]} to {state['window'][1]}", "",
             f"Updated {state['ran_at_ist']} IST. Sessions replayed: {len(days)}"
             + (f" ({days[0]} … {days[-1]})" if days else "") + f". Status: **{status}**. "
             "Research only: none of these arms trades; Production's books are unchanged.", ""]
    if not state["sessions"]:
        return "\n".join(lines + ["No forward session exported yet.", ""])
    lines += ["| Arm | Trades | Net ₹ | Net without best day ₹ | Max DD ₹ | Days traded | Green / red days "
              "| Promising? |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for arm, m in state["metrics"].items():
        verdict = "control" if arm == SHIPPED else (
            "yes" if state["decision"]["arms"][arm]["promising"] else "not yet")
        lines.append(f"| {arm} | {m['trades']} | {m['net_pnl']:,.0f} | {m['net_excluding_best_day']:,.0f} | "
                     f"{m['max_drawdown']:,.0f} | {m['trade_days']} | {m['green_days']} / {m['red_days']} "
                     f"| {verdict} |")
    lines += ["", "Daily net ₹ (entry day):", "", "| Day | " + " | ".join(state["metrics"]) + " |",
              "| --- |" + " --- |" * len(state["metrics"])]
    for day in state["sessions"]:
        lines.append(f"| {day} | " + " | ".join(f"{m['by_day'][day]:,.0f}" for m in state["metrics"].values()) + " |")
    unpriced = {arm: n for arm, n in state["unresolved"].items() if n}
    if unpriced:
        lines += ["", f"Unpriced holds (outside the archived strikes): {unpriced}."]
    lines += ["", f"Rule (frozen): {RULE['promising']}. {RULE['interim']}.", ""]
    return "\n".join(lines)


def run(out: Path, jobs: int) -> dict:
    frozen = json.loads((out / "freeze.json").read_text(encoding="utf-8"))
    if frozen["bound"] != _bound():
        raise SystemExit("bound inputs changed since freeze; refusing to run (sources or effective F&O settings)")
    if {arm: list(g) for arm, g in PANEL.items()} != {arm: v["genome"] for arm, v in frozen["panel"].items()}:
        raise SystemExit("panel differs from the frozen panel; refusing to run")
    local = out / "_local"
    exports, cache = local / "exports", local / "observations"
    cache.mkdir(parents=True, exist_ok=True)
    folder = exports / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    _export(folder)
    manifest = _verify(folder)
    sessions = [d for d in manifest["quote_days"] if START <= d <= END]
    ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    state = {"schema": "fno_forward_panel_state_v1", "ran_at_ist": ist_now.strftime("%Y-%m-%d %H:%M"),
             "window": [START, END], "export": folder.name, "sessions": sessions,
             "unsealed": [d for d in manifest.get("unsealed_days", []) if d in sessions],
             "freeze_sha256": grid._sha(out / "freeze.json")}
    if sessions:
        tasks = [(arm, list(genome), str(folder), str(cache), START, sessions[-1]) for arm, genome in PANEL.items()]
        pool = ProcessPoolExecutor(max_workers=jobs) if jobs > 1 else None
        try:
            results = list((pool.map if pool else map)(_replay, tasks))
        finally:
            if pool:
                pool.shutdown()
        state["metrics"] = {arm: forward_metrics(trades, sessions) for arm, trades, _ in results}
        state["unresolved"] = {arm: state["metrics"][arm]["unresolved"] for arm, _, _ in results}
        state["notes"] = {arm: notes for arm, _, notes in results}
        state["trades"] = {arm: trades for arm, trades, _ in results}
        state["decision"] = decide(state["metrics"], complete=sessions[-1] >= END or ist_now.date().isoformat() > END)
    if frozen["bound"] != _bound():
        raise SystemExit("bound inputs changed during the run; refusing results")
    (local / "latest.json").write_text(json.dumps(state, indent=1, default=str), encoding="utf-8")
    (local / "REPORT.md").write_text(_report(state), encoding="utf-8")
    with (local / "history.jsonl").open("a", encoding="utf-8") as history:
        history.write(json.dumps({"ran_at_ist": state["ran_at_ist"], "sessions": len(sessions),
                                  "net": {arm: m["net_pnl"] for arm, m in state.get("metrics", {}).items()},
                                  "status": state.get("decision", {}).get("status")}) + "\n")
    for old in sorted(p for p in exports.iterdir() if p.is_dir() and p.name != folder.name):
        shutil.rmtree(old)
    print(f"forward panel: {len(sessions)} session(s); report {local / 'REPORT.md'}")
    return state


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("action", choices=("freeze", "run"))
    cli.add_argument("--out", type=Path, required=True)
    cli.add_argument("--jobs", type=int, default=3)
    args = cli.parse_args()
    if args.action == "freeze":
        freeze(args.out.resolve())
    else:
        run(args.out.resolve(), max(1, args.jobs))


if __name__ == "__main__":
    main()
