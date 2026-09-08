from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
import research_archive as archive


def event(stamp="2026-09-08T04:00:00Z", provider="2026-09-08T04:00:00Z"):
    return {"received_at_utc": stamp, "provider_timestamp_utc": provider,
            "contract": {"underlying": "NIFTY"}, "depth_state": "USABLE"}


@pytest.mark.parametrize("provider,status", [(None,"TIME_UNKNOWN"), ("2026-08-01T04:00:00Z","STALE"),
    ("2026-09-08T04:01:00Z","TIME_INVALID"), ("2026-09-08T04:00:00Z","OBSERVED_USABLE")])
def test_readiness_after_finalisation(tmp_path, monkeypatch, provider, status):
    monkeypatch.setattr(archive, "utc_now", lambda: datetime(2026,9,8,4,0,30,tzinfo=timezone.utc))
    writer = archive.QuoteArchive(str(tmp_path), reserved_free_bytes=0)
    writer.append(event(provider=provider)); writer.finalize_day("2026-09-08")
    assert archive.readiness_view(str(tmp_path))["per_index"]["NIFTY"]["quote_observation_status"] == status


def test_budget_survives_restart_and_covers_journals(tmp_path):
    writer = archive.QuoteArchive(str(tmp_path), reserved_free_bytes=0, session_max_bytes=2000)
    writer.record_collection_run({"detail":"x"*900}, expected_interval_sec=60)
    other = archive.QuoteArchive(str(tmp_path), reserved_free_bytes=0, session_max_bytes=2000)
    with pytest.raises(OSError, match="budget"):
        other.record_collection_run({"detail":"x"*900}, expected_interval_sec=60)


def test_compression_low_disk_keeps_source(tmp_path, monkeypatch):
    writer = archive.QuoteArchive(str(tmp_path), reserved_free_bytes=100)
    writer.append(event())
    monkeypatch.setattr(archive.shutil,"disk_usage",lambda _: SimpleNamespace(free=101))
    with pytest.raises(OSError, match="reserve"):
        writer.finalize_day("2026-09-08")
    assert (tmp_path/"quotes/2026-09-08/quotes.jsonl.open").exists()


def test_external_writer_lease_rejects_admission(tmp_path):
    lease=sqlite3.connect(str(tmp_path/"writer-lease.sqlite3")); lease.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(OSError,match="busy"):
            archive.QuoteArchive(str(tmp_path),reserved_free_bytes=0).append(event())
    finally:
        lease.rollback(); lease.close()


@pytest.mark.asyncio
async def test_failed_batch_does_not_prevent_second_index(tmp_path,monkeypatch):
    import research_quote_collector as collector
    from config import settings
    from fno_models import Contract
    import pytz
    now=pytz.timezone("Asia/Kolkata").localize(datetime(2026,9,8,10))
    monkeypatch.setattr(settings,"RESEARCH_ARCHIVE_UNDERLYINGS","NIFTY,SENSEX")
    monkeypatch.setattr(settings,"RESEARCH_ARCHIVE_PATH",str(tmp_path))
    monkeypatch.setattr(settings,"RESEARCH_RESERVED_FREE_BYTES",0)
    collector._archive=None
    contracts={name:Contract(i,name+"FUT",name,now.date(),0,"FUT",1) for i,name in enumerate(("NIFTY","SENSEX"),1)}
    books={name:SimpleNamespace(ready=lambda _:True,front_future=lambda _,c=c:c) for name,c in contracts.items()}
    monkeypatch.setattr(collector,"_select_contracts",lambda book,*_: [(book.front_future(None),"test")])
    class Kite:
        access_token="fixture"
        calls={}
        async def get_quote(self,tokens):
            token=tokens[0]; self.calls[token]=self.calls.get(token,0)+1
            if token==1 and self.calls[token]==2: raise ValueError("bad batch")
            return {token:{"last_price":100,"instrument_token":token}}
    result=await collector.collect_rest_quote_snapshot(Kite(),now_ist=now,books=books)
    assert result["indices"]["SENSEX"]["received_tokens"]==[2]
    assert any(g["reason"]=="quote_batch_exception" for g in result["gaps"])


@pytest.mark.asyncio
async def test_changed_row_is_not_deleted_after_export(tmp_path,monkeypatch):
    import fno_oi_store
    from config import settings
    source=tmp_path/"source.db"
    conn=sqlite3.connect(source)
    conn.executescript("CREATE TABLE fno_chain_oi(snap_ts TEXT,underlying TEXT,expiry TEXT,strike REAL,opt_type TEXT,oi INTEGER,volume INTEGER,ltp REAL,iv REAL); CREATE TABLE fno_fut_snap(snap_ts TEXT,underlying TEXT,fut_ltp REAL,fut_oi INTEGER,pcr REAL,max_pain REAL,atm_iv REAL);")
    conn.execute("INSERT INTO fno_chain_oi VALUES('2026-08-01','NIFTY','2026-08-06',25000,'CE',100,10,50,NULL)")
    conn.commit(); conn.close()
    monkeypatch.setattr(settings,"RESEARCH_ARCHIVE_PATH",str(tmp_path/"archive"))
    monkeypatch.setattr(settings,"RESEARCH_RESERVED_FREE_BYTES",0)
    original=archive.export_operational_fno_evidence
    def export_and_update(*args,**kwargs):
        result=original(*args,**kwargs)
        conn=sqlite3.connect(source)
        conn.execute("UPDATE fno_chain_oi SET oi=999");conn.commit();conn.close()
        return result
    monkeypatch.setattr(archive,"export_operational_fno_evidence",export_and_update)
    await fno_oi_store.archive_then_purge_older_than(str(source),7,datetime(2026,9,8))
    conn=sqlite3.connect(source)
    try: assert conn.execute("SELECT oi FROM fno_chain_oi").fetchall()==[(999,)]
    finally: conn.close()


def test_shared_budget_covers_candidate_writes(tmp_path,monkeypatch):
    from config import settings
    monkeypatch.setattr(settings,"RESEARCH_SESSION_MAX_BYTES",300)
    with pytest.raises(OSError,match="budget"):
        archive.archive_candidate_evidence(str(tmp_path),advisory_id="test",candidate_payload={"large":"x"*500},validation_reasons=[],reserved_free_bytes=0)
    assert not list(tmp_path.glob("candidate-evidence/**/evidence.json"))
