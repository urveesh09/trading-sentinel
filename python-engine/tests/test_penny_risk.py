"""
[PENNY-RISK 2026-06-21] Tests for PennyRiskEngine.

Spec §7:
  - per-trade sizing (5% / 2.5% / 0% by regime)
  - per-stock cap (Rs 500)
  - position caps (5 total, 2 CNC, 3 MIS)
  - NSE circuit-band filter (skip if at band + >3% from day high)
  - 20% daily loss kill-switch (per spec §7.3)
  - mandatory SL-M order validation (spec §7.2)
  - PENNY_DISABLE_TICKERS manual kill-switch
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock


# ---- sizing ------------------------------------------------------------

def test_position_size_pr1_uses_full_pct():
    """PR1: Rs 2000 bankroll * 5% = Rs 100 risk / Rs 2 risk-per-share = 50 shares."""
    from penny_risk import PennyRiskEngine
    from penny_models import PennyRegime
    eng = PennyRiskEngine(bankroll=2000.0)
    assert eng.position_size(
        entry=10.0, stop_loss=9.8, regime=PennyRegime.PR1_CALM
    ) == 50


def test_position_size_pr2_uses_half_pct():
    """PR2 uses half the PR1 risk budget -> smaller position when cap doesn't bind.

    At entry=10 the per-stock cap (500/10=50) binds both PR1 and PR2 at 50.
    To prove the regime discount actually applies, use a wider stop so
    risk_per_share is large enough that cap doesn't bind.
    """
    from penny_risk import PennyRiskEngine
    from penny_models import PennyRegime
    eng = PennyRiskEngine(bankroll=2000.0)
    # entry=10, stop=5 -> risk_per_share=5
    # PR1: 2000 * 0.05 = 100 / 5 = 20, cap=50 -> 20
    # PR2: 2000 * 0.025 = 50 / 5 = 10, cap=50 -> 10
    pr1 = eng.position_size(entry=10.0, stop_loss=5.0, regime=PennyRegime.PR1_CALM)
    pr2 = eng.position_size(entry=10.0, stop_loss=5.0, regime=PennyRegime.PR2_ELEVATED)
    assert pr1 == 20
    assert pr2 == 10
    assert pr2 < pr1


def test_position_size_pr3_trades_small_not_zero():
    """PR3 sizes SMALL (1% risk), it does not shut off. A 0-size regime is
    unfalsifiable -- it can never produce an accept, so nothing can ever
    show whether the gate was right (see the PENNY_RISK_PCT_PR3 comment in
    config.py). This test used to pin the old shutdown behaviour (== 0)
    and had been failing since the config change."""
    from penny_risk import PennyRiskEngine
    from penny_models import PennyRegime
    eng = PennyRiskEngine(bankroll=2000.0)
    # entry=10, stop=5 -> risk_per_share=5; PR3: 2000 * 0.01 = 20 / 5 = 4
    pr3 = eng.position_size(entry=10.0, stop_loss=5.0, regime=PennyRegime.PR3_HOT)
    pr2 = eng.position_size(entry=10.0, stop_loss=5.0, regime=PennyRegime.PR2_ELEVATED)
    assert pr3 == 4
    assert 0 < pr3 < pr2


def test_position_size_respects_per_stock_cap():
    """Per-stock cap (Rs 500) clamps shares even if risk math allows more."""
    from penny_risk import PennyRiskEngine
    from penny_models import PennyRegime
    eng = PennyRiskEngine(bankroll=2000.0)
    # Without cap: Rs 100 / Rs 0.20 = 500 shares -> cap at 500/10 = 50
    shares = eng.position_size(entry=10.0, stop_loss=9.8, regime=PennyRegime.PR1_CALM)
    assert shares == 50


def test_position_size_respects_cap_at_higher_entry():
    from penny_risk import PennyRiskEngine
    from penny_models import PennyRegime
    eng = PennyRiskEngine(bankroll=2000.0)
    # Rs 100 risk / Rs 1.00 risk = 100 shares -> cap at 500/30 = 16
    shares = eng.position_size(entry=30.0, stop_loss=29.0, regime=PennyRegime.PR1_CALM)
    assert shares == 16


def test_position_size_returns_zero_if_stop_above_entry():
    from penny_risk import PennyRiskEngine
    from penny_models import PennyRegime
    eng = PennyRiskEngine(bankroll=2000.0)
    assert eng.position_size(entry=10.0, stop_loss=10.5, regime=PennyRegime.PR1_CALM) == 0


def test_position_size_handles_zero_bankroll():
    from penny_risk import PennyRiskEngine
    from penny_models import PennyRegime
    eng = PennyRiskEngine(bankroll=0.0)
    assert eng.position_size(entry=10.0, stop_loss=9.8, regime=PennyRegime.PR1_CALM) == 0


# ---- kill-switch -------------------------------------------------------

def test_kill_switch_triggers_at_20pct_daily_loss():
    from penny_risk import PennyRiskEngine
    eng = PennyRiskEngine(bankroll=2000.0)
    # 20% of 2000 = 400
    eng.record_realized_pnl(-100.0, datetime.now(timezone.utc))
    eng.record_realized_pnl(-100.0, datetime.now(timezone.utc))
    eng.record_realized_pnl(-150.0, datetime.now(timezone.utc))
    assert eng.daily_pnl == -350.0
    assert eng.kill_switch_active() is False
    eng.record_realized_pnl(-50.0, datetime.now(timezone.utc))
    assert eng.kill_switch_active() is True


def test_kill_switch_resets_on_new_day():
    from penny_risk import PennyRiskEngine
    eng = PennyRiskEngine(bankroll=2000.0)
    yesterday = datetime(2026, 6, 20, 14, 0, tzinfo=timezone.utc)
    today = datetime(2026, 6, 21, 9, 30, tzinfo=timezone.utc)
    eng.record_realized_pnl(-500.0, yesterday)
    # At yesterday's time, kill switch was active
    assert eng.kill_switch_active(as_of=yesterday) is True
    # By today, the daily P&L counter has reset
    assert eng.kill_switch_active(as_of=today) is False
    # And the no-arg call (uses now) also shows it as not active
    assert eng.kill_switch_active() is False


def test_record_realized_pnl_handles_winning_day():
    from penny_risk import PennyRiskEngine
    eng = PennyRiskEngine(bankroll=2000.0)
    eng.record_realized_pnl(100.0, datetime.now(timezone.utc))
    assert eng.daily_pnl == 100.0
    assert eng.kill_switch_active() is False


# ---- circuit filter ----------------------------------------------------

def test_circuit_filter_skips_when_at_5pct_band():
    """5% band stock near lower band + >3% below day high -> skip."""
    from penny_risk import PennyRiskEngine
    eng = PennyRiskEngine(bankroll=2000.0)
    # 5% band from prev_close=10.0 -> lower=9.5, upper=10.5
    # Scaled skip = 0.5% of band.
    # last=9.51 (within 0.5% of lower band 9.5: dist=0.001 < 0.005, first check passes)
    # day_high=10.50 (last is (10.50-9.51)/10.50 = 9.4% below high, > 3% -> skip)
    skip, reason = eng.circuit_blocked(
        last_price=9.51, day_high=10.50, prev_close=10.0, band_pct=0.05
    )
    assert skip is True
    assert "circuit" in reason.lower()


def test_circuit_filter_skips_when_at_10pct_band():
    """10% band stock near lower band + >3% below day high -> skip."""
    from penny_risk import PennyRiskEngine
    eng = PennyRiskEngine(bankroll=2000.0)
    # 10% band from prev_close=10.0 -> lower=9.0, upper=11.0
    # Scaled skip = 1.0% of band.
    # last=9.05 (within 0.5% of lower 9.0: dist=0.005, scale-skip=0.01,
    #   0.005 < 0.01, first check passes)
    # day_high=10.50 (last is (10.50-9.05)/10.50 = 13.8% below high, > 3% -> skip)
    skip, reason = eng.circuit_blocked(
        last_price=9.05, day_high=10.50, prev_close=10.0, band_pct=0.10
    )
    assert skip is True


def test_circuit_filter_allows_when_far_from_band():
    from penny_risk import PennyRiskEngine
    eng = PennyRiskEngine(bankroll=2000.0)
    skip, reason = eng.circuit_blocked(
        last_price=10.10, day_high=10.20, prev_close=10.0, band_pct=0.05
    )
    assert skip is False
    assert reason == ""


def test_circuit_filter_allows_when_close_to_day_high():
    """Within 3% of day high -> allowed even if near band (momentum)."""
    from penny_risk import PennyRiskEngine
    eng = PennyRiskEngine(bankroll=2000.0)
    # day_high=10.49, last=10.48 -> within 0.1% of high -> allow
    skip, reason = eng.circuit_blocked(
        last_price=10.48, day_high=10.49, prev_close=10.0, band_pct=0.05
    )
    assert skip is False


# ---- caps --------------------------------------------------------------

def test_cap_check_total_blocks_when_at_max():
    from penny_risk import PennyRiskEngine
    from penny_models import PennyLeg
    eng = PennyRiskEngine(bankroll=2000.0)
    open_positions = [{"leg": PennyLeg.CNC}, {"leg": PennyLeg.CNC},
                      {"leg": PennyLeg.MIS}, {"leg": PennyLeg.MIS}, {"leg": PennyLeg.MIS}]
    can_open, reason = eng.can_open_new(open_positions=open_positions, leg=PennyLeg.CNC)
    assert can_open is False
    assert "max" in reason.lower()


def test_cap_check_cnc_blocks_at_2():
    from penny_risk import PennyRiskEngine
    from penny_models import PennyLeg
    eng = PennyRiskEngine(bankroll=2000.0)
    open_positions = [{"leg": PennyLeg.CNC}, {"leg": PennyLeg.CNC}]
    can_open, _ = eng.can_open_new(open_positions=open_positions, leg=PennyLeg.CNC)
    assert can_open is False


def test_cap_check_mis_blocks_at_3():
    from penny_risk import PennyRiskEngine
    from penny_models import PennyLeg
    eng = PennyRiskEngine(bankroll=2000.0)
    open_positions = [{"leg": PennyLeg.MIS}, {"leg": PennyLeg.MIS}, {"leg": PennyLeg.MIS}]
    can_open, _ = eng.can_open_new(open_positions=open_positions, leg=PennyLeg.MIS)
    assert can_open is False


def test_cap_check_allows_within_caps():
    from penny_risk import PennyRiskEngine
    from penny_models import PennyLeg
    eng = PennyRiskEngine(bankroll=2000.0)
    open_positions = [{"leg": PennyLeg.CNC}, {"leg": PennyLeg.MIS}]
    can_open, _ = eng.can_open_new(open_positions=open_positions, leg=PennyLeg.MIS)
    assert can_open is True


# ---- manual disable ----------------------------------------------------

def test_disable_tickers_blocks_specific_symbol():
    from penny_risk import PennyRiskEngine
    eng = PennyRiskEngine(bankroll=2000.0)
    eng.disable_tickers = "XYZ,ABC,FOO"
    assert eng.is_disabled("XYZ") is True
    assert eng.is_disabled("abc") is True   # case-insensitive
    assert eng.is_disabled("OTHER") is False


def test_disable_tickers_empty_allows_all():
    from penny_risk import PennyRiskEngine
    eng = PennyRiskEngine(bankroll=2000.0)
    eng.disable_tickers = ""
    assert eng.is_disabled("XYZ") is False


# ---- SL-M validation ---------------------------------------------------

def test_sl_m_required_blocks_market_only_order():
    """Spec §7.2: every penny entry MUST have an SL-M. Pure market = blocked."""
    from penny_risk import PennyRiskEngine
    eng = PennyRiskEngine(bankroll=2000.0)
    can, reason = eng.validate_order(
        entry_order_type="MARKET", sl_order_type="NONE"
    )
    assert can is False
    assert "sl-m" in reason.lower()


def test_sl_m_required_allows_limit_with_sl_m():
    from penny_risk import PennyRiskEngine
    eng = PennyRiskEngine(bankroll=2000.0)
    can, reason = eng.validate_order(
        entry_order_type="LIMIT", sl_order_type="SL-M"
    )
    assert can is True
    assert reason == ""


# ---- 2026-06-24 bankroll fix: ledger_writer integration ----------------

@pytest.mark.asyncio
async def test_record_close_invokes_ledger_writer_with_net_pnl(db_path):
    """[BK-WIRE 2026-06-24] When a ledger_writer is provided, record_close
    must invoke it with (ticker, net_pnl). The net is post-cost, so it can
    be negative even on a gross win."""
    from penny_risk import PennyRiskEngine
    from datetime import datetime, timezone

    captured = []

    async def fake_writer(ticker: str, pnl: float) -> None:
        captured.append((ticker, pnl))

    eng = PennyRiskEngine(bankroll=2000.0, ledger_writer=fake_writer)
    # Win: 100 shares, entry 10, exit 11, intraday -> gross 100, costs ~5.
    eng.record_close(
        entry_price=10.0, exit_price=11.0, shares=100,
        is_intraday=True, when=datetime.now(timezone.utc), ticker="PENNY_A",
    )
    # record_close schedules the writer via loop.create_task. The scheduling
    # itself is fast (no I/O). The actual write happens on the next loop tick.
    # Yield a few times to let the task drain -- but the test asserts on
    # captured args, which are appended before any await, so the task may
    # already have appended them by the time we yield.
    import asyncio
    for _ in range(3):
        await asyncio.sleep(0)
    assert len(captured) == 1, f"expected 1 invocation, got {len(captured)}"
    ticker_arg, pnl_arg = captured[0]
    assert ticker_arg == "PENNY_A"
    assert pnl_arg > 0  # net positive (gross 100 - costs ~5)


@pytest.mark.asyncio
async def test_record_close_invokes_writer_on_loss(db_path):
    """Loss: net pnl must be negative -- the writer gets the loss."""
    from penny_risk import PennyRiskEngine
    from datetime import datetime, timezone
    import asyncio

    captured = []

    async def fake_writer(ticker: str, pnl: float) -> None:
        captured.append((ticker, pnl))

    eng = PennyRiskEngine(bankroll=2000.0, ledger_writer=fake_writer)
    # Loss: 100 shares, entry 10, exit 9.5 -> gross -50, costs ~5.
    eng.record_close(
        entry_price=10.0, exit_price=9.5, shares=100,
        is_intraday=True, when=datetime.now(timezone.utc), ticker="PENNY_LOSS",
    )
    for _ in range(3):
        await asyncio.sleep(0)
    assert len(captured) == 1
    assert captured[0][0] == "PENNY_LOSS"
    assert captured[0][1] < 0


@pytest.mark.asyncio
async def test_record_close_without_ledger_writer_still_updates_daily_pnl(db_path):
    """When NO ledger_writer is passed, the in-memory daily_pnl counter
    must still update -- back-compat with existing callers. No write is
    attempted, no exception is raised."""
    from penny_risk import PennyRiskEngine
    from datetime import datetime, timezone

    eng = PennyRiskEngine(bankroll=2000.0)  # no ledger_writer
    eng.record_close(
        entry_price=10.0, exit_price=9.5, shares=100,
        is_intraday=True, when=datetime.now(timezone.utc), ticker="PENNY_B",
    )
    # daily_pnl should have absorbed the net loss.
    assert eng.daily_pnl < 0


@pytest.mark.asyncio
async def test_record_close_ledger_write_failure_does_not_propagate(db_path):
    """If the writer raises, record_close must log and continue --
    the daily_pnl counter is still authoritative for risk gating.
    record_close itself is sync, so a failing async writer (scheduled via
    create_task) cannot bubble up to it. We test by inspecting that
    record_close does not raise AND that daily_pnl updated."""
    from penny_risk import PennyRiskEngine
    from datetime import datetime, timezone

    async def broken_writer(ticker: str, pnl: float) -> None:
        raise RuntimeError("simulated DB outage")

    eng = PennyRiskEngine(bankroll=2000.0, ledger_writer=broken_writer)
    # Must not raise -- the task is scheduled, not awaited inline.
    eng.record_close(
        entry_price=10.0, exit_price=10.5, shares=100,
        is_intraday=True, when=datetime.now(timezone.utc), ticker="PENNY_C",
    )
    # In-memory counter still updated.
    assert eng.daily_pnl > 0


def test_penny_risk_does_not_import_performance():
    """Isolation rule (spec §12 / test_penny_isolation): penny_risk.py MUST
    NOT import from performance. The fix uses dependency injection, not an
    import. We check the AST for actual import statements (not just the
    words appearing in docstrings or comments)."""
    import ast
    import penny_risk

    with open(penny_risk.__file__) as f:
        tree = ast.parse(f.read())

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bad = alias.name.startswith("performance")
                assert not bad, (
                    f"penny_risk.py has 'import {alias.name}' at "
                    f"line {node.lineno} -- isolation violated"
                )
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("performance"):
                raise AssertionError(
                    f"penny_risk.py has 'from {node.module} import ...' at "
                    f"line {node.lineno} -- isolation violated"
                )
