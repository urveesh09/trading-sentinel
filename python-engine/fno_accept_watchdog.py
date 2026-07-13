"""
[FNO-WATCHDOG 2026-07-10] Zero-accept alarm for the F&O subsystem
(spec §9.2). Sibling of penny_accept_watchdog (GAP-2), tuned for the
F&O reject taxonomy.

Fires when accepts == 0 across FNO_ZERO_ACCEPT_ALERT_DAYS consecutive
trading days while evaluations > 0 -- carrying the reject-reason
histogram. It MUST distinguish two cases (this is the whole reason the
§3 reject taxonomy earns its keep):

  - `pool_below_min_viable` dominating -> HEALTHY. The module is
    correctly declining expensive-premium days (the §3 volatility
    filter). Reported as a self-regulation note, severity=info.
  - a histogram that never varies / one reason at ~100% on every day
    regardless of market conditions -> a DEAD GATE. Alert loudly.

BUG-1 (penny) ran nine months at 215,814 evaluations / 0 accepts with
perfect breadcrumbs. At the default of 2 days this fires on day two.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

import aiosqlite
import structlog

from config import settings

logger = structlog.get_logger()

# Reject reasons that mean "the module declined for capital/vol reasons"
# rather than "a gate might be dead".
SELF_REGULATION_REASONS = {"pool_below_min_viable"}
DEAD_GATE_DOMINANCE = 0.95   # one reason >= 95% of rejects on every day


async def zero_accept_scan(
    db_path: str, n_days: Optional[int] = None,
) -> Optional[dict]:
    """Returns None when healthy (accepts in window, or not enough data).
    Otherwise a payload dict with days, evaluations, histogram, severity."""
    n_days = n_days or settings.FNO_ZERO_ACCEPT_ALERT_DAYS
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='fno_signals'"
            ) as cur:
                if await cur.fetchone() is None:
                    logger.info("fno_watchdog_db_unready reason=fno_signals_missing")
                    return None
            # Last n distinct bar-days with any evaluation.
            async with db.execute(
                "SELECT DISTINCT substr(bar_ts, 1, 10) AS d FROM fno_signals "
                "WHERE bar_ts != '' ORDER BY d DESC LIMIT ?",
                (n_days,),
            ) as cur:
                days = [r[0] for r in await cur.fetchall()]
            if len(days) < n_days:
                return None  # not enough history yet
            rows = []
            for d in days:
                async with db.execute(
                    "SELECT accepted, reject_reason FROM fno_signals "
                    "WHERE substr(bar_ts, 1, 10) = ?",
                    (d,),
                ) as cur:
                    rows.append((d, await cur.fetchall()))
    except Exception as exc:
        logger.error("fno_watchdog_query_failed err=%s", str(exc))
        return None

    total_evals = 0
    histogram: Counter = Counter()
    per_day_dominant = []
    for d, day_rows in rows:
        day_hist: Counter = Counter()
        for accepted, reason in day_rows:
            total_evals += 1
            if accepted:
                return None  # any accept in the window -> healthy
            if reason:
                day_hist[reason] += 1
                histogram[reason] += 1
        if day_hist:
            top_reason, top_n = day_hist.most_common(1)[0]
            per_day_dominant.append(
                (top_reason, top_n / sum(day_hist.values()))
            )
    if total_evals == 0:
        return None  # nothing evaluated (holiday-ish window); tick breadcrumbs own this

    # Classification (§9.2).
    top = histogram.most_common(1)[0] if histogram else ("", 0)
    self_regulating = top[0] in SELF_REGULATION_REASONS and (
        top[1] / max(1, sum(histogram.values()))
    ) >= 0.5
    dead_gate = ""
    if per_day_dominant and not self_regulating:
        first = per_day_dominant[0][0]
        if all(r == first and share >= DEAD_GATE_DOMINANCE for r, share in per_day_dominant):
            dead_gate = first

    return {
        "days": days,
        "evaluations": total_evals,
        "histogram": dict(histogram.most_common(8)),
        "self_regulating": self_regulating,
        "dead_gate": dead_gate,
    }


def format_zero_accept_alert(payload: dict) -> str:
    days = ", ".join(payload["days"])
    lines = []
    if payload.get("self_regulating"):
        lines.append("*F&O self-regulation note* (not an alarm)")
        lines.append(
            f"0 accepts across {days} with {payload['evaluations']} evaluations -- "
            "dominated by `pool_below_min_viable`: premium too rich for the "
            "pool. This is the §3 volatility filter working."
        )
    else:
        lines.append("*F&O ZERO-ACCEPT ALARM*")
        lines.append(
            f"0 accepts across {days} ({payload['evaluations']} evaluations)."
        )
        if payload.get("dead_gate"):
            lines.append(
                f"Suspected DEAD GATE: `{payload['dead_gate']}` is >=95% of "
                "rejects on every day in the window. A gate whose histogram "
                "never varies is broken, not unlucky (BUG-1 class)."
            )
    hist = payload.get("histogram", {})
    if hist:
        lines.append("Reject histogram: " + ", ".join(f"`{k}`x{v}" for k, v in hist.items()))
    return "\n".join(lines)
