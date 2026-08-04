"""[DECAY 2026-08-05] Tests for the per-division health state machine.

The design claim being tested is the ASYMMETRY: demotion is slow (repetition
required) and promotion is fast (one reading). Get that backwards and the
system ratchets itself shut, which is precisely what the regime ratchet did.
"""
import pytest

from strategy_health import (
    Health,
    Status,
    Thresholds,
    describe,
    evaluate,
    explain,
    next_status,
    read_health,
)

T = Thresholds()
MANY = 50           # comfortably above min_trades


# ── one reading ───────────────────────────────────────────────────────────

def test_good_numbers_read_healthy():
    assert read_health(expectancy_r=0.3, profit_factor=1.6,
                       activity_ratio=0.9, n_trades=MANY) is Health.HEALTHY


def test_negative_expectancy_reads_worse_than_healthy():
    assert read_health(expectancy_r=-0.05, profit_factor=1.6,
                       activity_ratio=0.9, n_trades=MANY) is not Health.HEALTHY


def test_the_worst_metric_wins():
    """Fine expectancy plus a dead book is not healthy, and averaging hides it."""
    assert read_health(expectancy_r=0.5, profit_factor=2.0,
                       activity_ratio=0.0, n_trades=MANY) is Health.CRITICAL


def test_a_silent_book_is_critical_even_with_no_pnl_metrics():
    """The loudest failure this system has had was a SILENT strategy, not a
    losing one: penny breakout at 0 accepts from 533k evaluations."""
    assert read_health(activity_ratio=0.0, n_trades=0) is Health.CRITICAL


def test_pnl_metrics_are_ignored_below_min_trades():
    """Three losing trades is not decay."""
    assert read_health(expectancy_r=-2.0, profit_factor=0.1,
                       activity_ratio=0.9, n_trades=3) is Health.HEALTHY


def test_activity_is_still_read_below_min_trades():
    """'Too few trades to judge' is itself the activity finding."""
    assert read_health(expectancy_r=-2.0, activity_ratio=0.01,
                       n_trades=3) is Health.CRITICAL


def test_no_measurable_metrics_is_warning_not_healthy():
    """Unknown must not read as fine, but must not start a demotion clock."""
    assert read_health(n_trades=0) is Health.WARNING


@pytest.mark.parametrize("pf,expected", [
    (1.5, Health.HEALTHY), (1.1, Health.WARNING),
    (0.9, Health.DECAYED), (0.5, Health.CRITICAL),
])
def test_profit_factor_buckets(pf, expected):
    assert read_health(profit_factor=pf, n_trades=MANY) is expected


# ── demotion is slow ──────────────────────────────────────────────────────

def test_one_bad_reading_does_not_demote_an_active_book():
    assert next_status(Status.ACTIVE, [Health.WARNING]) is None


def test_two_bad_readings_still_do_not_demote():
    assert next_status(Status.ACTIVE, [Health.WARNING, Health.DECAYED]) is None


def test_three_consecutive_bad_readings_move_to_monitoring():
    assert next_status(
        Status.ACTIVE, [Health.WARNING] * 3) is Status.MONITORING


def test_a_healthy_reading_resets_the_demotion_clock():
    """Only the CONSECUTIVE tail counts -- three bad readings scattered among
    good ones is noise, not decay."""
    readings = [Health.WARNING, Health.WARNING, Health.HEALTHY, Health.WARNING]
    assert next_status(Status.ACTIVE, readings) is None


def test_monitoring_needs_two_decayed_readings_to_decay():
    assert next_status(Status.MONITORING, [Health.DECAYED]) is None
    assert next_status(
        Status.MONITORING, [Health.DECAYED, Health.DECAYED]) is Status.DECAYED


def test_warnings_alone_do_not_push_monitoring_to_decayed():
    assert next_status(
        Status.MONITORING, [Health.WARNING] * 5) is None


def test_decayed_needs_three_criticals_to_disable():
    assert next_status(Status.DECAYED, [Health.CRITICAL] * 2) is None
    assert next_status(
        Status.DECAYED, [Health.CRITICAL] * 3) is Status.DISABLED


# ── promotion is fast ─────────────────────────────────────────────────────

def test_one_healthy_reading_restores_a_monitored_book():
    """Fast on purpose: a book held down by stale history is a book nobody
    turns back on."""
    assert next_status(
        Status.MONITORING, [Health.CRITICAL, Health.HEALTHY]) is Status.ACTIVE


def test_a_decayed_book_climbs_back_one_rung_at_a_time():
    assert next_status(
        Status.DECAYED, [Health.CRITICAL, Health.HEALTHY]) is Status.MONITORING


def test_recovery_beats_the_disable_clock():
    """A healthy reading in the tail must win over three earlier criticals."""
    readings = [Health.CRITICAL] * 3 + [Health.HEALTHY]
    assert next_status(Status.DECAYED, readings) is Status.MONITORING


# ── disabled is terminal for the machine ──────────────────────────────────

def test_disabled_never_re_enables_itself():
    """Turning a book back on after the machine judged it dead is an operator
    decision, not one code should make."""
    assert next_status(Status.DISABLED, [Health.HEALTHY] * 10) is None


# ── edges ─────────────────────────────────────────────────────────────────

def test_no_readings_means_no_transition():
    for status in Status:
        assert next_status(status, []) is None


def test_a_short_history_cannot_trigger_a_transition_that_needs_more():
    assert next_status(Status.ACTIVE, [Health.CRITICAL, Health.CRITICAL]) is None


# ── the combined call ─────────────────────────────────────────────────────

def test_evaluate_returns_the_reading_and_the_transition():
    reading, transition = evaluate(
        Status.ACTIVE, [Health.WARNING, Health.WARNING],
        # 0.05 sits between the warning floor (0.0) and healthy (0.10);
        # pf 1.05 likewise. Both read WARNING, so the reading is WARNING.
        expectancy_r=0.05, profit_factor=1.05, activity_ratio=0.9,
        n_trades=MANY)
    assert reading is Health.WARNING
    assert transition is Status.MONITORING


def test_evaluate_leaves_a_healthy_book_alone():
    reading, transition = evaluate(
        Status.ACTIVE, [Health.HEALTHY] * 5,
        expectancy_r=0.3, profit_factor=1.8, activity_ratio=0.9, n_trades=MANY)
    assert reading is Health.HEALTHY
    assert transition is None


def test_evaluate_appends_the_new_reading_to_history():
    """Two priors plus this one is three -- enough to demote."""
    _reading, transition = evaluate(
        Status.ACTIVE, [Health.DECAYED, Health.DECAYED],
        activity_ratio=0.0, n_trades=0)
    assert transition is Status.MONITORING


# ── operator-facing text ──────────────────────────────────────────────────

def test_describe_shows_a_pending_transition():
    line = describe("momentum", Status.ACTIVE, Health.WARNING, Status.MONITORING)
    assert "momentum" in line and "MONITORING" in line


def test_describe_without_a_transition_omits_the_arrow():
    assert "->" not in describe("penny", Status.ACTIVE, Health.HEALTHY)


def test_explain_is_explicit_that_disabled_does_not_stop_trading():
    """Assuming protection that is not there is the check_circuit_breakers
    mistake, and it must not be repeated here."""
    text = explain(Status.DISABLED)
    assert "does NOT stop" in text
    assert "sentinel" in text


def test_every_status_has_an_explanation():
    for status in Status:
        assert explain(status)
