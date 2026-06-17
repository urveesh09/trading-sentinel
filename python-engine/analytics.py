"""
[ANALYTICS 2026-06-16] Self-improving analytics layer for Trading Sentinel.

Three things this module does, all from the data we already persist:

1. Gate-funnel report — counts which MC-gate rejection reasons kill the most
   signals. The first place to look when "I'm getting too few / too many
   signals" or "entries aren't great" is this.

2. Outcome correlator — joins closed trades (from positions + bankroll_ledger)
   with their original signal-log row (from momentum_signals) to compute
   "what was the gate fingerprint of trades that won vs lost." Reveals which
   gates actually predict success.

3. Strategy suggestions — turns (1) + (2) into 3-5 actionable changes the
   operator can A/B. Always returns the reasoning + the data backing it, so
   nothing is a black-box recommendation.

Public API (all async, all take db_path):
  init_analytics_db(db_path)                          — idempotent
  record_trade_outcome(db_path, ticker, pnl, r_mult)   — wired in main.py on close
  gate_funnel_report(db_path, days)                    -> dict
  outcome_correlator(db_path, days)                    -> dict
  strategy_suggestions(db_path, days)                  -> dict

CLI: `python -m analytics --days 14`  (prints a human report)

Design rules:
- All writes are best-effort. An analytics failure must NOT break live trading.
- No new third-party deps. SQLite + stdlib only.
- Schemas are forward-compatible: only ADD columns/tables, never rename.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiosqlite
import structlog

from config import settings

logger = structlog.get_logger()


# ────────────────────────────────────────────────────────────────────
# Schema
# ────────────────────────────────────────────────────────────────────

# trade_outcomes: one row per CLOSED momentum trade. Joins closed position
# with the signal-log row that produced it (so we can correlate gate state
# with realized P&L).
CREATE_TRADE_OUTCOMES_SQL = """
CREATE TABLE IF NOT EXISTS trade_outcomes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT    NOT NULL,
    closed_at       TEXT    NOT NULL,
    realised_pnl    REAL    NOT NULL,
    r_multiple      REAL,
    scan_id         TEXT,
    regime          TEXT,
    close           REAL,
    stop_loss       REAL,
    target_1        REAL,
    volume_ratio    REAL,
    rvol_ratio      REAL,
    rsi_7           REAL,
    minutes_from_open INTEGER,
    strategy_version TEXT,
    notes           TEXT,
    UNIQUE(ticker, closed_at)
);
CREATE INDEX IF NOT EXISTS idx_outcomes_closed_at ON trade_outcomes(closed_at);
CREATE INDEX IF NOT EXISTS idx_outcomes_ticker     ON trade_outcomes(ticker);
CREATE INDEX IF NOT EXISTS idx_outcomes_regime     ON trade_outcomes(regime);
"""


async def init_analytics_db(db_path: str) -> None:
    """Idempotent. Call from main.py startup alongside init_positions_db."""
    try:
        async with aiosqlite.connect(db_path) as db:
            for stmt in CREATE_TRADE_OUTCOMES_SQL.split(";"):
                s = stmt.strip()
                if s:
                    await db.execute(s)
            await db.commit()
    except Exception as e:
        logger.error("analytics_init_failed", error=str(e))


# ────────────────────────────────────────────────────────────────────
# 1. Record a trade outcome (called from main.py on position close)
# ────────────────────────────────────────────────────────────────────

async def record_trade_outcome(
    db_path: str,
    ticker: str,
    realised_pnl: float,
    r_multiple: Optional[float] = None,
    notes: Optional[str] = None,
) -> Optional[str]:
    """Record a closed trade + join with the latest signal-log row for that ticker.

    Returns the scan_id of the matched signal-log row, or None if no match.
    Idempotent on (ticker, closed_at) — re-recording the same close is a no-op.
    """
    # Idempotent — safe to call on every close
    try:
        await init_analytics_db(db_path)
    except Exception:
        pass
    try:
        closed_at = datetime.now(timezone.utc).isoformat()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            try:
                cur = await db.execute(
                    """SELECT scan_id, regime, close, stop_loss, target_1,
                              volume_ratio, rvol_ratio, rsi_7, minutes_from_open,
                              strategy_version
                       FROM momentum_signals
                       WHERE ticker = ? AND accepted = 1 AND scanned_at >= ?
                       ORDER BY scanned_at DESC LIMIT 1""",
                    (ticker, cutoff),
                )
                row = await cur.fetchone()
            except aiosqlite.OperationalError:
                # Table doesn't exist yet — log a minimal outcome
                await db.execute(
                    """INSERT OR IGNORE INTO trade_outcomes
                       (ticker, closed_at, realised_pnl, r_multiple, notes)
                       VALUES (?, ?, ?, ?, ?)""",
                    (ticker, closed_at, realised_pnl, r_multiple,
                     notes or "no_signal_log_table"),
                )
                await db.commit()
                return None
            if not row:
                # No matched signal — log a minimal outcome so we still have the P&L
                await db.execute(
                    """INSERT OR IGNORE INTO trade_outcomes
                       (ticker, closed_at, realised_pnl, r_multiple, notes)
                       VALUES (?, ?, ?, ?, ?)""",
                    (ticker, closed_at, realised_pnl, r_multiple,
                     notes or "no_matched_signal"),
                )
                await db.commit()
                return None
            await db.execute(
                """INSERT OR IGNORE INTO trade_outcomes
                   (ticker, closed_at, realised_pnl, r_multiple, scan_id, regime,
                    close, stop_loss, target_1, volume_ratio, rvol_ratio, rsi_7,
                    minutes_from_open, strategy_version, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (ticker, closed_at, realised_pnl, r_multiple, row["scan_id"],
                 row["regime"], row["close"], row["stop_loss"], row["target_1"],
                 row["volume_ratio"], row["rvol_ratio"], row["rsi_7"],
                 row["minutes_from_open"], row["strategy_version"], notes),
            )
            await db.commit()
            return row["scan_id"]
    except Exception as e:
        logger.error("record_outcome_failed", ticker=ticker, error=str(e))
        return None


# ────────────────────────────────────────────────────────────────────
# 2. Gate-funnel report
# ────────────────────────────────────────────────────────────────────

async def gate_funnel_report(db_path: str, days: int = 7) -> dict:
    """Count rejections by reason over the last `days`.

    Returns:
      {
        "days": N,
        "scanned_total": int,
        "accepted": int,
        "rejected": int,
        "rejection_rate": float,    # 0..1
        "by_reason": [
            {"reason": "MC3_volume_surge_insufficient", "count": N, "pct": 0.32},
            ...
        ],
        "as_of": iso8601,
      }
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        async with aiosqlite.connect(db_path) as db:
            try:
                cur = await db.execute(
                    """SELECT
                           SUM(CASE WHEN accepted=1 THEN 1 ELSE 0 END) AS acc,
                           SUM(CASE WHEN accepted=0 THEN 1 ELSE 0 END) AS rej,
                           COUNT(*) AS total
                       FROM momentum_signals
                       WHERE scanned_at >= ?""",
                    (cutoff,),
                )
                r = await cur.fetchone()
            except aiosqlite.OperationalError:
                # Table doesn't exist yet — fresh DB. Return empty funnel.
                return {
                    "days": days, "scanned_total": 0, "accepted": 0,
                    "rejected": 0, "rejection_rate": 0.0,
                    "by_reason": [], "as_of": datetime.now(timezone.utc).isoformat(),
                }
            accepted = r[0] or 0
            rejected = r[1] or 0
            total    = r[2] or 0

            cur = await db.execute(
                """SELECT reject_reason, COUNT(*) AS n
                   FROM momentum_signals
                   WHERE scanned_at >= ? AND accepted = 0 AND reject_reason != ''
                   GROUP BY reject_reason
                   ORDER BY n DESC""",
                (cutoff,),
            )
            rows = await cur.fetchall()
        by_reason = [
            {"reason": r[0] or "(empty)", "count": r[1],
             "pct": round(r[1] / rejected, 4) if rejected else 0.0}
            for r in rows
        ]
        return {
            "days": days,
            "scanned_total": total,
            "accepted": accepted,
            "rejected": rejected,
            "rejection_rate": round(rejected / total, 4) if total else 0.0,
            "by_reason": by_reason,
            "as_of": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("funnel_report_failed", error=str(e))
        return {"days": days, "error": str(e), "by_reason": []}


# ────────────────────────────────────────────────────────────────────
# 3. Outcome correlator
# ────────────────────────────────────────────────────────────────────

async def outcome_correlator(db_path: str, days: int = 14) -> dict:
    """Correlate gate fingerprint with realized P&L.

    Splits closed trades into winners (r > 0) and losers (r <= 0) and computes
    the average value of each gate-state field for each group. Reveals which
    gates are actually predictive vs just decorative.

    Returns:
      {
        "days": N,
        "n_trades": int,
        "n_winners": int, "n_losers": int,
        "win_rate": float,
        "avg_r": float, "avg_r_winners": float, "avg_r_losers": float,
        "by_regime": [
          {"regime": "REGIME_1_NORMAL", "trades": N, "win_rate": 0.6, "avg_r": 0.8},
          ...
        ],
        "winners_avg": { field: value, ... },
        "losers_avg":  { field: value, ... },
        "predictive_gates": [ "volume_ratio", ... ],   # gates where diff > 20%
      }
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    FIELDS = ["volume_ratio", "rvol_ratio", "rsi_7", "minutes_from_open", "close"]
    try:
        async with aiosqlite.connect(db_path) as db:
            cur = await db.execute(
                f"""SELECT realised_pnl, r_multiple, regime, {", ".join(FIELDS)}
                    FROM trade_outcomes
                    WHERE closed_at >= ? AND r_multiple IS NOT NULL""",
                (cutoff,),
            )
            rows = await cur.fetchall()
        if not rows:
            return {"days": days, "n_trades": 0, "predictive_gates": []}

        winners = [r for r in rows if (r[1] or 0) > 0]
        losers  = [r for r in rows if (r[1] or 0) <= 0]
        n = len(rows)
        nw = len(winners)
        nl = len(losers)
        avg_r  = sum((r[1] or 0) for r in rows) / n
        avg_rw = sum((r[1] or 0) for r in winners) / nw if nw else 0.0
        avg_rl = sum((r[1] or 0) for r in losers)  / nl if nl else 0.0

        def _avg(idx: int, group: list) -> Optional[float]:
            vals = [r[idx] for r in group if r[idx] is not None]
            return round(sum(vals) / len(vals), 3) if vals else None

        winners_avg = {f: _avg(3 + i, winners) for i, f in enumerate(FIELDS)}
        losers_avg  = {f: _avg(3 + i, losers)  for i, f in enumerate(FIELDS)}

        # Predictive = at least 20% relative difference between winner and loser avg
        predictive = []
        for f in FIELDS:
            w, l = winners_avg[f], losers_avg[f]
            if w is None or l is None:
                continue
            denom = max(abs(w), abs(l), 1e-9)
            if abs(w - l) / denom > 0.20:
                predictive.append(f)

        # By regime breakdown
        by_regime_map: dict = {}
        for r in rows:
            reg = r[2] or "UNKNOWN"
            by_regime_map.setdefault(reg, []).append(r)
        by_regime = []
        for reg, g in sorted(by_regime_map.items()):
            n_reg = len(g)
            wins_reg = sum(1 for x in g if (x[1] or 0) > 0)
            avg_r_reg = sum((x[1] or 0) for x in g) / n_reg
            by_regime.append({
                "regime": reg,
                "trades": n_reg,
                "win_rate": round(wins_reg / n_reg, 4),
                "avg_r": round(avg_r_reg, 3),
            })

        return {
            "days": days,
            "n_trades": n,
            "n_winners": nw, "n_losers": nl,
            "win_rate": round(nw / n, 4) if n else 0.0,
            "avg_r": round(avg_r, 3),
            "avg_r_winners": round(avg_rw, 3),
            "avg_r_losers": round(avg_rl, 3),
            "by_regime": by_regime,
            "winners_avg": winners_avg,
            "losers_avg":  losers_avg,
            "predictive_gates": predictive,
        }
    except Exception as e:
        logger.error("outcome_correlator_failed", error=str(e))
        return {"days": days, "n_trades": 0, "predictive_gates": [], "error": str(e)}


# ────────────────────────────────────────────────────────────────────
# 4. Strategy suggestions
# ────────────────────────────────────────────────────────────────────

async def strategy_suggestions(db_path: str, days: int = 14) -> dict:
    """Reads funnel + outcomes, returns 3-5 actionable suggestions.

    Each suggestion includes:
      - headline (1 line)
      - evidence (the data that triggered it)
      - action (what to flip in config)
      - confidence ("high" if n >= 20 trades, "medium" if 5-20, "low" if < 5)

    Rules (in priority order):
      1. If 1 reason accounts for >40% of rejections AND n_trades >= 10:
         "Reason X is your bottleneck. Consider relaxing it."
      2. If predictive_gates is non-empty AND n_trades >= 10:
         "Gates A, B differ between winners and losers by >20%. Consider
          tighter threshold on the side that's worse for winners."
      3. If win_rate < 0.40 AND n_trades >= 10:
         "Win rate below 40% — consider raising the entry bar (require more
          gates to pass, e.g. enable MC7 RVOL)."
      4. If avg_r_losers < -1.5R:
         "Losers exceed -1.5R avg — consider tighter stop or position sizing."
      5. If by_regime shows R1 winning >60% AND R2/R3 < 40%:
         "R1 is your edge. Consider disabling R2 entries until you have more
          R2 data."
    """
    funnel   = await gate_funnel_report(db_path, days=days)
    outcomes = await outcome_correlator(db_path, days=days)
    n_trades = outcomes.get("n_trades", 0)
    confidence = "high" if n_trades >= 20 else "medium" if n_trades >= 5 else "low"

    suggestions = []

    # Rule 1: dominant rejection reason
    by_reason = funnel.get("by_reason", [])
    if by_reason and funnel.get("rejected", 0) >= 10:
        top = by_reason[0]
        if top["pct"] > 0.40:
            suggestions.append({
                "headline":  f"'{top['reason']}' kills {top['pct']*100:.0f}% of signals",
                "evidence":  f"{top['count']} of {funnel['rejected']} rejections in last {days} days",
                "action":    f"Consider relaxing the {top['reason']} gate (lower threshold or extend window)",
                "confidence": confidence,
                "rule":      "dominant_rejection",
            })

    # Rule 2: predictive gates
    pred = outcomes.get("predictive_gates", [])
    if pred and n_trades >= 10:
        for g in pred:
            w = outcomes["winners_avg"].get(g)
            l = outcomes["losers_avg"].get(g)
            if w is None or l is None:
                continue
            if w > l:
                suggestions.append({
                    "headline":  f"Winners have higher {g} ({w}) than losers ({l})",
                    "evidence":  f"{g} avg differs by {abs(w-l):.2f} between winner/loser cohorts",
                    "action":    f"Consider raising the {g} floor (require higher value to pass)",
                    "confidence": confidence,
                    "rule":      "predictive_gate_higher_for_winners",
                })
            else:
                suggestions.append({
                    "headline":  f"Winners have lower {g} ({w}) than losers ({l})",
                    "evidence":  f"{g} avg differs by {abs(w-l):.2f} between winner/loser cohorts",
                    "action":    f"Consider lowering the {g} threshold (accept more in this range)",
                    "confidence": confidence,
                    "rule":      "predictive_gate_lower_for_winners",
                })

    # Rule 3: low win rate
    win_rate = outcomes.get("win_rate", 0.0)
    if win_rate < 0.40 and n_trades >= 10:
        suggestions.append({
            "headline":  f"Win rate is {win_rate*100:.0f}% (target ≥ 40%)",
            "evidence":  f"{outcomes.get('n_winners', 0)} wins / {n_trades} trades in last {days} days",
            "action":    "Tighten the entry bar — enable MOMENTUM_USE_RVOL=True (MC7) to filter further",
            "confidence": confidence,
            "rule":      "low_win_rate",
        })

    # Rule 4: oversized losers
    avg_rl = outcomes.get("avg_r_losers", 0.0)
    if avg_rl is not None and avg_rl < -1.5:
        suggestions.append({
            "headline":  f"Average losing trade is {avg_rl:.2f}R (target ≥ -1.0R)",
            "evidence":  f"avg_r_losers={avg_rl:.2f} from {outcomes.get('n_losers', 0)} losing trades",
            "action":    "Tighten stop-loss or reduce position size; check MOMENTUM_ATR_FUEL_BUFFER",
            "confidence": confidence,
            "rule":      "oversized_losers",
        })

    # Rule 5: regime divergence
    for r in outcomes.get("by_regime", []):
        reg = r["regime"]
        wr  = r["win_rate"]
        n   = r["trades"]
        if reg == "REGIME_1_NORMAL" and wr > 0.60 and n >= 5:
            for r2 in outcomes.get("by_regime", []):
                if r2["regime"] != reg and r2["win_rate"] < 0.40 and r2["trades"] >= 5:
                    suggestions.append({
                        "headline":  f"{reg} wins {wr*100:.0f}% but {r2['regime']} wins {r2['win_rate']*100:.0f}%",
                        "evidence":  f"R1: {r['trades']} trades, R2/3: {r2['trades']} trades",
                        "action":    f"Consider disabling {r2['regime']} entries until more data confirms edge",
                        "confidence": confidence,
                        "rule":      "regime_divergence",
                    })

    # Always include an "insufficient data" hint when n is tiny
    if n_trades < 5:
        suggestions.append({
            "headline":  f"Only {n_trades} closed trades in last {days} days",
            "evidence":  "Sample size too small for reliable suggestions",
            "action":    "Keep logging. Re-run analytics in 7-14 days.",
            "confidence": "low",
            "rule":      "insufficient_data",
        })

    return {
        "days": days,
        "n_trades": n_trades,
        "confidence": confidence,
        "funnel_summary": {
            "scanned_total": funnel.get("scanned_total", 0),
            "accepted": funnel.get("accepted", 0),
            "rejected": funnel.get("rejected", 0),
            "rejection_rate": funnel.get("rejection_rate", 0.0),
        },
        "outcome_summary": {
            "win_rate": win_rate,
            "avg_r": outcomes.get("avg_r", 0.0),
            "avg_r_winners": outcomes.get("avg_r_winners", 0.0),
            "avg_r_losers": avg_rl,
        },
        "suggestions": suggestions,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


# ────────────────────────────────────────────────────────────────────
# 5. Human report (CLI)
# ────────────────────────────────────────────────────────────────────

def _bar(label: str, count: int, max_count: int, width: int = 40) -> str:
    if max_count <= 0:
        return f"  {label}: (no data)"
    filled = int(width * count / max_count)
    return f"  {label:<42} {'█' * filled:<{width}} {count}"


async def print_report(db_path: str, days: int = 14) -> None:
    funnel   = await gate_funnel_report(db_path, days=days)
    outcomes = await outcome_correlator(db_path, days=days)
    sugg     = await strategy_suggestions(db_path, days=days)

    print("=" * 70)
    print(f"  TRADING SENTINEL — ANALYTICS REPORT (last {days} days)")
    print(f"  As of: {sugg.get('as_of', '?')}")
    print("=" * 70)
    print()
    print("[1] GATE FUNNEL")
    print(f"    Scanned:   {funnel.get('scanned_total', 0)}")
    print(f"    Accepted:  {funnel.get('accepted', 0)}")
    print(f"    Rejected:  {funnel.get('rejected', 0)} "
          f"({funnel.get('rejection_rate', 0)*100:.1f}%)")
    by_reason = funnel.get("by_reason", [])
    if by_reason:
        max_n = by_reason[0]["count"]
        print("    Top rejection reasons:")
        for r in by_reason[:8]:
            print(_bar(r["reason"], r["count"], max_n))
    else:
        print("    (no rejections logged)")

    print()
    print("[2] OUTCOME CORRELATION")
    nt = outcomes.get("n_trades", 0)
    if nt == 0:
        print("    No closed trades in this window. Run the system a few more days.")
    else:
        print(f"    Trades:    {nt}  "
              f"({outcomes.get('n_winners', 0)}W / {outcomes.get('n_losers', 0)}L)")
        print(f"    Win rate:  {outcomes.get('win_rate', 0)*100:.1f}%")
        print(f"    Avg R:     {outcomes.get('avg_r', 0):.3f}  "
              f"(W: {outcomes.get('avg_r_winners', 0):.3f}, "
              f"L: {outcomes.get('avg_r_losers', 0):.3f})")
        pred = outcomes.get("predictive_gates", [])
        if pred:
            print(f"    Predictive gates: {', '.join(pred)}")
        else:
            print("    Predictive gates: (none — no field differs >20% between W/L)")
        br = outcomes.get("by_regime", [])
        if br:
            print("    By regime:")
            for r in br:
                print(f"      {r['regime']:<25} n={r['trades']:<3} "
                      f"win={r['win_rate']*100:.0f}%  avg_r={r['avg_r']:.2f}")

    print()
    print("[3] SUGGESTIONS")
    suggestions = sugg.get("suggestions", [])
    if not suggestions:
        print("    No suggestions (insufficient data or no issues detected).")
    else:
        for i, s in enumerate(suggestions, 1):
            print(f"    {i}. [{s['confidence'].upper()}] {s['headline']}")
            print(f"       Evidence: {s['evidence']}")
            print(f"       Action:   {s['action']}")
            print()

    print("=" * 70)


# ────────────────────────────────────────────────────────────────────
# CLI entry: python -m analytics --days 14
# ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Trading Sentinel analytics")
    parser.add_argument("--days", type=int, default=14, help="Lookback window in days")
    parser.add_argument("--db", type=str, default=None, help="Override DB path")
    args = parser.parse_args()

    db = args.db or settings.DB_PATH
    asyncio.run(print_report(db, days=args.days))
