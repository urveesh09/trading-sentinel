"""Read-only audit probe. Run inside the engine as quantuser; no credentials emitted."""
import collections
import json
import pathlib
import sqlite3
import urllib.request
from datetime import date, datetime, timezone
from config import settings
from partner_collection_attempts import PartnerCollectionAttemptStore

out = {"observed_at": datetime.now(timezone.utc).isoformat()}
out["health"] = json.load(urllib.request.urlopen("http://localhost:8000/health", timeout=10))
keys = ["INITIAL_BANKROLL", "MOMENTUM_POOL_PCT", "RISK_PCT", "MAX_TOTAL_RISK_PCT",
        "MOMENTUM_RISK_PCT_R1", "MOMENTUM_RISK_PCT_R2", "MOMENTUM_RISK_PCT_R3",
        "FNO_LIVE_TRADING", "FNO_DISABLE_LIVE", "PENNY_LIVE_TRADING", "PENNY_EDGE_DISABLE_LIVE",
        "PARTNER_BOT_ENABLED", "PARTNER_MANUAL_ADVISORY_ENABLED", "PARTNER_MANUAL_ADVISORY_SHADOW_ENABLED",
        "PARTNER_MANUAL_ADVISORY_DELIVERY_ENABLED", "PARTNER_HEDGE_ENABLED",
        "PARTNER_HEDGE_INPUT_REFRESH_ENABLED", "PARTNER_HEDGE_PHASE2_ENABLED", "PARTNER_HEDGE_PHASE3_ENABLED",
        "PROACTIVE_SHADOW_ENABLED", "PROACTIVE_SHADOW_DATA_SOURCE", "PROACTIVE_SHADOW_FIXTURE_PATH",
        "PROACTIVE_SHADOW_ACCOUNT_ID", "CAS_PHASE1_FNO_UNDERLYINGS", "CAPITAL_POLICY_LOSS_TOLERANCE_PCT"]
out["settings"] = {k: getattr(settings, k, "NOT_A_SETTING") for k in keys}
c = sqlite3.connect("file:" + settings.DB_PATH + "?mode=ro", uri=True)
c.row_factory = sqlite3.Row
c.execute("PRAGMA query_only=ON")
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
out["table_counts"] = {t: c.execute('SELECT COUNT(*) FROM "'+t+'"').fetchone()[0] for t in tables
                       if t.startswith(("partner_", "proactive_", "broker_", "optional_ai_"))}
out["latest"] = {}
for t in ["partner_advisory_profiles", "partner_advisory_input_status", "proactive_scan_runs", "optional_ai_status_reports"]:
    if t in tables:
        out["latest"][t] = [dict(r) for r in c.execute('SELECT * FROM "'+t+'" ORDER BY rowid DESC LIMIT 2')]
out["scheduler"] = [dict(r) for r in c.execute("""SELECT substr(created_at,1,10) day, job_id,event_kind,
    count(*) n, round(avg(elapsed_seconds),3) mean_seconds,round(max(elapsed_seconds),3) max_seconds
    FROM scheduler_run_telemetry GROUP BY day,job_id,event_kind ORDER BY day,job_id""")]
root = pathlib.Path("/data/research")
out["archives"] = {}
for sub in sorted(root.iterdir()):
    if sub.is_dir():
        files = [p for p in sub.rglob("*") if p.is_file()]
        out["archives"][sub.name] = {"files":len(files), "bytes":sum(p.stat().st_size for p in files),
            "dates":dict(collections.Counter(next((x for x in p.parts if len(x)==10 and x.startswith("2026-")), "other") for p in files))}
out["collection_reasons"] = {}
for p in sorted((root/"collection-runs").glob("*/runs.jsonl")):
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    out["collection_reasons"][p.parent.name] = dict(collections.Counter(str(r["result"].get("reason",r["result"].get("status","other"))) for r in rows))
out["session_completeness"] = [PartnerCollectionAttemptStore(root).session_readiness(
    session_date=date.fromisoformat(d), now=datetime.now(timezone.utc), underlyings=["NIFTY","SENSEX"],
    entry_start_minute=585,entry_end_minute=885) for d in ["2026-09-15","2026-09-16","2026-09-17","2026-09-18"]]
print(json.dumps(out,indent=2,default=str))
