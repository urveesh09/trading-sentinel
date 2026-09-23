"""Synthetic, explicitly test-only full evidence package; never exported to runtime."""
from dataclasses import asdict
from datetime import timedelta
import hashlib
import json
from pathlib import Path

from intraday_spread_chronological import ChronologicalReplay
from intraday_spread_replay import ReplayResult
from intraday_spread_holdout import build_heldout_comparison, heldout_case_from_full_policy_report
from partner_qualification_review import QualificationCriteria, freeze_qualification_criteria, _sha
from partner_qualification_authority import policy_configuration
from policy_identity import module_sha256s


def authorization_package(profile, now):
    at = now - timedelta(days=2)
    day = at.date().isoformat()
    train = (at - timedelta(days=2)).date().isoformat()
    frozen = dict(format="partner_frozen_policy_v1", evaluator="partner_manual_intraday_full_policy_v1",
        underlying="NIFTY", structure_kind="DIRECTIONAL_DEBIT_SPREAD",
        source_sha256=module_sha256s(Path(__file__).parents[1]),
        configuration=policy_configuration(), profile=asdict(profile))
    frozen["manifest_sha256"] = _sha(frozen)
    policy = frozen["manifest_sha256"]
    manifest = dict(evaluator="partner_manual_intraday_full_policy_v1", underlying="NIFTY",
        decision_at=at.isoformat(), policy_sha256=policy, frozen_policy=frozen,
        contract_master_sha256="c" * 64)
    manifest["manifest_sha256"] = _sha(manifest)
    result = ReplayResult("CLOSED", "test-only", 1, 2, 1, 5, at.isoformat(),
        (at + timedelta(minutes=5)).isoformat(), "a" * 64)
    chronological = ChronologicalReplay(result,"CLOSED",1,(),at.isoformat(),"target",2,"a"*64)
    sensitivity = dict(format="intraday_spread_cost_sensitivity_v1", underlying="NIFTY",
        expiry=(at + timedelta(days=5)).date().isoformat(), policy_id=policy, can_qualify=False,
        can_place_orders=False, scenarios=[dict(fee_multiplier=f,additional_slippage_bps=s,
            state="CLOSED",reason="test-only",net_pnl_rs=p,evidence_sha256=h*64)
            for f,s,p,h in [(1.,0.,5,"a"),(1.5,5.,4,"b")]])
    sensitivity["evidence_sha256"] = _sha(sensitivity)
    public_scope = dict(contract_master_raw_sha256="c"*64)
    report = dict(format="partner_full_policy_replay_v1",decision_id="test-only",
        manifest=manifest,state="CLOSED",replay=asdict(chronological),
        economics_contract="FULL_POLICY_ECONOMICS_V1",cost_sensitivity=sensitivity,
        public_evidence_contract="VERIFIED_ARCHIVED_FUTURE_SCOPE_V1",
        public_sources=dict(sources=[dict(public_scope_state="VERIFIED_CONTRACT_SCOPE",
            public_scope=public_scope,public_scope_sha256=_sha(public_scope))]))
    report["evidence_sha256"] = _sha(report)
    criteria = QualificationCriteria(policy,1,1,0,-100,1.5,5.)
    declared = [("NIFTY",policy,day)]
    cm = freeze_qualification_criteria(criteria=criteria,underlying="NIFTY",training_sessions=[train],
        holdout_sessions=[day],declared_coverage=declared,frozen_at=at-timedelta(days=1))
    heldout = build_heldout_comparison(dataset_sha256="d"*64,code_revision="synthetic-test-only",
        training_sessions=[train],holdout_sessions=[day],declared_coverage=declared,
        cases=[heldout_case_from_full_policy_report(report,signal_artifact_sha256="e"*64)],
        review_criteria_sha256=cm["criteria_manifest_sha256"])
    return dict(format="partner_advisory_authorization_v1",underlying="NIFTY",
        structure_kind="DIRECTIONAL_DEBIT_SPREAD",horizon="INTRADAY",policy_version="partner-manual-intraday-v1",
        policy_manifest=manifest,criteria_manifest=cm,heldout_report=heldout,
        source_reports=[dict(report=report,signal_artifact_sha256="e"*64)],
        review_identity=dict(operator="test-only",decision="APPROVED",reviewed_at=now.isoformat()),
        validity_period=dict(start=now.isoformat(),end=(now+timedelta(days=29)).isoformat()))


async def register_test_package(db_path, profile, now, monkeypatch):
    from config import settings
    from partner_manual_advisory import record_research_artifact, record_strategy_qualification
    root=Path(db_path).parent/'test-artifacts'; root.mkdir(exist_ok=True)
    monkeypatch.setattr(settings,"PARTNER_ARTIFACT_ROOT",str(root))
    data=json.dumps(authorization_package(profile,now),sort_keys=True).encode()
    (root/'test-package.json').write_bytes(data)
    await record_research_artifact(db_path,dataset_ref='test-package.json',content_sha256=hashlib.sha256(data).hexdigest(),
        created_at=now,description='Synthetic test evidence only')
    await record_strategy_qualification(db_path,underlying='NIFTY',structure_kind='DIRECTIONAL_DEBIT_SPREAD',
        horizon='INTRADAY',policy_version='partner-manual-intraday-v1',dataset_ref='test-package.json',reviewed_at=now)
