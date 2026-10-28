"""O29b forward panel D (research only): the opening-drive filter that the O29b chop study found on the studied
strategies, replayed beside the shipped book on every session from Oct 29 to Nov 27. Oct 28 (the day that prompted
the study) and every earlier session were seen; only these sessions can tell.

python docs/research/fno/2026-10-29-forward-panel-d/panel_d.py freeze
python docs/research/fno/2026-10-29-forward-panel-d/panel_d.py run [--jobs 3]

Arms (O29b configs, chosen before Oct 29):
  SHIPPED          the shipped book (CURRENT), the control;
  SHIPPED_DRIVE    the shipped strategy, only on mornings with a HIGH 09:45 opening drive;
  OR20_DRIVE       the O27 grid's 20-minute break, only on HIGH-drive mornings (O29b walk-forward: passed);
  EFF_DRIVE        the O27e efficiency break, only on HIGH-drive mornings (O29b walk-forward: passed);
  DRIVE_BOOK_FADE  the O29b FINAL smart book: the three breakouts on HIGH-drive mornings, the trend-day pullback
                   always, and a VWAP 2-sigma rejection fade (O29b walk-forward: FAILED; observed only).
Neither arm trades. Each run takes a fresh read-only export of the Production research archive (panel A's exporter),
replays every arm over the window, and writes _local/latest.json, _local/REPORT.md and a line in history.jsonl.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
sys.path[:0] = [str(ROOT / "python-engine"), str(ROOT / "scripts")]
import fno_policy_replay as replay  # noqa: E402
import run_fno_consistency_grid as grid  # noqa: E402
import run_fno_forward_panel as panel_a  # noqa: E402

STUDY_DIR = ROOT / "docs/research/fno/2026-10-28-chop-study"
SOURCES = tuple(sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "python-engine").glob("*.py"))) + (
    "scripts/run_fno_consistency_grid.py", "scripts/run_fno_evolution.py", "scripts/run_fno_forward_panel.py",
    "scripts/export_fno_replay_dataset.py", "docs/research/fno/2026-10-27-genome-round3/lab.py",
    "docs/research/simulation/2026-10-27-fno-novel-families/lab.py",
    "docs/research/fno/2026-10-28-regime-router/router.py", "docs/research/fno/2026-10-28-chop-study/study.py",
    "docs/research/fno/2026-10-28-chop-study/freeze.json", "docs/research/fno/2026-10-29-forward-panel-d/panel_d.py")
START, END = "2026-10-29", panel_a.END
SHIPPED = "SHIPPED"
BANKROLL = 250000.0  # settings.FNO_PAPER_BANKROLL; a test ties them
EXTREME = {"worst_day": -0.02 * BANKROLL, "drawdown": 0.05 * BANKROLL}


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


study = _load(STUDY_DIR / "study.py", "o29b_study")
router = study.router
STUDY_FUTURES = dict(router.NIFTY_FUTURES)  # Sep, Oct and Nov contracts

FADE = {"family": "VWAP_REVERT", "k": 2.0, "er_below": 1.0, "stop": 1.5, "target_r": 2.4, "exit": "LIVE"}
PANEL: dict = {
    SHIPPED: None,
    "SHIPPED_DRIVE": study.single("SHIPPED", "drive:HIGH"),
    "OR20_DRIVE": study.single("OR20", "drive:HIGH"),
    "EFF_DRIVE": study.single("EFF", "drive:HIGH"),
    "DRIVE_BOOK_FADE": study.smart("drive:HIGH", FADE),
}
RULE = {**panel_a.RULE,
        "panel": "D (O29b): the 09:45 opening-drive filter on the studied strategies, from Oct 29",
        "promising": panel_a.RULE["promising"] + f", and no day worse than Rs {-EXTREME['worst_day']:,.0f} "
                     f"(2% of the Rs {BANKROLL:,.0f} paper bankroll)",
        "extreme_loss_alarm": f"any arm with a day worse than Rs {-EXTREME['worst_day']:,.0f} or a drawdown above "
                              f"Rs {EXTREME['drawdown']:,.0f} is flagged at the top of REPORT.md",
        "drive_filter_reading": "a filtered arm that sits out more days is not better for it: it is better only by "
                                "the rule above, against the unfiltered strategy's own forward result in panels A-C",
        "brakes": "every arm runs through the shipped book unchanged"}


def _bound() -> dict:
    return {"sources": {rel: grid._sha(ROOT / rel) for rel in SOURCES}, "fno_settings_sha256": panel_a._settings_hash()}


def freeze() -> None:
    grid._write_new(HERE / "freeze.json", {
        "schema": "fno_forward_panel_d_freeze_v1", "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "bound": _bound(), "window": [START, END], "rule": RULE, "extreme": EXTREME, "panel": PANEL,
        "export": {"volume": panel_a.VOLUME, "image": panel_a.IMAGE, "mode": "read-only throwaway container"},
        "can_place_orders": False, "qualification": "NOT_ASSESSED"})
    print("frozen forward panel D:", HERE / "freeze.json")


def front_futures(data, days: list[str]) -> dict[int, str]:
    out = dict(STUDY_FUTURES)
    for day in days:
        observations, _ = data.observations(day)
        if observations:
            contract = observations[0].future.contract
            out[int(contract.token)] = str(contract.expiry)
    return out


def replay_arm(data, db: Path, config: dict, start: str, end: str) -> tuple[dict, dict]:
    """One filtered arm over [start, end] through the O29b book; returns the result and the day states it read."""
    days = [d for d in data.days if start <= d <= end]
    futures = front_futures(data, days)
    router.NIFTY_FUTURES.clear()
    router.NIFTY_FUTURES.update(futures)
    states = study.bar_states(study.futures_bars(db))
    with router.dispatch():
        result = study.ChopReplay(data, config, states, {}).run(start, end)
    return result, states


def _replay(task: tuple):
    arm, config, folder, cache, start, end = task
    data = panel_a.SessionCache(Path(folder), Path(cache))
    if config is None:
        result = replay.SingleLegReplay(data, replay.resolve_policy("CURRENT")).run(start, end)
        extra = {}
    else:
        result, states = replay_arm(data, Path(folder) / "fno-replay.sqlite", config, start, end)
        sessions = [d for d in data.days if start <= d <= end]
        extra = {"drive": {d: next(iter(states[d].values()))["drive"] if states.get(d) else None for d in sessions},
                 "by_component": dict(Counter(str(t.get("component")) for t in result["trades"]))}
    notes = {k: v for k, v in result["notes"].items() if not k.startswith(("regime_", "grid_", "memo_"))}
    return arm, result["trades"], notes, extra


def worst_day(metrics: dict) -> float:
    return min([0.0, *metrics["by_day"].values()])


def decide(metrics: dict, complete: bool) -> dict:
    saved = panel_a.PANEL
    panel_a.PANEL = {arm: None for arm in PANEL}
    try:
        decision = panel_a.decide(metrics, complete=complete)
    finally:
        panel_a.PANEL = saved
    for arm, verdict in decision["arms"].items():
        verdict["checks"]["no_extreme_day"] = worst_day(metrics[arm]) >= EXTREME["worst_day"]
        verdict["promising"] = all(verdict["checks"].values())
    decision["alarms"] = {arm: {"worst_day": round(worst_day(m), 2), "max_drawdown": m["max_drawdown"]}
                          for arm, m in metrics.items()
                          if worst_day(m) < EXTREME["worst_day"] or m["max_drawdown"] > EXTREME["drawdown"]}
    return decision


def report(state: dict) -> str:
    text = panel_a._report(state).replace("# F&O forward panel", "# F&O forward panel D (O29b)", 1)
    text = text.replace(panel_a.RULE["promising"], RULE["promising"])
    lines = text.split("\n")
    extra = []
    alarms = state.get("decision", {}).get("alarms")
    if alarms:
        extra += ["**EXTREME-LOSS ALARM:** " + "; ".join(
            f"{arm} worst day ₹{a['worst_day']:,.0f}, max drawdown ₹{a['max_drawdown']:,.0f}"
            for arm, a in alarms.items()), ""]
    drive = next((info["drive"] for info in state.get("extra", {}).values() if info.get("drive")), None)
    if drive:
        extra += ["09:45 opening drive (the filtered arms trade their breakouts only on HIGH):", "",
                  "| Day | Drive |", "| --- | --- |", *[f"| {d} | {s} |" for d, s in drive.items()], ""]
    mix = {arm: info["by_component"] for arm, info in state.get("extra", {}).items() if "by_component" in info}
    if mix:
        extra += ["Trades by strategy: " + "; ".join(f"{arm} {m}" for arm, m in mix.items()) + ".", ""]
    extra += ["DRIVE_BOOK_FADE failed the O29b walk-forward (its fade family did no better than random entries); it is "
              "observed, not a candidate.", ""]
    return "\n".join(lines[:4] + extra + lines[4:])


def run(jobs: int) -> dict:
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    if frozen["bound"] != _bound():
        raise SystemExit("bound inputs changed since freeze; refusing to run (sources or effective F&O settings)")
    if json.loads(json.dumps(PANEL)) != frozen["panel"]:
        raise SystemExit("panel differs from the frozen panel; refusing to run")
    local = HERE / "_local"
    exports, cache = local / "exports", local / "observations"
    cache.mkdir(parents=True, exist_ok=True)
    folder = exports / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    panel_a._export(folder)
    manifest = panel_a._verify(folder)
    sessions = [d for d in manifest["quote_days"] if START <= d <= END]
    ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    state = {"schema": "fno_forward_panel_d_state_v1", "ran_at_ist": ist_now.strftime("%Y-%m-%d %H:%M"),
             "window": [START, END], "export": folder.name, "sessions": sessions,
             "unsealed": [d for d in manifest.get("unsealed_days", []) if d in sessions],
             "freeze_sha256": grid._sha(HERE / "freeze.json")}
    if sessions:
        tasks = [(arm, config, str(folder), str(cache), START, sessions[-1]) for arm, config in PANEL.items()]
        with ProcessPoolExecutor(max_workers=max(1, jobs)) as pool:
            results = list(pool.map(_replay, tasks))
        state["metrics"] = {arm: panel_a.forward_metrics(trades, sessions) for arm, trades, _, _ in results}
        state["unresolved"] = {arm: state["metrics"][arm]["unresolved"] for arm, _, _, _ in results}
        state["notes"] = {arm: notes for arm, _, notes, _ in results}
        state["extra"] = {arm: extra for arm, _, _, extra in results if extra}
        state["trades"] = {arm: trades for arm, trades, _, _ in results}
        complete = sessions[-1] >= END or ist_now.date().isoformat() > END
        state["decision"] = decide(state["metrics"], complete)
    if frozen["bound"] != _bound():
        raise SystemExit("bound inputs changed during the run; refusing results")
    (local / "latest.json").write_text(json.dumps(state, indent=1, default=str), encoding="utf-8")
    (local / "REPORT.md").write_text(report(state), encoding="utf-8")
    with (local / "history.jsonl").open("a", encoding="utf-8") as history:
        history.write(json.dumps({"ran_at_ist": state["ran_at_ist"], "sessions": len(sessions),
                                  "net": {arm: m["net_pnl"] for arm, m in state.get("metrics", {}).items()},
                                  "alarms": state.get("decision", {}).get("alarms"),
                                  "status": state.get("decision", {}).get("status")}) + "\n")
    for old in sorted(p for p in exports.iterdir() if p.is_dir() and p.name != folder.name):
        shutil.rmtree(old)
    print(f"forward panel D: {len(sessions)} session(s); report {local / 'REPORT.md'}")
    return state


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("action", choices=("freeze", "run"))
    cli.add_argument("--jobs", type=int, default=3)
    args = cli.parse_args()
    freeze() if args.action == "freeze" else run(args.jobs)
