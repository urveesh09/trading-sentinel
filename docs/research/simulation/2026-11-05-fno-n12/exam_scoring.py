"""Score the frozen N012 gates from in-memory replay trades."""

from collections import defaultdict
from decimal import Decimal


ZERO = Decimal(0)
IDENTITY = ("tradingsymbol", "entry_time")
TERMS = ("entry_qty", "lots_at_exit", "entry_premium", "exit_time", "exit_premium", "exit_reason", "net_pnl")


def index(trades):
    rows = {}
    for row in trades:
        key = tuple(row[name] for name in IDENTITY)
        if key in rows:
            raise ValueError(f"Duplicate trade identity: {key}")
        rows[key] = row
    return rows


def summarize(trades, bankroll):
    daily = defaultdict(Decimal)
    closed = sorted((row for row in trades if row["status"] == "CLOSED"),
                    key=lambda row: row["exit_time"])
    equity = peak = bankroll
    drawdown = drawdown_pct = ZERO
    for row in closed:
        net = Decimal(str(row["net_pnl"]))
        daily[row["exit_time"][:10]] += net
        equity += net
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
        drawdown_pct = max(drawdown_pct, 100 * (peak - equity) / peak)
    total = equity - bankroll
    worst = min(ZERO, *daily.values()) if daily else ZERO
    return {
        "net": total,
        "daily": dict(daily),
        "worst_day": worst,
        "closed_drawdown": drawdown,
        "drawdown_pct": drawdown_pct,
        "net_to_drawdown": total / drawdown if drawdown else None,
        "net_to_worst_day": total / -worst if worst else None,
        "closed": len(closed),
        "unresolved": len(trades) - len(closed),
    }


def score(control, candidate, doubled_control, doubled_candidate, freeze):
    bankroll = Decimal(str(freeze["historical_bankroll"]))
    rows = [index(trades) for trades in (control, candidate, doubled_control, doubled_candidate)]
    native, challenger, stressed_native, stressed_challenger = [
        summarize(book.values(), bankroll) for book in rows
    ]
    native_rows, challenger_rows = rows[:2]
    changed = native_rows.keys() ^ challenger_rows.keys()
    for key in native_rows.keys() & challenger_rows.keys():
        if any(native_rows[key].get(field) != challenger_rows[key].get(field) for field in TERMS):
            changed.add(key)

    days = native["daily"].keys() | challenger["daily"].keys()
    increments = {day: challenger["daily"].get(day, ZERO) - native["daily"].get(day, ZERO)
                  for day in sorted(days)}
    best = max(increments, key=increments.get, default=None)
    best_delta = increments.get(best, ZERO)
    net = challenger["net"] - native["net"]
    ex_best = net - best_delta
    doubled_net = stressed_challenger["net"] - stressed_native["net"]
    gates = {
        "positive_net": net > ZERO,
        "positive_ex_best_day": ex_best > ZERO,
        "worst_day": native["worst_day"] - challenger["worst_day"] <=
        Decimal(str(freeze["max_extra_worst_day_loss"])),
        "closed_drawdown": challenger["drawdown_pct"] - native["drawdown_pct"] <=
        Decimal(str(freeze["max_extra_closed_drawdown_pp"])),
        "positive_doubled_cost_net": doubled_net > ZERO,
    }
    summaries = {"control": native, "candidate": challenger,
                 "doubled_control": stressed_native, "doubled_candidate": stressed_challenger}
    if any(result["unresolved"] for result in summaries.values()):
        verdict = "incomplete"
    elif len(changed) < freeze["minimum_changed_trades"]:
        verdict = "insufficient"
    else:
        verdict = "pass" if all(gates.values()) else "fail"
    return {"verdict": verdict, "gates": gates, "changed_trades": len(changed),
            "net_delta": net, "best_day": best, "best_day_delta": best_delta,
            "ex_best_day_delta": ex_best, "doubled_cost_delta": doubled_net,
            "summaries": summaries}
