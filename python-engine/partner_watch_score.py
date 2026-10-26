"""[O26 2026-10-26] Do the check's warnings pick out the partner's losing trades? Scored on the trades the watch
stored, read-only.

    python -m partner_watch_score [FIRST_DAY [LAST_DAY]]     (default: FROZEN_FROM to the latest stored day)

Frozen on 2026-10-26 (O26), before any day it decides on. Owner's rules: freeze, then score; no tuning on a day
already seen; a result informs the owner and changes nothing by itself. [O26d] The rule is ``SPEC``, its own
numbers (not the live ones a check uses: changing those must not rewrite a score), named by ``SPEC_ID``, which
every result carries. Changing the rule is a new version, frozen again before the days it decides on.

Trades: ``partner_watch_trips`` rows that are closed and were bought that day (not carried in). The result is
after charges (``realised``, the watch's modelled charges, not the contract note); a trade whose fills came partly
from the orders (``exact`` 0) counts and each side says how many.

Warnings, from what the watch knew at the buy:
  CHASED_SPIKE       the 15-minute run before the buy (the plan's) at least SPEC spike_run_pct (20%)
  AFTER_LOSS         bought within SPEC after_loss_window_min (30 min) of a losing exit (the trade closed last
                     before the buy)
  BIGGER_AFTER_LOSS  that, and the opening order filled more units than the losing trade had
  UNUSUAL_SIZE       the opening order's filled value over the day's cash more than SPEC usual_size_mult (1.5x)
                     the partner's usual share
  ANY                any of them
[O26d] Each is POSITIVE, NEGATIVE (known not to apply) or UNKNOWN (an input missing: no plan run, no usual share
or cash, an opening order that could still fill more). A warning is compared POSITIVE against NEGATIVE only;
UNKNOWN trades are left out and counted (review R2: they had counted as unwarned). ANY is POSITIVE when one
is, NEGATIVE only when all four are, else UNKNOWN.
CHECKED (a check reply for the same option sent in the check_lookback_min, 15, minutes before the buy) is not a
warning: checked and unchecked trades are reported apart.

Verdict per warning, on decision days only (FROZEN_FROM on; Oct 26 is the day these were designed on, so it is
shown and never counted):
  SUPPORTED      all four hold:
                   1. at least min_warned (20) warned trades;
                   2. the warned trades' mean result is below the known-unwarned trades' mean;
                   3. the warned trades' total is negative (not taking them would have kept money);
                   4. it is still negative without the warned trades' single worst loss;
  TOO_FEW        under min_warned warned trades, or no known-unwarned trade;
  NOT_SUPPORTED  otherwise.
Twenty warned trades is the declared minimum for this description, not proof that a warning predicts losses or
saved money. A skipped trade's cash is taken as idle (not traded elsewhere). Nothing here says what the partner
would have done instead, and nothing here is about the system's own trading.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from typing import Optional

# [O26d] The frozen rule. Edit nothing here without a new version (SPEC_ID changes, and a test pins it).
SPEC = {
    "name": "partner_watch_score",
    "version": 2,
    "frozen_on": "2026-10-26",
    "frozen_from": "2026-10-27",
    "design_days": ["2026-10-26"],
    "spike_run_pct": 0.20,
    "after_loss_window_min": 30,
    "usual_size_mult": 1.5,
    "min_warned": 20,
    "check_lookback_min": 15,
    "cohort": "closed partner_watch_trips rows bought that day (carried=0); realised after modelled charges",
    "compare": "POSITIVE against NEGATIVE; UNKNOWN left out and counted",
    "any": "POSITIVE if one is; NEGATIVE only if all are; else UNKNOWN",
}
SPEC_ID = f"v{SPEC['version']}-" + hashlib.sha256(json.dumps(SPEC, sort_keys=True).encode()).hexdigest()[:12]
FROZEN_FROM = SPEC["frozen_from"]
DESIGN_DAYS = tuple(SPEC["design_days"])
MIN_WARNED = SPEC["min_warned"]
CHECK_LOOKBACK_MIN = SPEC["check_lookback_min"]
WARNINGS = ("CHASED_SPIKE", "AFTER_LOSS", "BIGGER_AFTER_LOSS", "UNUSUAL_SIZE", "ANY")
POSITIVE, NEGATIVE, UNKNOWN = "POSITIVE", "NEGATIVE", "UNKNOWN"


def _dt(value) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def evidence_of(trip: dict) -> dict:
    """Each warning's state at this trade's buy under SPEC (module doc)."""
    run = trip.get("run_pct")
    spike = UNKNOWN if run is None else POSITIVE if run >= SPEC["spike_run_pct"] else NEGATIVE
    prior = trip.get("prior_exit") or {}
    minutes, result = prior.get("minutes"), prior.get("result")
    if prior.get("state") == "NONE":
        after = NEGATIVE
    elif prior.get("state") not in ("KNOWN", "UNKNOWN") or minutes is None:
        after = UNKNOWN
    elif minutes >= SPEC["after_loss_window_min"] or (result is not None and result >= 0):
        after = NEGATIVE
    else:
        after = POSITIVE if result is not None else UNKNOWN
    final, qty = bool(trip.get("opening_final")), trip.get("opening_qty")
    if after != POSITIVE:
        bigger = after
    elif qty is None or prior.get("bought") is None:
        bigger = UNKNOWN
    elif qty > prior["bought"]:
        bigger = POSITIVE                          # fills only add: it stays bigger
    else:
        bigger = NEGATIVE if final else UNKNOWN
    usual, cash, value = trip.get("usual"), trip.get("cash"), trip.get("opening_value")
    if not usual or not cash or value is None:
        size = UNKNOWN
    elif value / cash > SPEC["usual_size_mult"] * usual:
        size = POSITIVE
    else:
        size = NEGATIVE if final else UNKNOWN
    out = {"CHASED_SPIKE": spike, "AFTER_LOSS": after, "BIGGER_AFTER_LOSS": bigger, "UNUSUAL_SIZE": size}
    states = set(out.values())
    out["ANY"] = POSITIVE if POSITIVE in states else NEGATIVE if states == {NEGATIVE} else UNKNOWN
    return out


def warnings_of(trip: dict) -> set:
    """The warnings that apply (POSITIVE) at this trade's buy."""
    return {name for name, state in evidence_of(trip).items() if state == POSITIVE}


COLS = ("session_date", "position_key", "tradingsymbol", "first_at", "realised", "exact", "run_pct", "prior_exit",
        "usual", "cash", "opening_qty", "opening_value", "opening_final")


def load(db_path: str, first_day: Optional[str] = None, last_day: Optional[str] = None) -> tuple:
    """(first_day, last_day, trades): the closed trades bought that day, each with its warnings' states and whether
    it was checked; read-only."""
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='partner_watch_trips'").fetchone():
            return first_day, last_day, []
        first_day = first_day or FROZEN_FROM
        last_day = last_day or db.execute("SELECT MAX(session_date) FROM partner_watch_trips").fetchone()[0] or first_day
        have = {row[1] for row in db.execute("PRAGMA table_info(partner_watch_trips)")}
        cols = [c if c in have else f"NULL AS {c}" for c in COLS]
        rows = db.execute(f"SELECT {', '.join(cols)} FROM partner_watch_trips WHERE session_date>=? AND "
                          "session_date<=? AND carried=0 AND realised IS NOT NULL ORDER BY session_date, first_at",
                          (first_day, last_day)).fetchall()
        checks = db.execute("SELECT session_date, context, COALESCE(sent_at, created_at) FROM partner_watch_messages "
                            "WHERE kind='CHECK' AND sent=1 AND session_date>=? AND session_date<=?",
                            (first_day, last_day)).fetchall() if rows else []
    finally:
        db.close()
    asked: dict = {}
    for day, context, at in checks:
        try:
            symbol = ((json.loads(context or "{}") or {}).get("contract") or {}).get("tradingsymbol")
        except ValueError:
            symbol = None
        when = _dt(at)
        if symbol and when is not None:
            asked.setdefault((day, symbol), []).append(when)
    trades = []
    for row in rows:
        trip = dict(zip(COLS, row))
        try:
            trip["prior_exit"] = json.loads(trip["prior_exit"]) if trip["prior_exit"] else None
        except ValueError:
            trip["prior_exit"] = None
        bought = _dt(trip["first_at"])
        trip["evidence"] = evidence_of(trip)
        trip["checked"] = bought is not None and any(
            bought - timedelta(minutes=CHECK_LOOKBACK_MIN) <= at <= bought
            for at in asked.get((trip["session_date"], trip["tradingsymbol"]), []))
        trades.append(trip)
    return first_day, last_day, trades


def _side(trades: list) -> dict:
    results = [t["realised"] for t in trades]
    return {"n": len(results), "won": sum(r > 0 for r in results), "total": round(sum(results), 2),
            "mean": round(sum(results) / len(results), 2) if results else None,
            "from_orders": sum(not t.get("exact", 1) for t in trades)}


def score(trades: list) -> dict:
    """Per warning: POSITIVE against NEGATIVE trades (decision days only), the UNKNOWN ones counted, and the verdict
    (module doc); also checked against unchecked. Trades before FROZEN_FROM (the design day among them) are counted
    apart, never scored. Every result carries SPEC_ID."""
    decided = [t for t in trades if t["session_date"] not in DESIGN_DAYS and t["session_date"] >= FROZEN_FROM]
    for trade in decided:
        trade.setdefault("evidence", evidence_of(trade))
    out = {"spec": SPEC_ID, "decision_trades": len(decided), "estimated": sum(not t["exact"] for t in decided),
           "days": sorted({t["session_date"] for t in decided}), "seen_trades": len(trades) - len(decided),
           "warnings": {}}
    for name in WARNINGS:
        warned = [t for t in decided if t["evidence"][name] == POSITIVE]
        unwarned = [t for t in decided if t["evidence"][name] == NEGATIVE]
        w, u = _side(warned), _side(unwarned)
        if w["n"] < MIN_WARNED or not u["n"]:
            verdict = "TOO_FEW"
        else:
            worst = min(t["realised"] for t in warned)
            checks = [w["mean"] < u["mean"], w["total"] < 0, w["total"] - worst < 0]
            verdict = "SUPPORTED" if all(checks) else "NOT_SUPPORTED"
        out["warnings"][name] = {"warned": w, "unwarned": u, "unknown": len(decided) - w["n"] - u["n"],
                                 "verdict": verdict}
    out["checked"] = _side([t for t in decided if t["checked"]])
    out["unchecked"] = _side([t for t in decided if not t["checked"]])
    return out


def _rupees(value: Optional[float]) -> str:
    return "-" if value is None else f"{'−' if value < 0 else '+'}₹{abs(value):,.0f}"


def _line(label: str, side: dict) -> str:
    return (f"{label} {side['n']} trades, {side['won']} won, total {_rupees(side['total'])}, "
            f"mean {_rupees(side['mean'])}" + (f" ({side['from_orders']} from the orders)" if side.get("from_orders")
                                               else ""))


def render(first_day: str, last_day: str, data: dict) -> str:
    lines = [f"Check warnings scored, {first_day} to {last_day} (frozen rule {data.get('spec', SPEC_ID)}; decision "
             f"days from {FROZEN_FROM})"]
    if not data["decision_trades"]:
        lines.append("No closed trade stored on a decision day yet.")
    else:
        lines.append(f"{data['decision_trades']} closed trades on {len(data['days'])} day"
                     f"{'s' if len(data['days']) != 1 else ''}"
                     + (f" ({data['estimated']} with fills from the orders)" if data["estimated"] else "") + ".")
        for name in WARNINGS:
            entry = data["warnings"][name]
            lines.append(f"  {name}: {entry['verdict']}")
            lines.append("    " + _line("warned:  ", entry["warned"]))
            lines.append("    " + _line("unwarned:", entry["unwarned"]))
            if entry["unknown"]:
                lines.append(f"    unknown:  {entry['unknown']} trades (an input missing at the buy): left out")
        lines.append("  " + _line("checked before the buy:  ", data["checked"]))
        lines.append("  " + _line("not checked before the buy:", data["unchecked"]))
    if data["seen_trades"]:
        lines.append(f"{data['seen_trades']} trades before {FROZEN_FROM} (seen while designing): never scored.")
    lines.append(f"A verdict needs at least {MIN_WARNED} warned trades and informs the owner; it changes nothing. "
                 "Results are after modelled charges, not the contract note.")
    return "\n".join(lines)


def main(argv: list) -> int:
    from config import settings
    first_day, last_day, trades = load(settings.DB_PATH, argv[1] if len(argv) > 1 else None,
                                       argv[2] if len(argv) > 2 else None)
    print(render(first_day or FROZEN_FROM, last_day or first_day or FROZEN_FROM, score(trades)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
