"""scripts/run_preregistered_study.py: frozen-input guard, score-once rule and result assembly."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import run_preregistered_study as rps  # noqa: E402


def _fake_study():
    return rps.Study(
        strategy="fake", snapshot=Path("unused"), base_config=lambda: {}, sources=(),
        windows={"untouched": (("2026-01-01", "2026-01-31"), ("2026-03-01", "2026-03-31"))},
        arms={"BASELINE": {"arm": "base"}, "CAND": {"arm": "cand"}},
        books={"b1": {"book": 1}}, candidate="CAND", decision_window="untouched", decision_book="b1",
        drawdown_key="max_drawdown", drawdown_floor=10.0, metrics="trades")


@pytest.fixture
def study(monkeypatch, tmp_path):
    monkeypatch.setitem(rps.STUDIES, "fake", _fake_study())
    monkeypatch.setattr(rps, "_bound", lambda s: {"sources": {}, "snapshot": {"rows_sha256": "x"}})
    calls = []

    def execute(study, frozen, start, end, overrides, target):
        calls.append((start, overrides["arm"], overrides["book"]))
        net = 5.0 if overrides["arm"] == "cand" else -1.0
        trade = {"status": "CLOSED", "net_pnl": net, "ticker": "A", "trading_date": start, "exit_bar_ts": start}
        report = {"state": "SUCCEEDED", "result": {"trades": [trade]}}
        target.write_text(json.dumps(report))
        return report

    monkeypatch.setattr(rps, "_execute", execute)
    out = tmp_path / "study"
    out.mkdir()
    (out / "freeze.json").write_text(json.dumps({"study": "fake", "bound": rps._bound(None), "config": {}}))
    return out, calls


def test_scores_every_range_once_and_decides(study):
    out, calls = study
    rps.run("fake", out)
    assert sorted(calls) == sorted([(s, a, 1) for s in ("2026-01-01", "2026-03-01") for a in ("base", "cand")])
    results = json.loads((out / "results.json").read_text())
    cand = results["results"]["untouched"]["b1"]["CAND"]
    assert cand["closed"] == 2 and cand["net_pnl"] == 10.0
    assert results["decision"]["verdict"] == "PROMISING_CONTINUE_SHADOW"   # +10, +5 excl. best, beats -2
    with pytest.raises(SystemExit, match="scored once"):
        rps.run("fake", out)


def test_refuses_when_bound_inputs_changed(study, monkeypatch):
    out, calls = study
    monkeypatch.setattr(rps, "_bound", lambda s: {"sources": {"x": "changed"}, "snapshot": {}})
    with pytest.raises(SystemExit, match="bound inputs changed"):
        rps.run("fake", out)
    assert calls == []
