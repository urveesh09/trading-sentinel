"""Frozen F&O shadow ``FNO_SPREAD_TILT_V1``: the single option's risk budget spent on spread lots.

[O9 2026-10-09, owner-approved shadow] The paper book opens a naked option and
a debit spread on the same directional signal. Since Sep 1 the spread made
+₹4,756 over 15 trades (worst −₹851) and the naked options +₹3,080 over 14
(worst −₹3,228), yet every spread was one lot: the drawdown multiplier shrinks
it while the naked option keeps its own larger stop budget.

The variant asks, per signal where both were opened: what if the naked
option's max-loss budget had bought extra spread lots instead?

    extra lots = floor(naked max loss / spread max loss per lot)
    variant lots = min(actual spread lots + extra, MANIFEST["max_lots"])
    variant net = spread net per lot x variant lots      (naked option dropped)

A signal with only one vehicle keeps its actual result. The spread's lifecycle
(target/stop/square-off) does not depend on lots, so scaling its realised net
per lot is exact except for flat brokerage, which this overcounts (the variant
is charged per-lot brokerage it would not pay); depth for up to three NIFTY
lots is assumed. It never trades, never sizes a live position and never
changes the real book. Scored only on signals from ``SCORING_FROM`` onward;
earlier pairs are shown separately as in-sample context.

[O12-T1/T2 2026-10-12] Pairing and freeze hardened before the first forward
pair (the forward sample was still 0, so no score changes):

* a pair needs the same underlying, the same option type, the same expiry
  when both sides record one, and entries within ``PAIR_WINDOW_SEC``; the
  nearest entry wins. A spread whose long type or contract identity is
  ambiguous is UNAVAILABLE with a reason, never a wildcard. Spread rows
  written before contract binding carry no identity; the defined-risk book
  has only ever traded NIFTY, so they are read as NIFTY with an unknown
  expiry (``identity: "legacy"``).
* the terms are frozen in ``MANIFEST`` (lot cap included) and the report
  carries their fingerprint; the runtime ``FNO_DR_MAX_LOTS`` is shown only
  for comparison and no longer changes the score.
* OPEN rows are paired too: a signal with an open side is OPEN (no net yet)
  instead of leaving its closed side "unpaired".
* the summary adds a chronological max drawdown (by the time each signal's
  last side closed) for the owner's 20-pair review.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Optional

from config import settings

VERSION = "FNO_SPREAD_TILT_V1"
SCORING_FROM = date(2026, 10, 12)     # first session after the rule was frozen
PAIR_WINDOW_SEC = 120.0               # naked and spread entries on the same tick
LEGACY_SPREAD_UNDERLYING = "NIFTY"    # the defined-risk book's only underlying so far
MANIFEST = {
    "version": VERSION,
    "scoring_from": SCORING_FROM.isoformat(),
    "max_lots": 3,
    "pair_window_sec": PAIR_WINDOW_SEC,
    "pair_identity": "underlying+opt_type+expiry_when_known+nearest_entry",
    "variant": "spread_net_per_lot x min(spread_lots + floor(naked_max_loss / spread_max_loss_per_lot), max_lots)",
    "spread_net": "cash_pnl, else pnl",
    "single_max_loss": "initial_max_loss_rupees, else max_loss_rupees",
}
MANIFEST_FINGERPRINT = hashlib.sha256(json.dumps(MANIFEST, sort_keys=True).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Single:
    id: int
    entry_time: datetime
    opt_type: str
    max_loss: float
    net: Optional[float]                       # None while OPEN
    underlying: str = "NIFTY"
    expiry: Optional[str] = None
    closed_at: Optional[datetime] = None


@dataclass(frozen=True)
class Spread:
    id: int
    opened_at: datetime
    long_opt_type: Optional[str]
    lots: int
    max_loss: float
    net: Optional[float]                       # None while OPEN
    underlying: Optional[str] = "NIFTY"
    expiry: Optional[str] = None
    closed_at: Optional[datetime] = None
    identity: str = "contract"                 # contract | legacy
    unavailable: Optional[str] = None          # reason the spread cannot be paired


@dataclass(frozen=True)
class SignalOutcome:
    day: date
    single_id: Optional[int]
    spread_id: Optional[int]
    actual: Optional[float]
    variant: Optional[float]
    variant_lots: Optional[int]
    state: str = "CLOSED"                      # CLOSED | OPEN | UNAVAILABLE
    closed_at: Optional[datetime] = None
    reason: Optional[str] = None


def _pairable(single: Single, spread: Spread) -> bool:
    return (single.underlying == spread.underlying and single.opt_type == spread.long_opt_type
            and (single.expiry is None or spread.expiry is None or single.expiry == spread.expiry)
            and abs((single.entry_time - spread.opened_at).total_seconds()) <= PAIR_WINDOW_SEC)


def _last_close(*sides) -> Optional[datetime]:
    stamps = [side.closed_at for side in sides if side is not None and side.closed_at is not None]
    return max(stamps) if stamps else None


def pair_and_score(singles: Iterable[Single], spreads: Iterable[Spread],
                   max_lots: int = MANIFEST["max_lots"]) -> list[SignalOutcome]:
    """Pure: pair each spread with the naked option opened on the same signal, then score."""
    pending = sorted(singles, key=lambda s: s.entry_time)
    outcomes: list[SignalOutcome] = []
    for spread in sorted(spreads, key=lambda s: s.opened_at):
        if spread.unavailable or spread.long_opt_type is None:
            outcomes.append(SignalOutcome(spread.opened_at.date(), None, spread.id, spread.net, spread.net,
                                          spread.lots or None, "UNAVAILABLE", spread.closed_at,
                                          spread.unavailable or "ambiguous_long_type"))
            continue
        candidates = [s for s in pending if _pairable(s, spread)]
        match = min(candidates, key=lambda s: abs((s.entry_time - spread.opened_at).total_seconds()),
                    default=None)
        state = "OPEN" if spread.net is None or (match is not None and match.net is None) else "CLOSED"
        if match is None or spread.lots < 1 or spread.max_loss <= 0:
            outcomes.append(SignalOutcome(spread.opened_at.date(), None, spread.id, spread.net, spread.net,
                                          spread.lots or None, "OPEN" if spread.net is None else "CLOSED",
                                          spread.closed_at))
            continue
        pending.remove(match)
        per_lot_loss = spread.max_loss / spread.lots
        extra = int(match.max_loss // per_lot_loss) if per_lot_loss > 0 else 0
        lots = max(spread.lots, min(spread.lots + extra, max_lots))
        if state == "OPEN":
            outcomes.append(SignalOutcome(spread.opened_at.date(), match.id, spread.id, None, None, lots, "OPEN"))
            continue
        outcomes.append(SignalOutcome(spread.opened_at.date(), match.id, spread.id,
                                      match.net + spread.net, spread.net / spread.lots * lots, lots,
                                      "CLOSED", _last_close(match, spread)))
    outcomes += [SignalOutcome(s.entry_time.date(), s.id, None, s.net, s.net, None,
                               "OPEN" if s.net is None else "CLOSED", s.closed_at) for s in pending]
    return sorted(outcomes, key=lambda o: (o.day, o.single_id or 0, o.spread_id or 0))


def _max_drawdown(outcomes: list[SignalOutcome], attr: str) -> Optional[float]:
    """Largest peak-to-trough fall of the cumulative net, in close order."""
    ordered = sorted((o for o in outcomes if o.closed_at is not None),
                     key=lambda o: (o.closed_at, o.single_id or 0, o.spread_id or 0))
    if not ordered:
        return None
    cumulative = peak = drawdown = 0.0
    for outcome in ordered:
        cumulative += getattr(outcome, attr)
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    return round(drawdown, 2)


def _summary(outcomes: list[SignalOutcome]) -> dict:
    # Unpairable spreads still count in the book's net (actual = variant).
    closed = [o for o in outcomes if o.state != "OPEN" and o.actual is not None]
    paired = [o for o in closed if o.state == "CLOSED" and o.single_id is not None and o.spread_id is not None]

    def worst(values):
        return round(min(values), 2) if values else None

    return {
        "signals": len(closed), "paired": len(paired),
        "open": sum(o.state == "OPEN" for o in outcomes),
        "unavailable": sum(o.state == "UNAVAILABLE" for o in outcomes),
        "actual_net": round(sum(o.actual for o in closed), 2),
        "variant_net": round(sum(o.variant for o in closed), 2),
        "paired_actual_net": round(sum(o.actual for o in paired), 2),
        "paired_variant_net": round(sum(o.variant for o in paired), 2),
        "paired_actual_worst": worst([o.actual for o in paired]),
        "paired_variant_worst": worst([o.variant for o in paired]),
        "paired_actual_max_drawdown": _max_drawdown(paired, "actual"),
        "paired_variant_max_drawdown": _max_drawdown(paired, "variant"),
    }


def _when(raw) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(raw)) if raw else None
    except ValueError:
        return None


def _spread_identity(legs_json: str) -> dict:
    """Long option type, underlying and expiry of a spread's legs, or why not."""
    try:
        legs = json.loads(legs_json)
        longs = [leg["opt_type"] for leg in legs if float(leg["quantity"]) > 0]
        contracts = [leg.get("contract") for leg in legs]
    except (ValueError, TypeError, KeyError, AttributeError):
        return {"unavailable": "unreadable_legs"}
    if len(set(longs)) != 1:
        return {"unavailable": "ambiguous_long_type"}
    if not any(contracts):
        return {"long": longs[0], "underlying": LEGACY_SPREAD_UNDERLYING, "expiry": None, "identity": "legacy"}
    if not all(isinstance(c, dict) for c in contracts):
        return {"unavailable": "partial_contract_identity"}
    underlyings = {str(c.get("underlying") or "").upper() for c in contracts}
    expiries = {str(c.get("expiry") or "") for c in contracts}
    if len(underlyings) != 1 or "" in underlyings or len(expiries) != 1 or "" in expiries:
        return {"unavailable": "mixed_contract_identity"}
    return {"long": longs[0], "underlying": underlyings.pop(), "expiry": expiries.pop(), "identity": "contract"}


def _column(columns: set, name: str) -> str:
    return name if name in columns else "NULL"


def _load(db_path: str, source: str) -> tuple[list[Single], list[Spread]]:
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5.0) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        singles, spreads = [], []
        if "fno_positions" in tables:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(fno_positions)")}
            for row in conn.execute(
                    f"SELECT id, entry_time, opt_type, COALESCE({_column(cols, 'initial_max_loss_rupees')}, "
                    f"max_loss_rupees), pnl, status, {_column(cols, 'underlying')}, {_column(cols, 'expiry')}, "
                    f"{_column(cols, 'exit_time')} FROM fno_positions WHERE source=? "
                    "AND (status='OPEN' OR (status='CLOSED' AND pnl IS NOT NULL))", (source,)):
                closed = row[5] == "CLOSED"
                singles.append(Single(int(row[0]), datetime.fromisoformat(row[1]), str(row[2]),
                                      float(row[3] or 0.0), float(row[4]) if closed else None,
                                      str(row[6] or "NIFTY").upper(), str(row[7]) if row[7] else None,
                                      _when(row[8]) if closed else None))
        if "fno_dr_positions" in tables:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(fno_dr_positions)")}
            for row in conn.execute(
                    "SELECT id, opened_at, legs_json, lots, max_loss_rs, COALESCE(cash_pnl, pnl), status, "
                    f"{_column(cols, 'closed_at')} FROM fno_dr_positions WHERE source=? AND kind='DEBIT_SPREAD' "
                    "AND (status='OPEN' OR (status='CLOSED' AND COALESCE(cash_pnl, pnl) IS NOT NULL))",
                    (source,)):
                closed = row[6] == "CLOSED"
                ident = _spread_identity(row[2])
                spreads.append(Spread(int(row[0]), datetime.fromisoformat(row[1]), ident.get("long"),
                                      int(row[3] or 0), float(row[4] or 0.0), float(row[5]) if closed else None,
                                      ident.get("underlying"), ident.get("expiry"),
                                      _when(row[7]) if closed else None, ident.get("identity", "contract"),
                                      ident.get("unavailable")))
    return singles, spreads


def _row(outcome: SignalOutcome) -> dict:
    return outcome.__dict__ | {"day": outcome.day.isoformat(),
                               "closed_at": outcome.closed_at.isoformat() if outcome.closed_at else None}


def spread_tilt_report(db_path: Optional[str] = None, source: str = "FNO_PAPER") -> dict:
    """Read-only score of the frozen variant: forward (scored) and in-sample (context)."""
    singles, spreads = _load(db_path or settings.DB_PATH, source)
    outcomes = pair_and_score(singles, spreads, MANIFEST["max_lots"])
    forward = [o for o in outcomes if o.day >= SCORING_FROM]
    seen = [o for o in outcomes if o.day < SCORING_FROM]
    runtime_lots = int(getattr(settings, "FNO_DR_MAX_LOTS", MANIFEST["max_lots"]))
    return {"version": VERSION, "source": source, "scoring_from": SCORING_FROM.isoformat(),
            "manifest": MANIFEST, "manifest_fingerprint": MANIFEST_FINGERPRINT,
            "runtime_dr_max_lots": runtime_lots, "runtime_differs_from_manifest": runtime_lots != MANIFEST["max_lots"],
            "forward": _summary(forward), "in_sample_context": _summary(seen),
            "forward_signals": [_row(o) for o in forward],
            "can_place_orders": False}


def report_line(report: dict) -> str:
    """One line for the F&O hourly report."""
    f = report["forward"]
    if not f["paired"]:
        pending = f" ({f['open']} open)" if f.get("open") else ""
        return f"Shadow {VERSION}: no closed paired signal since {report['scoring_from']} yet{pending}"
    return (f"Shadow {VERSION} (more spread lots instead of the naked option), since "
            f"{report['scoring_from']}: paired {f['paired']} | actual Rs {f['paired_actual_net']:+,.0f} "
            f"vs variant Rs {f['paired_variant_net']:+,.0f} | worst {f['paired_actual_worst']:+,.0f} "
            f"vs {f['paired_variant_worst']:+,.0f} | max DD {_rs(f['paired_actual_max_drawdown'])} "
            f"vs {_rs(f['paired_variant_max_drawdown'])}")


def _rs(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:,.0f}"
