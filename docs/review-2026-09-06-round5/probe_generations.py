"""Offline generation-safety probes for 7b19ffc. No network calls."""
import asyncio
import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python-engine"))
import hedge_advisory as ha
import pytz

NOW = pytz.timezone("Asia/Kolkata").localize(datetime(2026, 9, 4, 11))


async def run():
    output = {}
    with tempfile.TemporaryDirectory(prefix="hedge-round5-") as folder:
        db = str(Path(folder) / "probe.db")
        await ha.init_hedge_advisory_db(db)
        for name, state in (("inflight", "transport_started"), ("rate_limit", "rate_limited")):
            detail = {"decision_id": name, "valid_until": (NOW + timedelta(minutes=5)).isoformat()}
            token = await ha._claim(db, "probe", name + ":g1", now=NOW, detail=detail)
            await ha._mark_transport_started(db, "probe", name + ":g1", token, now=NOW)
            if state == "rate_limited":
                await ha._fail_claim(db, "probe", name + ":g1", token, now=NOW,
                    detail={**detail, "delivery": {"state": state, "error": "telegram_429_retry_after_3600"}})
            second = await ha._claim(db, "probe", name + ":g2", now=NOW + timedelta(seconds=1), detail=detail)
            output[name + "_allows_second_generation"] = bool(second)

        detail = {"decision_id": "manual", "state": "manual_recovery_required"}
        await ha._record(db, "probe", "manual:g1", False, now=NOW, detail=detail)
        output["persisted_manual_blocks_second_generation"] = (await ha._claim(
            db, "probe", "manual:g2", now=NOW, detail={"decision_id": "manual"})) is None

        await ha._claim(db, "probe", "expired:g1", now=NOW,
            detail={"decision_id": "expired", "valid_until": (NOW - timedelta(seconds=1)).isoformat()})
        output["expired_generation_allows_fresh_generation"] = bool(await ha._claim(
            db, "probe", "expired:g2", now=NOW,
            detail={"decision_id": "expired", "valid_until": (NOW + timedelta(minutes=5)).isoformat()}))

        output["explicit_absence"] = await ha._whole_portfolio_input_reason(db, (), (), NOW, snapshot=None)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    asyncio.run(run())
