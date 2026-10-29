"""O29f lab checks: the candle model is causal and declared, and the genome operators only make valid books."""
import random
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lab  # noqa: E402
import yeardata  # noqa: E402


def test_spread_model_is_the_declared_table():
    assert yeardata.spread_for(30) == 0.10 and yeardata.spread_for(120) == 0.30 and yeardata.spread_for(449) == 0.80
    assert yeardata.spread_for(1000) == 2.0
    for close in (0.35, 12.0, 99.95, 187.4, 512.0):
        bid, ask = yeardata.bid_ask(close)
        assert 0 < bid < ask and bid <= close <= ask
        assert round(ask - bid, 2) <= round(yeardata.spread_for(close) + 0.1, 2)


def _tiny_dataset(tmp: Path) -> Path:
    con = sqlite3.connect(tmp / "breeze.sqlite")
    con.execute("CREATE TABLE candles (kind TEXT, expiry TEXT, strike REAL, opt TEXT, datetime TEXT, open REAL, "
                "high REAL, low REAL, close REAL, volume REAL, oi REAL)")
    rows = [("future", "2026-01-27", 0.0, "", "2026-01-05 09:15:00", 100, 101, 99, 100.5, 10, 0),
            ("future", "2026-01-27", 0.0, "", "2026-01-05 09:16:00", 100.5, 103, 100, 102, 20, 0),
            ("future", "2026-01-27", 0.0, "", "2026-01-05 09:17:00", 102, 102, 101, 101.5, 5, 0),
            ("option", "2026-01-06", 100.0, "CE", "2026-01-05 09:15:00", 5, 6, 4, 5.5, 100, 9000),
            ("option", "2026-01-06", 100.0, "CE", "2026-01-05 09:17:00", 6, 7, 5, 6.5, 50, 9100)]
    con.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    manifest = {"underlying": "NIFTY", "lot_size": 65, "sessions": ["2026-01-05"],
                "weekly_expiry_calendar": ["2026-01-06"], "future_expiries": ["2026-01-27"],
                "logged_regimes": {"2026-01-05 09:15:00": "REGIME_1_NORMAL",
                                   "2026-01-05 10:00:00": "REGIME_3_CRISIS"}, "files_sha256": {}}
    (tmp / "manifest.json").write_text(__import__("json").dumps(manifest), encoding="utf-8")
    return tmp


def test_an_observation_shows_only_its_minute_close_and_ages_untraded_quotes(tmp_path):
    data = yeardata.YearData(_tiny_dataset(tmp_path))
    obs, _ = data.observations("2026-01-05")
    assert [o.at.strftime("%H:%M:%S") for o in obs] == ["09:15:59", "09:16:59", "09:17:59"]
    assert [o.future.ltp for o in obs] == [100.5, 102.0, 101.5]          # closes, never the minute's high
    assert [o.future.volume for o in obs] == [10, 30, 35]                  # running day volume
    ce = [next(iter(o.options.values())) for o in obs]
    assert [q.ltp for q in ce] == [5.5, 5.5, 6.5]                          # carried while untraded
    assert ce[1].last_trade_time == ce[0].last_trade_time == obs[0].at     # the planner's quote age grows
    assert ce[2].last_trade_time == obs[2].at and ce[2].volume == 150 and ce[2].oi == 9100
    assert all(q.bid < q.ltp < q.ask for q in ce)


def test_futures_bars_are_five_minute_bars_of_the_contract_itself(tmp_path):
    data = yeardata.YearData(_tiny_dataset(tmp_path))
    token = data.future_contract(date(2026, 1, 27)).token
    bars = data.futures_frame(token, date(2026, 1, 5))
    assert list(bars.index.strftime("%H:%M")) == ["09:15"]
    row = bars.iloc[0]
    assert (row["open"], row["high"], row["low"], row["close"], row["volume"]) == (100, 103, 99, 101.5, 35)


def test_the_regime_is_the_live_logged_label_else_an_open_gate(tmp_path):
    data = yeardata.YearData(_tiny_dataset(tmp_path))
    assert data.regime("2026-01-05 09:15:00", "2026-01-05") == ("REGIME_1_NORMAL", "logged_for_bar")
    assert data.regime("2026-01-05 09:40:00", "2026-01-05") == ("REGIME_1_NORMAL", "logged_earlier_same_day")
    assert data.regime("2026-01-05 10:05:00", "2026-01-05") == ("REGIME_3_CRISIS", "logged_earlier_same_day")
    assert data.regime("2026-01-06 10:00:00", "2026-01-06") == ("UNKNOWN", "not_logged")


def _valid(book: dict, track: str) -> bool:
    members = book["members"]
    if not 1 <= len(members) <= lab.MAX_MEMBERS or len({lab.digest(m) for m in members}) != len(members):
        return False
    for m in members:
        if m["gate"] not in lab.GATES:
            return False
        if m["kind"] == "NAMED":
            if track == "NULL" or m["name"] not in lab.NAMED or m["exit"] not in lab.NAMED_EXITS:
                return False
        else:
            g = m["genome"]
            if any(g[k] != v for k, v in lab.FIXED_SHARED.items()):
                return False
            if (g["family"] == "NULL_RANDOM") != (track == "NULL"):
                return False
    return True


def test_random_recombined_and_mutated_books_are_valid():
    rng = random.Random(7)
    for track in ("REAL", "NULL"):
        books = [lab.random_book(track, rng) for _ in range(60)]
        assert all(_valid(b, track) for b in books)
        for _ in range(200):
            child = lab.crossover(rng.choice(books), rng.choice(books), rng)
            assert _valid(child, track)
            assert _valid(lab.mutate(child, track, rng), track)
        for b in books[:10]:
            assert all(_valid(n, track) for n in lab.neighbours(b))
            assert len(lab.neighbours(b)) <= lab.GA["plateau_neighbours"]


def test_the_live_book_is_the_frozen_union_drive_shape():
    members = lab.FIXED["UNION_DRIVE"]["members"]
    assert [(m["name"], m["gate"], m["exit"]) for m in members] == [
        ("SHIPPED", "open_drive:HIGH", "OWN"), ("OR20", "open_drive:HIGH", "OWN"), ("EFF", "open_drive:HIGH", "OWN"),
        ("TPB", "ALWAYS", "OWN")]


def test_fitness_requires_trades_and_punishes_a_day_past_the_bound():
    base = {"sessions": 40, "trades": 20, "net_without_best_day": 4000, "dd": 2000, "green_weeks": 5, "red_weeks": 3,
            "weeks": 8, "green_months": 2, "red_months": 0, "months": 2, "stressed": 100, "worst_day": -1000}
    assert lab.fitness({**base, "trades": 5}) < -4
    assert lab.fitness(base) - lab.fitness({**base, "worst_day": -5001}) == 1.0


def test_market_hours_cap_the_workers():
    assert lab.market_hours(datetime(2026, 10, 29, 10, 0, tzinfo=lab.IST))
    assert not lab.market_hours(datetime(2026, 10, 29, 16, 0, tzinfo=lab.IST))
    assert not lab.market_hours(datetime(2026, 10, 31, 10, 0, tzinfo=lab.IST))  # a Saturday
    assert lab.free_gb() > 0
