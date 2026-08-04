"""
[DIVISION-BREAKDOWN 2026-07-15] Per-division P&L attribution.

Verifies that division_breakdown() attributes P&L to the correct division by
ledger `source`, rolls capital up per pool (swing + momentum share ONE Nifty
pool, counted once), and totals live vs paper separately — and that the
Telegram formatter renders it without error.
"""
import sqlite3
import pytest

import performance
from performance import (
    division_breakdown,
    format_division_breakdown,
    record_trade_close,
)


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "cache.db")
    con = sqlite3.connect(path)
    con.execute(
        """
        CREATE TABLE bankroll_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT, event_type TEXT, ticker TEXT, pnl REAL,
            bankroll_before REAL, bankroll_after REAL, source TEXT
        )
        """
    )
    con.commit()
    con.close()
    return path


def _div(data, key):
    return next(d for d in data["divisions"] if d["key"] == key)


@pytest.mark.asyncio
async def test_pnl_is_attributed_to_the_right_division(db):
    await record_trade_close(db, "AAA", -124.88, source="MOMENTUM")
    await record_trade_close(db, "BBB", 39.16, source="EDGE_LIVE")
    await record_trade_close(db, "CCC", 1732.60, source="EDGE_PAPER")

    data = await division_breakdown(db)

    assert _div(data, "momentum")["realised_pnl"] == pytest.approx(-124.88)
    assert _div(data, "penny_edge_live")["realised_pnl"] == pytest.approx(39.16)
    assert _div(data, "penny_edge_paper")["realised_pnl"] == pytest.approx(1732.60)
    # Swing saw no trades — a momentum loss must not bleed into it.
    assert _div(data, "swing")["realised_pnl"] == 0.0
    assert _div(data, "swing")["trades"] == 0
    assert _div(data, "momentum")["trades"] == 1


@pytest.mark.asyncio
async def test_swing_and_momentum_split_the_nifty_pool(db):
    # Swing and momentum are separate, non-overlapping slices of the Nifty pool,
    # divided by MOMENTUM_POOL_PCT.
    #
    # [CAPITAL-REALLOC 2026-07-26] No longer 50/50. Rs 500 of REAL capital moved
    # from swing to the penny edge live book (INITIAL_BANKROLL 5,000 -> 4,500) and
    # the split moved to 5/9 so momentum kept its full Rs 2,500:
    #     momentum = 4500 * 5/9 = 2500,  swing = 4500 * 4/9 = 2000.
    # The property under test is unchanged -- the two slices are complementary and
    # sum to the pool -- so it is asserted from settings rather than pinned.
    await record_trade_close(db, "SW", 200.0, source="SYSTEM")
    await record_trade_close(db, "MO", -50.0, source="MOMENTUM")

    data = await division_breakdown(db)
    mom_share = performance.settings.INITIAL_BANKROLL * performance.settings.MOMENTUM_POOL_PCT
    swing = _div(data, "swing")
    momentum = _div(data, "momentum")
    # abs=0.01: _division_registry rounds allocations to paise, and 5/9 is a
    # repeating fraction, so sub-paise equality is not a meaningful assertion.
    assert swing["allocated"] == pytest.approx(
        performance.settings.INITIAL_BANKROLL - mom_share, abs=0.01)
    assert momentum["allocated"] == pytest.approx(mom_share, abs=0.01)
    # Together they sum to the full Nifty pool — no double counting.
    assert swing["allocated"] + momentum["allocated"] == pytest.approx(
        performance.settings.INITIAL_BANKROLL, abs=0.01)
    assert swing["realised_pnl"] == pytest.approx(200.0)
    assert momentum["realised_pnl"] == pytest.approx(-50.0)


@pytest.mark.asyncio
async def test_live_and_paper_totalled_separately(db):
    await record_trade_close(db, "L", 39.16, source="EDGE_LIVE")     # live
    await record_trade_close(db, "P", 1732.60, source="EDGE_PAPER")  # paper

    data = await division_breakdown(db)
    live = data["totals"]["live"]
    paper = data["totals"]["paper"]

    # Paper P&L must never land in the live total.
    assert live["realised_pnl"] == pytest.approx(39.16)
    assert paper["realised_pnl"] == pytest.approx(1732.60)
    # Live capital = Nifty 5000 + penny_breakout + edge_live 1000 (+ fno_live 0).
    assert live["capacity"] > 0
    assert paper["capacity"] >= 100000  # edge paper alone


@pytest.mark.asyncio
async def test_formatter_renders(db):
    await record_trade_close(db, "MO", -124.88, source="MOMENTUM")
    data = await division_breakdown(db)
    text = format_division_breakdown(data)
    assert "Bankroll by Division" in text
    assert "Intraday Momentum" in text
    assert "LIVE" in text and "PAPER" in text


# ---- [PAPER-MARKING 2026-08-04] paper money must not read as real ----------
#
# The F&O tick message rendered `pnl=Rs -730` for a book that has never held a
# rupee, on the same day the genuine live loss was Rs 8.41. Two numbers 87x
# apart, formatted identically, separated only by a bracketed source tag
# mid-line. The 2026-08-04 audit misread the F&O ledger for exactly this
# reason; an operator glancing at a phone has less time than an audit.

from performance import fmt_money, is_paper_source, _division_registry


class TestPaperMarking:
    def test_every_registry_source_is_classified(self):
        """No division may be unclassifiable -- that is how a new book ships
        unmarked."""
        for _k, _l, source, _p, _a, mode in _division_registry():
            assert is_paper_source(source) == (mode == "paper"), source

    def test_paper_sources_are_marked(self):
        assert is_paper_source("FNO_PAPER") is True
        assert is_paper_source("MOMENTUM_PAPER") is True
        assert is_paper_source("EDGE_PAPER") is True

    def test_live_sources_are_not_marked(self):
        assert is_paper_source("MOMENTUM") is False
        assert is_paper_source("SYSTEM") is False
        assert is_paper_source("EDGE_LIVE") is False

    def test_momentum_paper_is_not_confused_with_momentum(self):
        """Substring matching would classify the live book as paper (or worse,
        the reverse). The lookup is exact."""
        assert is_paper_source("MOMENTUM") is False
        assert is_paper_source("MOMENTUM_PAPER") is True

    def test_unknown_source_defaults_to_LIVE(self):
        """Safe direction: mislabelling real money as paper is cosmetic;
        mislabelling paper as real is how a fabricated number gets acted on.
        An unknown source must never silently claim to be paper."""
        assert is_paper_source("SOMETHING_NEW") is False
        assert is_paper_source("") is False
        assert is_paper_source(None) is False

    def test_case_insensitive(self):
        assert is_paper_source("fno_paper") is True

    def test_formatting_marks_paper_and_leaves_live_alone(self):
        assert fmt_money(-730.08, "FNO_PAPER") == "-Rs 730.08 (paper)"
        assert fmt_money(-8.41, "MOMENTUM") == "-Rs 8.41"
        assert fmt_money(1234.5, "MOMENTUM_PAPER") == "Rs 1,234.50 (paper)"

    def test_the_two_numbers_from_2026_08_03_are_now_distinguishable(self):
        """The concrete regression: same day, same report style, 87x apart."""
        paper = fmt_money(-730.08, "FNO_PAPER")
        live = fmt_money(-8.41, "MOMENTUM")
        assert "(paper)" in paper
        assert "(paper)" not in live

    def test_explicit_is_paper_overrides_the_registry(self):
        assert fmt_money(10.0, "MOMENTUM", is_paper=True).endswith("(paper)")
        assert not fmt_money(10.0, "FNO_PAPER", is_paper=False).endswith("(paper)")


def test_fno_telegram_marks_paper_exits():
    from fno_orchestrator import format_fno_telegram
    msg = format_fno_telegram({
        "scan_id": "abc",
        "entries": [{"source": "FNO_PAPER", "symbol": "NIFTY24650CE",
                     "direction": "LONG", "lots": 2, "fill": 30.55,
                     "delta": 0.49, "iv": 0.06}],
        "exits": [{"source": "FNO_PAPER", "symbol": "NIFTY24650CE",
                   "reason": "underlying_stop", "entry": 32.25, "exit": 27.05,
                   "pnl": -730.08, "r": -0.70}],
    })
    assert "(paper)" in msg
    assert "-Rs 730.08 (paper)" in msg
