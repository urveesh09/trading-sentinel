"""Actionable, read-only health diagnoses for the proactive funnel."""
from __future__ import annotations

from datetime import datetime

from proactive_intelligence import proactive_activity_report, proactive_inactivity_diagnostics, proactive_session_diagnostics


async def proactive_owner_diagnostics(db_path: str, *, now: datetime) -> dict:
    """Keep distinct causes distinct; no finding alters risk or execution."""
    findings=list(await proactive_inactivity_diagnostics(db_path,now=now))
    activity=await proactive_activity_report(db_path,now=now)
    for row in activity.get("market_data",{}).get("latest",[]):
        if row.get("state") in {"STALE","UNAVAILABLE"}:
            findings.append({"code":"MARKET_DATA_STALE_OR_UNAVAILABLE","account_id":row.get("account_id"),"reason":row.get("reason")})
    sessions=await proactive_session_diagnostics(db_path,now=now,session_count=2)
    for report in sessions.get("reports",[]):
        activity_row=report.get("activity",{})
        deferred=activity_row.get("stages",{}).get("DEFERRED",0)
        if deferred:
            findings.append({"code":"CAPITAL_OR_RISK_DEFERRAL","scope":report.get("scope"),"deferred":deferred,"reasons":activity_row.get("reasons",{})})
        if report.get("scan_health",{}).get("missing_sessions",0):
            findings.append({"code":"MISSED_SCHEDULED_SCAN","scope":report.get("scope")})
    return {"mode":"OBSERVATION_ONLY","as_of":now.isoformat(),"findings":findings,"can_place_orders":False,"authorization_effect":"NONE"}
