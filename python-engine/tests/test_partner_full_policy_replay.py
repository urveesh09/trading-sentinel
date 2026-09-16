from dataclasses import replace
from datetime import timedelta

import pytest

import partner_full_policy_replay as replay
from intraday_spread_archive_adapter import ArchiveObservationBuild
from intraday_spread_chronological import ChronologicalPolicy, SpreadObservation
from intraday_spread_replay import LegQuote, ReplayInputError
from partner_qualification import evaluate_deployed_full_policy, load_candidate_evidence
from tests.test_partner_qualification import candidate_bundle, provenance
from tests.test_fno_signal_scan import _frame, LONG_ROWS, NOW, EXPIRY


def public_scope(master_sha256, token=123):
    return {"format": "partner_public_future_scope_v1", "provider": "KITE",
            "channel": "HISTORICAL", "interval": "5minute", "underlying": "NIFTY",
            "exchange": "NFO", "contract_master_raw_sha256": master_sha256,
            "selection_as_of": NOW.date().isoformat(),
            "selected_future": {"token": token, "tradingsymbol": "NIFTY26SEPFUT",
                                "expiry": "2026-09-24", "instrument_type": "FUT", "lot_size": 75, "tick_size": .05},
            "eligible_future_expiries": ["2026-09-24", "2026-10-29"],
            "next_future": {"token": 124, "tradingsymbol": "NIFTY26OCTFUT",
                            "expiry": "2026-10-29", "instrument_type": "FUT", "lot_size": 75, "tick_size": .05},
            "nearest_strictly_future_option_expiry": EXPIRY.isoformat()}


@pytest.fixture
def case(monkeypatch, tmp_path):
    value = candidate_bundle()
    value['received_at'] = value['snapshot']['taken_at'] = NOW.isoformat()
    value['snapshot']['expiry'] = EXPIRY.isoformat()
    for item in value['contracts']:
        item['expiry'] = EXPIRY.isoformat()
    for item in value['snapshot']['quotes']:
        item['last_trade_time'] = NOW.isoformat()
    book, snapshot, profile = load_candidate_evidence(value, underlying='NIFTY', decision_at=NOW)
    inputs = dict(underlying='NIFTY', bars=_frame(LONG_ROWS), regime='REGIME_1_NORMAL',
                  decision_at=NOW, bar_provenance=provenance(NOW), book=book, snapshot=snapshot,
                  profile=profile, contract_master_sha256='a' * 64)
    decision = evaluate_deployed_full_policy(**inputs)
    assert decision.state == 'ACCEPTED'
    def row(at):
        quotes = tuple(LegQuote(leg.tradingsymbol, leg.side, 'NFO', leg.lot_size,
            leg.bid, leg.ask, leg.bid_quantity, leg.ask_quantity, at, at,
            token=leg.instrument_token, option_type=leg.option_type, strike=leg.strike,
            expiry=leg.expiry, quantity=leg.lot_size, master_sha256='a' * 64,
            oi=leg.oi, volume=leg.volume)
            for leg in decision.candidate.legs)
        return SpreadObservation(at, at, 0, quotes)
    rows = [row(NOW), row(NOW + timedelta(minutes=1))]
    monkeypatch.setattr(replay, 'build_spread_observations', lambda **_: ArchiveObservationBuild(tuple(rows), (), 0, None))
    public = [dict(received_at=item.received_at, observed_at=item.received_at,
                   price=decision.signal.close if i == 0 else decision.candidate.invalidation_level)
              for i, item in enumerate(rows)]
    args = dict(evaluation_inputs=inputs, events=[], archive_root=tmp_path, master_sha256='a' * 64,
                execution_policy=ChronologicalPolicy('caller', 99, 1, 1), public_observations=public)
    return args, rows


def test_real_policy_connector_exits_on_invalidation(case):
    args, _ = case
    result = replay.replay_full_policy(**args)
    assert result['state'] == 'CLOSED'
    assert result['replay']['exit_trigger'] == 'INVALIDATION'
    assert not result['can_qualify'] and not result['can_deliver']
    assert result['public_evidence_contract'] == 'CALLER_SUPPLIED_DIAGNOSTIC'


def test_missing_public_evidence_cannot_claim_complete_replay(case):
    args, _ = case
    args['public_observations'] = []
    assert replay.replay_full_policy(**args)['reason'] == 'public_lifecycle_coverage_missing'


def test_does_not_silently_discard_between_book_invalidation(case):
    args, _ = case
    args['public_observations'][1]['received_at'] -= timedelta(seconds=1)
    args['public_observations'][1]['observed_at'] -= timedelta(seconds=1)
    result = replay.replay_full_policy(**args)
    assert result['state'] == 'CLOSED'
    assert result['replay']['exit_trigger'] == 'INVALIDATION'


def test_thesis_crossed_at_decision_remains_a_reviewable_costed_no_fill(case):
    from intraday_spread_holdout import heldout_case_from_full_policy_report
    args, _ = case
    decision = evaluate_deployed_full_policy(**args['evaluation_inputs'])
    args['public_observations'][0]['price'] = decision.candidate.invalidation_level
    result = replay.replay_full_policy(**args)
    assert result['state'] == 'NO_FILL'
    assert result['reason'] == 'public_thesis_already_crossed_at_decision'
    assert result['replay']['state'] == 'NO_FILL'
    assert result['cost_sensitivity']['scenarios'][0]['state'] == 'NO_FILL'
    heldout = heldout_case_from_full_policy_report(result, signal_artifact_sha256='d' * 64)
    assert heldout.replay.state == 'NO_FILL'


def test_decision_book_must_match_candidate(case):
    args, rows = case
    rows[0] = replace(rows[0], quotes=(replace(rows[0].quotes[0], ask=999), rows[0].quotes[1]))
    with pytest.raises(ReplayInputError, match='differs'):
        replay.replay_full_policy(**args)


def test_missing_exact_decision_book_is_evidence_gap(case):
    args, rows = case
    rows.pop(0)
    assert replay.replay_full_policy(**args)['reason'] == 'decision_book_missing'


def test_prior_book_can_support_decision_without_backdating_quote(case):
    args, rows = case
    earlier = NOW - timedelta(seconds=2)
    rows[0] = replace(rows[0], observed_at=earlier, received_at=earlier,
        quotes=tuple(replace(q, observed_at=earlier, received_at=earlier) for q in rows[0].quotes))
    result = replay.replay_full_policy(**args)
    assert result['state'] == 'CLOSED'
    assert result['decision_book_received_at'] == earlier.isoformat()
    assert result['replay']['active_entry_at'] == NOW.isoformat()
    assert all(q.received_at == earlier for q in rows[0].quotes)


def test_prior_stale_book_cannot_be_freshened_by_decision_clock(case):
    args, rows = case
    earlier = NOW - timedelta(minutes=2)
    rows[0] = replace(rows[0], observed_at=earlier, received_at=earlier,
        quotes=tuple(replace(q, observed_at=earlier, received_at=earlier) for q in rows[0].quotes))
    assert replay.replay_full_policy(**args)['reason'] == 'decision_book_stale'


def test_intervening_partial_book_blocks_reuse_of_older_complete_pair(case, monkeypatch):
    args, rows = case
    earlier = NOW - timedelta(seconds=2)
    rows[0] = replace(rows[0], observed_at=earlier, received_at=earlier,
        quotes=tuple(replace(q, observed_at=earlier, received_at=earlier) for q in rows[0].quotes))
    monkeypatch.setattr(replay, 'build_spread_observations', lambda **_: ArchiveObservationBuild(tuple(rows),
        ({'received_at': (NOW - timedelta(seconds=1)).isoformat(), 'missing': ['short']},), 0, None))
    assert replay.replay_full_policy(**args)['reason'] == 'partial_book_before_decision'


def test_decision_book_conflict_is_explicit(case, monkeypatch):
    args, rows = case
    monkeypatch.setattr(replay, 'build_spread_observations', lambda **_: ArchiveObservationBuild(tuple(rows),
        (), 0, None, ({'received_at': NOW.isoformat(), 'conflicting': ['long']},)))
    result = replay.replay_full_policy(**args)
    assert result['reason'] == 'decision_book_conflict'
    assert result['conflicting_batches'][0]['conflicting'] == ['long']


# [WORKFLOW-C.A1 2026-09-15] Asymmetric-fills
# diagnostic surfaces through the full-policy report.
# Mirror the existing ``test_decision_book_conflict_is_explicit``
# and ``test_intervening_partial_book_blocks_reuse_of_older_complete_pair``
# patterns: monkeypatch ``build_spread_observations`` to
# return an ``ArchiveObservationBuild`` with an
# ``asymmetric_batches`` entry between the decision book's
# receipt time and the decision clock -- the operator
# cannot claim a fully executable two-leg book at decision
# time. The report must be INSUFFICIENT_EVIDENCE with
# reason ``asymmetric_execution_quality_before_decision``.


def test_asymmetric_execution_quality_before_decision_is_insufficient_evidence(case, monkeypatch):
    args, rows = case
    # [WORKFLOW-C.A1 2026-09-15] Mirror the partial-book
    # discipline at line 127. The check at line 138 is
    # ``book_at_decision.received_at < received_at <= now``.
    # To trigger it: move the decision book EARLIER than
    # NOW, then place the asymmetric batch BETWEEN the
    # decision book's receipt time and the decision clock.
    # The decision clock (``now``) stays at NOW.
    earlier = NOW - timedelta(seconds=2)
    rows[0] = replace(rows[0], observed_at=earlier, received_at=earlier,
        quotes=tuple(replace(q, observed_at=earlier, received_at=earlier) for q in rows[0].quotes))
    asymmetric_received = (NOW - timedelta(seconds=1)).isoformat()
    monkeypatch.setattr(replay, 'build_spread_observations', lambda **_: ArchiveObservationBuild(tuple(rows),
        (), 0, None, (), ({'received_at': asymmetric_received, 'state': 'ASYMMETRIC_EXECUTION_QUALITY',
                            'executable': ['long'], 'insufficient': ['short'],
                            'depth_by_leg': {'long': {'bid_depth': 75, 'ask_depth': 75, 'lot_size': 75},
                                             'short': {'bid_depth': 1, 'ask_depth': 1, 'lot_size': 75}}},)))
    result = replay.replay_full_policy(**args)
    assert result['reason'] == 'asymmetric_execution_quality_before_decision'
    assert result['state'] == 'INSUFFICIENT_EVIDENCE'
    # The diagnostic is surfaced in the report for the
    # qualification review to read.
    assert result['asymmetric_batches'][0]['state'] == 'ASYMMETRIC_EXECUTION_QUALITY'
    assert result['asymmetric_batches'][0]['insufficient'] == ['short']


def test_asymmetric_after_decision_does_not_block_replay(case, monkeypatch):
    """[WORKFLOW-C.A1 2026-09-15] An asymmetric batch that
    arrives AFTER the decision clock does not invalidate
    the decision -- the operator had a fully executable
    two-leg book at decision time. The diagnostic still
    surfaces in the report (so the operator can see
    post-decision liquidity shifts), but the report's state
    is not INSUFFICIENT_EVIDENCE.
    """
    args, rows = case
    # Asymmetric batch 1 minute AFTER the decision clock.
    asymmetric_received = (NOW + timedelta(minutes=1)).isoformat()
    monkeypatch.setattr(replay, 'build_spread_observations', lambda **_: ArchiveObservationBuild(tuple(rows),
        (), 0, None, (), ({'received_at': asymmetric_received, 'state': 'ASYMMETRIC_EXECUTION_QUALITY',
                            'executable': ['long'], 'insufficient': ['short'],
                            'depth_by_leg': {'long': {'bid_depth': 75, 'ask_depth': 75, 'lot_size': 75},
                                             'short': {'bid_depth': 1, 'ask_depth': 1, 'lot_size': 75}}},)))
    result = replay.replay_full_policy(**args)
    # The decision was made against a fully executable
    # book; the asymmetric batch is post-decision.
    assert result['reason'] != 'asymmetric_execution_quality_before_decision'
    # The diagnostic still surfaces for transparency.
    assert result['asymmetric_batches'][0]['state'] == 'ASYMMETRIC_EXECUTION_QUALITY'


# ---------------------------------------------------------------------------
# [WORKFLOW-C.C1 2026-09-15] Structured asymmetric-fill
# diagnostic (Option 3). Tests pin the shape and content of
# the new ``asymmetric_diagnostic`` block on the report.


def test_asymmetric_diagnostic_present_on_clean_run(case, monkeypatch):
    """[WORKFLOW-C.C1] Even on a clean run (no asymmetric
    batches), the report carries an ``asymmetric_diagnostic``
    block with default empty values. Operators can rely on
    the field always being present -- they don't have to
    check ``'asymmetric_diagnostic' in report`` before
    reading its keys.
    """
    args, rows = case
    monkeypatch.setattr(replay, 'build_spread_observations',
                        lambda **_: ArchiveObservationBuild(tuple(rows), (), 0, None))
    result = replay.replay_full_policy(**args)
    assert "asymmetric_diagnostic" in result
    diag = result["asymmetric_diagnostic"]
    # Default state: no asymmetric batches.
    assert diag["pre_decision_asymmetric_observed"] is False
    assert diag["asymmetric_batch_count"] == 0
    assert diag["pre_decision_batch_count"] == 0
    assert diag["executable_legs"] == []
    assert diag["insufficient_legs"] == []
    assert diag["earliest_received_at"] is None
    assert diag["latest_received_at"] is None


def test_asymmetric_diagnostic_attribution_pre_decision(case, monkeypatch):
    """[WORKFLOW-C.C1] When a pre-decision asymmetric batch
    exists, the diagnostic names the executable and
    insufficient legs, surfaces the timestamp range, and
    sets ``pre_decision_asymmetric_observed`` to True.
    Mirrors the existing A1 ``asymmetric_batches`` field
    but in a single structured block.
    """
    args, rows = case
    # The case fixture has ``book_at_decision.received_at
    # == NOW`` (the first observation). The pre-decision
    # window is strictly AFTER book_at_decision and at-or-
    # before now. Drop the post-decision row (NOW + 1min)
    # so prior_books doesn't include it, and APPEND an
    # earlier observation AFTER rows[0] so book_at_decision
    # (= prior_books[-1]) is that earlier timestamp. Now
    # book_at_decision.received_at = NOW - 60s, the
    # asymmetric batch at NOW - 30s is in the pre-decision
    # window.
    earlier = NOW - timedelta(seconds=60)
    new_last = rows[0].__class__(
        observed_at=earlier, received_at=earlier,
        signal_score=rows[0].signal_score, quotes=rows[0].quotes,
    )
    new_rows = (rows[0], new_last)
    # Asymmetric batch 30s before the decision clock -- but
    # after book_at_decision (which is now at NOW - 60s).
    asymmetric_received = (NOW - timedelta(seconds=30)).isoformat()
    monkeypatch.setattr(replay, 'build_spread_observations', lambda **_: ArchiveObservationBuild(
        new_rows, (), 0, None, (), ({'received_at': asymmetric_received,
                            'state': 'ASYMMETRIC_EXECUTION_QUALITY',
                            'executable': ['long'], 'insufficient': ['short'],
                            'depth_by_leg': {'long': {'bid_depth': 75, 'ask_depth': 75, 'lot_size': 75},
                                             'short': {'bid_depth': 1, 'ask_depth': 1, 'lot_size': 75}}},)))
    result = replay.replay_full_policy(**args)
    diag = result["asymmetric_diagnostic"]
    # The diagnostic correctly attributes the asymmetry to
    # the LONG leg (executable) and SHORT leg (insufficient).
    assert diag["pre_decision_asymmetric_observed"] is True
    assert diag["executable_legs"] == ["long"]
    assert diag["insufficient_legs"] == ["short"]
    # The pre-decision batch count is 1; the asymmetric
    # batch count (all batches, pre + post) is also 1.
    assert diag["pre_decision_batch_count"] == 1
    assert diag["asymmetric_batch_count"] == 1
    # The timestamp range is the asymmetric batch's
    # received_at (only one batch in this test).
    assert diag["earliest_received_at"] == asymmetric_received
    assert diag["latest_received_at"] == asymmetric_received
    # The replay is still fail-closed (Option 1 behavior
    # preserved): the state is INSUFFICIENT_EVIDENCE.
    assert result["reason"] == "asymmetric_execution_quality_before_decision"


def test_asymmetric_diagnostic_post_decision_does_not_trigger_observed(case, monkeypatch):
    """[WORKFLOW-C.C1] An asymmetric batch that arrives
    AFTER the decision clock does NOT count as a pre-decision
    observation. The diagnostic block correctly reports
    ``pre_decision_asymmetric_observed`` = False, even when
    there's a post-decision asymmetric batch in the report.
    The post-decision batch is still surfaced in the raw
    ``asymmetric_batches`` list for transparency.
    """
    args, rows = case
    asymmetric_received = (NOW + timedelta(minutes=1)).isoformat()
    monkeypatch.setattr(replay, 'build_spread_observations', lambda **_: ArchiveObservationBuild(tuple(rows),
        (), 0, None, (), ({'received_at': asymmetric_received, 'state': 'ASYMMETRIC_EXECUTION_QUALITY',
                            'executable': ['long'], 'insufficient': ['short'],
                            'depth_by_leg': {'long': {'bid_depth': 75, 'ask_depth': 75, 'lot_size': 75},
                                             'short': {'bid_depth': 1, 'ask_depth': 1, 'lot_size': 75}}},)))
    result = replay.replay_full_policy(**args)
    diag = result["asymmetric_diagnostic"]
    # Post-decision batches don't count as pre-decision
    # observations -- the decision was made against a
    # fully executable book.
    assert diag["pre_decision_asymmetric_observed"] is False
    assert diag["pre_decision_batch_count"] == 0
    # But the raw batch IS in the asymmetric_batches list --
    # post-decision liquidity shifts are still surfaced.
    assert diag["asymmetric_batch_count"] == 1


def test_asymmetric_diagnostic_aggregates_multiple_batches(case, monkeypatch):
    """[WORKFLOW-C.C1] When multiple pre-decision
    asymmetric batches exist, the diagnostic aggregates:
    the executable/insufficient leg SETS are unions across
    batches; the timestamp range spans the earliest and
    latest pre-decision received_at.
    """
    args, rows = case
    # Make book_at_decision earlier than the asymmetric
    # batches (same fix as test_asymmetric_diagnostic_attribution_pre_decision).
    earlier = NOW - timedelta(seconds=90)
    new_last = rows[0].__class__(
        observed_at=earlier, received_at=earlier,
        signal_score=rows[0].signal_score, quotes=rows[0].quotes,
    )
    new_rows = (rows[0], new_last)
    # Two asymmetric batches: one with long-executable,
    # one with short-executable (different asymmetry
    # polarity). Both AFTER book_at_decision (NOW - 90s)
    # and BEFORE now.
    batch1 = (NOW - timedelta(seconds=60)).isoformat()
    batch2 = (NOW - timedelta(seconds=30)).isoformat()
    monkeypatch.setattr(replay, 'build_spread_observations', lambda **_: ArchiveObservationBuild(
        new_rows, (), 0, None, (), (
            {'received_at': batch1, 'state': 'ASYMMETRIC_EXECUTION_QUALITY',
             'executable': ['long'], 'insufficient': ['short'],
             'depth_by_leg': {'long': {'bid_depth': 75, 'ask_depth': 75, 'lot_size': 75},
                              'short': {'bid_depth': 1, 'ask_depth': 1, 'lot_size': 75}}},
            {'received_at': batch2, 'state': 'ASYMMETRIC_EXECUTION_QUALITY',
             'executable': ['short'], 'insufficient': ['long'],
             'depth_by_leg': {'long': {'bid_depth': 1, 'ask_depth': 1, 'lot_size': 75},
                              'short': {'bid_depth': 75, 'ask_depth': 75, 'lot_size': 75}}},
        )))
    result = replay.replay_full_policy(**args)
    diag = result["asymmetric_diagnostic"]
    # Both batches are pre-decision.
    assert diag["pre_decision_asymmetric_observed"] is True
    assert diag["pre_decision_batch_count"] == 2
    assert diag["asymmetric_batch_count"] == 2
    # Union: both legs appear in both executable and
    # insufficient (across different batches with different
    # polarity). sorted() gives deterministic ordering.
    assert diag["executable_legs"] == ["long", "short"]
    assert diag["insufficient_legs"] == ["long", "short"]
    # Timestamp range: earliest is batch1, latest is batch2.
    assert diag["earliest_received_at"] == batch1
    assert diag["latest_received_at"] == batch2
    # Still fail-closed.
    assert result["reason"] == "asymmetric_execution_quality_before_decision"


def test_asymmetric_diagnostic_malformed_received_at_does_not_crash(case, monkeypatch):
    """[WORKFLOW-C.C1] Defensive: a malformed ``received_at``
    in an asymmetric batch entry degrades to exclusion from
    the timestamp range (not a crash). The diagnostic block
    still surfaces the leg attribution and counts.
    """
    args, rows = case
    # The case fixture has ``book_at_decision.received_at
    # == NOW`` (the first observation). The pre-decision
    # window is strictly AFTER book_at_decision and at-or-
    # before now. Drop the post-decision row (NOW + 1min)
    # so prior_books doesn't include it, and APPEND an
    # earlier observation AFTER rows[0] so book_at_decision
    # (= prior_books[-1]) is that earlier timestamp.
    # Now book_at_decision.received_at = NOW - 60s, the
    # asymmetric batch at NOW - 30s is in the pre-decision
    # window (NOW - 60s < NOW - 30s <= NOW), and the
    # malformed batch is excluded by the defensive helper.
    earlier = NOW - timedelta(seconds=60)
    new_last = rows[0].__class__(
        observed_at=earlier, received_at=earlier,
        signal_score=rows[0].signal_score, quotes=rows[0].quotes,
    )
    new_rows = (rows[0], new_last)
    monkeypatch.setattr(replay, 'build_spread_observations', lambda **_: ArchiveObservationBuild(
        new_rows, (), 0, None, (), (
            {'received_at': 'not-a-date', 'state': 'ASYMMETRIC_EXECUTION_QUALITY',
             'executable': ['long'], 'insufficient': ['short'],
             'depth_by_leg': {'long': {'bid_depth': 75, 'ask_depth': 75, 'lot_size': 75},
                              'short': {'bid_depth': 1, 'ask_depth': 1, 'lot_size': 75}}},
            {'received_at': (NOW - timedelta(seconds=30)).isoformat(),
             'state': 'ASYMMETRIC_EXECUTION_QUALITY',
             'executable': ['short'], 'insufficient': ['long'],
             'depth_by_leg': {'long': {'bid_depth': 1, 'ask_depth': 1, 'lot_size': 75},
                              'short': {'bid_depth': 75, 'ask_depth': 75, 'lot_size': 75}}},
        )))
    # Should not raise.
    result = replay.replay_full_policy(**args)
    diag = result["asymmetric_diagnostic"]
    # The malformed batch is excluded from the pre-decision
    # LIST (the timestamp doesn't parse), so pre_decision_batch_count
    # is 1 (only the well-formed batch).
    assert diag["pre_decision_batch_count"] == 1
    # But both batches contribute to the LEG attribution --
    # the malformed batch still has a parseable
    # ``executable``/``insufficient`` field, so the union
    # spans both batches. This is the operator-visible
    # answer to "which legs were involved?"
    assert diag["executable_legs"] == ["long", "short"]
    assert diag["insufficient_legs"] == ["long", "short"]
    # And the timestamp range is the well-formed batch only
    # (the malformed one can't contribute to earliest/latest).
    assert diag["earliest_received_at"] == (NOW - timedelta(seconds=30)).isoformat()


def test_master_scope_mismatch_rejected(case):
    args, _ = case
    args['master_sha256'] = 'b' * 64
    with pytest.raises(ReplayInputError, match='digests must match'):
        replay.replay_full_policy(**args)


def test_connector_consumes_verified_public_capture(case, monkeypatch):
    from types import SimpleNamespace
    from partner_research_capture import persist_public_input
    args, _ = case
    monkeypatch.setattr("intraday_spread_archive_adapter.master_proves_public_scope", lambda *_: True)
    capture = persist_public_input(args['archive_root'], SimpleNamespace(name='NIFTY',
        research_bars=args['evaluation_inputs']['bars'], research_received_at=NOW,
        research_future_token=123, research_public_scope=public_scope('a' * 64), sig=None, error=''),
        regime='REGIME_1_NORMAL', evaluation_at=NOW)
    args['public_capture_paths'] = [capture['path']]
    with pytest.raises(ReplayInputError, match='cannot mix'):
        replay.replay_full_policy(**args)
    args['public_observations'] = []
    result = replay.replay_full_policy(**args)
    assert result['public_sources']['sources'][0]['sha256'] == capture['sha256']
    assert result['public_sources']['coverage'] == 'SUPPLIED_CAPTURES_ONLY'
    assert result['state'] == 'UNRESOLVED'
    assert not result['can_qualify']


def test_connector_rejects_decision_bars_not_bound_to_capture(case, monkeypatch):
    from types import SimpleNamespace
    from partner_research_capture import persist_public_input
    args, _ = case
    monkeypatch.setattr("intraday_spread_archive_adapter.master_proves_public_scope", lambda *_: True)
    capture = persist_public_input(args['archive_root'], SimpleNamespace(name='NIFTY',
        research_bars=args['evaluation_inputs']['bars'], research_received_at=NOW,
        research_future_token=123, research_public_scope=public_scope('a' * 64), sig=None, error=''),
        regime='REGIME_1_NORMAL', evaluation_at=NOW)
    args['public_observations'] = []
    args['public_capture_paths'] = [capture['path']]
    args['evaluation_inputs']['bars'] = args['evaluation_inputs']['bars'].copy()
    args['evaluation_inputs']['bars'].iloc[-1, 4] += 1
    with pytest.raises(ReplayInputError, match="decision bars are not bound"):
        replay.replay_full_policy(**args)


def test_unmocked_archive_to_real_policy_and_exit(case, monkeypatch):
    import hashlib
    import json
    from intraday_spread_archive_adapter import build_spread_observations
    args, rows = case
    monkeypatch.setattr(replay, 'build_spread_observations', build_spread_observations)
    quotes = rows[0].quotes
    contracts = {q.token: dict(instrument_token=str(q.token), tradingsymbol=q.symbol, underlying='NIFTY',
        exchange='NFO', instrument_type=q.option_type, expiry=q.expiry, strike=q.strike, lot_size=q.lot_size)
        for q in quotes}
    futures = {
        123: dict(instrument_token='123', tradingsymbol='NIFTY26SEPFUT', underlying='NIFTY', exchange='NFO',
                  instrument_type='FUT', expiry='2026-09-24', strike=0.0, lot_size=75, tick_size=.05),
        124: dict(instrument_token='124', tradingsymbol='NIFTY26OCTFUT', underlying='NIFTY', exchange='NFO',
                  instrument_type='FUT', expiry='2026-10-29', strike=0.0, lot_size=75, tick_size=.05),
    }
    master_contracts = [*contracts.values(), *futures.values()]
    raw = ('instrument_token,tradingsymbol,name,exchange,instrument_type,expiry,strike,lot_size,tick_size\n' +
           ''.join(f"{q['instrument_token']},{q['tradingsymbol']},NIFTY,NFO,{q['instrument_type']},"
                   f"{q['expiry']},{q['strike']},{q['lot_size']},{q.get('tick_size', .05)}\n"
                   for q in master_contracts)).encode()
    digest = hashlib.sha256(raw).hexdigest()
    canonical = ('\n'.join(json.dumps(item) for item in master_contracts) + '\n').encode()
    directory = args['archive_root'] / 'contract-masters' / 'NFO' / digest
    directory.mkdir(parents=True)
    (directory / 'raw.csv').write_bytes(raw)
    (directory / 'contracts.jsonl').write_bytes(canonical)
    (directory / 'manifest.json').write_text(json.dumps(dict(raw_sha256=digest,
        canonical_sha256=hashlib.sha256(canonical).hexdigest())), encoding='utf-8')
    events = []
    for row in rows:
        for quote in row.quotes:
            depth = dict(buy=[dict(price=quote.bid, quantity=quote.bid_depth)],
                         sell=[dict(price=quote.ask, quantity=quote.ask_depth)])
            packet = dict(instrument_token=quote.token, timestamp=row.received_at.isoformat(), depth=depth,
                          oi=quote.oi, volume=quote.volume)
            events.append(dict(received_at_utc=row.received_at.isoformat(), provider_timestamp_utc=row.received_at.isoformat(),
                contract=contracts[quote.token], buy_depth=depth['buy'], sell_depth=depth['sell'],
                oi=quote.oi, volume=quote.volume, raw_packet=packet,
                raw_sha256=hashlib.sha256(json.dumps(packet, sort_keys=True, separators=(',', ':')).encode()).hexdigest()))
    args['master_sha256'] = args['evaluation_inputs']['contract_master_sha256'] = digest
    args['events'] = events
    result = replay.replay_full_policy(**args)
    assert result['state'] == 'CLOSED'
    assert result['replay']['exit_trigger'] == 'INVALIDATION'
    assert result['partial_batches'] == []
    assert not result['can_qualify']
    from types import SimpleNamespace
    from partner_research_capture import persist_public_input
    from research_cli import main
    capture = persist_public_input(args['archive_root'], SimpleNamespace(name='NIFTY',
        research_bars=args['evaluation_inputs']['bars'], research_received_at=NOW,
        research_future_token=123, research_public_scope=public_scope(digest), sig=None, error=''),
        regime='REGIME_1_NORMAL', evaluation_at=NOW)
    forged_scope = {**public_scope(digest), "selected_future": {
        **public_scope(digest)["selected_future"], "tradingsymbol": "FORGEDFUT"}}
    forged = persist_public_input(args['archive_root'], SimpleNamespace(name='NIFTY',
        research_bars=args['evaluation_inputs']['bars'], research_received_at=NOW,
        research_future_token=123, research_public_scope=forged_scope, sig=None, error=''),
        regime='REGIME_1_NORMAL', evaluation_at=NOW)
    diagnostic = dict(args, public_observations=[], public_capture_paths=[forged['path']])
    with pytest.raises(ReplayInputError, match="does not prove public futures"):
        replay.replay_full_policy(**diagnostic)
    omitted_front_scope = {**public_scope(digest), "selected_future": public_scope(digest)["next_future"],
                           "eligible_future_expiries": ["2026-10-29"], "next_future": None}
    omitted = persist_public_input(args['archive_root'], SimpleNamespace(name='NIFTY',
        research_bars=args['evaluation_inputs']['bars'], research_received_at=NOW,
        research_future_token=124, research_public_scope=omitted_front_scope, sig=None, error=''),
        regime='REGIME_1_NORMAL', evaluation_at=NOW)
    with pytest.raises(ReplayInputError, match="does not prove public futures"):
        replay.replay_full_policy(**dict(args, public_observations=[], public_capture_paths=[omitted['path']]))
    bundle = candidate_bundle()
    bundle['received_at'] = bundle['snapshot']['taken_at'] = NOW.isoformat()
    bundle['snapshot']['expiry'] = EXPIRY.isoformat()
    for item in bundle['contracts']:
        item['expiry'] = EXPIRY.isoformat()
    for item in bundle['snapshot']['quotes']:
        item['last_trade_time'] = NOW.isoformat()
    root = args['archive_root']
    chain_path, policy_path, output = root / 'chain.json', root / 'policy.json', root / 'report.json'
    chain_path.write_text(json.dumps(bundle), encoding='utf-8')
    policy_path.write_text(json.dumps(dict(policy_id='fixture', min_signal_score=1,
        take_profit_rs=1, stop_loss_rs=1, execution_delay=0,
        fee_multipliers=[1, 1.25], additional_slippage_bps=[0, 10])), encoding='utf-8')
    quote_dir = root / 'quotes' / NOW.date().isoformat()
    quote_dir.mkdir(parents=True)
    (quote_dir / 'quotes.jsonl.open').write_text('\n'.join(json.dumps(event) for event in events) + '\n', encoding='utf-8')
    command = ['replay-full-policy', '--archive-root', str(root), '--public-input', capture['path'],
        '--public-capture', capture['path'], '--candidate-evidence', str(chain_path), '--underlying', 'NIFTY',
        '--master-sha256', digest, '--policy', str(policy_path), '--output', str(output)]
    assert main(command) == 0
    stored = json.loads(output.read_text())
    assert stored['state'] == 'UNRESOLVED'  # Only initial public capture, no fabricated exit.
    assert len(stored['cost_sensitivity']['scenarios']) == 4
    assert not stored['can_qualify']
    before = output.read_bytes()
    assert main(command) == 0
    assert output.read_bytes() == before
    policy_path.write_text(json.dumps(dict(policy_id='fixture', min_signal_score=1,
        take_profit_rs=1, stop_loss_rs=1, fee_per_leg_rs=100)), encoding='utf-8')
    assert main(command) == 2  # Same destination cannot replace earlier economics.
    assert output.read_bytes() == before
    # Tampering with normalized quotes without modifying raw evidence removes
    # the decision book instead of producing a fabricated executable outcome.
    events[0]['buy_depth'] = [dict(price=999, quantity=500)]
    assert replay.replay_full_policy(**args)['reason'] == 'decision_book_missing'
