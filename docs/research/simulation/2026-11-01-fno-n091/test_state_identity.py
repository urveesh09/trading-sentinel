"""Reproduce and prevent overwriting one independent year's terminal state with another."""
import json
import os
from types import SimpleNamespace


def test_same_policy_fresh_years_keep_distinct_terminal_cash(tmp_path, monkeypatch):
    os.environ.setdefault("N08_YEAR", "2025")
    import n091_lab as L
    monkeypatch.setattr(L, "LOCAL", tmp_path)
    def run(self, start, end):
        return {"start_equity": 250000., "trades": [{"net_pnl": 100. if start.startswith("2024") else 200.}]}
    monkeypatch.setattr(L, "_run", run)
    book = {"label": "IDENTITY_TEST", "n091": {"mode": "CUSHION"}}
    paths = []
    for year in ("2024", "2025"):
        engine = SimpleNamespace(book=book, source="year", decisions=[])
        L.run_book(engine, year + "-01-01", year + "-12-31")
        key = L.Y.task_key(book, "year", (year + "-01-01", year + "-12-31"))
        paths.append(tmp_path / "states" / (key + ".json"))
    assert paths[0] != paths[1]
    assert [json.loads(p.read_text())["end_equity"] for p in paths] == [250100., 250200.]
