"""Frozen F&O shadow ``FNO_SPREAD_TILT_V1``: the single option's risk budget spent on spread lots.

[O9 2026-10-09, owner-approved shadow] The paper book opens a naked option and
a debit spread on the same directional signal. Since Sep 1 the spread made
+₹4,756 over 15 trades (worst −₹851) and the naked options +₹3,080 over 14
(worst −₹3,228), yet every spread was one lot: the drawdown multiplier shrinks
it while the naked option keeps its own larger stop budget.

The variant asks, per signal where both were opened: what if the naked
option's max-loss budget had bought extra spread lots instead?

    extra lots = floor(naked max loss / spread max loss per lot)
    variant lots = min(actual spread lots + extra, FNO_DR_MAX_LOTS)
    variant net = spread net per lot x variant lots      (naked option dropped)

A signal with only one vehicle keeps its actual result. The spread's lifecycle
(target/stop/square-off) does not depend on lots, so scaling its realised net
per lot is exact except for flat brokerage, which this overcounts (the variant
is charged per-lot brokerage it would not pay); depth for up to three NIFTY
lots is assumed. It never trades, never sizes a live position and never
changes the real book. Scored only on signals from ``SCORING_FROM`` onward;
earlier pairs are shown separately as in-sample context.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Optional

from config import settings

VERSION = "FNO_SPREAD_TILT_V1"
SCORING_FROM = date(2026, 10, 12)     # first session after the rule was frozen
PAIR_WINDOW_SEC = 120.0               # naked and spread entries on the same tick


@dataclass(frozen=True)
class Single:
    id: int
    entry_time: datetime
    opt_type: str
    max_loss: float
    net: float


@dataclass(frozen=True)
class Spread:
    id: int
    opened_at: datetime
    long_opt_type: Optional[str]
    lots: int
    max_loss: float
    net: float


@dataclass(frozen=True)
class SignalOutcome:
    day: date
    single_id: Optional[int]
    spread_id: Optional[int]
    actual: float
    variant: float
    variant_lots: Optional[int]


def pair_and_score(singles: Iterable[Single], spreads: Iterable[Spread],
                   max_lots: int) -> list[SignalOutcome]:
    """Pure: pair each spread with the naked option opened on the same signal, then score."""
    pending = sorted(singles, key=lambda s: s.entry_time)
    outcomes: list[SignalOutcome] = []
    for spread in sorted(spreads, key=lambda s: s.opened_at):
        match = next((s for s in pending
                      if abs((s.entry_time - spread.opened_at).total_seconds()) <= PAIR_WINDOW_SEC
                      and (spread.long_opt_type is None or s.opt_type == spread.long_opt_type)), None)
        if match is None or spread.lots < 1 or spread.max_loss <= 0:
            outcomes.append(SignalOutcome(spread.opened_at.date(), None, spread.id,
                                          spread.net, spread.net, spread.lots or None))
            continue
        pending.remove(match)
        per_lot_loss, per_lot_net = spread.max_loss / spread.lots, spread.net / spread.lots
        extra = int(match.max_loss // per_lot_loss) if per_lot_loss > 0 else 0
        lots = max(spread.lots, min(spread.lots + extra, max_lots))
        outcomes.append(SignalOutcome(spread.opened_at.date(), match.id, spread.id,
                                      match.net + spread.net, per_lot_net * lots, lots))
    outcomes += [SignalOutcome(s.entry_time.date(), s.id, None, s.net, s.net, None) for s in pending]
    return sorted(outcomes, key=lambda o: (o.day, o.single_id or 0, o.spread_id or 0))


def _summary(outcomes: list[SignalOutcome]) -> dict:
    paired = [o for o in outcomes if o.single_id is not None and o.spread_id is not None]

    def worst(values):
        return round(min(values), 2) if values else None

    return {
        "signals": len(outcomes), "paired": len(paired),
        "actual_net": round(sum(o.actual for o in outcomes), 2),
        "variant_net": round(sum(o.variant for o in outcomes), 2),
        "paired_actual_net": round(sum(o.actual for o in paired), 2),
        "paired_variant_net": round(sum(o.variant for o in paired), 2),
        "paired_actual_worst": worst([o.actual for o in paired]),
        "paired_variant_worst": worst([o.variant for o in paired]),
    }


def _load(db_path: str, source: str) -> tuple[list[Single], list[Spread]]:
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5.0) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        singles, spreads = [], []
        if "fno_positions" in tables:
            for row in conn.execute(
                    "SELECT id, entry_time, opt_type, COALESCE(initial_max_loss_rupees, max_loss_rupees), pnl "
                    "FROM fno_positions WHERE source=? AND status='CLOSED' AND pnl IS NOT NULL", (source,)):
                singles.append(Single(int(row[0]), datetime.fromisoformat(row[1]), str(row[2]),
                                      float(row[3] or 0.0), float(row[4])))
        if "fno_dr_positions" in tables:
            for row in conn.execute(
                    "SELECT id, opened_at, legs_json, lots, max_loss_rs, COALESCE(cash_pnl, pnl) "
                    "FROM fno_dr_positions WHERE source=? AND kind='DEBIT_SPREAD' AND status='CLOSED' "
                    "AND COALESCE(cash_pnl, pnl) IS NOT NULL", (source,)):
                try:
                    longs = [leg["opt_type"] for leg in json.loads(row[2]) if float(leg["quantity"]) > 0]
                except (ValueError, TypeError, KeyError):
                    longs = []
                spreads.append(Spread(int(row[0]), datetime.fromisoformat(row[1]),
                                      longs[0] if len(set(longs)) == 1 else None,
                                      int(row[3] or 0), float(row[4] or 0.0), float(row[5])))
    return singles, spreads


def spread_tilt_report(db_path: Optional[str] = None, source: str = "FNO_PAPER") -> dict:
    """Read-only score of the frozen variant: forward (scored) and in-sample (context)."""
    singles, spreads = _load(db_path or settings.DB_PATH, source)
    outcomes = pair_and_score(singles, spreads, int(getattr(settings, "FNO_DR_MAX_LOTS", 3)))
    forward = [o for o in outcomes if o.day >= SCORING_FROM]
    seen = [o for o in outcomes if o.day < SCORING_FROM]
    return {"version": VERSION, "source": source, "scoring_from": SCORING_FROM.isoformat(),
            "forward": _summary(forward), "in_sample_context": _summary(seen),
            "forward_signals": [o.__dict__ | {"day": o.day.isoformat()} for o in forward],
            "can_place_orders": False}


def report_line(report: dict) -> str:
    """One line for the F&O hourly report."""
    f = report["forward"]
    if not f["paired"]:
        return f"Shadow {VERSION}: no paired signal since {report['scoring_from']} yet"
    return (f"Shadow {VERSION} (more spread lots instead of the naked option), since "
            f"{report['scoring_from']}: paired {f['paired']} | actual Rs {f['paired_actual_net']:+,.0f} "
            f"vs variant Rs {f['paired_variant_net']:+,.0f} | worst {f['paired_actual_worst']:+,.0f} "
            f"vs {f['paired_variant_worst']:+,.0f}")
