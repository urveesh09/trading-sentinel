"""End-of-day index-future candle recording (NIFTY + SENSEX research history)."""
from datetime import date, datetime

import pandas as pd
import pytest
import pytz

import fno_underlyings
from config import settings
from fno_instruments import FnoInstruments
from fno_models import Contract
from research_future_candles import record_index_future_candles, recorded_underlyings

IST = pytz.timezone("Asia/Kolkata")
TODAY = date(2026, 10, 5)
NOW = IST.localize(datetime(2026, 10, 5, 15, 40))


def _book(name, segment, token, lot):
    book = FnoInstruments(name, segment=segment)
    book._load_contracts([Contract(token, f"{name}26OCTFUT", name, date(2026, 10, 27), 0.0, "FUT", lot)])
    book.refreshed_on = TODAY
    return book


class _Kite:
    def __init__(self, fail_token=None):
        self.calls, self.fail_token = [], fail_token

    async def get_intraday_by_token(self, token, frm, to, interval="5minute"):
        self.calls.append((token, frm, to, interval))
        if token == self.fail_token:
            raise RuntimeError("provider down")
        return pd.DataFrame({"close": [1.0] * (75 if interval == "5minute" else 375)})


@pytest.fixture
def books(monkeypatch):
    import fno_instruments as fi
    monkeypatch.setattr(fi, "_instruments", _book("NIFTY", "NFO", 111, 65))
    monkeypatch.setitem(fno_underlyings._books, "SENSEX", _book("SENSEX", "BFO", 222, 20))
    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_UNDERLYINGS", "NIFTY,SENSEX,MADEUP,NIFTY")


@pytest.mark.asyncio
async def test_records_whole_session_for_both_indices(books):
    kite = _Kite()
    result = await record_index_future_candles(kite, NOW)
    assert recorded_underlyings() == ["NIFTY", "SENSEX"]
    assert result["recorded"]["SENSEX"] == {"tradingsymbol": "SENSEX26OCTFUT", "5minute": 75, "minute": 375}
    assert {(t, i) for t, _, _, i in kite.calls} == {(111, "5minute"), (111, "minute"),
                                                     (222, "5minute"), (222, "minute")}
    assert all(frm == "2026-10-05 09:15:00" and to == "2026-10-05 15:30:00" for _, frm, to, _ in kite.calls)


@pytest.mark.asyncio
async def test_one_failure_does_not_lose_the_other_index(books):
    result = await record_index_future_candles(_Kite(fail_token=111), NOW)
    assert result["recorded"]["NIFTY"]["5minute"] == -1
    assert result["recorded"]["SENSEX"]["5minute"] == 75


def test_recorder_is_market_data_only():
    import ast
    from pathlib import Path
    import research_future_candles
    tree = ast.parse(Path(research_future_candles.__file__).read_text(encoding="utf-8"))
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not names & {"place_order", "modify_order", "cancel_order"}
