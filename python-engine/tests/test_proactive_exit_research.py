from datetime import datetime,timedelta,timezone
from proactive_exit_research import simulate_partial_target_trail
from proactive_intelligence import ShadowProposal
from dataclasses import replace
import asyncio
import hashlib
import json
import aiosqlite
import pytest
import proactive_exit_research as exit_research


def _comparison_inputs():
    at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    proposal = ShadowProposal("identity", "trend_pullback_v1", "NSE:X", 100, 95, 110,
        at + timedelta(minutes=30), 1, 100, "fixture", at, at,
        at + timedelta(minutes=30), at + timedelta(hours=1))
    return dict(research_run_id="immutable-exit", proposals=[proposal],
        future_bars={"NSE:X": [{"timestamp": (at + timedelta(minutes=1)).isoformat(),
            "open":100, "high":101, "low":99, "close":100}]}, cash=1000, fee_rate=0, slippage_bps=0)


@pytest.mark.asyncio
async def test_exit_comparison_retains_canonical_manifest_and_identical_retry(db_path):
    inputs = _comparison_inputs()
    first = await exit_research.persist_exit_policy_comparison(db_path, **inputs)
    async with aiosqlite.connect(db_path) as db:
        before = await (await db.execute("SELECT * FROM proactive_exit_research_runs")).fetchall()
        digest, manifest = await (await db.execute("SELECT r.input_sha256,m.manifest_json FROM proactive_exit_research_runs r JOIN proactive_exit_research_manifests m USING (research_run_id)")).fetchone()
    assert hashlib.sha256(manifest.encode()).hexdigest() == digest
    payload = json.loads(manifest)
    assert payload["version"] == "matched-exit-evidence-v3"
    assert payload["proposals"][0]["instrument"] == "NSE:X"
    assert payload["proposals"][0]["holding_deadline"] == inputs["proposals"][0].holding_deadline.isoformat()
    assert set(payload["implementation_sha256"]) == {"exit_research", "primary_evaluator"}
    assert await exit_research.persist_exit_policy_comparison(db_path, **inputs) == first
    async with aiosqlite.connect(db_path) as db:
        assert await (await db.execute("SELECT * FROM proactive_exit_research_runs")).fetchall() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["instrument", "policy_id", "data_cutoff", "entry_deadline", "holding_deadline"])
async def test_exit_comparison_rejects_changed_proposal_identity_and_clocks(db_path, field):
    inputs = _comparison_inputs()
    await exit_research.persist_exit_policy_comparison(db_path, **inputs)
    proposal = inputs["proposals"][0]
    value = "NSE:OTHER" if field == "instrument" else "other-policy" if field == "policy_id" else getattr(proposal, field) + timedelta(minutes=1)
    inputs["proposals"] = [replace(proposal, **{field:value})]
    with pytest.raises(ValueError, match="manifest conflicts"):
        await exit_research.persist_exit_policy_comparison(db_path, **inputs)


@pytest.mark.asyncio
async def test_exit_comparison_rejects_changed_implementation(db_path, monkeypatch):
    inputs = _comparison_inputs()
    await exit_research.persist_exit_policy_comparison(db_path, **inputs)
    monkeypatch.setattr(exit_research, "_shadow_implementation_identity", lambda: "a" * 64)
    with pytest.raises(ValueError, match="manifest conflicts"):
        await exit_research.persist_exit_policy_comparison(db_path, **inputs)


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["bars", "fee_rate", "slippage_bps"])
async def test_exit_comparison_still_binds_bars_and_costs(db_path, changed):
    inputs = _comparison_inputs()
    await exit_research.persist_exit_policy_comparison(db_path, **inputs)
    if changed == "bars":
        inputs["future_bars"]["NSE:X"][0]["high"] = 102
    else:
        inputs[changed] = .1
    with pytest.raises(ValueError, match="manifest conflicts"):
        await exit_research.persist_exit_policy_comparison(db_path, **inputs)


@pytest.mark.asyncio
async def test_legacy_exit_row_is_preserved_readable_and_not_current_reusable(db_path):
    inputs = _comparison_inputs()
    async with aiosqlite.connect(db_path) as db:
        await db.execute("CREATE TABLE proactive_exit_research_runs (research_run_id TEXT PRIMARY KEY,input_sha256 TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL)")
        await db.execute("INSERT INTO proactive_exit_research_runs VALUES (?,?,?,?)", (inputs["research_run_id"], "legacy-digest", "[]", "legacy-time"))
        await db.commit()
    with pytest.raises(ValueError, match="manifest conflicts"):
        await exit_research.persist_exit_policy_comparison(db_path, **inputs)
    report = await exit_research.exit_policy_report(db_path)
    assert report[0]["comparisons"] == [] and report[0]["can_place_orders"] is False
    async with aiosqlite.connect(db_path) as db:
        assert await (await db.execute("SELECT research_run_id,input_sha256,result_json,created_at FROM proactive_exit_research_runs")).fetchall() == [(inputs["research_run_id"], "legacy-digest", "[]", "legacy-time")]
    inputs["research_run_id"] = "fresh-v3"
    await exit_research.persist_exit_policy_comparison(db_path, **inputs)
    assert len(await exit_research.exit_policy_report(db_path)) == 2


@pytest.mark.asyncio
async def test_concurrent_identical_exit_requests_are_idempotent(db_path):
    inputs = _comparison_inputs()
    results = await asyncio.gather(*[exit_research.persist_exit_policy_comparison(db_path, **inputs) for _ in range(2)])
    assert results[0] == results[1]
    async with aiosqlite.connect(db_path) as db:
        assert (await (await db.execute("SELECT COUNT(*) FROM proactive_exit_research_runs")).fetchone())[0] == 1


@pytest.mark.asyncio
async def test_original_four_value_writer_remains_schema_compatible(db_path):
    await exit_research.persist_exit_policy_comparison(db_path, **_comparison_inputs())
    async with aiosqlite.connect(db_path) as db:
        columns = await (await db.execute("PRAGMA table_info(proactive_exit_research_runs)")).fetchall()
        assert [row[1] for row in columns] == ["research_run_id", "input_sha256", "result_json", "created_at"]
        # Literal old-code insert shape on an isolated database, not a data
        # rollback or permission to deploy previous code against actual data.
        await db.execute("INSERT INTO proactive_exit_research_runs VALUES (?,?,?,?)", ("old-writer", "old-hash", "[]", "old-time"))
        await db.commit()
    assert len(await exit_research.exit_policy_report(db_path)) == 2


@pytest.mark.asyncio
async def test_conflicting_concurrent_exit_requests_preserve_one_manifest(db_path):
    inputs = _comparison_inputs()
    changed = dict(inputs, fee_rate=.001)
    results = await asyncio.gather(exit_research.persist_exit_policy_comparison(db_path, **inputs),
                                   exit_research.persist_exit_policy_comparison(db_path, **changed),
                                   return_exceptions=True)
    assert sum(isinstance(result, list) for result in results) == 1
    assert sum(isinstance(result, ValueError) for result in results) == 1
    async with aiosqlite.connect(db_path) as db:
        assert (await (await db.execute("SELECT COUNT(*) FROM proactive_exit_research_runs")).fetchone())[0] == 1
        assert (await (await db.execute("SELECT COUNT(*) FROM proactive_exit_research_manifests")).fetchone())[0] == 1


@pytest.mark.asyncio
async def test_caller_bar_mutation_after_admission_cannot_change_evaluated_input(db_path, monkeypatch):
    inputs = _comparison_inputs()
    original_init = exit_research._init_exit_research_schema

    async def mutate_after_snapshot(db):
        inputs["future_bars"]["NSE:X"][0]["low"] = 94
        await original_init(db)

    monkeypatch.setattr(exit_research, "_init_exit_research_schema", mutate_after_snapshot)
    rows = await exit_research.persist_exit_policy_comparison(db_path, **inputs)
    assert all(row["open_outcomes"] == 1 for row in rows)
    async with aiosqlite.connect(db_path) as db:
        manifest = (await (await db.execute("SELECT manifest_json FROM proactive_exit_research_manifests")).fetchone())[0]
    assert json.loads(manifest)["bars"]["NSE:X"][0]["low"] == 99


@pytest.mark.asyncio
async def test_duplicate_opportunity_cannot_inflate_exit_sample(db_path):
    inputs = _comparison_inputs()
    inputs["proposals"] *= 2
    with pytest.raises(ValueError, match="unique opportunity identities"):
        await exit_research.persist_exit_policy_comparison(db_path, **inputs)


def test_partial_trail_uses_stop_first_for_ambiguous_target_bar_and_costs_both_exits():
    at=datetime(2026,1,1,tzinfo=timezone.utc); p=ShadowProposal("x","trend_pullback_v1","NSE:X",100,95,110,at+timedelta(minutes=30),1,100,"x",at,at,at+timedelta(minutes=30),at+timedelta(hours=1))
    bars=[{"timestamp":(at+timedelta(minutes=1)).isoformat(),"open":100,"high":111,"low":94,"close":100}]
    r=simulate_partial_target_trail(p,bars,cash=1000,fee_rate=.001,slippage_bps=0)
    assert r.status=="CLOSED" and r.reason=="STOP" and r.fees>0
