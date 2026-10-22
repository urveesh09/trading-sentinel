"""[SX-F1] The confirmed profit lock, the exit loop's recorded looks and the
exit arms replayed at the live clock. [A22-R3/R6] The recorder is bounded and
counts every drop; the evaluator scores only whole evidence that reproduces
the live exit."""
import json
import sqlite3
import threading
import time
from datetime import timedelta, timezone

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


@pytest.fixture(autouse=True)
def _fresh_recorder():
    fno_exit_paths.close()
    for key in fno_exit_paths._counts:
        fno_exit_paths._counts[key] = 0
    fno_exit_paths._first_looks.clear()
    yield
    fno_exit_paths.close()


def _record(params=None, at=NOW):
    return fno_exit_paths.record(at, "FNO_PAPER", _Position(), bid=219.0, ask=219.5, ltp=219.2, fut=22610.0,
                                 decision=_Decision(), params=params)


def _lines():
    return fno_exit_paths.read_day(settings.RESEARCH_ARCHIVE_PATH, NOW.date().isoformat())


def test_each_look_is_one_line_written_off_the_exit_path():
    assert _record() is True and fno_exit_paths.flush()
    [line] = _lines()
    assert line == {"at": NOW.isoformat(), "source": "FNO_PAPER", "position_id": 7, "token": 12345,
                    "tradingsymbol": "NIFTY26O2722600CE", "underlying": "NIFTY", "direction": "LONG",
                    "bid": 219.0, "ask": 219.5, "ltp": 219.2, "fut": 22610.0, "exit_reason": "",
                    "best_premium": 240.0, "lock_floor": 220.0, "lock_breach_since": NOW.isoformat(),
                    "trail_active": False, "trail_stop": None}
    assert fno_exit_paths.stats()["written"] == 1


def test_the_settings_ride_on_a_positions_first_look_and_a_digest_on_every_look():
    params = {**CONFIRMED, "FNO_HARD_FLAT_MIN": 910}
    assert _record(params) and _record(params, at=NOW + timedelta(seconds=10)) and fno_exit_paths.flush()
    first, second = _lines()
    assert first["params"] == params and "params" not in second
    assert first["params_sha"] == second["params_sha"] == fno_exit_paths.params_digest(params)


def test_recording_off_writes_nothing(monkeypatch):
    monkeypatch.setattr(settings, "FNO_EXIT_PATH_RECORDING", False)
    assert _record() is False and fno_exit_paths.flush()
    assert _lines() == []


def test_a_stuck_disk_never_blocks_an_exit_and_every_drop_is_counted(monkeypatch):
    # The audit's probe: with writes blocked, looks piled up without bound.
    release = threading.Event()
    real = fno_exit_paths._append_batch
    monkeypatch.setattr(fno_exit_paths, "_append_batch", lambda *a: (release.wait(5), real(*a)))
    monkeypatch.setattr(fno_exit_paths, "MAX_QUEUE", 3)
    monkeypatch.setattr(fno_exit_paths, "BATCH_MAX", 2)
    started = time.monotonic()
    outcomes = [_record() for _ in range(100)]
    assert time.monotonic() - started < 1.0                      # no look waited for the disk
    stats = fno_exit_paths.stats()
    # Held at most: the queue (3) plus the one batch the writer is stuck on (2).
    assert stats["queued"] == sum(outcomes) <= 5 and stats["dropped_queue_full"] == 100 - sum(outcomes)
    release.set()
    assert fno_exit_paths.flush()
    assert fno_exit_paths.stats()["written"] == sum(outcomes)


def test_a_full_session_file_or_the_archive_reserve_drops_and_counts(monkeypatch):
    monkeypatch.setattr(fno_exit_paths, "DAY_MAX_BYTES", 10)
    assert _record() and fno_exit_paths.flush()
    assert fno_exit_paths.stats()["dropped_day_cap"] == 1
    monkeypatch.setattr(fno_exit_paths, "DAY_MAX_BYTES", 32 * 1024 * 1024)
    monkeypatch.setattr(settings, "RESEARCH_RESERVED_FREE_BYTES", 10 ** 18)     # the disk reserve is reached
    assert _record() and fno_exit_paths.flush()
    assert fno_exit_paths.stats()["dropped_storage"] == 1
    assert _lines() == []


def test_close_drains_what_was_queued():
    assert _record()
    fno_exit_paths.close()
    assert len(_lines()) == 1


# ---------------------------------------------------------------- the evaluator

DAY = NOW.date().isoformat()
ENTRY = NOW - timedelta(minutes=5)
OLD_LIVE = {**LOCK, "FNO_PROFIT_LOCK_CONFIRM_SEC": 0.0, "FNO_HARD_FLAT_MIN": 910}


def _steady(until, bid=200.0, step=30):
    """Looks every ``step`` seconds from the entry up to (not including) ``until``."""
    out, at = [], ENTRY
    while at < until:
        out.append((at, bid))
        at += timedelta(seconds=step)
    return out


FLICKER = _steady(NOW) + [(NOW, 240.0), (NOW + timedelta(seconds=10), 219.0)]
RUN_AFTER = [(NOW + timedelta(seconds=20), 226.0, 22612.0), (NOW + timedelta(minutes=1), 260.0, 22640.0),
             (NOW + timedelta(minutes=2), 228.0, 22615.0), (NOW + timedelta(minutes=3), 225.0, 22612.0),
             (NOW + timedelta(minutes=4), 225.0, 22612.0)]


def _export(tmp_path, looks, *, live_exit_at, live_reason="profit_lock", live_premium=219.0, archive=(),
            params=OLD_LIVE, line_extra=None):
    root = tmp_path / "export"
    (root / "fno_exit_paths").mkdir(parents=True)
    con = sqlite3.connect(root / "fno-replay.sqlite")
    con.execute("CREATE TABLE fno_positions (id, source, tradingsymbol, token, underlying, direction, qty, "
                "entry_time, entry_date, entry_premium, entry_underlying, stop_underlying, target_underlying, "
                "premium_stop, atr_at_entry, status, exit_time, exit_premium, exit_reason, pnl)")
    con.execute("INSERT INTO fno_positions VALUES (7,'FNO_PAPER','NIFTY26O2722600CE',12345,'NIFTY','LONG',65,?,?,"
                "200.0,22600.0,22560.0,22800.0,150.0,30.0,'CLOSED',?,?,?,0)",
                (ENTRY.isoformat(), DAY, live_exit_at.isoformat(), live_premium, live_reason))
    con.commit()
    con.close()
    digest = fno_exit_paths.params_digest(params) if params is not None else None
    with open(root / "fno_exit_paths" / f"{DAY}.jsonl", "w", encoding="utf-8") as handle:
        for i, (at, bid) in enumerate(looks):
            line = {"at": at.isoformat(), "source": "FNO_PAPER", "position_id": 7, "token": 12345,
                    "tradingsymbol": "NIFTY26O2722600CE", "bid": bid, "ltp": bid, "fut": 22610.0}
            if params is not None:
                line["params_sha"] = digest
                if i == 0:
                    line["params"] = params
            line.update((line_extra or {}).get(i, {}))
            handle.write(json.dumps(line) + "\n")
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
    # Live ran the first-look lock (recorded with the looks): best 240, one flicker to 219 under the 220
    # floor sold. The archive after the live exit carries the option to 260 and back to 225.
    root = _export(tmp_path, FLICKER, live_exit_at=NOW + timedelta(seconds=10), archive=RUN_AFTER)
    out = cadence.evaluate(root, start=DAY, end=DAY)
    [position] = out["positions"]
    assert position["looks"] == {"live_loop": len(FLICKER), "archive_after": 5}
    current, confirmed = position["arms"]["CURRENT"], position["arms"]["LOCK_CONFIRMED"]
    # CURRENT is the recorded live configuration and reproduces the live exit; the confirmed lock held
    # through the flicker, the floor ratcheted to 230 at the 260 peak and two looks under it sold at 225.
    assert (current["exit_reason"], current["exit_premium"], current["observed_by"]) == (
        "profit_lock", 219.0, "LIVE_LOOP")
    assert position["arms"]["LOCK_FIRST_LOOK"] == current
    assert (confirmed["exit_reason"], confirmed["exit_premium"], confirmed["observed_by"]) == (
        "profit_lock", 225.0, "ARCHIVE")
    assert out["paired"]["LOCK_CONFIRMED"] == {
        "both_resolved": 1, "delta_vs_current": round(confirmed["net_pnl"] - current["net_pnl"], 2)}
    assert confirmed["net_pnl"] > current["net_pnl"]
    assert out["coverage"] == {"closed_positions": 1, "scored": 1}
    assert set(out["skipped"].values()) == {0} and out["mismatches"] == []


def test_a_baseline_that_does_not_reproduce_the_live_exit_is_not_scored(tmp_path):
    # The audit's counterexample: the stored exit is an underlying stop at ₹0, but CURRENT replays a
    # profit lock. Counting CURRENT's profit would credit a rule with a trade it never made.
    root = _export(tmp_path, FLICKER, live_exit_at=NOW + timedelta(seconds=10), live_reason="underlying_stop",
                   live_premium=200.0, archive=RUN_AFTER)
    out = cadence.evaluate(root, start=DAY, end=DAY)
    assert out["positions"] == [] and out["skipped"]["baseline_mismatch"] == 1
    assert all(total == {"closed": 0, "unresolved": 0, "net_pnl": 0.0} for total in out["arms"].values())
    [mismatch] = out["mismatches"]
    assert (mismatch["live"]["exit_reason"], mismatch["current"]["exit_reason"]) == ("underlying_stop",
                                                                                    "profit_lock")
    # The same exit at another price (beyond 1%) is a mismatch too.
    off = _export(tmp_path / "b", FLICKER, live_exit_at=NOW + timedelta(seconds=10), live_premium=215.0)
    assert cadence.evaluate(off, start=DAY, end=DAY)["skipped"]["baseline_mismatch"] == 1


def test_evidence_without_its_settings_or_its_contract_or_with_gaps_is_reported_not_scored(tmp_path):
    exit_at = NOW + timedelta(seconds=10)
    cases = {
        "settings_unbound": dict(params=None),
        "settings_changed_mid_trade": dict(line_extra={3: {"params_sha": "0" * 16}}),
        "contract_mismatch": dict(line_extra={3: {"token": 54321}}),
        "observation_gap": dict(looks=[(ENTRY, 200.0), (NOW, 240.0), (exit_at, 219.0)]),
    }
    for reason, kwargs in cases.items():
        looks = kwargs.pop("looks", FLICKER)
        root = _export(tmp_path / reason, looks, live_exit_at=exit_at, **kwargs)
        out = cadence.evaluate(root, start=DAY, end=DAY)
        assert out["positions"] == [] and out["skipped"][reason] == 1, reason


def test_positions_without_a_full_recorded_path_are_reported_not_scored(tmp_path):
    root = _export(tmp_path, _steady(NOW + timedelta(seconds=1)), live_exit_at=NOW + timedelta(minutes=5))
    out = cadence.evaluate(root, start=DAY, end=DAY)
    assert out["positions"] == [] and out["skipped"]["path_ends_before_live_exit"] == 1
    empty = _export(tmp_path / "b", [], live_exit_at=NOW)
    assert cadence.evaluate(empty, start=DAY, end=DAY)["skipped"]["no_recorded_path"] == 1


def test_the_archive_is_used_only_up_to_its_first_long_gap(tmp_path):
    # Quotes at +20 s, then nothing until +10 min: the quote after the gap is not passed, so the
    # confirmed lock is still open when the evidence ends (never filled at the late price).
    gapped = RUN_AFTER[:1] + [(NOW + timedelta(minutes=10), 150.0, 22500.0)]
    root = _export(tmp_path, FLICKER, live_exit_at=NOW + timedelta(seconds=10), archive=gapped)
    [position] = cadence.evaluate(root, start=DAY, end=DAY)["positions"]
    assert position["looks"]["archive_after"] == 1
    assert position["arms"]["LOCK_CONFIRMED"]["unresolved"] is True


def test_the_evaluator_is_inert_research():
    import ast
    from pathlib import Path
    root = Path(cadence.__file__).resolve().parent
    source = (root / "fno_exit_cadence.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert not imported & {"aiosqlite", "httpx", "kite_client", "main", "fno_executor", "fno_orchestrator",
                           "scheduler_setup", "fno_positions", "fno_dr_book", "performance", "config"}
    assert source.count("sqlite3.connect(") == source.count("?mode=ro\", uri=True)")
    callers = [path.name for path in root.glob("*.py") if path.stem != "fno_exit_cadence"
               and "fno_exit_cadence" in path.read_text(encoding="utf-8", errors="ignore")]
    assert callers == []


def test_an_arm_still_open_when_the_looks_end_is_unresolved_not_filled(tmp_path):
    root = _export(tmp_path, FLICKER, live_exit_at=NOW + timedelta(seconds=10))
    out = cadence.evaluate(root, start=DAY, end=DAY)
    confirmed = out["positions"][0]["arms"]["LOCK_CONFIRMED"]
    assert confirmed["unresolved"] is True and confirmed["exit_reason"] is None
    assert out["arms"]["LOCK_CONFIRMED"] == {"closed": 0, "unresolved": 1, "net_pnl": 0.0}
    assert out["paired"]["LOCK_CONFIRMED"] == {"both_resolved": 0, "delta_vs_current": 0.0}
