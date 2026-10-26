"""[O26] partner_watch_score: the check's warnings scored on stored trades, by the rule frozen before the days it
decides on (read-only). [O26d] Each warning is POSITIVE, NEGATIVE or UNKNOWN; the rule is its own frozen SPEC."""
import json

import aiosqlite
import pytest

import partner_watch as pw
import partner_watch_score as score
from config import settings

SYMBOL = "NIFTY26OCT22300PE"
NONE = {"state": "NONE"}
P, N, U = score.POSITIVE, score.NEGATIVE, score.UNKNOWN


def _loss(result=-700.0, minutes=5, bought=65, state="KNOWN"):
    return {"state": state, "result": result, "at": "10:05", "minutes": minutes, "bought": bought}


def _trip(day, n, realised, *, run=0.05, prior=NONE, usual=0.5, cash=10000.0, qty=65, value=None, final=1, exact=1,
          carried=0, closed=True, symbol=SYMBOL, at="10:00:00"):
    """A stored trade; by default every warning is known not to apply (NEGATIVE)."""
    value = 80.0 * qty if value is None else value
    return {"session_date": day, "position_key": f"{day}:{n}", "exchange": "NFO", "tradingsymbol": symbol,
            "product": "NRML", "first_at": f"{day}T{at}+05:30", "closed_at": f"{day}T10:30:00+05:30" if closed else None,
            "bought": qty, "sold": qty if closed else 0, "entry": 80.0, "exit": 70.0 if closed else None,
            "realised": realised if closed else None, "orders": 2, "exact": exact, "carried": carried, "run_pct": run,
            "prior_exit": json.dumps(prior) if prior is not None else None, "usual": usual, "cash": cash,
            "opening_order": f"o{n}", "opening_qty": qty, "opening_value": value, "opening_final": final,
            "opening_exact": exact, "paid_share": round(value / cash, 4) if cash else None,
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


def _ev(**row):
    trip = {"prior_exit": NONE, "usual": 0.5, "cash": 10000.0, "opening_qty": 65, "opening_value": 5200.0,
            "opening_final": 1, "run_pct": 0.05} | row
    return score.evidence_of(trip)


def test_each_warning_is_positive_negative_or_unknown_from_what_was_known_at_the_buy():
    """[O26d, independent review R2] A missing input is UNKNOWN, not "no warning"."""
    assert [_ev(run_pct=r)["CHASED_SPIKE"] for r in (0.1999, 0.2, None)] == [N, P, U]
    assert [_ev(prior_exit=p)["AFTER_LOSS"] for p in (
        None, NONE, _loss(), _loss(minutes=30), _loss(result=50.0), _loss(result=None, state="UNKNOWN"),
        _loss(result=None, state="UNKNOWN", minutes=40))] == [U, N, P, N, N, U, N]
    # Bigger after a loss: the opening order's units against the losing trade's; fills only add.
    assert [_ev(prior_exit=_loss(), opening_qty=q, opening_final=f)["BIGGER_AFTER_LOSS"]
            for q, f in ((130, 1), (65, 1), (65, 0), (130, 0), (None, 1))] == [P, N, U, P, U]
    assert _ev(prior_exit=NONE, opening_qty=130)["BIGGER_AFTER_LOSS"] == N
    assert _ev(prior_exit=None)["BIGGER_AFTER_LOSS"] == U
    # Size: the opening order's value over the first-known cash against 1.5 x the usual share.
    assert [_ev(usual=0.2, opening_value=v, opening_final=f)["UNUSUAL_SIZE"]
            for v, f in ((3100.0, 1), (3000.0, 1), (3000.0, 0), (3100.0, 0))] == [P, N, U, P]
    assert _ev(usual=None)["UNUSUAL_SIZE"] == U and _ev(cash=None)["UNUSUAL_SIZE"] == U
    assert _ev()["ANY"] == N
    assert _ev(run_pct=None)["ANY"] == U
    assert _ev(run_pct=None, usual=0.2, opening_value=3100.0)["ANY"] == P
    assert score.warnings_of({"run_pct": 0.25}) == {"CHASED_SPIKE", "ANY"}


def test_the_frozen_rule_does_not_move_when_the_live_thresholds_do(monkeypatch):
    """[O26d, independent review R6] The scorer imported the live spike and size thresholds: moving the spike one
    from 20% to 30% turned a stored 25% run from warned to not. The rule is now its own SPEC, named by SPEC_ID."""
    import partner_coach
    import partner_insights
    row = {"run_pct": 0.25, "prior_exit": _loss(minutes=20), "usual": 0.2, "cash": 10000.0, "opening_qty": 65,
           "opening_value": 3100.0, "opening_final": 1}
    before = score.evidence_of(row)
    assert before["CHASED_SPIKE"] == before["AFTER_LOSS"] == before["UNUSUAL_SIZE"] == P
    monkeypatch.setattr(partner_insights, "SPIKE_RUN_PCT", 0.30)
    monkeypatch.setattr(partner_insights, "USUAL_SIZE_MULT", 3.0)
    monkeypatch.setattr(partner_coach, "REENTRY_WINDOW_MIN", 10)
    assert score.evidence_of(row) == before
    # Editing the rule changes its identity; a new version is frozen again before the days it decides on.
    assert score.SPEC_ID == "v2-a3150fcf5a68"
    assert score.score([])["spec"] == score.SPEC_ID


@pytest.mark.asyncio
async def test_trades_without_the_evidence_are_left_out_not_counted_as_unwarned():
    """[O26d, independent review R2] 20 spike trades losing ₹100 and 20 winning trades with no evidence at all used
    to make CHASED_SPIKE SUPPORTED: the 20 were taken as unwarned. They are UNKNOWN: left out and counted."""
    trips = [_trip("2026-10-27", i, -100.0, run=0.25) for i in range(20)]
    trips += [_trip("2026-10-27", 100 + i, 10.0, run=None, prior=None, usual=None) for i in range(20)]
    db = await _store(trips)
    result = score.score(score.load(db)[2])
    spike = result["warnings"]["CHASED_SPIKE"]
    assert (spike["warned"]["n"], spike["unwarned"]["n"], spike["unknown"], spike["verdict"]) == (20, 0, 20, "TOO_FEW")
    assert result["warnings"]["ANY"]["unknown"] == 20 and result["warnings"]["ANY"]["verdict"] == "TOO_FEW"
    # Ten trades known to have no warning, all winning: now the comparison has a side to compare with.
    trips += [_trip("2026-10-28", 200 + i, 50.0) for i in range(10)]
    db = await _store(trips[40:])
    result = score.score(score.load(db)[2])
    spike = result["warnings"]["CHASED_SPIKE"]
    assert (spike["warned"]["n"], spike["unwarned"]["n"], spike["unknown"], spike["verdict"]) == (
        20, 10, 20, "SUPPORTED")


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
    assert spike["verdict"] == "SUPPORTED" and spike["warned"] == {"n": 20, "won": 0, "total": -2000.0, "mean": -100.0,
                                                                   "from_orders": 0}
    assert spike["unwarned"] == {"n": 10, "won": 10, "total": 500.0, "mean": 50.0, "from_orders": 0}
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
    trips = [_trip("2026-10-27", 1, -200.0, at="10:00:00"), _trip("2026-10-27", 2, 300.0, at="11:00:00", exact=0),
             _trip("2026-10-27", 3, 100.0, at="12:00:00", symbol="NIFTY26OCT22400CE", run=None)]
    checks = [("check:1", "2026-10-27", SYMBOL, "2026-10-27T09:50:00+05:30"),          # 10 min before trade 1
              ("check:2", "2026-10-27", SYMBOL, "2026-10-27T10:40:00+05:30"),          # 20 min before trade 2
              ("check:3", "2026-10-27", SYMBOL, "2026-10-27T11:58:00+05:30")]          # another option
    db = await _store(trips, checks)
    _first, _last, trades = score.load(db)
    assert [t["checked"] for t in trades] == [True, False, False]
    result = score.score(trades)
    assert result["checked"] == {"n": 1, "won": 0, "total": -200.0, "mean": -200.0, "from_orders": 0}
    assert result["unchecked"]["n"] == 2 and result["unchecked"]["from_orders"] == 1
    assert score.main(["partner_watch_score"]) == 0
    text = capsys.readouterr().out
    assert text.startswith(f"Check warnings scored, 2026-10-27 to 2026-10-27 (frozen rule {score.SPEC_ID}; decision "
                           "days from 2026-10-27)")
    assert "3 closed trades on 1 day (1 with fills from the orders)." in text and "  CHASED_SPIKE: TOO_FEW" in text
    assert "    unknown:  1 trades (an input missing at the buy): left out" in text
    assert "A verdict needs at least 20 warned trades and informs the owner; it changes nothing." in text


def test_nothing_stored_says_so(tmp_path):
    import sqlite3
    path = str(tmp_path / "empty.db")
    sqlite3.connect(path).close()
    first, last, trades = score.load(path)
    assert trades == []
    assert "No closed trade stored on a decision day yet." in score.render(score.FROZEN_FROM, score.FROZEN_FROM,
                                                                          score.score(trades))
