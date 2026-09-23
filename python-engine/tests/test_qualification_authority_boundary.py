"""Exercise real registry admission and revalidation, not just an isolated verifier."""
import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import aiosqlite
import pytest

from config import settings
from partner_manual_advisory import (PartnerAdvisoryProfile, save_partner_profile,
    record_research_artifact, record_strategy_qualification, qualification_is_current)
from partner_qualification_authority import read_artifact, verify_authorization_package
from tests.qualification_package_fixture import authorization_package, register_test_package

NOW = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=1)
SCOPE = dict(underlying="NIFTY", structure_kind="DIRECTIONAL_DEBIT_SPREAD",
             horizon="INTRADAY", policy_version="partner-manual-intraday-v1")


@pytest.mark.asyncio
async def test_real_registry_requires_verified_package_and_revalidates(db_path, monkeypatch):
    profile = PartnerAdvisoryProfile(holding_period="INTRADAY")
    await save_partner_profile(db_path, profile, now=NOW)
    await register_test_package(db_path, profile, NOW, monkeypatch)
    assert await qualification_is_current(db_path, **SCOPE, now=NOW)
    assert not await qualification_is_current(db_path, **{**SCOPE,"underlying":"SENSEX"}, now=NOW)
    assert not await qualification_is_current(db_path, **SCOPE, now=NOW+timedelta(days=30))
    monkeypatch.setattr(settings, "FNO_STOP_PREMIUM_PCT", settings.FNO_STOP_PREMIUM_PCT + .01)
    assert not await qualification_is_current(db_path, **SCOPE, now=NOW)


@pytest.mark.asyncio
async def test_profile_mutation_and_file_tampering_revoke_authority(db_path, monkeypatch):
    profile = PartnerAdvisoryProfile(holding_period="INTRADAY")
    await save_partner_profile(db_path, profile, now=NOW)
    await register_test_package(db_path, profile, NOW, monkeypatch)
    await save_partner_profile(db_path, replace(profile, version=2, risk_limit_rs=100), now=NOW)
    assert not await qualification_is_current(db_path, **SCOPE, now=NOW)
    from pathlib import Path
    (Path(settings.PARTNER_ARTIFACT_ROOT)/'test-package.json').write_text('{}')
    assert not await qualification_is_current(db_path, **SCOPE, now=NOW)


@pytest.mark.asyncio
async def test_json_stub_and_disable_flag_cannot_qualify(db_path, tmp_path, monkeypatch):
    monkeypatch.setattr(settings,"PARTNER_ARTIFACT_ROOT",str(tmp_path))
    monkeypatch.setattr(settings,"PARTNER_VERIFY_RESEARCH_ARTIFACTS",False)
    (tmp_path/'stub.json').write_bytes(b'{}')
    profile=PartnerAdvisoryProfile(holding_period="INTRADAY")
    await save_partner_profile(db_path,profile,now=NOW)
    with pytest.raises(ValueError,match="fingerprint"):
        await record_research_artifact(db_path,dataset_ref='stub.json',content_sha256='a'*64,
            created_at=NOW,description='test stub')
    await record_research_artifact(db_path,dataset_ref='stub.json',content_sha256=hashlib.sha256(b'{}').hexdigest(),
        created_at=NOW,description='test stub')
    with pytest.raises(ValueError,match="authorization package"):
        await record_strategy_qualification(db_path,**SCOPE,dataset_ref='stub.json',reviewed_at=NOW)
    # Even an old, directly written qualification row cannot bypass runtime checks.
    async with aiosqlite.connect(db_path) as db:
        await db.execute("INSERT INTO partner_advisory_strategy_qualifications VALUES(?,?,?,?,?,?,?)",
            (*SCOPE.values(),'stub.json',NOW.isoformat(),'QUALIFIED_FOR_ADVISORY'))
        await db.commit()
    assert not await qualification_is_current(db_path,**SCOPE,now=NOW)


@pytest.mark.parametrize("fault", ["future_review","naive_review","expired","no_approval",
    "failed_heldout","missing_reports","changed_policy","changed_hash","overlong_validity"])
def test_authorization_package_failure_cases(fault):
    profile=PartnerAdvisoryProfile(holding_period="INTRADAY")
    value=authorization_package(profile,NOW)
    if fault=="future_review": value['review_identity']['reviewed_at']=(NOW+timedelta(days=1)).isoformat()
    if fault=="naive_review": value['review_identity']['reviewed_at']=NOW.replace(tzinfo=None).isoformat()
    if fault=="expired": value['validity_period']['end']=NOW.isoformat()
    if fault=="no_approval": value['review_identity']['decision']='PENDING'
    if fault=="failed_heldout": value['heldout_report']['groups'][0]['net_pnl_rs']=-100
    if fault=="missing_reports": value['source_reports']=[]
    if fault=="changed_policy": value['policy_manifest']['frozen_policy']['source_sha256']['fno_costs.py']='0'*64
    if fault=="overlong_validity": value['validity_period']['end']=(NOW+timedelta(days=365)).isoformat()
    data=json.dumps(value).encode(); sha=hashlib.sha256(data).hexdigest()
    if fault=="changed_hash": sha='0'*64
    with pytest.raises(ValueError):
        verify_authorization_package(data,sha,**SCOPE,profile=profile,now=NOW)


def test_artifact_path_cannot_escape_root(tmp_path,monkeypatch):
    root=tmp_path/'root';root.mkdir()
    (tmp_path/'outside.json').write_text('{}')
    monkeypatch.setattr(settings,'PARTNER_ARTIFACT_ROOT',str(root))
    for ref in ['../outside.json',str(tmp_path/'outside.json')]:
        with pytest.raises(ValueError,match='inside'):
            read_artifact(ref)


@pytest.mark.asyncio
async def test_final_dispatch_revalidates_artifact_after_card_was_queued(db_path, monkeypatch):
    from pathlib import Path
    from tests.test_partner_manual_advisory import _candidate, NOW as card_now
    from partner_manual_advisory import persist_candidate, StrategyEvidence
    from hedge_advisory import _claim, _authorize_dispatch

    profile=PartnerAdvisoryProfile(holding_period="INTRADAY")
    await save_partner_profile(db_path,profile,now=card_now)
    await register_test_package(db_path,profile,card_now,monkeypatch)
    candidate=replace(_candidate(),evidence=StrategyEvidence.QUALIFIED_FOR_ADVISORY)
    stored=await persist_candidate(db_path,candidate,profile,now=card_now,queue_for_delivery=True)
    assert stored['status']=='QUEUED'
    key=stored['advisory_id'];kind='manual_market_advisory'
    token=await _claim(db_path,kind,key,now=card_now)
    detail=dict(phase='manual_v1',advisory_id=key,profile_id='default',underlying='NIFTY',
        valid_until=stored['valid_until'],rendered_text=stored['rendered_card'])
    assert await _authorize_dispatch(db_path,kind,key,token,detail,now=card_now)
    (Path(settings.PARTNER_ARTIFACT_ROOT)/'test-package.json').write_bytes(b'{}')
    assert not await _authorize_dispatch(db_path,kind,key,token,detail,now=card_now)
