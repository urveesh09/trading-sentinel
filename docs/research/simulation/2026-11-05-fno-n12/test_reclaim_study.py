from dataclasses import replace
from decimal import Decimal

import pytest

from test_paired_reclaim import scenario
from test_shared_control import NOW, observation
from exam_scoring import summarize
from fno_costs import calc_fno_costs
from paired_reclaim import BASELINE, CHALLENGER
from reclaim_study import BANKROLL, _decide, run_study
from shared_control import SharedControl, Tick


def test_both_cost_cases_run_identical_tape_and_charge_each_ticket(monkeypatch):
    ticks, scans, quote = scenario(monkeypatch, earned=True)
    study = run_study(iter(ticks), iter(scans), signals={quote.signal_at: quote.signal}, quotes=iter([quote]))
    standard, doubled = study.standard, study.doubled
    assert not standard.pair.gaps and not doubled.pair.gaps
    assert study.decision.verdict == "insufficient"
    assert study.decision.changed_executions == 2  # parent plus reclaim; the parent's add does not count twice
    for result, factor in ((standard, 1), (doubled, 2)):
        baseline_parent, baseline_add = result.pair.exits[BASELINE]
        reclaim, challenger_parent = result.pair.exits[CHALLENGER]
        assert (baseline_parent.qty, baseline_add.qty, reclaim.qty, challenger_parent.qty) == (130, 65, 65, 65)
        assert baseline_parent.stress == 420 * factor
        assert baseline_add.stress == reclaim.stress == challenger_parent.stress == 205 * factor
        assert result.native_entries[0].challenger.directional_net == reclaim.net
        assert result.pair.net_delta == result.reclaim_net + result.native_net_delta
    for arm in (BASELINE, CHALLENGER):
        for first, second in zip(standard.pair.exits[arm], doubled.pair.exits[arm], strict=True):
            assert first.fees == second.fees
            assert first.net - second.net == pytest.approx(first.stress)


def test_shared_cost_reserve_can_disallow_native_second_lot():
    signal = observation("NIFTY", vol_up=True, positive=True)
    fees_only = SharedControl(BANKROLL)
    placed, = fees_only.step(Tick(NOW, 0, entries={"NIFTY": signal})).entries
    ticket = fees_only.positions[placed.position_id]
    assert ticket.lots == 2
    reservation = ticket.entry_premium * ticket.qty + calc_fno_costs(ticket.entry_premium, 0, ticket.qty)
    tick = Tick(NOW, BANKROLL - reservation - 100, entries={"NIFTY": signal})
    plain, stressed = SharedControl(BANKROLL), SharedControl(BANKROLL, stress_multiple=1)
    first, = plain.step(tick).entries
    second, = stressed.step(tick).entries
    assert plain.positions[first.position_id].lots == 2
    assert stressed.positions[second.position_id].lots == 1


def test_missing_quote_withholds_whole_study(monkeypatch):
    ticks, scans, quote = scenario(monkeypatch, earned=False)
    study = run_study(ticks, scans, signals={quote.signal_at: quote.signal}, quotes=())
    assert study.decision.verdict == "incomplete" and not study.decision.gates
    assert study.standard.pair.net_delta is study.doubled.pair.net_delta is None


def gate_fixture(result, values):
    rows = [{"status": "CLOSED", "exit_time": f"2099-01-{day:02}T11:00:00", "net_pnl": net}
            for day, net in enumerate(values, 1)]
    summary = summarize(rows, Decimal(BANKROLL))
    flat = summarize([], Decimal(BANKROLL))
    source, = result.reclaim_exits
    exits = tuple(replace(source, position_id=i, at=source.at.replace(day=i)) for i in range(1, len(values) + 1))
    pair = replace(result.pair, summaries={BASELINE: flat, CHALLENGER: summary}, net_delta=summary["net"])
    return replace(result, pair=pair, native_trades=(), reclaim_exits=exits)


def test_gates_require_profit_without_best_day_and_at_doubled_cost(monkeypatch):
    ticks, scans, quote = scenario(monkeypatch, earned=False)
    actual = run_study(ticks, scans, signals={quote.signal_at: quote.signal}, quotes=(quote,)).standard
    concentrated = gate_fixture(actual, [2000] + [-1] * 14)
    doubled = gate_fixture(actual, [0] * 15)
    decision = _decide(concentrated, doubled)
    assert decision.verdict == "fail" and decision.changed_executions == 15
    assert decision.best_incremental_day == "2099-01-01" and decision.ex_best_day_delta == -14
    assert decision.gates["positive_net"]
    assert not decision.gates["positive_ex_best_day"] and not decision.gates["positive_doubled_cost_net"]


def test_downside_allowances_are_inclusive_and_independent(monkeypatch):
    ticks, scans, quote = scenario(monkeypatch, earned=False)
    actual = run_study(ticks, scans, signals={quote.signal_at: quote.signal}, quotes=(quote,)).standard
    boundary = gate_fixture(actual, [-1000, -1000, -500] + [1000] * 12)
    assert _decide(boundary, boundary).verdict == "pass"
    over_worst = _decide(gate_fixture(actual, [-1001, -999, -500] + [1000] * 12), boundary)
    assert not over_worst.gates["worst_day"] and over_worst.gates["closed_drawdown"]
    over_drawdown = _decide(gate_fixture(actual, [-1000, -1000, -501] + [1000] * 12), boundary)
    assert over_drawdown.gates["worst_day"] and not over_drawdown.gates["closed_drawdown"]
