"""EDGE read handles must close on early-return and query-error paths."""
import sqlite3

import pytest

import penny_edge_live


@pytest.mark.parametrize("query_error", [False, True])
def test_scan_closes_database_before_return_or_raise(tmp_path, monkeypatch, query_error):
    path = tmp_path / "edge.sqlite"
    original = sqlite3.connect
    if query_error:
        conn = original(path)
        conn.execute("CREATE TABLE ohlcv_cache (ticker,date,open,high,low,close,volume)")
        conn.close()
        def broken(*args, **kwargs):
            raise RuntimeError("query fixture")
        monkeypatch.setattr(penny_edge_live.pee, "load_recent_daily_bars_from_db", broken)
    seen = []
    def tracked(*args, **kwargs):
        conn = original(*args, **kwargs)
        seen.append(conn)
        return conn
    monkeypatch.setattr(penny_edge_live.sqlite3, "connect", tracked)
    if query_error:
        with pytest.raises(RuntimeError, match="query fixture"):
            penny_edge_live.scan_today(db_path=str(path), as_of_date="2026-08-10")
    else:
        assert penny_edge_live.scan_today(db_path=str(path))["n_candidates"] == 0
    assert len(seen) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        seen[0].execute("SELECT 1")
    path.unlink()  # catches a remaining Windows handle, too
