"""scripts/run_fno_forward_panel.py (O27c): the panel's provenance, the frozen rule and a run's outputs."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import run_fno_evolution as evo  # noqa: E402
import run_fno_forward_panel as panel  # noqa: E402
from tests.test_fno_policy_replay import DAY, _write_dataset  # noqa: E402


def test_every_panel_arm_is_the_genome_its_study_named():
    results = json.loads((REPO / "docs/research/fno/2026-10-27-evolution/results.json").read_text(encoding="utf-8"))
    finalists = results["decision"]["finalists"]
    keys = {arm: evo.key(genome) for arm, genome in panel.PANEL.items()}
    assert panel.PANEL[panel.SHIPPED] == evo.SHIPPED and keys[panel.SHIPPED] == results["shipped"]
    assert keys["EVO_PLATEAU_1"] == finalists[0]
    assert keys["EVO_BEST_FITNESS"] == max(finalists, key=lambda k: results["evaluations"][k]["fitness"])
    assert keys["EVO_OR20_LET_RUN"] in finalists
    assert evo.seeds({"decision": {"rank": ["OR20|LOCK_LATE|T75|TR1.5", "OR20_NOEMA|LOCK_LATE|T75|TR1.5"]}}) == [
        panel.PANEL["O27_PICK"], panel.PANEL["O27_OR20_NOEMA"]]
    assert all(value in evo.ALLELES[name] for genome in panel.PANEL.values()
               for name, value in zip(evo.NAMES, genome))


def _m(trades=0, net=0.0, ex_day=0.0, dd=0.0):
    return {"trades": trades, "net_pnl": net, "net_excluding_best_day": ex_day, "max_drawdown": dd}


def test_the_rule_needs_five_trades_profit_beyond_the_best_day_and_beating_the_shipped_book():
    metrics = {arm: _m() for arm in panel.PANEL}
    metrics[panel.SHIPPED] = _m(6, 2000, 500, 4000)
    metrics["EVO_PLATEAU_1"] = _m(7, 5000, 1000, 5500)               # passes; limit max(6,000, 5,000)
    metrics["O27_PICK"] = _m(4, 9000, 3000, 100)                     # too few trades
    metrics["O27_OR20_NOEMA"] = _m(9, 6000, -100, 100)               # one lucky day
    metrics["EVO_BEST_FITNESS"] = _m(9, 1500, 900, 100)              # under the shipped book
    decision = panel.decide(metrics, complete=False)
    assert decision["status"] == "PROVISIONAL" and decision["drawdown_limit"] == 6000
    assert {arm: v["promising"] for arm, v in decision["arms"].items()} == {
        "EVO_PLATEAU_1": True, "O27_PICK": False, "O27_OR20_NOEMA": False, "EVO_BEST_FITNESS": False,
        "EVO_OR20_LET_RUN": False}
    assert panel.decide(metrics, complete=True)["status"] == "FINAL"


def test_a_run_exports_replays_reports_and_keeps_only_the_newest_export(tmp_path, monkeypatch):
    source = _write_dataset(tmp_path / "data")
    manifest = json.loads((source / "manifest.json").read_text())
    manifest["files_sha256"] = {
        p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in source.rglob("*") if p.is_file() and p.name != "manifest.json"}
    (source / "manifest.json").write_text(json.dumps(manifest))

    def fake_export(folder):
        shutil.copytree(source, folder)

    monkeypatch.setattr(panel, "_export", fake_export)
    monkeypatch.setattr(panel, "START", DAY.isoformat())
    monkeypatch.setattr(panel, "END", DAY.isoformat())
    monkeypatch.setattr(panel, "_bound", lambda: {"sources": {}, "fno_settings_sha256": "x"})
    out = tmp_path / "panel"
    panel.freeze(out)
    first = panel.run(out, jobs=1)
    assert first["sessions"] == [DAY.isoformat()] and first["decision"]["status"] == "FINAL"
    assert first["metrics"][panel.SHIPPED]["trades"] == 1
    assert set(first["metrics"]) == set(panel.PANEL)
    panel.run(out, jobs=1)
    local = out / "_local"
    assert len(list((local / "exports").iterdir())) == 1
    assert len((local / "history.jsonl").read_text().splitlines()) == 2
    assert "SHIPPED" in (local / "REPORT.md").read_text(encoding="utf-8")
    monkeypatch.setattr(panel, "_bound", lambda: {"sources": {"x": "changed"}, "fno_settings_sha256": "x"})
    with pytest.raises(SystemExit, match="changed since freeze"):
        panel.run(out, jobs=1)
