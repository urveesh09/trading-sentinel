"""[SX-F1 2026-10-21] Single-leg F&O exit arms replayed at the live clock.

The full-book policy replay re-runs the book on the minute-scale research
archive, so it cannot show how an exit rule behaves on the live loop's
10-second looks (the profit lock was validated on 90-second samples and then
sold Oct 15's winner on one look). This evaluator keeps every live entry as
it was and replays declared exit arms on what the live loop itself saw
(``fno_exit_paths``: one line per look while the position was held), then on
the research archive's quotes of the same contract after the live exit, up
to the close. An arm still open when the observations end is ``unresolved``,
never filled at an invented price.

Arms (declared 2026-10-21, before any recorded session exists; score only
sessions recorded after deployment, with at least 20 matched trades, and
change a live rule only with the owner):
  CURRENT          the live ladder as configured (since SX-F1 the lock needs a
                   second look under its floor at least 8 s after the first);
  LOCK_FIRST_LOOK  the lock sells on the first look under its floor (before SX-F1);
  FNO_LOCK_OFF / FNO_LOCK_LATE_ARM / FNO_LOCK_LOOSE_KEEP  the O19-F1 lock arms.
Every arm starts from the live entry (price, time, stops, ATR) and is charged
with the same F&O cost schedule; the exit is at the bid (else LTP) of the
look that triggered it, as the live executor fills.

Parity: for each position the arm matching the live configuration should
reproduce the live exit (reason and time within one look). A position whose
recorded path does not end at the live exit is reported, not scored.
Research only: nothing here reads a broker or places an order.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import pytz

IST = pytz.timezone("Asia/Kolkata")
DECLARED = "2026-10-21"
ARMS = {
    "CURRENT": {},
    "LOCK_FIRST_LOOK": {"FNO_PROFIT_LOCK_CONFIRM_SEC": 0.0},
    "FNO_LOCK_OFF": {"FNO_PROFIT_LOCK_ENABLED": False},
    "FNO_LOCK_LATE_ARM": {"FNO_PROFIT_LOCK_ARM_R": 0.80},
    "FNO_LOCK_LOOSE_KEEP": {"FNO_PROFIT_LOCK_KEEP_FRACTION": 0.25},
}
PARITY_SECONDS = 20


@dataclass(frozen=True)
class Look:
    at: datetime
    bid: float
    ltp: float
    fut: Optional[float]
    source: str          # "LIVE_LOOP" or "ARCHIVE"

    @property
    def basis(self) -> float:
        return self.bid if self.bid > 0 else self.ltp


def _dt(value) -> Optional[datetime]:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.astimezone(IST) if parsed.tzinfo else IST.localize(parsed)


def live_looks(lines: list[dict], position_id: int, source: str) -> list[Look]:
    out = []
    for line in lines:
        if line.get("position_id") != position_id or line.get("source") != source:
            continue
        at = _dt(line.get("at"))
        if at is None:
            continue
        out.append(Look(at, float(line.get("bid") or 0.0), float(line.get("ltp") or 0.0),
                        float(line["fut"]) if line.get("fut") else None, "LIVE_LOOP"))
    return sorted(out, key=lambda look: look.at)


def archive_looks(events: list[dict], token: int, underlying: str, day: date, after: datetime) -> list[Look]:
    """The contract's archived quotes after ``after``, each with the latest
    front-future price at or before it (verified against the raw packets)."""
    from fno_exit_experiment import verify_archive_event
    options, futures = [], []
    front = None
    for event in events:
        spec = event.get("contract") or {}
        if spec.get("underlying") != underlying:
            continue
        kind = spec.get("instrument_type")
        if kind == "FUT":
            expiry = date.fromisoformat(spec["expiry"])
            if expiry >= day and (front is None or expiry < front):
                front = expiry
        if str(spec.get("instrument_token")) != str(token) and kind != "FUT":
            continue
        at = _dt(event.get("received_at_utc"))
        if at is None or at <= after:
            continue
        verified, _reason = verify_archive_event(event, token=int(spec["instrument_token"]),
                                                 symbol=spec.get("tradingsymbol"), max_age_seconds=300)
        if verified is None:
            continue
        if kind == "FUT":
            futures.append((at, date.fromisoformat(spec["expiry"]), float(event.get("ltp") or 0.0)))
        else:
            bids = event.get("buy_depth") or [{}]
            options.append((at, float((bids[0] or {}).get("price") or 0.0), float(event.get("ltp") or 0.0)))
    fut_series = sorted((at, px) for at, expiry, px in futures if expiry == front and px > 0)
    out = []
    for at, bid, ltp in sorted(options):
        fut = next((px for f_at, px in reversed(fut_series) if f_at <= at), None)
        out.append(Look(at, bid, ltp, fut, "ARCHIVE"))
    return out


def _state(position: dict) -> SimpleNamespace:
    return SimpleNamespace(
        direction=position["direction"], entry_time=position["entry_time"],
        entry_premium=float(position["entry_premium"]), entry_underlying=float(position["entry_underlying"]),
        stop_underlying=float(position["stop_underlying"]), target_underlying=float(position["target_underlying"]),
        premium_stop=float(position["premium_stop"]), atr_at_entry=float(position.get("atr_at_entry") or 0.0),
        trail_active=0, trail_stop_underlying=None, best_underlying=None, best_premium=None)


def simulate(position: dict, looks: list[Look], params: dict, *, hard_flat_min: int) -> dict:
    """One arm on one position: the first exit the ladder takes, or unresolved."""
    from fno_costs import calc_fno_costs
    from fno_exit_rules import evaluate_single_leg_exit
    state = _state(position)
    entry_at = _dt(position["entry_time"])
    qty = int(position["qty"])
    exchange = "BFO" if str(position.get("underlying") or "").upper() == "SENSEX" else "NFO"
    breach = None
    for look in looks:
        if entry_at is not None and look.at < entry_at:
            continue
        minute = look.at.hour * 60 + look.at.minute
        decision = evaluate_single_leg_exit(state, now_ist=look.at, fut_price=look.fut, exit_px_basis=look.basis,
                                            hard_flat=minute >= hard_flat_min, params=params,
                                            lock_breach_since=breach)
        breach = decision.lock_breach_since
        if decision.persist_trail:
            state.trail_active = 1 if decision.trail_active else 0
            state.trail_stop_underlying = decision.trail_stop
            state.best_underlying = decision.best_underlying
        state.best_premium = decision.best_premium
        if decision.exit_reason and look.basis > 0:
            entry = state.entry_premium
            net = (look.basis - entry) * qty - calc_fno_costs(entry, look.basis, qty, exchange=exchange)
            return {"exit_reason": decision.exit_reason, "exit_at": look.at.isoformat(),
                    "exit_premium": look.basis, "net_pnl": round(net, 2), "observed_by": look.source}
    return {"exit_reason": None, "unresolved": True,
            "last_look": looks[-1].at.isoformat() if looks else None}


def evaluate(root: str | Path, *, start: str, end: str) -> dict:
    """Every closed single-leg position in [start, end] with a recorded path."""
    import sqlite3
    from config import settings
    from fno_exit_paths import read_day
    from fno_exit_rules import live_single_leg_exit_params
    from intraday_spread_archive_adapter import read_archived_quote_events
    root = Path(root)
    con = sqlite3.connect(f"file:{(root / 'fno-replay.sqlite').resolve().as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM fno_positions WHERE status='CLOSED' AND entry_date>=? AND entry_date<=? "
        "ORDER BY entry_time", (start, end))]
    con.close()
    base = live_single_leg_exit_params(settings)
    lines_by_day: dict = {}
    events_by_day: dict = {}
    results, totals = [], {arm: {"closed": 0, "unresolved": 0, "net_pnl": 0.0} for arm in ARMS}
    skipped = {"no_recorded_path": 0, "path_ends_before_live_exit": 0}
    for position in rows:
        day = position["entry_date"]
        if day not in lines_by_day:
            lines_by_day[day] = read_day(root, day)
        looks = live_looks(lines_by_day[day], position["id"], position["source"])
        if not looks:
            skipped["no_recorded_path"] += 1
            continue
        live_exit = _dt(position.get("exit_time"))
        if live_exit is not None and (live_exit - looks[-1].at).total_seconds() > PARITY_SECONDS:
            skipped["path_ends_before_live_exit"] += 1
            continue
        if day not in events_by_day:
            events_by_day[day] = read_archived_quote_events(root, days=[day])
        after = archive_looks(events_by_day[day], int(position["token"]),
                              str(position.get("underlying") or "NIFTY").upper(), date.fromisoformat(day),
                              looks[-1].at)
        path = looks + after
        arms = {name: simulate(position, path, {**base, **overrides}, hard_flat_min=int(settings.FNO_HARD_FLAT_MIN))
                for name, overrides in ARMS.items()}
        for name, out in arms.items():
            if out.get("unresolved"):
                totals[name]["unresolved"] += 1
            else:
                totals[name]["closed"] += 1
                totals[name]["net_pnl"] = round(totals[name]["net_pnl"] + out["net_pnl"], 2)
        results.append({"position_id": position["id"], "tradingsymbol": position["tradingsymbol"],
                        "entry_time": position["entry_time"],
                        "live": {"exit_reason": position.get("exit_reason"), "exit_at": position.get("exit_time"),
                                 "exit_premium": position.get("exit_premium"), "net_pnl": position.get("pnl")},
                        "looks": {"live_loop": len(looks), "archive_after": len(after)}, "arms": arms})
    return {"declared": DECLARED, "window": {"start": start, "end": end}, "arms": totals, "positions": results,
            "skipped": skipped,
            "note": "Score only sessions recorded after deployment; >= 20 matched trades before any rule change."}


if __name__ == "__main__":  # pragma: no cover - research CLI
    import argparse
    import sys
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("--data", required=True)
    cli.add_argument("--start", required=True)
    cli.add_argument("--end", required=True)
    args = cli.parse_args()
    json.dump(evaluate(args.data, start=args.start, end=args.end), sys.stdout, indent=2, default=str)
