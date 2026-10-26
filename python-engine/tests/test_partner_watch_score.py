"""[O26] partner_watch_score: the check's warnings scored on stored trades, by the rule frozen before the days it
decides on (read-only)."""
import json

import aiosqlite
import pytest

import partner_watch as pw
import partner_watch_score as score
from config import settings

SYMBOL = "NIFTY26OCT22300PE"


def _trip(day, n, realised, *, run=None, after=None, usual=None, share=None, exact=1, carried=0, closed=True,
          symbol=SYMBOL, at="10:00:00"):
    return {"session_date": day, "position_key": f"{day}:{n}", "exchange": "NFO", "tradingsymbol": symbol,
            "product": "NRML", "first_at": f"{day}T{at}+05:30", "closed_at": f"{day}T10:30:00+05:30" if closed else None,
            "bought": 65, "sold": 65 if closed else 0, "entry": 80.0, "exit": 70.0 if closed else None,
            "realised": realised if closed else None, "orders": 2, "exact": exact, "carried": carried, "run_pct": run,
            "after_loss": json.dumps(after) if after else None, "usual": usual, "paid_share": share,
            "updated_at": f"{day}T10:30:00+05:30"}


async def _store(trips, checks=()):
    db = settings.DB_PATH
    await pw.init_partner_watch_db(db)
    async with aiosqlite.connect(db) as conn:
        await conn.executemany(f"INSERT INTO partner_watch_trips({','.join(pw._TRIP_COLS)}) "
                               f"VALUES({','.join('?' * len(pw._TRIP_COLS))})",
                               [tuple(t[c] for c in pw._TRIP_COLS) for t in trips])
        for key, day, symbol, sent_at in checks:
            await conn.execute(
                "INSERT INTO partner_watch_messages(message_key, session_date, kind, created_at, sent, text, context, "
                "sent_at) VALUES(?, ?, 'CHECK', ?, 1, 'x', ?, ?)",
                (key, day, sent_at, json.dumps({"contract": {"tradingsymbol": symbol}}), sent_at))
        await conn.commit()
    return db


def test_the_warnings_are_the_ones_a_check_gives_at_the_buy():
    after = {"loss": 700.0, "at": "10:05", "minutes": 5, "bigger": None}
    assert score.warnings_of({"run_pct": 0.1999}) == set()
    assert score.warnings_of({"run_pct": 0.2}) == {"CHASED_SPIKE", "ANY"}
    assert score.warnings_of({"after_loss": after}) == {"AFTER_LOSS", "ANY"}
    assert score.warnings_of({"after_loss": after | {"bigger": "130 after 65"}}) == {
        "AFTER_LOSS", "BIGGER_AFTER_LOSS", "ANY"}
    assert score.warnings_of({"usual": 0.2, "paid_share": 0.31}) == {"UNUSUAL_SIZE", "ANY"}
    assert score.warnings_of({"usual": 0.2, "paid_share": 0.30}) == set()       # not over 1.5 x
    assert score.warnings_of({"usual": None, "paid_share": 0.9}) == set()       # no usual known


@pytest.mark.asyncio
async def test_a_warning_is_supported_only_by_twenty_warned_trades_that_lose_on_decision_days():
    trips = [_trip("2026-10-27", i, -100.0, run=0.25) for i in range(20)]
    trips += [_trip("2026-10-28", 100 + i, 50.0, run=0.05) for i in range(10)]
    trips += [_trip("2026-10-26", 200 + i, -900.0, run=0.30) for i in range(5)]           # the design day
    trips += [_trip("2026-10-27", 300, -5000.0, carried=1), _trip("2026-10-27", 301, 0.0, closed=False)]
    db = await _store(trips)
    first, last, trades = score.load(db, "2026-10-26")
    assert (first, last, len(trades)) == ("2026-10-26", "2026-10-28", 35)                 # not carried, closed only
    result = score.score(trades)
    assert (result["decision_trades"], result["seen_trades"]) == (30, 5)
    spike = result["warnings"]["CHASED_SPIKE"]
    assert spike["verdict"] == "SUPPORTED" and spike["warned"] == {"n": 20, "won": 0, "total": -2000.0, "mean": -100.0}
    assert spike["unwarned"] == {"n": 10, "won": 10, "total": 500.0, "mean": 50.0}
    assert result["warnings"]["ANY"]["verdict"] == "SUPPORTED"
    assert result["warnings"]["AFTER_LOSS"]["verdict"] == "TOO_FEW"
    # By default only decision days are read.
    assert score.load(db)[0] == score.FROZEN_FROM and len(score.load(db)[2]) == 30


@pytest.mark.asyncio
async def test_one_big_loss_is_not_enough_and_nineteen_warned_trades_are_too_few():
    trips = [_trip("2026-10-27", 0, -5000.0, run=0.4)] + [_trip("2026-10-27", i, 100.0, run=0.3) for i in range(1, 20)]
    trips += [_trip("2026-10-28", 50 + i, 0.0) for i in range(5)]
    db = await _store(trips)
    spike = score.score(score.load(db)[2])["warnings"]["CHASED_SPIKE"]
    # Total −₹3,100 and a mean under the unwarned one, but without the one −₹5,000 trade the rest made money.
    assert spike["warned"]["total"] == -3100.0 and spike["verdict"] == "NOT_SUPPORTED"
    assert score.score(score.load(db)[2][1:])["warnings"]["CHASED_SPIKE"]["verdict"] == "TOO_FEW"


@pytest.mark.asyncio
async def test_a_trade_counts_as_checked_when_a_check_for_its_option_was_sent_in_the_15_minutes_before(capsys):
    trips = [_trip("2026-10-27", 1, -200.0, at="10:00:00"), _trip("2026-10-27", 2, 300.0, at="11:00:00"),
             _trip("2026-10-27", 3, 100.0, at="12:00:00", symbol="NIFTY26OCT22400CE")]
    checks = [("check:1", "2026-10-27", SYMBOL, "2026-10-27T09:50:00+05:30"),          # 10 min before trade 1
              ("check:2", "2026-10-27", SYMBOL, "2026-10-27T10:40:00+05:30"),          # 20 min before trade 2
              ("check:3", "2026-10-27", SYMBOL, "2026-10-27T11:58:00+05:30")]          # another option
    db = await _store(trips, checks)
    _first, _last, trades = score.load(db)
    assert [t["checked"] for t in trades] == [True, False, False]
    result = score.score(trades)
    assert result["checked"] == {"n": 1, "won": 0, "total": -200.0, "mean": -200.0}
    assert result["unchecked"]["n"] == 2
    assert score.main(["partner_watch_score"]) == 0
    text = capsys.readouterr().out
    assert text.startswith("Check warnings scored, 2026-10-27 to 2026-10-27 (frozen O26; decision days from 2026-10-27)")
    assert "3 closed trades on 1 day." in text and "  CHASED_SPIKE: TOO_FEW" in text
    assert "A verdict needs at least 20 warned trades and informs the owner; it changes nothing." in text


def test_nothing_stored_says_so(tmp_path):
    import sqlite3
    path = str(tmp_path / "empty.db")
    sqlite3.connect(path).close()
    first, last, trades = score.load(path)
    assert trades == []
    assert "No closed trade stored on a decision day yet." in score.render(score.FROZEN_FROM, score.FROZEN_FROM,
                                                                          score.score(trades))
