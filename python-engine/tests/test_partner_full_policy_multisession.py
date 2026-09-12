"""Unmocked archive -> deployed policy -> held-out review acceptance fixture."""
from datetime import timedelta
import hashlib
import json

from intraday_spread_chronological import ChronologicalPolicy
from intraday_spread_holdout import build_heldout_comparison, heldout_case_from_full_policy_report
from partner_full_policy_replay import replay_full_policy
from partner_qualification import evaluate_deployed_full_policy, load_candidate_evidence
from partner_qualification_review import (QualificationCriteria, build_qualification_review_package,
    freeze_qualification_criteria, write_qualification_criteria_manifest)
from tests.test_fno_signal_scan import _frame, LONG_ROWS, NOW, EXPIRY
from tests.test_partner_qualification import candidate_bundle, provenance


def _raw_event(contract, received_at, *, bid, ask):
    depth = {"buy": [{"price": bid, "quantity": 500}],
             "sell": [{"price": ask, "quantity": 500}]}
    packet = {"instrument_token": int(contract["instrument_token"]),
              "timestamp": received_at.isoformat(), "depth": depth}
    return {"received_at_utc": received_at.isoformat(),
            "provider_timestamp_utc": received_at.isoformat(), "contract": contract,
            "buy_depth": depth["buy"], "sell_depth": depth["sell"], "raw_packet": packet,
            "raw_sha256": hashlib.sha256(json.dumps(packet, sort_keys=True,
                separators=(",", ":")).encode()).hexdigest()}


def _inputs(decision_at, master_sha256):
    shift = decision_at.date() - NOW.date()
    frame = _frame(LONG_ROWS).copy()
    frame.index = frame.index + shift
    bundle = candidate_bundle()
    bundle["received_at"] = bundle["snapshot"]["taken_at"] = decision_at.isoformat()
    bundle["snapshot"]["expiry"] = EXPIRY.isoformat()
    for item in bundle["contracts"]:
        item["expiry"] = EXPIRY.isoformat()
    for item in bundle["snapshot"]["quotes"]:
        item["last_trade_time"] = decision_at.isoformat()
    book, snapshot, profile = load_candidate_evidence(bundle, underlying="NIFTY", decision_at=decision_at)
    inputs = {"underlying": "NIFTY", "bars": frame, "regime": "REGIME_1_NORMAL",
              "decision_at": decision_at, "bar_provenance": provenance(decision_at),
              "book": book, "snapshot": snapshot, "profile": profile,
              "contract_master_sha256": master_sha256}
    decision = evaluate_deployed_full_policy(**inputs)
    assert decision.state == "ACCEPTED"
    return inputs, decision


def _write_master(root, contracts):
    raw = ("instrument_token,tradingsymbol,name,exchange,instrument_type,expiry,strike,lot_size\n" +
           "".join(f"{item['instrument_token']},{item['tradingsymbol']},NIFTY,NFO,{item['instrument_type']},"
                   f"{item['expiry']},{item['strike']},{item['lot_size']}\n" for item in contracts.values())).encode()
    digest = hashlib.sha256(raw).hexdigest()
    canonical = ("\n".join(json.dumps(item) for item in contracts.values()) + "\n").encode()
    directory = root / "contract-masters" / "NFO" / digest
    directory.mkdir(parents=True)
    (directory / "raw.csv").write_bytes(raw)
    (directory / "contracts.jsonl").write_bytes(canonical)
    (directory / "manifest.json").write_text(json.dumps({"raw_sha256": digest,
        "canonical_sha256": hashlib.sha256(canonical).hexdigest()}), encoding="utf-8")
    return digest


def test_unmocked_multisession_archive_reaches_costed_close_and_unresolved_review(tmp_path):
    template = candidate_bundle()
    contracts = {int(item["token"]): {"instrument_token": str(item["token"]),
        "tradingsymbol": item["tradingsymbol"], "underlying": "NIFTY", "exchange": "NFO",
        "instrument_type": item["instrument_type"], "expiry": EXPIRY.isoformat(),
        "strike": item["strike"], "lot_size": item["lot_size"]} for item in template["contracts"]}
    master_sha256 = _write_master(tmp_path, contracts)
    reports = []
    for offset, closes in ((0, True), (3, False)):
        decision_at = NOW + timedelta(days=offset)
        inputs, decision = _inputs(decision_at, master_sha256)
        legs = {leg.instrument_token: leg for leg in decision.candidate.legs}
        entry_events = [_raw_event(contracts[token], decision_at, bid=leg.bid, ask=leg.ask)
                        for token, leg in legs.items()]
        events = list(entry_events)
        public = [{"observed_at": decision_at, "received_at": decision_at,
                   "price": decision.signal.close}]
        if closes:
            exit_at = decision_at + timedelta(minutes=1)
            for token, leg in legs.items():
                bid, ask = ((80, 82) if leg.side == "BUY" else (44, 46))
                events.append(_raw_event(contracts[token], exit_at, bid=bid, ask=ask))
            public.append({"observed_at": exit_at, "received_at": exit_at,
                           "price": decision.candidate.invalidation_level})
        report = replay_full_policy(evaluation_inputs=inputs, events=events, archive_root=tmp_path,
            master_sha256=master_sha256, execution_policy=ChronologicalPolicy(
                "fixture-caller", 1, 1, 1, fee_per_leg_rs=2), public_observations=public,
            fee_multipliers=[1, 1.25], additional_slippage_bps=[0, 10])
        reports.append(report)

    assert reports[0]["state"] == "CLOSED"
    assert reports[0]["replay"]["result"]["total_cost_rs"] > 0
    assert reports[0]["replay"]["result"]["net_pnl_rs"] is not None
    assert reports[1]["state"] == "UNRESOLVED"
    assert reports[1]["replay"]["result"]["accepted_entry"] is True

    signal_identity = hashlib.sha256(b"unmocked-multisession-signal-evidence").hexdigest()
    cases = [heldout_case_from_full_policy_report(item, signal_artifact_sha256=signal_identity)
             for item in reports]
    policy_ids = {item.policy_id for item in cases}
    assert len(policy_ids) == 1
    policy_id = policy_ids.pop()
    holdout_sessions = [item.session_date for item in cases]
    criteria = QualificationCriteria(policy_id, min_covered_sessions=2, min_closed_outcomes=1,
        max_unresolved_outcomes=1, max_drawdown_rs=-10_000,
        stressed_fee_multiplier=1.25, stressed_slippage_bps=10)
    declared = [("NIFTY", policy_id, day) for day in holdout_sessions]
    criteria_manifest = freeze_qualification_criteria(criteria=criteria, underlying="NIFTY",
        training_sessions=["2026-07-09"], holdout_sessions=holdout_sessions,
        declared_coverage=declared, frozen_at=NOW - timedelta(days=1))
    criteria_path = tmp_path / "criteria.json"
    write_qualification_criteria_manifest(criteria_path, criteria_manifest)
    before = criteria_path.read_bytes()
    write_qualification_criteria_manifest(criteria_path, criteria_manifest)
    assert criteria_path.read_bytes() == before
    dataset_sha256 = hashlib.sha256("".join(item["evidence_sha256"] for item in reports).encode()).hexdigest()
    heldout = build_heldout_comparison(dataset_sha256=dataset_sha256, code_revision="fixture-real-path",
        training_sessions=["2026-07-09"], holdout_sessions=holdout_sessions,
        declared_coverage=declared, cases=cases,
        review_criteria_sha256=criteria_manifest["criteria_manifest_sha256"])
    group = heldout["groups"][0]
    assert group["closed"] == 1 and group["unresolved"] == 1 and group["unavailable"] == 0
    assert group["net_pnl_rs"] == reports[0]["replay"]["result"]["net_pnl_rs"]
    assert group["max_sequential_drawdown_rs"] <= 0
    assert heldout["automatic_qualification"] is False
    review = build_qualification_review_package(policy_manifest=reports[0]["manifest"], criteria=criteria,
        heldout_report=heldout, readiness={"collection": "COMPLETE", "causal_research": "COMPLETE",
                                          "outcome_coverage": "COMPLETE"},
        criteria_manifest=criteria_manifest)
    row = review["per_index"][0]
    assert row["drawdown_state"] == row["cost_stress_state"] == "VERIFIED"
    assert row["review_state"] == "READY_FOR_HUMAN_REVIEW" and not row["blockers"]
    assert review["automatic_qualification"] is False and review["can_send_advice"] is False
