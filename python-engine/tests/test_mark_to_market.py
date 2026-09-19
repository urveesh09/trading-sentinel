"""[WORKFLOW-F 2026-09-13] Mark-to-market valuation acceptance.

Closes F3 (sub-slices F3.a, F3.b, F3.c) of workstream F per
``docs/2026-09-13-workflow-f-state-of-codebase-audit.md`` section 6
future plan and ``docs/NEXT_AGENT_PLAN.md`` section 10.4.

Acceptance coverage for ``python-engine/mark_to_market.py``.

[WHY-THIS-EXISTS 2026-09-13]
  Pre-fix, ``main.py:1599`` read ``p.get(\"current_price\", 0.0)`` from
  every penny position and silently reported ``Unrealised: +Rs 0``
  because the ``positions`` table has no ``current_price`` column.
  The hourly report lied about open P&L. F3 ships the producer
  side; the consumer-side wiring is deferred to a follow-up commit
  that calls ``mark_open_positions`` from the orchestrator tick.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from mark_to_market import (
    MAX_QUOTE_AGE_SECONDS,
    OpenMarkToMarket,
    PositionMark,
    QuoteStatus,
    QuoteTick,
    mark_open_positions,
)


# ---- helpers ---------------------------------------------------------------

def _now() -> datetime:
    """Return a fresh tz-aware UTC reference instant."""
    return datetime.now(timezone.utc)


def _quote(last_price: float, age_seconds: int = 0) -> QuoteTick:
    """Build a QuoteTick ``age_seconds`` before now."""
    return QuoteTick.build(last_price, _now() - timedelta(seconds=age_seconds))


def _equity_row(
    ticker: str = "TCS",
    shares: int = 10,
    entry_price: float = 3000.0,
    source: str = "PENNY",
) -> Dict[str, Any]:
    return {
        "ticker": ticker,
        "shares": shares,
        "entry_price": entry_price,
        "source": source,
    }


def _fno_row(
    tradingsymbol: str = "BANKNIFTY26SEP25400CE",
    token: int = 12345,
    qty: int = 1,
    lot_size: int = 15,
    entry_premium: float = 100.0,
    source: str = "FNO_PAPER",
) -> Dict[str, Any]:
    return {
        "tradingsymbol": tradingsymbol,
        "token": token,
        "qty": qty,
        "lot_size": lot_size,
        "entry_premium": entry_premium,
        "source": source,
    }


def _fno_dr_row(
    structure_id: int = 7,
    legs: List[Dict[str, Any]] = None,
    net_premium_rs: float = 200.0,
    source: str = "FNO_PAPER",
) -> Dict[str, Any]:
    return {
        "id": structure_id,
        "kind": "BULL_CALL_SPREAD",
        "legs_json": json.dumps(legs or []),
        "net_premium_rs": net_premium_rs,
        "source": source,
    }


# ---- QuoteTick validation --------------------------------------------------

class TestQuoteTickValidation:
    def test_rejects_nan_price(self) -> None:
        with pytest.raises(ValueError, match="last_price"):
            QuoteTick.build(float("nan"), _now())

    def test_rejects_inf_price(self) -> None:
        with pytest.raises(ValueError, match="last_price"):
            QuoteTick.build(float("inf"), _now())

    def test_rejects_negative_inf_price(self) -> None:
        with pytest.raises(ValueError, match="last_price"):
            QuoteTick.build(float("-inf"), _now())

    def test_rejects_naive_datetime(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            QuoteTick.build(100.0, datetime(2026, 9, 13, 10, 0, 0))

    def test_rejects_none_datetime(self) -> None:
        with pytest.raises(ValueError, match="must not be None"):
            QuoteTick.build(100.0, None)  # type: ignore[arg-type]

    def test_accepts_zero_price_with_fresh_datetime(self) -> None:
        # A delisted or halted instrument could legitimately have LTP 0.
        # The validation accepts this; the consumer decides whether 0
        # is a sensible mark.
        t = QuoteTick.build(0.0, _now())
        assert t.last_price == 0.0


# ---- Equity MTM ------------------------------------------------------------

class TestEquityMark:
    def test_fresh_quote_profit(self) -> None:
        now = _now()
        result = mark_open_positions(
            equity_rows=[_equity_row(shares=10, entry_price=3000.0)],
            fno_rows=[],
            fno_dr_rows=[],
            quotes={"TCS": _quote(3500.0, age_seconds=0)},
            now_utc=now,
        )
        assert result.total_unrealised_pnl == pytest.approx(5000.0)
        m = result.marks[0]
        assert m.subsystem == "EQUITY"
        assert m.quote_status == QuoteStatus.FRESH
        assert m.entry_cost == pytest.approx(30_000.0)
        assert m.unrealised_pnl == pytest.approx(5000.0)
        assert m.quote_age_seconds == 0

    def test_fresh_quote_loss(self) -> None:
        now = _now()
        result = mark_open_positions(
            equity_rows=[_equity_row(shares=10, entry_price=3000.0)],
            fno_rows=[],
            fno_dr_rows=[],
            quotes={"TCS": _quote(2800.0)},
            now_utc=now,
        )
        # (2800 - 3000) * 10 = -2000
        assert result.total_unrealised_pnl == pytest.approx(-2000.0)

    def test_partial_close_remaining_quantity(self) -> None:
        """A 100-share position with shares=30 after a partial T1 exit."""
        now = _now()
        result = mark_open_positions(
            equity_rows=[_equity_row(shares=30, entry_price=3000.0)],
            fno_rows=[],
            fno_dr_rows=[],
            quotes={"TCS": _quote(3300.0)},
            now_utc=now,
        )
        # (3300 - 3000) * 30 = +9000
        assert result.total_unrealised_pnl == pytest.approx(9000.0)

    def test_zero_shares_position_is_flat(self) -> None:
        now = _now()
        result = mark_open_positions(
            equity_rows=[_equity_row(shares=0, entry_price=3000.0)],
            fno_rows=[],
            fno_dr_rows=[],
            quotes={"TCS": _quote(3300.0)},
            now_utc=now,
        )
        assert result.total_unrealised_pnl == pytest.approx(0.0)
        assert result.marks[0].quote_status == QuoteStatus.FRESH

    def test_missing_quote_returns_unavailable(self) -> None:
        now = _now()
        result = mark_open_positions(
            equity_rows=[_equity_row()],
            fno_rows=[],
            fno_dr_rows=[],
            quotes={},
            now_utc=now,
        )
        assert result.total_unrealised_pnl == 0.0
        assert result.marks[0].quote_status == QuoteStatus.UNAVAILABLE
        assert result.marks[0].quote_age_seconds is None

    def test_stale_quote_is_rejected(self) -> None:
        now = _now()
        result = mark_open_positions(
            equity_rows=[_equity_row()],
            fno_rows=[],
            fno_dr_rows=[],
            quotes={"TCS": _quote(3500.0, age_seconds=MAX_QUOTE_AGE_SECONDS + 60)},
            now_utc=now,
        )
        assert result.total_unrealised_pnl == 0.0
        assert result.marks[0].quote_status == QuoteStatus.STALE
        # STALE marks still carry the observed mark_price so the
        # operator can see *what* the stale quote said.
        assert result.marks[0].mark_price == pytest.approx(3500.0)

    def test_future_quote_treated_as_stale(self) -> None:
        """A clock-skewed tick (now_utc older than the tick) is rejected."""
        now = _now()
        future_tick = QuoteTick.build(3500.0, now + timedelta(seconds=60))
        result = mark_open_positions(
            equity_rows=[_equity_row()],
            fno_rows=[],
            fno_dr_rows=[],
            quotes={"TCS": future_tick},
            now_utc=now,
        )
        assert result.total_unrealised_pnl == 0.0
        assert result.marks[0].quote_status == QuoteStatus.STALE

    def test_custom_freshness_window(self) -> None:
        now = _now()
        result = mark_open_positions(
            equity_rows=[_equity_row()],
            fno_rows=[],
            fno_dr_rows=[],
            quotes={"TCS": _quote(3500.0, age_seconds=10)},
            now_utc=now,
            freshness_seconds=5,  # 10s > 5s budget
        )
        assert result.marks[0].quote_status == QuoteStatus.STALE

    def test_negative_freshness_rejected(self) -> None:
        now = _now()
        with pytest.raises(ValueError, match="freshness_seconds"):
            mark_open_positions(
                equity_rows=[], fno_rows=[], fno_dr_rows=[],
                quotes={}, now_utc=now, freshness_seconds=-1,
            )

    def test_naive_now_utc_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            mark_open_positions(
                equity_rows=[_equity_row()],
                fno_rows=[],
                fno_dr_rows=[],
                quotes={"TCS": _quote(3500.0)},
                now_utc=datetime(2026, 9, 13, 10, 0, 0),  # naive
            )


# ---- Equity validation -----------------------------------------------------

class TestEquityValidation:
    def test_missing_ticker_rejected(self) -> None:
        row = {"shares": 10, "entry_price": 100.0, "source": "PENNY"}
        with pytest.raises(ValueError, match="ticker"):
            mark_open_positions(
                equity_rows=[row], fno_rows=[], fno_dr_rows=[],
                quotes={}, now_utc=_now(),
            )

    def test_empty_ticker_rejected(self) -> None:
        with pytest.raises(ValueError, match="ticker"):
            mark_open_positions(
                equity_rows=[{"ticker": "", "shares": 10, "entry_price": 100.0, "source": "PENNY"}],
                fno_rows=[], fno_dr_rows=[], quotes={}, now_utc=_now(),
            )

    def test_negative_shares_rejected(self) -> None:
        with pytest.raises(ValueError, match="shares"):
            mark_open_positions(
                equity_rows=[_equity_row(shares=-1)],
                fno_rows=[], fno_dr_rows=[], quotes={}, now_utc=_now(),
            )

    def test_bool_shares_rejected(self) -> None:
        with pytest.raises(ValueError, match="shares"):
            mark_open_positions(
                equity_rows=[{"ticker": "X", "shares": True, "entry_price": 100.0, "source": "PENNY"}],
                fno_rows=[], fno_dr_rows=[], quotes={}, now_utc=_now(),
            )

    def test_nan_entry_price_rejected(self) -> None:
        with pytest.raises(ValueError, match="entry_price"):
            mark_open_positions(
                equity_rows=[{"ticker": "X", "shares": 10, "entry_price": float("nan"), "source": "PENNY"}],
                fno_rows=[], fno_dr_rows=[], quotes={}, now_utc=_now(),
            )

    def test_string_entry_price_rejected_when_not_numeric(self) -> None:
        # ``float("100")`` succeeds, so a numeric string is accepted
        # (a SQLite row might carry one). A non-numeric string is
        # rejected because no real number can be derived.
        with pytest.raises(ValueError, match="entry_price"):
            mark_open_positions(
                equity_rows=[{"ticker": "X", "shares": 10, "entry_price": "not_a_number", "source": "PENNY"}],
                fno_rows=[], fno_dr_rows=[], quotes={}, now_utc=_now(),
            )

    def test_numeric_string_entry_price_accepted(self) -> None:
        # SQLite often carries numerics as strings; accept them
        # silently rather than failing every MTM call.
        now = _now()
        result = mark_open_positions(
            equity_rows=[{"ticker": "TCS", "shares": 10, "entry_price": "3000", "source": "PENNY"}],
            fno_rows=[], fno_dr_rows=[],
            quotes={"TCS": _quote(3500.0)}, now_utc=now,
        )
        assert result.total_unrealised_pnl == pytest.approx(5000.0)


# ---- F&O MTM ---------------------------------------------------------------

class TestFnoMark:
    def test_fresh_quote_uses_premium_multiplier(self) -> None:
        now = _now()
        # qty is contracts, not lots: (110 - 100) * 25 = 250.
        result = mark_open_positions(
            equity_rows=[],
            fno_rows=[_fno_row(entry_premium=100.0, lot_size=25, qty=25)],
            fno_dr_rows=[],
            quotes={"BANKNIFTY26SEP25400CE": _quote(110.0)},
            now_utc=now,
        )
        assert result.total_unrealised_pnl == pytest.approx(250.0)
        m = result.marks[0]
        assert m.subsystem == "FNO"
        assert m.entry_cost == pytest.approx(2500.0)  # 100 * 25

    def test_fno_negative_premium_quote(self) -> None:
        now = _now()
        result = mark_open_positions(
            equity_rows=[],
            fno_rows=[_fno_row(entry_premium=100.0, lot_size=25, qty=25)],
            fno_dr_rows=[],
            quotes={"BANKNIFTY26SEP25400CE": _quote(80.0)},
            now_utc=now,
        )
        # (80 - 100) * 25 = -500
        assert result.total_unrealised_pnl == pytest.approx(-500.0)

    def test_fno_lookup_by_token_fallback(self) -> None:
        """When tradingsymbol misses, the token key is tried."""
        now = _now()
        result = mark_open_positions(
            equity_rows=[],
            fno_rows=[_fno_row(tradingsymbol="MISS", token=98765, qty=15, entry_premium=50.0)],
            fno_dr_rows=[],
            quotes={98765: _quote(70.0)},
            now_utc=now,
        )
        # (70 - 50) * 15 = +300
        assert result.total_unrealised_pnl == pytest.approx(300.0)
        assert result.marks[0].quote_status == QuoteStatus.FRESH

    @pytest.mark.asyncio
    async def test_actual_fno_writer_qty_is_not_multiplied_twice(self, tmp_path) -> None:
        """Bind MTM to the owning SQLite writer/readback contract."""
        from fno_positions import insert_position, open_positions

        db_path = str(tmp_path / "fno.db")
        await insert_position(
            db_path,
            source="FNO_PAPER", tradingsymbol="BANKNIFTY26SEP25400CE",
            token=12345, lots=1, lot_size=50, qty=50,
            entry_premium=100.0,
        )
        [stored] = await open_positions(db_path, "FNO_PAPER")
        now = _now()
        result = mark_open_positions(
            equity_rows=[], fno_rows=[asdict(stored)], fno_dr_rows=[],
            quotes={12345: _quote(110.0)}, now_utc=now,
        )
        assert result.marks[0].entry_cost == pytest.approx(5_000.0)
        assert result.total_unrealised_pnl == pytest.approx(500.0)

    def test_fno_zero_qty_is_flat(self) -> None:
        now = _now()
        result = mark_open_positions(
            equity_rows=[],
            fno_rows=[_fno_row(qty=0, entry_premium=100.0)],
            fno_dr_rows=[],
            quotes={"BANKNIFTY26SEP25400CE": _quote(150.0)},
            now_utc=now,
        )
        assert result.total_unrealised_pnl == 0.0
        assert result.marks[0].quote_status == QuoteStatus.FRESH

    def test_fno_lot_size_required_positive(self) -> None:
        with pytest.raises(ValueError, match="lot_size"):
            mark_open_positions(
                equity_rows=[],
                fno_rows=[_fno_row(lot_size=0)],
                fno_dr_rows=[],
                quotes={},
                now_utc=_now(),
            )

    def test_fno_qty_non_negative(self) -> None:
        with pytest.raises(ValueError, match="qty"):
            mark_open_positions(
                equity_rows=[],
                fno_rows=[_fno_row(qty=-5)],
                fno_dr_rows=[],
                quotes={},
                now_utc=_now(),
            )

    def test_fno_nan_premium_rejected(self) -> None:
        with pytest.raises(ValueError, match="entry_premium"):
            mark_open_positions(
                equity_rows=[],
                fno_rows=[{"tradingsymbol": "X", "qty": 1, "lot_size": 25,
                           "entry_premium": float("nan"), "source": "FNO_PAPER"}],
                fno_dr_rows=[],
                quotes={},
                now_utc=_now(),
            )


# ---- F&O debit/credit MTM --------------------------------------------------

class TestFnoDrMark:
    @pytest.mark.asyncio
    async def test_actual_dr_writer_row_is_explicitly_unsupported(self, tmp_path) -> None:
        """Real stored DR legs lack an immutable quote identity."""
        from fno_defined_risk import Structure, StructureKind
        from fno_dr_book import PlannedStructure, init_dr_db, insert_structure, open_structures
        from fno_models import Leg, OptionType

        db_path = str(tmp_path / "dr.db")
        await init_dr_db(db_path)
        structure = Structure(
            kind=StructureKind.DEBIT_SPREAD,
            legs=[Leg(OptionType.CE, 25_000.0, 1, 100.0)],
            lot_size=25, net_premium=-100.0, max_profit_rs=100.0,
            max_loss_rs=100.0, breakevens=[25_100.0],
        )
        await insert_structure(
            db_path, "FNO_PAPER", PlannedStructure(structure, 25_000.0), _now(),
        )
        [stored] = await open_structures(db_path, "FNO_PAPER")
        result = mark_open_positions(
            equity_rows=[], fno_rows=[], fno_dr_rows=[stored],
            quotes={"unrelated": _quote(999.0)}, now_utc=_now(),
        )
        assert result.marks[0].quote_status == QuoteStatus.UNSUPPORTED
        assert "immutable" in result.marks[0].notes
    def test_all_legs_fresh(self) -> None:
        now = _now()
        # Two-leg spread: long 25400CE @ 100, short 25600CE @ 50. Net
        # premium paid = 50. Current marks: long 130, short 60.
        # Long leg pnl = (130 - 100) * 1 * 25 = +750
        # Short leg pnl = (60 - 50) * 1 * 25 * -1 = -250 (short multiplies
        #   by direction=-1; convention depends on the broker. We use
        #   direction as a signed multiplier with the default +1.)
        # Wait: in real DR book convention ``direction`` is a string like
        # 'BUY' / 'SELL'. We treat direction as a *signed multiplier*
        # where the caller can pass either string-encoded directions
        # via a numeric direction. To keep the public surface tight we
        # use the convention: BUY = +1, SELL = -1. The caller is
        # responsible for the mapping.
        legs = [
            {"tradingsymbol": "BANKNIFTY26SEP25400CE", "qty": 1,
             "lot_size": 25, "entry_premium": 100.0, "direction": 1.0},
            {"tradingsymbol": "BANKNIFTY26SEP25600CE", "qty": 1,
             "lot_size": 25, "entry_premium": 50.0, "direction": -1.0},
        ]
        quotes = {
            "BANKNIFTY26SEP25400CE": _quote(130.0),
            "BANKNIFTY26SEP25600CE": _quote(60.0),
        }
        result = mark_open_positions(
            equity_rows=[],
            fno_rows=[],
            fno_dr_rows=[_fno_dr_row(legs=legs, net_premium_rs=1250.0)],
            quotes=quotes,
            now_utc=now,
        )
        # Long pnl: 30 * 1 * 25 = +750
        # Short pnl: 10 * 1 * 25 * -1 = -250
        # Total leg marks = 500
        # Net premium = 1250 (entry_cost)
        # Structure pnl = 500 - 1250 = -750
        assert result.total_unrealised_pnl == pytest.approx(-750.0)
        m = result.marks[0]
        assert m.subsystem == "FNO_DR"
        assert m.quote_status == QuoteStatus.FRESH
        assert m.entry_cost == pytest.approx(1250.0)

    def test_one_leg_stale_marks_structure_stale(self) -> None:
        now = _now()
        legs = [
            {"tradingsymbol": "A", "qty": 1, "lot_size": 25,
             "entry_premium": 100.0, "direction": 1.0},
            {"tradingsymbol": "B", "qty": 1, "lot_size": 25,
             "entry_premium": 50.0, "direction": -1.0},
        ]
        quotes = {
            "A": _quote(110.0),  # fresh
            "B": _quote(60.0, age_seconds=MAX_QUOTE_AGE_SECONDS + 60),  # stale
        }
        result = mark_open_positions(
            equity_rows=[],
            fno_rows=[],
            fno_dr_rows=[_fno_dr_row(legs=legs)],
            quotes=quotes,
            now_utc=now,
        )
        # One stale leg -> structure is STALE; pnl is not added to
        # aggregate (conservative). mark_price stays 0.0 for the row.
        assert result.total_unrealised_pnl == 0.0
        assert result.marks[0].quote_status == QuoteStatus.STALE

    def test_unparseable_legs_json(self) -> None:
        now = _now()
        result = mark_open_positions(
            equity_rows=[],
            fno_rows=[],
            fno_dr_rows=[{"id": 1, "legs_json": "{not json", "net_premium_rs": 100.0, "source": "FNO_PAPER"}],
            quotes={},
            now_utc=now,
        )
        assert result.marks[0].quote_status == QuoteStatus.UNAVAILABLE

    def test_empty_legs_returns_unavailable(self) -> None:
        now = _now()
        result = mark_open_positions(
            equity_rows=[],
            fno_rows=[],
            fno_dr_rows=[_fno_dr_row(legs=[])],
            quotes={},
            now_utc=now,
        )
        assert result.marks[0].quote_status == QuoteStatus.UNAVAILABLE

    def test_non_dict_leg_is_marked_unsupported(self) -> None:
        now = _now()
        result = mark_open_positions(
            equity_rows=[],
            fno_rows=[],
            fno_dr_rows=[_fno_dr_row(legs=["not a dict"])],
            quotes={},
            now_utc=now,
        )
        assert result.marks[0].quote_status == QuoteStatus.UNSUPPORTED

    def test_nan_net_premium_rejected(self) -> None:
        with pytest.raises(ValueError, match="net_premium_rs"):
            mark_open_positions(
                equity_rows=[],
                fno_rows=[],
                fno_dr_rows=[{"legs_json": "[]", "net_premium_rs": float("nan"), "source": "X"}],
                quotes={},
                now_utc=_now(),
            )


# ---- Aggregation -----------------------------------------------------------

class TestAggregation:
    def test_aggregate_sums_only_fresh_and_stale_with_mark(self) -> None:
        """Stale marks contribute 0 to the aggregate but keep the data."""
        now = _now()
        result = mark_open_positions(
            equity_rows=[
                _equity_row(ticker="FRESH", shares=10, entry_price=3000.0),
                _equity_row(ticker="STALE", shares=10, entry_price=3000.0),
                _equity_row(ticker="MISS", shares=10, entry_price=3000.0),
            ],
            fno_rows=[],
            fno_dr_rows=[],
            quotes={
                "FRESH": _quote(3500.0),  # +5000
                "STALE": _quote(3500.0, age_seconds=MAX_QUOTE_AGE_SECONDS + 60),
                # MISS: no quote
            },
            now_utc=now,
        )
        # Only FRESH contributes: +5000
        assert result.total_unrealised_pnl == pytest.approx(5000.0)
        assert result.count_by_status == {
            QuoteStatus.FRESH: 1,
            QuoteStatus.STALE: 1,
            QuoteStatus.UNAVAILABLE: 1,
            QuoteStatus.UNSUPPORTED: 0,
        }

    def test_filter_by_source_isolates_rows(self) -> None:
        now = _now()
        result = mark_open_positions(
            equity_rows=[
                _equity_row(ticker="A", source="EDGE_LIVE", shares=10),
                _equity_row(ticker="B", source="EDGE_PAPER", shares=10),
            ],
            fno_rows=[],
            fno_dr_rows=[],
            quotes={"A": _quote(3500.0), "B": _quote(3600.0)},
            now_utc=now,
        )
        live = result.filter_by_source("EDGE_LIVE")
        paper = result.filter_by_source("EDGE_PAPER")
        assert len(live.marks) == 1
        assert len(paper.marks) == 1
        assert live.marks[0].source == "EDGE_LIVE"
        assert paper.marks[0].source == "EDGE_PAPER"

    def test_empty_inputs_return_empty_result(self) -> None:
        now = _now()
        result = mark_open_positions(
            equity_rows=[], fno_rows=[], fno_dr_rows=[],
            quotes={}, now_utc=now,
        )
        assert result.marks == []
        assert result.total_unrealised_pnl == 0.0
        assert result.count_by_status == {
            QuoteStatus.FRESH: 0,
            QuoteStatus.STALE: 0,
            QuoteStatus.UNAVAILABLE: 0,
            QuoteStatus.UNSUPPORTED: 0,
        }

    def test_count_by_subsystem(self) -> None:
        now = _now()
        result = mark_open_positions(
            equity_rows=[_equity_row()],
            fno_rows=[_fno_row()],
            fno_dr_rows=[_fno_dr_row(legs=[
                {"tradingsymbol": "X", "qty": 1, "lot_size": 25, "entry_premium": 100.0, "direction": 1.0}
            ])],
            quotes={"TCS": _quote(3500.0), "BANKNIFTY26SEP25400CE": _quote(110.0), "X": _quote(110.0)},
            now_utc=now,
        )
        assert result.count_by_subsystem == {"EQUITY": 1, "FNO": 1, "FNO_DR": 1}


# ---- Reproduction / determinism --------------------------------------------

class TestReproducibility:
    """The same inputs must produce the same P&L across runs."""

    def test_same_inputs_same_pnl(self) -> None:
        now = _now()
        kwargs = dict(
            equity_rows=[_equity_row(ticker="A", shares=10, entry_price=100.0)],
            fno_rows=[_fno_row(entry_premium=50.0, lot_size=25, qty=2)],
            fno_dr_rows=[],
            quotes={"A": _quote(110.0), "BANKNIFTY26SEP25400CE": _quote(60.0)},
            now_utc=now,
        )
        r1 = mark_open_positions(**kwargs)
        r2 = mark_open_positions(**kwargs)
        assert r1.total_unrealised_pnl == r2.total_unrealised_pnl

    def test_summary_string_format_stable(self) -> None:
        # Build a tick whose age is *strictly* in the past (age=1s)
        # so that sub-second clock jitter between this call and the
        # ``mark_open_positions`` invocation never crosses the
        # freshness boundary. The summary's ``age=Ns`` substring is
        # excluded from the assertion for the same reason.
        now = _now()
        tick_as_of = now - timedelta(seconds=1)
        tick = QuoteTick.build(3500.0, tick_as_of)
        result = mark_open_positions(
            equity_rows=[_equity_row()],
            fno_rows=[],
            fno_dr_rows=[],
            quotes={"TCS": tick},
            now_utc=now,
        )
        s = result.marks[0].summary()
        # Snapshot the substring positions; the exact numbers come
        # from the inputs. Lock down the structural shape only.
        # ``age=Ns`` is intentionally NOT asserted because the
        # integer-second truncation can drift by one between
        # subprocess calls.
        assert s.startswith("[EQUITY/PENNY/TCS]")
        assert "entry=Rs" in s
        assert "mark=Rs" in s
        assert "pnl=" in s
        assert "quote=FRESH" in s


# ---- Silent-zero bug regression --------------------------------------------

class TestSilentZeroRegression:
    """The exact bug F3 closes: ``main.py:1599`` previously read
    ``p.get(\"current_price\", 0.0)`` and silently returned 0.0 because
    the column does not exist. The new module computes the correct
    P&L from the row's actual entry_price and a fresh quote.
    """

    def test_main_penny_unrealised_computation_now_correct(self) -> None:
        """Reproduce the main.py:1599 expression with MTM and compare.

        The pre-F3 expression was
        ``(p.get(\"current_price\", 0.0) - p.get(\"entry_price\", 0.0))
        * p.get(\"shares\", 0)``. With ``current_price`` missing from
        every row, ``p.get(\"current_price\", 0.0)`` returns ``0.0`` and
        the expression collapses to ``-entry_price * shares``. For a
        TCS position with entry=3000 and shares=10, that gives
        ``-30000`` -- a false loss of 30,000 rupees on a position
        whose mark is *unknown*. MTM replaces the lie with either a
        correct FRESH mark (when a quote is supplied) or a STALE/
        UNAVAILABLE mark (when it is not).
        """
        now = _now()
        penny_pos = [
            {"ticker": "TCS", "shares": 10, "entry_price": 3000.0, "source": "PENNY"},
        ]
        deployed_stale = sum(
            (p.get("entry_price", 0.0) * p.get("shares", 0)) for p in penny_pos
        )
        unrealised_stale = sum(
            (p.get("current_price", 0.0) - p.get("entry_price", 0.0))
            * p.get("shares", 0)
            for p in penny_pos
        )
        # The silent-zero bug is *worse* than I initially thought:
        # because every ``current_price`` is missing, the expression
        # collapses to ``-entry_price * shares``. The hourly report
        # has been reporting a false -30,000 rupee loss, NOT a true
        # zero. The bug is asymmetric and dangerous.
        assert deployed_stale == 30_000.0
        assert unrealised_stale == -30_000.0  # the silent-zero bug

        # MTM with a fresh quote produces the correct unrealised P&L.
        result = mark_open_positions(
            equity_rows=penny_pos, fno_rows=[], fno_dr_rows=[],
            # Bind the quote to the same clock as the report. Calling _quote()
            # here samples a second ``now`` which can cross a Windows clock
            # tick under full-suite load and make the quote microscopically
            # future-dated (correctly rejected by the runtime as stale).
            quotes={"TCS": QuoteTick.build(3500.0, now)}, now_utc=now,
        )
        assert result.total_unrealised_pnl == pytest.approx(5000.0)

        # MTM without a quote produces UNAVAILABLE, not the silent
        # false loss. The hourly report can now distinguish
        # \"unknown\" from \"false loss\".
        result_no_quote = mark_open_positions(
            equity_rows=penny_pos, fno_rows=[], fno_dr_rows=[],
            quotes={}, now_utc=now,
        )
        assert result_no_quote.total_unrealised_pnl == 0.0
        assert (
            result_no_quote.marks[0].quote_status == QuoteStatus.UNAVAILABLE
        )
