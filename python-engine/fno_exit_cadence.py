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

Arms (declared 2026-10-21, before any recorded session exists; amended
2026-10-22 [A22-R3] before any session was scored: arms are overrides on
the settings recorded with the looks; score only sessions recorded after
deployment, with at least 20 matched trades, and change a live rule only
with the owner):
  CURRENT          the settings in force when the position was held (bound
                   from the recorded looks, not from this process);
  LOCK_FIRST_LOOK  the lock sells on the first look under its floor (before SX-F1);
  LOCK_CONFIRMED   the lock needs a second look >= 8 s after the first (SX-F1);
  FNO_LOCK_OFF / FNO_LOCK_LATE_ARM / FNO_LOCK_LOOSE_KEEP  the O19-F1 lock arms.
Every arm starts from the live entry (price, time, stops, ATR) and is charged
with the same F&O cost schedule; the exit is at the bid (else LTP) of the
look that triggered it, as the live executor fills.

[A22-R3 2026-10-22] A position is scored only when its evidence is whole
(Oct 22 audit: a stored underlying_stop at ₹0 was counted as CURRENT's
+₹1,089.73 profit lock). Each is otherwise reported under ``skipped``:
  no_recorded_path            no looks for it;
  contract_mismatch           a look names another token or symbol;
  settings_unbound            the looks carry no recorded settings;
  settings_changed_mid_trade  two settings digests while it was held;
  path_ends_before_live_exit  the looks stop > 20 s before the live exit;
  observation_gap             the first look > 120 s after the entry, or a
                              gap > 120 s between looks while held;
  baseline_mismatch           CURRENT does not reproduce the stored exit
                              (same reason, within 20 s, premium within 1%
                              or ₹0.10); listed under ``mismatches``.
After the live exit the archive's quotes are used only while consecutive
quotes are <= 180 s apart (later quotes are not passed: an arm still open
then is unresolved), each with a front-future price no older than 180 s.
Totals and paired deltas against CURRENT count scored positions only.
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
AMENDED = "2026-10-22"
ARMS = {
    "CURRENT": {},
    "LOCK_FIRST_LOOK": {"FNO_PROFIT_LOCK_CONFIRM_SEC": 0.0},
    "LOCK_CONFIRMED": {"FNO_PROFIT_LOCK_CONFIRM_SEC": 8.0},
    "FNO_LOCK_OFF": {"FNO_PROFIT_LOCK_ENABLED": False},
    "FNO_LOCK_LATE_ARM": {"FNO_PROFIT_LOCK_ARM_R": 0.80},
    "FNO_LOCK_LOOSE_KEEP": {"FNO_PROFIT_LOCK_KEEP_FRACTION": 0.25},
}
PARITY_SECONDS = 20
PRICE_TOLERANCE_PCT, PRICE_TOLERANCE_RS = 0.01, 0.10
MAX_START_GAP_SEC = 120
MAX_LIVE_GAP_SEC = 120
MAX_ARCHIVE_GAP_SEC = 180
SKIP_REASONS = ("no_recorded_path", "contract_mismatch", "settings_unbound", "settings_changed_mid_trade",
                "path_ends_before_live_exit", "observation_gap", "baseline_mismatch")


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


def position_lines(lines: list[dict], position_id: int, source: str) -> list[dict]:
    return [line for line in lines if line.get("position_id") == position_id and line.get("source") == source]


def live_looks(lines: list[dict]) -> list[Look]:
    out = []
    for line in lines:
        at = _dt(line.get("at"))
        if at is None:
            continue
        out.append(Look(at, float(line.get("bid") or 0.0), float(line.get("ltp") or 0.0),
                        float(line["fut"]) if line.get("fut") else None, "LIVE_LOOP"))
    return sorted(out, key=lambda look: look.at)


def recorded_params(lines: list[dict]) -> tuple[Optional[dict], Optional[str]]:
    """(the exit settings in force, None) or (None, the skip reason)."""
    digests = {line.get("params_sha") for line in lines}
    if None in digests or not digests:
        return None, "settings_unbound"
    if len(digests) > 1:
        return None, "settings_changed_mid_trade"
    from fno_exit_paths import params_digest
    params = next((line["params"] for line in lines if isinstance(line.get("params"), dict)
                   and params_digest(line["params"]) == line["params_sha"]), None)
    if params is None or "FNO_HARD_FLAT_MIN" not in params:
        return None, "settings_unbound"
    return params, None


def _same_contract(lines: list[dict], position: dict) -> bool:
    return all(str(line.get("token")) == str(position.get("token"))
               and line.get("tradingsymbol") == position.get("tradingsymbol") for line in lines)


def _gapped(looks: list[Look], entry_at: Optional[datetime]) -> bool:
    if entry_at is not None and (looks[0].at - entry_at).total_seconds() > MAX_START_GAP_SEC:
        return True
    return any((b.at - a.at).total_seconds() > MAX_LIVE_GAP_SEC for a, b in zip(looks, looks[1:]))


def archive_looks(events: list[dict], token: int, symbol: str, underlying: str, day: date,
                  after: datetime) -> list[Look]:
    """The contract's archived quotes after ``after``, each with the latest
    front-future price at or before it (verified against the raw packets),
    up to the first gap longer than MAX_ARCHIVE_GAP_SEC."""
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
        elif str(spec.get("instrument_token")) != str(token) or spec.get("tradingsymbol") != symbol:
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
    out, previous = [], after
    for at, bid, ltp in sorted(options):
        if (at - previous).total_seconds() > MAX_ARCHIVE_GAP_SEC:
            break
        fut = next((px for f_at, px in reversed(fut_series)
                    if f_at <= at and (at - f_at).total_seconds() <= MAX_ARCHIVE_GAP_SEC), None)
        out.append(Look(at, bid, ltp, fut, "ARCHIVE"))
        previous = at
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


def reconciles(position: dict, current: dict) -> bool:
    """CURRENT reproduces the stored live exit: reason, time and premium."""
    live_at, live_premium = _dt(position.get("exit_time")), position.get("exit_premium")
    if current.get("unresolved") or live_at is None or live_premium is None:
        return False
    if current["exit_reason"] != position.get("exit_reason"):
        return False
    if abs((_dt(current["exit_at"]) - live_at).total_seconds()) > PARITY_SECONDS:
        return False
    tolerance = max(PRICE_TOLERANCE_RS, PRICE_TOLERANCE_PCT * float(live_premium))
    return abs(float(current["exit_premium"]) - float(live_premium)) <= tolerance


def evaluate(root: str | Path, *, start: str, end: str) -> dict:
    """Every closed single-leg position in [start, end]; scored only when whole."""
    import sqlite3
    from fno_exit_paths import read_day
    from intraday_spread_archive_adapter import read_archived_quote_events
    root = Path(root)
    con = sqlite3.connect(f"file:{(root / 'fno-replay.sqlite').resolve().as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM fno_positions WHERE status='CLOSED' AND entry_date>=? AND entry_date<=? "
        "ORDER BY entry_time", (start, end))]
    con.close()
    lines_by_day: dict = {}
    events_by_day: dict = {}
    results, mismatches = [], []
    totals = {arm: {"closed": 0, "unresolved": 0, "net_pnl": 0.0} for arm in ARMS}
    paired = {arm: {"both_resolved": 0, "delta_vs_current": 0.0} for arm in ARMS if arm != "CURRENT"}
    skipped = {reason: 0 for reason in SKIP_REASONS}
    for position in rows:
        day = position["entry_date"]
        if day not in lines_by_day:
            lines_by_day[day] = read_day(root, day)
        lines = position_lines(lines_by_day[day], position["id"], position["source"])
        looks = live_looks(lines)
        reason = None
        params = None
        live_exit = _dt(position.get("exit_time"))
        if not looks:
            reason = "no_recorded_path"
        elif not _same_contract(lines, position):
            reason = "contract_mismatch"
        else:
            params, reason = recorded_params(lines)
        if reason is None and live_exit is not None and (live_exit - looks[-1].at).total_seconds() > PARITY_SECONDS:
            reason = "path_ends_before_live_exit"
        if reason is None and _gapped(looks, _dt(position.get("entry_time"))):
            reason = "observation_gap"
        if reason is not None:
            skipped[reason] += 1
            continue
        if day not in events_by_day:
            events_by_day[day] = read_archived_quote_events(root, days=[day])
        after = archive_looks(events_by_day[day], int(position["token"]), str(position["tradingsymbol"]),
                              str(position.get("underlying") or "NIFTY").upper(), date.fromisoformat(day),
                              looks[-1].at)
        path = looks + after
        hard_flat_min = int(params["FNO_HARD_FLAT_MIN"])
        arms = {name: simulate(position, path, {**params, **overrides}, hard_flat_min=hard_flat_min)
                for name, overrides in ARMS.items()}
        live = {"exit_reason": position.get("exit_reason"), "exit_at": position.get("exit_time"),
                "exit_premium": position.get("exit_premium"), "net_pnl": position.get("pnl")}
        if not reconciles(position, arms["CURRENT"]):
            skipped["baseline_mismatch"] += 1
            mismatches.append({"position_id": position["id"], "tradingsymbol": position["tradingsymbol"],
                               "live": live, "current": arms["CURRENT"]})
            continue
        current = arms["CURRENT"]
        for name, out in arms.items():
            if out.get("unresolved"):
                totals[name]["unresolved"] += 1
                continue
            totals[name]["closed"] += 1
            totals[name]["net_pnl"] = round(totals[name]["net_pnl"] + out["net_pnl"], 2)
            if name != "CURRENT":
                paired[name]["both_resolved"] += 1
                paired[name]["delta_vs_current"] = round(
                    paired[name]["delta_vs_current"] + out["net_pnl"] - current["net_pnl"], 2)
        results.append({"position_id": position["id"], "tradingsymbol": position["tradingsymbol"],
                        "entry_time": position["entry_time"], "live": live,
                        "looks": {"live_loop": len(looks), "archive_after": len(after)}, "arms": arms})
    return {"declared": DECLARED, "amended": AMENDED, "window": {"start": start, "end": end},
            "scope": "exit-only experiment: every live entry, size and price is kept; only the exit rule differs",
            "coverage": {"closed_positions": len(rows), "scored": len(results)},
            "arms": totals, "paired": paired, "positions": results, "skipped": skipped, "mismatches": mismatches,
            "note": "Scored = whole evidence that reproduces the live exit; >= 20 scored trades before any rule "
                    "change."}


if __name__ == "__main__":  # pragma: no cover - research CLI
    import argparse
    import sys
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("--data", required=True)
    cli.add_argument("--start", required=True)
    cli.add_argument("--end", required=True)
    args = cli.parse_args()
    json.dump(evaluate(args.data, start=args.start, end=args.end), sys.stdout, indent=2, default=str)
