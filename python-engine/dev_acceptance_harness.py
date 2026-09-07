"""Controlled Dev acceptance harness; no external service or order path."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

from integrated_dev_demo import run_integrated_dev_demo


async def run_dev_acceptance_harness(output_dir: str) -> dict:
    """Exercise durable demo evidence plus a real optional-AI outage boundary.

    This is intentionally not a production scheduler/broker canary. It proves
    deterministic work completes while the optional worker's circuit opens.
    """
    # The worker is deliberately a standalone module in ``agent/`` rather
    # than a production dependency of the engine.  Keep this Dev-only bridge
    # explicit so the harness can run from the repository root or pytest.
    agent_dir = Path(__file__).resolve().parents[1] / "agent"
    if str(agent_dir) not in sys.path:
        sys.path.insert(0, str(agent_dir))
    from advisory import unavailable
    from async_reviews import AsyncReviewQueue

    root = Path(output_dir)
    demo = await run_integrated_dev_demo(str(root / "demo"))
    queue = AsyncReviewQueue(
        lambda *_args: unavailable("harness_outage"),
        failure_limit=1,
        cooldown_seconds=60,
        budget_state_path=str(root / "ai-budget.json"),
    )
    try:
        started = time.monotonic()
        expiry = datetime.now(timezone.utc) + timedelta(minutes=1)
        queued = queue.submit("harness:outage", {}, "", "UNKNOWN", expires_at=expiry)
        deadline = time.monotonic() + 1
        while (
            time.monotonic() < deadline
            and (queue.status("harness:outage") or queued).state not in {"UNAVAILABLE", "CIRCUIT_OPEN"}
        ):
            time.sleep(0.01)
        state = queue.status("harness:outage")
        elapsed = time.monotonic() - started
    finally:
        queue.shutdown()
    if demo.get("can_place_orders") is not False or state is None:
        raise RuntimeError("Dev acceptance safety contract failed")
    return {
        "mode": "DEV_HARNESS",
        "demo": demo,
        "ai_outage_state": state.state,
        "ai_elapsed_seconds": round(elapsed, 3),
        "scheduler": "NOT_STARTED_BY_DESIGN",
        "can_place_orders": False,
        "authorization_effect": "NONE",
    }
