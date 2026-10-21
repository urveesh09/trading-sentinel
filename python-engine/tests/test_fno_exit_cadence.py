"""[SX-F1] The confirmed profit lock, the exit loop's recorded looks and the
exit arms replayed at the live clock."""
import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
import pytz

import fno_exit_cadence as cadence
import fno_exit_paths
from config import settings
from fno_exit_rules import evaluate_single_leg_exit
from tests.test_fno_profit_lock_and_reentry import LOCK, NOW, _pos

IST = pytz.timezone("Asia/Kolkata")
CONFIRMED = {**LOCK, "FNO_PROFIT_LOCK_CONFIRM_SEC": 8.0}


def _look(pos, bid, at, breach=None, params=CONFIRMED):
    decision = evaluate_single_leg_exit(pos, now_ist=at, fut_price=22610.0, exit_px_basis=bid, hard_flat=False,
                                        params=params, lock_breach_since=breach)
    pos.best_premium = decision.best_premium
    return decision


# ---------------------------------------------------------------- the lock

def test_one_look_under_the_floor_waits_and_a_second_one_sells():
    # Entry 200, best 240: armed (gain 40 >= 0.4 x 50), floor keeps half the gain = 220.
    pos = _pos(best_premium=240.0)
    first = _look(pos, 219.0, NOW)
    assert first.exit_reason == "" and first.lock_breach_since == NOW and first.profit_lock_floor == 220.0
    early = _look(pos, 218.0, NOW + timedelta(seconds=5), first.lock_breach_since)
    assert early.exit_reason == "" and early.lock_breach_since == NOW
    second = _look(pos, 218.0, NOW + timedelta(seconds=10), first.lock_breach_since)
    assert second.exit_reason == "profit_lock"


def test_a_recovery_above_the_floor_clears_the_first_look():
    pos = _pos(best_premium=240.0)
    first = _look(pos, 219.0, NOW)
    back = _look(pos, 221.0, NOW + timedelta(seconds=10), first.lock_breach_since)
    assert back.exit_reason == "" and back.lock_breach_since is None
    again = _look(pos, 219.0, NOW + timedelta(seconds=20), back.lock_breach_since)
    assert again.exit_reason == "" and again.lock_breach_since == NOW + timedelta(seconds=20)


def test_without_confirmation_the_first_look_sells_and_stops_never_wait():
    pos = _pos(best_premium=240.0)
    assert _look(pos, 219.0, NOW, params=LOCK).exit_reason == "profit_lock"
    # The underlying stop is protective: it sells on the first look whatever the lock state.
    stopped = evaluate_single_leg_exit(_pos(best_premium=240.0), now_ist=NOW, fut_price=22550.0,
                                       exit_px_basis=219.0, hard_flat=False, params=CONFIRMED)
    assert stopped.exit_reason == "underlying_stop"
    backstop = evaluate_single_leg_exit(_pos(best_premium=240.0), now_ist=NOW, fut_price=22610.0,
                                        exit_px_basis=149.0, hard_flat=False, params=CONFIRMED)
    assert backstop.exit_reason == "premium_backstop"


def test_the_live_setting_confirms_and_its_rollback_is_zero():
    from fno_exit_rules import live_single_leg_exit_params
    assert live_single_leg_exit_params(settings)["FNO_PROFIT_LOCK_CONFIRM_SEC"] == 8.0


# ---------------------------------------------------------------- the recorder

class _Decision:
    exit_reason = ""
    best_premium = 240.0
    profit_lock_floor = 220.0
    lock_breach_since = NOW
    trail_active = False
    trail_stop = None


class _Position:
    id, token, tradingsymbol, underlying, direction = 7, 12345, "NIFTY26O2722600CE", "NIFTY", "LONG"


@pytest.mark.asyncio
async def test_each_look_is_one_line_written_off_the_exit_path():
    await fno_exit_paths.record(NOW, "FNO_PAPER", _Position(), bid=219.0, ask=219.5, ltp=219.2, fut=22610.0,
                                decision=_Decision())
    [line] = fno_exit_paths.read_day(settings.RESEARCH_ARCHIVE_PATH, NOW.date().isoformat())
    assert line == {"at": NOW.isoformat(), "source": "FNO_PAPER", "position_id": 7, "token": 12345,
                    "tradingsymbol": "NIFTY26O2722600CE", "underlying": "NIFTY", "direction": "LONG",
                    "bid": 219.0, "ask": 219.5, "ltp": 219.2, "fut": 22610.0, "exit_reason": "",
                    "best_premium": 240.0, "lock_floor": 220.0, "lock_breach_since": NOW.isoformat(),
                    "trail_active": False, "trail_stop": None}


def test_recording_off_or_without_a_loop_never_raises(monkeypatch):
    fno_exit_paths.record(NOW, "FNO_PAPER", _Position(), bid=1, ask=1, ltp=1, fut=None, decision=_Decision())
    monkeypatch.setattr(settings, "FNO_EXIT_PATH_RECORDING", False)
    fno_exit_paths.record(NOW, "FNO_PAPER", _Position(), bid=1, ask=1, ltp=1, fut=None, decision=_Decision())
    assert fno_exit_paths.read_day(settings.RESEARCH_ARCHIVE_PATH, NOW.date().isoformat()) == []


# ---------------------------------------------------------------- the evaluator

DAY = NOW.date().isoformat()
ENTRY = NOW - timedelta(minutes=5)


def _export(tmp_path, looks, *, live_exit_at, live_reason="profit_lock", archive=()):
    root = tmp_path / "export"
    (root / "fno_exit_paths").mkdir(parents=True)
    con = sqlite3.connect(root / "fno-replay.sqlite")
    con.execute("CREATE TABLE fno_positions (id, source, tradingsymbol, token, underlying, direction, qty, "
                "entry_time, entry_date, entry_premium, entry_underlying, stop_underlying, target_underlying, "
                "premium_stop, atr_at_entry, status, exit_time, exit_premium, exit_reason, pnl)")
    con.execute("INSERT INTO fno_positions VALUES (7,'FNO_PAPER','NIFTY26O2722600CE',12345,'NIFTY','LONG',65,?,?,"
                "200.0,22600.0,22560.0,22800.0,150.0,30.0,'CLOSED',?,219.0,?,0)",
                (ENTRY.isoformat(), DAY, live_exit_at.isoformat(), live_reason))
    con.commit()
    con.close()
    with open(root / "fno_exit_paths" / f"{DAY}.jsonl", "w", encoding="utf-8") as handle:
        for at, bid in looks:
            handle.write(json.dumps({"at": at.isoformat(), "source": "FNO_PAPER", "position_id": 7, "bid": bid,
                                     "ltp": bid, "fut": 22610.0}) + "\n")
    if archive:
        from research_quote_collector import normalise_quote
        from fno_models import Contract
        from datetime import date
        option = Contract(token=12345, tradingsymbol="NIFTY26O2722600CE", name="NIFTY", expiry=date(2026, 10, 27),
                          strike=22600.0, instrument_type="CE", lot_size=65)
        future = Contract(token=999, tradingsymbol="NIFTY26OCTFUT", name="NIFTY", expiry=date(2026, 10, 27),
                          strike=0.0, instrument_type="FUT", lot_size=65)
        (root / "quotes" / DAY).mkdir(parents=True)
        with open(root / "quotes" / DAY / "quotes.jsonl.open", "w", encoding="utf-8") as handle:
            for at, bid, fut in archive:
                stamp = at.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")
                for contract, price in ((future, fut), (option, bid)):
                    raw = {"instrument_token": contract.token, "last_price": price, "timestamp": stamp,
                           "depth": {"buy": [{"price": price, "quantity": 75, "orders": 1}],
                                     "sell": [{"price": price + 0.5, "quantity": 75, "orders": 1}]}}
                    event = normalise_quote(contract, raw, source="KITE", mode="KITE_REST_FULL_LOWER_FREQUENCY",
                                            received_at=at.astimezone(timezone.utc), selection_reason="t",
                                            exchange="NFO")
                    handle.write(json.dumps(event, default=str) + "\n")
    return root


def test_arms_replay_the_live_looks_and_the_archive_after_the_exit(tmp_path):
    # Best 240 at NOW, one flicker to 219 (under the 220 floor) at NOW+10s, back to 226, then the
    # option runs: the archive after the live exit carries it to 260 and back to 225.
    looks = [(ENTRY, 200.0), (NOW, 240.0), (NOW + timedelta(seconds=10), 219.0)]
    archive = [(NOW + timedelta(seconds=20), 226.0, 22612.0), (NOW + timedelta(minutes=1), 260.0, 22640.0),
               (NOW + timedelta(minutes=2), 228.0, 22615.0), (NOW + timedelta(minutes=3), 225.0, 22612.0),
               (NOW + timedelta(minutes=4), 225.0, 22612.0)]
    root = _export(tmp_path, looks, live_exit_at=NOW + timedelta(seconds=10), archive=archive)
    out = cadence.evaluate(root, start=DAY, end=DAY)
    [position] = out["positions"]
    assert position["looks"] == {"live_loop": 3, "archive_after": 5}
    first, current = position["arms"]["LOCK_FIRST_LOOK"], position["arms"]["CURRENT"]
    # The old lock sold the flicker (as live did); the confirmed one held through it, then the floor
    # ratcheted to 230 at the 260 peak and two looks under it sold at 228 / 225.
    assert (first["exit_reason"], first["exit_premium"], first["observed_by"]) == ("profit_lock", 219.0, "LIVE_LOOP")
    assert (current["exit_reason"], current["exit_premium"], current["observed_by"]) == ("profit_lock", 225.0, "ARCHIVE")
    assert current["net_pnl"] > first["net_pnl"]
    assert out["arms"]["CURRENT"]["closed"] == 1 and out["skipped"] == {"no_recorded_path": 0,
                                                                         "path_ends_before_live_exit": 0}


def test_positions_without_a_full_recorded_path_are_reported_not_scored(tmp_path):
    root = _export(tmp_path, [(ENTRY, 200.0), (NOW, 240.0)], live_exit_at=NOW + timedelta(minutes=5))
    out = cadence.evaluate(root, start=DAY, end=DAY)
    assert out["positions"] == [] and out["skipped"]["path_ends_before_live_exit"] == 1
    empty = _export(tmp_path / "b", [], live_exit_at=NOW)
    assert cadence.evaluate(empty, start=DAY, end=DAY)["skipped"]["no_recorded_path"] == 1


def test_the_evaluator_is_inert_research():
    import ast
    from pathlib import Path
    root = Path(cadence.__file__).resolve().parent
    source = (root / "fno_exit_cadence.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert not imported & {"aiosqlite", "httpx", "kite_client", "main", "fno_executor", "fno_orchestrator",
                           "scheduler_setup", "fno_positions", "fno_dr_book", "performance"}
    assert source.count("sqlite3.connect(") == source.count("?mode=ro\", uri=True)")
    callers = [path.name for path in root.glob("*.py") if path.stem != "fno_exit_cadence"
               and "fno_exit_cadence" in path.read_text(encoding="utf-8", errors="ignore")]
    assert callers == []


def test_an_arm_still_open_when_the_looks_end_is_unresolved_not_filled(tmp_path):
    looks = [(ENTRY, 200.0), (NOW, 240.0), (NOW + timedelta(seconds=10), 219.0)]
    root = _export(tmp_path, looks, live_exit_at=NOW + timedelta(seconds=10))
    out = cadence.evaluate(root, start=DAY, end=DAY)
    current = out["positions"][0]["arms"]["CURRENT"]
    assert current["unresolved"] is True and current["exit_reason"] is None
    assert out["arms"]["CURRENT"] == {"closed": 0, "unresolved": 1, "net_pnl": 0.0}
