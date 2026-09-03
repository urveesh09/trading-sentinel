"""
[FNO-E2E-TESTS 2026-07-10] Paper-leg end-to-end: synthetic breakout bars
+ synthetic chain quotes -> run_fno_tick -> entry recorded honestly
(fill at ASK, one entry per bar) -> hard flat at 15:10 closes it (fill
at BID) with costs subtracted and a ledger row tagged FNO_PAPER.

This is the P1 "plumbing is proven honest" criterion (spec §1) in test
form: paper fills reconcile against real bid/ask, gates are satisfiable,
max_loss holds, the log tells the truth.
"""
from datetime import date, datetime, timedelta

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
        self.bar_calls = 0
        self.quote_calls = 0

    async def get_intraday_by_token(self, token, frm, to, interval="5minute"):
        self.bar_calls += 1
        return self.bars

    async def get_quote(self, tokens):
        self.quote_calls += 1
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
async def test_defined_risk_and_directional_books_share_tick_market_data(
    kite, db_path, monkeypatch,
):
    """One tick must not download the same 21-day bar set twice.

    The DR router and directional ORB engine intentionally decide from one
    closed-bar view and one chain snapshot.  This also keeps the 90-second job
    inside cadence when other scanners are consuming the shared Kite budget.
    """
    monkeypatch.setattr(settings, "FNO_DR_DISABLE_PAPER", False)

    summary = await run_fno_tick(
        kite, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW,
    )

    assert summary["entries"]  # prove the directional consumer also ran
    assert kite.bar_calls == 1
    # One future mark + the chain's anchor and batched ladder.  A second chain
    # fetch for the directional book would add two more calls.
    assert kite.quote_calls == 3


@pytest.mark.asyncio
async def test_shadow_toggle_adds_no_market_or_order_calls(book, tmp_path, monkeypatch):
    import fno_orchestrator

    monkeypatch.setattr(settings, "FNO_DR_DISABLE_PAPER", True)
    enabled_kite = FakeKite(_breakout_bars(), _quote_table(book, NOW))
    disabled_kite = FakeKite(_breakout_bars(), _quote_table(book, NOW))

    monkeypatch.setattr(settings, "FNO_SHADOW_ENABLED", True)
    enabled = await run_fno_tick(
        enabled_kite, db_path=str(tmp_path / "enabled.db"),
        regime="REGIME_1_NORMAL", now_ist=NOW,
    )
    pending = list(fno_orchestrator._SHADOW_TASKS)
    monkeypatch.setattr(settings, "FNO_SHADOW_ENABLED", False)
    disabled = await run_fno_tick(
        disabled_kite, db_path=str(tmp_path / "disabled.db"),
        regime="REGIME_1_NORMAL", now_ist=NOW,
    )
    for task in pending:
        task.result(timeout=5)

    assert (enabled_kite.bar_calls, enabled_kite.quote_calls) == (
        disabled_kite.bar_calls, disabled_kite.quote_calls,
    )
    assert enabled_kite.orders_placed == disabled_kite.orders_placed == []
    assert [(row["direction"], row["lots"]) for row in enabled["entries"]] == [
        (row["direction"], row["lots"]) for row in disabled["entries"]
    ]


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


# ---------------------------------------------------------------------------
# [NAKED-LEG-EXPECTANCY 2026-07-31] Reward:risk gate on the single-leg book
# ---------------------------------------------------------------------------
# 12 naked legs since 2026-07-16: 2 winners, -Rs 15,474. The defined-risk
# spreads over the same window ran ~flat on a 1.7:1 structure. The geometry is
# what differs, so the gate encodes the geometry.

def _rr(*, delta, stop_pts, target_pts, premium, spread_pct, qty,
        stop_premium_pct):
    """Mirror of the orchestrator's reward:risk arithmetic, so the numbers a
    production reject is based on are pinned by a test."""
    reward = delta * target_pts * qty
    risk = min(delta * stop_pts, premium * stop_premium_pct) * qty
    spread = spread_pct * premium * qty
    return (reward - spread) / (risk + spread)


def test_the_2026_07_30_naked_leg_would_now_be_refused():
    """The real trade, with the levels production actually logged.

    NIFTY2680424350CE, 2 lots, fill 101.30, delta 0.55,
    entry_underlying 24375.2, stop_u 24333.2, target_u 24413.0.

    Note the asymmetry, and where it comes from: the engine anchors stop and
    target to the SIGNAL BAR's close (24365.1, r=31.9 -> 1.5R target), but the
    position filled 10 points higher at 24375.2. Measured from the price we
    actually paid, that 1.5:1 geometry had already become 37.8 points of
    reward against 42 points of risk -- 0.9:1 before the option's own drag.
    The gate therefore measures from the ENTRY underlying, not from the signal
    close, which is the whole reason it catches this trade."""
    from config import settings
    entry_u, stop_u, target_u = 24375.2, 24333.2, 24413.0
    rr = _rr(
        delta=0.55,
        stop_pts=abs(entry_u - stop_u),
        target_pts=abs(target_u - entry_u),
        premium=101.30, spread_pct=0.01, qty=130,
        stop_premium_pct=settings.FNO_STOP_PREMIUM_PCT,
    )
    assert rr < 1.0, f"expected a losing geometry, got rr={rr:.2f}"
    assert rr < settings.FNO_MIN_REWARD_RISK, (
        f"the trade that lost Rs 3,570 still passes the gate (rr={rr:.2f})"
    )


def test_entry_slippage_against_a_fixed_target_degrades_the_ratio():
    """Why the gate is anchored to the entry price.

    Same signal geometry, but the fill lands progressively further above the
    signal close. Stop and target are absolute levels, so every point of
    adverse slippage widens the risk and narrows the reward at once."""
    from config import settings
    signal_close, r_points = 24365.1, 31.9
    stop_u = signal_close - r_points
    target_u = signal_close + 1.5 * r_points
    ratios = []
    for slip in (0.0, 5.0, 10.0):
        entry_u = signal_close + slip
        ratios.append(_rr(
            delta=0.55,
            stop_pts=abs(entry_u - stop_u),
            target_pts=abs(target_u - entry_u),
            premium=101.30, spread_pct=0.01, qty=130,
            stop_premium_pct=settings.FNO_STOP_PREMIUM_PCT,
        ))
    assert ratios == sorted(ratios, reverse=True), ratios
    assert ratios[0] > settings.FNO_MIN_REWARD_RISK   # clean fill is tradeable
    assert ratios[-1] < settings.FNO_MIN_REWARD_RISK  # 10 pts of slip is not


def test_a_wide_target_with_a_tight_spread_still_passes():
    """The gate must not close the book entirely -- a genuinely favourable
    geometry (wide target, liquid strike) has to remain tradeable."""
    from config import settings
    rr = _rr(
        delta=0.55, stop_pts=30.0, target_pts=settings.FNO_TARGET_R * 30.0,
        premium=60.0, spread_pct=0.002, qty=130,
        stop_premium_pct=settings.FNO_STOP_PREMIUM_PCT,
    )
    assert rr >= settings.FNO_MIN_REWARD_RISK, (
        f"gate is too tight -- no naked leg could ever fire (rr={rr:.2f})"
    )


def test_spread_cost_is_charged_on_both_sides():
    """A wide bid-ask must degrade the ratio; it is paid entering and exiting."""
    from config import settings
    kw = dict(delta=0.55, stop_pts=30.0,
              target_pts=settings.FNO_TARGET_R * 30.0,
              premium=60.0, qty=130,
              stop_premium_pct=settings.FNO_STOP_PREMIUM_PCT)
    assert _rr(spread_pct=0.002, **kw) > _rr(spread_pct=0.02, **kw)


# ---------------------------------------------------------------------------
# [TIME-STOP-PREMIUM 2026-08-04] the clock must not cut a profitable trade
#
# The time stop measures UNDERLYING points while the book is paid in PREMIUM,
# and delta separates the two. It is the single biggest loser in this book's
# history (8 exits, -Rs 7,010) and two of those eight were cut while in profit:
# 2026-07-23 at +286 and 2026-08-03 at +530. Meanwhile trail_stop is the only
# exit reason with positive expectancy (2 exits, +Rs 2,869, avg +0.62R) -- and
# a trade can only reach the trail by living long enough to get there.
#
# Both tests hold the FUTURE flat, so underlying progress is exactly zero and
# the time stop's own condition is unambiguously met. Only the premium differs.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_time_stop_defers_when_the_premium_is_in_profit(
    kite, db_path, book, monkeypatch,
):
    monkeypatch.setattr(settings, "FNO_DR_DISABLE_PAPER", True)
    monkeypatch.setattr(settings, "FNO_TIME_STOP_RESPECTS_PREMIUM", True)
    from performance import init_ledger
    await init_ledger(db_path)
    await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)

    # Well past FNO_TIME_STOP_MIN, underlying unchanged, premium up.
    later = NOW + timedelta(minutes=settings.FNO_TIME_STOP_MIN + 5)
    kite.quote_table = _quote_table(book, later, opt_bid_shift=+8.0)
    summary = await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL",
                                 now_ist=later)

    assert summary["exits"] == [], (
        "a position up on premium was cut by the clock; this is the "
        "2026-08-03 +Rs 530 exit reproducing"
    )
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT status FROM fno_positions WHERE source='FNO_PAPER'"
        ) as cur:
            assert (await cur.fetchone())[0] == "OPEN"


@pytest.mark.asyncio
async def test_time_stop_still_cuts_a_losing_position_on_schedule(
    kite, db_path, book, monkeypatch,
):
    """The deferral must not disable the time stop. A trade going nowhere on
    the underlying AND losing on premium is still cut -- that is the whole
    purpose of the clock."""
    monkeypatch.setattr(settings, "FNO_DR_DISABLE_PAPER", True)
    monkeypatch.setattr(settings, "FNO_TIME_STOP_RESPECTS_PREMIUM", True)
    from performance import init_ledger
    await init_ledger(db_path)
    await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)

    later = NOW + timedelta(minutes=settings.FNO_TIME_STOP_MIN + 5)
    kite.quote_table = _quote_table(book, later, opt_bid_shift=-4.0)
    summary = await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL",
                                 now_ist=later)

    assert len(summary["exits"]) == 1
    assert summary["exits"][0]["reason"] == "time_stop"


@pytest.mark.asyncio
async def test_premium_deferral_can_be_switched_off(kite, db_path, book, monkeypatch):
    """Flag off restores the pre-2026-08-04 behaviour exactly, so the change
    is reversible without a code edit if the paper record argues against it."""
    monkeypatch.setattr(settings, "FNO_DR_DISABLE_PAPER", True)
    monkeypatch.setattr(settings, "FNO_TIME_STOP_RESPECTS_PREMIUM", False)
    from performance import init_ledger
    await init_ledger(db_path)
    await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)

    later = NOW + timedelta(minutes=settings.FNO_TIME_STOP_MIN + 5)
    kite.quote_table = _quote_table(book, later, opt_bid_shift=+8.0)
    summary = await run_fno_tick(kite, db_path=db_path, regime="REGIME_1_NORMAL",
                                 now_ist=later)

    assert len(summary["exits"]) == 1
    assert summary["exits"][0]["reason"] == "time_stop"
