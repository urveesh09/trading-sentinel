"""[SX-P2] PEN_SMART_V2 runs beside an unchanged V1: its own paper book, a
wider noise-aware stop, a three-close thesis failure, and V1's binding is
untouched (no configuration drift)."""
import json
from unittest.mock import AsyncMock

import aiosqlite
import pandas as pd
import pytest

import penny_smart_shadow as shadow
from penny_smart_book import new_book, step_book
from penny_smart_policy import SMART_PARAMS, SMART_VERSION
from penny_smart_v2 import SMART_V2_PARAMS, SMART_V2_VERSION
from tests.test_penny_smart_policy import bars, quote, raw_quote, retest


def _enter(params):
    data = bars()
    items = {"AAA": {"bars": data, "median_volume": 100000}}
    state, _ = step_book(new_book("2026-10-05", 2000.0, {}), items, {"AAA": quote()}, now=data[-1].available_at,
                         cost=lambda e, x, q: 0.05, params=params)
    items = {"AAA": {"bars": data + [retest(data)], "median_volume": 100000}}
    return step_book(state, items, {"AAA": quote()}, now=retest(data).available_at, cost=lambda e, x, q: 0.05,
                     params=params)


def test_v2_changes_three_numbers_and_gives_the_stop_room():
    changed = {k for k, v in SMART_V2_PARAMS.__dict__.items() if getattr(SMART_PARAMS, k) != v}
    assert changed == {"policy_version", "noise_atr_mult", "min_noise_pct", "failed_breakout_closes"}
    v1_state, _ = _enter(SMART_PARAMS)
    v2_state, _ = _enter(SMART_V2_PARAMS)
    v1, v2 = v1_state["positions"]["AAA"]["thesis"], v2_state["positions"]["AAA"]["thesis"]
    # V1 sat 0.6% under the breakout anchor (10.00); V2 at least 1.2% under it.
    assert (v1["anchor"], v1["stop"], v2["stop"]) == (10.0, 9.94, 9.88)


def _frame(data):
    return pd.DataFrame([{"open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume}
                         for b in data], index=pd.DatetimeIndex([b.observed_at for b in data]))


@pytest.mark.asyncio
async def test_v2_is_its_own_book_and_v1_keeps_its_binding(tmp_path):
    path = str(tmp_path / "paper.sqlite")
    data = bars()
    frame = _frame(data)
    obs = {"AAA": {"frame": frame, "median_volume": 100000}}
    now = data[-1].available_at
    for policy in (SMART_VERSION, SMART_V2_VERSION):
        await shadow.observe_smart_shadow(path, obs, {"AAA": raw_quote(now)}, now=now, policy=policy)
    completed = retest(data)
    frame.loc[completed.observed_at] = [completed.open, completed.high, completed.low, completed.close,
                                        completed.volume]
    now = completed.available_at
    results = [await shadow.observe_smart_shadow(path, obs, {"AAA": raw_quote(now)}, now=now, policy=policy)
               for policy in (SMART_VERSION, SMART_V2_VERSION)]
    assert [(r["policy"], r["open"], r["configuration_drift"]) for r in results] == [
        (SMART_VERSION, 1, False), (SMART_V2_VERSION, 1, False)]
    async with aiosqlite.connect(path) as db:
        states = dict(await (await db.execute("SELECT policy, state_json FROM penny_smart_paper_state")).fetchall())
        entries = await (await db.execute(
            "SELECT policy, COUNT(*) FROM penny_smart_paper_events WHERE kind='ENTRY_FILLED' GROUP BY policy"
        )).fetchall()
    assert dict(entries) == {SMART_VERSION: 1, SMART_V2_VERSION: 1}
    v1, v2 = json.loads(states[SMART_VERSION]), json.loads(states[SMART_V2_VERSION])
    # V1's binding is exactly what it always was: the same params and the same four hashed files.
    assert v1["binding"]["params"] == json.loads(json.dumps(SMART_PARAMS.__dict__))
    assert sorted(v1["binding"]["policy_sha256"]) == ["adaptive_penny_policy.py", "penny_prices.py",
                                                       "penny_smart_book.py", "penny_smart_policy.py"]
    assert "penny_smart_v2.py" in v2["binding"]["policy_sha256"]
    assert v2["positions"]["AAA"]["thesis"]["stop"] < v1["positions"]["AAA"]["thesis"]["stop"]
    assert shadow.smart_held_tickers(path) == ["AAA"]
    assert shadow.smart_exposure_snapshot(str(tmp_path / "paper.sqlite").removesuffix(".penny-smart-paper.db"))[
        "status"] in ("NO_BOOK", "OPEN", "ATTENTION", "FLAT")


@pytest.mark.asyncio
async def test_v2_can_be_switched_off(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "PENNY_SMART_V2_ENABLED", False)
    assert list(shadow.smart_policies()) == [SMART_VERSION]
    monkeypatch.setattr(settings, "PENNY_SMART_V2_ENABLED", True)
    assert list(shadow.smart_policies()) == [SMART_VERSION, SMART_V2_VERSION]
    with pytest.raises(ValueError):
        shadow._params_for("PEN_SMART_V9")


@pytest.mark.asyncio
async def test_the_exit_monitor_observes_every_smart_book(monkeypatch):
    from types import SimpleNamespace
    import main
    from config import settings
    monitor = AsyncMock()
    monkeypatch.setattr(settings, "PENNY_SMART_SHADOW_ENABLED", True)
    monkeypatch.setattr(main, "_get_penny_scanner",
                        lambda: SimpleNamespace(kite=object(), executor=SimpleNamespace(paper_mode=False)))
    monkeypatch.setattr(shadow, "monitor_smart_shadow", monitor)
    await main.run_penny_paper_stop_monitor()
    assert [call.kwargs["policy"] for call in monitor.await_args_list] == [SMART_VERSION, SMART_V2_VERSION]


@pytest.mark.asyncio
async def test_the_comparison_counts_each_books_closes_from_v2s_first_session(tmp_path):
    ledger = str(tmp_path / "cache.db")
    path = shadow.smart_db_path(ledger)
    async with aiosqlite.connect(path) as db:
        await shadow._schema(db)
        for i, (policy, at, net, reason) in enumerate((
                (SMART_VERSION, "2026-10-21T11:00:00+05:30", -3.0, "SMART_PAPER_STOP"),
                (SMART_VERSION, "2026-10-22T11:00:00+05:30", -2.0, "SMART_THESIS_FAILED"),
                (SMART_V2_VERSION, "2026-10-22T11:05:00+05:30", 4.0, "SMART_PAPER_STOP"),
                (SMART_V2_VERSION, "2026-10-22T12:05:00+05:30", -1.0, "SMART_THESIS_FAILED"))):
            await db.execute("INSERT INTO penny_smart_paper_events VALUES (?,?,?,?,?,?)",
                             (f"e{i}", policy, at, "AAA", "EXIT_FILLED",
                              json.dumps({"net_pnl": net, "reason": reason})))
        await db.commit()
    out = shadow.smart_policy_comparison(ledger)
    v1, v2 = out["policies"]
    assert (v1["policy"], v1["closes"], v1["net"]) == (SMART_VERSION, 1, -2.0)
    assert (v2["closes"], v2["wins"], v2["losses"], v2["net"], v2["profit_factor"]) == (2, 1, 1, 3.0, 4.0)
