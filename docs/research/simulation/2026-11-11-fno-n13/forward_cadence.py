"""N13 forward check: the live paper book's exits on its own recorded 10-second looks, the lock on its live clock
(CURRENT) against the lock on one look a minute (MINUTE, fno_lock_cadence), from Oct 27 to Nov 11.

Declared Nov 11, after these sessions were recorded (FORWARD_CADENCE.md), and committed before it is run.
Built on fno_exit_cadence (live looks from fno_exit_paths, then the research archive's quotes of the same contract
after the live exit, to the first gap over 180 s) with two differences:
  - each look uses the exit settings recorded with it (the N012-A trend lock changes them between looks; the last
    recorded settings carry on after the live exit);
  - the arms are only CURRENT and MINUTE (CURRENT + FNO_PROFIT_LOCK_LOOK_SEC 55).
A position counts only when CURRENT reproduces its stored live exit (reason, within 20 s, premium within 1%).
Usage: python forward_cadence.py <root with fno-replay.sqlite, fno_exit_paths/, quotes/> [start] [end]
"""
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3] / "python-engine"))

import fno_exit_cadence as C  # noqa: E402
import fno_lock_cadence as L  # noqa: E402
from fno_costs import calc_fno_costs  # noqa: E402
from fno_exit_paths import params_digest, read_day  # noqa: E402
from intraday_spread_archive_adapter import read_archived_quote_events  # noqa: E402

MINUTE_SEC = 55.0


def per_look_params(lines):
    """[(look, params)] with each look's recorded settings (the latest recorded dict whose digest matches)."""
    known, out = {}, []
    for line in sorted(lines, key=lambda l: l.get("at") or ""):
        if isinstance(line.get("params"), dict):
            known[params_digest(line["params"])] = line["params"]
        params = known.get(line.get("params_sha"))
        at = C._dt(line.get("at"))
        if at is None:
            continue
        look = C.Look(at, float(line.get("bid") or 0.0), float(line.get("ltp") or 0.0),
                      float(line["fut"]) if line.get("fut") else None, "LIVE_LOOP")
        out.append((look, params))
    return out


def simulate(position, path, minute):
    state = C._state(position)
    entry_at = C._dt(position["entry_time"])
    qty = int(position["qty"])
    exchange = "BFO" if str(position.get("underlying") or "").upper() == "SENSEX" else "NFO"
    breach = look_at = None
    for look, params in path:
        if entry_at is not None and look.at < entry_at:
            continue
        p = {**params, L.LOOK_KEY: MINUTE_SEC} if minute else params
        hard = look.at.hour * 60 + look.at.minute >= int(params["FNO_HARD_FLAT_MIN"])
        decision, look_at = L.evaluate(state, now_ist=look.at, fut_price=look.fut, exit_px_basis=look.basis,
                                       hard_flat=hard, params=p, lock_breach_since=breach, lock_look_at=look_at)
        breach = decision.lock_breach_since
        if decision.persist_trail:
            state.trail_active = 1 if decision.trail_active else 0
            state.trail_stop_underlying = decision.trail_stop
            state.best_underlying = decision.best_underlying
        state.best_premium = decision.best_premium
        if decision.exit_reason and look.basis > 0:
            net = (look.basis - state.entry_premium) * qty - calc_fno_costs(state.entry_premium, look.basis, qty,
                                                                            exchange=exchange)
            return {"exit_reason": decision.exit_reason, "exit_at": look.at.isoformat(), "exit_premium": look.basis,
                    "net_pnl": round(net, 2), "observed_by": look.source}
    return {"exit_reason": None, "unresolved": True, "last_look": path[-1][0].at.isoformat() if path else None}


def main(root, start="2026-10-27", end="2026-11-11"):
    root = Path(root)
    con = sqlite3.connect(f"file:{(root / 'fno-replay.sqlite').resolve().as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM fno_positions WHERE status='CLOSED' AND entry_date>=? "
                                         "AND entry_date<=? ORDER BY entry_time", (start, end))]
    days, events, out, skipped = {}, {}, [], {}
    for pos in rows:
        day = pos["entry_date"]
        days.setdefault(day, read_day(root, day))
        lines = C.position_lines(days[day], pos["id"], pos["source"])
        reason = None
        if not lines:
            reason = "no_recorded_path"
        elif not C._same_contract(lines, pos):
            reason = "contract_mismatch"
        live = per_look_params(lines) if reason is None else []
        if reason is None and any(p is None or "FNO_HARD_FLAT_MIN" not in p for _, p in live):
            reason = "settings_unbound"
        looks = [l for l, _ in live]
        exit_at = C._dt(pos.get("exit_time"))
        if reason is None and exit_at is not None and (exit_at - looks[-1].at).total_seconds() > C.PARITY_SECONDS:
            reason = "path_ends_before_live_exit"
        if reason is None and C._gapped(looks, C._dt(pos.get("entry_time"))):
            reason = "observation_gap"
        if reason is not None:
            skipped[reason] = skipped.get(reason, 0) + 1
            out.append({"id": pos["id"], "symbol": pos["tradingsymbol"], "strategy": pos.get("strategy"),
                        "skipped": reason})
            continue
        events.setdefault(day, read_archived_quote_events(root, days=[day]))
        after = C.archive_looks(events[day], int(pos["token"]), str(pos["tradingsymbol"]),
                                str(pos.get("underlying") or "NIFTY").upper(), date.fromisoformat(day), looks[-1].at)
        path = live + [(a, live[-1][1]) for a in after]
        current, minute = simulate(pos, path, False), simulate(pos, path, True)
        row = {"id": pos["id"], "symbol": pos["tradingsymbol"], "strategy": pos.get("strategy"),
               "underlying": pos.get("underlying"), "lock_on": bool(live[0][1].get("FNO_PROFIT_LOCK_ENABLED")),
               "live": {"exit_reason": pos.get("exit_reason"), "exit_at": pos.get("exit_time"),
                        "exit_premium": pos.get("exit_premium"), "net_pnl": pos.get("pnl")},
               "current": current, "minute": minute, "looks": {"live": len(looks), "archive_after": len(after)}}
        row["reproduces"] = C.reconciles(pos, current)
        out.append(row)
    scored = [r for r in out if r.get("reproduces")]
    both = [r for r in scored if not r["current"].get("unresolved") and not r["minute"].get("unresolved")]
    changed = [r for r in both if r["minute"] != r["current"]]
    summary = {"window": [start, end], "closed": len(rows), "skipped": skipped,
               "baseline_mismatch": sum(1 for r in out if "reproduces" in r and not r["reproduces"]),
               "scored": len(scored), "both_resolved": len(both),
               "minute_unresolved": sum(1 for r in scored if r["minute"].get("unresolved")),
               "changed": len(changed),
               "delta_vs_current": round(sum(r["minute"]["net_pnl"] - r["current"]["net_pnl"] for r in both), 2),
               "lock_positions_scored": sum(1 for r in scored if r["lock_on"])}
    return {"summary": summary, "positions": out}


if __name__ == "__main__":
    result = main(*sys.argv[1:])
    print(json.dumps(result["summary"], indent=1))
    (HERE / "forward-cadence.json").write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
