"""
[FNO-E2E-TESTS 2026-07-10] Paper-leg end-to-end: synthetic breakout bars
+ synthetic chain quotes -> run_fno_tick -> entry recorded honestly
(fill at ASK, one entry per bar) -> hard flat at 15:10 closes it (fill
at BID) with costs subtracted and a ledger row tagged FNO_PAPER.

This is the P1 "plumbing is proven honest" criterion (spec §1) in test
form: paper fills reconcile against real bid/ask, gates are satisfiable,
max_loss holds, the log tells the truth.
"""
from datetime import date, datetime

import pandas as pd
import pytest
import pytz

import fno_instruments as fi
import options_math
from config import settings
from fno_chain import RISK_FREE_RATE, years_to_expiry
from fno_executor import FnoExecutor
from fno_instruments import FnoInstruments
from fno_models import Contract
from fno_orchestrator import format_fno_telegram, run_fno_tick

IST = pytz.timezone("Asia/Kolkata")
TODAY = date(2026, 7, 10)
OPT_EXPIRY = date(2026, 7, 14)
FUT_EXPIRY = date(2026, 7, 30)
FUT_TOKEN = 999
FUT_PRICE = 25100.0
VOL = 0.06
NOW = IST.localize(datetime(2026, 7, 10, 10, 3))

PRIOR_DAYS = ["2026-07-03", "2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09"]


# ---------------------------------------------------------------------------
# fixtures: instrument book, breakout bars, quote table
# ---------------------------------------------------------------------------

def _build_book() -> FnoInstruments:
    book = FnoInstruments("NIFTY")
    contracts = [Contract(
        token=FUT_TOKEN, tradingsymbol="NIFTY26JULFUT", name="NIFTY",
        expiry=FUT_EXPIRY, strike=0.0, instrument_type="FUT", lot_size=75,
    )]
    token = 1000
    strike = 24500.0
    while strike <= 25700.0:
        for ot in ("CE", "PE"):
            token += 1
            contracts.append(Contract(
                token=token, tradingsymbol=f"NIFTY26714{int(strike)}{ot}",
                name="NIFTY", expiry=OPT_EXPIRY, strike=strike,
                instrument_type=ot, lot_size=75,
            ))
        strike += 50.0
    book._load_contracts(contracts)
    book.refreshed_on = TODAY
    return book


def _breakout_bars() -> pd.DataFrame:
    frames = []
    for d in PRIOR_DAYS:
        idx = pd.date_range(f"{d} 09:15", periods=74, freq="5min")
        frames.append(pd.DataFrame({
            "open": 25000.0, "high": 25005.0, "low": 24995.0,
            "close": 25000.0, "volume": 100.0,
        }, index=idx))
    rows = [
        ("09:15", 25000, 25010, 24990, 25000, 100),
        ("09:20", 25000, 25008, 24992, 25000, 100),
        ("09:25", 25000, 25010, 24990, 25000, 100),
        ("09:30", 25000, 25007, 24993, 25000, 100),
        ("09:35", 25000, 25009, 24991, 25000, 100),
        ("09:40", 25000, 25010, 24990, 25000, 100),
        ("09:45", 25000, 25008, 25000, 25005, 100),
        ("09:50", 25005, 25010, 25002, 25005, 100),
        ("09:55", 25010, 25105, 25005, 25100, 300),
    ]
    idx = pd.to_datetime([f"2026-07-10 {hm}" for hm, *_ in rows])
    cols = list(zip(*[r[1:] for r in rows]))
    frames.append(pd.DataFrame({
        "open": cols[0], "high": cols[1], "low": cols[2],
        "close": cols[3], "volume": cols[4],
    }, index=idx))
    return pd.concat(frames)


def _quote_table(book: FnoInstruments, now_ist: datetime, opt_bid_shift: float = 0.0):
    """Kite-shaped /quote payloads for every contract. Option mids come
    from Black-76 so the IV solve inside the orchestrator recovers VOL.
    opt_bid_shift moves option bids/asks (used to fake a profitable exit)."""
    ltt = now_ist.strftime("%Y-%m-%d %H:%M:%S")
    T = years_to_expiry(OPT_EXPIRY, now_ist)
    table = {
        FUT_TOKEN: {
            "last_price": FUT_PRICE, "volume": 50000, "oi": 100000,
            "last_trade_time": ltt,
            "depth": {"buy": [{"price": FUT_PRICE - 0.5}],
                      "sell": [{"price": FUT_PRICE + 0.5}]},
        }
    }
    for c in book.by_symbol.values():
        if c.instrument_type == "FUT":
            continue
        mid = options_math.black76_price(
            FUT_PRICE, c.strike, T, VOL, RISK_FREE_RATE, c.instrument_type == "CE",
        ) + opt_bid_shift
        mid = max(mid, 0.6)
        table[c.token] = {
            "last_price": round(mid, 2), "volume": 5000, "oi": 10000,
            "last_trade_time": ltt,
            "depth": {"buy": [{"price": round(mid - 0.3, 2)}],
                      "sell": [{"price": round(mid + 0.3, 2)}]},
        }
    return table


class FakeKite:
    access_token = "fake"

    def __init__(self, bars, quote_table):
        self.bars = bars
        self.quote_table = quote_table
        self.orders_placed = []

    async def get_intraday_by_token(self, token, frm, to, interval="5minute"):
        return self.bars

    async def get_quote(self, tokens):
        if isinstance(tokens, (int, str)):
            tokens = [tokens]
        return {int(t): self.quote_table[int(t)] for t in tokens
                if int(t) in self.quote_table}

    async def place_order(self, **kw):
        self.orders_placed.append(kw)
        return {"order_id": "SHOULD-NOT-HAPPEN-IN-PAPER"}


@pytest.fixture
def book(monkeypatch):
    b = _build_book()
    monkeypatch.setattr(fi, "_instruments", b)
    return b


@pytest.fixture
def kite(book):
    return FakeKite(_breakout_bars(), _quote_table(book, NOW))


# ---------------------------------------------------------------------------
# entry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_paper_entry_end_to_end(kite, db_path):
    summary = await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL",
                                 now_ist=NOW)
    assert len(summary["entries"]) == 1, f"no entry: {summary}"
    e = summary["entries"][0]
    assert e["source"] == "FNO_PAPER"
    assert e["direction"] == "LONG"
    # [ROADMAP-3.1 2026-07-12] 250k pool: risk budget min(2% pool,
    # FNO_MAX_LOSS_PER_TRADE) = 5000 admits 4 lots at this premium ->
    # capped by FNO_MAX_LOTS=2 (was 1 lot under the 100k pool).
    assert e["lots"] == 2
    # IV solved from the synthetic chain must recover the vol we priced with
    assert e["iv"] == pytest.approx(VOL, abs=0.01)
    # paper never touches the broker
    assert kite.orders_placed == []

    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT status, opt_type, lots, entry_premium, premium_stop, "
            "max_loss_rupees, bar_ts, token FROM fno_positions WHERE source='FNO_PAPER'"
        ) as cur:
            rows = await cur.fetchall()
    assert len(rows) == 1
    status, opt_type, lots, entry_premium, premium_stop, ml, bar_ts, token = rows[0]
    assert status == "OPEN" and opt_type == "CE" and lots == 2
    assert bar_ts == "2026-07-10 09:55:00"
    # honest paper fill: at the ASK, so entry pays the spread
    quote = kite.quote_table[token]
    assert entry_premium == pytest.approx(quote["depth"]["sell"][0]["price"])
    # premium backstop = 75% of fill (spec §8.4)
    assert premium_stop == pytest.approx(0.75 * entry_premium, abs=0.01)
    # structural max loss = full premium, and it passed the constitution
    assert ml == pytest.approx(entry_premium * 75 * lots, abs=0.5)
    assert ml <= settings.FNO_MAX_STRUCTURAL_LOSS_PER_TRADE

    # accepted row in the signal log
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT accepted, reject_reason FROM fno_signals WHERE leg='FNO_PAPER'"
        ) as cur:
            log_rows = await cur.fetchall()
    assert (1, "") in log_rows

    # Telegram formatter includes the entry
    msg = format_fno_telegram(summary)
    assert "ENTRY [FNO_PAPER]" in msg


@pytest.mark.asyncio
async def test_same_bar_never_enters_twice(kite, db_path):
    await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)
    second = await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL",
                                now_ist=NOW)
    assert second["entries"] == []
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM fno_positions") as cur:
            assert (await cur.fetchone())[0] == 1


@pytest.mark.asyncio
async def test_never_pyramids_the_same_contract_across_bars(db_path, book):
    """[NO-PYRAMID 2026-07-26] A NEW bar must not re-enter a held contract.

    already_entered_bar() only blocks a repeat inside the same 5-min bar, and
    the other caps are count/premium-based, so nothing stopped the paper book
    from stacking the identical strike on a later bar. On 2026-07-24 FNO_PAPER
    opened NIFTY26JUL23700PE three times (10:05, 10:35, 11:00) -- the third
    entry added 2 lots while the second was still open and already losing,
    concentrating ~Rs 30k of premium on one strike and averaging into a
    signal that had been wrong twice. Total: -Rs 5,718 on the day.
    """
    # Extend the fixture frame (which stops at the 09:55 breakout) with a
    # pullback below the OR level and then a FRESH re-break. The engine's
    # fresh-break rule rejects a bar that was already resident above the level,
    # so a second entry needs exactly this shape -- and it is the shape prod saw
    # on 2026-07-24, where three separate re-breaks resolved to one strike.
    bars = _breakout_bars()
    later = pd.DataFrame(
        {"open":   [25100.0, 25000.0],
         "high":   [25105.0, 25155.0],
         "low":    [24995.0, 24998.0],
         "close":  [25000.0, 25150.0],   # 10:00 back below OR, 10:05 re-breaks
         "volume": [100.0,   300.0]},
        index=pd.to_datetime(["2026-07-10 10:00", "2026-07-10 10:05"]),
    )
    bars = pd.concat([bars, later])

    now_bar1 = IST.localize(datetime(2026, 7, 10, 10, 3))     # -> bar_ts 09:55
    now_bar2 = IST.localize(datetime(2026, 7, 10, 10, 13))    # -> bar_ts 10:05
    k = FakeKite(bars, _quote_table(book, now_bar1))

    first = await run_fno_tick(k, db_path=db_path, regime="REGIME_1_NORMAL",
                               now_ist=now_bar1)
    assert len(first["entries"]) == 1, f"setup failed, no first entry: {first}"
    held_symbol = first["entries"][0]["symbol"]

    # Re-quote at the later timestamp, otherwise the quote-freshness gate
    # rejects first and the pyramid guard is never reached.
    k.quote_table = _quote_table(book, now_bar2)
    second = await run_fno_tick(k, db_path=db_path, regime="REGIME_1_NORMAL",
                                now_ist=now_bar2)
    assert second["entries"] == [], (
        f"pyramided into {held_symbol} on a new bar: {second}"
    )

    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM fno_positions WHERE tradingsymbol=?",
            (held_symbol,),
        ) as cur:
            assert (await cur.fetchone())[0] == 1
        # and the refusal is legible in the signal log, not silent
        async with db.execute(
            "SELECT COUNT(*) FROM fno_signals "
            "WHERE reject_reason='already_holding_this_contract'"
        ) as cur:
            assert (await cur.fetchone())[0] >= 1


@pytest.mark.asyncio
async def test_crisis_regime_blocks_entry(kite, db_path):
    summary = await run_fno_tick(kite, db_path=db_path, regime="REGIME_3_CRISIS",
                                 now_ist=NOW)
    assert summary["entries"] == []


@pytest.mark.asyncio
async def test_instruments_not_ready_is_a_loud_noop(kite, db_path, book):
    book.refreshed_on = date(2026, 7, 9)   # yesterday's book -> stale
    summary = await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL",
                                 now_ist=NOW)
    assert summary["note"] == "instruments_not_ready"
    assert summary["entries"] == []


# ---------------------------------------------------------------------------
# exit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hard_flat_closes_at_bid_with_costs_and_ledger(kite, db_path, book, monkeypatch):
    # This test isolates the single-leg engine's hard-flat + ledger mechanics.
    # The defined-risk paper book rides the same tick and (correctly) books its
    # own FNO_PAPER close, so silence it here to keep the single-leg assertions
    # exact -- the DR book has its own coverage in test_fno_dr_book.py.
    monkeypatch.setattr(settings, "FNO_DR_DISABLE_PAPER", True)
    from performance import init_ledger
    await init_ledger(db_path)
    await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)

    # 15:12 IST: hard flat. Rebuild quotes a touch higher so the trade
    # exits green and the pnl sign is unambiguous.
    later = IST.localize(datetime(2026, 7, 10, 15, 12))
    kite.quote_table = _quote_table(book, later, opt_bid_shift=+10.0)
    summary = await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL",
                                 now_ist=later)
    assert len(summary["exits"]) == 1
    x = summary["exits"][0]
    assert x["reason"] == "hard_flat_1510"

    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT status, exit_premium, gross_pnl, costs, pnl, exit_reason "
            "FROM fno_positions WHERE source='FNO_PAPER'"
        ) as cur:
            status, exit_premium, gross, costs, pnl, reason = await cur.fetchone()
    assert status == "CLOSED" and reason == "hard_flat_1510"
    # honest paper exit: at the BID; costs subtracted, never bypassed
    assert costs > 0
    assert pnl == pytest.approx(gross - costs, abs=0.01)

    # ledger row tagged FNO_PAPER (spec §10.3) -- and only that tag
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT source, pnl FROM bankroll_ledger WHERE event_type='TRADE_CLOSED'"
        ) as cur:
            ledger = await cur.fetchall()
    assert ledger == [("FNO_PAPER", pytest.approx(pnl, abs=0.01))]

    from performance import fno_bankroll
    assert await fno_bankroll(db_path, "FNO_PAPER") == pytest.approx(
        settings.FNO_PAPER_BANKROLL + pnl, abs=0.01,
    )


@pytest.mark.asyncio
async def test_premium_backstop_exit(kite, db_path, book):
    await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)
    # Crush the option quotes ~40% below entry: bid <= premium_stop fires.
    later = IST.localize(datetime(2026, 7, 10, 10, 30))
    crushed = _quote_table(book, later)
    for t, q in crushed.items():
        if t == FUT_TOKEN:
            continue
        for side in ("buy", "sell"):
            q["depth"][side][0]["price"] = round(q["depth"][side][0]["price"] * 0.6, 2)
        q["last_price"] = round(q["last_price"] * 0.6, 2)
    kite.quote_table = crushed
    summary = await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL",
                                 now_ist=later)
    assert len(summary["exits"]) == 1
    assert summary["exits"][0]["reason"] == "premium_backstop"
    assert summary["exits"][0]["pnl"] < 0


# ---------------------------------------------------------------------------
# executor paper honesty
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_executor_paper_fills_at_ask_and_bid():
    ex = FnoExecutor(kite=None, paper_mode=True, source_tag="FNO_PAPER")
    entry = await ex.execute_entry("NIFTYTEST", 75, ask=101.3)
    assert entry["status"] == "paper"
    assert entry["fill_price"] == 101.3
    assert entry["order_id"].startswith("PAPER-FNO-ENT-")
    exit_ = await ex.execute_exit("NIFTYTEST", 75, bid=99.1, tick_size=0.05)
    assert exit_["status"] == "paper"
    assert exit_["fill_price"] == 99.1
    assert exit_["order_id"].startswith("PAPER-FNO-EXT-")
