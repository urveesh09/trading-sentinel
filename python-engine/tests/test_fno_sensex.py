"""[FNO-GROWTH] SENSEX on the single-leg paper book: participation proxy, guard, scoping."""
from datetime import timedelta

import aiosqlite
import pytest

import fno_underlyings
import fno_exit_paths
from config import settings
from fno_engine_mom import evaluate_fno_mom
from fno_instruments import FnoInstruments
from fno_models import Contract
from fno_orchestrator import run_fno_fast_exit
from tests.test_fno_orchestrator import (
    FUT_EXPIRY, FUT_TOKEN, NOW, OPT_EXPIRY, TODAY, FakeKite, _breakout_bars, _quote_table, run_fno_tick,
    book,  # noqa: F401  (pytest fixture: the NIFTY book)
)

SENSEX_FUT = 777


def _sensex_book() -> FnoInstruments:
    book = FnoInstruments("SENSEX", segment="BFO")
    contracts = [Contract(SENSEX_FUT, "SENSEX26JULFUT", "SENSEX", FUT_EXPIRY, 0.0, "FUT", 20)]
    token, strike = 50_000, 24_500.0
    while strike <= 25_700.0:
        for kind in ("CE", "PE"):
            token += 1
            contracts.append(Contract(token, f"SENSEX26714{int(strike)}{kind}", "SENSEX", OPT_EXPIRY,
                                      strike, kind, 20))
        strike += 50.0
    book._load_contracts(contracts)
    book.refreshed_on = TODAY
    return book


@pytest.fixture
def sensex(monkeypatch, book):
    sensex_book = _sensex_book()
    monkeypatch.setitem(fno_underlyings._books, "SENSEX", sensex_book)
    table = _quote_table(book, NOW)
    for token, payload in _quote_table(sensex_book, NOW).items():
        table[token] = payload
    table[SENSEX_FUT] = dict(table[FUT_TOKEN])    # SENSEX future priced like the NIFTY fixture
    return FakeKite(_breakout_bars(), table)


def test_thin_sensex_volume_borrows_nifty_participation():
    bars = _breakout_bars()
    thin = bars.copy()
    thin["volume"] = 0.0                            # SENSEX-like: futures volume unusable
    assert evaluate_fno_mom(thin, "REGIME_1_NORMAL", NOW).direction is None
    borrowed = evaluate_fno_mom(thin, "REGIME_1_NORMAL", NOW, rvol_bars=bars)
    assert borrowed.direction is not None and borrowed.rvol >= settings.FNO_MIN_RVOL
    missing = evaluate_fno_mom(thin, "REGIME_1_NORMAL", NOW, rvol_bars=bars.iloc[:-3])
    assert missing.direction is None and missing.reject_reason == "rvol_baseline_unavailable"


def test_trading_underlyings_put_nifty_first_and_skip_unknown(monkeypatch):
    monkeypatch.setattr(settings, "FNO_TRADING_UNDERLYINGS", "sensex, NIFTY, MADEUP")
    assert [spec.name for spec in fno_underlyings.trading_underlyings()] == ["NIFTY", "SENSEX"]
    assert fno_underlyings.SPECS["SENSEX"].rvol_source == "NIFTY"


@pytest.mark.asyncio
async def test_sensex_alone_enters_with_its_own_contract_and_lot(sensex, db_path, monkeypatch):
    monkeypatch.setattr(settings, "FNO_TRADING_UNDERLYINGS", "SENSEX")
    monkeypatch.setattr(settings, "FNO_DR_DISABLE_PAPER", True)
    summary = await run_fno_tick(sensex, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)
    assert len(summary["entries"]) == 1, summary
    assert summary["entries"][0]["symbol"].startswith("SENSEX")
    assert sensex.orders_placed == []                # paper never touches the broker
    async with aiosqlite.connect(db_path) as db:
        rows = await (await db.execute("SELECT underlying, lot_size, tradingsymbol FROM fno_positions")).fetchall()
        logged = await (await db.execute("SELECT DISTINCT underlying FROM fno_signals")).fetchall()
    assert rows == [("SENSEX", 20, summary["entries"][0]["symbol"])]
    assert ("SENSEX",) in logged


@pytest.mark.asyncio
async def test_same_breakout_on_both_indices_is_one_bet(sensex, db_path, monkeypatch):
    monkeypatch.setattr(settings, "FNO_TRADING_UNDERLYINGS", "NIFTY,SENSEX")
    monkeypatch.setattr(settings, "FNO_DR_DISABLE_PAPER", True)
    summary = await run_fno_tick(sensex, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)
    assert [e["symbol"][:5] for e in summary["entries"]] == ["NIFTY"]
    async with aiosqlite.connect(db_path) as db:
        reasons = await (await db.execute(
            "SELECT reject_reason FROM fno_signals WHERE underlying='SENSEX' AND leg='FNO_PAPER'")).fetchall()
    assert reasons == [("correlated_exposure_open",)]


@pytest.mark.asyncio
@pytest.mark.parametrize("capture", [False, True])
async def test_each_position_is_managed_against_its_own_future(sensex, db_path, book, monkeypatch, capture):
    monkeypatch.setattr(settings, "FNO_TRADING_UNDERLYINGS", "SENSEX")
    monkeypatch.setattr(settings, "FNO_DR_DISABLE_PAPER", True)
    monkeypatch.setattr(settings, "FNO_N012_FORWARD_EVIDENCE", capture)
    await run_fno_tick(sensex, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)
    async with aiosqlite.connect(db_path) as db:
        direction, stop_u, token, qty = await (await db.execute(
            "SELECT direction, stop_underlying, token, qty FROM fno_positions WHERE status='OPEN'")).fetchone()
        await db.execute("UPDATE fno_positions SET strategy='N11_OR20' WHERE token=?", (token,))
        await db.commit()
    later = NOW + timedelta(minutes=10)
    table = _quote_table(book, later)
    for quote_token, payload in _quote_table(fno_underlyings._books["SENSEX"], later).items():
        table[quote_token] = payload
    # Only SENSEX breaches its stop; the NIFTY future stays where it was.
    table[SENSEX_FUT] = dict(table[FUT_TOKEN])
    table[SENSEX_FUT]["last_price"] = stop_u - 1.0 if direction == "LONG" else stop_u + 1.0
    for key in (token, SENSEX_FUT, FUT_TOKEN):
        table[key].update(instrument_token=key, timestamp=later.isoformat())
    table[token]["depth"]["buy"][0]["quantity"] = qty
    sensex.quote_table = table
    quote_calls = sensex.quote_calls
    summary = await run_fno_fast_exit(sensex, db_path=db_path, now_ist=later)
    assert [x["reason"] for x in summary["exits"]] == ["underlying_stop"]
    assert sensex.quote_calls - quote_calls == 3  # NIFTY future, SENSEX future, held option
    assert sensex.orders_placed == []
    assert fno_exit_paths.flush()
    [look] = fno_exit_paths.read_day(settings.RESEARCH_ARCHIVE_PATH, TODAY.isoformat())
    assert look["fut"] == round(table[SENSEX_FUT]["last_price"], 4)
    if capture:
        evidence = look["quote_evidence"]
        assert evidence["schema"] == fno_exit_paths.N11_QUOTE_SCHEMA
        assert (evidence["strategy"], evidence["held_qty"], evidence["held_lot_size"]) == ("N11_OR20", qty, 20)
        assert evidence["held_expiry"] == OPT_EXPIRY.isoformat()
        option, future = evidence["option"], evidence["future"]
        assert (option["provider_token"], option["bid_qty"], option["ask_qty"]) == (token, qty, None)
        assert option["bid"] == table[token]["depth"]["buy"][0]["price"]
        assert option["received_at"] == future["received_at"] == later.isoformat()
        assert future["provider_token"] == future["token"] == SENSEX_FUT and future["underlying"] == "SENSEX"
        assert future["expiry"] == FUT_EXPIRY.isoformat()
        assert future["ltp"] == table[SENSEX_FUT]["last_price"]
        assert option["provider_at"] == future["provider_at"] and option["provider_at"].startswith(TODAY.isoformat())
    else:
        assert "quote_evidence" not in look
