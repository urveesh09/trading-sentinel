"""Regression tests for the Oct 19 2026 Production audit (non-expiry items).

O19-E1 EDGE morning scan scores the last completed session, O19-P1 partner
update spacing per card / reminder outside the cap, O19-P2 unsendable cards
expire, O19-S1/S2 Smart held marks and named halts, O19-O1 overnight cash
split, O19-F1 profit-lock replay arms, O19-B1 bootstrap order, O19-M2
MOM_RS_PULLBACK shadow variant.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import aiosqlite
import pandas as pd
import pytest
import pytz

from config import settings

IST = pytz.timezone("Asia/Kolkata")


# ---------------------------------------------------------------------------
# O19-E1: the 09:30 EDGE scan scores yesterday's completed bars
# ---------------------------------------------------------------------------

def _edge_cache(tmp_path, today: str):
    from tests.test_edge_overnight_paper import HISTORY
    path = tmp_path / "cache.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE ohlcv_cache (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, "
                     "close REAL, volume REAL, PRIMARY KEY (ticker, date))")
        for ticker, price in (("PENNY", 20.0), ("BIG", 500.0), ("NIFTYBEES", 250.0)):
            conn.executemany("INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?)",
                             [(ticker, d, price, price * 1.01, price * 0.99, price, 100000.0) for d in HISTORY])
        # The 09:20 screener's daily fetch caches today's unfinished candle for its names only.
        conn.execute("INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?)", ("BIG", today, 500, 501, 499, 500, 9000.0))
    return str(path)


def test_edge_scan_before_today_scores_the_last_completed_session(tmp_path):
    import penny_edge_live
    from tests.test_edge_overnight_paper import HISTORY, TODAY
    db = _edge_cache(tmp_path, TODAY.isoformat())
    newest = penny_edge_live.scan_today(db_path=db)
    assert newest["date"] == TODAY.isoformat() and newest["eligible_tickers"] == 1   # the Oct 19 shape
    completed = penny_edge_live.scan_today(db_path=db, before_date=TODAY.isoformat())
    assert completed["date"] == HISTORY[-1] and completed["eligible_tickers"] == 3


@pytest.mark.asyncio
async def test_orchestrator_asks_for_the_session_before_today(tmp_path, monkeypatch):
    import penny_edge_orchestrator as peo
    seen = {}

    def scan(**kwargs):
        seen.update(kwargs)
        raise RuntimeError("stop after the call")

    monkeypatch.setattr(peo.pel, "scan_today", scan)
    monkeypatch.setattr(peo, "_edge_paper_disabled", lambda: False)
    now = IST.localize(datetime(2026, 10, 19, 9, 30, 5))
    summary = await peo.run_penny_edge_scan(None, str(tmp_path / "ledger.db"), now_fn=lambda: now)
    assert seen["before_date"] == "2026-10-19"
    assert summary["status"] == "ERROR"


# ---------------------------------------------------------------------------
# O19-P1: per-card spacing below the tick; the reminder is outside the cap
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_spacing_is_per_card_and_reminders_skip_the_cap(tmp_path, monkeypatch):
    import hedge_advisory as ha
    db = str(tmp_path / "advisory.db")
    t0 = IST.localize(datetime(2026, 10, 19, 15, 10, 5))
    gap = timedelta(seconds=45)

    async def send(key, advisory, event, at, cap=4):
        reminder = event == "SESSION_EXIT_REMINDER"
        token = await ha._claim(db, "manual_advisory_update", key, now=at, min_gap=gap,
                                gap_counts=lambda prior: prior.get("advisory_id") == advisory,
                                daily_cap=None if reminder else cap,
                                cap_counts=lambda prior: prior.get("event_type") != "SESSION_EXIT_REMINDER",
                                detail={"advisory_id": advisory, "event_type": event})
        if token is None:
            return False
        async with aiosqlite.connect(db) as conn:
            await conn.execute("UPDATE partner_hedge_messages SET delivered=1, claim_token=NULL WHERE dedup_key=?",
                               (key,))
            await conn.commit()
        return True

    # Oct 19: SENSEX and NIFTY reminders in the same tick -> both go now.
    assert await send("r-sensex", "sensex", "SESSION_EXIT_REMINDER", t0)
    assert await send("r-nifty", "nifty", "SESSION_EXIT_REMINDER", t0 + timedelta(seconds=1))
    # The SENSEX target 30 s later waits for its own card's gap, not two minutes.
    assert not await send("t-sensex", "sensex", "TARGET_ZONE", t0 + timedelta(seconds=30))
    assert await send("t-sensex", "sensex", "TARGET_ZONE", t0 + timedelta(seconds=60))
    # The cap still bounds target/invalidation updates but never a reminder.
    assert not await send("t-nifty", "nifty", "TARGET_ZONE", t0 + timedelta(seconds=90), cap=1)
    assert await send("r-third", "third", "SESSION_EXIT_REMINDER", t0 + timedelta(seconds=90))


def test_dispatcher_uses_the_per_card_contract():
    import inspect
    import partner_manual_advisory as pma
    src = inspect.getsource(pma.dispatch_queued_management_update)
    assert "min_gap=MANAGEMENT_UPDATE_GAP" in src and "gap_counts=" in src and "cap_counts=" in src
    assert pma.MANAGEMENT_UPDATE_GAP < timedelta(minutes=1)


# ---------------------------------------------------------------------------
# O19-P2: a card that can no longer be sent stops being offered
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unsendable_queued_cards_expire(tmp_path, monkeypatch):
    from partner_manual_advisory import load_advisory_cards, run_intraday_session_lifecycle
    from tests.test_partner_buyer import NOW, _persist
    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", False)
    monkeypatch.setattr(settings, "PARTNER_MANUAL_ADVISORY_SEND_UNQUALIFIED", True)
    store = str(tmp_path / "advisory.db")
    _c, _v, stored = await _persist(store, True, monkeypatch)
    deadline = datetime.fromisoformat(json.loads(json.dumps(stored))["entry_deadline"])
    await run_intraday_session_lifecycle(store, now=deadline - timedelta(seconds=1))
    [card] = (await load_advisory_cards(store))["cards"]
    assert card["status"] == "QUEUED" and card["can_send"]
    await run_intraday_session_lifecycle(store, now=deadline + timedelta(seconds=1))
    [card] = (await load_advisory_cards(store))["cards"]
    assert card["status"] == "EXPIRED_UNSENT" and not card["can_send"]


# ---------------------------------------------------------------------------
# O19-S1/S2: Smart held names are quoted; halts name their condition
# ---------------------------------------------------------------------------

def test_halt_events_name_the_condition_and_skip_exit_only_batches():
    from penny_smart_shadow import _explain_halts
    state = {"positions": {"AAA": {}, "BBB": {}}, "daily_loss_latched": False}
    quotes = {"AAA": {"executable": True}, "BBB": {"executable": False}}

    def halted():
        return [{"kind": "ENTRY_HALTED", "reason": "regime_or_missing_marks_or_daily_loss"}]

    monitor = _explain_halts(halted(), state, quotes, observations={"AAA": {"entry_allowed": False}},
                             allow_entries=False, drift=False)
    assert monitor == []
    [event] = _explain_halts(halted(), state, quotes, observations={"CCC": {}}, allow_entries=True, drift=False)
    assert event["reason"] == "held_mark_unavailable" and event["unmarked"] == ["BBB"]
    [event] = _explain_halts(halted(), {**state, "daily_loss_latched": True}, {"AAA": quotes["AAA"],
                             "BBB": {"executable": True}}, observations={"CCC": {}}, allow_entries=True,
                             drift=True)
    assert event["reason"] == "configuration_drift+daily_loss_latched" and "unmarked" not in event


def test_smart_held_tickers_reads_the_book_read_only(tmp_path):
    from penny_smart_policy import SMART_VERSION
    from penny_smart_shadow import smart_held_tickers
    path = tmp_path / "smart.db"
    assert smart_held_tickers(str(path)) == []
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE penny_smart_paper_state (policy TEXT PRIMARY KEY, state_json TEXT NOT NULL)")
        conn.execute("INSERT INTO penny_smart_paper_state VALUES (?,?)",
                     (SMART_VERSION, json.dumps({"positions": {"PCJEWELLER": {}, "KMSUGAR": {}}})))
    assert smart_held_tickers(str(path)) == ["KMSUGAR", "PCJEWELLER"]


def test_smart_policy_files_are_not_edited_by_this_fix():
    """The Smart binding hashes these files; editing them halts entries for good."""
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    changed = subprocess.run(["git", "diff", "--name-only", "9c5becb", "--", "penny_smart_policy.py",
                              "penny_smart_book.py", "adaptive_penny_policy.py", "penny_prices.py"],
                             cwd=root, capture_output=True, text=True)
    if changed.returncode != 0:
        pytest.skip("git history unavailable")
    assert changed.stdout.strip() == ""


# ---------------------------------------------------------------------------
# O19-O1: overnight picks share the free cash across the open slots
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_overnight_pick_uses_at_most_its_share_of_free_cash(tmp_path, monkeypatch):
    import edge_overnight_paper as eop
    from tests.test_edge_overnight_paper import TODAY, _Kite, _at, _cache, _quote

    def pick(ticker):
        return SimpleNamespace(ticker=ticker, signal_subtype="MO_strong", adjusted_strength=1.0, shares=2000)

    ranked = [pick("AAA"), pick("BBB")]
    monkeypatch.setattr("penny_edge_live.scan_today", lambda **_k: {"positions": ranked, "candidates": ranked})
    monkeypatch.setattr(eop, "universe_from_cache", lambda _db: ["AAA", "BBB"])
    monkeypatch.setattr(settings, "PENNY_EDGE_MAX_POSITIONS", 3)
    quotes = {"AAA": _quote(20.0, 20.2, 19.8, 20.0, 900000.0), "BBB": _quote(20.0, 20.2, 19.8, 20.0, 900000.0),
              "NIFTYBEES": _quote(20.0, 20.1, 19.9, 20.0, 100000.0)}
    summary = await eop.run_overnight_entry(_Kite(quotes), _cache(tmp_path), now=_at(TODAY, 15, 20))
    equity = summary["equity"]
    first, second = summary["opened"]
    first_cost = first["entry_price"] * first["shares"] + first["buy_charges"]
    assert first_cost <= equity / 3
    assert second["entry_price"] * second["shares"] + second["buy_charges"] <= (equity - first_cost) / 2
    assert summary["cash_after"] > equity / 3 - 50          # the unused slot's share stays free


def test_replay_runtime_arm_splits_cash_like_the_runtime():
    import inspect
    import edge_portfolio_replay as epr
    assert "split_cash=runtime_overnight" in inspect.getsource(epr.run_edge_portfolio)
    assert "split_cash" in inspect.signature(epr.run_overnight_book).parameters


# ---------------------------------------------------------------------------
# O19-F1: profit-lock arms; O19-B1: bootstrap order
# ---------------------------------------------------------------------------

def test_profit_lock_arms_are_declared_against_current():
    from fno_policy_replay import POLICIES, resolve_policy
    expected = {"FNO_LOCK_LATE_ARM": ("FNO_PROFIT_LOCK_ARM_R", 0.80),
                "FNO_LOCK_LOOSE_KEEP": ("FNO_PROFIT_LOCK_KEEP_FRACTION", 0.25),
                "FNO_LOCK_OFF": ("FNO_PROFIT_LOCK_ENABLED", False)}
    for name, override in expected.items():
        policy = resolve_policy(name)
        assert policy is POLICIES[name] and policy.manage_every_observation
        assert policy.exit_overrides == (override,)


def test_the_fno_catalogue_is_refreshed_before_the_penny_universe():
    import daily_bootstrap
    assert list(daily_bootstrap.TASK_LABELS) == ["fno_instruments", "penny_universe"]


# ---------------------------------------------------------------------------
# O19-M2: MOM_RS_PULLBACK, a market leader's VWAP pullback
# ---------------------------------------------------------------------------

def _frame(closes, volumes, day="2026-10-19"):
    index = pd.date_range(f"{day} 09:15", periods=len(closes), freq="15min")
    rows = []
    previous = closes[0]
    for close, volume in zip(closes, volumes):
        rows.append({"open": previous, "high": max(previous, close) * 1.001,
                     "low": min(previous, close) * 0.999, "close": close, "volume": volume})
        previous = close
    return pd.DataFrame(rows, index=index)


def _leader():
    # Up early, holds above VWAP, dips toward it at 11:00, reclaims at 11:15 on volume.
    closes = [100.0, 101.0, 101.8, 102.4, 102.6, 102.9, 102.1, 101.75, 102.6]
    volumes = [9000, 8000, 7000, 6000, 6000, 5000, 5000, 5000, 12000]
    return _frame(closes, volumes)


def _falling_index(n):
    closes = [22900.0 - 20 * i for i in range(n)]
    return _frame(closes, [1] * n)


def _daily():
    index = pd.date_range("2026-09-15", periods=20, freq="B")
    return pd.DataFrame({"open": 100.0, "high": 101.5, "low": 98.5, "close": 100.0, "volume": 1e5}, index=index)


def test_rs_pullback_buys_a_leader_on_a_falling_day():
    from momentum_rs_pullback import rs_pullback_signal
    stock = _leader()
    accepted, decision = rs_pullback_signal(stock, _falling_index(len(stock)), momentum_pool=50000.0,
                                            df_daily=_daily())
    assert accepted, decision
    assert decision["index_session_return"] < 0 < decision["stock_session_return"]
    assert decision["stop_loss"] < decision["entry_price"] < decision["target_1"]
    assert decision["shares"] > 0 and decision["shares"] * decision["entry_price"] <= 50000.0
    # The stop honours the shipped percent floor.
    assert decision["stop_loss"] <= decision["entry_price"] * (1 - settings.MOMENTUM_MIN_STOP_PCT) + 1e-9


def test_rs_pullback_refuses_without_the_setup_or_the_index():
    from momentum_rs_pullback import rs_pullback_signal
    stock = _leader()
    ok, decision = rs_pullback_signal(stock, None, momentum_pool=50000.0)
    assert not ok and decision["reject_reason"] == "index_bar_unavailable"
    rising = _frame([22900.0 + 80 * i for i in range(len(stock))], [1] * len(stock))   # +2.8%, above the stock
    ok, decision = rs_pullback_signal(stock, rising, momentum_pool=50000.0)
    assert not ok and decision["reject_reason"] == "relative_strength_too_low"
    quiet = stock.copy()
    quiet.loc[quiet.index[-1], "volume"] = 4000
    ok, decision = rs_pullback_signal(quiet, _falling_index(len(stock)), momentum_pool=50000.0)
    assert not ok and decision["reject_reason"] == "reclaim_volume_insufficient"


def test_rs_pullback_shadow_keeps_existing_variant_fingerprints():
    from momentum_shadow import VARIANTS, evaluate_momentum_shadows
    assert "MOM_RS_PULLBACK" in VARIANTS
    stock = _leader()
    rows = evaluate_momentum_shadows("AAA", stock, prev_day_high=101.5, bankroll=50000.0, momentum_pool=50000.0,
                                     df_daily=_daily(), index_today=_falling_index(len(stock)))
    by_name = {row["variant"]: row for row in rows}
    assert "rs_pullback" not in by_name["MOM_BASE"]["config"]
    assert "rs_pullback" not in by_name["MOM_SELECTIVE"]["config"]
    assert by_name["MOM_RS_PULLBACK"]["config"]["rs_pullback"] is True
    assert by_name["MOM_RS_PULLBACK"]["accepted"]
