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
# [TIER0-0.5] Below the dead-gate bar but still lopsided enough to name in the
# alert. Zero accepts + one reason taking most of the rejects is never "healthy",
# and reporting `dead_gate=none` made it read that way.
SUSPECT_GATE_DOMINANCE = 0.60

# Reasons whose *prefix* groups many distinct messages into one gate.
# reject_reason strings carry per-ticker numbers ("volume 1234 < ..."),
# so histogram on the stable prefix, not the raw string.
_REASON_PREFIXES = [
    "outside breakout time window",
    "volume",
    "breakout not confirmed",
    "no prior bars to anchor breakout",
    # [WATCHDOG-LABEL 2026-07-17] New stable-text-first labels (numbers
    # moved to a trailing parenthesis so the bucket names read cleanly in
    # the Telegram alarm, and the threshold vs dead-cat gates get separate
    # buckets). The old "RSI(N)=" formats stay below so rows written
    # before the change still histogram correctly in the 2-day window.
    "RSI(2) not below buy threshold",
    "RSI(2) below dead-cat floor",
    "RSI(14) overbought",
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

            # Dead gate: one reason dominates the rejects ACROSS THE WINDOW, and
            # is the top reason on every day in it.
            #
            # [TIER0-0.5 2026-07-14] This used to require the reason to clear
            # DEAD_GATE_DOMINANCE on EVERY day independently. That AND-across-days
            # rule is too brittle, and it failed on the real thing it was built to
            # catch. On 2026-07-14 the watchdog fired with `dead_gate=none` while
            # the penny book sat at 0 accepts in 349,297 lifetime evaluations:
            #
            #     2026-07-13   regime PR3_HOT = 68.6%   <- below the 90% bar
            #     2026-07-14   regime PR3_HOT = 96.0%
            #     window       regime PR3_HOT = 94.8%   <- obviously the dead gate
            #
            # One quieter day diluted the per-day test, so the alert went out
            # reading like a slow market instead of "your gate is broken". Judge
            # dominance over the WINDOW (which is the question being asked), and
            # keep a per-day check only that the same reason leads every day --
            # that is what actually rules out a one-day spike.
            total_rejects = sum(overall.values())
            dead_gate = None
            suspect_gate = None
            if top and total_rejects:
                candidate, candidate_count = top[0]
                window_share = candidate_count / total_rejects
                leads_every_day = all(
                    by_day[d]
                    and max(by_day[d], key=by_day[d].get) == candidate
                    for d in days
                )
                if leads_every_day:
                    if window_share >= DEAD_GATE_DOMINANCE:
                        dead_gate = candidate
                    elif window_share >= SUSPECT_GATE_DOMINANCE:
                        # Not conclusive, but 0 accepts with one reason taking
                        # most of the rejects is worth naming rather than
                        # reporting "dead_gate=none" and looking healthy.
                        suspect_gate = candidate

            return {
                "days": days,
                "evaluations": total_evals,
                "accepts": 0,
                "top_reasons": top_reasons,
                "dead_gate": dead_gate,
                "suspect_gate": suspect_gate,
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
            f"One gate rejects ≥{int(DEAD_GATE_DOMINANCE * 100)}% of all "
            f"rejects across the window and leads EVERY day: "
            f"`{payload['dead_gate']}`. "
            "This is the BUG-1 signature (unsatisfiable gate), not a "
            "quiet market."
        )
    elif payload.get("suspect_gate"):
        # [TIER0-0.5] Never report "no dominant gate" when one reason is taking
        # most of the rejects and nothing is being accepted. The old code went
        # quiet here, and that is how a 0-accept book read as a slow market.
        lines.append(
            f"No single gate clears the {int(DEAD_GATE_DOMINANCE * 100)}% "
            f"dead-gate bar, but `{payload['suspect_gate']}` leads every day "
            f"and takes most of the rejects. With 0 accepts, treat it as the "
            "prime suspect."
        )
    lines.append("Top reject reasons:")
    for reason, count, pct in payload.get("top_reasons", []):
        lines.append(f"  • {count} ({pct}%) — {reason}")
    lines.append(
        "Ground truth: /data/penny_signals.csv (ops rule 75). "
        "If the histogram never varies day-to-day, suspect a dead gate."
    )
    return "\n".join(lines)
