"""End-to-end F&O policy replay on a synthetic but format-genuine archive."""
from datetime import date, datetime, timedelta, timezone
import gzip
import hashlib
import json
import sqlite3

import pytest
import pytz

import options_math
from fno_chain import RISK_FREE_RATE, years_to_expiry
from fno_costs import calc_fno_costs
from fno_models import Contract
from fno_policy_replay import run_replay
from research_archive import _canonical_json
from research_quote_collector import normalise_quote

IST = pytz.timezone("Asia/Kolkata")
DAY = date(2026, 9, 14)            # Monday
EXPIRY = date(2026, 9, 22)
FUT = Contract(9001, "NIFTY26SEPFUT", "NIFTY", date(2026, 9, 29), 0.0, "FUT", 65, 0.1)
IV = 0.15


def _sessions(n):
    days, day = [], DAY - timedelta(days=1)
    while len(days) < n:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    return sorted(days)


def _candles():
    """Rising prior sessions (EMA21 > EMA50), a tight 09:15-09:45 range today,
    and a 3x-volume breakout bar 09:55 that closes above OR high + 0.25 ATR."""
    rows, price = [], 24_800.0
    for session in _sessions(12):
        for i in range(75):
            stamp = datetime.combine(session, datetime.min.time()) + timedelta(hours=9, minutes=15 + 5 * i)
            price += 0.25
            rows.append((stamp, price - 1, price + 3, price - 3, price, 1000.0))
    base = price
    for i in range(10):                        # 09:15 .. 10:00 bars today
        stamp = datetime.combine(DAY, datetime.min.time()) + timedelta(hours=9, minutes=15 + 5 * i)
        if i < 8:
            rows.append((stamp, base, base + 3, base - 3, base + (1 if i % 2 else -1), 1000.0))
        elif i == 8:                           # 09:55 breakout bar
            rows.append((stamp, base + 1, base + 12, base, base + 10, 3000.0))
        else:
            rows.append((stamp, base + 10, base + 11, base + 9, base + 10, 1000.0))
    return rows, base + 10


def _quote_events(base_forward, start, minutes, path=lambda minute: 0.0, iv=IV):
    """``path(minute)`` offsets the futures price from the breakout close."""
    events = []
    T_strikes = [round(base_forward / 50) * 50 + 50 * k for k in range(-3, 4)]
    for m in range(minutes):
        at = start + timedelta(minutes=m)
        forward = base_forward + path(m)
        stamp = at.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")
        ltt = (at - timedelta(seconds=2)).astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")
        T = years_to_expiry(EXPIRY, at.astimezone(IST))

        def raw(token, ltp, bid, ask):
            return {"instrument_token": token, "last_price": ltp, "oi": 60_000, "volume": 25_000,
                    "timestamp": stamp, "last_trade_time": ltt,
                    "depth": {"buy": [{"price": bid, "quantity": 650, "orders": 3}],
                              "sell": [{"price": ask, "quantity": 650, "orders": 3}]}}
        events.append(normalise_quote(FUT, raw(FUT.token, forward, forward - 0.5, forward + 0.5),
                                      source="KITE", mode="KITE_REST_FULL_LOWER_FREQUENCY", received_at=at,
                                      selection_reason="underlying_future_reference", exchange="NFO"))
        for strike in T_strikes:
            for kind in ("CE", "PE"):
                token = 10_000 + strike * 10 + (1 if kind == "CE" else 2)
                contract = Contract(token, f"NIFTY26922{strike}{kind}", "NIFTY", EXPIRY, float(strike), kind, 65)
                mid = options_math.black76_price(forward, strike, T, iv, RISK_FREE_RATE, kind == "CE")
                bid, ask = round(mid * 0.998, 2), round(mid * 1.002, 2)
                events.append(normalise_quote(contract, raw(token, round(mid, 2), bid, ask), source="KITE",
                                              mode="KITE_REST_FULL_LOWER_FREQUENCY", received_at=at,
                                              selection_reason=f"atm_window_expiry={EXPIRY}", exchange="NFO"))
    return events


def _write_dataset(tmp_path, path=lambda minute: 0.0, iv=IV):
    candles, breakout_close = _candles()
    start = IST.localize(datetime.combine(DAY, datetime.min.time()) + timedelta(hours=9, minutes=50, seconds=5))
    events = _quote_events(breakout_close, start.astimezone(timezone.utc), 70, path, iv)
    payload = b"".join(_canonical_json(event) + b"\n" for event in events)
    digest = hashlib.sha256(payload).hexdigest()
    folder = tmp_path / "quotes" / DAY.isoformat()
    folder.mkdir(parents=True)
    segment = folder / f"quotes-{digest[:16]}.jsonl.gz"
    segment.write_bytes(gzip.compress(payload, mtime=0))
    segment.with_suffix(".manifest.json").write_text(json.dumps({
        "kind": "observed_quote_segment", "day": DAY.isoformat(), "event_count": len(events),
        "raw_sha256": digest, "path": segment.name}))
    con = sqlite3.connect(tmp_path / "fno-replay.sqlite")
    con.execute("CREATE TABLE fut_candles (instrument_token, tradingsymbol, interval, datetime, open, high, low,"
                " close, volume, oi)")
    con.executemany("INSERT INTO fut_candles VALUES (?,?,?,?,?,?,?,?,?,?)",
                    [(FUT.token, FUT.tradingsymbol, "5minute", s.strftime("%Y-%m-%d %H:%M:%S"), o, h, l, c, v, 0)
                     for s, o, h, l, c, v in candles])
    con.execute("CREATE TABLE fno_signals (evaluated_at, bar_ts, regime)")
    con.execute("INSERT INTO fno_signals VALUES (?,?,?)",
                (f"{DAY}T09:20:00+05:30", f"{DAY} 09:15:00", "REGIME_1_NORMAL"))
    con.execute("CREATE TABLE fno_positions (source, status, exit_time, pnl, tradingsymbol, lots, entry_time,"
                " entry_premium, exit_premium, exit_reason, bar_ts, entry_date)")
    con.execute("CREATE TABLE fno_dr_positions (source, status, closed_at, pnl)")
    con.commit()
    con.close()
    (tmp_path / "manifest.json").write_text(json.dumps({
        "schema": "sentinel_fno_replay_dataset_v1", "source": "TEST", "quote_days": [DAY.isoformat()],
        "unsealed_days": []}))
    return tmp_path


@pytest.fixture
def dataset(tmp_path):
    return _write_dataset(tmp_path)


def _run_up_then_reverse(minute):
    """Flat until the 10:00 entry, +60 points by 10:30, back to +20 by 10:50."""
    if minute <= 11:
        return 0.0
    if minute <= 40:
        return 60.0 * (minute - 11) / 29
    return max(20.0, 60.0 - 2.0 * (minute - 40))


def test_replay_enters_breakout_at_ask_and_exits_on_time_stop_at_bid(dataset):
    result = run_replay(dataset, start=DAY.isoformat(), end=DAY.isoformat())
    assert result["archive_exclusions"] == {}
    trades = [t for t in result["trades"] if "net_pnl" in t]
    assert len(trades) == 1, result["funnel"]
    trade = trades[0]
    assert trade["bar_ts"] == f"{DAY} 09:55:00" and trade["direction"] == "LONG"
    assert trade["tradingsymbol"].endswith("CE")
    entry = datetime.fromisoformat(trade["entry_time"])
    assert entry >= IST.localize(datetime(2026, 9, 14, 10, 0))     # only after the bar closed
    # Flat underlying: no target, so the 45-minute time stop fires (premium is under water).
    assert trade["exit_reason"] == "time_stop"
    assert (datetime.fromisoformat(trade["exit_time"]) - entry) >= timedelta(minutes=45)
    qty = trade["lots_at_exit"] * 65
    expected = (trade["exit_premium"] - trade["entry_premium"]) * qty \
        - calc_fno_costs(trade["entry_premium"], trade["exit_premium"], qty)
    assert trade["net_pnl"] == pytest.approx(expected, abs=1e-3)
    assert trade["exit_premium"] < trade["entry_premium"]            # sold at bid, bought at ask
    assert result["notes"]["grid_phase_live_aligned"] == 1


def test_fast_exit_manages_between_grid_ticks(dataset):
    base = run_replay(dataset, start=DAY.isoformat(), end=DAY.isoformat())
    fast = run_replay(dataset, start=DAY.isoformat(), end=DAY.isoformat(), policy="FNO_FAST_EXIT")
    b, f = (next(t for t in r["trades"] if "net_pnl" in t) for r in (base, fast))
    assert b["entry_time"] == f["entry_time"]
    assert datetime.fromisoformat(f["exit_time"]) <= datetime.fromisoformat(b["exit_time"])


def test_trend_run_trails_out_in_profit_and_candidates_act_after_target(tmp_path):
    data = _write_dataset(tmp_path, _run_up_then_reverse, iv=0.08)    # cheap premium -> 2 lots
    base = next(t for t in run_replay(data, start=DAY.isoformat(), end=DAY.isoformat())["trades"] if "net_pnl" in t)
    assert base["exit_reason"] == "trail_stop" and base["net_pnl"] > 0 and base["lots_at_exit"] == 2
    partial = run_replay(data, start=DAY.isoformat(), end=DAY.isoformat(), policy="FNO_PARTIAL_TRAIL")
    trade = next(t for t in partial["trades"] if "net_pnl" in t)
    assert partial["notes"]["partial_banked"] == 1
    assert trade["fills"][0]["kind"] == "PARTIAL" and trade["lots_at_exit"] == 1
    assert trade["net_pnl"] == pytest.approx(
        trade["fills"][0]["net_pnl"] + (trade["exit_premium"] - trade["entry_premium"]) * 65
        - calc_fno_costs(trade["entry_premium"], trade["exit_premium"], 65), abs=1e-3)
    pyramid = run_replay(data, start=DAY.isoformat(), end=DAY.isoformat(), policy="FNO_HOUSE_MONEY_PYRAMID")
    # Already at the two-lot ceiling: the hard cap wins over the pyramid idea.
    assert pyramid["notes"].get("pyramid_skipped_max_lots") == 1


def test_house_money_pyramid_adds_one_lot_after_profit_is_locked(tmp_path):
    # IV 0.12: one lot at entry (risk per lot above half the 2% budget) and
    # the two-lot position stays under the structural max-loss cap.
    data = _write_dataset(tmp_path, _run_up_then_reverse, iv=0.12)
    result = run_replay(data, start=DAY.isoformat(), end=DAY.isoformat(), policy="FNO_HOUSE_MONEY_PYRAMID")
    trade = next(t for t in result["trades"] if "net_pnl" in t)
    added = [f for f in trade["fills"] if f["kind"] == "PYRAMID_ADD"]
    assert result["notes"].get("pyramid_added") == 1, result["notes"]
    assert len(added) == 1 and trade["lots_at_exit"] == 2 and added[0]["at"] > trade["entry_time"]


def test_pyramid_never_breaks_the_structural_loss_cap(tmp_path):
    data = _write_dataset(tmp_path, _run_up_then_reverse)               # pricier premium
    result = run_replay(data, start=DAY.isoformat(), end=DAY.isoformat(), policy="FNO_HOUSE_MONEY_PYRAMID")
    trade = next(t for t in result["trades"] if "net_pnl" in t)
    assert result["notes"].get("pyramid_skipped_constitution") == 1
    assert not [f for f in trade["fills"] if f["kind"] == "PYRAMID_ADD"] and trade["lots_at_exit"] == 1


def test_replay_is_inert_research():
    """No runtime caller, broker/order/scheduler import or writable database."""
    import ast
    from pathlib import Path
    import fno_policy_replay
    root = Path(fno_policy_replay.__file__).resolve().parent
    source = (root / "fno_policy_replay.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert not imported & {"aiosqlite", "httpx", "kite_client", "main", "fno_executor", "fno_orchestrator",
                           "scheduler_setup", "fno_positions", "fno_dr_book", "performance"}
    assert source.count("sqlite3.connect(") == source.count('?mode=ro", uri=True)')
    callers = [path.name for path in root.glob("*.py") if path.stem != "fno_policy_replay"
               and "fno_policy_replay" in path.read_text(encoding="utf-8", errors="ignore")]
    assert callers == []
