"""[O25] The owner's real-money F&O test: the exit that must complete, the mirror
entry, the account's cash holds and the order route. Broker doubles only."""
import math
import sqlite3
from contextlib import closing
from datetime import datetime

import httpx
import pytest
import pytest_asyncio
import pytz

import fno_executor
import fno_live_test
import fno_orchestrator
import fno_positions as fpos
from config import settings
from fno_executor import FnoExecutor, exit_ladder_prices
from tests.test_fno_orchestrator import NOW, FakeKite, book, kite  # noqa: F401 (fixtures)

IST = pytz.timezone("Asia/Kolkata")
LATE = IST.localize(datetime(2026, 10, 27, 15, 15))       # past the 15:10 hard flat


@pytest.fixture
def quick_ladder(monkeypatch):
    """The real ladder's prices with short waits, so a test runs in milliseconds."""
    monkeypatch.setattr(fno_executor, "EXIT_LADDER", tuple((share, ticks, 0.02)
                                                           for share, ticks, _wait in fno_executor.EXIT_LADDER))


class Killed(BaseException):
    """The process dies here (not an Exception: nothing in the engine catches it)."""


class Broker:
    """One working order at a time, as Kite keeps it: placed (with its tag),
    modified when accepted, cancelled, and read back with its resting price."""

    def __init__(self, *, place=None, fill_after_modifies=None, terminal=None, fill_price=None,
                 refuse_modifies=0, die_while_waiting=False):
        self.placed, self.modified, self.attempts, self.cancelled, self.quotes = [], [], [], [], 0
        self.place_reply = place
        self.fill_after = fill_after_modifies
        self.terminal = terminal
        self.fill_price = fill_price
        self.refuse_modifies = refuse_modifies
        self.die_while_waiting = die_while_waiting
        self.complete = False
        self.resting = None

    async def place_order(self, **kw):
        self.placed.append(kw)
        if self.place_reply is not None:
            return dict(self.place_reply)
        self.resting = kw.get("price")
        return {"order_id": f"B{len(self.placed)}", "dispatch_certainty": "ACCEPTED"}

    async def modify_order(self, order_id, price=None, **kw):
        self.attempts.append(price)
        if self.refuse_modifies > 0:
            self.refuse_modifies -= 1
            return {"order_id": order_id, "status": "ERROR", "message": "HTTP 400: price out of range"}
        self.modified.append(price)
        self.resting = price
        return {"order_id": order_id, "status": "MODIFIED"}

    async def cancel_order(self, order_id, variety="regular"):
        self.cancelled.append(order_id)
        return {"order_id": order_id, "status": "CANCELLED"}

    def _state(self) -> dict:
        if self.terminal is not None:
            return dict(self.terminal)
        if self.complete or (self.fill_after is not None and len(self.modified) >= self.fill_after):
            price = self.fill_price or self.resting
            return {"status": "COMPLETE", "filled_quantity": self.placed[-1]["quantity"], "average_price": price,
                    "price": self.resting}
        if self.cancelled:
            return {"status": "CANCELLED", "filled_quantity": 0, "price": self.resting}
        return {"status": "OPEN", "filled_quantity": 0, "price": self.resting}

    async def order_history(self, order_id):
        if self.die_while_waiting:
            raise Killed()
        return [{**self._state(), "order_timestamp": "2026-10-27 15:15:00"}]

    async def orders_snapshot(self):
        return [{**self._state(), "order_id": f"B{i + 1}", "tag": kw.get("tag"), "tradingsymbol": kw["tradingsymbol"],
                 "transaction_type": kw["transaction_type"], "quantity": kw["quantity"],
                 "order_timestamp": "2026-10-27 15:15:00"} for i, kw in enumerate(self.placed)]

    async def get_quote(self, tokens):
        self.quotes += 1
        return {1: {"last_price": 100.0, "depth": {"buy": [{"price": 100.0}], "sell": [{"price": 100.5}]}}}


def _live(broker) -> FnoExecutor:
    executor = FnoExecutor(broker, paper_mode=False, source_tag="FNO_LIVE")
    executor.poll_interval_sec = 0.005
    return executor


# ---------------------------------------------------------------- the exit that must complete

def test_the_ladder_steps_down_under_the_bid_and_never_below_a_tick():
    assert exit_ladder_prices(100.0, 0.05) == [(99.5, 4.0), (97.0, 6.0), (90.0, 20.0)]
    low = [price for price, _ in exit_ladder_prices(2.0, 0.05)]
    assert low == sorted(low, reverse=True) and low[-1] == 0.05


@pytest.mark.asyncio
async def test_a_live_exit_is_one_order_moved_lower_until_it_fills(quick_ladder):
    broker = Broker(fill_after_modifies=2)
    result = await _live(broker).execute_exit("NIFTY26OCT25000CE", 65, 100.0, 0.05)
    assert result == {"status": "filled", "order_id": "B1", "fill_price": 90.0}
    assert len(broker.placed) == 1 and broker.placed[0]["price"] == 99.5          # never a second SELL
    assert broker.placed[0]["transaction_type"] == "SELL" and broker.placed[0]["intent"] == "exit"
    assert broker.modified == [97.0, 90.0]


@pytest.mark.asyncio
async def test_the_hard_flat_starts_at_the_deepest_step(quick_ladder):
    broker = Broker(fill_after_modifies=0)
    result = await _live(broker).execute_exit("NIFTY26OCT25000CE", 65, 100.0, 0.05, hard_flat=True)
    assert result["status"] == "filled" and broker.placed[0]["price"] == 90.0 and broker.modified == []


@pytest.mark.asyncio
async def test_what_an_unfilled_exit_leaves_is_named(quick_ladder):
    not_sent = Broker(place={"order_id": None, "dispatch_certainty": "NOT_SENT"})
    assert (await _live(not_sent).execute_exit("S", 65, 100.0, 0.05))["status"] == "not_sent"
    ambiguous = Broker(place={"order_id": None, "dispatch_certainty": "AMBIGUOUS"})
    assert (await _live(ambiguous).execute_exit("S", 65, 100.0, 0.05))["status"] == "unknown"
    rejected = Broker(terminal={"status": "REJECTED", "filled_quantity": 0, "status_message": "price band"})
    assert (await _live(rejected).execute_exit("S", 65, 100.0, 0.05))["status"] == "rejected_verified"
    working = Broker()
    result = await _live(working).execute_exit("S", 65, 100.0, 0.05)
    assert result == {"status": "unfilled", "order_id": "B1", "fill_price": None, "limit": 90.0}
    # A later pass moves it under the fresh bid (never up), then reads the fill.
    followed = await _live(working).follow_exit("B1", 90.0, 80.0, 0.05)
    assert working.modified[-1] == 72.0 and followed["status"] == "unfilled" and followed["limit"] == 72.0
    working.complete = True
    assert (await _live(working).follow_exit("B1", 72.0, 79.0, 0.05))["status"] == "filled"
    assert len(working.placed) == 1


# ---------------------------------------------------------------- management of a live position

async def _live_position(db: str, *, entry_order_id: str) -> int:
    return await fpos.insert_position(
        db, source="FNO_LIVE", tradingsymbol="NIFTY26OCT25000CE", token=1, underlying="NIFTY",
        expiry="2026-10-27", strike=25000.0, opt_type="CE", direction="LONG", lots=1, lot_size=65, qty=65,
        entry_time=LATE.replace(hour=10).isoformat(), entry_date="2026-10-27", entry_premium=110.0,
        entry_underlying=25000.0, delta_at_entry=0.55, iv_at_entry=0.12, atr_at_entry=40.0,
        stop_underlying=24950.0, target_underlying=25100.0, premium_stop=82.5, max_loss_rupees=7150.0,
        bar_ts="2026-10-27 10:00:00", entry_order_id=entry_order_id,
    )


@pytest_asyncio.fixture
async def live_db(tmp_path):
    from performance import init_ledger
    path = str(tmp_path / "live.db")
    await fpos.init_fno_positions_db(path)
    await init_ledger(path)
    return path


def _status(db: str, position_id: int):
    with closing(sqlite3.connect(db)) as conn:
        row = conn.execute("SELECT status, exit_premium, exit_reason, exit_order_id FROM fno_positions WHERE id=?",
                           (position_id,)).fetchone()
        intents = conn.execute("SELECT order_id FROM fno_exit_intents WHERE position_id=?",
                               (position_id,)).fetchall()
    return row, intents


@pytest.mark.asyncio
async def test_an_exit_that_never_left_is_sent_again_on_the_next_pass(live_db, quick_ladder, monkeypatch):
    monkeypatch.setattr(fno_orchestrator, "_page_live_exit_once", _no_page)
    position_id = await _live_position(live_db, entry_order_id="LIVE-ENTRY-1")
    broker = Broker(place={"order_id": None, "dispatch_certainty": "NOT_SENT"})
    assert await fno_orchestrator._manage_open_positions(broker, live_db, "FNO_LIVE", _live(broker), LATE,
                                                         25000.0) == []
    assert _status(live_db, position_id) == (("OPEN", None, None, None), [])          # the claim was freed
    broker.place_reply, broker.fill_after = None, 0
    closed = await fno_orchestrator._manage_open_positions(broker, live_db, "FNO_LIVE", _live(broker), LATE,
                                                           25000.0)
    assert len(closed) == 1 and len(broker.placed) == 2
    assert _status(live_db, position_id)[0][:3] == ("CLOSED", 90.0, "hard_flat_1510")


@pytest.mark.asyncio
async def test_a_working_exit_is_followed_after_a_restart_until_it_fills(live_db, quick_ladder, monkeypatch):
    monkeypatch.setattr(fno_orchestrator, "_page_live_exit_once", _no_page)
    position_id = await _live_position(live_db, entry_order_id="LIVE-ENTRY-1")
    broker = Broker()
    assert await fno_orchestrator._manage_open_positions(broker, live_db, "FNO_LIVE", _live(broker), LATE,
                                                         25000.0) == []
    assert _status(live_db, position_id) == (("OPEN", None, None, None), [("B1",)])   # kept on the claim
    broker.complete = True                                                       # it filled meanwhile
    later = FnoExecutor(broker, paper_mode=False, source_tag="FNO_LIVE")           # a new process
    later.poll_interval_sec = 0.005
    closed = await fno_orchestrator._manage_open_positions(broker, live_db, "FNO_LIVE", later, LATE, 25000.0)
    assert len(closed) == 1 and len(broker.placed) == 1                            # no second SELL
    assert _status(live_db, position_id) == (("CLOSED", 90.0, "hard_flat_1510", "B1"), [])


@pytest.mark.asyncio
async def test_each_live_position_is_exited_the_way_it_was_entered(live_db, monkeypatch):
    paper_row = await _live_position(live_db, entry_order_id="PAPER-FNO-ENT-1")
    broker = Broker(fill_after_modifies=0)
    closed = await fno_orchestrator._manage_open_positions(broker, live_db, "FNO_LIVE", _live(broker), LATE,
                                                           25000.0)
    assert len(closed) == 1 and broker.placed == []                    # a paper row is never sold for real
    assert _status(live_db, paper_row)[0][0] == "CLOSED"
    real = await _live_position(live_db, entry_order_id="LIVE-ENTRY-2")
    monkeypatch.setattr(settings, "FNO_DISABLE_LIVE", True)
    monkeypatch.setattr(settings, "FNO_LIVE_TEST_ENABLED", False)
    assert await fno_orchestrator._live_leg_managed(live_db)          # the switches are off, a position is open
    paper_exec = FnoExecutor(broker, paper_mode=True, source_tag="FNO_LIVE")
    position = (await fpos.open_positions(live_db, "FNO_LIVE"))[0]
    assert position.id == real and not fno_orchestrator._executor_for_position(broker, paper_exec, "FNO_LIVE",
                                                                               position).paper_mode


class SoldInKite(Broker):
    """The owner sold it in Kite: the broker's positions hold none of it."""

    async def get_broker_positions(self):
        return {"net": [{"tradingsymbol": "NIFTY26OCT25000CE", "quantity": 0, "product": "MIS"}]}


@pytest.mark.asyncio
async def test_a_position_the_broker_no_longer_holds_is_never_sold_again(live_db, quick_ladder, monkeypatch):
    pages = []

    async def page(position, reason, text):
        pages.append(reason)

    monkeypatch.setattr(fno_orchestrator, "_page_live_exit_once", page)
    position_id = await _live_position(live_db, entry_order_id="LIVE-ENTRY-1")
    broker = SoldInKite(fill_after_modifies=0)
    assert await fno_orchestrator._manage_open_positions(broker, live_db, "FNO_LIVE", _live(broker), LATE,
                                                         25000.0) == []
    assert broker.placed == [] and pages == ["not_held"]                      # no SELL: it would be a short
    # claimed: listed for exit recovery, and no later pass sells it
    assert _status(live_db, position_id) == (("OPEN", None, None, None), [(None,)])
    assert await fno_orchestrator._manage_open_positions(broker, live_db, "FNO_LIVE", _live(broker), LATE,
                                                         25000.0) == []
    assert broker.placed == []


async def _no_page(*args, **kwargs):
    return None


# ---------------------------------------------------------------- the mirror entry

class LiveKite(FakeKite):
    """The orchestrator's synthetic market, plus a broker that fills a LIMIT at its price."""

    def __init__(self, bars, quote_table):
        super().__init__(bars, quote_table)
        self.history = {}

    async def place_order(self, **kw):
        self.orders_placed.append(kw)
        order_id = f"LIVE-{len(self.orders_placed)}"
        state = ({"status": "TRIGGER PENDING", "filled_quantity": 0} if kw.get("order_type") == "SL"
                 else {"status": "COMPLETE", "filled_quantity": kw["quantity"], "average_price": kw["price"]})
        self.history[order_id] = {**state, "order_timestamp": "2026-07-10 10:03:00"}
        return {"order_id": order_id, "dispatch_certainty": "ACCEPTED"}

    async def order_history(self, order_id):
        return [self.history[order_id]] if order_id in self.history else []

    async def orders_snapshot(self):
        return []


@pytest.fixture
def armed(monkeypatch):
    monkeypatch.setattr(settings, "FNO_LIVE_TEST_ENABLED", True)
    monkeypatch.setattr(settings, "FNO_LIVE_TEST_CAPITAL", 12500.0)
    monkeypatch.setattr(settings, "FNO_LIVE_TEST_FLOOR", 7000.0)


def _rows(db: str, source: str):
    with closing(sqlite3.connect(db)) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM fno_positions WHERE source=? ORDER BY id", (source,))]


@pytest.mark.asyncio
async def test_the_test_buys_one_real_lot_of_what_the_paper_book_bought(book, db_path, armed):
    from fno_orchestrator import format_fno_telegram, run_fno_tick
    from tests.test_fno_orchestrator import _breakout_bars, _quote_table
    broker = LiveKite(_breakout_bars(), _quote_table(book, NOW))
    summary = await run_fno_tick(broker, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)
    sources = [e["source"] for e in summary["entries"]]
    assert sources == ["FNO_PAPER", "FNO_LIVE"], summary
    [paper], [live] = _rows(db_path, "FNO_PAPER"), _rows(db_path, "FNO_LIVE")
    assert paper["lots"] == 2 and live["lots"] == 1 and live["qty"] == 75
    for same in ("tradingsymbol", "token", "direction", "stop_underlying", "target_underlying", "bar_ts", "expiry"):
        assert live[same] == paper[same], same
    buy, stop = broker.orders_placed
    ask = broker.quote_table[live["token"]]["depth"]["sell"][0]["price"]
    assert (buy["transaction_type"], buy["order_type"], buy["product"], buy["quantity"]) == ("BUY", "LIMIT", "MIS", 75)
    on_grid = math.ceil(round(ask / 0.05, 6)) * 0.05                             # the ask on the tick grid
    assert buy["price"] == pytest.approx(on_grid + 2 * 0.05) and buy["price"] <= paper["entry_premium"] * 1.02
    assert live["entry_premium"] == buy["price"] and live["entry_order_id"] == "LIVE-1"
    assert live["premium_stop"] == pytest.approx(0.75 * live["entry_premium"], abs=0.01)
    assert (stop["transaction_type"], stop["order_type"], stop["quantity"]) == ("SELL", "SL", 75)     # backstop
    text = format_fno_telegram(summary)
    assert "💰 REAL MONEY ENTRY [FNO_LIVE]" in text and "paper bought @" in text


@pytest.mark.asyncio
async def test_without_the_switch_nothing_real_is_sent(book, db_path, monkeypatch):
    from fno_orchestrator import run_fno_tick
    from tests.test_fno_orchestrator import _breakout_bars, _quote_table
    monkeypatch.setattr(settings, "FNO_LIVE_TEST_ENABLED", False)
    broker = LiveKite(_breakout_bars(), _quote_table(book, NOW))
    summary = await run_fno_tick(broker, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)
    assert [e["source"] for e in summary["entries"]] == ["FNO_PAPER"] and broker.orders_placed == []


async def _reasons(db: str):
    with closing(sqlite3.connect(db)) as conn:
        return [r[0] for r in conn.execute("SELECT reject_reason FROM fno_signals WHERE leg='FNO_LIVE' "
                                           "AND accepted=0 ORDER BY rowid")]


async def _mirror(book, db, broker, *, sig, when=NOW):
    paper = _rows(db, "FNO_PAPER")[-1]
    return await fno_live_test.mirror_entry(
        broker, db, _live(broker), sig=sig, paper_entry={"symbol": paper["tradingsymbol"]}, underlying="NIFTY",
        instruments=book, regime="REGIME_1_NORMAL", now_ist=when, scan_id="T")


@pytest_asyncio.fixture
async def paper_entered(book, db_path, monkeypatch):
    """A paper entry on the synthetic breakout, with the switch off (the mirror is called by hand)."""
    from fno_engine_mom import evaluate_fno_mom
    from fno_orchestrator import run_fno_tick
    from tests.test_fno_orchestrator import _breakout_bars, _quote_table
    monkeypatch.setattr(settings, "FNO_LIVE_TEST_ENABLED", False)
    broker = LiveKite(_breakout_bars(), _quote_table(book, NOW))
    await run_fno_tick(broker, db_path=db_path, regime="REGIME_1_NORMAL", now_ist=NOW)
    monkeypatch.setattr(settings, "FNO_LIVE_TEST_ENABLED", True)
    return broker, evaluate_fno_mom(_breakout_bars(), "REGIME_1_NORMAL", NOW)


@pytest.mark.asyncio
async def test_the_mirror_refuses_what_the_test_rules_out(book, db_path, paper_entered, monkeypatch):
    broker, sig = paper_entered
    token = _rows(db_path, "FNO_PAPER")[-1]["token"]
    quote = broker.quote_table[token]
    original = {side: [dict(level) for level in quote["depth"][side]] for side in ("buy", "sell")}
    for side in ("buy", "sell"):                                                    # ran 3% past paper
        quote["depth"][side][0]["price"] = round(original[side][0]["price"] * 1.03, 2)
    assert await _mirror(book, db_path, broker, sig=sig) is None
    quote["depth"] = original
    monkeypatch.setattr(book, "is_expiry_day", lambda day: True)
    assert await _mirror(book, db_path, broker, sig=sig) is None
    monkeypatch.setattr(book, "is_expiry_day", lambda day: False)
    monkeypatch.setattr(settings, "FNO_LIVE_TEST_CAPITAL", 4000.0)                    # a lot costs more
    monkeypatch.setattr(settings, "FNO_LIVE_TEST_FLOOR", 1000.0)
    assert await _mirror(book, db_path, broker, sig=sig) is None
    monkeypatch.setattr(settings, "FNO_LIVE_TEST_FLOOR", 7000.0)
    monkeypatch.setattr(fno_live_test, "_FLOOR_TOLD", set())
    told = []

    async def notify(text, *, event):
        told.append(event)
        return True

    import operator_alert
    monkeypatch.setattr(operator_alert, "notify_operator", notify)
    monkeypatch.setattr(settings, "FNO_LIVE_TEST_CAPITAL", 6500.0)                    # under the 7,000 floor
    assert await _mirror(book, db_path, broker, sig=sig) is None
    assert await _mirror(book, db_path, broker, sig=sig) is None and told == ["fno_live_test_floor"]
    assert await _reasons(db_path) == ["live_test_price_ran", "live_test_expiry_day",
                                       "live_test_shared_worst_case_cash_exhausted", "live_test_floor",
                                       "live_test_floor"]
    assert broker.orders_placed == []


@pytest.mark.asyncio
async def test_an_unfilled_real_buy_is_cancelled_and_frees_its_cash(book, db_path, paper_entered):
    broker, sig = paper_entered

    async def resting(**kw):                       # the ask moved away: the LIMIT rests, then is cancelled
        broker.orders_placed.append(kw)
        broker.history["LIVE-X"] = {"status": "OPEN", "filled_quantity": 0, "order_timestamp": "2026-07-10 10:03:00"}
        return {"order_id": "LIVE-X", "dispatch_certainty": "ACCEPTED"}

    async def cancel(order_id, variety="regular"):
        broker.history[order_id] = {"status": "CANCELLED", "filled_quantity": 0,
                                    "order_timestamp": "2026-07-10 10:03:40"}
        return {"status": "CANCELLED"}

    broker.place_order, broker.cancel_order = resting, cancel
    executor = _live(broker)
    executor.fill_timeout_sec = 0.02
    paper = _rows(db_path, "FNO_PAPER")[-1]
    assert await fno_live_test.mirror_entry(
        broker, db_path, executor, sig=sig, paper_entry={"symbol": paper["tradingsymbol"]}, underlying="NIFTY",
        instruments=book, regime="REGIME_1_NORMAL", now_ist=NOW, scan_id="T") is None
    assert _rows(db_path, "FNO_LIVE") == [] and (await _reasons(db_path))[-1] == "entry_zero_fill_verified"
    with closing(sqlite3.connect(db_path)) as conn:
        assert conn.execute("SELECT state FROM fno_risk_reservations WHERE source='FNO_LIVE'").fetchall() \
            == [("RELEASED",)]


def test_the_buy_limit_is_the_ask_plus_two_ticks_inside_the_chase_cap():
    assert fno_live_test.entry_limit(100.0, 0.05, 2, cap=102.0) == 100.1
    assert fno_live_test.entry_limit(101.97, 0.05, 2, cap=102.0) == 102.0
    assert fno_live_test.entry_limit(102.03, 0.05, 2, cap=102.0) is None


# ---------------------------------------------------------------- the account's own-cash holds

def test_a_filled_buy_frees_its_hold_so_the_next_day_can_trade(tmp_path, monkeypatch):
    from kite_client import KiteClient
    monkeypatch.setattr(settings, "KITE_ORDER_BASE_URL", "")
    client = KiteClient(str(tmp_path / "cash.db"))
    holds = client.account_cash_reservations
    for rid, order_id in (("PY:A", "O-1"), ("PY:B", "O-2")):
        holds.reserve(reservation_id=rid, account_id="kite-primary", book="fno", broker_tag=rid[3:],
                      notional=7000.0, own_uncommitted_cash=12500.0 if rid == "PY:A" else 20000.0, broker_orders=[])
        holds.mark_dispatch(rid, broker_order_id=order_id, ambiguous=False)
    assert client.settle_entry_reservation("O-1", final_status="COMPLETE", filled_quantity=65)
    assert client.settle_entry_reservation("O-2", final_status="CANCELLED", filled_quantity=0)
    assert not client.settle_entry_reservation("O-3", final_status="COMPLETE", filled_quantity=65)
    # The next day's order book no longer lists them: nothing is held, a ₹9k buy fits ₹12.5k.
    assert holds.reserve(reservation_id="PY:C", account_id="kite-primary", book="fno", broker_tag="C",
                         notional=9000.0, own_uncommitted_cash=12500.0, broker_orders=[]).amount > 9000.0


def test_a_hold_with_an_unproven_outcome_stays(tmp_path, monkeypatch):
    from account_cash_reservations import ReservationRefused
    from kite_client import KiteClient
    monkeypatch.setattr(settings, "KITE_ORDER_BASE_URL", "")
    client = KiteClient(str(tmp_path / "cash.db"))
    holds = client.account_cash_reservations
    holds.reserve(reservation_id="PY:A", account_id="kite-primary", book="fno", broker_tag="A", notional=7000.0,
                  own_uncommitted_cash=12500.0, broker_orders=[])
    holds.mark_dispatch("PY:A", broker_order_id="O-1", ambiguous=False)
    assert not client.settle_entry_reservation("O-1", final_status="OPEN", filled_quantity=0)
    with pytest.raises(ReservationRefused):
        holds.reserve(reservation_id="PY:B", account_id="kite-primary", book="fno", broker_tag="B",
                      notional=7000.0, own_uncommitted_cash=12500.0, broker_orders=[])


# ---------------------------------------------------------------- the order route

@pytest.mark.asyncio
async def test_order_writes_leave_from_the_order_route_and_reads_do_not(tmp_path, monkeypatch):
    from kite_client import KiteClient
    monkeypatch.setattr(settings, "KITE_BASE_URL", "https://api.kite.trade")
    monkeypatch.setattr(settings, "KITE_ORDER_BASE_URL", "http://relay.test:31527/")
    client = KiteClient(str(tmp_path / "route.db"))
    client.set_token("TOKEN")
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.host, request.headers.get("Authorization", "")[-5:]))
        if request.method == "GET":
            return httpx.Response(200, json={"data": []})
        return httpx.Response(200, json={"data": {"order_id": "R1"}})

    for http in (client.client, client.order_client):
        http._transport = httpx.MockTransport(handler)
    await client.modify_order("R1", price=90.0)
    await client.cancel_order("R1")
    await client.order_history("R1")
    assert seen == [("PUT", "relay.test", "TOKEN"), ("DELETE", "relay.test", "TOKEN"),
                    ("GET", "api.kite.trade", "TOKEN")]
    monkeypatch.setattr(settings, "KITE_ORDER_BASE_URL", "")
    assert KiteClient(str(tmp_path / "route2.db")).order_client is None          # unset: one client, as before


# ---------------------------------------------------------------- [O25b] the review's reproduced gaps

@pytest.mark.asyncio
async def test_a_refused_price_change_is_not_taken_for_one_and_is_tried_again(quick_ladder):
    broker = Broker(refuse_modifies=2)                         # both ladder modifications refused
    result = await _live(broker).execute_exit("S", 65, 100.0, 0.05)
    assert result["status"] == "unfilled" and result["limit"] == 99.5     # where it really rests
    followed = await _live(broker).follow_exit("B1", result["limit"], 100.0, 0.05)
    assert broker.attempts[-1] == 90.0 and followed["limit"] == 90.0      # the next pass moves it


@pytest.mark.asyncio
async def test_a_restart_while_the_sell_waits_follows_the_same_order(live_db, quick_ladder, monkeypatch):
    monkeypatch.setattr(fno_orchestrator, "_page_live_exit_once", _no_page)
    position_id = await _live_position(live_db, entry_order_id="LIVE-ENTRY-1")
    broker = Broker(die_while_waiting=True)
    with pytest.raises(Killed):
        await fno_orchestrator._manage_open_positions(broker, live_db, "FNO_LIVE", _live(broker), LATE, 25000.0)
    broker.die_while_waiting, broker.complete = False, True                # it filled while the engine was down
    closed = await fno_orchestrator._manage_open_positions(broker, live_db, "FNO_LIVE", _live(broker), LATE,
                                                           25000.0)
    assert len(closed) == 1 and len(broker.placed) == 1                    # followed, never sent twice
    assert _status(live_db, position_id)[0][3] == "B1"


@pytest.mark.asyncio
async def test_a_send_whose_reply_was_lost_is_found_by_its_tag(live_db, quick_ladder, monkeypatch):
    monkeypatch.setattr(fno_orchestrator, "_page_live_exit_once", _no_page)
    position_id = await _live_position(live_db, entry_order_id="LIVE-ENTRY-1")
    broker = Broker()
    assert await fpos.claim_exit_intent(live_db, position_id, "FNO_LIVE")
    await fpos.record_exit_tag(live_db, position_id, "FNO_LIVE", tag="FXlostreply000000",
                               exit_reason="hard_flat_1510")
    await broker.place_order(tradingsymbol="NIFTY26OCT25000CE", transaction_type="SELL", quantity=65, price=99.5,
                             tag="FXlostreply000000")                       # it reached Kite; the reply was lost
    assert await fno_orchestrator._manage_open_positions(broker, live_db, "FNO_LIVE", _live(broker), LATE,
                                                         25000.0) == []
    assert _status(live_db, position_id)[1] == [("B1",)]                    # adopted from the order book
    broker.complete = True
    assert len(await fno_orchestrator._manage_open_positions(broker, live_db, "FNO_LIVE", _live(broker), LATE,
                                                             25000.0)) == 1
    assert len(broker.placed) == 1


@pytest.mark.asyncio
async def test_a_tagged_send_that_never_reached_kite_is_sent_again(live_db, quick_ladder, monkeypatch):
    monkeypatch.setattr(fno_orchestrator, "_page_live_exit_once", _no_page)
    position_id = await _live_position(live_db, entry_order_id="LIVE-ENTRY-1")
    assert await fpos.claim_exit_intent(live_db, position_id, "FNO_LIVE")
    await fpos.record_exit_tag(live_db, position_id, "FNO_LIVE", tag="FXneversent0000000",
                               exit_reason="hard_flat_1510")
    with closing(sqlite3.connect(live_db)) as conn:                         # claimed a minute earlier
        conn.execute("UPDATE fno_exit_intents SET created_at=?", (LATE.replace(minute=14).isoformat(),))
        conn.commit()
    broker = Broker(fill_after_modifies=0)
    assert await fno_orchestrator._manage_open_positions(broker, live_db, "FNO_LIVE", _live(broker), LATE,
                                                         25000.0) == []
    assert _status(live_db, position_id)[1] == [] and broker.placed == []   # absent from the book: freed
    assert len(await fno_orchestrator._manage_open_positions(broker, live_db, "FNO_LIVE", _live(broker), LATE,
                                                             25000.0)) == 1


class HeldAsNrml(Broker):
    """Kite holds the contract only under NRML; the system's own MIS lot is gone."""

    async def get_broker_positions(self):
        return {"net": [{"tradingsymbol": "NIFTY26OCT25000CE", "exchange": "NFO", "product": "MIS", "quantity": 0},
                        {"tradingsymbol": "NIFTY26OCT25000CE", "exchange": "NFO", "product": "NRML",
                         "quantity": 65}]}


@pytest.mark.asyncio
async def test_an_nrml_holding_never_lets_an_mis_sell_through(live_db, quick_ladder, monkeypatch):
    pages = []

    async def page(position, reason, text):
        pages.append(reason)

    monkeypatch.setattr(fno_orchestrator, "_page_live_exit_once", page)
    await _live_position(live_db, entry_order_id="LIVE-ENTRY-1")
    broker = HeldAsNrml(fill_after_modifies=0)
    assert await fno_orchestrator._manage_open_positions(broker, live_db, "FNO_LIVE", _live(broker), LATE,
                                                         25000.0) == []
    assert broker.placed == [] and pages == ["not_held"]


@pytest.mark.asyncio
async def test_only_nifty_is_ever_bought_for_real(book, db_path, paper_entered, monkeypatch):
    broker, sig = paper_entered
    paper = _rows(db_path, "FNO_PAPER")[-1]
    import aiosqlite
    async with aiosqlite.connect(db_path) as conn:                           # the same trade, on BANKNIFTY
        await conn.execute("UPDATE fno_positions SET underlying='BANKNIFTY' WHERE id=?", (paper["id"],))
        await conn.commit()
    assert await fno_live_test.mirror_entry(
        broker, db_path, _live(broker), sig=sig, paper_entry={"symbol": paper["tradingsymbol"]},
        underlying="BANKNIFTY", instruments=book, regime="REGIME_1_NORMAL", now_ist=NOW, scan_id="T") is None
    assert broker.orders_placed == [] and (await _reasons(db_path))[-1] == "live_test_not_nifty"


# ---------------------------------------------------------------- [O25b] bounded runs, readiness, evidence

@pytest.mark.asyncio
async def test_a_run_ends_after_its_sessions_and_the_owner_is_told_once(book, db_path, paper_entered, monkeypatch):
    broker, sig = paper_entered
    from datetime import date
    first = await fno_live_test.current_run(db_path, date(2026, 7, 1))            # armed on Wed Jul 1
    assert (first["label"], first["started_on"], first["session"], first["ended"]) == ("1", "2026-07-01", 1, False)
    assert (await fno_live_test.current_run(db_path, date(2026, 7, 7)))["ended"] is False     # the 5th session
    later = await fno_live_test.current_run(db_path, date(2026, 7, 8))            # the 6th
    assert (later["session"], later["ended"]) == (6, True)
    told = []

    async def notify(text, *, event):
        told.append(event)
        return True

    import operator_alert
    monkeypatch.setattr(operator_alert, "notify_operator", notify)
    monkeypatch.setattr(fno_live_test, "_RUN_END_TOLD", set())
    assert await _mirror(book, db_path, broker, sig=sig) is None                 # NOW (Fri Jul 10): session 8
    assert await _mirror(book, db_path, broker, sig=sig) is None
    assert told == ["fno_live_test_run_ended"] and broker.orders_placed == []
    assert (await _reasons(db_path))[-2:] == ["live_test_run_ended", "live_test_run_ended"]
    monkeypatch.setattr(settings, "FNO_LIVE_TEST_RUN", "2")                       # a new, named run
    assert (await fno_live_test.current_run(db_path, date(2026, 11, 2)))["session"] == 1


class Account:
    """The account as the morning check reads it."""

    def __init__(self, *, cash=15000.0, logged_in=True, held=(), route_down=None):
        from datetime import date
        self.access_token = "T" if logged_in else ""
        self.token_set_ist_date = date(2026, 11, 2) if logged_in else None
        self.cash, self.held, self.route_down = cash, list(held), route_down

    async def probe_order_route(self):
        return self.route_down

    async def get_funds_margins(self):
        return {"equity": {"enabled": True, "available": {"cash": self.cash}, "utilised": {"m2m_realised": 0.0}}}

    async def get_broker_positions(self):
        return {"net": self.held}

    async def orders_snapshot(self):
        return []


@pytest.mark.asyncio
async def test_the_morning_check_says_ready_or_names_what_is_missing(live_db, armed, monkeypatch):
    monkeypatch.setattr(settings, "KITE_ORDER_PROXY_URL", "http://relay.test:8888")
    monkeypatch.setattr(settings, "KITE_ORDER_BASE_URL", "")
    monday = IST.localize(datetime(2026, 11, 2, 9, 25))
    for i, premium in enumerate((120.0, 140.0, 136.0)):                         # lots of ₹7.8k-9.1k
        await fpos.insert_position(
            live_db, source="FNO_PAPER", tradingsymbol=f"NIFTYX{i}CE", token=i, underlying="NIFTY",
            expiry="2026-11-03", strike=25000.0, opt_type="CE", direction="LONG", lots=1, lot_size=65, qty=65,
            entry_time=f"2026-10-2{i}T10:00:00+05:30", entry_date=f"2026-10-2{i}", entry_premium=premium,
            entry_underlying=25000.0, delta_at_entry=0.55, iv_at_entry=0.12, atr_at_entry=40.0,
            stop_underlying=24950.0, target_underlying=25100.0, premium_stop=0.75 * premium,
            max_loss_rupees=premium * 65, bar_ts=f"2026-10-2{i} 10:00:00")
    ready = await fno_live_test.morning_check(Account(), live_db, monday)
    assert ready == ("✅ REAL-money F&O test ready today: orders via an encrypted tunnel; free cash ₹15,000 (a lot "
                     "has cost about ₹8,840); run 1, session 1 of 5; equity ₹12,500 (floor ₹7,000).")
    short = await fno_live_test.morning_check(Account(cash=8000.0), live_db, monday)
    assert short.startswith("⚠️ REAL-money F&O test NOT ready today: free cash ₹8,000 is under a typical lot")
    out = await fno_live_test.morning_check(Account(logged_in=False), live_db, monday)
    assert "no Kite login for today yet" in out
    nrml = Account(held=[{"tradingsymbol": "NIFTY26NOV25000CE", "exchange": "NFO", "product": "NRML",
                          "quantity": 65}])
    assert "the broker holds F&O positions this morning: NIFTY26NOV25000CE NRML 65" in \
        await fno_live_test.morning_check(nrml, live_db, monday)
    tunnel_down = await fno_live_test.morning_check(Account(route_down="ProxyError: 407"), live_db, monday)
    assert tunnel_down.startswith("⚠️ REAL-money F&O test NOT ready today: the order route does not answer "
                                  "(ProxyError: 407): check the tunnel on the VM")
    monkeypatch.setattr(settings, "FNO_LIVE_TEST_ENABLED", False)
    assert await fno_live_test.morning_check(Account(), live_db, monday) is None


@pytest.mark.asyncio
async def test_the_evening_report_shows_how_each_real_trade_was_executed(live_db, armed):
    import aiosqlite

    async def closed(source, entry, exit_, when):
        position_id = await fpos.insert_position(
            live_db, source=source, tradingsymbol="NIFTY26NOV25000CE", token=1, underlying="NIFTY",
            expiry="2026-11-03", strike=25000.0, opt_type="CE", direction="LONG", lots=1, lot_size=65, qty=65,
            entry_time=when, entry_date="2026-11-02", entry_premium=entry, entry_underlying=25000.0,
            delta_at_entry=0.55, iv_at_entry=0.12, atr_at_entry=40.0, stop_underlying=24950.0,
            target_underlying=25100.0, premium_stop=0.75 * entry, max_loss_rupees=entry * 65,
            bar_ts="2026-11-02 10:00:00", entry_order_id="LIVE-1" if source == "FNO_LIVE" else "PAPER-FNO-ENT-1")
        pnl = fno_live_test.one_lot_pnl(entry, exit_, 65)
        async with aiosqlite.connect(live_db) as db:
            await db.execute("UPDATE fno_positions SET status='CLOSED', exit_premium=?, exit_reason='trail_stop', "
                             "pnl=?, exit_date='2026-11-02' WHERE id=?", (exit_, pnl, position_id))
            await db.commit()
        return position_id

    await closed("FNO_PAPER", 100.0, 110.2, "2026-11-02T10:00:02+05:30")
    live = await closed("FNO_LIVE", 100.1, 110.0, "2026-11-02T10:00:06+05:30")
    await fno_live_test.record_event(live_db, live, "entry_filled", {"decision_to_fill_sec": 4.2})
    await fno_live_test.record_event(live_db, live, "exit_modified", {"price": 108.0})
    await fno_live_test.record_event(live_db, live, "exit_modify_refused", {"price": 100.0})
    text = await fno_live_test.day_report(live_db, "2026-11-02")
    lines = text.split("\n")
    assert lines[0].startswith("💰 REAL-money F&O test, 2026-11-02: 1 real trade(s) -- run 1, session")
    paper_lot, real_lot = fno_live_test.one_lot_pnl(100.0, 110.2, 65), fno_live_test.one_lot_pnl(100.1, 110.0, 65)
    assert lines[1] == (f"- NIFTY26NOV25000CE: real ₹100.10 → ₹110.00 (trail_stop) = +₹{real_lot:,.0f}; paper "
                        f"₹100.00 → ₹110.20 = +₹{paper_lot:,.0f} a lot; bought +₹0.10/unit (+0.1% worse) vs paper, "
                        "4s after the paper decision; sold +₹0.20/unit (+0.2% worse) vs paper; exit price moved 1x, "
                        "1 change(s) refused")
    assert "Outstanding: nothing" in text and "the floor stops new entries, it cannot cap" in text


@pytest.mark.asyncio
async def test_a_claim_left_without_a_name_is_held_and_paged_never_sold(live_db, quick_ladder, monkeypatch):
    pages = []

    async def page(position, reason, text):
        pages.append(reason)

    monkeypatch.setattr(fno_orchestrator, "_page_live_exit_once", page)
    position_id = await _live_position(live_db, entry_order_id="LIVE-ENTRY-1")
    assert await fpos.claim_exit_intent(live_db, position_id, "FNO_LIVE")      # stopped before naming it
    broker = Broker(fill_after_modifies=0)
    for _ in range(2):
        assert await fno_orchestrator._manage_open_positions(broker, live_db, "FNO_LIVE", _live(broker), LATE,
                                                             25000.0) == []
    assert broker.placed == [] and pages == ["claimed_unsent", "claimed_unsent"]   # (the real page dedupes)
    assert _status(live_db, position_id) == (("OPEN", None, None, None), [(None,)])
