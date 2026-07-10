"""
[GAP-2 ZERO-ACCEPT ALARM 2026-07-10] Accept-rate watchdog for the penny
subsystem, backported from the F&O module spec (docs/superpowers/specs/
fno-module.md §9.2).

Why this exists: production ran a mathematically unsatisfiable breakout
gate for nine months (215,814 evaluations, 0 accepts) and no health
check noticed, because every existing check asks "did the engine run?"
and none asks "does the engine ever say yes?". Rule-59's breadcrumb
tree classified every one of those days as "legit empty day".

The rule: if accepts == 0 across N consecutive evaluation days while
evaluations > 0, fire a Telegram alert carrying the top reject-reason
histogram. Per the spec, the alert must distinguish:

  - a histogram DOMINATED BY ONE REASON on every day regardless of
    market conditions -> a suspected DEAD GATE. Alert loudly.
  - a varied histogram -> could be a quiet market; alert once, calmly.

This module is read-only over the penny_signals table and follows the
same isolation rule as penny_signal_log: it MUST NOT import from
engine, regime, risk_engine, portfolio, or the evaluators. Failures
here must never break the trading loop -- every public function
catches and logs.

Public API:
  zero_accept_scan(db_path, n_days=..., leg=None) -> Optional[dict]
  format_zero_accept_alert(payload)               -> str
"""
import logging
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)

# A single reject reason covering at least this share of a day's rejects,
# on EVERY day in the window, marks a suspected dead gate (spec §9.2).
DEAD_GATE_DOMINANCE = 0.90

# Reasons whose *prefix* groups many distinct messages into one gate.
# reject_reason strings carry per-ticker numbers ("volume 1234 < ..."),
# so histogram on the stable prefix, not the raw string.
_REASON_PREFIXES = [
    "outside breakout time window",
    "volume",
    "breakout not confirmed",
    "no prior bars to anchor breakout",
    "RSI(14)=",
    "RSI(2)=",
    "RSI not rising",
    "non-positive risk",
    "regime PR3_HOT",
    "position size = 0",
    "insufficient history",
    "below 200 SMA",
    "below 50 SMA",
    "cumulative RSI(2)",
    "volume too low",
    "evaluator returned None",
]


def _normalise_reason(reason: str) -> str:
    """Collapse per-ticker numeric variation to a stable gate label."""
    r = (reason or "").strip()
    if not r:
        return "(empty)"
    for prefix in _REASON_PREFIXES:
        if r.startswith(prefix):
            return prefix
    return r[:60]


async def zero_accept_scan(
    db_path: str,
    *,
    n_days: int = 2,
    leg: Optional[str] = None,
) -> Optional[dict]:
    """Inspect the last `n_days` evaluation days in penny_signals.

    Returns None when healthy (any accept in the window, or not enough
    history to judge). Returns an alert payload dict when every one of
    the last `n_days` evaluation days had evaluations > 0 and 0 accepts:

      {
        "days":           ["2026-07-09", "2026-07-10"],
        "evaluations":    int,   # total across the window
        "accepts":        0,
        "top_reasons":    [(reason, count, pct), ...],  # max 5
        "dead_gate":      Optional[str],  # dominant reason, if any
        "per_day":        [{"day": d, "evals": n, "accepts": a}, ...],
        "leg":            leg or "ALL",
      }
    """
    leg_clause = "AND leg = ?" if leg else ""
    params: list = [leg] if leg else []
    try:
        async with aiosqlite.connect(db_path) as db:
            # [Rule 57 DB preflight] Verify the table exists; a fresh
            # container that has never scanned has nothing to audit.
            cur = await db.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='penny_signals'"
            )
            if await cur.fetchone() is None:
                logger.warning(
                    "penny_watchdog_db_unready reason=penny_signals_missing "
                    "FIX=table is created on first scan; nothing to audit yet"
                )
                return None

            # Last n_days DISTINCT evaluation days (days with >= 1 row).
            cur = await db.execute(
                f"""
                SELECT date(scanned_at) AS d,
                       COUNT(*)          AS evals,
                       SUM(accepted)     AS accepts
                FROM penny_signals
                WHERE 1=1 {leg_clause}
                GROUP BY d
                ORDER BY d DESC
                LIMIT ?
                """,
                params + [n_days],
            )
            rows = await cur.fetchall()
            if len(rows) < n_days:
                return None  # not enough history to judge
            if any((r[2] or 0) > 0 for r in rows):
                return None  # at least one accept in the window: healthy

            days = sorted(r[0] for r in rows)
            per_day = [
                {"day": r[0], "evals": int(r[1]), "accepts": int(r[2] or 0)}
                for r in sorted(rows, key=lambda r: r[0])
            ]
            total_evals = sum(int(r[1]) for r in rows)

            # Reject-reason histogram across the window, plus per-day
            # dominance for the dead-gate heuristic.
            cur = await db.execute(
                f"""
                SELECT date(scanned_at) AS d, reject_reason
                FROM penny_signals
                WHERE accepted = 0
                  AND date(scanned_at) >= ?
                  {leg_clause}
                """,
                [days[0]] + params,
            )
            overall: dict = {}
            by_day: dict = {d: {} for d in days}
            async for d, reason in cur:
                key = _normalise_reason(reason)
                overall[key] = overall.get(key, 0) + 1
                if d in by_day:
                    by_day[d][key] = by_day[d].get(key, 0) + 1

            top = sorted(overall.items(), key=lambda kv: -kv[1])[:5]
            top_reasons = [
                (k, v, round(100.0 * v / max(total_evals, 1), 1))
                for k, v in top
            ]

            # Dead gate: one reason >= DEAD_GATE_DOMINANCE share of the
            # rejects on EVERY day in the window.
            dead_gate = None
            if top:
                candidate = top[0][0]
                dominant_everywhere = all(
                    by_day[d]
                    and by_day[d].get(candidate, 0)
                    >= DEAD_GATE_DOMINANCE * sum(by_day[d].values())
                    for d in days
                )
                if dominant_everywhere:
                    dead_gate = candidate

            return {
                "days": days,
                "evaluations": total_evals,
                "accepts": 0,
                "top_reasons": top_reasons,
                "dead_gate": dead_gate,
                "per_day": per_day,
                "leg": leg or "ALL",
            }
    except Exception as e:
        # Watchdog failure must never break anything downstream; it is
        # itself observability, so it logs and steps aside.
        logger.error("penny_watchdog_scan_failed error=%s", str(e))
        return None


def format_zero_accept_alert(payload: dict) -> str:
    """Telegram-ready message for a zero-accept alert payload."""
    days = payload.get("days", [])
    header = (
        "🚨 **PENNY DEAD-GATE SUSPECTED** 🚨"
        if payload.get("dead_gate")
        else "⚠️ **Penny zero-accept alarm** ⚠️"
    )
    lines = [
        header,
        (
            f"{payload.get('evaluations', 0)} evaluations, 0 accepts "
            f"across {len(days)} consecutive day(s) "
            f"({days[0]} → {days[-1]}, leg={payload.get('leg', 'ALL')})."
        ),
    ]
    if payload.get("dead_gate"):
        lines.append(
            f"One gate rejects ≥{int(DEAD_GATE_DOMINANCE * 100)}% of "
            f"evaluations on EVERY day: `{payload['dead_gate']}`. "
            "This is the BUG-1 signature (unsatisfiable gate), not a "
            "quiet market."
        )
    lines.append("Top reject reasons:")
    for reason, count, pct in payload.get("top_reasons", []):
        lines.append(f"  • {count} ({pct}%) — {reason}")
    lines.append(
        "Ground truth: /data/penny_signals.csv (ops rule 75). "
        "If the histogram never varies day-to-day, suspect a dead gate."
    )
    return "\n".join(lines)
