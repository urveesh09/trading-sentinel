"""[Gold v6 WK-H] The hedged weekly straddle on paper: its rules against the research engine that passed the unseen exam
(docs/research/fno/2026-11-15-sn221/wk3.py), and a full week on a real temporary database (Monday 15:15 entry, the
15-minute futures hedge, the 15:15 marks, the expiry-day hedge close, settlement at the next open, the wallet)."""
from __future__ import annotations

import asyncio
import json
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import aiosqlite
import pytest
import pytz

import sn_wkh
from config import settings
from fno_models import Contract

IST = pytz.timezone("Asia/Kolkata")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "docs/research/fno/2026-11-15-sn221"))
import wk3  # noqa: E402  (the research engine; importing it loads no data)


def at(day: str, hhmm: str) -> datetime:
    return IST.localize(datetime.fromisoformat(f"{day}T{hhmm}:00"))


def run(coro):
    return asyncio.run(coro)


# ---- the rules against the research -----------------------------------------------------------------------------------

def test_settings_are_the_frozen_pick():
    h = wk3.HEDGES["H15x2"]
    assert settings.SN_WKH_LOTS_PER_UNIT == h["lots"] == 2
    assert h["band"] == 0.6 and settings.SN_WKH_EVERY_MIN == h["every"] == 15        # Gold v6: the exam-passed band
    v7 = json.loads((ROOT / "docs/research/fno/2026-11-15-sn231/results-sn245.json").read_text(encoding="utf-8"))["gold_v7"]
    assert v7 == "SN236 band 0.8 every 15" and settings.SN_WKH_BAND == 0.8 and settings.SN_WKH_LABEL == "Gold v7"   # Gold v7 (SN245)
    assert settings.SN_WKH_NIGHT == wk3.NIGHT == 0.15
    assert settings.SN_WKH_FREEZE_MIN == 9 * 60 + 15 + wk3.FREEZE == 14 * 60 + 30
    assert settings.SN_WKH_FUT_STRESS_PER_LOT == wk3.FUT_STRESS and settings.SN_WKH_OPEN_PENALTY == wk3.OPEN_PEN
    assert settings.SN_WKH_STRESS_PER_LEG_LOT == wk3.wk.SCORE_STRESS == 100.0
    assert sn_wkh.lots_for(500000) == 2 and sn_wkh.lots_for(499999) == 0 and sn_wkh.lots_for(1000000) == 4


def test_delta_matches_the_research():
    legs = [(24000, "CE", -1), (24000, "PE", -1)]
    for s in (23500.0, 23950.0, 24000.0, 24120.0, 24600.0):
        for t in (0.12, 1.15, 3.6):
            assert sn_wkh.straddle_delta(24000, s, t, 0.01) == pytest.approx(wk3._delta(legs, s, t, 0.01), abs=1e-12)
    assert sn_wkh.straddle_delta(24000, 24400, 1.0, 0.01) < -0.5 < 0.5 < sn_wkh.straddle_delta(24000, 23600, 1.0, 0.01)


def test_clock_matches_the_research():
    # Monday entry for a Thursday expiry: the research's n_after = sessions after the day before the expiry
    e = date(2021, 3, 4)
    for day, n_after in ((date(2021, 3, 1), 2), (date(2021, 3, 2), 1), (date(2021, 3, 3), 0)):
        for minute in (555, 870, 915):
            j = minute - 555
            want = (375 - j) / 375.0 + n_after + 360 / 375.0 + wk3.NIGHT * (n_after + 1)
            assert sn_wkh.session_time(day, minute, e) == pytest.approx(want)
    assert sn_wkh.session_time(e, 555 + 300, e) == pytest.approx(60 / 375.0)
    assert sn_wkh.session_time(e, 555 + 361, e) == pytest.approx(1e-4)


def test_hedge_target_band_and_rounding():
    assert sn_wkh.hedge_target(2, 0.2, 0, 0.6) is None               # |0.4| inside the band
    assert sn_wkh.hedge_target(2, 0.4, 0, 0.6) == -1                  # 0.8 -> sell 1
    assert sn_wkh.hedge_target(2, 0.79, -1, 0.6) is None              # 1.58 - 1 = 0.58 is inside the band
    assert sn_wkh.hedge_target(2, 0.85, -1, 0.6) == -2                # 1.7 - 1 = 0.7 -> -round(1.7)
    assert sn_wkh.hedge_target(2, 0.75, -1, 0.6) is None              # 1.5 - 1 = 0.5
    assert sn_wkh.hedge_target(2, -0.45, 0, 0.6) == 1
    assert sn_wkh.hedge_target(2, 0.1, -2, 0.6) == 0                  # 0.2 - 2 = -1.8 -> back to flat


def test_futures_charges_match_the_research_schedule():
    for px, lots, side in ((24100.0, 1, "SELL"), (24100.0, 2, "BUY"), (18000.5, 1, "BUY")):
        assert sn_wkh.fut_charges(px, lots, side, 65) == pytest.approx(wk3.fut_charges(px, lots, side.lower(), wk3.wk.NIFTY))
    assert sn_wkh.fut_charges(24000, 1, "SELL", 65) > 300                 # STT 0.02% on Rs 15.6 lakh dominates


def test_option_settlement_is_the_research_value_without_stress():
    mk = wk3.wk.NIFTY
    legs = [(24000, "CE", -1), (24000, "PE", -1)]
    for s_t in (23800.0, 24000.0, 24333.3):
        want = wk3.wk._settle_value(mk, legs, [120.0, 110.0], s_t, 0.0)
        assert sn_wkh.option_settle_net(24000, 120.0, 110.0, s_t, 65) == pytest.approx(want)


def test_entry_day_never_holds_a_weekend():
    holidays = {date(2026, 11, 24)}
    sess = lambda d: d.weekday() < 5 and d not in holidays      # noqa: E731
    tue = date(2026, 11, 17)
    assert sn_wkh.entry_day_ok(date(2026, 11, 16), tue, sess)          # Monday for a Tuesday expiry
    assert not sn_wkh.entry_day_ok(date(2026, 11, 13), tue, sess)      # Friday holds the weekend
    assert not sn_wkh.entry_day_ok(date(2026, 11, 12), tue, sess)
    assert not sn_wkh.entry_day_ok(tue, tue, sess)                     # never on expiry day
    thu = date(2021, 3, 4)
    assert sn_wkh.entry_day_ok(date(2021, 3, 1), thu, sess) and not sn_wkh.entry_day_ok(date(2021, 3, 2), thu, sess)
    # a holiday inside the week (Tue Nov 24): no session is free of a gap before Wed Nov 25 except Wed itself (= expiry)
    assert not any(sn_wkh.entry_day_ok(date(2026, 11, 18) + timedelta(days=i), date(2026, 11, 25), sess) for i in range(7))
    for d in (date(2021, 3, 1), date(2026, 11, 16)):
        e = thu if d.year == 2021 else tue
        days = [x for x in (d - timedelta(days=4) + timedelta(days=i) for i in range(10)) if sess(x) and x < e and x > e - timedelta(days=7)]
        k = wk3.k_of("M", e.isoformat(), [x.isoformat() for x in days])
        assert days[-k] == d                                           # the research picks the same day


def test_atm_is_the_closest_call_put_pair_ties_to_the_index():
    chain = {23950.0: (180.0, 181.0, 120.0, 121.0), 24000.0: (150.0, 151.0, 148.0, 149.0), 24050.0: (122.0, 123.0, 175.0, 176.0)}
    assert sn_wkh.pick_atm(chain, 24010.0) == 24000.0
    tie = {24000.0: (150.0, 151.0, 149.0, 150.0), 24050.0: (125.0, 126.0, 126.0, 127.0)}
    assert sn_wkh.pick_atm(tie, 24040.0) == 24050.0 and sn_wkh.pick_atm(tie, 24010.0) == 24000.0
    assert sn_wkh.pick_atm({24000.0: (0.0, 151.0, 149.0, 150.0)}, 24000.0) is None


def test_module_never_imports_an_order_path():
    src = Path(sn_wkh.__file__).read_text(encoding="utf-8")
    for word in ("place_order", "fno_live", "executor", "kite.place", "order_execution", "modify_order"):
        assert word not in src, word


# ---- a full week on a real database -------------------------------------------------------------------------------------

EXPIRY = date(2021, 3, 4)          # a Thursday expiry: Monday entry, two mid days, the expiry day, Friday settlement
FUT_E = date(2021, 3, 25)


class Inst:
    underlying = "NIFTY"
    lot_size = 65
    future_expiries = [FUT_E]

    def __init__(self):
        self.by_key = {("NIFTY", FUT_E.isoformat(), 0.0, "FUT"): Contract(token=9, tradingsymbol="NIFTY21MARFUT", name="NIFTY", expiry=FUT_E,
                                                                           strike=0.0, instrument_type="FUT", lot_size=65)}

    def nearest_option_expiry(self, today):
        return EXPIRY if today <= EXPIRY else None

    def front_future(self, today):
        return self.by_key[("NIFTY", FUT_E.isoformat(), 0.0, "FUT")]

    def strikes_window(self, spot, window):
        atm = round(spot / 50) * 50
        return [atm + 50 * i for i in range(-window, window + 1)]

    def option(self, expiry, strike, opt_type):
        tok = int(strike) * 10 + (1 if opt_type.value == "CE" else 2)
        return Contract(token=tok, tradingsymbol=f"NIFTY21304{int(strike)}{opt_type.value}", name="NIFTY", expiry=expiry, strike=float(strike),
                        instrument_type=opt_type.value, lot_size=65)


class Kite:
    """Quotes from a small state: the index, the future (bid/ask = mid -/+ 0.5) and options priced off the index."""

    def __init__(self):
        self.spot, self.prev_close, self.calls = 15000.0, 0.0, 0

    def opt_mid(self, strike, opt):
        iv = max(0.0, self.spot - strike) if opt == "CE" else max(0.0, strike - self.spot)
        return iv + 100.0

    async def get_quote_by_instruments(self, request):
        self.calls += 1
        out = {}
        for key, name in request.items():
            if key == sn_wkh.SPOT_KEY:
                out[key] = {"last_price": self.spot, "ohlc": {"close": self.prev_close}}
            elif key == sn_wkh.FUT_KEY:
                f = self.spot + 20.0
                out[key] = {"depth": {"buy": [{"price": f - 0.5}], "sell": [{"price": f + 0.5}]}, "last_price": f}
            else:
                strike, opt = (key // 10), ("CE" if key % 10 == 1 else "PE")
                m = self.opt_mid(strike, opt)
                out[key] = {"depth": {"buy": [{"price": m - 0.5}], "sell": [{"price": m + 0.5}]}, "last_price": m}
        return out


def _sess(d):
    return d.weekday() < 5


async def _is_session(d):
    return _sess(d)


@pytest.fixture
def wk(tmp_path, monkeypatch):
    path = str(tmp_path / "wkh.db")
    told = []
    monkeypatch.setattr(sn_wkh, "_tell", lambda text: told.append(text))
    monkeypatch.setattr(sn_wkh, "_instruments", lambda: Inst())
    monkeypatch.setattr(settings, "SN_WKH_ENABLED", True)
    run(sn_wkh.init_db(path))
    return SimpleNamespace(path=path, told=told, kite=Kite())


def _tick(w, day, hhmm):
    return run(sn_wkh.tick(w.kite, w.path, now=at(day, hhmm), is_session=_is_session))


async def _rows(path, table):
    async with aiosqlite.connect(path) as d:
        d.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await d.execute(f"SELECT * FROM {table} ORDER BY rowid")).fetchall()]


def test_a_full_hedged_week(wk):
    assert _tick(wk, "2021-02-26", "15:16") == ""                     # Friday: the weekend is not held
    assert _tick(wk, "2021-03-01", "15:10") == ""                     # Monday before 15:15
    assert _tick(wk, "2021-03-01", "15:16") == "entered"
    week = run(_rows(wk.path, "gold_v6_wkh_weeks"))[0]
    assert week["strike"] == 15000.0 and week["lots"] == 2 and week["ce_bid"] == 99.5 and week["pe_bid"] == 99.5
    assert week["sigma"] == pytest.approx(sn_wkh.sigma_from(200.0, 15000.0, sn_wkh.session_time(date(2021, 3, 1), 915, EXPIRY)))
    assert _tick(wk, "2021-03-01", "15:18") == ""                     # one week only; no hedge on the entry day
    # Tuesday 09:16: the index is 150 points up, the straddle is short delta -> buy futures
    wk.kite.spot = 15150.0
    assert _tick(wk, "2021-03-02", "09:16") == "hedged"
    week = run(_rows(wk.path, "gold_v6_wkh_weeks"))[0]
    t = sn_wkh.session_time(date(2021, 3, 2), 9 * 60 + 16, EXPIRY)
    d = sn_wkh.straddle_delta(15000.0, 15150.0, t, week["sigma"])
    assert week["hedge_lots"] == -int(round(2 * d)) > 0
    assert _tick(wk, "2021-03-02", "09:20") == ""                     # the same 15-minute slot is checked once
    order = run(_rows(wk.path, "gold_v6_wkh_orders"))[0]
    assert order["side"] == "BUY" and order["price"] == 15170.5 and order["costs"] == pytest.approx(sn_wkh.fut_charges(15170.5, order["lots"], "BUY", 65))
    # 15:15 mark on Tuesday
    assert _tick(wk, "2021-03-02", "15:16") in ("marked", "hedged")
    mark = run(_rows(wk.path, "gold_v6_wkh_marks"))[0]
    assert mark["total"] == pytest.approx(mark["option_value"] + mark["hedge_value"])
    # Thursday (expiry): no new orders from 14:30; samples from 15:00; the hedge closes at 15:24 at the samples' mean
    wk.kite.spot = 15000.0
    n_orders = len(run(_rows(wk.path, "gold_v6_wkh_orders")))
    assert _tick(wk, "2021-03-04", "14:35") == ""
    assert len(run(_rows(wk.path, "gold_v6_wkh_orders"))) == n_orders
    for m in range(0, 24):
        _tick(wk, "2021-03-04", f"15:{m:02d}")
    assert _tick(wk, "2021-03-04", "15:24") == "hedge_closed"
    week = run(_rows(wk.path, "gold_v6_wkh_weeks"))[0]
    assert week["hedge_lots"] == 0 and week["hedge_closed"] == 1 and week["status"] == "SETTLING"
    # Friday's first tick: settle at Kite's previous close (the expiry day's official close)
    wk.kite.prev_close = 15010.0
    assert _tick(wk, "2021-03-05", "09:16") == "settled"
    week = run(_rows(wk.path, "gold_v6_wkh_weeks"))[0]
    opt = sn_wkh.option_settle_net(15000.0, 99.5, 99.5, 15010.0, 130)
    assert week["status"] == "CLOSED" and week["option_net"] == pytest.approx(opt)
    assert week["net"] == pytest.approx(opt + week["hedge_cash"]) and week["hedge_net"] == pytest.approx(week["hedge_cash"])
    assert week["net_stressed"] == pytest.approx(week["net"] - 100.0 * 2 * 2 - week["hedge_stress"])
    wallet = run(_rows(wk.path, "gold_v6_wkh_wallet"))[0]
    assert wallet["weeks"] == 1 and wallet["banked"] - wallet["refilled"] == pytest.approx(week["net"])
    assert any("sold the NIFTY 15000 straddle" in x for x in wk.told) and any("settled at 15,010.00" in x for x in wk.told)
    assert _tick(wk, "2021-03-05", "15:16") == ""                     # Friday: not an entry day; nothing open


def test_quotes_are_read_rarely(wk):
    _tick(wk, "2021-03-01", "15:16")
    before = wk.kite.calls
    for h in range(9, 16):
        for m in range(0, 60, 1):
            if (h, m) < (9, 15) or (h, m) > (15, 14):
                continue
            _tick(wk, "2021-03-02", f"{h:02d}:{m:02d}")
    assert wk.kite.calls - before <= 26                                # 25 checks + the 15:15 mark at most


def test_missed_expiry_close_is_unresolved_not_guessed(wk):
    _tick(wk, "2021-03-01", "15:16")
    wk.kite.spot = 15400.0
    _tick(wk, "2021-03-02", "09:16")                                    # a hedge is open
    assert run(_rows(wk.path, "gold_v6_wkh_weeks"))[0]["hedge_lots"] != 0
    wk.kite.prev_close = 15400.0
    assert _tick(wk, "2021-03-05", "09:16") == "unresolved"            # the engine was not running on expiry day
    assert run(_rows(wk.path, "gold_v6_wkh_weeks"))[0]["reason"] == "engine_down_at_expiry"


def test_disabled_does_nothing(wk, monkeypatch):
    monkeypatch.setattr(settings, "SN_WKH_ENABLED", False)
    assert _tick(wk, "2021-03-01", "15:16") == ""
    assert run(_rows(wk.path, "gold_v6_wkh_weeks")) == [] and wk.kite.calls == 0
