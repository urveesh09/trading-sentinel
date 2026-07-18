"""
[PARTNER-TIPS-TESTS 2026-07-18] Multi-underlying registry (plan WS1):
one dump fetch per segment, failure isolation (a BFO outage must never
sink the NIFTY trading-path refresh), NIFTY legacy-path back-compat,
and the F&O-underlying-names sidecar file.
"""
import json
from datetime import date

import pytest

import fno_underlyings as fu
from config import settings
from fno_instruments import FnoInstruments

CSV_HEADER = (
    "instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,"
    "strike,tick_size,lot_size,instrument_type,segment,exchange"
)


def _nfo_dump() -> str:
    rows = [CSV_HEADER]
    rows.append("101,1,NIFTY0714250000CE,NIFTY,0,2026-07-21,25000,0.05,75,CE,NFO-OPT,NFO")
    rows.append("102,1,NIFTY0714250000PE,NIFTY,0,2026-07-21,25000,0.05,75,PE,NFO-OPT,NFO")
    rows.append("103,1,NIFTY26JULFUT,NIFTY,0,2026-07-30,0,0.05,75,FUT,NFO-FUT,NFO")
    rows.append("201,1,BANKNIFTY0714570000CE,BANKNIFTY,0,2026-07-28,57000,0.05,35,CE,NFO-OPT,NFO")
    rows.append("202,1,BANKNIFTY0714570000PE,BANKNIFTY,0,2026-07-28,57000,0.05,35,PE,NFO-OPT,NFO")
    rows.append("203,1,BANKNIFTY26JULFUT,BANKNIFTY,0,2026-07-28,0,0.05,35,FUT,NFO-FUT,NFO")
    rows.append("301,1,RELIANCE26JULFUT,RELIANCE,0,2026-07-30,0,0.05,250,FUT,NFO-FUT,NFO")
    return "\n".join(rows)


def _bfo_dump() -> str:
    rows = [CSV_HEADER]
    rows.append("401,1,SENSEX0714820000CE,SENSEX,0,2026-07-23,82000,0.05,20,CE,BFO-OPT,BFO")
    rows.append("402,1,SENSEX0714820000PE,SENSEX,0,2026-07-23,82000,0.05,20,PE,BFO-OPT,BFO")
    rows.append("403,1,SENSEX26JULFUT,SENSEX,0,2026-07-30,0,0.05,20,FUT,BFO-FUT,BFO")
    return "\n".join(rows)


class _SegmentKite:
    """Counts dump fetches per segment; optionally fails a segment."""

    def __init__(self, fail_segments=()):
        self.calls = {}
        self.fail_segments = set(fail_segments)

    async def get_instruments_dump(self, segment):
        self.calls[segment] = self.calls.get(segment, 0) + 1
        if segment in self.fail_segments:
            return ""
        return _nfo_dump() if segment == "NFO" else _bfo_dump()


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Isolate books + disk paths from the module singletons."""
    monkeypatch.setattr(fu, "_books", {})
    monkeypatch.setattr(
        fu, "FNO_UNDERLYING_NAMES_PATH", str(tmp_path / "names.json")
    )
    monkeypatch.setattr(
        fu, "instruments_path",
        lambda name: str(tmp_path / f"{name.lower()}.json"),
    )
    # A private NIFTY book too, so tests never touch the real singleton
    # state or its legacy disk path. Patched BY NAME on fno_instruments --
    # get_instruments_for resolves it lazily through the module.
    import fno_instruments as fi
    nifty = FnoInstruments("NIFTY", json_path=str(tmp_path / "nifty.json"))
    monkeypatch.setattr(fi, "get_fno_instruments", lambda: nifty)
    return tmp_path


def test_specs_table():
    assert fu.SPECS["NIFTY"].segment == "NFO"
    assert fu.SPECS["BANKNIFTY"].segment == "NFO"
    assert fu.SPECS["SENSEX"].segment == "BFO"
    # SENSEX signals stay dark until scripts/verify_bfo.py passes (WS6)
    assert fu.SPECS["SENSEX"].signal_enabled is False
    assert fu.SPECS["NIFTY"].signal_enabled is True


def test_analytics_underlyings_parses_and_skips_unknown(monkeypatch):
    monkeypatch.setattr(
        settings, "FNO_ANALYTICS_UNDERLYINGS", "NIFTY, banknifty ,TYPO,,SENSEX"
    )
    names = [s.name for s in fu.analytics_underlyings()]
    assert names == ["NIFTY", "BANKNIFTY", "SENSEX"]


def test_instruments_path_nifty_is_legacy():
    # NIFTY must keep the legacy path: the trading path's cold-start
    # rehydration reads it.
    assert fu.instruments_path("NIFTY") == settings.FNO_INSTRUMENTS_JSON_PATH
    assert fu.instruments_path("BANKNIFTY") == "/data/fno_banknifty_instruments.json"


def test_get_instruments_for_nifty_is_the_singleton(sandbox):
    import fno_instruments as fi
    assert fu.get_instruments_for("NIFTY") is fi.get_fno_instruments()
    b1 = fu.get_instruments_for("BANKNIFTY")
    assert b1 is fu.get_instruments_for("BANKNIFTY")   # cached
    assert b1.segment == "NFO" and b1.underlying == "BANKNIFTY"
    assert fu.get_instruments_for("SENSEX").segment == "BFO"


@pytest.mark.asyncio
async def test_refresh_all_one_dump_per_segment(sandbox):
    kite = _SegmentKite()
    results = await fu.refresh_all(kite)
    assert results == {"NIFTY": True, "BANKNIFTY": True, "SENSEX": True}
    # ONE NFO dump feeds both NIFTY and BANKNIFTY; ONE BFO feeds SENSEX.
    assert kite.calls == {"NFO": 1, "BFO": 1}
    assert fu.get_instruments_for("BANKNIFTY").lot_size == 35
    assert fu.get_instruments_for("SENSEX").lot_size == 20
    assert fu.get_instruments_for("NIFTY").lot_size == 75


@pytest.mark.asyncio
async def test_bfo_failure_does_not_sink_nifty(sandbox):
    kite = _SegmentKite(fail_segments={"BFO"})
    results = await fu.refresh_all(kite)
    assert results["NIFTY"] is True
    assert results["BANKNIFTY"] is True
    assert results["SENSEX"] is False


@pytest.mark.asyncio
async def test_refresh_all_always_includes_nifty(sandbox, monkeypatch):
    # An .env that trims the analytics list must never starve the live
    # NIFTY book (daily_bootstrap delegates its refresh here).
    monkeypatch.setattr(settings, "FNO_ANALYTICS_UNDERLYINGS", "SENSEX")
    kite = _SegmentKite()
    results = await fu.refresh_all(kite)
    assert results["NIFTY"] is True
    assert "BANKNIFTY" not in results


@pytest.mark.asyncio
async def test_underlying_names_sidecar_written(sandbox):
    kite = _SegmentKite()
    await fu.refresh_all(kite)
    with open(fu.FNO_UNDERLYING_NAMES_PATH) as f:
        names = set(json.load(f)["names"])
    # every distinct NFO `name`, index AND stock
    assert {"NIFTY", "BANKNIFTY", "RELIANCE"} <= names
    assert fu.load_underlying_names() == names


def test_load_underlying_names_missing_file(sandbox):
    assert fu.load_underlying_names() == set()
