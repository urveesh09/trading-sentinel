"""O28b forward panel C (research only): the four studied strategies run together in one book (UNION), and the same
with the three breakouts gated by the 09:45 opening drive (UNION_DRIVE, the O28 THEORY_DRIVE router), replayed
beside the shipped book on every session from Oct 28 to Nov 27. Same export, cache, metrics and rule as panel A,
plus an extreme-loss check.

python docs/research/fno/2026-10-28-forward-panel-c/panel_c.py freeze
python docs/research/fno/2026-10-28-forward-panel-c/panel_c.py run [--jobs 3]

Neither arm trades. Each run takes a fresh read-only export of the Production research archive (panel A's exporter,
``--include-finished-today``), replays every arm from the window's first session to the newest exported one, and
writes ``_local/latest.json``, ``_local/REPORT.md`` and a line in ``_local/history.jsonl``.
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

O28_DIR = ROOT / "docs/research/fno/2026-10-28-regime-router"
SOURCES = tuple(sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "python-engine").glob("*.py"))) + (
    "scripts/run_fno_consistency_grid.py", "scripts/run_fno_evolution.py", "scripts/run_fno_forward_panel.py",
    "scripts/export_fno_replay_dataset.py", "docs/research/fno/2026-10-27-genome-round3/lab.py",
    "docs/research/simulation/2026-10-27-fno-novel-families/lab.py",
    "docs/research/fno/2026-10-28-regime-router/router.py", "docs/research/fno/2026-10-28-regime-router/freeze.json",
    "docs/research/fno/2026-10-28-forward-panel-c/panel_c.py")
START, END = panel_a.START, panel_a.END
SHIPPED = "SHIPPED"
BANKROLL = 250000.0  # settings.FNO_PAPER_BANKROLL; a test ties them
EXTREME = {"worst_day": -0.02 * BANKROLL, "drawdown": 0.05 * BANKROLL}  # -Rs 5,000 a day; Rs 12,500 drawdown


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


router = _load(O28_DIR / "router.py", "o28_router")
O28_FUTURES = dict(router.NIFTY_FUTURES)  # the Sep / Oct contracts the O28 study used

# Arm -> O28 router config (None = the shipped book). Both were committed in O28 before the Oct 28 open.
PANEL: dict = {
    SHIPPED: None,
    "UNION": dict(router.UNION),
    "UNION_DRIVE": dict(router.THEORY["THEORY_DRIVE"]),
}
RULE = {**panel_a.RULE,
        "panel": "C (O28b): the four studied strategies in one book, and with the breakouts gated by the opening drive",
        "promising": panel_a.RULE["promising"] + f", and no day worse than Rs {-EXTREME['worst_day']:,.0f} "
                     f"(2% of the Rs {BANKROLL:,.0f} paper bankroll)",
        "extreme_loss_alarm": f"any arm with a day worse than Rs {-EXTREME['worst_day']:,.0f} or a drawdown above "
                              f"Rs {EXTREME['drawdown']:,.0f} (5% of the bankroll) is flagged at the top of REPORT.md",
        "brakes": "both arms run through the shipped book unchanged: 2% pool risk per trade, 3 entries a day, the "
                  "15% open-premium cap, the two-loss day halt and the 15% drawdown halt"}


def _bound() -> dict:
    return {"sources": {rel: grid._sha(ROOT / rel) for rel in SOURCES}, "fno_settings_sha256": panel_a._settings_hash()}


def frozen_history() -> dict:
    """The O28 study's 09:45 feature values for its 29 sessions (the forward table must reproduce them)."""
    results = json.loads((O28_DIR / "results.json").read_text(encoding="utf-8"))
    return {day: row["values"] for day, row in results["per_day"].items()}


def freeze() -> None:
    grid._write_new(HERE / "freeze.json", {
        "schema": "fno_forward_panel_c_freeze_v1", "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "bound": _bound(), "window": [START, END], "rule": RULE, "extreme": EXTREME, "panel": PANEL,
        "history": frozen_history(),
        "export": {"volume": panel_a.VOLUME, "image": panel_a.IMAGE, "mode": "read-only throwaway container"},
        "can_place_orders": False, "qualification": "NOT_ASSESSED"})
    print("frozen forward panel C:", HERE / "freeze.json")


def front_futures(data, days: list[str]) -> dict[int, str]:
    """NIFTY future token -> expiry: the O28 contracts plus the front future of every replayed session."""
    out = dict(O28_FUTURES)
    for day in days:
        observations, _ = data.observations(day)
        if observations:
            contract = observations[0].future.contract
            out[int(contract.token)] = str(contract.expiry)
    return out


def replay_router(data, db: Path, config: dict, start: str, end: str) -> tuple[dict, dict]:
    """One router arm over [start, end]; returns the replay result and the conditions it read."""
    days = [d for d in data.days if start <= d <= end]
    futures = front_futures(data, days)
    router.NIFTY_FUTURES.clear()
    router.NIFTY_FUTURES.update(futures)
    table = router.condition_table(router.nifty_bars(db))
    with router.dispatch():
        result = router.RouterReplay(data, config, table, {}).run(start, end)
    return result, table


def history_check(table: dict, history: dict) -> list[str]:
    """Sessions whose recomputed 09:45 values differ from the O28 study's (4 d.p.)."""
    bad = []
    for day, values in history.items():
        row = table.get(day)
        mine = {f: (round(row[f], 4) if row and row[f] is not None else None) for f in router.FEATURES}
        if mine != values:
            bad.append(day)
    return bad


def _replay(task: tuple):
    arm, config, folder, cache, start, end = task
    data = panel_a.SessionCache(Path(folder), Path(cache))
    if config is None:
        result = replay.SingleLegReplay(data, replay.resolve_policy("CURRENT")).run(start, end)
        extra = {}
    else:
        result, table = replay_router(data, Path(folder) / "fno-replay.sqlite", config, start, end)
        sessions = [d for d in data.days if start <= d <= end]
        extra = {"conditions": {d: {"open_drive": (table.get(d) or {}).get("open_drive"),
                                    "side": (table.get(d) or {}).get("side", {}).get("open_drive"),
                                    "on": [c for c in router.COMPONENTS if router.allowed(config[c], table.get(d))]}
                                for d in sessions},
                 "history_mismatch": history_check(table, json.loads((HERE / "freeze.json").read_text(
                     encoding="utf-8"))["history"]),
                 "by_component": {c: sum(1 for t in result["trades"] if t.get("component") == c)
                                  for c in router.COMPONENTS}}
    notes = {k: v for k, v in result["notes"].items() if not k.startswith(("regime_", "grid_", "memo_"))}
    return arm, result["trades"], notes, extra


def worst_day(metrics: dict) -> float:
    return min([0.0, *metrics["by_day"].values()])


def decide(metrics: dict, complete: bool) -> dict:
    """Panel A's frozen checks over this panel's arms, plus: no day worse than 2% of the bankroll."""
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
    text = panel_a._report(state).replace("# F&O forward panel", "# F&O forward panel C (O28b)", 1)
    text = text.replace(panel_a.RULE["promising"], RULE["promising"])
    lines = text.split("\n")
    extra = []
    alarms = state.get("decision", {}).get("alarms")
    if alarms:
        extra += ["**EXTREME-LOSS ALARM:** " + "; ".join(
            f"{arm} worst day ₹{a['worst_day']:,.0f}, max drawdown ₹{a['max_drawdown']:,.0f}"
            for arm, a in alarms.items()), ""]
    for arm, info in state.get("extra", {}).items():
        if info.get("history_mismatch"):
            extra += [f"**Check:** {arm} recomputed different 09:45 values for {info['history_mismatch']} than the "
                      "O28 study; its UNION_DRIVE gating may not match the frozen rule.", ""]
    drive = state.get("extra", {}).get("UNION_DRIVE", {}).get("conditions", {})
    if drive:
        extra += ["Opening drive at 09:45 (UNION_DRIVE turns the three breakouts on only on HIGH):", "",
                  "| Day | Drive | Side | Strategies on |", "| --- | --- | --- | --- |"]
        extra += [f"| {d} | {c['open_drive'] if c['open_drive'] is None else round(c['open_drive'], 2)} | "
                  f"{c['side']} | {', '.join(c['on']) or 'none'} |" for d, c in drive.items()]
        extra += [""]
    mix = {arm: info["by_component"] for arm, info in state.get("extra", {}).items() if "by_component" in info}
    if mix:
        extra += ["Trades by strategy: " + "; ".join(f"{arm} {m}" for arm, m in mix.items()) + ".", ""]
    return "\n".join(lines[:4] + extra + lines[4:])


def run(jobs: int) -> dict:
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    if frozen["bound"] != _bound():
        raise SystemExit("bound inputs changed since freeze; refusing to run (sources or effective F&O settings)")
    if PANEL != frozen["panel"]:
        raise SystemExit("panel differs from the frozen panel; refusing to run")
    local = HERE / "_local"
    exports, cache = local / "exports", local / "observations"
    cache.mkdir(parents=True, exist_ok=True)
    folder = exports / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    panel_a._export(folder)
    manifest = panel_a._verify(folder)
    sessions = [d for d in manifest["quote_days"] if START <= d <= END]
    ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    state = {"schema": "fno_forward_panel_c_state_v1", "ran_at_ist": ist_now.strftime("%Y-%m-%d %H:%M"),
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
    print(f"forward panel C: {len(sessions)} session(s); report {local / 'REPORT.md'}")
    return state


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("action", choices=("freeze", "run"))
    cli.add_argument("--jobs", type=int, default=3)
    args = cli.parse_args()
    freeze() if args.action == "freeze" else run(args.jobs)
