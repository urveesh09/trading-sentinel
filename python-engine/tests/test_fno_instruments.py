"""
[FNO-INSTRUMENTS-TESTS 2026-07-10] NFO dump parsing, the read-never-
hardcode rules (VERIFY-2/VERIFY-3), and the same-day disk rehydration
that dodges the 38-minute cold-start pathology (ops rule 61).
"""
from datetime import date

import pytest

import fno_instruments as fi
from fno_instruments import FnoInstruments
from fno_models import OptionType

CSV_HEADER = (
    "instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,"
    "strike,tick_size,lot_size,instrument_type,segment,exchange"
)


def _dump_csv() -> str:
    rows = [CSV_HEADER]
    token = 100
    # NIFTY weeklies: two expiries, strikes 24900-25100 step 50.
    # Tradingsymbols embed the expiry, as Kite's real ones do.
    for expiry in ("2026-07-14", "2026-07-21"):
        tag = expiry[5:7] + expiry[8:10]
        for strike in (24900, 24950, 25000, 25050, 25100):
            for ot in ("CE", "PE"):
                token += 1
                rows.append(
                    f"{token},1,NIFTY{tag}{strike}{ot},NIFTY,0,{expiry},"
                    f"{strike},0.05,75,{ot},NFO-OPT,NFO"
                )
    rows.append(f"900,1,NIFTY26JULFUT,NIFTY,0,2026-07-30,0,0.05,75,FUT,NFO-FUT,NFO")
    # noise the parser must drop: another underlying + malformed row
    rows.append("901,1,BANKNIFTY51000CE,BANKNIFTY,0,2026-07-14,51000,0.05,35,CE,NFO-OPT,NFO")
    rows.append("bad,row,with,not,enough")
    return "\n".join(rows)


class _DumpKite:
    async def get_instruments_dump(self, segment):
        assert segment == "NFO"
        return _dump_csv()


class _EmptyKite:
    async def get_instruments_dump(self, segment):
        return ""


@pytest.mark.asyncio
async def test_refresh_parses_only_the_underlying():
    book = FnoInstruments("NIFTY")
    assert await book.refresh(_DumpKite())
    assert "BANKNIFTY51000CE" not in book.by_symbol
    assert len(book.by_symbol) == 21   # 20 options + 1 future
    # VERIFY-2: lot size READ from the dump
    assert book.lot_size == 75
    # strike step derived, not hardcoded
    assert book.strike_step == 50.0
    # VERIFY-3: expiry calendar read from the dump
    assert book.option_expiries == [date(2026, 7, 14), date(2026, 7, 21)]
    assert book.nearest_option_expiry(date(2026, 7, 10)) == date(2026, 7, 14)
    assert book.is_expiry_day(date(2026, 7, 14))
    assert not book.is_expiry_day(date(2026, 7, 10))
    fut = book.front_future(date(2026, 7, 10))
    assert fut is not None and fut.token == 900


@pytest.mark.asyncio
async def test_refresh_failure_keeps_previous_book():
    book = FnoInstruments("NIFTY")
    assert await book.refresh(_DumpKite())
    assert not await book.refresh(_EmptyKite())
    assert len(book.by_symbol) == 21   # stale beats empty intraday


def test_ready_requires_today():
    book = FnoInstruments("NIFTY")
    assert not book.ready(date(2026, 7, 10))


@pytest.mark.asyncio
async def test_disk_rehydration_same_day(patch_settings):
    book = FnoInstruments("NIFTY")
    await book.refresh(_DumpKite())   # persists to the tmp path via conftest
    # refresh stamps the real IST today, so a fresh instance rehydrates
    fresh = FnoInstruments("NIFTY")
    assert fresh.load_from_disk()
    assert fresh.lot_size == 75
    assert fresh.refreshed_on == book.refreshed_on
    assert len(fresh.by_symbol) == 21


@pytest.mark.asyncio
async def test_disk_rehydration_refuses_stale_snapshot(patch_settings):
    import json
    book = FnoInstruments("NIFTY")
    await book.refresh(_DumpKite())
    # age the snapshot to yesterday: tokens/expiries may have rolled
    path = patch_settings.FNO_INSTRUMENTS_JSON_PATH
    with open(path) as f:
        payload = json.load(f)
    payload["refreshed_on"] = "2020-01-01"
    with open(path, "w") as f:
        json.dump(payload, f)
    fresh = FnoInstruments("NIFTY")
    assert not fresh.load_from_disk()
    assert not fresh.ready(date(2026, 7, 10))


def test_atm_and_window_arithmetic():
    book = FnoInstruments("NIFTY")
    book._strike_step = 50.0
    assert book.atm_strike(25087.0) == 25100.0
    assert book.atm_strike(25024.9) == 25000.0
    window = book.strikes_window(25000.0, 2)
    assert window == [24900.0, 24950.0, 25000.0, 25050.0, 25100.0]


def test_option_lookup(monkeypatch):
    book = FnoInstruments("NIFTY")

    async def _run():
        await book.refresh(_DumpKite())
    import asyncio
    asyncio.run(_run())
    c = book.option(date(2026, 7, 14), 25000.0, OptionType.CE)
    assert c is not None and c.tradingsymbol == "NIFTY071425000CE"
    assert book.option(date(2026, 7, 14), 99999.0, OptionType.CE) is None
