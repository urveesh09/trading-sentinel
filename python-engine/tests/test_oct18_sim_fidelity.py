"""Oct 18 simulation-report fixes: replays that answer like the runtime does.

* F&O replay: a dated expiry calendar (not the series one batch carries) and a
  CURRENT arm that follows the live switches.
* EDGE overnight: the runtime book's daily-bar realism refusals, ranked deep.
(Penny paper-exit parity is tested in test_penny_lifecycle_replay.py.)
"""
import gzip
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

import tests.test_fno_policy_replay as fno_fixture
from config import settings
from fno_policy_replay import FnoReplayError, ReplayData, resolve_policy, run_replay
from tests.test_edge_portfolio_replay import DAYS, _pos, _rows, _scanner

DAY = fno_fixture.DAY.isoformat()


def _with_calendar(dataset, expiries):
    manifest = json.loads((dataset / "manifest.json").read_text())
    manifest["option_expiries"] = {"NIFTY": sorted(expiries)}
    (dataset / "manifest.json").write_text(json.dumps(manifest))
    return dataset


# ---- F&O replay calendar ---------------------------------------------------

def test_archive_scan_calendar_keeps_a_regular_day_tradeable(tmp_path):
    dataset = fno_fixture._write_dataset(tmp_path)
    assert ReplayData(dataset).option_expiries() == ((fno_fixture.EXPIRY,), "archive_scan")
    result = run_replay(dataset, start=DAY, end=DAY)
    assert len([t for t in result["trades"] if "net_pnl" in t]) == 1
    assert result["expiry_calendar"] == {"source": "archive_scan", "window_expiry_days": []}


def test_a_batch_missing_the_same_day_series_never_trades_the_next_series(tmp_path):
    # Oct 13: the calendar says today is an expiry, but these batches only carry
    # the next series. The old replay read "no 0DTE quotes" as a regular day and
    # bought the next series (an INVALID -Rs 2,270 in the Oct 18 simulation).
    dataset = _with_calendar(fno_fixture._write_dataset(tmp_path), [DAY, fno_fixture.EXPIRY.isoformat()])
    result = run_replay(dataset, start=DAY, end=DAY)
    assert not [t for t in result["trades"] if "net_pnl" in t]
    assert result["funnel"]["chain_unavailable:calendar_expiry_not_archived"] >= 1
    assert result["expiry_calendar"] == {"source": "export_manifest", "window_expiry_days": [DAY]}


def test_an_archived_expiry_day_is_blocked_by_the_runtime_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(fno_fixture, "EXPIRY", fno_fixture.DAY)   # the batches quote the 0DTE series
    result = run_replay(fno_fixture._write_dataset(tmp_path), start=DAY, end=DAY)
    assert not [t for t in result["trades"] if "net_pnl" in t]
    assert result["funnel"]["expiry_day_block"] >= 1
    assert result["expiry_calendar"]["window_expiry_days"] == [DAY]


def test_current_arm_follows_the_live_fast_exit_switch(monkeypatch):
    monkeypatch.setattr(settings, "FNO_FAST_EXIT_ENABLED", True)
    assert resolve_policy("CURRENT").manage_every_observation is True
    monkeypatch.setattr(settings, "FNO_FAST_EXIT_ENABLED", False)
    current = resolve_policy("CURRENT")
    assert current.manage_every_observation is False
    assert (current.partial_at_target, current.pyramid_house_money, current.trend_day_filter) == (False,) * 3
    assert resolve_policy("BASELINE").name == "BASELINE"
    with pytest.raises(FnoReplayError, match="unknown policy"):
        resolve_policy("NOPE")


def test_exporter_records_every_quoted_option_expiry(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "export_fno_replay_dataset", Path(__file__).resolve().parents[2] / "scripts/export_fno_replay_dataset.py")
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    folder = tmp_path / "data/research/quotes/2026-10-12"
    folder.mkdir(parents=True)
    lines = [{"contract": {"underlying": "NIFTY", "instrument_type": kind, "expiry": expiry,
                           "instrument_token": token, "tradingsymbol": f"S{token}"}}
             for kind, expiry, token in (("FUT", "2026-10-27", 1), ("CE", "2026-10-13", 2),
                                         ("PE", "2026-10-20", 3), ("CE", "2026-10-13", 4))]
    lines.append({"contract": {"underlying": "SENSEX", "instrument_type": "PE", "expiry": "2026-10-15",
                               "instrument_token": 5, "tradingsymbol": "S5"}})
    lines.append({"contract": {"underlying": "RELIANCE", "instrument_type": "CE", "expiry": "2026-10-27",
                               "instrument_token": 6, "tradingsymbol": "S6"}})
    (folder / "quotes-abc.jsonl.gz").write_bytes(gzip.compress("".join(json.dumps(l) + "\n" for l in lines).encode()))
    with sqlite3.connect(tmp_path / "data/cache.db") as con:
        con.execute("CREATE TABLE intraday_cache_by_token (instrument_token, interval, datetime, open, high, low,"
                    " close, volume, oi)")
    manifest = exporter.export(tmp_path / "data", tmp_path / "out")
    assert manifest["option_expiries"] == {"NIFTY": ["2026-10-13", "2026-10-20"], "SENSEX": ["2026-10-15"]}
    assert manifest["nifty_future_tokens"] == {"1": "S1"}


# ---- EDGE overnight runtime realism -----------------------------------------

LIQUID = (20.0, 20.2, 19.8, 20.0, 100000.0)


def _overnight_signals(monkeypatch, policy):
    names = ("AAA-SM", "BBB", "CCC", "DDD", "DDD-BE", "EEE", "FFF", "GGG")
    paths = {name: {DAYS[1]: LIQUID} for name in names}
    paths["CCC"] = {DAYS[1]: (20.0, 20.5, 19.9, 20.5, 100000.0)}     # closes at the high, +2.5%
    picks = [_pos(name, DAYS[1], close=paths[name][DAYS[1]][3], subtype="MR_mid" if name == "BBB" else "MO_mid")
             for name in names]
    depths = []

    def scan(**kwargs):
        depths.append(kwargs["max_positions"])
        return _scanner({DAYS[1]: picks})(**kwargs)
    monkeypatch.setattr("penny_edge_live.scan_today", scan)
    from edge_portfolio_replay import EdgeReplayConfig, run_edge_portfolio
    rows = _rows(paths)
    config = EdgeReplayConfig(tickers=tuple(sorted(names)), policy=policy, max_positions=3)
    return run_edge_portfolio(rows, start=DAYS[0], end=DAYS[-1], config=config), set(depths)


def test_runtime_overnight_refuses_like_the_live_book_and_fills_by_rank(monkeypatch):
    result, depths = _overnight_signals(monkeypatch, "EDGE_OVERNIGHT_RUNTIME")
    from edge_overnight_paper import RANK_DEPTH
    assert depths == {RANK_DEPTH}
    assert sorted(t["ticker"] for t in result["trades"]) == ["DDD", "EEE", "FFF"]
    outcomes = result["admission_outcomes"]
    assert (outcomes["REALISM_sme_series"], outcomes["REALISM_weak_kind_MR_mid"],
            outcomes["REALISM_at_day_high_after_rise"], outcomes["REALISM_duplicate_series"]) == (1, 1, 1, 1)
    assert outcomes["FILLED"] == 3 and outcomes["DAILY_ENTRY_CAP"] == 1


def test_study_overnight_arm_is_unchanged(monkeypatch):
    result, depths = _overnight_signals(monkeypatch, "EDGE_OVERNIGHT")
    assert depths == {3}
    assert sorted(t["ticker"] for t in result["trades"]) == ["AAA-SM", "BBB", "CCC"]
    assert not any(key.startswith("REALISM_") for key in result["admission_outcomes"])


def test_runtime_refusal_reasons_are_unchanged_by_the_split():
    import edge_overnight_paper as eop
    assert eop.series_refusal("AAA-ST", "MO_strong", set()) == "sme_series"
    assert eop.day_high_refusal((20.0, 20.5, 19.9, 20.5, 1.0), 20.0) == "at_day_high_after_rise"
    assert eop.day_high_refusal((20.0, 20.5, 19.9, 20.5, 1.0), 20.2) is None     # +1.5%: not a lock
    assert eop.day_high_refusal((20.0, 20.5, 19.9, 20.5, 1.0), None) is None
