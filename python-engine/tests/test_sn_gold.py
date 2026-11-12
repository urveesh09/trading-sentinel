"""[SN Gold v5] The small-wallet paper book: its rules against the frozen research config, and its life on a real temporary
database (entry off N11's paper record, scale-in, N11-synced exit, extension, day stop, skips, the day's ledger)."""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import aiosqlite
import pytest
import pytz

import fno_n11
import sn_gold
from config import settings
from fno_costs import calc_fno_costs
from fno_models import Contract, ContractQuote

IST = pytz.timezone("Asia/Kolkata")
ROOT = Path(__file__).resolve().parents[2]
V5 = json.loads((ROOT / "docs/research/fno/sn-gold/SN_GOLD_V5.json").read_text(encoding="utf-8"))


def at(hhmm: str, day: str = "2026-11-13") -> datetime:
    return IST.localize(datetime.fromisoformat(f"{day}T{hhmm}:00"))


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


# ---- the rules ------------------------------------------------------------------------------------------------------

def test_settings_match_the_frozen_research_config():
    v = V5["variant_dict"]
    assert settings.SN_GOLD_EXTEND_AT == v["ext_x"] and settings.SN_GOLD_EXTEND_ATR == v["ext_k"]
    assert settings.SN_GOLD_SCALE_ATR == v["in_atr"] and v["in_full"] is True
    assert [settings.SN_GOLD_ITM_PER_LOT_1, settings.SN_GOLD_ITM_PER_LOT_2] == v["itm_auto"]
    assert v["books"] == ["N11", "R0.85"] and settings.SN_GOLD_STAND_RATIO == 0.85
    # the owner chose the start with the agent (Nov 13): Rs 30,000, tested as SN70's "start 30k, step after 100%, stop after 3"
    assert settings.SN_GOLD_START_WALLET == 30000 and settings.SN_GOLD_MAX_STEPS == 3 and settings.SN_GOLD_DAY_LOSS_SHARE == 0.20
    assert settings.SN_GOLD_STEP_TRIGGER == 1.0


def test_lots_follow_the_wallet_and_halve_on_quiet_days():
    assert sn_gold.lots_for(15000, True) == 1 and sn_gold.lots_for(15000, False) == 1
    assert sn_gold.lots_for(33750, True) == 2 and sn_gold.lots_for(33750, False) == 1
    assert sn_gold.lots_for(50625, True) == 3 and sn_gold.lots_for(50625, False) == 1


def test_itm_depth_follows_money_per_lot():
    assert sn_gold.itm_depth(15000) == 1 and sn_gold.itm_depth(17500) == 2 and sn_gold.itm_depth(19999) == 2
    assert sn_gold.itm_depth(20000) == 3


def q(token, strike, opt, bid, ask, expiry=date(2026, 11, 17)):
    return ContractQuote(contract=Contract(token=token, tradingsymbol=f"NIFTY{int(strike)}{opt}", name="NIFTY", expiry=expiry,
                                           strike=float(strike), instrument_type=opt, lot_size=65), bid=bid, ask=ask, ltp=(bid + ask) / 2)


def chain():
    return {(24000.0, "CE"): q(111, 24000, "CE", 149.5, 150.0), (23950.0, "CE"): q(112, 23950, "CE", 179.5, 180.0),
            (23900.0, "CE"): q(113, 23900, "CE", 214.5, 215.0), (24050.0, "CE"): q(114, 24050, "CE", 124.5, 125.0),
            (24000.0, "PE"): q(211, 24000, "PE", 139.5, 140.0), (24050.0, "PE"): q(212, 24050, "PE", 169.5, 170.0)}


def test_pick_contract_deepest_itm_that_fits_else_n11_strike_else_one_out():
    c = chain()
    strike, qt, lots = sn_gold.pick_contract(c, 24000, "CE", 1, 15000, 65)
    assert strike == 23950 and qt.contract.token == 112 and lots == 1          # 1 ITM: 180 x 65 = 11,700 fits
    strike, qt, lots = sn_gold.pick_contract(c, 24000, "CE", 1, 20000, 65)
    assert strike == 23900                                                    # Rs 20k per lot: up to 3 deep, 2 exists
    strike, qt, _ = sn_gold.pick_contract(c, 24000, "PE", 1, 15000, 65)
    assert strike == 24050                                                    # a put's ITM is above
    strike, qt, _ = sn_gold.pick_contract(c, 24000, "CE", 1, 9000, 65)
    assert strike == 24050                                                    # N11's 150 x 65 = 9,750 too dear: one out
    assert sn_gold.pick_contract(c, 24000, "CE", 1, 7000, 65) is None


def test_day_stop_spends_exactly_the_room():
    stop = sn_gold.day_stop(150.0, 65, 3000.0)
    loss = (150.0 - stop) * 65 + calc_fno_costs(150.0, stop, 65)
    assert 2990 <= loss <= 3000 + 65 * 0.05


def test_wallet_grows_50_percent_at_most_three_times():
    w, s, p = sn_gold.grow(15000, 0, 0.0, 15000)
    assert (w, s, p) == (22500, 1, 0.0)
    w, s, p = sn_gold.grow(w, s, p, -3000)
    assert (w, s) == (22500, 1) and p == -3000
    w, s, p = sn_gold.grow(50625, 3, 0.0, 999999)
    assert (w, s) == (50625, 3), "growth stops after the third step"


def test_atr_needs_five_bars():
    assert sn_gold.atr_from_bars([(1, 2, 0, 1)] * 4) is None
    assert sn_gold.atr_from_bars([(100, 110, 100, 105)] * 20) == pytest.approx(10.0)


# ---- the life of a position on a real database ------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "sn.db")
    told = []
    monkeypatch.setattr(sn_gold, "_tell", lambda text: told.append(text))
    monkeypatch.setattr(settings, "SN_GOLD_ENABLED", True)
    monkeypatch.setattr(settings, "SN_GOLD_START_WALLET", 15000.0)     # the mechanics are pinned on a Rs 15k wallet
    sn_gold._BARS.clear()
    sn_gold._LAST_LOOK.clear()
    run(fno_n11.init_db(path))
    run(sn_gold.init_db(path))
    monkeypatch.setattr(sn_gold, "atr_from_bars", lambda bars: 10.0 if len(bars) >= 5 else None)   # ATR is pinned; tested on its own
    path_told = SimpleNamespace(path=path, told=told)
    return path_told


async def _paper(path, bar_ts="2026-11-13 10:00:00", token=111, direction="LONG", status="OPEN", vol_up=0, atr=1.0, usual=1.0, nets=()):
    async with aiosqlite.connect(path) as d:
        await d.execute("INSERT OR IGNORE INTO fno_n11_gate(session_date,atr_pct,usual,vol_up,above_line,recorded_at) VALUES(?,?,?,?,?,?)",
                        ("2026-11-13", atr, usual, vol_up, 1, "x"))
        for i, n in enumerate(nets):
            await d.execute("INSERT INTO fno_n11_paper(underlying,bar_ts,strategy,direction,status,exit_time,net,source) VALUES('NIFTY',?,?,?,?,?,?,?)",
                            (f"2026-11-0{1 + i % 9} 10:{i:02d}:00", "N11_TPB", "LONG", "CLOSED", f"2026-11-0{1 + i % 9}T11:{i:02d}:00", n, fno_n11.PAPER_SOURCE))
        cur = await d.execute("INSERT INTO fno_n11_paper(underlying,bar_ts,strategy,direction,tradingsymbol,token,lot_size,entry_time,entry_premium,"
                              "status,source) VALUES('NIFTY',?,?,?,?,?,?,?,?,?,?)",
                              (bar_ts, "N11_TPB", direction, "NIFTY24000CE", token, 65, at("10:05").isoformat(), 150.0, status, fno_n11.PAPER_SOURCE))
        await d.commit()
        return cur.lastrowid


def snapshot(forward=24050.0):
    return SimpleNamespace(quotes=chain(), lot_size=65, forward=forward)


def sig(bar_ts="2026-11-13 10:00:00"):
    return SimpleNamespace(bar_ts=bar_ts)


def quotes(bids: dict):
    async def read(kite, tokens):
        return {t: {"depth": {"buy": [{"price": bids[t]}], "sell": [{"price": bids[t] + 0.5}]}, "last_price": bids[t]} for t in tokens if t in bids}, None
    return read


async def _row(path, table="sn_gold_positions"):
    async with aiosqlite.connect(path) as d:
        d.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await d.execute(f"SELECT * FROM {table} ORDER BY rowid")).fetchall()]


def _bars(path, start="09:15", n=40, base=24000.0, step=0.0, rng=10.0):
    for k in range(n):
        h, m = divmod(9 * 60 + 15 + k, 60)
        sn_gold._record_price(path, at(f"{h:02d}:{m:02d}"), base + step * k)
        sn_gold._BARS[(path, "2026-11-13")][9 * 60 + 15 + k] = [base + step * k, base + step * k + rng / 2, base + step * k - rng / 2, base + step * k]


async def _close_paper(path, pid, reason="time_stop"):
    async with aiosqlite.connect(path) as d:
        await d.execute("UPDATE fno_n11_paper SET status='CLOSED', exit_reason=?, exit_time=?, net=0 WHERE id=?", (reason, at("10:50").isoformat(), pid))
        await d.commit()


def test_entry_buys_the_itm_strike_with_the_day_stop(db):
    _bars(db.path)
    pid = run(_paper(db.path))
    run(sn_gold.on_paper_signal(db.path, sig(), snapshot(), at("10:05")))
    (r,) = run(_row(db.path))
    assert r["n11_paper_id"] == pid and r["strike"] == 23950 and r["token"] == 112 and json.loads(r["pieces"]) == [[180.0, 1]]
    assert r["stop_price"] == sn_gold.day_stop(180.0, 65, 3000.0) and r["atr1"] == pytest.approx(10.0)
    assert r["wallet"] == 15000 and "bought 1 lot" in db.told[0]


def test_exit_follows_n11_and_books_charges(db):
    _bars(db.path)
    pid = run(_paper(db.path))
    run(sn_gold.on_paper_signal(db.path, sig(), snapshot(), at("10:05")))
    run(sn_gold.tick(None, db.path, now=at("10:07"), fut_prices={"NIFTY": 24052.0}, read_quote=quotes({112: 185.0})))
    assert run(_row(db.path))[0]["status"] == "OPEN", "N11's lot is still open"
    run(_close_paper(db.path, pid))
    run(sn_gold.tick(None, db.path, now=at("10:50"), fut_prices={"NIFTY": 24055.0}, read_quote=quotes({112: 190.0})))
    (r,) = run(_row(db.path))
    assert r["status"] == "CLOSED" and r["exit_reason"] == "n11:time_stop"
    assert r["net"] == pytest.approx((190.0 - 180.0) * 65 - calc_fno_costs(180.0, 190.0, 65))
    assert r["net_stressed"] == pytest.approx(r["net"] - 205.0)


def test_winner_up_25_percent_is_kept_and_leaves_on_the_trail(db):
    _bars(db.path)
    pid = run(_paper(db.path))
    run(sn_gold.on_paper_signal(db.path, sig(), snapshot(), at("10:05")))
    run(_close_paper(db.path, pid))
    run(sn_gold.tick(None, db.path, now=at("10:50"), fut_prices={"NIFTY": 24150.0}, read_quote=quotes({112: 230.0})))
    (r,) = run(_row(db.path))
    assert r["status"] == "OPEN" and r["extended"] == 1, "230 >= 1.25 x 180: kept"
    run(sn_gold.tick(None, db.path, now=at("10:52"), fut_prices={"NIFTY": 24160.0}, read_quote=quotes({112: 240.0})))
    assert run(_row(db.path))[0]["status"] == "OPEN"
    run(sn_gold.tick(None, db.path, now=at("10:54"), fut_prices={"NIFTY": 24120.0}, read_quote=quotes({112: 215.0})))
    (r,) = run(_row(db.path))
    assert r["status"] == "CLOSED" and r["exit_reason"] == "extended_trail", "24120 is below 24160 - 3 ATR (30)"


def test_scale_in_once_at_one_atr_inside_the_day_room(db):
    _bars(db.path)
    run(_paper(db.path))
    run(sn_gold.on_paper_signal(db.path, sig(), snapshot(forward=24050.0), at("10:05")))
    run(sn_gold.tick(None, db.path, now=at("10:07"), fut_prices={"NIFTY": 24061.0}, read_quote=quotes({112: 60.0 + 120})))
    (r,) = run(_row(db.path))
    # 15,000 // (180.5 x 65) = 1 lot already held -> max(1, 1 - 1) = 1 more would cost 2 x 180.5 x 65 > 15,000: no add
    assert r["scaled"] == 1 and json.loads(r["pieces"]) == [[180.0, 1]]


def test_scale_in_buys_when_the_wallet_carries_it(db, monkeypatch):
    _bars(db.path)
    run(_paper(db.path))
    async def wallet(path, now):
        return {"wallet": 30000.0, "steps": 1, "progress": 0.0, "banked": 0.0, "refilled": 0.0}
    monkeypatch.setattr(sn_gold, "wallet_state", wallet)
    run(sn_gold.on_paper_signal(db.path, sig(), snapshot(forward=24050.0), at("10:05")))
    (r,) = run(_row(db.path))
    assert r["strike"] == 23900 and json.loads(r["pieces"]) == [[215.0, 1]], "Rs 30k, quiet day, 1 lot: up to 3 deep, 23900 is the deepest quoted"
    run(sn_gold.tick(None, db.path, now=at("10:07"), fut_prices={"NIFTY": 24061.0}, read_quote=quotes({113: 220.0})))
    (r,) = run(_row(db.path))
    assert r["scaled"] == 1 and json.loads(r["pieces"]) == [[215.0, 1], [220.5, 1]]
    assert r["stop_price"] > sn_gold.day_stop(215.0, 65, 6000.0), "the whole position's stop rises to fit the room"


def test_day_stop_closes_the_position(db):
    _bars(db.path)
    run(_paper(db.path))
    run(sn_gold.on_paper_signal(db.path, sig(), snapshot(), at("10:05")))
    stop = run(_row(db.path))[0]["stop_price"]
    run(sn_gold.tick(None, db.path, now=at("10:07"), fut_prices={"NIFTY": 23950.0}, read_quote=quotes({112: stop - 1})))
    (r,) = run(_row(db.path))
    assert r["status"] == "CLOSED" and r["exit_reason"] == "day_loss_stop" and r["net"] > -3000 - 70


def test_skips_when_open_or_standing_aside(db):
    _bars(db.path)
    run(_paper(db.path))
    run(sn_gold.on_paper_signal(db.path, sig(), snapshot(), at("10:05")))
    run(_paper(db.path, bar_ts="2026-11-13 10:30:00", token=111))
    run(sn_gold.on_paper_signal(db.path, sig("2026-11-13 10:30:00"), snapshot(), at("10:35")))
    assert len(run(_row(db.path))) == 1
    assert run(_row(db.path, "sn_gold_skips"))[0]["reason"] == "position_open"


def test_stand_aside_at_085(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SN_GOLD_START_WALLET", 15000.0)
    path = str(tmp_path / "s.db")
    monkeypatch.setattr(sn_gold, "_tell", lambda text: None)
    run(fno_n11.init_db(path))
    run(sn_gold.init_db(path))
    run(_paper(path, atr=0.80, usual=1.0, nets=[-10.0] * 20))       # 0.80 < 0.85 and a losing record: wait
    assert run(sn_gold.on_paper_signal(path, sig(), snapshot(), at("10:05"))) is None
    assert run(_row(path, "sn_gold_skips"))[0]["reason"] == "stand_aside_0.85"
    path2 = str(tmp_path / "s2.db")
    run(fno_n11.init_db(path2))
    run(sn_gold.init_db(path2))
    run(_paper(path2, atr=0.87, usual=1.0, nets=[-10.0] * 20))      # 0.87: N11 waits (0.9), SN Gold (R0.85) takes it
    assert run(sn_gold.on_paper_signal(path2, sig(), snapshot(), at("10:05"))) is not None


def test_day_close_books_refill_and_grows_once(db):
    _bars(db.path)
    pid = run(_paper(db.path))
    run(sn_gold.on_paper_signal(db.path, sig(), snapshot(), at("10:05")))
    run(_close_paper(db.path, pid))
    run(sn_gold.tick(None, db.path, now=at("10:50"), fut_prices={"NIFTY": 24000.0}, read_quote=quotes({112: 160.0})))
    run(sn_gold.tick(None, db.path, now=at("15:25"), fut_prices={"NIFTY": 24000.0}, read_quote=quotes({})))
    (d,) = run(_row(db.path, "sn_gold_days"))
    net = (160.0 - 180.0) * 65 - calc_fno_costs(180.0, 160.0, 65)
    assert d["trades"] == 1 and d["net"] == pytest.approx(net) and d["refill"] == pytest.approx(-net)
    assert d["wallet_after"] == 15000
    (w,) = run(_row(db.path, "sn_gold_wallet"))
    assert w["refilled"] == pytest.approx(-net) and w["progress"] == pytest.approx(net)
    assert not run(sn_gold.close_day(db.path, at("15:40"))), "booked once"
    assert any("today: Rs" in t for t in db.told)


def test_disabled_does_nothing(db, monkeypatch):
    monkeypatch.setattr(settings, "SN_GOLD_ENABLED", False)
    run(_paper(db.path))
    assert run(sn_gold.on_paper_signal(db.path, sig(), snapshot(), at("10:05"))) is None
    assert run(sn_gold.tick(None, db.path, now=at("10:07"), fut_prices={"NIFTY": 1.0}, read_quote=quotes({}))) == 0
    assert run(_row(db.path)) == []


def test_module_never_imports_an_order_path():
    src = (Path(sn_gold.__file__)).read_text(encoding="utf-8")
    for word in ("place_order", "fno_live", "executor", "kite.place", "order_execution"):
        assert word not in src, word


def test_minute_atr_reads_completed_future_candles_only(monkeypatch):
    import pandas as pd
    import fno_instruments
    fut = SimpleNamespace(token=999)
    monkeypatch.setattr(fno_instruments, "get_fno_instruments", lambda: SimpleNamespace(front_future=lambda d: fut))
    idx = pd.DatetimeIndex([at(f"09:{15 + k}").replace(tzinfo=None) for k in range(20)] + [at("09:35").replace(tzinfo=None)])
    frame = pd.DataFrame({"open": [100.0] * 21, "high": [110.0] * 20 + [500.0], "low": [100.0] * 20 + [0.0], "close": [105.0] * 21}, index=idx)

    class Kite:
        async def get_intraday_by_token(self, token, frm, to, interval="5minute"):
            assert token == 999 and interval == "minute" and frm.endswith("09:15:00")
            return frame
    assert run(sn_gold.minute_atr(Kite(), at("09:35"))) == pytest.approx(10.0), "the forming 09:35 candle is left out"
    assert run(sn_gold.minute_atr(None, at("09:35"))) is None


def test_production_wallet_30k_sizes_and_strikes(tmp_path, monkeypatch):
    """Rs 30,000 as deployed: a quiet day is 1 lot with Rs 30k behind it (up to 3 strikes in), a lively day 2 lots (1 in)."""
    monkeypatch.setattr(sn_gold, "_tell", lambda text: None)
    monkeypatch.setattr(sn_gold, "atr_from_bars", lambda bars: 10.0 if len(bars) >= 5 else None)
    assert settings.SN_GOLD_START_WALLET == 30000
    for vol_up, strike, lots in ((0, 23900, 1), (1, 23950, 2)):
        path = str(tmp_path / f"p{vol_up}.db")
        sn_gold._BARS.clear()
        run(fno_n11.init_db(path))
        run(sn_gold.init_db(path))
        _bars(path)
        run(_paper(path, vol_up=vol_up))
        run(sn_gold.on_paper_signal(path, sig(), snapshot(), at("10:05")))
        (r,) = run(_row(path))
        assert r["wallet"] == 30000 and r["strike"] == strike and json.loads(r["pieces"])[0][1] == lots
        assert r["stop_price"] == sn_gold.day_stop(json.loads(r["pieces"])[0][0], 65 * lots, 6000.0)
